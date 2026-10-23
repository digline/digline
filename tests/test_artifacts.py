"""The files that are the thing under test, recorded with the run.

The centrepiece is `test_two_dirty_prompts_stay_distinguishable`, which is the
measurement friction 24 was opened on: while a prompt is being tuned the tree is
dirty, every run says `-dirty`, and before this the run files of two different
prompts were identical documents. The rest guards the boundary — a prompt is the
software house's file and the end company's rules at once, so it leaves only
where the suite said it may (ADR 0003).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from html import unescape
from pathlib import Path
from typing import cast

import pytest
from tests._helpers import baseline_in, cli, git

from digline.core import (
    NOTHING_EXTRA,
    Artifact,
    CaseResult,
    Comparison,
    Contains,
    Disclosure,
    Run,
    Score,
    Verdict,
    artifacts_sha,
    compare,
    redact,
    withhold_artifacts,
)
from digline.core.run import SCHEMA_VERSION, run_from_json, run_to_json
from digline.host import read_artifacts
from digline.report import (
    Headline,
    Locale,
    artifact_lines,
    diff_lines,
    headline,
    phrase,
    render_html,
)
from digline.run import Case, Response, Suite, execute
from digline.store import FileResultStore
from digline.wire import compare_json, exit_code
from digline.wire.run import run_document

SUITE = """\
from pathlib import Path

from digline.core import Contains, Disclosure
from digline.run import Case, Response, Suite

PROMPT = Path(__file__).parent / "prompt.md"

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="capital-it")],
    artifacts=[Path("prompt.md")],
    disclosure=Disclosure(%(disclosure)s),
)


def target(case):
    return Response(output=PROMPT.read_text(encoding="utf-8"), cost_usd=0.01)
"""


#: What a commit's SHA is made of besides the tree: two dates, and whatever the
#: machine's git configuration adds (a `commit.gpgsign` puts a signature, and
#: its clock, into the object). Every one of them is pinned, so the SHA is the
#: same on every run. The run document carries that SHA, and a test that looks
#: for four chosen digits in a document must not find them in forty hex
#: characters nobody chose. The timestamps are the other such source, and the
#: redaction test takes them out itself.
PINNED_GIT = {
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository with a prompt beside the suite, committed once."""
    for name, value in PINNED_GIT.items():
        monkeypatch.setenv(name, value)
    root = tmp_path / "project"
    root.mkdir()
    (root / "suite.py").write_text(SUITE % {"disclosure": ""}, encoding="utf-8")
    (root / "prompt.md").write_text(
        "Answer with Rome. Version one.\n", encoding="utf-8"
    )
    git(root, "init")
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-m", "first")
    return root


def stored(root: Path, key: str) -> Run:
    store = FileResultStore(root)
    from digline.store import RunRef

    return store.read_run(RunRef(tenant="acme-bank", suite="qa", key=key))


def run_once(root: Path) -> str:
    done = cli(root, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


# --------------------------------------------------------------------------- #
# Friction 24, reproduced and closed
# --------------------------------------------------------------------------- #


def test_two_dirty_prompts_stay_distinguishable(project: Path) -> None:
    """The measurement this feature exists for.

    Two runs, one uncommitted edit between them, nothing else. Before artifacts
    both run files said `-dirty` and were otherwise identical documents: which
    prompt produced which set of verdicts was unrecoverable an hour later.
    """
    # Both runs from an uncommitted tree, which is the condition this happens
    # in: nobody commits between two attempts at a prompt.
    (project / "prompt.md").write_text("Rome, one line. Take one.\n", encoding="utf-8")
    first = run_once(project)
    (project / "prompt.md").write_text("Rome, briefly. Take two.\n", encoding="utf-8")
    second = run_once(project)

    one, two = stored(project, first), stored(project, second)
    # Both are from a dirty tree, so the commit cannot tell them apart...
    assert one.git_commit is not None and one.git_commit.endswith("-dirty")
    assert one.git_commit == two.git_commit
    # ...and the configuration cannot either: a prompt is not a rule.
    assert one.config_hash == two.config_hash
    # The artifacts can.
    assert one.artifacts["prompt.md"].sha != two.artifacts["prompt.md"].sha
    assert artifacts_sha(one.artifacts) != artifacts_sha(two.artifacts)


def test_the_prompt_is_reproducible_from_the_run_file_alone(project: Path) -> None:
    """Not merely distinguishable: recoverable. A digest says two runs differ; it
    does not say what the difference was, and the reader weeks later needs the
    text, not the fact that there was one."""
    key = run_once(project)
    (project / "prompt.md").write_text("something else entirely\n", encoding="utf-8")

    path = project / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    recovered = document["artifacts"]["prompt.md"]["text"]
    assert recovered == "Answer with Rome. Version one.\n"
    assert (
        document["artifacts"]["prompt.md"]["sha"]
        == hashlib.sha256(recovered.encode("utf-8")).hexdigest()
    )


def test_a_missing_artifact_is_refused_rather_than_recorded_as_absent(
    project: Path,
) -> None:
    """The declared file is the evidence. A run that quietly recorded none would
    be missing it exactly when it matters."""
    (project / "prompt.md").unlink()
    done = cli(project, "run", "--suite", "suite.py")
    assert done.returncode != 0
    assert "prompt.md" in done.stderr


# --------------------------------------------------------------------------- #
# What a declaration accepts
# --------------------------------------------------------------------------- #


def declaring(artifacts: object) -> Suite:
    return Suite(
        tenant="acme-bank",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="capital-it")],
        artifacts=cast("Sequence[Path]", artifacts),
    )


def test_a_str_is_the_path_it_meant(tmp_path: Path) -> None:
    """`artifacts=["prompt.md"]` is what a reader writes, and it used to travel
    as a `str` until `read_artifacts` asked it whether it was absolute."""
    (tmp_path / "prompt.md").write_text("Answer with Rome.\n", encoding="utf-8")
    suite = declaring(["prompt.md"])
    assert suite.artifacts == (Path("prompt.md"),)
    assert set(read_artifacts(suite, object(), tmp_path)) == {"prompt.md"}


def test_the_two_forms_of_the_same_file_are_one_declaration() -> None:
    """Coerced before the duplicate check, or the same prompt would be declared
    twice under two spellings and stored under one key."""
    with pytest.raises(ValueError, match="same artifact twice"):
        declaring(["prompt.md", Path("prompt.md")])


def test_what_cannot_be_a_path_is_refused_by_field_name() -> None:
    """The fallback the loader's errors model: which suite, which field, what
    was given. Refused at construction, where the mistake was written."""
    with pytest.raises(ValueError) as raised:
        declaring([Path("prompt.md"), 3])
    message = str(raised.value)
    assert "`artifacts`" in message and "qa" in message
    assert "int" in message and "entry 1" in message


def test_a_bare_string_is_not_a_list_of_one() -> None:
    """A `str` is a `Sequence` — of characters — so this is the one wrong value
    the rule would otherwise accept enthusiastically, as nine one-letter paths."""
    with pytest.raises(ValueError, match="`artifacts`"):
        declaring("prompt.md")


def test_what_is_not_a_list_at_all_is_named_too() -> None:
    """Or it would leave as a bare `TypeError` from the loop, which names the
    field no better than the `AttributeError` this replaces."""
    with pytest.raises(ValueError, match="`artifacts`"):
        declaring(3)


