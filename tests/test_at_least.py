"""At least k of n, the held-out answer moved among the held-in ones, and
the runs a stability scan passed over: the fifth pull request of ADR 0067
§10, with the ruling of 2026-11-23 (P-1719).

What is held here, each with the mutation that turns it red, listed in the
session's report:

- **two of three pass and one of three fails at `"2/3"`**, the score the
  share in favour and the threshold k/n, the mean beside them;
- **an n that is not the suite's samples × repeats is refused**, by name, at
  load;
- **`config_hash` does not move for a suite without `at_least`**, pinned to
  the value `main` computed before it, and moves for one that declares it;
  no check's identity moves;
- **after `record revise --held-in`, the answer is in the held-in figures
  and out of the held-out count**;
- **runs of a schema this version does not read are counted and said**, in
  the reading and in `--json`.
"""

from __future__ import annotations

import itertools
import json
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.test_review import CAPTURED, LONG_ID, cases_in
from tests.test_view_recorder import WRITES, by_command
from tests.test_view_recorder import (
    root as root,  # noqa: F401 — the fixture, by its name
)

from digline.core import (
    Contains,
    JudgeReply,
    LlmRubric,
    Repeated,
    Verdict,
    compare,
    config_hash,
    reviewed_agreement,
    uncertain_cases,
)
from digline.core.refused import RefusedError
from digline.core.sampling import MEAN_SCORE_KEY, directions
from digline.host import load_suite
from digline.report.render import judgements_said, render_run_html
from digline.run import Case, Response, Suite, execute

CREATED = "2026-11-23T09:00:00+00:00"


def judge_voting(*scores: float) -> Any:
    cycle = itertools.cycle(scores)

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=next(cycle), reason="r")

    return judge


def rubric(judge: Any, **changes: Any) -> LlmRubric:
    return LlmRubric(
        rubric="ok?", judge=judge, threshold=0.7, tolerance=0.05, **changes
    )


def suite(*assertions: Any, samples: int = 3, **changes: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "support",
        "assertions": list(assertions),
        "cases": [Case(id="c1")],
        "samples": samples,
        "min_agreement": f"1/{samples}" if samples > 1 else None,
    }
    fields.update(changes)
    return Suite(**fields)


def folded(checked: Suite) -> Verdict:
    run = execute(checked, lambda case: Response(output="x"), created_at=CREATED)
    (found,) = run.results[0].verdicts
    return found


# -- 1. at least k of n ------------------------------------------------------ #


def test_two_of_three_pass_at_two_thirds_on_the_suite_s_samples() -> None:
    """Three answers, judged 0.9, 0.8 and 0.2 against 0.7: two in favour.
    The mean, 0.633333, is under 0.7, so by the mean the check fails; by
    the count it passes. Mutation: deciding the status on the mean in
    `counted` turns it red, and so does leaving the driver's `_counted` out."""
    found = folded(suite(rubric(judge_voting(0.9, 0.8, 0.2), at_least="2/3")))
    assert (found.status, found.score.score, found.threshold) == (
        "pass",
        0.666667,
        0.666667,
    )
    assert found.score.metadata[MEAN_SCORE_KEY] == 0.633333
    assert found.score.metadata["at_least"] == 2
    assert found.score.metadata["at_least_of"] == 3
    assert found.score.metadata["judgement_threshold"] == 0.7
    assert found.reason.startswith("2 of 3 judgements reached 0.7, at least 2 needed")
    # The control: the same judgements without `at_least` fail on the mean.
    plain = folded(suite(rubric(judge_voting(0.9, 0.8, 0.2))))
    assert (plain.status, plain.score.score) == ("fail", 0.633333)


def test_one_of_three_fails_at_two_thirds() -> None:
    """0.9, 0.3 and 0.3: one in favour. Mutation: counting `judgements`
    where `in_favour` is read turns it red."""
    found = folded(suite(rubric(judge_voting(0.9, 0.3, 0.3), at_least="2/3")))
    assert (found.status, found.score.score, found.threshold) == (
        "fail",
        0.333333,
        0.666667,
    )
    assert directions(found) == (1, 2, 0)


