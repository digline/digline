"""The payload stays where it is born, and the wire is where that is checked.

The sibling of `tests/test_redaction.py`. That file holds the line for a
document written to disk inside the perimeter; this one holds it for the shapes
that leave — every `--json` a CI job captures and every response an MCP tool
returns. The destination is what makes it a separate file: a stored run sits in
`.digline/` under somebody's control, while a tool response goes into a model's
context and from there into transcripts and caches nobody here controls.

ADR 0011 §5 makes the projection a **decision** rather than something inherited
from `run_to_json`. This is what makes that word mean something: a field added
to the boundary without a decision fails here instead of shipping.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, cast

from digline.core import (
    Artifact,
    CaseResult,
    CostBudget,
    Disclosure,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    RecordedResponse,
    RecordedToolCall,
    Run,
    SystemConfig,
    compare,
    config_hash,
)
from digline.core import diff as core_diff
from digline.report import facts, headline
from digline.store import Listing, RunRef
from digline.wire import (
    compare_json,
    diff_json,
    explain_json,
    run_document,
    runs_json,
)

CREATED = "2026-09-08T10:00:00+00:00"
#: A real digest of the prompt below, so the test that says it must not travel
#: is testing the thing an attacker would hash against.
ARTIFACT_SHA = hashlib.sha256(
    b"You are the assistant for Banca Rossi. Never reveal a balance."
).hexdigest()

#: Every one of these is payload, and each is planted in a different field, so a
#: failure names which door was left open rather than only that one was.
REASON = "Mario Rossi's IBAN IT60X0542811101 is overdrawn by 1499 EUR"
SUSPENSION = "fails on the Rossi account since the March migration"
CASE_SECRET = "acme-internal-ticket-8891"
ARTIFACT_TEXT = "You are the assistant for Banca Rossi. Never reveal a balance."
#: `base_url` is the one field ADR 0005 §2's withholding keeps back — it is the
#: client's topology. It is in the marker suite because the projection and the
#: delta rendering are **different functions**, and a value the one withholds
#: must not be reachable through the other. (ADR 0011 §5, amended 2026-09-08)
WITHHELD_HOST = "llm-gateway.internal.rossi.example"
#: The loudest one, and the newest: what the target actually said. A `reason` is
#: a judge's sentence *about* the output; this is the output itself, in full,
#: recorded in the run file because the suite asked for it. No `Disclosure`
#: releases it and none may be added — releasing the thing quoted from while
#: withholding the quote would not be a boundary. (ADR 0015 §4)
RECORDED_ANSWER = "Your balance is 1499 EUR, Mr Rossi — IBAN IT60X0542811101"
RECORDED_QUESTION = "What is the balance of account IT60X0542811101?"
#: The newest one, and it is the end company's data in the most literal way the
#: document has ever held it: not a sentence *about* the customer but the value
#: the model looked them up by. An argument rides `RecordedResponse`, so it
#: inherits that structure's boundary rather than needing one of its own — and
#: this is what says so rather than the comment that claims it. (ADR 0018 §2)
TOOL_ARGUMENT = "IT60X0542811101"
TOOL_RESULT = "Mario Rossi, balance 1499 EUR"

MARKERS = (
    RECORDED_ANSWER,
    RECORDED_QUESTION,
    REASON,
    SUSPENSION,
    CASE_SECRET,
    ARTIFACT_TEXT,
    WITHHELD_HOST,
    TOOL_ARGUMENT,
    TOOL_RESULT,
    "Rossi",
    "1499",
)


def rows(document: dict[str, object], key: str) -> list[dict[str, Any]]:
    """Narrow one list-valued key. The projection is `dict[str, object]` by
    design — it is a JSON document, not a model — so a strict reader has to say
    what it expects, and saying it once here keeps it out of every assertion."""
    value = document[key]
    assert isinstance(value, list), f"{key} is not a list: {value!r}"
    return cast(list[dict[str, Any]], value)


def loaded_run() -> Run:
    """A run with payload in every field that has ever carried it."""

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=0.2, reason=REASON)

    rubric = LlmRubric(
        rubric="Does it leak account data?", judge=judge, threshold=0.7, tolerance=0.05
    )
    budget = CostBudget(max_usd=0.10, tolerance=0.02)
    probe = EvaluatorInputs(output="…", cost_usd=0.01)
    return Run(
        tenant="acme",
        environment="staging",
        suite="privacy",
        config_hash=config_hash([rubric, budget]),
        created_at=CREATED,
        results=(
            CaseResult(
                "case-1",
                (rubric(probe), budget(probe)),
                responses=(
                    RecordedResponse(
                        output=RECORDED_ANSWER,
                        kind="text",
                        input=RECORDED_QUESTION,
                        cost_usd=0.01,
                        latency_ms=120.0,
                        tool_calls=(
                            RecordedToolCall(
                                tool="lookup_account",
                                arguments=f'{{"iban":"{TOOL_ARGUMENT}"}}',
                                result=TOOL_RESULT,
                            ),
                        ),
                    ),
                ),
            ),
            CaseResult("case-2", (), suspended=SUSPENSION),
        ),
        metadata={"model": "claude-opus-5", "customer_balance": 1499.0},
        artifacts={"prompt.md": Artifact(sha=ARTIFACT_SHA, text=ARTIFACT_TEXT)},
        target_config=SystemConfig(
            values={
                "provider": "anthropic",
                "model": "claude-opus-5",
                "temperature": 0.3,
                "base_url": WITHHELD_HOST,
            }
        ),
        judge_config=SystemConfig(
            values={"provider": "anthropic", "model": "claude-haiku-4-5"},
            identities=("anthropic/claude-haiku-4-5",),
        ),
    )


def test_no_marker_survives_the_projection() -> None:
    """The gate, stated as the end company would state it: none of our data.

    Serialized whole and searched, rather than checked key by key, because the
    failure this guards against is a field nobody thought to check.
    """
    document = json.dumps(run_document(loaded_run(), Disclosure()))
    for marker in MARKERS:
        assert marker not in document, f"{marker!r} crossed the boundary"


def test_the_recorded_answer_has_no_key_to_travel_through() -> None:
    """A property of the projection rather than of a filter: `run_document` does
    not know the field's name, so no caller can ask for it and no `Disclosure`
    can widen its way to it. The marker suite above already proves the text does
    not appear; this says *why* it cannot."""
    document = run_document(loaded_run(), Disclosure(artifacts=True))
    assert "responses" not in json.dumps(document)
    for case in rows(document, "results"):
        assert "responses" not in case
        assert "output" not in case


def test_the_recorded_trajectory_has_no_key_to_travel_through() -> None:
    """The same property as the recorded answer, one field deeper.

    The trajectory rides *inside* `RecordedResponse`, so the projection that
    does not know `responses` cannot know `tool_calls` either — there is no
    second door to close and no `Disclosure` that could widen its way to one.
    The marker suite proves the argument does not appear; this says why it
    cannot. (ADR 0018 §2)
    """
    document = run_document(loaded_run(), Disclosure(artifacts=True))
    serialized = json.dumps(document)
    assert "tool_calls" not in serialized
    assert "lookup_account" not in serialized
    for case in rows(document, "results"):
        assert "tool_calls" not in case


def test_no_perimeter_field_crosses_through_a_comparison() -> None:
    """The door 0.8.1 did not close, and the gap this suite did not cover.

    0.8.1 withheld `resolved_model` on the *projection* when the run went to a
    named endpoint. `config_deltas` read `.values` raw, so the same field walked
    out of the **delta** instead — and the delta is what `compare --json full`
    ships to CI and what the MCP server returns to a model. One server answered
    two ways about one run: `get_run` withheld it, `compare` handed it over.

    Driven through `compare_json` *and* `diff_json`, in both `--json` modes,
    because that is exactly the surface the boundary suite never drove.
    (0.12.1, from the release delta-pass)
    """
    run = loaded_run()
    other = replace(run, created_at="2026-09-09T10:00:00+00:00")
    head = headline(compare(run, other), run, other, locale="en")
    difference = core_diff(run, other)

    documents = [
        json.dumps(compare_json(compare(run, other), head, full=True)),
        json.dumps(compare_json(compare(run, other), head, full=False)),
        json.dumps(
            diff_json(
                difference,
                run,
                other,
                keys=("a", "b"),
                labels=("a", "b"),
                sentence="",
                full=True,
            )
        ),
    ]
    for document in documents:
        assert WITHHELD_HOST not in document, "the perimeter host crossed a delta"
        for marker in MARKERS:
            assert marker not in document, f"{marker!r} crossed a delta"


def test_a_withheld_field_says_unknown_rather_than_same() -> None:
    """The value goes and the *question* is answered honestly: a field nobody
    can see did not "stay the same", it is not knowable from here — which is the
    rule `config_deltas` already applied to a field redaction had taken, now
    applied to one it is about to take."""
    run = loaded_run()
    deltas = compare(run, run).target_config_deltas
    # `base_url` alone, because that is the perimeter field this fixture plants.
    # Naming `fingerprint` here too would read as two fields covered and check
    # one, which is the shape of a test that passes over nothing.
    perimeter = [d for d in deltas if d.field == "base_url"]
    assert len(perimeter) == 1, [d.field for d in deltas]
    withheld = perimeter[0]
    assert withheld.outcome == "unknown"
    assert withheld.withheld is True
    assert withheld.before is None and withheld.after is None
    # And a measurement still travels, or the fix would have closed the door by
    # bricking it up: a model id is what the reader came for.
    named = {d.field: d for d in deltas}
    assert named["model"].outcome == "same"
    assert named["model"].after == "claude-opus-5"


def test_the_reason_is_absent_not_emptied() -> None:
    """Omitted, so not even the length of the original survives, and no caller
    can put it back by filling in a key that is already there."""
    document = json.dumps(run_document(loaded_run(), Disclosure()))
    assert '"reason"' not in document


def test_a_suspension_travels_as_a_fact_and_not_as_a_sentence() -> None:
    """That a case was set aside is coverage and belongs here; why it was is
    payload and does not."""
    document = run_document(loaded_run(), Disclosure())
    results = rows(document, "results")
    assert results[0]["suspended"] is False
    assert results[1]["suspended"] is True
    assert SUSPENSION not in json.dumps(document)


def test_the_verdict_itself_travels_intact() -> None:
    """The positive half. A gate that only proved things were absent would be
    satisfied by a projection that emitted nothing at all."""
    document = run_document(loaded_run(), Disclosure())
    verdict = rows(document, "results")[0]["verdicts"][0]
    assert verdict["name"] == "llm_rubric"
    assert verdict["score"] == 0.2
    assert verdict["threshold"] == 0.7
    assert verdict["tolerance"] == 0.05
    assert verdict["status"] == "fail"
    assert verdict["assertion_id"]


def instrumented() -> Run:
    """A run carrying every instrument flag at once.

    Built beside `loaded_run()` rather than inside it: that fixture is the
    payload gate and must stay a run with data in every field that has ever
    carried some. This one is the opposite question — our own facts, none of
    them the customer's.
    """
    import dataclasses

    from digline.core import CalibrationBand, Score

    run = loaded_run()
    judged = dataclasses.replace(
        run.results[0].verdicts[0],
        judged=True,
        score=Score(
            name=run.results[0].verdicts[0].score.name,
            score=0.5,
            samples=(0.5, 0.5),
            sample_min=0.5,
            sample_max=0.5,
            sample_means=True,
        ),
    )
    return dataclasses.replace(
        run,
        rejudged_from="2026-01-01T00-00-00-00-00-abcdef0123456789",
        judge_samples=5,
        results=(
            dataclasses.replace(run.results[0], verdicts=(judged,), canary=True),
            dataclasses.replace(
                run.results[1],
                calibration=CalibrationBand(check="llm_rubric", low=0.4, high=0.8),
            ),
        ),
    )


def test_the_instrument_flags_cross() -> None:
    """ADR 0011 §5, amended 2026-09-19. Five facts a caller reading **one run**
    could not get anywhere else."""
    document = run_document(instrumented(), Disclosure())
    cases = rows(document, "results")

    assert document["rejudged_from"] == "2026-01-01T00-00-00-00-00-abcdef0123456789"
    assert cases[0]["canary"] is True
    assert cases[1]["calibration"] == {"check": "llm_rubric", "low": 0.4, "high": 0.8}
    assert cases[0]["verdicts"][0]["judged"] is True
    assert cases[0]["verdicts"][0]["sample_means"] is True


def test_what_the_samples_are_travels_with_the_samples() -> None:
    """The pair is the claim. `samples` alone cannot say whether it holds two
    judgements or two means of judgements — the misreading schema 13 was spent
    to stop, and this surface was shipping it."""
    verdict = rows(run_document(instrumented(), Disclosure()), "results")[0][
        "verdicts"
    ][0]
    assert verdict["samples"] == [0.5, 0.5]
    assert verdict["sample_means"] is True


def test_judge_samples_is_absent_and_that_is_a_ruling() -> None:
    """Ruled out, not pending. The numbers it qualifies — `judge_min`,
    `judge_max`, `judge_errored`, `judge_answer` — live in `Score.metadata`,
    which this projection filters to the suite's `Disclosure` with no
    `travels()` fallback, so a bare count would arrive with nothing to count
    against.

    Asserted so a later reader meets the ruling rather than the gap, and so that
    closing it is a decision somebody makes rather than a key somebody adds.
    """
    run = instrumented()
    assert run.judge_samples == 5, (
        "the fixture must carry it for this to prove anything"
    )
    assert "judge_samples" not in json.dumps(run_document(run, Disclosure()))


def test_a_run_with_no_instrument_flags_says_so_plainly() -> None:
    """The ordinary document: the keys are there and each says *no*, so a
    consumer reads one shape whatever the run was."""
    document = run_document(loaded_run(), Disclosure())
    cases = rows(document, "results")

    assert document["rejudged_from"] == ""
    assert cases[0]["canary"] is False
    assert cases[0]["calibration"] is None
    assert cases[0]["verdicts"][0]["judged"] is False
    assert cases[0]["verdicts"][0]["sample_means"] is False


def test_the_added_keys_did_not_move_the_output_version() -> None:
    """The rule and its application, read in one place: an added key breaks no
    consumer, and that is the rule this change is under — unlike the bump to 2,
    which rewrote bytes inside values a consumer already read."""
    from digline.wire import OUTPUT_VERSION

    assert OUTPUT_VERSION == 2
    assert run_document(instrumented(), Disclosure())["output_version"] == 2


def test_the_instrument_flags_carry_none_of_the_customers_data() -> None:
    """The boundary half. The flags are booleans, a band of our own numbers and
    a key digline composed; the payload gate below them is unchanged."""
    document = json.dumps(run_document(instrumented(), Disclosure()))
    for marker in MARKERS:
        assert marker not in document, f"{marker!r} crossed with the new keys"


def test_score_metadata_travels_only_by_disclosure() -> None:
    """A measurement an assertion wrote is still the customer's data until the
    suite says otherwise."""
    run = loaded_run()
    # `cost_usd` is what CostBudget measured — the second verdict on case-1.
    closed = run_document(run, Disclosure())
    opened = run_document(run, Disclosure(score_metadata=frozenset({"cost_usd"})))
    assert rows(closed, "results")[0]["verdicts"][1]["metadata"] == {}
    assert rows(opened, "results")[0]["verdicts"][1]["metadata"] == {"cost_usd": 0.01}
    # And only what was named: the budget measured three things, one was asked
    # for, and a disclosure is a list rather than a switch.
    assert "max_usd" not in json.dumps(opened)


def test_run_metadata_travels_only_by_disclosure() -> None:
    """Numbers included: an amount copied out of a customer's request is their
    data wearing the same clothes as a measurement."""
    run = loaded_run()
    assert run_document(run, Disclosure())["metadata"] == {}
    disclosed = run_document(run, Disclosure(run_metadata=frozenset({"model"})))
    assert disclosed["metadata"] == {"model": "claude-opus-5"}
    assert "customer_balance" not in json.dumps(disclosed)


def test_the_document_says_what_it_was_allowed_to_carry() -> None:
    """So a reader learns the policy from a field rather than inferring it from
    what happens to be missing — ADR 0003 §4's rule, applied to the whole."""
    document = run_document(loaded_run(), Disclosure(run_metadata=frozenset({"model"})))
    assert document["disclosure"] == {
        "run_metadata": ["model"],
        "score_metadata": [],
        "artifacts": False,
    }


