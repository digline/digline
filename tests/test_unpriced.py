"""A call whose counts were read and whose cost cannot be computed (#569).

ADR 0004 §8. A call that answered can leave digline holding three things
about its cost: priced, counts not recorded (`usage=None`, #629), and **cost
not computable**, which had no word. The plugin refused, and the check or the
case errored over a problem of accounting. `Completion.unpriced` is the word:
the counts stay on the line, the money does not, and `every_cost_known` says
so.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path

import pytest
from tests._helpers import cli

from digline.cli import EXIT_OK
from digline.core import (
    Contains,
    CostBudget,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Run,
    RunUsage,
)
from digline.run import Case, Response, Suite, execute
from digline.run.driver import default_mapper, judge_totals
from digline.targets import Completion, ProviderTarget
from digline.targets.judge import ScoreJudge
from digline.targets.pricing import (
    ModelPrice,
    Pricing,
    UnknownModelError,
    Usage,
    free,
)
from digline.wire import EXIT_UNJUDGED, run_exit_code

COUNTS = Usage(input_tokens=100, output_tokens=10)


# --------------------------------------------------------------------------- #
# The vocabulary: `Completion.unpriced` (§8.2)
# --------------------------------------------------------------------------- #


def test_unpriced_is_none_by_default_and_for_the_pair() -> None:
    """What every plugin written before the field returns."""
    assert Completion(text="yes", usage=COUNTS).unpriced is None


def test_unpriced_with_counts_is_a_sentence_kept_as_given() -> None:
    reply = Completion(text="yes", usage=COUNTS, unpriced="no rate for 'eu'")
    assert reply.unpriced == "no rate for 'eu'"
    assert reply.usage == COUNTS


def test_unpriced_with_no_counts_is_refused() -> None:
    """Counts not recorded already say the cost is not known."""
    with pytest.raises(ValueError, match="usage=None"):
        Completion(text="yes", usage=None, unpriced="no rate for 'eu'")


@pytest.mark.parametrize("sentence", ["", "   "])
def test_an_empty_sentence_is_refused(sentence: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        Completion(text="yes", usage=COUNTS, unpriced=sentence)


# --------------------------------------------------------------------------- #
# The predicate: `Pricing.why_unpriced`, and its default (§8.4)
# --------------------------------------------------------------------------- #

NO_CACHE_RATES = Pricing(per_model={"m-1": ModelPrice(1.0, 2.0)})
CACHED_READS = Usage(input_tokens=100, output_tokens=10, cache_read_tokens=50)
CACHE_WRITES = Usage(input_tokens=100, output_tokens=10, cache_write_tokens=40)


@pytest.mark.parametrize(
    ("usage", "kind", "count"),
    [(CACHED_READS, "cached-read", 50), (CACHE_WRITES, "cache-write", 40)],
)
def test_the_default_answers_for_a_rate_the_list_lacks(
    usage: Usage, kind: str, count: int
) -> None:
    sentence = NO_CACHE_RATES.why_unpriced("m-1", usage)
    assert sentence is not None
    assert f"used {count} {kind} tokens" in sentence
    assert f"declares no {kind} rate" in sentence


def test_cost_still_raises_where_the_predicate_has_a_sentence() -> None:
    """A caller that does not ask first gets no number nobody stated."""
    with pytest.raises(UnknownModelError, match="cached-read"):
        NO_CACHE_RATES.cost("m-1", CACHED_READS)


def test_a_rate_the_list_has_is_priced_and_the_predicate_is_silent() -> None:
    """The control: with the rate, a figure."""
    priced = NO_CACHE_RATES.override("m-1", ModelPrice(1.0, 2.0, 0.1))
    assert priced.why_unpriced("m-1", CACHED_READS) is None
    assert priced.cost("m-1", CACHED_READS) == pytest.approx(0.000125)


def test_an_unknown_model_is_not_unpriced_and_cost_refuses_it() -> None:
    """The reason for a predicate: `UnknownModelError` covers this too, and a
    typo in a model's name is not *cost not known*."""
    assert NO_CACHE_RATES.why_unpriced("m-typo", CACHED_READS) is None
    with pytest.raises(UnknownModelError, match="no price"):
        NO_CACHE_RATES.cost("m-typo", CACHED_READS)