# --------------------------------------------------------------------------- #
# The boundary
# --------------------------------------------------------------------------- #


def a_run(**artifacts: Artifact) -> Run:
    return Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="h",
        created_at="2026-08-26T10:00:00+00:00",
        artifacts=dict(artifacts),
    )


def test_by_default_the_prompt_does_not_leave() -> None:
    """A prompt is written for an end company and is where its rules end up. The
    rule from ADR 0002 §3 holds without an exception: redacting without knowing
    the policy discloses less, never more."""
    run = a_run(prompt=Artifact(sha="a" * 64, text="eligibility: over 65 only"))
    out = redact(run).artifacts["prompt"]
    assert out.text is None
    assert out.withheld is True
    assert out.sha == ""


def test_the_digest_does_not_leave_either() -> None:
    """A digest is a verifier, not a summary.

    Prompts live in a small guessable space — the software house wrote the
    template and the customer tuned the numbers — so a leaked digest recovers
    the text, and with it the end company's rules. Demonstrated rather than
    asserted, because "it is a fingerprint" is the kind of claim that gets
    waved through. (ADR 0003 §4)
    """
    template = "Escalate above {amount} EUR after {days} days."
    secret = template.format(amount=2500, days=90)
    run = a_run(prompt=Artifact(sha=hashlib.sha256(secret.encode()).hexdigest()))

    leaked = run_to_json(redact(run))
    assert secret not in leaked
    # And no digest to hash candidates against, which is the part that matters:
    # with one, this loop finds the rule in milliseconds.
    for amount in range(0, 3001, 500):
        for days in range(0, 121, 30):
            candidate = template.format(amount=amount, days=days)
            assert hashlib.sha256(candidate.encode()).hexdigest() not in leaked


def test_a_suite_can_opt_in_and_it_is_one_line() -> None:
    run = a_run(prompt=Artifact(sha="a" * 64, text="eligibility: over 65 only"))
    out = redact(run, Disclosure(artifacts=True)).artifacts["prompt"]
    assert out.text == "eligibility: over 65 only"
    assert out.withheld is False


def test_withheld_and_never_declared_are_different_facts() -> None:
    """A reader must be able to tell "this suite kept it back" from "this run
    had none", and an empty map says only the second."""
    withheld = redact(a_run(prompt=Artifact(sha="a" * 64, text="x"))).artifacts
    assert withheld["prompt"].withheld is True
    assert redact(a_run()).artifacts == {}
    # Absent, not emptied: fixed decision 9 applies to the digest too.
    document = json.loads(run_to_json(redact(a_run(prompt=Artifact(sha="a" * 64)))))
    assert document["artifacts"]["prompt"] == {"withheld": True}


def test_an_artifact_cannot_claim_to_be_withheld_and_carry_its_text() -> None:
    """Same family as `Run.redacted`: a flag that announces a guarantee nothing
    provides is worse than no flag."""
    with pytest.raises(ValueError, match="withheld"):
        Artifact(sha="a" * 64, text="still here", withheld=True)


def test_redaction_survives_the_round_trip() -> None:
    run = redact(a_run(prompt=Artifact(sha="a" * 64, text="secret")))
    back = run_from_json(run_to_json(run))
    assert back.artifacts["prompt"].text is None
    assert back.artifacts["prompt"].sha == ""
    assert back.artifacts["prompt"].withheld is True
    assert "secret" not in run_to_json(run)


def test_a_complete_artifact_still_needs_its_digest() -> None:
    """Empty only where there is nothing to put in it. A recorded file nobody
    can identify is not a record."""
    with pytest.raises(ValueError, match="sha"):
        Artifact(text="present but unidentifiable")


def test_a_redacted_run_carries_no_label() -> None:
    """`artifacts_sha` has no digests to build from, and a label computed from
    their absence would be identical on every redacted run."""
    assert artifacts_sha(redact(a_run(prompt=Artifact(sha="a" * 64))).artifacts) == ""


# --------------------------------------------------------------------------- #
# What the comparison says
# --------------------------------------------------------------------------- #


def test_a_changed_prompt_is_reported_beside_the_scores() -> None:
    before = a_run(prompt=Artifact(sha="a" * 64, text="v1"))
    after = a_run(prompt=Artifact(sha="b" * 64, text="v2"))
    result = compare(after, before)
    assert result.artifacts_changed
    (delta,) = result.artifact_deltas
    assert (delta.outcome, delta.before, delta.after) == ("changed", "v1", "v2")


def test_a_withheld_prompt_cannot_say_whether_it_moved() -> None:
    """The price of dropping the digest, stated rather than hidden.

    `same` would be a guess dressed as a finding and `changed` would be another,
    so the outcome is `unknown` and the sentence says so.
    """
    before = a_run(prompt=Artifact(sha="a" * 64, text="v1"))
    after = redact(a_run(prompt=Artifact(sha="b" * 64, text="v2")))
    result = compare(after, before)
    (delta,) = result.artifact_deltas
    assert delta.outcome == "unknown"
    assert delta.after is None and delta.withheld is True
    # And it is not reported as a change, which would be a fact nobody has.
    assert not result.artifacts_changed


def test_an_unchanged_prompt_is_not_a_change() -> None:
    same = Artifact(sha="a" * 64, text="v1")
    result = compare(a_run(prompt=same), a_run(prompt=same))
    assert not result.artifacts_changed
    assert result.artifact_deltas[0].outcome == "same"


def test_the_prompt_is_not_part_of_the_configuration(project: Path) -> None:
    """Changing a prompt must leave the runs comparable: that comparison is the
    experiment. Folding artifacts into `config_hash` would refuse it."""
    first = stored(project, run_once(project))
    (project / "prompt.md").write_text("a different prompt\n", encoding="utf-8")
    second = stored(project, run_once(project))
    assert first.config_hash == second.config_hash
    # And therefore the verdicts still pair, rather than becoming new + missing.
    assert all(d.outcome != "new" for d in compare(second, first).deltas)


# --------------------------------------------------------------------------- #
# The schema
# --------------------------------------------------------------------------- #


def test_a_run_without_artifacts_is_unchanged_but_for_the_empty_map() -> None:
    document = json.loads(run_to_json(a_run()))
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["artifacts"] == {}