def test_the_listing_never_drops_history_in_silence() -> None:
    """A listing that quietly skipped half a suite would read exactly like a
    suite with a shorter history. Over MCP there is no stderr to say so, which
    is why the note is a field. (ADR 0011 §4)"""
    listing = Listing(
        runs=(RunRef("acme", "privacy", "k"),),
        skipped={5: 3},
        unreadable=("/Users/somebody/.digline/acme/runs/broken.json",),
    )
    document = runs_json(
        [("k", loaded_run())],
        tenant="acme",
        suite="privacy",
        baseline_key=None,
        listing=listing,
    )
    assert document["skipped"] == {"5": 3}
    assert "3 run(s) at schema 5" in str(document["note"])
    # A count, never the paths: a path under `.digline/` is this machine's fact.
    assert document["unreadable"] == 1
    assert "somebody" not in json.dumps(document)


def test_the_listing_is_newest_first_on_the_recorded_fact() -> None:
    import dataclasses

    older = dataclasses.replace(loaded_run(), created_at="2026-09-01T10:00:00+00:00")
    document = runs_json(
        [("older", older), ("newer", loaded_run())],
        tenant="acme",
        suite="privacy",
        baseline_key="older",
        listing=Listing(runs=()),
    )
    assert [r["key"] for r in rows(document, "runs")] == ["newer", "older"]
    assert document["baseline_key"] == "older"