def test_a_list_the_user_built_inherits_the_default() -> None:
    """A user enters by doing nothing: `override` and `free` give the base
    class, and so does `Pricing(...)`."""
    theirs = Pricing(per_model={}).override("theirs", ModelPrice(1.0, 2.0))
    assert theirs.why_unpriced("theirs", CACHED_READS) is not None
    assert free("hosted").why_unpriced("hosted", CACHED_READS) is None


# --------------------------------------------------------------------------- #
# The target: the one reading of a reply (§8.5)
# --------------------------------------------------------------------------- #

CREATED = "2026-01-01T00:00:00+00:00"
PRICING = Pricing(
    per_model={
        "m-1": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0),
        "j-1": ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0),
    }
)
GEO = "model 'm-1' ran in inference geography 'not_available'"


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    path = tmp_path / "prompt.md"
    path.write_text("Say yes.\n", encoding="utf-8")
    return path


class Replying(ProviderTarget):
    """A provider target whose plugin hands over each reply as given."""

    provider = "fake"

    def __init__(self, prompt: Path, *replies: Completion) -> None:
        super().__init__(prompt, "m-1", pricing=PRICING)
        self.replies = list(replies)

    def _complete(self, prompt: str, system: str | None) -> Completion:
        return self.replies.pop(0)


def suite(*assertions: object, cases: int = 1) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=list(assertions) or [Contains(needle="yes", threshold=1.0)],  # pyright: ignore[reportArgumentType]
        cases=[Case(id=f"c{n}") for n in range(1, cases + 1)],
    )


def usage_of(run: Run) -> RunUsage:
    assert run.usage is not None
    return run.usage


def test_the_plugins_sentence_keeps_the_counts_and_drops_the_cost(
    prompt: Path,
) -> None:
    reply = Completion(text="yes", usage=COUNTS, unpriced=GEO)
    response = Replying(prompt, reply)(Case(id="c1"))
    assert (response.usage, response.cost_usd, response.unpriced) == (COUNTS, None, GEO)


def test_the_price_lists_sentence_keeps_the_counts_and_drops_the_cost(
    prompt: Path,
) -> None:
    """The core's own refusal moves: no `CostBudget`, no error, no figure."""
    target = Replying(prompt, Completion(text="yes", usage=CACHED_READS))
    response = target(Case(id="c1"))
    assert response.usage == CACHED_READS
    assert response.cost_usd is None
    assert response.unpriced == PRICING.why_unpriced("m-1", CACHED_READS)


def test_a_priced_reply_has_its_figure_and_no_sentence(prompt: Path) -> None:
    """The control."""
    response = Replying(prompt, Completion(text="yes", usage=COUNTS))(Case(id="c1"))
    assert response.cost_usd == pytest.approx(0.00012)
    assert response.unpriced is None


def test_the_sentence_reaches_the_assertion(prompt: Path) -> None:
    reply = Completion(text="yes", usage=COUNTS, unpriced=GEO)
    response = Replying(prompt, reply)(Case(id="c1"))
    assert default_mapper(response, Case(id="c1")).unpriced == GEO


def test_the_target_line_counts_the_call_and_its_tokens_and_not_its_cost(
    prompt: Path,
) -> None:
    reply = Completion(text="yes", usage=COUNTS, unpriced=GEO)
    run = execute(suite(), Replying(prompt, reply), created_at=CREATED)
    line = usage_of(run).target
    assert (line.calls, line.counted, line.spent_usd) == (1, 1, 0.0)
    assert (line.tokens.input_tokens, line.tokens.output_tokens) == (100, 10)
    assert line.every_cost_known is False
    assert line.every_call_seen is True
    assert [v.status for v in run.results[0].verdicts] == ["pass"]
    assert run.results[0].error_kind is None


