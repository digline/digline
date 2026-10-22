"""`digline run` says how many checks could not run. (#654)

On stderr when there are any, and in `--json` always, `0` included: a count a
pipeline reads is a measurement even when it is zero, while a line a person
reads at zero would be noise. The count is every verdict in `error`, the case
checks and the run's aggregates, which is `errored_verdicts`.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests._helpers import cli

#: One case raises at the target, so its one check errors; the other two are
#: judged. The one case labelled positive is the one that errored, so `Recall`
#: has an empty denominator and errors too: one case check and one aggregate.
ERRORED = """
from digline.core import Contains, Recall
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="errored",
    assertions=[Contains(needle="Rome")],
    run_assertions=[Recall(over="contains", threshold="1/2", tolerance=0.0)],
    cases=[
        Case(id="a", label="negative"),
        Case(id="b", label="negative"),
        Case(id="flaky", label="positive"),
    ],
)


def target(case):
    if case.id == "flaky":
        raise TimeoutError("provider did not answer")
    return Response(output="Paris")
"""

LINE = "digline: 2 checks could not run."


def errored(repo: Path) -> Path:
    path = repo / "suite_errored.py"
    path.write_text(ERRORED, encoding="utf-8")
    return path


def test_the_fixture_errs_once_in_a_case_and_once_in_an_aggregate(repo: Path) -> None:
    """The guard on the two tests below: read off the run file, not off the
    code under test, so a count that left the aggregates out cannot pass by a
    fixture that has none."""
    errored(repo)
    ran = cli(repo, "run", "--suite", "suite_errored.py")
    document = json.loads(
        (
            repo
            / ".digline"
            / "acme-bank"
            / "runs"
            / "errored"
            / f"{ran.stdout.strip()}.json"
        ).read_text(encoding="utf-8")
    )
    in_cases = sum(
        v["status"] == "error" for case in document["results"] for v in case["verdicts"]
    )
    in_aggregates = sum(v["status"] == "error" for v in document["aggregate"])
    assert (in_cases, in_aggregates) == (1, 1)


def test_run_says_on_stderr_how_many_checks_could_not_run(repo: Path) -> None:
    errored(repo)
    ran = cli(repo, "run", "--suite", "suite_errored.py")
    assert ran.returncode == 0, ran.stderr
    assert LINE in ran.stderr.splitlines(), ran.stderr


def test_run_says_nothing_on_stderr_when_every_check_ran(repo: Path) -> None:
    ran = cli(repo, "run", "--suite", "suite_qa.py")
    assert ran.returncode == 0, ran.stderr
    assert "could not run" not in ran.stderr, ran.stderr


def test_run_json_carries_the_count_and_zero_is_a_count(repo: Path) -> None:
    ran = cli(repo, "run", "--suite", "suite_qa.py", "--json")
    assert json.loads(ran.stdout)["errored_checks"] == 0, ran.stdout


def test_run_json_carries_the_count_of_case_checks_and_aggregates(repo: Path) -> None:
    errored(repo)
    ran = cli(repo, "run", "--suite", "suite_errored.py", "--json")
    assert json.loads(ran.stdout)["errored_checks"] == 2, ran.stdout
