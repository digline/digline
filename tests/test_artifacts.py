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
from pathlib import Path

import pytest
from tests._helpers import cli, git

from digline.core import (
    Artifact,
    Disclosure,
    Run,
    artifacts_sha,
    compare,
    redact,
    withhold_artifacts,
)
from digline.core.run import SCHEMA_VERSION, run_from_json, run_to_json
from digline.report import artifact_lines, diff_lines, render_html
from digline.store import FileResultStore

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


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A repository with a prompt beside the suite, committed once."""
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
    document = render_html(compare(after, before), after, before, locale="en")
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
    document = render_html(withheld, redact(after), before, locale="en")

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
        compare(small_after, small_before), small_after, small_before, locale="en"
    )
    assert "<details open><summary><code>prompt</code>" in small

    wide_v1 = "\n".join(f"line {i}" for i in range(40))
    wide_v2 = "\n".join(f"changed {i}" for i in range(40))
    big_before, big_after = two_versions(wide_v1, wide_v2)
    big = render_html(
        compare(big_after, big_before), big_after, big_before, locale="en"
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
        cli(project, "promote", "--suite", "suite.py", "--run", "latest").returncode
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
    assert "2500" not in hidden and "1000" not in hidden
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
    cli(project, "promote", "--suite", "suite.py", "--run", "latest")
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