def test_a_schema_six_file_is_migrated_by_declaring_none(project: Path) -> None:
    """Additive, and nothing is reconstructed: the prompt of a run from last
    month is not recoverable and must not be invented."""
    key = run_once(project)
    path = project / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["artifacts"]
    document["schema_version"] = 6
    path.write_text(json.dumps(document), encoding="utf-8")

    done = cli(project, "migrate", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    assert "1 migrated" in done.stdout
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert migrated["artifacts"] == {}


# --------------------------------------------------------------------------- #
# The diff: what changed, not merely that it did
# --------------------------------------------------------------------------- #

PROMPT_V1 = """\
You are Northwind Support.
Answer the customer in at most three sentences.
Escalate the ticket when the refund exceeds 2500 EUR.
Sign off as Northwind Support.
"""
REMOVED = "Escalate the ticket when the refund exceeds 2500 EUR."
ADDED = "Escalate the ticket when the refund exceeds 1000 EUR."
PROMPT_V2 = PROMPT_V1.replace(REMOVED, ADDED)


def two_versions(v1: str = PROMPT_V1, v2: str = PROMPT_V2) -> tuple[Run, Run]:
    return (
        a_run(prompt=Artifact(sha="a" * 64, text=v1)),
        a_run(prompt=Artifact(sha="b" * 64, text=v2)),
    )


def test_the_report_carries_the_line_taken_out_and_the_line_put_in() -> None:
    """The requirement in one sentence: a reader must be able to see the change,
    not be told there was one."""
    before, after = two_versions()
    document = render_html(
        compare(after, before), after, before, locale="en", declared=None
    )
    assert REMOVED in document
    assert ADDED in document
    # As a diff, not as two paragraphs: the signs are what make it readable.
    assert f'<span class="d-del">-{REMOVED}' in document
    assert f'<span class="d-add">+{ADDED}' in document
    # With context around it, which is what makes a one-line change locatable.
    assert '<span class="d-ctx"> You are Northwind Support.</span>' in document


def test_the_redacted_report_carries_neither() -> None:
    """The other half of the requirement. `report --redacted` is exercised end
    to end in `test_cli`; here the rendering is checked directly, because this
    is the assertion that must never quietly stop being true."""
    before, after = two_versions()
    withheld = withhold_artifacts(compare(after, before))
    document = render_html(withheld, redact(after), before, locale="en", declared=None)

    assert REMOVED not in document
    assert ADDED not in document
    assert "2500" not in document and "1000" not in document
    # Not the digest either, and not even the path.
    assert "a" * 64 not in document and "b" * 64 not in document
    assert "prompt" not in document
    # What it does say: how many, and nothing else.
    assert "1 file under test changed" in document
    # The elements, not the stylesheet: `.d-del` is in the CSS on every page.
    assert '<span class="d-del">' not in document
    assert '<pre class="diff">' not in document


def test_a_small_diff_opens_and_a_large_one_does_not() -> None:
    """Thirty lines is where a diff stops being something you read in passing.
    Below it the reader came for exactly this; above it they came for the
    scores and the prompt was rewritten."""
    small_before, small_after = two_versions()
    small = render_html(
        compare(small_after, small_before),
        small_after,
        small_before,
        locale="en",
        declared=None,
    )
    assert "<details open><summary><code>prompt</code>" in small

    wide_v1 = "\n".join(f"line {i}" for i in range(40))
    wide_v2 = "\n".join(f"changed {i}" for i in range(40))
    big_before, big_after = two_versions(wide_v1, wide_v2)
    big = render_html(
        compare(big_after, big_before),
        big_after,
        big_before,
        locale="en",
        declared=None,
    )
    # Scoped to the section: the report's own sections are `<details open>` too.
    section = big.split('<section class="artifacts">')[1].split("</section>")[0]
    assert "<details><summary><code>prompt</code>" in section
    assert "<details open>" not in section


def test_the_terminal_says_it_compactly() -> None:
    """A terminal summary that unrolled a prompt would bury the regressions it
    exists to point at."""
    before, after = two_versions()
    (line,) = artifact_lines(compare(after, before), locale="en")
    assert line == "prompt · +1 −1 lines"
    assert REMOVED not in line


def test_the_terminal_says_nothing_when_the_artifact_was_withheld() -> None:
    before, after = two_versions()
    withheld = withhold_artifacts(compare(after, before))
    assert artifact_lines(withheld, locale="en") == ()


def test_an_added_or_removed_artifact_has_no_diff_to_show() -> None:
    """A diff against nothing is the whole file, and a report is not the place
    to print one."""
    before = a_run()
    after = a_run(prompt=Artifact(sha="b" * 64, text=PROMPT_V2))
    (delta,) = compare(after, before).artifact_deltas
    assert delta.outcome == "new"
    assert diff_lines(delta) == []


def test_report_redacted_is_the_path_that_has_to_be_right(project: Path) -> None:
    """The rendering is tested above; this is the command a person runs.

    `report --redacted` redacts the run and *then* compares, so the artifact
    outcomes have to be computed before that and stripped of their payload —
    otherwise the document either leaks the prompt or loses the count. Both
    failures are silent, which is why this goes end to end.
    """
    (project / "prompt.md").write_text(PROMPT_V1, encoding="utf-8")
    run_once(project)
    assert (
        cli(
            project,
            "promote",
            "--replacing",
            baseline_in(project),
            "--suite",
            "suite.py",
            "--run",
            "latest",
        ).returncode
        == 0
    )
    (project / "prompt.md").write_text(PROMPT_V2, encoding="utf-8")
    run_once(project)

    complete = project / "complete.html"
    assert (
        cli(
            project,
            "report",
            "--suite",
            "suite.py",
            "--run",
            "latest",
            "--locale",
            "en",
            "--out",
            str(complete),
        ).returncode
        == 0
    )
    shown = complete.read_text(encoding="utf-8")
    assert REMOVED in shown and ADDED in shown

    hidden_path = project / "redacted.html"
    assert (
        cli(
            project,
            "report",
            "--suite",
            "suite.py",
            "--run",
            "latest",
            "--locale",
            "en",
            "--redacted",
            "--out",
            str(hidden_path),
        ).returncode
        == 0
    )
    hidden = hidden_path.read_text(encoding="utf-8")
    assert REMOVED not in hidden and ADDED not in hidden
    # The commit's SHA is pinned by the fixture, which is what keeps forty hex
    # characters from carrying "2500" — once, at `a462500aee…`, they did.
    # The timestamps come out first, and that is not fastidiousness: this run
    # was stamped by the real clock, and the microseconds of an ISO timestamp
    # are four digits nobody chose — `…T14:11:03.525004+00:00` contains "2500".
    # Left in, this gate reds once in a few thousand runs over a coincidence
    # that says nothing about redaction, which is the worst way for a
    # redaction test to fail: on a release day, and unreproducibly.
    body = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:.+-]+", "", hidden)
    assert "2500" not in body and "1000" not in body
    assert "prompt.md" not in hidden
    # And still says how many, which is a measurement and travels.
    assert "1 file under test changed" in hidden


def test_the_opt_in_shows_the_diff_in_a_redacted_report(project: Path) -> None:
    """`Disclosure(artifacts=True)` is the one line that changes it, and it has
    to actually change it — a flag that quietly does nothing is worse than no
    flag."""
    (project / "suite.py").write_text(
        SUITE % {"disclosure": "artifacts=True"}, encoding="utf-8"
    )
    (project / "prompt.md").write_text(PROMPT_V1, encoding="utf-8")
    run_once(project)
    cli(
        project,
        "promote",
        "--replacing",
        baseline_in(project),
        "--suite",
        "suite.py",
        "--run",
        "latest",
    )
    (project / "prompt.md").write_text(PROMPT_V2, encoding="utf-8")
    run_once(project)

    out = project / "opted-in.html"
    assert (
        cli(
            project,
            "report",
            "--suite",
            "suite.py",
            "--run",
            "latest",
            "--locale",
            "en",
            "--redacted",
            "--out",
            str(out),
        ).returncode
        == 0
    )
    document = out.read_text(encoding="utf-8")
    assert REMOVED in document and ADDED in document
    # The rest of the redaction is untouched by the opt-in.
    assert "Not included in this report" in document


