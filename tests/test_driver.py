"""The offline driver: a declared suite, a target, a `Run` and nothing else."""

from __future__ import annotations

import pytest

from digline.core import (
    Contains,
    CostBudget,
    Disclosure,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Regex,
    Run,
    Verdict,
    compare,
    config_hash,
    redact,
)
from digline.run import Case, Response, Suite, default_mapper, execute

CREATED = "2026-01-01T00:00:00+00:00"


def a_suite(*cases: Case, environment: str = "test") -> Suite:
    return Suite(
        tenant="acme",
        environment=environment,
        name="qa",
        assertions=[
            Contains(needle="Rome"),
            CostBudget(max_usd=0.10, tolerance=0.02),
        ],
        cases=cases or (Case(id="capital-of-italy"),),
    )


def answering(text: str, *, cost: float = 0.01) -> object:
    def target(case: Case) -> Response:
        return Response(
            output=text,
            input=f"What is the capital of {case.vars.get('country', 'Italy')}?",
            cost_usd=cost,
            latency_ms=120.0,
        )

    return target


# --------------------------------------------------------------------------- #
# What execute returns
# --------------------------------------------------------------------------- #


def test_it_returns_a_run_carrying_the_suite_identity() -> None:
    suite = a_suite()
    run = execute(suite, answering("Rome"), created_at=CREATED)  # type: ignore[arg-type]
    assert isinstance(run, Run)
    assert run.tenant == "acme"
    assert run.environment == "test"
    assert run.suite == "qa"
    assert run.config_hash == config_hash(suite.assertions)
    assert run.redacted is False


def test_every_case_yields_a_result_with_every_assertion() -> None:
    suite = a_suite(Case(id="one"), Case(id="two"))
    run = execute(suite, answering("Rome"), created_at=CREATED)  # type: ignore[arg-type]
    assert [c.case_id for c in run.results] == ["one", "two"]
    assert all(len(c.verdicts) == 2 for c in run.results)


def test_the_run_it_returns_can_be_compared_with_itself() -> None:
    run = execute(a_suite(), answering("Rome"), created_at=CREATED)  # type: ignore[arg-type]
    assert compare(run, run).counts == {"unchanged": 2}


def test_a_failing_answer_produces_a_failing_verdict() -> None:
    run = execute(a_suite(), answering("Milan"), created_at=CREATED)  # type: ignore[arg-type]
    contains = run.results[0].verdicts[0]
    assert contains.status == "fail"


def test_run_metadata_describes_the_launch_not_the_suite() -> None:
    """Which model, which prompt version: a property of this launch, hence an
    argument here rather than a field on the declared suite."""
    run = execute(
        a_suite(),
        answering("Rome"),  # type: ignore[arg-type]
        created_at=CREATED,
        run_metadata={"model": "claude-opus-5", "prompt_version": 3},
    )
    assert run.metadata["model"] == "claude-opus-5"


def test_run_metadata_is_payload_unless_the_suite_discloses_it() -> None:
    run = execute(
        a_suite(),
        answering("Rome"),  # type: ignore[arg-type]
        created_at=CREATED,
        run_metadata={"model": "claude-opus-5", "account_balance": 1499.0},
    )
    assert redact(run).metadata == {}
    allowed = Disclosure(run_metadata=frozenset({"model"}))
    assert redact(run, allowed).metadata == {"model": "claude-opus-5"}


# --------------------------------------------------------------------------- #
# A target that raises
# --------------------------------------------------------------------------- #


def test_a_target_that_raises_errors_that_case_and_leaves_the_others_intact() -> None:
    """The failure cannot travel through metadata — assertions do not read it,
    and teaching them to would reopen the channel ADR 0002 closes. The driver
    builds the errored verdicts itself, from the assertion protocol."""
    suite = a_suite(Case(id="fine-before"), Case(id="broken"), Case(id="fine-after"))

    def flaky(case: Case) -> Response:
        if case.id == "broken":
            raise TimeoutError("provider did not answer in 30s")
        return Response(output="Rome", cost_usd=0.01)

    run = execute(suite, flaky, created_at=CREATED)

    by_case = {c.case_id: c for c in run.results}
    assert len(by_case) == 3

    broken = by_case["broken"].verdicts
    assert len(broken) == 2  # every assertion of the suite, not just one
    assert all(v.status == "error" for v in broken)
    assert all(v.passed is False for v in broken)
    assert all("target raised TimeoutError" in v.reason for v in broken)

    for intact in ("fine-before", "fine-after"):
        assert all(v.status == "pass" for v in by_case[intact].verdicts)


def test_an_errored_case_keeps_the_assertion_identity() -> None:
    """Otherwise `compare()` could not pair the failure with its baseline, and a
    broken target would read as `missing` plus `new`."""
    suite = a_suite()

    def broken(case: Case) -> Response:
        raise RuntimeError("boom")

    run = execute(suite, broken, created_at=CREATED)
    ids = {v.assertion_id for v in run.results[0].verdicts}
    assert ids == {a.identity for a in suite.assertions}