def test_neither_the_prompt_nor_its_digest_travels_undisclosed() -> None:
    """A prompt is the software house's file and the end company's rules at the
    same time, so it leaves only where the suite said it may (ADR 0003).

    The path stays, and `withheld` says which absence it is: "this suite kept it
    back" and "this run declared no artifacts" are different facts.
    """
    document = run_document(loaded_run(), Disclosure())
    assert document["artifacts"] == {"prompt.md": {"withheld": True}}
    assert ARTIFACT_TEXT not in json.dumps(document)
    # The digest is a verifier: prompts live in a small, guessable space, so a
    # few thousand candidates hashed against a leaked one recover the text in
    # milliseconds. It leaves with the text or not at all. (ADR 0003 §4)
    assert ARTIFACT_SHA not in json.dumps(document)


def test_the_prompt_travels_when_the_suite_declares_it() -> None:
    """The positive half, so the gate is proving a boundary and not proving that
    a field is always empty."""
    document = run_document(loaded_run(), Disclosure(artifacts=True))
    artifacts = cast(dict[str, dict[str, Any]], document["artifacts"])
    assert artifacts["prompt.md"]["text"] == ARTIFACT_TEXT
    assert artifacts["prompt.md"]["sha"] == ARTIFACT_SHA


def test_the_measured_interval_travels_with_the_score() -> None:
    """A reading of the instrument, and the reason it is here.

    A score of 0.667 alone cannot say whether it was measured once or five
    times, so a reader given only the number cannot tell a wobble from a drift —
    which is the judgement `AGENTS.md` §3 asks for. (ADR 0011 §5, amended)
    """
    import dataclasses

    from digline.core import Score

    run = loaded_run()
    verdict = run.results[0].verdicts[0]
    sampled = dataclasses.replace(
        verdict,
        score=Score(
            name=verdict.score.name,
            score=0.667,
            samples=(1.0, 1.0, 0.0),
            sample_min=0.0,
            sample_max=1.0,
        ),
    )
    run = dataclasses.replace(
        run, results=(dataclasses.replace(run.results[0], verdicts=(sampled,)),)
    )
    projected = rows(run_document(run, Disclosure()), "results")[0]["verdicts"][0]
    assert projected["samples"] == [1.0, 1.0, 0.0]
    assert projected["sample_min"] == 0.0
    assert projected["sample_max"] == 1.0