# --------------------------------------------------------------------------- #
# The artifact that must not drift (ADR 0029)
# --------------------------------------------------------------------------- #
#
# **A negative assertion needs a token that cannot occur for another reason.**
# Paid for here: `assert "acme" not in document` was written to prove a pinned
# path had not leaked, and the tenant is `acme-bank`, printed in every report
# header. It tested the header and not the pin.
#
# That one was caught only because the polarity was noisy — it failed, loudly,
# on the first run. **The same slip in an `assert x in document` passes green
# forever**, because a substring that appears for an unrelated reason satisfies
# it just as well as the fact under test. So pick the token that can only come
# from the thing being asserted: a path segment no tenant, suite, environment or
# boilerplate string shares. The tests below use `underwriting` for exactly that
# reason, and it is not an aesthetic choice.


#: One judged case. A run with no case judged nothing, and since ADR 0049 that
#: exits 2 and is never promoted, so a fixture about something else carries
#: one rather than test that by accident. (ADR 0049 §3)
JUDGED = CaseResult(
    "judged",
    (
        Verdict(
            score=Score(name="contains", score=1.0),
            threshold=1.0,
            status="pass",
            reason="found",
            assertion_id="contains-1",
        ),
    ),
)


def a_pinned_run(pinned: tuple[str, ...], **artifacts: Artifact) -> Run:
    """`a_run`, plus the declaration that some of those paths must not drift."""
    return Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="h",
        created_at="2026-08-26T10:00:00+00:00",
        results=(JUDGED,),
        artifacts=dict(artifacts),
        pinned=pinned,
    )


def test_a_pinned_path_that_moved_is_a_fact_of_its_own() -> None:
    """Not folded into `worse`: no score moved, the input did. A drifted file
    reported as a regression would send a reader looking for a check that got
    worse, and there is none. (ADR 0029 §2)"""
    before = a_pinned_run((), tools=Artifact(sha="a" * 64, text="v1"))
    after = a_pinned_run(("tools",), tools=Artifact(sha="b" * 64, text="v2"))
    result = compare(after, before)
    assert result.pinned_drifted
    assert result.pinned_unchecked == ()
    # It is a change too — the two facts coexist rather than replacing each
    # other — and it is emphatically not a regression.
    assert result.artifacts_changed
    assert not any(d.outcome == "regressed" for d in result.deltas)


def test_an_unpinned_path_that_moved_is_not_drift() -> None:
    """The prompt's default, which must survive this feature: changing the file
    *is* the experiment, so a change nobody pinned moves no exit code."""
    before = a_pinned_run((), prompt=Artifact(sha="a" * 64, text="v1"))
    after = a_pinned_run((), prompt=Artifact(sha="b" * 64, text="v2"))
    result = compare(after, before)
    assert result.artifacts_changed
    assert not result.pinned_drifted, (
        "an unpinned file that moved was reported as drift: every suite that "
        "declares a prompt would fail on the edit it was declared to measure"
    )


def test_a_pin_the_reference_never_had_is_not_drift() -> None:
    """`new` is not a change — the rule every outcome here is read by — and it
    is what the comparison right after declaring a pin looks like. Firing there
    would teach an author that the feature is noise before it caught anything.
    (ADR 0029 §7)"""
    before = a_pinned_run(())
    after = a_pinned_run(("tools",), tools=Artifact(sha="b" * 64, text="v2"))
    result = compare(after, before)
    (delta,) = result.artifact_deltas
    assert (delta.outcome, delta.pinned) == ("new", True)
    assert not result.pinned_drifted, (
        "a pinned path the reference never recorded was reported as drift: the "
        "run would fail on the comparison that declared the pin, saying a file "
        "moved when the only thing that moved is the declaration"
    )


def test_a_pin_nobody_could_check_is_counted_and_not_passed() -> None:
    """Redaction leaves no digest, so *it did not drift* is not available. The
    count is, and it is never silent. (ADR 0029 §8)"""
    before = a_pinned_run((), tools=Artifact(sha="a" * 64, text="v1"))
    after = redact(a_pinned_run(("tools",), tools=Artifact(sha="b" * 64, text="v2")))
    result = compare(after, before)
    assert result.pinned_unchecked == ("tools",), (
        "a pin nobody could check went unreported: the comparison would read as "
        "having checked it, which is the silence that makes a control worse than "
        "no control"
    )
    # Not a failure: the fact layer declines to assert what it cannot see.
    assert not result.pinned_drifted, (
        "an unanswerable pin was reported as drift: the document would claim a "
        "file moved on the strength of a digest it does not hold"
    )
    assert not result.artifacts_changed


def test_redaction_carries_the_pin_like_the_canary() -> None:
    """A redacted document that lost it would report an exit code its own
    contents could not account for. No `Disclosure` gates it. (ADR 0029 §3)"""
    run = a_pinned_run(("tools",), tools=Artifact(sha="a" * 64, text="secret rules"))
    assert redact(run).pinned == ("tools",)
    # And the payload still goes, which is the point of the pairing.
    assert redact(run).artifacts["tools"].text is None
    # Narrowing further never widens, and never drops the declaration either.
    assert redact(redact(run)).pinned == ("tools",)


def test_a_withheld_comparison_still_knows_the_path_was_pinned() -> None:
    """The one line that decides the software-house case, guarded by name.

    `withhold_artifacts` keeps *that* a file moved and drops *what* it was, for
    a party holding both runs who is producing a document for someone holding
    neither. Keeping `outcome` and dropping `pinned` would hand that reader a
    document which knows a file moved and has forgotten anybody declared it must
    not — green, type-checked and quietly wrong, which is why this test exists
    and why it is paired with a mutation control. (ADR 0029 §5)
    """
    before = a_pinned_run((), tools=Artifact(sha="a" * 64, text="v1"))
    after = a_pinned_run(("tools",), tools=Artifact(sha="b" * 64, text="v2"))
    withheld = withhold_artifacts(compare(after, before))

    (delta,) = withheld.artifact_deltas
    assert delta.pinned is True, (
        "withhold_artifacts dropped `pinned`: the document now says a file moved "
        "and no longer says anybody declared it must not"
    )
    # The outcome survives, which is what makes the pin answerable at all here —
    # unlike `redact()` on one run, which has nothing to compare with.
    assert delta.outcome == "changed"
    assert withheld.pinned_drifted
    # And the payload is gone, on the same row.
    assert (delta.before, delta.after, delta.before_sha) == (None, None, "")


def test_a_drifted_pin_exits_two_and_an_unchecked_one_exits_zero() -> None:
    """The line the whole ruling sits on, asserted on both sides of it.

    Visible without being a failure: `pinned_unchecked` reaches the headline and
    the sentence and moves no number, because it says nobody here can tell rather
    than saying the file moved. (ADR 0029 §6, §8)
    """
    before = a_pinned_run((), tools=Artifact(sha="a" * 64, text="v1"))
    moved = a_pinned_run(("tools",), tools=Artifact(sha="b" * 64, text="v2"))
    drifted = headline(
        compare(moved, before), moved, before, locale="en", declared=None
    )
    assert exit_code(drifted) == 2, (
        "a pinned file that moved did not stop the pipeline: the declaration "
        "would be a line in a report, which is the vacuously green control "
        "ADR 0029 exists to end"
    )
    assert not drifted.worse, (
        "drift was folded into `worse`: the report would claim a check got worse "
        "when no score moved, and a reader would look for a regression there is "
        "none of"
    )
    assert "declared not to change" in drifted.sentence

    unchecked = headline(
        compare(redact(moved), before),
        redact(moved),
        before,
        locale="en",
        declared=None,
    )
    assert unchecked.pinned_unchecked == 1
    assert exit_code(unchecked) == 0, (
        "an unanswerable pin failed the run: the exit code would assert drift "
        "that the fact layer refuses to assert, off a digest nobody holds"
    )
    assert "was not checked" in unchecked.sentence, (
        "an unchecked pin was silent: the comparison reads as having checked it, "
        "which produces the same green as a control that ran"
    )