def test_a_mapper_that_raises_is_diagnosed_separately() -> None:
    def bad_mapper(response: Response, case: Case) -> EvaluatorInputs:
        raise KeyError("vars")

    run = execute(
        a_suite(),
        answering("Rome"),  # type: ignore[arg-type]
        created_at=CREATED,
        mapper=bad_mapper,
    )
    assert all("mapper raised KeyError" in v.reason for v in run.results[0].verdicts)


def test_one_broken_assertion_does_not_take_the_run_down() -> None:
    class Exploding(Contains):
        def __call__(self, inputs: EvaluatorInputs) -> Verdict:
            raise ValueError("custom assertion is broken")

    suite = Suite(
        tenant="acme",
        environment="test",
        name="qa",
        assertions=[Contains(needle="Rome"), Exploding(needle="Rome")],
        cases=[Case(id="one")],
    )
    run = execute(suite, answering("Rome"), created_at=CREATED)  # type: ignore[arg-type]
    good, bad = run.results[0].verdicts
    assert good.status == "pass"
    assert bad.status == "error" and "assertion raised ValueError" in bad.reason


def test_a_long_failure_message_is_clipped() -> None:
    def verbose(case: Case) -> Response:
        raise RuntimeError("x" * 5000)

    run = execute(a_suite(), verbose, created_at=CREATED)
    assert all(len(v.reason) < 700 for v in run.results[0].verdicts)


# --------------------------------------------------------------------------- #
# The mapper is the boundary
# --------------------------------------------------------------------------- #


def test_the_default_mapper_carries_the_rendered_prompt() -> None:
    """Without it `llm_rubric` would judge an answer without knowing the
    question. Rendering happens inside the target, so the response carries it."""
    inputs = default_mapper(
        Response(output="Rome", input="What is the capital of Italy?"),
        Case(id="one"),
    )
    assert inputs.input == "What is the capital of Italy?"


def test_the_rendered_prompt_reaches_the_judge() -> None:
    seen: list[str] = []

    def judge(prompt: str) -> JudgeReply:
        seen.append(prompt)
        return JudgeReply(score=1.0, reason="fine")

    suite = Suite(
        tenant="acme",
        environment="test",
        name="qa",
        assertions=[
            LlmRubric(rubric="answers?", judge=judge, threshold=0.7, tolerance=0.05)
        ],
        cases=[Case(id="one")],
    )
    execute(suite, answering("Rome"), created_at=CREATED)  # type: ignore[arg-type]
    assert "What is the capital of Italy?" in seen[0]


def test_the_default_mapper_passes_expected_and_context() -> None:
    inputs = default_mapper(
        Response(output="Rome"),
        Case(id="one", expected="Rome", context=("Italy's capital is Rome.",)),
    )
    assert inputs.expected == "Rome"
    assert inputs.context == ("Italy's capital is Rome.",)


def test_case_and_response_metadata_do_not_overwrite_each_other() -> None:
    inputs = default_mapper(
        Response(output="Rome", metadata={"source": "response"}),
        Case(id="one", metadata={"source": "case"}),
    )
    assert inputs.metadata == {
        "case": {"source": "case"},
        "response": {"source": "response"},
    }


def test_mapper_metadata_never_reaches_a_score() -> None:
    """The structural guarantee, re-checked through the driver rather than only
    through a hand-built `EvaluatorInputs`."""
    suite = a_suite(Case(id="one", metadata={"iban": "IT60X0542811101"}))

    def leaky(case: Case) -> Response:
        return Response(output="Rome", cost_usd=0.01, metadata={"balance": 1499.0})

    run = execute(suite, leaky, created_at=CREATED)
    for verdict in run.results[0].verdicts:
        assert "iban" not in verdict.score.metadata
        assert "balance" not in verdict.score.metadata


# --------------------------------------------------------------------------- #
# What the suite refuses to declare
# --------------------------------------------------------------------------- #


def test_duplicate_case_ids_are_refused() -> None:
    """Two cases sharing an id collide in the key `compare()` pairs on, and the
    second would silently replace the first."""
    with pytest.raises(ValueError, match="case id 'twice' twice"):
        a_suite(Case(id="twice"), Case(id="other"), Case(id="twice"))


def test_a_suite_without_assertions_is_refused() -> None:
    with pytest.raises(ValueError, match="declares no assertions"):
        Suite(
            tenant="acme",
            environment="test",
            name="qa",
            assertions=[],
            cases=[Case(id="one")],
        )


def test_a_suite_without_cases_is_refused() -> None:
    with pytest.raises(ValueError, match="declares no cases"):
        Suite(
            tenant="acme",
            environment="test",
            name="qa",
            assertions=[Contains(needle="Rome")],
            cases=[],
        )


def test_a_suite_needs_a_tenant_and_an_environment() -> None:
    for field_name in ("tenant", "environment"):
        kwargs: dict[str, object] = {
            "tenant": "acme",
            "environment": "test",
            "name": "qa",
            "assertions": [Contains(needle="Rome")],
            "cases": [Case(id="one")],
        }
        kwargs[field_name] = ""
        with pytest.raises(ValueError, match=f"Suite.{field_name}"):
            Suite(**kwargs)  # type: ignore[arg-type]


def test_the_suite_config_hash_matches_the_core() -> None:
    suite = a_suite()
    assert suite.config_hash() == config_hash(suite.assertions)
    assert suite.config_hash() != config_hash([Regex(pattern="x")])