def test_a_repeated_counts_samples_times_repeats_in_the_driver() -> None:
    """A `Repeated` of 3 under two samples is six judgements: four of six in
    favour pass at `"4/6"`, and the interval of the means is not the count's
    noise floor."""
    inner = rubric(judge_voting(1.0, 0.0, 1.0, 1.0, 0.0, 1.0))
    found = folded(
        suite(
            Repeated(inner, samples=3, min_agreement="1/3", at_least="4/6"),
            samples=2,
        )
    )
    assert (found.status, found.score.score, found.threshold) == (
        "pass",
        0.666667,
        0.666667,
    )
    assert (found.score.sample_min, found.score.sample_max) == (None, None)
    assert judgements_said(found, "en") == ("6 judgements, 4 in favour · mean 0.666667")


def test_a_repeated_called_on_its_own_counts_what_it_counts_in_a_run() -> None:
    """Fixed decision 1: where its fold is every judgement, the check alone
    says what the run says."""
    from digline.core import EvaluatorInputs

    check = Repeated(
        rubric(judge_voting(0.9, 0.8, 0.2)),
        samples=3,
        min_agreement="1/3",
        at_least="2/3",
    )
    alone = check(EvaluatorInputs(output="x"))
    assert (alone.status, alone.score.score, alone.threshold) == (
        "pass",
        0.666667,
        0.666667,
    )
    in_a_run = folded(suite(check, samples=1, min_agreement=None))
    assert (in_a_run.status, in_a_run.score.score) == ("pass", 0.666667)


def test_the_report_shows_the_mean_beside_the_count() -> None:
    checked = suite(rubric(judge_voting(0.9, 0.8, 0.2), at_least="2/3"))
    run = execute(checked, lambda case: Response(output="x"), created_at=CREATED)
    page = render_run_html(run, locale="en")
    assert (
        "<b>0.666667</b> / 0.666667 · 3 judgements, 2 in favour · mean 0.633333" in page
    )
    it = render_run_html(run, locale="it")
    assert "3 giudizi, 2 a favore · media 0.633333" in it


def test_uncertain_and_compare_read_the_count() -> None:
    """By the ruling: the share is the score, so the uncertain fact and
    compare's tolerance read it. Two of three is on the bar, within any
    margin, and a run at one of three against it regressed."""
    passed = suite(rubric(judge_voting(0.9, 0.8, 0.2), at_least="2/3"))
    failed = suite(rubric(judge_voting(0.9, 0.3, 0.3), at_least="2/3"))
    now = execute(failed, lambda case: Response(output="x"), created_at=CREATED)
    before = execute(passed, lambda case: Response(output="x"), created_at=CREATED)
    [found] = uncertain_cases(before)
    assert (found.score, found.threshold, found.near) == (0.666667, 0.666667, True)
    assert compare(now, before).counts["regressed"] == 1


@pytest.mark.parametrize(
    ("assertion", "samples", "said"),
    [
        (
            "plain",
            2,
            'declares at_least "2/3", n = 3, and the suite gives it 2 '
            "judgements a case (samples 2): n is that number",
        ),
        (
            "repeated",
            2,
            'declares at_least "2/3", n = 3, and the suite gives it 6 '
            "judgements a case (samples 2 × repeats 3): n is that number",
        ),
    ],
)
def test_an_n_that_is_not_the_judgements_produced_is_refused_by_name(
    assertion: str, samples: int, said: str
) -> None:
    """Mutation: dropping the comparison in
    `_refuse_a_count_that_does_not_match` turns it red."""
    judge = judge_voting(1.0)
    check: Any = (
        rubric(judge, at_least="2/3")
        if assertion == "plain"
        else Repeated(rubric(judge), samples=3, min_agreement="1/3", at_least="2/3")
    )
    with pytest.raises(RefusedError) as refused:
        suite(check, samples=samples)
    assert said in str(refused.value)
    assert "llm_rubric" in str(refused.value)


def test_a_count_that_matches_loads() -> None:
    """The control of the refusal above: n = 6 is samples 2 × repeats 3."""
    check = Repeated(
        rubric(judge_voting(1.0)), samples=3, min_agreement="1/3", at_least="4/6"
    )
    assert list(suite(check, samples=2).assertions) == [check]


def test_a_count_is_written_as_k_over_n_and_never_vacuous() -> None:
    judge = judge_voting(1.0)
    for bad, said in (
        (0.666667, "write it as a count"),
        ("0/3", "k is between 1 and 3"),
        ("4/3", "k is between 1 and 3"),
        ("1/1", "is the threshold itself"),
        ("two/3", "not a count"),
    ):
        with pytest.raises(RefusedError, match=said):
            rubric(judge, at_least=bad)


def test_at_least_on_what_a_repeated_wraps_is_refused() -> None:
    with pytest.raises(RefusedError, match="declare it on the repeated"):
        Repeated(
            rubric(judge_voting(1.0), at_least="2/3"), samples=3, min_agreement="1/3"
        )