def test_the_withheld_report_gives_the_pin_a_count_and_never_a_path() -> None:
    """A path is `prompts/acme-underwriting-rules.md` often enough that a list of
    them describes the customer, which is why the withheld branch drops the table
    altogether. The pin clause lives inside that branch, so it must be a count:
    naming the path would put back exactly what the branch removes. (ADR 0029 §10)
    """
    # A path token that is *not* the tenant's name: `acme-bank` is in the report
    # header legitimately, so asserting on "acme" would test the header rather
    # than the pin clause and would have passed for the wrong reason.
    path = "prompts/underwriting-rules.md"
    before = a_pinned_run((), **{path: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((path,), **{path: Artifact(sha="b" * 64, text="v2")})
    held = withhold_artifacts(compare(after, before))
    # The **document**, not `artifact_lines`: the terminal returns nothing at all
    # once anything is withheld, and carries the count in the headline sentence
    # instead. The page is where the withheld clause has to appear.
    section = render_html(held, redact(after), before, locale="en", declared=None)

    assert "declared not to change" in section, (
        "the withheld comparison lost the pin: the party holding both runs "
        "established that a file which must not drift moved, and the document "
        "they produced for the party holding neither does not say so"
    )
    assert "underwriting" not in section, (
        "a pinned path was named in a withheld report: the clause put back the "
        "customer's vocabulary that dropping the table exists to remove"
    )


def test_report_redacted_exits_on_the_drift_its_document_reports(
    project: Path,
) -> None:
    """The two halves above, run together through the command a person runs.

    Each half was pinned alone: `redact(moved)` exits 0, and the withheld
    document says the pinned file moved. `report --redacted` composes both, and
    until this test it took its exit code from a fresh `compare` over the
    redacted run — where the digest is gone and the pin reads `unknown` — while
    the page came from the comparison the artifact outcomes were restored to. So
    the page said a file declared not to change had moved, and the process
    exited 0. The exit code an archived document carries has to be the one its
    own contents account for. (ADR 0029 §5, §6)
    """
    (project / "suite.py").write_text(
        (SUITE % {"disclosure": ""}).replace(
            'artifacts=[Path("prompt.md")],',
            'artifacts=[Path("prompt.md")],\n    pinned=[Path("prompt.md")],',
        ),
        encoding="utf-8",
    )
    (project / "prompt.md").write_text(PROMPT_V1, encoding="utf-8")
    run_once(project)
    cli(
        project,
        "promote",
        "--replacing",
        baseline_in(project),
        "--suite",
        "suite.py",
        "--run",
        "latest",
    )
    (project / "prompt.md").write_text(PROMPT_V2, encoding="utf-8")
    run_once(project)

    report = ("report", "--suite", "suite.py", "--run", "latest", "--locale", "en")
    complete = cli(project, *report, "--out", str(project / "complete.html"))
    assert complete.returncode == 2, complete.stderr
    out = project / "redacted.html"
    hidden = cli(project, *report, "--redacted", "--out", str(out))

    assert "declared not to change" in out.read_text(encoding="utf-8")
    assert hidden.returncode == complete.returncode, (
        "the redacted report says a pinned file moved and exits "
        f"{hidden.returncode}: the exit code was computed from a comparison "
        "the document was not rendered from"
    )


def test_a_pinning_suite_refuses_a_launch_that_hands_down_no_pin_set() -> None:
    """The invariant that would have caught 0.19.0's inert feature.

    Every unit test passed while `read_pinned` had **no caller at all**: the CLI
    read the artifacts and never the pins, so `Run.pinned` was `()` in every run
    digline wrote, the example declared a control that was never recorded, and no
    comparison could exit 2. Tests that construct `Run(pinned=…)` cannot see
    that; only the layer where the mistake is made can. (F-1, the 0.19.0
    delta-pass)
    """
    suite = Suite(
        tenant="t",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="c", vars={"input": "x"})],
        artifacts=[Path("tools.json")],
        pinned=[Path("tools.json")],
    )
    with pytest.raises(ValueError, match="passed no resolved pin set"):
        execute(
            suite,
            lambda case: Response(output="x", input="q"),
            created_at="2026-08-26T10:00:00+00:00",
        )


def test_a_run_document_pinning_nothing_it_records_is_refused() -> None:
    """The read side gets the write side's refusal. `read_pinned` runs only on the
    machine that produced the run; `baselines/` is committed and git-mergeable, so
    a dead pin arrives through an ordinary conflict resolution. Unrefused it is a
    control that silently does not exist. (F-2, the 0.19.0 delta-pass)"""
    document = json.loads(
        run_to_json(
            a_pinned_run(
                ("tools.json",), **{"tools.json": Artifact(sha="a" * 64, text="x")}
            )
        )
    )
    document["pinned"] = ["no-such-file.json"]
    with pytest.raises(ValueError, match="records no artifact for"):
        run_from_json(json.dumps(document))


def test_a_run_document_carries_the_pin_across_the_boundary() -> None:
    """A run document plus an exit 2 and no field is the unaccountable pair ADR
    0029 §3 recorded the field to prevent — and the boundary form left it out.
    (F-4, the 0.19.0 delta-pass)"""
    run = a_pinned_run(
        ("tools.json",), **{"tools.json": Artifact(sha="a" * 64, text="x")}
    )
    assert run_document(redact(run), NOTHING_EXTRA)["pinned"] == ["tools.json"], (
        "the boundary form dropped the declaration: a reader outside the "
        "perimeter gets an exit code the document cannot account for"
    )


# --------------------------------------------------------------------------- #
# A pinned path the judged run no longer records (ADR 0051)
# --------------------------------------------------------------------------- #
#
# Three facts join the comparison and one of them moves the exit code. A pinned
# row with no reference value is `pinned_unreferenced`; a pin the reference
# held and the judged run does not is `pinned_withdrawn`; a withdrawn path the
# judged run does not record, beside an unreferenced pin, is `pinned_lost`, and
# that alone returns 2. (ADR 0051, *The decision*)
#
# The paths carry `underwriting` for the reason the ADR 0029 block gives: a
# token no tenant, suite or boilerplate string shares.

#: The headline's clauses for the three facts, one file each. Asserted whole,
#: so a failure prints the sentence the record will carry.
UNREFERENCED_ONE = (
    "1 file declared not to change has no reference to compare with, so "
    "whether it changed was not checked."
)
WITHDRAWN_ONE = "1 file the reference declared not to change is not declared here."
LOST = (
    "A file the reference declared not to change is gone, and a file declared "
    "not to change here has no reference, so whether one became the other "
    "could not be judged."
)

OLD = "eval/d1/underwriting-tools.json"
NEW = "eval/d2/underwriting-tools.json"

#: The same case, judged worse: the one check that passed now fails.
WORSE = CaseResult(
    "judged",
    (
        Verdict(
            score=Score(name="contains", score=0.0),
            threshold=1.0,
            status="fail",
            reason="missing",
            assertion_id="contains-1",
        ),
    ),
)