# --------------------------------------------------------------------------- #
# The judge: `unpriced_calls`, and the driver reading two counts (§8.5)
# --------------------------------------------------------------------------- #

VERDICT = json.dumps({"score": 1.0, "reason": "fine"})


class ReplyingJudge(ScoreJudge):
    """A `JudgeBase` whose plugin hands over each reply as given."""

    provider = "fake"
    system = "unused"

    def __init__(self, *replies: Completion, pricing: Pricing = PRICING) -> None:
        super().__init__(model="j-1", max_tokens=16, pricing=pricing)
        self.replies = list(replies)

    def _complete(self, system: str, prompt: str) -> Completion:
        return self.replies.pop(0)


class Answering:
    """A target that answers, priced at zero, so a judge line is alone in what
    its test varies."""

    config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        return Response(output="yes", cost_usd=0.0, usage=Usage(0, 0))


def rubric(judge: object) -> LlmRubric:
    return LlmRubric(
        rubric="Is it polite?",
        judge=judge,  # pyright: ignore[reportArgumentType]
        threshold=0.5,
        tolerance=0.0,
    )


def test_an_unpriced_judge_call_is_counted_with_its_tokens_and_not_its_money() -> None:
    judge = ReplyingJudge(Completion(text=VERDICT, usage=COUNTS, unpriced=GEO))
    judge("Output to judge:\nyes")
    assert (judge.calls, judge.uncounted_calls, judge.unpriced_calls) == (1, 0, 1)
    assert judge.spent_usd == 0.0
    assert judge.tokens == COUNTS
    assert judge.unpriced_reasons == {GEO: 1}


def test_the_price_lists_sentence_is_an_unpriced_judge_call() -> None:
    judge = ReplyingJudge(Completion(text=VERDICT, usage=CACHED_READS))
    judge("Output to judge:\nyes")
    assert (judge.calls, judge.unpriced_calls, judge.spent_usd) == (1, 1, 0.0)
    assert judge.tokens == CACHED_READS


def test_a_judge_call_with_no_counts_is_uncounted_and_not_unpriced() -> None:
    """The second direction: `usage=None` reads as before (#629)."""
    judge = ReplyingJudge(Completion(text=VERDICT, usage=None))
    judge("Output to judge:\nyes")
    assert (judge.calls, judge.uncounted_calls, judge.unpriced_calls) == (1, 1, 0)
    assert judge.unpriced_reasons == {}


def test_the_judge_line_counts_an_unpriced_call_and_not_its_cost() -> None:
    judge = ReplyingJudge(Completion(text=VERDICT, usage=COUNTS, unpriced=GEO))
    run = execute(suite(rubric(judge)), Answering(), created_at=CREATED)
    line = usage_of(run).judge
    assert (line.calls, line.counted, line.spent_usd) == (1, 1, 0.0)
    assert (line.tokens.input_tokens, line.tokens.output_tokens) == (100, 10)
    assert line.every_cost_known is False
    assert [v.status for v in run.results[0].verdicts] == ["pass"]


class HandWritten:
    """A judge written by hand, keeping the counts it was given, after one
    call that answered."""

    config = {"provider": "hand", "model": "h-1"}

    def __init__(self, **counts: int) -> None:
        self.calls = 1
        self.spent_usd = 0.0
        self.tokens = Usage(0, 0)
        self.raised_calls = 0
        for name, value in counts.items():
            setattr(self, name, value)

    def __call__(self, prompt: str) -> JudgeReply:
        self.calls += 1
        return JudgeReply(score=1.0, reason="fine")


@pytest.mark.parametrize(
    ("counts", "known"),
    [
        ({"uncounted_calls": 0, "unpriced_calls": 0}, True),
        ({"uncounted_calls": 0}, None),
        ({"unpriced_calls": 0}, None),
        ({}, None),
        ({"uncounted_calls": 1}, False),
        ({"unpriced_calls": 1}, False),
        ({"uncounted_calls": 0, "unpriced_calls": 1}, False),
    ],
)
def test_true_is_read_off_two_zeros_and_never_assumed(
    counts: dict[str, int], known: bool | None
) -> None:
    """A judge that keeps one count and not the other is *not recorded*,
    unless the count it keeps is above zero."""
    line = judge_totals(suite(rubric(HandWritten(**counts))))
    assert line.every_cost_known is known


