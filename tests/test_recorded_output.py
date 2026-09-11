"""The target's answers: recorded where the suite asks, and nowhere else.

The two halves of ADR 0015 are tested in the two places they live. What the
document may hold is here; what may **leave** is in `tests/test_wire_boundary.py`
and `tests/test_redaction.py`, where every other boundary is held — this file
would be the wrong place to prove a negative about a surface it does not import.

The replay half is here too, because a re-judge is a *measurement* question
before it is a boundary one: the whole of §6 is refusing to produce a weaker
measurement wearing the declared suite's name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli, run_key

from digline.core import (
    MAX_RECORDED_CHARS,
    CaseResult,
    Contains,
    Message,
    RecordedResponse,
    Run,
    record_output,
    redact,
    restore_output,
    run_to_json,
    without_responses,
)
from digline.report import headline, render_html
from digline.run import (
    Case,
    Replay,
    ReplayError,
    Response,
    Suite,
    Target,
    execute,
    planned_calls,
    rejudge,
)
from digline.store import FileResultStore, ReplayedRunError

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"


def answering(text: str = "The capital is Rome.") -> Target:
    def target(case: Case) -> Response:
        return Response(
            output=text, input=f"capital of {case.id}?", cost_usd=0.01, latency_ms=12.0
        )

    return target


def suite(**extra: object) -> Suite:
    declared: dict[str, object] = {
        "tenant": "acme",
        "environment": "staging",
        "name": "qa",
        "assertions": [Contains(needle="Rome")],
        "cases": [Case(id="one"), Case(id="two")],
    }
    declared.update(extra)
    return Suite(**declared)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Opt-in, and what the default costs: nothing
# --------------------------------------------------------------------------- #


def test_nothing_is_recorded_unless_the_suite_asks() -> None:
    run = execute(suite(), answering(), created_at=CREATED)
    assert all(case.responses == () for case in run.results)
    assert "responses" not in run_to_json(run)


def test_the_default_produces_the_document_it_produced_before() -> None:
    """The promise every opt-in feature in this codebase has had to make: a
    suite that does not ask sees the same bytes, key for key."""
    plain = json.loads(run_to_json(execute(suite(), answering(), created_at=CREATED)))
    recording = json.loads(
        run_to_json(
            execute(suite(record_responses=True), answering(), created_at=CREATED)
        )
    )
    for case in recording["results"]:
        del case["responses"]
    assert plain == recording


def test_one_entry_per_sample_in_the_order_produced() -> None:
    answers = iter(["Rome first", "Rome second", "Rome third"])

    def target(case: Case) -> Response:
        return Response(output=next(answers), input="capital?")

    run = execute(
        suite(
            record_responses=True, samples=3, min_agreement="2/3", cases=[Case("one")]
        ),
        target,
        created_at=CREATED,
    )
    recorded = [r.output for r in run.results[0].responses]
    assert recorded == ["Rome first", "Rome second", "Rome third"]


def test_the_question_is_recorded_beside_the_answer() -> None:
    """Not an extra: the prompt is rendered inside the target, so a stored
    answer with no stored question cannot be re-judged by any assertion that
    reads the input — which is most of the ones that call a model."""
    run = execute(suite(record_responses=True), answering(), created_at=CREATED)
    first = run.results[0].responses[0]
    assert first.input == "capital of one?"
    assert first.cost_usd == 0.01
    assert first.latency_ms == 12.0


def test_a_suspended_case_records_nothing_and_may_not_claim_to() -> None:
    run = execute(
        suite(
            record_responses=True,
            cases=[Case("one"), Case("two", suspended="the API is down")],
        ),
        answering(),
        created_at=CREATED,
    )
    assert run.results[1].responses == ()
    with pytest.raises(ValueError, match="never called"):
        CaseResult(
            "two",
            suspended="the API is down",
            responses=(RecordedResponse(output="x", kind="text"),),
        )


def test_recording_does_not_move_the_config_hash() -> None:
    """A recording decision changes no score, pairs no verdict differently and
    moves no bar — and `disclosure` has never been in the fingerprint either.
    A baseline promoted before the flag was set is still the reference after."""
    assert suite().config_hash() == suite(record_responses=True).config_hash()


# --------------------------------------------------------------------------- #
# Whole or nothing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", ["output", "input"])
def test_over_the_ceiling_records_neither_field(field: str) -> None:
    big = "x" * (MAX_RECORDED_CHARS + 1)

    def target(case: Case) -> Response:
        return Response(
            output=big if field == "output" else "Rome",
            input=big if field == "input" else "capital?",
            cost_usd=0.02,
        )

    run = execute(
        suite(record_responses=True, cases=[Case("one")]), target, created_at=CREATED
    )
    only = run.results[0].responses[0]
    assert only.oversize
    assert only.output is None and only.input is None
    # The measurements stay: they are not what the ceiling is about.
    assert only.cost_usd == 0.02


def test_exactly_at_the_ceiling_is_recorded() -> None:
    text = "x" * MAX_RECORDED_CHARS

    def target(case: Case) -> Response:
        return Response(output=text, input="capital?")

    run = execute(
        suite(record_responses=True, cases=[Case("one")]), target, created_at=CREATED
    )
    assert run.results[0].responses[0].output == text


def test_the_two_absences_are_different_facts() -> None:
    with pytest.raises(ValueError, match="both withheld and oversize"):
        RecordedResponse(withheld=True, oversize=True)
    with pytest.raises(ValueError, match="carries text"):
        RecordedResponse(oversize=True, output="half of it")
    with pytest.raises(ValueError, match="carries no output"):
        RecordedResponse(kind="text")


# --------------------------------------------------------------------------- #
# Every branch of Output survives the round trip
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "output",
    [
        "plain text",
        {"score": 3, "why": "because"},
        [Message(role="user", content="hi"), Message(role="assistant", content="ho")],
    ],
)
def test_an_answer_comes_back_as_what_it_was(output: object) -> None:
    text, kind = record_output(output)  # type: ignore[arg-type]
    restored = restore_output(text, kind)
    if kind == "conversation":
        assert list(restored) == list(output)  # type: ignore[arg-type]
    else:
        assert restored == output


def test_the_kind_is_recorded_because_the_text_cannot_say() -> None:
    """`"[]"` is a structured answer, a conversation with no turns, or a model
    that replied with two brackets."""
    assert record_output([])[1] == "conversation"
    assert record_output("[]")[1] == "text"


# --------------------------------------------------------------------------- #
# It never travels, and it never reaches a committed file
# --------------------------------------------------------------------------- #


def test_redaction_keeps_the_count_and_nothing_else() -> None:
    run = execute(
        suite(record_responses=True), answering("Mario Rossi"), created_at=CREATED
    )
    hidden = redact(run)
    assert [len(c.responses) for c in hidden.results] == [1, 1]
    assert all(r.withheld for c in hidden.results for r in c.responses)
    assert "Mario Rossi" not in run_to_json(hidden)


def test_a_document_cannot_claim_a_perimeter_it_does_not_keep() -> None:
    """Verified rather than believed, like every other claim in the document."""
    with pytest.raises(ValueError, match="recorded answer from the target"):
        Run(
            tenant="acme",
            environment="staging",
            suite="qa",
            config_hash="h",
            created_at=CREATED,
            results=(
                CaseResult(
                    "one", responses=(RecordedResponse(output="Rome", kind="text"),)
                ),
            ),
            redacted=True,
        )


def test_promotion_writes_a_reference_without_the_answers(tmp_path: Path) -> None:
    """`baselines/` is committed. Promoting a recorded run would put the model's
    answers into git as a side effect of the most routine action there is."""
    store = FileResultStore(tmp_path)
    declared = suite(record_responses=True)
    run = execute(declared, answering("Mario Rossi lives in Rome"), created_at=CREATED)
    ref = store.write_run(run)

    promoted = store.promote_baseline(
        ref, declared.config_hash(), promoted_at="2026-01-02T09:00:00+00:00"
    )
    assert all(case.responses == () for case in promoted.results)
    text = store.baseline_path("acme", "qa").read_text(encoding="utf-8")
    assert "Mario Rossi" not in text
    # And the run itself still has them: the strip is promotion's, not the
    # store's in general.
    assert "Mario Rossi" in store.run_path(ref).read_text(encoding="utf-8")


def test_without_responses_leaves_an_unrecorded_run_alone() -> None:
    run = execute(suite(), answering(), created_at=CREATED)
    assert without_responses(run) is run


# --------------------------------------------------------------------------- #
# The replay, and the four refusals
# --------------------------------------------------------------------------- #


def recorded_run() -> tuple[Suite, Run]:
    declared = suite(record_responses=True)
    return declared, execute(declared, answering(), created_at=CREATED)


def test_a_replay_scores_exactly_what_the_run_scored() -> None:
    """The test that makes the replay faithful rather than approximately so."""
    declared, source = recorded_run()
    again = rejudge(declared, source, key="src-key", created_at=LATER)
    assert [v.score.score for c in again.results for v in c.verdicts] == [
        v.score.score for c in source.results for v in c.verdicts
    ]
    assert again.rejudged_from == "src-key"


def test_a_moved_bar_flips_the_verdict_without_asking_the_target() -> None:
    """And this is the feature: same answers, different rules, no spend."""
    _, source = recorded_run()
    stricter = suite(
        record_responses=True,
        assertions=[Contains(needle="Paris")],
    )
    again = rejudge(stricter, source, key="src-key", created_at=LATER)
    assert all(v.status == "fail" for c in again.results for v in c.verdicts)


def test_the_replay_carries_what_produced_the_answers() -> None:
    declared, source = recorded_run()
    source = Run(
        tenant=source.tenant,
        environment=source.environment,
        suite=source.suite,
        config_hash=source.config_hash,
        created_at=source.created_at,
        results=source.results,
        artifacts={
            "prompt.md": __import__("digline").core.Artifact(sha="abc", text="p")
        },
    )
    again = rejudge(declared, source, key="src-key", created_at=LATER)
    assert again.artifacts["prompt.md"].sha == "abc"
    assert again.created_at == LATER


def test_a_replay_records_its_own_answers_again() -> None:
    """So the run it produces is itself a run, re-judgeable like any other."""
    declared, source = recorded_run()
    again = rejudge(declared, source, key="src-key", created_at=LATER)
    assert again.results[0].responses[0].output == "The capital is Rome."


def test_it_refuses_a_run_that_recorded_nothing() -> None:
    source = execute(suite(), answering(), created_at=CREATED)
    with pytest.raises(ReplayError, match="record_responses"):
        Replay(suite(record_responses=True), source)


def test_it_refuses_a_case_that_was_not_in_the_stored_run() -> None:
    _, source = recorded_run()
    grown = suite(
        record_responses=True, cases=[Case("one"), Case("two"), Case("three")]
    )
    with pytest.raises(ReplayError, match="'three' has no recorded answer"):
        Replay(grown, source)


def test_it_refuses_a_different_sample_count() -> None:
    _, source = recorded_run()
    sampled = suite(record_responses=True, samples=3, min_agreement="2/3")
    with pytest.raises(ReplayError, match="recorded 1 answer"):
        Replay(sampled, source)


def test_it_refuses_a_withheld_answer() -> None:
    declared, source = recorded_run()
    with pytest.raises(ReplayError, match="withheld at a boundary"):
        Replay(declared, redact(source))


def test_it_refuses_an_oversize_answer() -> None:
    declared, source = recorded_run()
    holed = Run(
        tenant=source.tenant,
        environment=source.environment,
        suite=source.suite,
        config_hash=source.config_hash,
        created_at=source.created_at,
        results=tuple(
            CaseResult(
                case.case_id,
                case.verdicts,
                responses=(RecordedResponse(oversize=True),),
            )
            for case in source.results
        ),
    )
    with pytest.raises(ReplayError, match="over the size ceiling"):
        Replay(declared, holed)


def test_it_refuses_to_cross_a_perimeter() -> None:
    _, source = recorded_run()
    other = suite(record_responses=True, tenant="other-customer")
    with pytest.raises(ReplayError, match="perimeter"):
        Replay(other, source)


def test_a_replay_may_not_become_the_baseline(tmp_path: Path) -> None:
    """The fourth condition on promotion: the answers must have been measured.

    A replay has zero target variance, so its interval is the judge's wobble
    alone — promoted, every ordinary movement of the target would then read as
    beyond the noise.
    """
    store = FileResultStore(tmp_path)
    declared, source = recorded_run()
    again = rejudge(declared, source, key="src-key", created_at=LATER)
    ref = store.write_run(again)
    with pytest.raises(ReplayedRunError, match="not from the target"):
        store.promote_baseline(
            ref, declared.config_hash(), promoted_at="2026-01-02T09:00:00+00:00"
        )


def test_the_announced_cost_says_the_target_is_not_called() -> None:
    plan = planned_calls(suite(record_responses=True))
    assert "no call to the target" in plan.sentence(replayed=True)
    assert "to the target" in plan.sentence()
    assert "no call" not in plan.sentence()


# --------------------------------------------------------------------------- #
# The whole cycle, through the CLI
# --------------------------------------------------------------------------- #


def test_rejudge_writes_a_run_that_declares_its_source(repo: Path) -> None:
    source = repo / "suite_qa.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            'disclosure=Disclosure(run_metadata=frozenset({"model"})),',
            'disclosure=Disclosure(run_metadata=frozenset({"model"})),\n'
            "    record_responses=True,",
        ),
        encoding="utf-8",
    )
    key = run_key(repo)

    done = cli(repo, "rejudge", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == 0, done.stderr
    assert "no call to the target" in done.stderr
    replayed = done.stdout.strip()

    stored = json.loads(
        (
            repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{replayed}.json"
        ).read_text(encoding="utf-8")
    )
    assert stored["rejudged_from"] == key
    assert stored["results"][0]["responses"][0]["output"] == "The capital is Rome."

    refused = cli(repo, "promote", "--suite", "suite_qa.py", "--run", replayed)
    assert refused.returncode != 0
    assert "ReplayedRunError" in refused.stderr


def test_rejudge_refuses_a_run_with_no_answers_in_it(repo: Path) -> None:
    key = run_key(repo)
    done = cli(repo, "rejudge", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != 0
    assert "record_responses" in done.stderr


def test_the_report_says_the_answers_were_replayed(repo: Path) -> None:
    declared, source = recorded_run()
    again = rejudge(declared, source, key="src-key", created_at=LATER)

    head = headline(
        __import__("digline").core.compare(again, source), again, source, locale="en"
    )
    assert head.rejudged
    assert "replayed from a stored run" in head.sentence
    document = render_html(
        __import__("digline").core.compare(again, source), again, source, locale="en"
    )
    assert "src-key" in document