def judged(run: Run, baseline: Run) -> tuple[Comparison, Headline]:
    """The comparison and the headline a front end would build from it."""
    comparison = compare(run, baseline)
    return comparison, headline(comparison, run, baseline, locale="en", declared=None)


def test_a_pinned_file_renamed_and_changed_is_lost_and_exits_two() -> None:
    """#483, the case the record is for. The old path is gone from the judged
    run, the new one has no reference value, and from the two documents nothing
    says whether one became the other: the gate says it could not judge.
    (ADR 0051 §3)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2")})
    comparison, head = judged(after, before)

    assert exit_code(head) == 2, (
        "a pinned file renamed and changed in one run exited "
        f"{exit_code(head)}: the pin lost its path and the gate still read "
        f"green. The headline should end with {LOST!r}; it says {head.sentence!r}"
    )
    assert comparison.pinned_unreferenced == (NEW,)
    assert comparison.pinned_withdrawn == (OLD,)
    assert comparison.pinned_lost
    for clause in (UNREFERENCED_ONE, WITHDRAWN_ONE, LOST):
        assert clause in head.sentence, (
            f"expected {clause!r} in the headline; it says {head.sentence!r}"
        )


def test_a_pin_added_beside_a_new_file_is_unreferenced_and_moves_nothing() -> None:
    """§7's case: the comparison right after a pin is declared. Its reason
    against `new` was a reason against red, not against the sentence: *this pin
    has no reference to compare against yet* is true. (ADR 0051 §1)"""
    before = a_pinned_run(())
    after = a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2")})
    comparison, head = judged(after, before)

    assert exit_code(head) == 0, (
        "a pin added beside its file moved the exit code: the feature would go "
        "red on the comparison that declared it (ADR 0029 §7)"
    )
    assert UNREFERENCED_ONE in head.sentence, (
        f"expected {UNREFERENCED_ONE!r} in the headline; it says {head.sentence!r}"
    )
    assert comparison.pinned_unreferenced == (NEW,)
    assert comparison.pinned_withdrawn == ()
    assert not comparison.pinned_lost


def test_a_pin_withdrawn_with_its_file_is_reported_and_moves_nothing() -> None:
    """§9's withdrawal, the file gone with the declaration. A withdrawal that
    could not be made without a red would be a pin nobody could ever remove.
    (ADR 0051 §2)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run(())
    comparison, head = judged(after, before)

    assert exit_code(head) == 0, (
        "a pin withdrawn with its file moved the exit code: §9's withdrawal "
        "would need a red to make"
    )
    assert WITHDRAWN_ONE in head.sentence, (
        f"expected {WITHDRAWN_ONE!r} in the headline; it says {head.sentence!r}"
    )
    assert comparison.pinned_withdrawn == (OLD,)
    assert comparison.pinned_unreferenced == ()
    assert not comparison.pinned_lost


def test_a_pin_withdrawn_while_its_file_stays_is_reported() -> None:
    """The half of §9 the code never built: the file is still recorded and
    still compared, and the reference's declaration on it is gone. ADR 0029 §9
    ruled *"the comparison reports it"*, and nothing read the baseline's pins.
    (ADR 0051 §2)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((), **{OLD: Artifact(sha="a" * 64, text="v1")})
    comparison, head = judged(after, before)

    assert exit_code(head) == 0, (
        "a withdrawn pin on a file that stayed moved the exit code: §9 reports "
        "a withdrawal and never enforces it"
    )
    assert WITHDRAWN_ONE in head.sentence, (
        f"expected {WITHDRAWN_ONE!r} in the headline; it says {head.sentence!r}"
    )
    assert comparison.pinned_withdrawn == (OLD,)
    assert not comparison.pinned_lost


def test_a_withdrawn_pin_on_a_kept_file_beside_a_new_pin_is_not_lost() -> None:
    """The case that tells `pinned_gone` from `pinned_withdrawn`. The old file is
    still recorded and only its pin is gone, beside a new pin with no reference
    value. Nothing was lost: the file the reference pinned is still here to be
    read. Only a path the run no longer records can pair with an unreferenced
    pin, so `pinned_lost` is false, and a condition widened to every withdrawn
    pin would read it as a rename and exit 2. (ADR 0051 §2, §3; #483)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run(
        (NEW,),
        **{
            OLD: Artifact(sha="a" * 64, text="v1"),
            NEW: Artifact(sha="b" * 64, text="v2"),
        },
    )
    comparison, head = judged(after, before)

    assert comparison.pinned_withdrawn == (OLD,)
    assert comparison.pinned_unreferenced == (NEW,)
    assert comparison.pinned_gone == ()
    assert not comparison.pinned_lost, (
        "a pin withdrawn on a file the run still records was read as lost beside "
        "an unreferenced pin: the file is here, so nothing became anything"
    )
    assert exit_code(head) == 0, head.sentence


def test_the_declared_cost_removing_one_pinned_file_and_pinning_another() -> None:
    """**The cost ADR 0051 declares, not a defect.** A run that removes pinned
    file X and adds a pin on a new file Y is, from the two documents,
    indistinguishable from the rename of #483, and in one of the two readings a
    guarantee was lost. Where the readings cannot be told apart the gate says
    it could not judge, which is what 2 means. A change that makes this exit 0
    reopens #483. (ADR 0051 §3, *The declared cost*)"""
    removed, added = "prompts/underwriting-x.md", "prompts/underwriting-y.md"
    before = a_pinned_run((removed,), **{removed: Artifact(sha="a" * 64, text="x")})
    after = a_pinned_run((added,), **{added: Artifact(sha="c" * 64, text="y")})
    comparison, head = judged(after, before)

    assert exit_code(head) == 2, (
        f"removing pinned {removed} and pinning a new {added} exited "
        f"{exit_code(head)}: that run cannot be told from a rename, and ADR "
        f"0051 declares a 2 for it. The headline should end with {LOST!r}; it "
        f"says {head.sentence!r}"
    )
    assert comparison.pinned_lost
    assert LOST in head.sentence


