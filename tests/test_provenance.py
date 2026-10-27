"""Schema 22: the provenance a projection reads. (ADR 0034 §17; #323, #711)

A projection receives a document and not a suite, so whether a configuration
key is digline's word, and whether a verdict's metadata was written by digline,
has to be in the document. Two fields carry it, and neither adds text:

- `SystemConfig.named`: the keys of digline's closed vocabulary, which cross a
  projection in clear while every other key and every string value is a token;
- `Verdict.origin`: `builtin` or `foreign`, about who wrote the metadata. A
  foreign verdict's keys become tokens and its values are withheld, except the
  keys the driver writes, which cross in clear on every verdict.

`None` on either is *not recorded*, and a projection never reads it as
digline's.

**The controls that hold the driver's keys run on foreign verdicts.** A builtin
assertion cannot misname its own verdict, so a control on one would pass with
the classification broken: a control must be able to fail in the case it
proves (ADR 0034 §17.6).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

import pytest

from digline.core import (
    DRIVER_METADATA_KEYS,
    NAMED_CONFIG_KEYS,
    SCHEMA_VERSION,
    TEXT_ONLY,
    AssertionBase,
    CaseResult,
    Contains,
    EvaluatorInputs,
    FromAutoevals,
    JudgeReply,
    LlmRubric,
    OutputKind,
    Repeated,
    Run,
    Score,
    SystemConfig,
    Verdict,
    combine_samples,
    compare,
    considered_cases,
    fold_judgements,
    is_token,
    misnamed,
    origin,
    project,
    project_served,
    run_from_json,
    run_to_json,
    unreconciled,
)
from digline.core.naming import DRIVER_MARKERS, MISNAMED
from digline.core.reconcile import UNRECONCILED
from digline.report import shape
from digline.report.pages import _votes  # pyright: ignore[reportPrivateUsage]
from digline.report.shape import CLAIMS_KEY
from digline.run import Case, Response, Suite, execute, target_config
from test_projection import Table, promoted

CREATED = "2026-10-27T10:00:00+00:00"
LATER = "2026-10-27T11:00:00+00:00"
FOREIGN_KEY = "rossi_mario_hits"
WITHHELD = {"withheld": True}


@dataclass(frozen=True, slots=True)
class Foreign(AssertionBase):
    """An assertion a suite wrote: its metadata keys are its own, and one of
    them is built from the data it read."""

    name: str = "foreign_check"
    threshold: float = 0.5
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        verdict = self._binary(True, "fine")
        return replace(
            verdict,
            score=replace(verdict.score, metadata={FOREIGN_KEY: 3}),
        )


def _scorer(**_: Any) -> Any:
    class _Result:
        score = 0.9
        metadata: dict[str, Any] = {"autoevals_detail": 1}

    return _Result()


def rubric() -> LlmRubric:
    return LlmRubric(
        rubric="right?",
        judge=lambda prompt: JudgeReply(score=1.0, reason=prompt[:1]),
        threshold=0.5,
        tolerance=0.05,
    )


def answering(case: Case) -> Response:
    return Response(output="Rome", input="capital?")


def suite(assertions: Sequence[Any]) -> Suite:
    return Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=list(assertions),
        cases=[Case(id="one")],
    )


# --------------------------------------------------------------------------- #
# What is recorded
# --------------------------------------------------------------------------- #


def test_origin_is_who_wrote_the_metadata_not_who_wrote_the_class() -> None:
    assert origin(Contains(needle="Rome")) == "builtin"
    assert origin(rubric()) == "builtin"
    assert origin(Foreign()) == "foreign"
    # The class is digline's, the keys are the third-party scorer's.
    assert (
        origin(FromAutoevals(scorer=_scorer, threshold=0.5, tolerance=0.0)) == "foreign"
    )
    # Followed through `Repeated`, as `judged()` is.
    builtin = Contains(needle="Rome")
    assert origin(Repeated(inner=builtin, samples=2, min_agreement="1/2")) == "builtin"
    assert (
        origin(Repeated(inner=Foreign(), samples=2, min_agreement="1/2")) == "foreign"
    )


def test_the_driver_stamps_the_origin_of_every_verdict() -> None:
    run = execute(
        suite([Contains(needle="Rome"), Foreign()]), answering, created_at=CREATED
    )
    builtin, foreign = run.results[0].verdicts
    assert (builtin.origin, foreign.origin) == ("builtin", "foreign")


def test_the_origin_round_trips_and_absent_is_not_recorded() -> None:
    run = execute(
        suite([Contains(needle="Rome"), Foreign()]), answering, created_at=CREATED
    )
    document = json.loads(run_to_json(run))
    assert document["schema_version"] == SCHEMA_VERSION == 22
    verdicts = document["results"][0]["verdicts"]
    assert [v["origin"] for v in verdicts] == ["builtin", "foreign"]
    assert run_from_json(run_to_json(run)) == run
    for v in verdicts:
        del v["origin"]
    read = run_from_json(json.dumps(document))
    assert [v.origin for v in read.results[0].verdicts] == [None, None]


def test_an_origin_outside_the_two_words_is_refused() -> None:
    run = execute(suite([Contains(needle="Rome")]), answering, created_at=CREATED)
    document = json.loads(run_to_json(run))
    document["results"][0]["verdicts"][0]["origin"] = "acme"
    with pytest.raises(ValueError, match="origin"):
        run_from_json(json.dumps(document))


@dataclass
class Declares:
    """A target written by hand: its `config` names what its author chose."""

    config: dict[str, Any]

    def __call__(self, case: Case) -> Response:
        return Response(output="Rome")


def test_a_configuration_records_the_keys_digline_names() -> None:
    declared = target_config(
        Declares(
            {
                "provider": "acme-gateway",
                "model": "m",
                "temperature": 0.3,
                "fingerprint": "fp",
                "rossi_tenant_flag": 1,
            }
        )
    )
    assert declared.named == frozenset(
        {"provider", "model", "temperature", "fingerprint"}
    )
    assert declared.named <= NAMED_CONFIG_KEYS


def test_named_round_trips_and_absent_is_not_recorded() -> None:
    run = execute(
        suite([Contains(needle="Rome")]),
        Declares({"provider": "p", "model": "m", "rossi_tenant_flag": 1}),
        created_at=CREATED,
    )
    assert run.target_config.named == frozenset({"provider", "model"})
    document = json.loads(run_to_json(run))
    assert document["target_config"]["named"] == ["model", "provider"]
    assert run_from_json(run_to_json(run)) == run
    del document["target_config"]["named"]
    assert run_from_json(json.dumps(document)).target_config.named is None


# --------------------------------------------------------------------------- #
# What a projection does with it: configuration (#323)
# --------------------------------------------------------------------------- #

TARGET = {
    "provider": "acme-gateway",
    "model": "acme-private-model",
    "temperature": 0.3,
    "base_url": "https://llm.acme-bank.internal/v1",
    "resolved_model": "acme-legal-assistant-prod",
    "rossi_tenant_flag": 1,
}


def _configured(named: frozenset[str] | None) -> Run:
    return promoted(target_config=SystemConfig(values=TARGET, named=named))


def test_a_key_digline_names_crosses_in_clear_and_its_value_does_not() -> None:
    named = frozenset(TARGET) & NAMED_CONFIG_KEYS
    table = Table()
    projected = project(_configured(named), table).target_config
    # The perimeter keys are withheld, and named in clear: #323's finding.
    assert projected.withheld == frozenset({"base_url", "resolved_model"})
    clear = {k for k in projected.values if not is_token(k)}
    assert clear == {"provider", "model", "temperature"}
    assert projected.values["temperature"] == 0.3
    assert is_token(str(projected.values["provider"]))
    assert is_token(str(projected.values["model"]))
    # A key the target's author chose is a token.
    assert ("target_config_key", "rossi_tenant_flag") in table.rows


def test_a_configuration_that_records_nothing_is_all_tokens() -> None:
    projected = project(_configured(None), Table()).target_config
    assert all(is_token(k) for k in projected.values)
    assert all(is_token(k) for k in projected.withheld)


def test_a_recorded_key_outside_the_vocabulary_is_a_token() -> None:
    """The recorded set never lets out a key that is not digline's word in the
    projecting digline: a forged or stale `named` fails closed."""
    projected = project(
        _configured(frozenset({"provider", "rossi_tenant_flag"})), Table()
    ).target_config
    assert not any(k == "rossi_tenant_flag" for k in projected.values)
    assert "provider" in projected.values


# --------------------------------------------------------------------------- #
# What a projection does with it: metadata (#711)
# --------------------------------------------------------------------------- #


def _verdict(
    name: str,
    ident: str,
    metadata: dict[str, Any],
    origin_: Any,
    *,
    status: Any = "pass",
    judged: bool = False,
) -> Verdict:
    return Verdict(
        score=Score(
            name=name, score=None if status == "error" else 0.9, metadata=metadata
        ),
        threshold=0.5,
        status=status,
        reason="r",
        assertion_id=ident,
        judged=judged,
        origin=origin_,
    )


def _with(*verdicts: Verdict, created_at: str = CREATED) -> Run:
    return promoted(
        created_at=created_at,
        results=(CaseResult("c", verdicts),),
        aggregate=(),
        target_config=SystemConfig(),
        judge_config=SystemConfig(),
    )


def test_a_builtin_verdicts_metadata_crosses_in_clear() -> None:
    v = _verdict("contains", "a" * 16, {"distance": 2, "samples": 3}, "builtin")
    (projected,) = project(_with(v), Table()).results[0].verdicts
    assert projected.score.metadata == {"distance": 2, "samples": 3}


@pytest.mark.parametrize("origin_", ["foreign", None])
def test_a_foreign_verdicts_keys_are_tokens_and_its_values_withheld(
    origin_: Any,
) -> None:
    v = _verdict("foreign_check", "b" * 16, {FOREIGN_KEY: 3, "samples": 3}, origin_)
    table = Table()
    (projected,) = project(_with(v), table).results[0].verdicts
    token = table.token("metadata_key", FOREIGN_KEY)
    assert projected.score.metadata == {token: WITHHELD, "samples": 3}


def test_the_driver_metadata_keys_are_the_ones_the_driver_writes() -> None:
    """Closed in code, and held equal to what the folds write, so the set
    cannot fall behind a key added to a fold."""
    sample = _verdict("x", "c" * 16, {}, None)
    folded = combine_samples(
        [replace(sample, score=replace(sample.score, score=s)) for s in (0.2, 0.9)],
        min_agreement=0.5,
    )
    judged = fold_judgements(
        [[replace(sample, score=replace(sample.score, score=s)) for s in (0.2, 0.9)]],
        min_agreement=0.5,
    )
    written = set(folded.score.metadata) | set(judged.score.metadata)
    assert written | DRIVER_MARKERS == DRIVER_METADATA_KEYS - {"total_cost_usd"}


# --------------------------------------------------------------------------- #
# The controls, on foreign verdicts: each can fail in the case it proves
# --------------------------------------------------------------------------- #


def test_compare_reads_samples_on_two_projected_foreign_verdicts() -> None:
    table = Table()
    now, before = (
        project(
            _with(
                _verdict(
                    "foreign_check", "d" * 16, {"samples": n, FOREIGN_KEY: 1}, "foreign"
                ),
                created_at=at,
            ),
            table,
        )
        for n, at in ((5, LATER), (3, CREATED))
    )
    deltas = compare(now, before).suite_deltas
    assert [(d.field, d.before, d.after) for d in deltas] == [("samples", 3.0, 5.0)]


def test_misnamed_classifies_a_projected_foreign_verdict() -> None:
    v = _verdict("foreign_check", "e" * 16, {MISNAMED: True}, "foreign", status="error")
    projected = project(_with(v), Table())
    assert len(misnamed(projected)) == 1


def test_unreconciled_classifies_a_projected_foreign_verdict() -> None:
    v = _verdict(
        "foreign_check", "f" * 16, {UNRECONCILED: True}, "foreign", status="error"
    )
    projected = project(_with(v), Table())
    assert len(unreconciled(projected)) == 1


def test_a_served_page_shows_the_votes_of_a_foreign_verdict() -> None:
    v = _verdict(
        "foreign_check", "1" * 16, {"scores": [0.2, 0.9], FOREIGN_KEY: 1}, "foreign"
    )
    (served,) = project_served(_with(v), Table()).results[0].verdicts
    assert _votes(served)


# And the builtin half: what digline's own keys feed stays fed.


def test_the_shape_reading_counts_a_projected_builtin_claim() -> None:
    table = Table()
    now, before = (
        project(
            _with(
                _verdict(
                    "faithfulness", "2" * 16, {CLAIMS_KEY: 1}, "builtin", judged=True
                ),
                created_at=at,
            ),
            table,
        )
        for at in (LATER, CREATED)
    )
    (reading,) = shape(compare(now, before))
    assert reading.run.single_claim == 1


def test_considered_survives_on_a_projected_builtin_aggregate() -> None:
    aggregate = _verdict(
        "accuracy",
        "3" * 16,
        {
            "considered": 4,
            "true_positive": 1,
            "false_positive": 1,
            "true_negative": 1,
            "false_negative": 1,
        },
        "builtin",
    )
    run = replace(_with(), aggregate=(aggregate,))
    (projected,) = project(run, Table()).aggregate
    assert considered_cases(projected) == 4


# --------------------------------------------------------------------------- #
# What a projected document must hold, checked when it is read
# --------------------------------------------------------------------------- #


def test_a_projected_foreign_verdict_with_a_key_in_clear_is_refused() -> None:
    v = _verdict("foreign_check", "4" * 16, {"samples": 3}, "foreign")
    document = json.loads(run_to_json(project(_with(v), Table())))
    document["results"][0]["verdicts"][0]["metadata"][FOREIGN_KEY] = 1
    with pytest.raises(ValueError, match=FOREIGN_KEY):
        run_from_json(json.dumps(document))


def test_a_projected_configuration_key_in_clear_and_not_named_is_refused() -> None:
    named = frozenset(TARGET) & NAMED_CONFIG_KEYS
    document = json.loads(run_to_json(project(_configured(named), Table())))
    document["target_config"]["values"]["rossi_tenant_flag"] = 1
    with pytest.raises(ValueError, match="rossi_tenant_flag"):
        run_from_json(json.dumps(document))