def test_at_least_in_a_suite_toml_is_refused_by_name_when_n_does_not_match(
    tmp_path: Path,
) -> None:
    (tmp_path / "cases.json").write_text('[{"id": "c1"}]', encoding="utf-8")
    (tmp_path / "suite.toml").write_text(
        """\
[suite]
tenant = "acme"
environment = "dev"
name = "support"
cases = "cases.json"
samples = 2
min_agreement = "1/2"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"

[[assertions]]
type = "repeated"
samples = 3
min_agreement = "1/3"
at_least = "2/3"

  [assertions.inner]
  type = "llm_rubric"
  rubric = "polite?"
  judge = "anthropic/claude-haiku-4-5"
  threshold = 0.7
  tolerance = 0.05
""",
        encoding="utf-8",
    )
    from digline.host import UsageError

    with pytest.raises((UsageError, RefusedError)) as refused:
        load_suite(str(tmp_path / "suite.toml"), root=tmp_path)
    assert (
        "check 'llm_rubric' declares at_least \"2/3\", n = 3, and the suite "
        "gives it 6 judgements a case (samples 2 × repeats 3): n is that number"
    ) in str(refused.value)


# -- the hash and the identities --------------------------------------------- #

#: What `config_hash` and the identities were on `main` at `98dfe6d7`, before
#: `at_least` existed, measured by the session for P-1719 with the suite
#: `unmoved` builds.
HASH_BEFORE = "9288f9f68c1cdb4e"
HASH_REPEATED_BEFORE = "7f7e547f06ad0279"
RUBRIC_IDENTITY = "98ac2cbfb4905917"
REPEATED_IDENTITY = "47943fd110c31866"


def _fixed_judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=1.0, reason="ok")


def unmoved(at_least: str | None = None) -> tuple[LlmRubric, Repeated, Contains]:
    check = LlmRubric(
        rubric="Is it polite?",
        judge=_fixed_judge,
        threshold=0.7,
        tolerance=0.05,
        at_least=at_least,
    )
    repeated = Repeated(
        LlmRubric(
            rubric="Is it polite?", judge=_fixed_judge, threshold=0.7, tolerance=0.05
        ),
        samples=3,
        min_agreement="2/3",
        at_least=at_least,
    )
    return check, repeated, Contains(needle="x", threshold=1.0, tolerance=0.0)


def test_the_hash_of_a_suite_without_at_least_has_not_moved() -> None:
    """Mutation: appending `{"at_least": []}` whatever was declared turns it
    red."""
    check, repeated, contains = unmoved()
    assert config_hash([check, contains]) == HASH_BEFORE
    assert config_hash([repeated, contains], samples=2, min_agreement=0.5) == (
        HASH_REPEATED_BEFORE
    )


def test_the_hash_moves_for_a_suite_that_declares_at_least() -> None:
    """Mutation: leaving `counts` out of the hash's body turns it red."""
    check, _, contains = unmoved(at_least="2/3")
    assert config_hash([check, contains]) != HASH_BEFORE


def test_no_identity_moves_with_at_least() -> None:
    """Mutation: taking `at_least` out of `IDENTITY_EXCLUDED`, or out of the
    nested set `Repeated` leaves out of `inner`, turns it red."""
    check, repeated, _ = unmoved()
    assert (check.identity, repeated.identity) == (RUBRIC_IDENTITY, REPEATED_IDENTITY)
    counted_check, counted_repeated, _ = unmoved(at_least="2/3")
    assert counted_check.identity == RUBRIC_IDENTITY
    assert counted_repeated.identity == REPEATED_IDENTITY


# -- 2. record revise --held-in ---------------------------------------------- #

AT = "2026-11-23T12:00:00+00:00"


def _figures(root_dir: Path) -> tuple[int, int]:
    checked, _ = load_suite(str(root_dir / "suites" / "suite.py"), root=root_dir)
    run = execute(checked, lambda case: Response(output="x"), created_at=CREATED)
    reading = reviewed_agreement(run)
    assert reading is not None
    return reading.held_in, reading.held_out


