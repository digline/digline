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
from typing import Any, cast

from digline.core import (
    Artifact,
    CaseResult,
    CostBudget,
    Disclosure,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Run,
    SystemConfig,
    compare,
    config_hash,
)
from digline.report import facts
from digline.store import Listing, RunRef
from digline.wire import explain_json, run_document, runs_json

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

MARKERS = (
    REASON,
    SUSPENSION,
    CASE_SECRET,
    ARTIFACT_TEXT,
    WITHHELD_HOST,
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
            CaseResult("case-1", (rubric(probe), budget(probe))),
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