def test_the_configurations_travel_as_measurements() -> None:
    """ADR 0005 ruled a model id and a temperature measurements of the system.
    A document that named neither could not say which model produced the run it
    describes."""
    document = run_document(loaded_run(), Disclosure())
    target = cast(dict[str, Any], document["target_config"])
    assert target["values"]["model"] == "claude-opus-5"
    assert target["values"]["temperature"] == 0.3
    judge = cast(dict[str, Any], document["judge_config"])
    assert judge["identities"] == ["anthropic/claude-haiku-4-5"]


def test_the_perimeter_field_leaves_as_a_name_and_never_as_a_value() -> None:
    """`base_url` is the client's topology and the one field ADR 0005 §2's
    withholding keeps back.

    The name travels so a reader can tell `unknown` from `unchanged`, which is
    the whole reason the flag exists — and the value does not, which is what
    puts it in the marker suite. Absent, never emptied: `SystemConfig` refuses
    to hold a key as both present and withheld, so this is an invariant of the
    type rather than a promise of the projection.
    """
    document = run_document(loaded_run(), Disclosure())
    target = cast(dict[str, Any], document["target_config"])
    assert target["withheld"] == ["base_url"]
    assert "base_url" not in target["values"]
    assert WITHHELD_HOST not in json.dumps(document)


