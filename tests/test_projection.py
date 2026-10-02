"""The projection: the reference the software house commits, naming nothing.

Written from the mistake each test prevents — a name crossing under a token
that does not hide it, or a check that passes because it cannot look. (ADR 0034
§2, §4, §5, §8; ADR 0036 §2, §5, §6)
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import replace

import pytest

from digline.core import (
    REDACTED,
    Artifact,
    CalibrationBand,
    CaseResult,
    DocumentRefusedError,
    ProjectionRefusedError,
    RecordedResponse,
    Run,
    Score,
    SystemConfig,
    TokenKind,
    Verdict,
    compare,
    grouped_name,
    is_token,
    project,
    redact,
    run_from_json,
    run_to_json,
    split_grouped_name,
)
from digline.host import REFUSALS

# Every name the fixture carries that a projection must not let through. The
# test that reads the document scans for each of them.
CASE = "rossi-mario-overdraft"
CHECK = "leaks_account_data"
FAMILY = "precision"
GROUP = "private-banking-milano"
ARTIFACT = "prompts/rossi-escalation.md"
BASE_URL = "https://llm.acme-bank.internal/v1"
RESOLVED = "acme-legal-assistant-prod-eu-west-v3"
FINGERPRINT = "fp-build-7781-acme"
TARGET_MODEL = "acme-private-model"
JUDGE_MODEL = "claude-opus-5-5"
LEAKS = "d0891fbb13f6509e"
PRECISION = "5e1f0c2a9b7d4e36"
PRECISION_GROUP = "8a3c61f0e2b95d47"
REASON = "The reply names Mario Rossi and his IBAN IT60X0542811101"

NAMES = (
    *(CASE, CHECK, FAMILY, GROUP, ARTIFACT, BASE_URL, RESOLVED, FINGERPRINT),
    *(TARGET_MODEL, JUDGE_MODEL, REASON, "acme-gateway", "anthropic"),
)


class Table:
    """A minter the way the owning process is one: look-up-or-mint on (kind,
    text), 128 random bits. It remembers every question it was asked."""

    def __init__(self) -> None:
        self.rows: dict[tuple[TokenKind, str], str] = {}
        self.asked: list[tuple[TokenKind, str]] = []

    def __call__(self, kind: TokenKind, text: str) -> str:
        self.asked.append((kind, text))
        return self.rows.setdefault((kind, text), secrets.token_urlsafe(16))

    def token(self, kind: TokenKind, text: str) -> str:
        return self.rows[(kind, text)]


def verdict(name: str, assertion_id: str, score: float = 0.9) -> Verdict:
    return Verdict(
        score=Score(name=name, score=score, metadata={"judge_min": 0.8}),
        threshold=0.5,
        status="pass" if score >= 0.5 else "fail",
        reason=REASON,
        assertion_id=assertion_id,
    )


def promoted(**overrides: object) -> Run:
    """A reference as `promote_baseline` returns it: stamped, and no answers."""
    fields: dict[str, object] = {
        "tenant": "acme",
        "environment": "production",
        "suite": "support",
        "config_hash": "c0ffee00c0ffee00",
        "created_at": "2026-09-30T10:00:00+00:00",
        "promoted_at": "2026-09-30T12:00:00+00:00",
        "results": (
            CaseResult(CASE, (verdict(CHECK, LEAKS),)),
            CaseResult(
                "calibration-1",
                (verdict(CHECK, LEAKS, 0.6),),
                calibration=CalibrationBand(CHECK, 0.4, 0.8, LEAKS),
            ),
            CaseResult("set-aside", suspended="fails on the Rossi account"),
        ),
        "aggregate": (
            verdict(FAMILY, PRECISION),
            verdict(grouped_name(FAMILY, GROUP), PRECISION_GROUP),
        ),
        "metadata": {"customer_balance": 1499.0},
        "artifacts": {ARTIFACT: Artifact(sha="ab" * 32, text="Escalate Rossi")},
        "pinned": (ARTIFACT,),
        "target_config": SystemConfig(
            values={
                "provider": "acme-gateway",
                "model": TARGET_MODEL,
                "temperature": 0.3,
                "base_url": BASE_URL,
                "resolved_model": RESOLVED,
                "fingerprint": FINGERPRINT,
            }
        ),
        "judge_config": SystemConfig(
            values={"provider": "anthropic", "model": JUDGE_MODEL, "max_tokens": 512},
            identities=(f"anthropic/{JUDGE_MODEL}",),
        ),
    }
    fields.update(overrides)
    return Run(**fields)  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------- #
# What a projected document carries
# --------------------------------------------------------------------------- #


def test_a_projected_document_names_nothing() -> None:
    document = run_to_json(project(promoted(), Table()))
    for name in NAMES:
        assert name not in document, name
    raw = json.loads(document)
    assert raw["projected"] is True
    assert raw["redacted"] is True


def test_what_is_not_a_name_crosses_in_clear() -> None:
    """The committing party's strings, digline's vocabulary, and the numbers
    §4 has not decided."""
    projected = project(promoted(), Table())
    assert (projected.tenant, projected.suite) == ("acme", "support")
    assert projected.environment == "production"
    assert projected.promoted_at == "2026-09-30T12:00:00+00:00"
    first = projected.results[0].verdicts[0]
    assert (first.assertion_id, first.status, first.score.score) == (LEAKS, "pass", 0.9)
    assert first.score.metadata == {"judge_min": 0.8}
    assert 0.3 in projected.target_config.values.values()


def test_every_name_is_the_token_its_kind_was_minted() -> None:
    table = Table()
    projected = project(promoted(), table)
    assert projected.results[0].case_id == table.token("case_id", CASE)
    band = projected.results[1].calibration
    assert band is not None
    assert band.check == table.token("calibration_check", CHECK)
    assert band.assertion_id == LEAKS
    assert list(projected.artifacts) == [table.token("artifact_path", ARTIFACT)]
    assert projected.pinned == (table.token("artifact_path", ARTIFACT),)
    assert projected.judge_config.identities == (
        table.token("judge_identity", f"anthropic/{JUDGE_MODEL}"),
    )
    assert table.token("judge_config_value", JUDGE_MODEL) in (
        projected.judge_config.values.values()
    )


def test_a_grouped_aggregate_still_parses_with_both_parts_tokenised() -> None:
    table = Table()
    grouped = project(promoted(), table).aggregate[1].score.name
    family, group = split_grouped_name(grouped)
    assert family == table.token("verdict_name", FAMILY)
    assert group == table.token("group", GROUP)


def test_equal_text_in_two_kinds_is_asked_as_two_kinds() -> None:
    """The check's name is both a verdict name and a band's check word. Keyed
    by (kind, text), they get two tokens, so the two places do not disclose
    that they are equal. (ADR 0036 §6)"""
    table = Table()
    project(promoted(), table)
    assert table.token("verdict_name", CHECK) != table.token("calibration_check", CHECK)


def test_the_payload_is_gone_as_redaction_removes_it() -> None:
    projected = project(promoted(), Table())
    assert projected.results[0].verdicts[0].reason == REDACTED
    assert projected.results[2].suspended == REDACTED
    assert projected.metadata == {}
    artifact = next(iter(projected.artifacts.values()))
    assert (artifact.withheld, artifact.text, artifact.sha) == (True, None, "")


def test_it_round_trips_through_the_document() -> None:
    projected = project(promoted(), Table())
    document = run_to_json(projected)
    assert run_to_json(run_from_json(document)) == document
    assert run_from_json(document).projected is True


def test_redacting_a_projection_keeps_its_declaration() -> None:
    projected = project(promoted(), Table())
    assert redact(projected).projected is True


def test_two_projections_from_one_table_pair_as_the_same_cases() -> None:
    """Tokens are stable across documents of one suite, which is what lets
    the software house compare two projections it holds. (ADR 0036 §4)"""
    table = Table()
    before = project(promoted(), table)
    now = project(promoted(created_at="2026-09-30T11:00:00+00:00"), table)
    outcomes = {delta.outcome for delta in compare(now, before).deltas}
    assert outcomes and not outcomes & {"new", "missing"}


# --------------------------------------------------------------------------- #
# The order: withheld while the keys are still text (§10)
# --------------------------------------------------------------------------- #


def test_the_perimeter_values_are_never_handed_to_the_minter() -> None:
    """If the projection tokenised before it redacted, `base_url`,
    `fingerprint` and — at a named endpoint — `resolved_model` would be minted
    like any other value, and cross under tokens. Asked of the minter rather
    than of the document, because on the document a token hides which it was."""
    table = Table()
    project(promoted(), table)
    handed = {text for _, text in table.asked}
    assert not {BASE_URL, FINGERPRINT, RESOLVED} & handed


def test_the_perimeter_keys_are_withheld_as_tokens() -> None:
    table = Table()
    config = project(promoted(), table).target_config
    assert config.withheld == frozenset(
        table.token("target_config_key", key)
        for key in ("base_url", "fingerprint", "resolved_model")
    )


def test_on_the_projected_document_the_named_endpoint_is_not_seen() -> None:
    """Declared, and consistent with §7.2's ruling: the protection happened
    during redaction, and the projected document no longer shows it."""
    config = project(promoted(), Table()).target_config
    assert config.perimeter() == frozenset({"base_url", "fingerprint"})
    assert config.redacted() is config


# --------------------------------------------------------------------------- #
# What the projection refuses
# --------------------------------------------------------------------------- #


def test_a_projection_is_not_projected_again() -> None:
    table = Table()
    with pytest.raises(ProjectionRefusedError, match="already projected"):
        project(project(promoted(), table), table)


def test_a_run_nobody_promoted_is_refused() -> None:
    with pytest.raises(ProjectionRefusedError, match="not promoted"):
        project(promoted(promoted_at=""), Table())


def test_a_run_still_carrying_answers_is_refused() -> None:
    run = promoted()
    answered = replace(
        run,
        results=(
            replace(run.results[0], responses=(RecordedResponse(withheld=True),)),
            *run.results[1:],
        ),
    )
    with pytest.raises(ProjectionRefusedError, match="recorded answers"):
        project(answered, Table())


def test_an_identity_on_the_target_side_is_refused() -> None:
    target = SystemConfig(values={"provider": "p", "model": "m"}, identities=("p/m",))
    with pytest.raises(ProjectionRefusedError, match="no token kind"):
        project(promoted(target_config=target), Table())


def test_an_answer_without_a_tokens_form_is_refused() -> None:
    with pytest.raises(ProjectionRefusedError, match="token's form"):
        project(promoted(), lambda kind, text: text)


def test_a_minter_answering_one_name_twice_differently_is_refused() -> None:
    with pytest.raises(ProjectionRefusedError, match="two tokens"):
        project(promoted(), lambda kind, text: secrets.token_urlsafe(16))


def test_a_minter_giving_two_names_one_token_is_refused() -> None:
    constant = secrets.token_urlsafe(16)
    with pytest.raises(ProjectionRefusedError, match="already given"):
        project(promoted(), lambda kind, text: constant)


def test_the_refusal_is_classified() -> None:
    assert ProjectionRefusedError in REFUSALS


# --------------------------------------------------------------------------- #
# `projected` is verified, not believed (§8)
# --------------------------------------------------------------------------- #


def projected_run() -> Run:
    return project(promoted(), Table())


def test_projected_without_redacted_is_refused() -> None:
    with pytest.raises(ValueError, match="not redacted"):
        replace(projected_run(), redacted=False)


def _case_id_in_clear(run: Run) -> Run:
    return replace(
        run, results=(replace(run.results[0], case_id=CASE), *run.results[1:])
    )


def _verdict_name_in_clear(run: Run) -> Run:
    named = replace(
        run.aggregate[0], score=replace(run.aggregate[0].score, name=FAMILY)
    )
    return replace(run, aggregate=(named, *run.aggregate[1:]))


def _run_metadata(run: Run) -> Run:
    return replace(run, metadata={"balance": 1.0})


def _artifact_path_in_clear(run: Run) -> Run:
    return replace(run, artifacts={ARTIFACT: Artifact(withheld=True)}, pinned=())


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (_case_id_in_clear, "case id"),
        (_verdict_name_in_clear, "name of a verdict"),
        (_run_metadata, "carries metadata"),
        (_artifact_path_in_clear, "artifact path"),
    ],
)
def test_a_projected_run_holding_a_name_is_refused(
    change: Callable[[Run], Run], match: str
) -> None:
    run = projected_run()
    with pytest.raises(ValueError, match=match):
        change(run)


def test_a_projected_run_with_an_artifact_in_clear_is_refused() -> None:
    run = projected_run()
    path = next(iter(run.artifacts))
    with pytest.raises(ValueError, match="not withheld"):
        replace(run, artifacts={path: Artifact(sha="ab" * 32, text="Escalate")})


def test_a_projected_run_with_string_metadata_on_a_verdict_is_refused() -> None:
    run = projected_run()
    leaking = replace(
        run.aggregate[0],
        score=replace(run.aggregate[0].score, metadata={"model": "claude"}),
    )
    with pytest.raises(ValueError, match="string metadata"):
        replace(run, aggregate=(leaking,))


def test_a_configuration_in_clear_inside_a_projected_run_is_refused() -> None:
    run = projected_run()
    clear = SystemConfig(values={"provider": "p", "model": "m"}, projected=True)
    with pytest.raises(ValueError, match="target_config key"):
        replace(run, target_config=clear)


def test_a_configuration_claiming_projected_in_a_plain_run_is_refused() -> None:
    token = secrets.token_urlsafe(16)
    with pytest.raises(ValueError, match="exactly when the run"):
        promoted(target_config=SystemConfig(values={token: token}, projected=True))


# --------------------------------------------------------------------------- #
# §7.1: the two key checks, relaxed together on a projected configuration
# --------------------------------------------------------------------------- #


def test_a_projected_configuration_needs_no_provider_or_model_in_clear() -> None:
    key, value = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    assert is_token(key)
    SystemConfig(values={key: value}, identities=(value,), projected=True)


def test_the_same_configuration_unprojected_is_still_refused() -> None:
    key, value = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    with pytest.raises(ValueError, match="missing model, provider"):
        SystemConfig(values={key: value})


def test_an_unprojected_identity_that_contradicts_values_is_still_refused() -> None:
    with pytest.raises(ValueError, match="one object cannot answer"):
        SystemConfig(values={"provider": "p", "model": "m"}, identities=("q/m",))


def test_two_identities_and_a_set_up_are_refused_projected_or_not() -> None:
    """A count survives tokenisation, so this one is not relaxed."""
    token = secrets.token_urlsafe(16)
    with pytest.raises(ValueError, match="2 instruments"):
        SystemConfig(values={token: token}, identities=("a", "b"), projected=True)


def test_a_document_that_does_not_say_whether_it_is_projected_is_refused() -> None:
    """Required, like `redacted`: a reader that took absence for `false` would
    read a projection as a document that names things."""
    raw = json.loads(run_to_json(promoted()))
    del raw["projected"]
    with pytest.raises(ValueError, match="projected"):
        run_from_json(json.dumps(raw))


NOT_JSON: list[tuple[str, Callable[[str], str]]] = [
    ("truncated", lambda text: text[: len(text) // 2]),
    ("trailing data", lambda text: text + "x"),
    ("empty", lambda text: ""),
]


@pytest.mark.parametrize(("label", "cut"), NOT_JSON)
def test_text_that_is_not_json_is_refused_by_a_type_the_front_ends_translate(
    label: str, cut: Callable[[str], str]
) -> None:
    table = Table()
    document = run_to_json(project(promoted(), table))
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_json(cut(document))
    assert type(refused.value) is DocumentRefusedError, label
    assert isinstance(refused.value.__cause__, json.JSONDecodeError), label
    assert DocumentRefusedError in REFUSALS
    for token in table.rows.values():
        assert token not in str(refused.value), label