# --------------------------------------------------------------------------- #
# The false line: a price that raises after an answer (§8.6)
# --------------------------------------------------------------------------- #


class Raising(Pricing):
    """A list digline did not write, whose `cost` raises on these counts and
    whose predicate does not say so."""

    def why_unpriced(self, model: str, usage: Usage) -> str | None:
        return None

    def cost(self, model: str, usage: Usage) -> float:
        if usage.cache_read_tokens:
            raise UnknownModelError("cached reads are not on this list")
        return Pricing.cost(self, model, usage)


RAISING = Raising(per_model=PRICING.per_model)


def test_a_price_that_raises_leaves_a_true_judge_line() -> None:
    """ADR 0004 §8.6's second row, measured at `80b70b7e`: two calls, the
    second's price raising, read `calls=2, counted=2`, one call's tokens and
    money, and `every_cost_known: true`. The line now says what it holds."""
    judge = ReplyingJudge(
        Completion(text=VERDICT, usage=COUNTS),
        Completion(text=VERDICT, usage=CACHED_READS),
        pricing=RAISING,
    )
    run = execute(suite(rubric(judge), cases=2), Answering(), created_at=CREATED)
    line = usage_of(run).judge
    assert (line.calls, line.counted) == (2, 2)
    assert (line.tokens.input_tokens, line.tokens.output_tokens) == (200, 20)
    assert line.spent_usd == pytest.approx(0.00012)
    assert line.every_cost_known is False


def test_a_price_that_raises_errors_the_check_naming_the_price() -> None:
    judge = ReplyingJudge(Completion(text=VERDICT, usage=CACHED_READS), pricing=RAISING)
    run = execute(suite(rubric(judge)), Answering(), created_at=CREATED)
    (verdict,) = run.results[0].verdicts
    assert verdict.status == "error"
    assert "the judge raised" not in verdict.reason
    assert verdict.reason.startswith(
        "the judge answered, and pricing its reply raised UnknownModelError"
    )


def test_an_unknown_judge_model_is_the_same_true_line() -> None:
    """The judge's `preflight()` is not called by the driver, so a model the
    list does not know answers and its price raises."""
    judge = ReplyingJudge(
        Completion(text=VERDICT, usage=COUNTS),
        pricing=Pricing(per_model={}),
    )
    run = execute(suite(rubric(judge)), Answering(), created_at=CREATED)
    line = usage_of(run).judge
    assert (line.calls, line.counted, line.every_cost_known) == (1, 1, False)
    (verdict,) = run.results[0].verdicts
    assert "pricing its reply raised UnknownModelError: no price" in verdict.reason


# --------------------------------------------------------------------------- #
# The sentence, for the person who ran the command (§8.3)
# --------------------------------------------------------------------------- #