def test_a_disclosure_cannot_release_the_perimeter_field() -> None:
    """No `Disclosure` widens this one. A credential is the category no
    disclosure releases (ADR 0004 §5), and the topology it sits in goes with
    it — so the widest possible policy still does not produce the host."""
    widest = Disclosure(
        run_metadata=frozenset({"model", "customer_balance"}),
        score_metadata=frozenset({"cost_usd", "max_usd", "ratio"}),
        artifacts=True,
    )
    assert WITHHELD_HOST not in json.dumps(run_document(loaded_run(), widest))


# --------------------------------------------------------------------------- #
# The reading's surface (ADR 0012 §4)
#
# The same marker suite, driven through `explain_json`. The difference from
# everything above is what the assertions are proving: there, that a function
# declines to emit; here, that there is nothing to decline. The fact types have
# no field a reason fits in, so the boundary is a property of the type rather
# than of the projection — and this is what makes that claim testable instead
# of merely stated.
# --------------------------------------------------------------------------- #


def test_no_marker_survives_the_reading() -> None:
    run = loaded_run()
    for reading, scope in (
        (facts(run), "run"),
        (facts(run, compare(run, loaded_run())), "comparison"),
    ):
        document = json.dumps(explain_json(reading, scope=scope, exit_code=0))
        for marker in MARKERS:
            assert marker not in document, f"{marker!r} crossed on the {scope} reading"