def test_a_lost_pin_beside_a_worse_check_exits_one() -> None:
    """Precedence does not move: a regression outranks every cause of 2, by
    ADR 0029 §6 and ADR 0024 §4.5. (ADR 0051, *Precedence is unchanged*)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = replace(
        a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2")}),
        results=(WORSE,),
    )
    comparison, head = judged(after, before)

    assert exit_code(head) == 1, (
        f"a lost pin beside a check that got worse exited {exit_code(head)}: "
        "the quieter cause would hide the louder one"
    )
    assert comparison.pinned_lost


def test_a_withheld_side_answers_unchecked_before_unreferenced() -> None:
    """A withheld side is read first: `artifact_deltas()` answers `unknown`
    before it asks about `new`, so the renamed path of a redacted run is §8's
    fact, counted and not passed, and moves nothing. (ADR 0051, *A withheld
    side is read first*)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = redact(a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2")}))
    comparison, head = judged(after, before)

    assert comparison.pinned_unchecked == (NEW,)
    assert exit_code(head) == 0, (
        "a withheld pinned path moved the exit code: the comparison asserted "
        "something about a digest it does not hold (ADR 0029 §8)"
    )
    assert comparison.pinned_withdrawn == (OLD,), (
        "the reference's pin on the old path was not reported as withdrawn: the "
        "fact is about the declaration, and the judged run's pins are readable "
        "in a redacted comparison"
    )
    assert comparison.pinned_unreferenced == (), (
        "a withheld pinned path was counted as having no reference: it has one "
        "nobody here can read, which is §8's fact and not ADR 0051's"
    )
    assert not comparison.pinned_lost


def test_pinned_unchecked_keeps_its_count_beside_an_unreferenced_pin() -> None:
    """`pinned_unchecked` keeps its meaning and its count: a withheld pin is
    counted as before, and a pinned row with no reference value beside it is
    counted elsewhere. §8 invited consumers to build a rule on this count.
    (ADR 0051, *What does not change*)"""
    held, fresh = "prompts/underwriting-held.md", "prompts/underwriting-fresh.md"
    before = a_pinned_run((), **{held: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run(
        (held, fresh),
        **{held: Artifact(withheld=True), fresh: Artifact(sha="c" * 64, text="f")},
    )
    comparison, head = judged(after, before)

    assert comparison.pinned_unchecked == (held,)
    assert head.pinned_unchecked == 1
    assert exit_code(head) == 0
    assert comparison.pinned_unreferenced == (fresh,), (
        "the unreferenced pin was not counted on its own: either it went into "
        "`pinned_unchecked` and changed what a consumer's rule counts, or it "
        "was not reported at all"
    )


def test_a_pinned_file_changed_under_its_own_name_still_drifts() -> None:
    """The road ADR 0029 built, untouched: same path, new digest, exit 2 for
    drift and for nothing new. (ADR 0051, *What does not change*)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((OLD,), **{OLD: Artifact(sha="b" * 64, text="v2")})
    comparison, head = judged(after, before)

    assert comparison.pinned_drifted
    assert exit_code(head) == 2
    assert comparison.pinned_unreferenced == ()
    assert comparison.pinned_withdrawn == ()
    assert not comparison.pinned_lost


def test_the_headline_counts_the_drifted_pins_the_comparison_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headline's clause and the gate read one property, never two filters.

    `pinned_changed` is where the condition is written; `pinned_drifted` and the
    clause read it. Replacing the property with an answer the deltas do not give
    shows whether they do: a headline that filtered `artifact_deltas` again
    would still count two, and a gate that did would still read drift. (#483)
    """
    before = a_pinned_run(
        (OLD, NEW),
        **{
            OLD: Artifact(sha="a" * 64, text="v1"),
            NEW: Artifact(sha="c" * 64, text="w1"),
        },
    )
    after = a_pinned_run(
        (OLD, NEW),
        **{
            OLD: Artifact(sha="b" * 64, text="v2"),
            NEW: Artifact(sha="d" * 64, text="w2"),
        },
    )
    comparison, head = judged(after, before)
    assert sorted(comparison.pinned_changed) == sorted((OLD, NEW))
    assert phrase("en", "fact.pinned.many", count=2) in head.sentence

    three = ("a/underwriting-1.json", "a/underwriting-2.json", "a/underwriting-3.json")
    monkeypatch.setattr(Comparison, "pinned_changed", property(lambda self: three))
    comparison, head = judged(after, before)
    assert phrase("en", "fact.pinned.many", count=3) in head.sentence, head.sentence

    monkeypatch.setattr(Comparison, "pinned_changed", property(lambda self: ()))
    comparison, head = judged(after, before)
    assert not comparison.pinned_drifted
    assert "declared not to change, and" not in head.sentence, head.sentence


def test_the_page_counts_the_pins_the_comparison_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page's drifted and unchecked clauses read the comparison, as the
    headline's does: replacing the paths with an answer the deltas do not give
    shows which is read. A page that counted `artifact_deltas` again would still
    say two and nothing, and a count property with a filter of its own would not
    follow the paths it is the count of. (#483)
    """
    before = a_pinned_run(
        (OLD, NEW),
        **{
            OLD: Artifact(sha="a" * 64, text="v1"),
            NEW: Artifact(sha="c" * 64, text="w1"),
        },
    )
    after = a_pinned_run(
        (OLD, NEW),
        **{
            OLD: Artifact(sha="b" * 64, text="v2"),
            NEW: Artifact(sha="d" * 64, text="w2"),
        },
    )

    def page() -> str:
        comparison = compare(after, before)
        return unescape(
            render_html(comparison, after, before, locale="en", declared=None)
        )

    drifted_two = phrase("en", "artifacts.pinned.many", count=2)
    assert drifted_two in page()

    three = ("a/underwriting-1.json", "a/underwriting-2.json", "a/underwriting-3.json")
    two = ("b/underwriting-1.json", "b/underwriting-2.json")
    monkeypatch.setattr(Comparison, "pinned_changed", property(lambda self: three))
    monkeypatch.setattr(Comparison, "pinned_unchecked", property(lambda self: two))
    shown = page()
    assert phrase("en", "artifacts.pinned.many", count=3) in shown
    assert phrase("en", "artifacts.pinned.unchecked.many", count=2) in shown

    monkeypatch.setattr(Comparison, "pinned_changed", property(lambda self: ()))
    monkeypatch.setattr(Comparison, "pinned_unchecked", property(lambda self: ()))
    shown = page()
    assert drifted_two not in shown
    assert "not included, so whether" not in shown


#: The headline's flags for the causes of 2, by the name each cause has in the
#: tuple. `unjudged` is not among them: it is a count, not a flag.
CAUSE_FLAGS = ("scale_lost", "pinned_drifted", "pinned_lost", "nothing_judged")


def test_the_headline_flags_follow_the_causes_of_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flags `exit_code` used to enumerate are read off the one tuple, and
    so is the number.

    `causes_of_two` is where the set is written; promote reads it in the write
    step, and the headline derives its flags and the list it carries from it.
    Replacing it with an answer the documents do not give shows whether they
    do: a flag computed again on its own would keep the documents' answer, and
    `exit_code` reading the flags rather than the tuple would too. (#483)
    """
    import digline.report.render as render

    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((OLD,), **{OLD: Artifact(sha="b" * 64, text="v2")})
    _comparison, head = judged(after, before)
    assert head.pinned_drifted
    assert head.unjudged_causes == ("pinned_drifted",)
    assert exit_code(head) == 2

    monkeypatch.setattr(render, "causes_of_two", lambda *a, **k: CAUSE_FLAGS)
    _comparison, head = judged(before, before)
    assert head.unjudged_causes == CAUSE_FLAGS
    for flag in CAUSE_FLAGS:
        assert getattr(head, flag), f"{flag} did not follow the tuple"
    assert exit_code(head) == 2

    monkeypatch.setattr(render, "causes_of_two", lambda *a, **k: ())
    _comparison, head = judged(after, before)
    assert head.unjudged_causes == ()
    for flag in CAUSE_FLAGS:
        assert not getattr(head, flag), f"{flag} did not follow the tuple"
    assert exit_code(head) == 0


def test_nothing_pinned_on_either_side_reports_none_of_the_three() -> None:
    """No pin, no pin fact: the default every suite that pins nothing reads.
    (ADR 0051, *What does not change*)"""
    before = a_pinned_run((), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((), **{NEW: Artifact(sha="b" * 64, text="v2")})
    comparison, head = judged(after, before)

    assert exit_code(head) == 0
    assert comparison.pinned_unreferenced == ()
    assert comparison.pinned_withdrawn == ()
    assert not comparison.pinned_lost


def test_compare_json_carries_the_three_facts_at_output_version_two() -> None:
    """Three added keys, and no bump: an added key does not break a consumer,
    and what changes here is behaviour, not format. (ADR 0051, *Its price*)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1")})
    after = a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2")})
    comparison, head = judged(after, before)
    payload = compare_json(comparison, head, baseline=before, full=False, run=after)

    assert payload["output_version"] == 2
    missing = {"pinned_unreferenced", "pinned_withdrawn", "pinned_lost"} - set(payload)
    assert not missing, f"compare --json does not carry {sorted(missing)}"
    assert (
        payload["pinned_unreferenced"],
        payload["pinned_withdrawn"],
        payload["pinned_lost"],
    ) == (1, 1, True)


#: The document's three clauses for #483, as each locale words them. "In this
#: run" where the headline says "here": a document is read apart from the
#: command that printed it. (ADR 0051, beside `artifacts.pinned.*`)
DOCUMENT_CLAUSES: dict[Locale, tuple[str, ...]] = {
    "en": (
        "1 file declared not to change has no reference to compare with, so "
        "whether it changed was not checked.",
        "1 file the reference declared not to change is not declared so in this run.",
        "A file the reference declared not to change is gone, and a file declared "
        "not to change in this run has no reference, so whether one became the "
        "other could not be judged.",
    ),
    "it": (
        "1 file dichiarato immutabile non ha un riferimento con cui confrontarlo, "
        "quindi non è stato verificato se sia cambiato.",
        "1 file che il riferimento dichiarava immutabile non è dichiarato tale in "
        "questa esecuzione.",
        "Un file che il riferimento dichiarava immutabile non c'è più, e un file "
        "dichiarato immutabile in questa esecuzione non ha un riferimento, quindi "
        "non si è potuto stabilire se l'uno sia diventato l'altro.",
    ),
}


def test_the_document_carries_the_three_clauses_of_a_lost_pin() -> None:
    """§8 named the document beside the sentence and the wire, and these are the
    same kind of fact: counts in the artifacts section, never a path.
    (ADR 0051, ADR 0029 §8)"""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1\n")})
    after = a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2\n")})
    comparison = compare(after, before)
    for locale, clauses in DOCUMENT_CLAUSES.items():
        page = unescape(
            render_html(comparison, after, before, locale=locale, declared=None)
        )
        for clause in clauses:
            assert clause in page, (
                f"the {locale} document does not say {clause!r}: the fact is on "
                "the headline and the wire and missing from the page a customer "
                "reads"
            )


def test_the_terminal_marks_both_rows_of_a_lost_pin() -> None:
    """Before ADR 0051 the two lines of #483 said nothing about a pin, which is
    the silence being removed. Each row carries its own marker, after the
    outcome, as `declared not to change` does for a drifted pin."""
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1\n")})
    after = a_pinned_run((NEW,), **{NEW: Artifact(sha="b" * 64, text="v2\n")})
    comparison = compare(after, before)
    expected: dict[Locale, tuple[str, ...]] = {
        "en": (
            f"{OLD} · no longer declared · was declared not to change",
            f"{NEW} · added since the reference · declared not to change, no "
            "reference to compare with",
        ),
        "it": (
            f"{OLD} · non più dichiarato · era dichiarato immutabile",
            f"{NEW} · aggiunto rispetto al riferimento · dichiarato immutabile, "
            "senza riferimento con cui confrontarlo",
        ),
    }
    for locale, lines in expected.items():
        assert tuple(artifact_lines(comparison, locale=locale)) == lines


def test_a_pin_withdrawn_on_a_file_that_did_not_move_gets_no_terminal_line() -> None:
    """**ADR 0051's decision, not an oversight.** `artifact_lines` lists the files
    that moved, and a pin withdrawn on a file that did not move is not a
    movement: the file gets no line. The withdrawal is said where facts about
    the comparison are said, in the headline and in the document. (ADR 0051 §2)
    """
    before = a_pinned_run((OLD,), **{OLD: Artifact(sha="a" * 64, text="v1\n")})
    after = a_pinned_run((), **{OLD: Artifact(sha="a" * 64, text="v1\n")})
    comparison, head = judged(after, before)

    assert WITHDRAWN_ONE in head.sentence
    page = unescape(render_html(comparison, after, before, locale="en", declared=None))
    assert DOCUMENT_CLAUSES["en"][1] in page
    assert tuple(artifact_lines(comparison, locale="en")) == (), (
        "a file that did not move got a terminal line: the list of files that "
        "moved now names one that did not"
    )


def test_two_pinned_files_renamed_together_count_both_and_say_lost_once() -> None:
    """#483 in the plural: the two counts take their `many` forms, and the lost
    clause is one fact about the comparison, so it is said once. (ADR 0051)"""
    olds = ("eval/d1/underwriting-a.json", "eval/d1/underwriting-b.json")
    news = ("eval/d2/underwriting-a.json", "eval/d2/underwriting-b.json")
    before = a_pinned_run(olds, **{p: Artifact(sha="a" * 64, text="v1") for p in olds})
    after = a_pinned_run(news, **{p: Artifact(sha="b" * 64, text="v2") for p in news})
    comparison, head = judged(after, before)

    assert exit_code(head) == 2
    assert (comparison.pinned_unreferenced, comparison.pinned_withdrawn) == (news, olds)
    for clause in (
        "2 files declared not to change have no reference to compare with, so "
        "whether they changed was not checked.",
        "2 files the reference declared not to change are not declared here.",
    ):
        assert clause in head.sentence, (
            f"expected {clause!r} in the headline; it says {head.sentence!r}"
        )
    assert head.sentence.count(LOST) == 1, (
        f"the lost clause appears {head.sentence.count(LOST)} times: it is one "
        "fact about the comparison, not one per file"
    )


def test_the_fixture_commit_carries_nothing_that_moves(project: Path) -> None:
    """The pin is what the redaction test's digit check stands on, so it is
    checked here rather than assumed. The dates are the pinned ones, not the
    clock's, and no signature was added by a configuration the machine had."""
    shown = subprocess.run(
        ["git", "-C", str(project), "log", "-1", "--format=%at %ct %G?"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    # 2026-01-01T00:00:00+00:00, as seconds: git spells UTC as `Z` in ISO.
    assert shown == ["1767225600", "1767225600", "N"]


#: The same case, not judged: its one check errored.
ERRORED = CaseResult(
    "judged",
    (
        Verdict(
            score=Score(name="contains", score=None),
            threshold=1.0,
            status="error",
            reason="the judge did not answer",
            assertion_id="contains-1",
        ),
    ),
)


@pytest.mark.parametrize(
    "results", [(JUDGED,), (ERRORED,), (JUDGED, replace(ERRORED, case_id="other"))]
)
def test_the_unjudged_count_and_the_tuple_say_the_same_thing(
    results: tuple[CaseResult, ...],
) -> None:
    """`unjudged` stays a count, because the sentence and the wire carry the
    number. It is not derived from the tuple, so this holds the two together:
    `unjudged` is among the causes **exactly when** the count is above zero.
    (#483)"""
    before = a_pinned_run(())
    after = replace(before, created_at="2026-08-27T10:00:00+00:00", results=results)
    _comparison, head = judged(after, before)
    assert ("unjudged" in head.unjudged_causes) == (head.unjudged > 0), (
        f"unjudged counts {head.unjudged} and the causes are {head.unjudged_causes}"
    )
    assert head.unjudged == sum(result is not JUDGED for result in results)