def test_each_distinct_sentence_is_handed_over_once_after_the_run(
    prompt: Path,
) -> None:
    replies = [
        Completion(text="yes", usage=COUNTS, unpriced=GEO),
        Completion(text="yes", usage=COUNTS, unpriced=GEO),
        Completion(text="yes", usage=CACHED_READS),
    ]
    judge = ReplyingJudge(
        *(
            Completion(text=VERDICT, usage=COUNTS, unpriced="judge geo")
            for _ in range(3)
        )
    )
    said: list[str] = []
    execute(
        suite(rubric(judge), cases=3),
        Replying(prompt, *replies),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    assert said == [GEO, PRICING.why_unpriced("m-1", CACHED_READS), "judge geo"]


def test_a_judges_sentence_from_an_earlier_run_is_not_this_runs(prompt: Path) -> None:
    judge = ReplyingJudge(
        Completion(text=VERDICT, usage=COUNTS, unpriced="earlier"),
        Completion(text=VERDICT, usage=COUNTS),
    )
    execute(suite(rubric(judge)), Answering(), created_at=CREATED)
    said: list[str] = []
    execute(
        suite(rubric(judge)), Answering(), created_at=CREATED, on_unpriced=said.append
    )
    assert said == []


def test_a_priced_run_hands_over_no_sentence(prompt: Path) -> None:
    """The control."""
    said: list[str] = []
    replies = [Completion(text="yes", usage=COUNTS)]
    judge = ReplyingJudge(Completion(text=VERDICT, usage=COUNTS))
    execute(
        suite(rubric(judge)),
        Replying(prompt, *replies),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    assert said == []


#: A suite whose target's replies report a geography with no rate, written to
#: disk so the command line runs it. The counts were read; the cost was not.
CLI_SUITE = """\
from digline.core import Contains
from digline.run import Case, Response, Suite
from digline.targets import Usage

suite = Suite(
    tenant="acme",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="yes", threshold=1.0)],
    cases=[Case(id="c1"), Case(id="c2")],
)


def target(case):
    return Response(
        output="yes",
        usage=Usage(input_tokens=100, output_tokens=10),
        cost_usd=%(cost)s,
        unpriced=%(unpriced)r,
    )
"""


def _run_cli(tmp_path: Path, *, cost: str, unpriced: str | None) -> tuple[int, str]:
    (tmp_path / "suite_qa.py").write_text(
        CLI_SUITE % {"cost": cost, "unpriced": unpriced}, encoding="utf-8"
    )
    done = cli(tmp_path, "run", "--suite", "suite_qa.py")
    return done.returncode, done.stderr


def test_the_run_prints_the_sentence_once_after_the_bill(tmp_path: Path) -> None:
    code, stderr = _run_cli(tmp_path, cost="None", unpriced=GEO)
    assert code == EXIT_OK, stderr
    lines = stderr.splitlines()
    bill = next(
        i for i, line in enumerate(lines) if line.startswith("digline: target:")
    )
    assert "cost not known for every call" in lines[bill]
    sentence = f"digline: cost not computable: {GEO}"
    assert lines.count(sentence) == 1
    assert lines.index(sentence) > bill


def test_a_priced_run_prints_neither(tmp_path: Path) -> None:
    """The control: the sentences appear only where their fact holds."""
    code, stderr = _run_cli(tmp_path, cost="0.001", unpriced=None)
    assert code == EXIT_OK, stderr
    assert "cost not known for every call" not in stderr
    assert "cost not computable" not in stderr


# --------------------------------------------------------------------------- #
# A `CostBudget` over an unpriced cost: the error stays, the word moves (§8.7)
# --------------------------------------------------------------------------- #


def test_a_budget_over_an_unpriced_cost_says_not_computable_and_why() -> None:
    verdict = CostBudget(max_usd=0.1, tolerance=0.0)(
        EvaluatorInputs(output="yes", cost_usd=None, unpriced=GEO)
    )
    assert verdict.status == "error"
    assert "not computable" in verdict.reason
    assert GEO in verdict.reason
    assert "missing" not in verdict.reason


def test_a_budget_over_a_missing_cost_still_says_missing() -> None:
    """The control: no sentence, and the word is the one it was."""
    verdict = CostBudget(max_usd=0.1, tolerance=0.0)(
        EvaluatorInputs(output="yes", cost_usd=None)
    )
    assert verdict.status == "error"
    assert verdict.reason == (
        "cost_usd is missing: an unverifiable budget is not a budget met"
    )


def test_a_budget_in_a_suite_errors_and_the_content_is_still_judged(
    prompt: Path,
) -> None:
    """§8.9's fourth direction. `run_exit_code` is `2`, for an unjudged check
    beside judged ones; `digline run` itself exits `0` there, and `2` only
    where nothing was judged (ADR 0049 §3)."""
    reply = Completion(text="yes", usage=COUNTS, unpriced=GEO)
    budgeted = suite(
        Contains(needle="yes", threshold=1.0), CostBudget(max_usd=0.1, tolerance=0.0)
    )
    run = execute(budgeted, Replying(prompt, reply), created_at=CREATED)
    content, budget = run.results[0].verdicts
    assert content.status == "pass"
    assert budget.status == "error"
    assert f"cost_usd is not computable: {GEO}" in budget.reason
    assert run_exit_code(run, declared=budgeted.declared()) == EXIT_UNJUDGED


# --------------------------------------------------------------------------- #
# The guard: whoever overrides `cost` overrides `why_unpriced` (§8.4)
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[1]


def _modules_under_src() -> list[str]:
    """Every module this repository ships: `src/digline` and each plugin's
    `packages/*/src`. `__main__` modules run a command line on import."""
    found: list[str] = []
    roots = [ROOT / "src", *sorted((ROOT / "packages").glob("*/src"))]
    for root in roots:
        for package in sorted(
            p for p in root.iterdir() if (p / "__init__.py").exists()
        ):
            found.append(package.name)
            found.extend(
                info.name
                for info in pkgutil.walk_packages([str(package)], f"{package.name}.")
                if not info.name.endswith(".__main__")
            )
    return found


def _pricing_subclasses() -> list[type[Pricing]]:
    for name in _modules_under_src():
        importlib.import_module(name)
    stack: list[type[Pricing]] = list(Pricing.__subclasses__())
    seen: list[type[Pricing]] = []
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.append(cls)
        stack.extend(cls.__subclasses__())
    shipped = {name.split(".")[0] for name in _modules_under_src()}
    # One per name: a dataclass built with `slots=True` is a second class
    # object, and the first stays among the subclasses.
    named = {
        (cls.__module__, cls.__qualname__): cls
        for cls in seen
        if cls.__module__.split(".")[0] in shipped
    }
    return list(named.values())


def _breaks_the_rule(cls: type[Pricing]) -> bool:
    """Overrides `cost` and inherits `why_unpriced`: read as unpriced before
    its own `cost` is asked. Read off each class's own namespace."""
    return "cost" in vars(cls) and "why_unpriced" not in vars(cls)


class _BothOverridden(Pricing):
    """The rule's example: a list that prices its own way, and says where it
    cannot."""

    def why_unpriced(self, model: str, usage: Usage) -> str | None:
        return None

    def cost(self, model: str, usage: Usage) -> float:
        return Pricing.cost(self, model, usage)


def test_the_example_keeps_the_rule() -> None:
    assert not _breaks_the_rule(_BothOverridden)


def test_every_shipped_subclass_that_overrides_cost_overrides_the_predicate() -> None:
    """Binds this project's repositories, and no third party: nothing can. The
    scan finds `_WhereServed`, the one shipped subclass, which is its positive
    control: a scan that found nothing would pass over a broken rule."""
    shipped = _pricing_subclasses()
    assert "_WhereServed" in {cls.__name__ for cls in shipped}
    assert [cls.__qualname__ for cls in shipped if _breaks_the_rule(cls)] == []


# --------------------------------------------------------------------------- #
# The second direction: counts not recorded, as today (§8.9)
# --------------------------------------------------------------------------- #


def test_counts_not_recorded_read_as_not_recorded_and_say_no_sentence(
    prompt: Path,
) -> None:
    """`usage=None` is the second row of §8.1, and it reads as #629 left it on
    both lines: neither the tokens nor the cost of that call, and no
    `unpriced` sentence, because nothing was read to be priced."""
    said: list[str] = []
    judge = ReplyingJudge(Completion(text=VERDICT, usage=None))
    run = execute(
        suite(rubric(judge)),
        Replying(prompt, Completion(text="yes", usage=None)),
        created_at=CREATED,
        on_unpriced=said.append,
    )
    for line in (usage_of(run).target, usage_of(run).judge):
        assert (line.calls, line.counted, line.spent_usd) == (1, 0, 0.0)
        assert line.every_cost_known is False
    assert judge.unpriced_calls == 0
    assert said == []