def test_the_reading_has_no_reason_field_to_fill() -> None:
    """Absent from the *type*, which is stronger than absent from the output: a
    key that is never written can be written by the next edit, and a field that
    does not exist cannot."""
    run = loaded_run()
    reading = facts(run, compare(run, loaded_run()))
    assert reading, "an empty reading would make this prove nothing"
    for fact in reading:
        assert not hasattr(fact, "reason")
    assert '"reason"' not in json.dumps(
        explain_json(reading, scope="comparison", exit_code=0)
    )


def test_a_suspension_reaches_the_reading_as_a_case_and_not_as_a_sentence() -> None:
    """The case id is a fact about coverage and travels; the stated reason is
    payload. A suite whose coverage silently shrank must still be visible."""
    run = loaded_run()
    document = json.dumps(explain_json(facts(run), scope="run", exit_code=0))
    assert "case-2" in document
    assert SUSPENSION not in document


def test_neither_the_prompt_nor_its_digest_reaches_the_reading() -> None:
    """A digest is a verifier: prompts live in a guessable space, so one
    travelling beside a withheld prompt would defeat the withholding it
    travelled beside. The reading carries the path and the outcome, and there
    is no field for either the text or the hash."""
    run = loaded_run()
    document = json.dumps(explain_json(facts(run), scope="run", exit_code=0))
    assert "prompt.md" in document
    assert ARTIFACT_TEXT not in document
    assert ARTIFACT_SHA not in document
    assert "sha" not in document


def test_the_withheld_perimeter_field_never_reaches_the_reading() -> None:
    """`base_url` is the client's topology and `SystemConfig.redacted()` keeps
    it back. The reading reads `config_deltas`, which already applied that
    rule — so a value one surface withholds is not reachable through another.
    """
    run = loaded_run()
    reading = facts(run, compare(run, loaded_run()))
    assert WITHHELD_HOST not in json.dumps(
        explain_json(reading, scope="comparison", exit_code=0)
    )
