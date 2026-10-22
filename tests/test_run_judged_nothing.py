"""`digline run` exits 2 when it judged nothing, and only then. (ADR 0049 §1, §3)

`0` asserts that a measurement was made. A run in which none of the cases the
suite measures was judged made none, so `run` says `2` about it, as `report`
and `explain` already did about the same run (`run_exit_code`). It still
writes the run and still prints its key: the document is real, the measurement
is what is missing.

**Only that cause.** `run_exit_code` gives `2` for two more, and `run` does not
follow it there: a run with one case that could not be judged beside cases
that were, and a first run whose calibration case left its band, still exit
`0` from `digline run`. Those two were held only by the generic `run_key`
helper before; here they are held on purpose. The same imbalance is held in
`tests/test_calibration.py`, which asserts the `0` for a lost scale. (#654)
"""

from __future__ import annotations

from pathlib import Path

from tests._helpers import cli, write_suite

from digline.cli import EXIT_OK, EXIT_UNJUDGED

SENTENCE = "None of the cases this suite measures was judged"

SUSPENDED_SUITE = """
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="parked",
    assertions=[Contains(needle="Rome")],
    cases=[
        Case(id="one", suspended="the API is down, ticket 1"),
        Case(id="two", suspended="the API is down, ticket 1"),
    ],
)


def target(case):
    raise AssertionError("a suspended case is never called")
"""

ERRORED_SUITE = """
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="down",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one"), Case(id="two")],
)


def target(case):
    raise TimeoutError("provider did not answer")
"""

# A calibration case whose judge places the half-right answer at 1.0, outside
# its band 0.3-0.7: the scale is lost on the first run, with no reference.
CALIBRATED_SUITE = """
from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Calibration, Case, Response, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="r")


suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="calibrated",
    assertions=[
        Contains(needle="Rome"),
        LlmRubric(rubric="right?", judge=judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[
        Case(id="one"),
        Case(
            id="half",
            calibration=Calibration(
                output="HALF-RIGHT", check="llm_rubric", low=0.3, high=0.7, input=""
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case):
    return Response(output="Rome", input="capital?")
"""


def _written(repo: Path, suite: str, stdout: str) -> bool:
    """The run is still written, and its key is the whole of stdout."""
    lines = stdout.strip().splitlines()
    return (
        len(lines) == 1
        and (
            repo / ".digline" / "acme-bank" / "runs" / suite / f"{lines[0]}.json"
        ).is_file()
    )


def _run(repo: Path, source: str, name: str):  # type: ignore[no-untyped-def]
    (repo / name).write_text(source, encoding="utf-8")
    return cli(repo, "run", "--suite", name)


def test_a_run_whose_every_case_is_suspended_exits_two(repo: Path) -> None:
    ran = _run(repo, SUSPENDED_SUITE, "suite_parked.py")
    assert ran.returncode == EXIT_UNJUDGED, ran.stderr
    assert _written(repo, "parked", ran.stdout)
    assert SENTENCE in ran.stderr


def test_a_run_whose_every_case_errored_exits_two(repo: Path) -> None:
    ran = _run(repo, ERRORED_SUITE, "suite_down.py")
    assert ran.returncode == EXIT_UNJUDGED, ran.stderr
    assert _written(repo, "down", ran.stdout)
    assert SENTENCE in ran.stderr


def test_one_case_that_could_not_be_judged_still_exits_zero_from_run(
    repo: Path,
) -> None:
    """`compare`, `report` and `explain` say `2` about this run. `run` does
    not: something was judged, and `run` reads only `nothing_judged`."""
    write_suite(repo, extra=', Case(id="flaky")')
    ran = cli(repo, "run", "--suite", "suite_qa.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    assert SENTENCE not in ran.stderr
    # The state is real: read alone, the same run is a 2.
    read = cli(repo, "explain", "--suite", "suite_qa.py", "--run", ran.stdout.strip())
    assert read.returncode == EXIT_UNJUDGED, read.stderr


def test_a_lost_scale_still_exits_zero_from_run(repo: Path) -> None:
    """`report` and `explain` say `2` about a first run that lost its scale.
    `run` does not: the cases were judged."""
    ran = _run(repo, CALIBRATED_SUITE, "suite_calibrated.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    assert SENTENCE not in ran.stderr
    # The state is real: read alone, the same run is a 2.
    read = cli(
        repo, "explain", "--suite", "suite_calibrated.py", "--run", ran.stdout.strip()
    )
    assert read.returncode == EXIT_UNJUDGED, read.stderr
