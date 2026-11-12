"""The estimate before a run, and the ceiling during it. (ADR 0064)

Proposed by a first use outside the project, on a Java application with a
judged suite, where a run kept paying, case after case, for a judge it could
not price. The suite here is the one that use had the shape of: 3 cases, 2
samples each, every answer judged 3 times by a `Repeated`. Every call costs
0.01 USD, the target's and the judge's, so a case is 2 + 6 calls, 0.08 USD,
and the run 0.24.

- Before the first call `run` says what the suite's newest stored run
  measured, scaled to the cases it will call, and which run that was; with no
  stored run it gives no figure and says so. An estimate, never a bound.
- `--max-cost` is a ceiling on what the run **measures** as it goes: above
  it the run stops between two cases, exits 2, names where it was and the
  command that finishes it, and the journal keeps what was paid for.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from tests._helpers import cli

from digline.core import Contains
from digline.core.refused import RefusedError
from digline.run import Case, CostCeilingReached, Suite, execute

SUITE_PY = """\
import json
from pathlib import Path

from digline.core import LlmRubric, Repeated, Usage
from digline.run import Case, Response, Suite
from digline.targets import Completion, ModelPrice, Pricing
from digline.targets.judge import ScoreJudge

#: Every call the target makes is appended here, so a test can count them.
CALLS = Path(__file__).with_name("calls.txt")


class Judge(ScoreJudge):
    provider = "fake"
    system = "unused"

    def __init__(self):
        # 10 000 USD a million input tokens: one token is 0.01 USD.
        super().__init__(
            model="j-1", max_tokens=16,
            pricing=Pricing({"j-1": ModelPrice(10_000.0, 0.0)}),
        )

    def _complete(self, system, prompt):
        return Completion(text=json.dumps({"score": 1.0, "reason": "ok"}),
                          usage=Usage(1, 0))


def target(case):
    with CALLS.open("a") as calls:
        calls.write(case.id + "\\n")
    return Response(output="yes", cost_usd=0.01, usage=Usage(1, 0))


suite = Suite(
    tenant="acme", environment="dev", name="support",
    assertions=[Repeated(
        LlmRubric(rubric="ok?", judge=Judge(), threshold=0.5, tolerance=0.0),
        samples=3, min_agreement="2/3",
    )],
    cases=[Case(id="one"), Case(id="two"), Case(id="three")],
    samples=2, min_agreement="2/2",
)
"""

KEY = re.compile(r"\d{4}-\d\d-\d\dT[\d-]+-[0-9a-f]+")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "suite.py").write_text(SUITE_PY, encoding="utf-8")
    return tmp_path


def calls(root: Path) -> list[str]:
    path = root / "calls.txt"
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def test_the_first_run_has_no_estimate_and_says_so(root: Path) -> None:
    done = cli(root, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    assert (
        "digline: no cost estimate: this suite has no stored run to read one "
        "from, and nothing before the first call can say what a run will cost"
    ) in done.stderr
    # Said before the first call: the plan, the estimate, then the bill.
    assert done.stderr.index("no cost estimate") < done.stderr.index("judge:")


def test_the_second_run_is_estimated_from_the_first(root: Path) -> None:
    first = cli(root, "run", "--suite", "suite.py")
    assert first.returncode == 0, first.stderr
    key = first.stdout.strip()
    second = cli(root, "run", "--suite", "suite.py")
    assert second.returncode == 0, second.stderr
    assert (
        f"digline: estimated from run {key}: 0.2400 USD, its 0.2400 USD over 3 "
        "cases scaled to 3; an estimate, not a ceiling\n"
    ) in second.stderr
    # The plan beside it: 3 × 2 calls to the target, 6 judgements a case.
    assert "3 cases × 2 samples = 6 calls to the target" in second.stderr
    assert "6 judgements a case" in second.stderr


def test_the_ceiling_stops_the_run_where_it_crossed(root: Path) -> None:
    """0.08 after the first case is under 0.10, 0.16 after the second is
    over: the run stops there, and the third case is never called."""
    done = cli(root, "run", "--suite", "suite.py", "--max-cost", "0.10")
    assert done.returncode == 2, done.stderr
    assert (
        "digline: stopped by the cost ceiling of 0.1000 USD after 2 of 3 cases: "
        "0.1600 USD measured so far"
    ) in done.stderr
    assert calls(root) == ["one", "one", "two", "two"]
    assert done.stdout == ""
    # No run document: the run did not finish, and the journal holds it.
    assert not list((root / ".digline" / "acme" / "runs").rglob("*.json"))
    [finish] = [line for line in done.stderr.splitlines() if "finish it with" in line]
    key = KEY.search(finish)
    assert key is not None
    assert "digline run --suite suite.py --resume " in finish

    resumed = cli(root, "run", "--suite", "suite.py", "--resume", key.group(0))
    assert resumed.returncode == 0, resumed.stderr
    # The resume calls the third case alone, and the run holds all three.
    assert calls(root) == ["one", "one", "two", "two", "three", "three"]
    run_file = next((root / ".digline" / "acme" / "runs" / "support").glob("*.json"))
    document = json.loads(run_file.read_text(encoding="utf-8"))
    assert [r["case_id"] for r in document["results"]] == ["one", "two", "three"]


def test_a_ceiling_above_the_run_changes_nothing(root: Path) -> None:
    done = cli(root, "run", "--suite", "suite.py", "--max-cost", "0.25")
    assert done.returncode == 0, done.stderr
    assert "cost ceiling" not in done.stderr
    assert len(calls(root)) == 6


@pytest.mark.parametrize("ceiling", [0.0, -1.0, float("nan"), float("inf")])
def test_a_ceiling_that_cannot_hold_is_refused_before_any_call(
    ceiling: float,
) -> None:
    asked: list[str] = []

    def target(case: object) -> object:
        asked.append("called")
        raise AssertionError("no call may be made")

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="s",
        assertions=[Contains(needle="yes")],
        cases=[Case(id="one")],
    )
    with pytest.raises(RefusedError, match="a cost ceiling is a positive number"):
        execute(
            suite,
            target,  # pyright: ignore[reportArgumentType]
            created_at="2026-11-12T00:00:00+00:00",
            max_cost=ceiling,
        )
    assert asked == []


def test_the_refusal_carries_the_facts_it_says() -> None:
    stopped = CostCeilingReached.stopped(
        done=2, declared=3, spent_usd=0.16, ceiling_usd=0.1
    )
    assert (stopped.done, stopped.declared) == (2, 3)
    assert "after 2 of 3 cases: 0.1600 USD" in str(stopped)
    assert isinstance(stopped, RefusedError)