def test_held_in_moves_a_held_out_answer_into_the_held_in_figures(
    root: Path,  # noqa: F811 — the fixture, by its name
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Written as a revision is, with the name and the time. Mutation:
    leaving `held_out` in the entry in `hold_in` turns it red."""
    monkeypatch.setattr(sys.modules["digline.cli.main"], "utc_now_iso", lambda: AT)
    by_command(
        root,
        shlex.join(
            [
                "digline",
                "record",
                "import",
                *WRITES,
                "--good",
                LONG_ID,
                "--by",
                "Ada",
                "--held-out",
            ]
        ),
        monkeypatch,
    )
    assert _figures(root) == (0, 1)
    by_command(
        root,
        shlex.join(
            [
                "digline",
                "record",
                "revise",
                *WRITES,
                "--held-in",
                LONG_ID,
                "--by",
                "Ada",
            ]
        ),
        monkeypatch,
    )
    [written] = [c for c in cases_in(root) if c["id"] == LONG_ID]
    held = written["reviewed_answer"]
    assert isinstance(held, dict)
    assert "held_out" not in held
    assert held["held_in"] == {"by": "Ada", "at": AT}
    assert _figures(root) == (1, 0)


def test_held_in_is_refused_on_an_answer_already_held_in(
    root: Path,  # noqa: F811 — the fixture, by its name
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    by_command(
        root,
        shlex.join(
            ["digline", "record", "import", *WRITES, "--good", LONG_ID, "--by", "Ada"]
        ),
        monkeypatch,
    )
    before = (root / CAPTURED).read_bytes()
    from digline.cli.main import main

    with monkeypatch.context() as patched:
        patched.chdir(root)
        code = main(["record", "revise", *WRITES, "--held-in", LONG_ID, "--by", "Ada"])
    assert code != 0
    assert "is already held in" in capsys.readouterr().err
    assert (root / CAPTURED).read_bytes() == before


def test_held_in_with_a_verdict_is_refused(
    root: Path,  # noqa: F811 — the fixture, by its name
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from digline.cli.main import main

    with monkeypatch.context() as patched:
        patched.chdir(root)
        code = main(
            [
                "record",
                "revise",
                *WRITES,
                "--held-in",
                LONG_ID,
                "--good",
                "--by",
                "Ada",
            ]
        )
    assert code != 0
    assert "takes no --case, --good, --bad or --failing" in capsys.readouterr().err


def test_a_case_file_that_is_held_out_and_held_in_is_refused(tmp_path: Path) -> None:
    from digline.host import read_cases

    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "a",
                    "reviewed_answer": {
                        "output": "o",
                        "check": "llm_rubric",
                        "good": True,
                        "input": "q",
                        "held_out": True,
                        "held_in": {"by": "Ada", "at": AT},
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="it is one or the other"):
        read_cases(path)


# -- 3. the runs a stability scan passed over --------------------------------- #


def test_runs_of_a_foreign_schema_are_counted_and_said(tmp_path: Path) -> None:
    """Two runs, the first set to a schema this version does not read: the
    reading says it was not read, in text and in `--json`. Mutation: passing
    `unread=0` in `_stability` turns it red."""
    from tests._helpers import cli
    from tests.test_stability import _run, _write  # pyright: ignore[reportPrivateUsage]

    _write(tmp_path, "")
    first = _run(tmp_path)
    second = _run(tmp_path)
    [path] = (tmp_path / ".digline" / "acme" / "runs").rglob(f"{first}.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = 999
    path.write_text(json.dumps(document), encoding="utf-8")

    said = cli(tmp_path, "explain", "--suite", "suite.py", "--run", second)
    assert "1 run not read: schema unknown to this version." in said.stdout, (
        said.stdout + said.stderr
    )
    shown = cli(tmp_path, "explain", "--suite", "suite.py", "--run", second, "--json")
    agreement = _agreement(shown.stdout)
    assert (agreement["runs_read"], agreement["runs_unread"]) == (1, 1)


def test_no_unread_run_says_nothing(tmp_path: Path) -> None:
    """The control: two runs this version reads, and no sentence."""
    from tests._helpers import cli
    from tests.test_stability import _run, _write  # pyright: ignore[reportPrivateUsage]

    _write(tmp_path, "")
    _run(tmp_path)
    second = _run(tmp_path)
    said = cli(tmp_path, "explain", "--suite", "suite.py", "--run", second)
    assert "not read" not in said.stdout
    shown = cli(tmp_path, "explain", "--suite", "suite.py", "--run", second, "--json")
    agreement = _agreement(shown.stdout)
    assert (agreement["runs_read"], agreement["runs_unread"]) == (2, 0)


def _agreement(stdout: str) -> Any:
    [tally] = [f for f in json.loads(stdout)["facts"] if f.get("kind") == "agreement"]
    return tally["agreement"]
