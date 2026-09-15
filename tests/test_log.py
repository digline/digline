"""The reading across runs, held to ADR 0020.

Every rule of that record is a test here, and the ones that matter most come in
pairs — a roll that is a roll beside an identical-looking one that is not —
because only the pair proves which fact decided it.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import pytest
from tests._helpers import cli, run_key
from tests._vocabulary import ADVICE, SPECULATION, spoken

from digline.cli import EXIT_OK, EXIT_USAGE
from digline.core import (
    CaseResult,
    Contains,
    EvaluatorInputs,
    JudgeReply,
    LlmRubric,
    Run,
    SystemConfig,
)
from digline.host import UsageError, instant
from digline.report import (
    LOCALES,
    TEXT,
    IdentityLog,
    IdentitySpan,
    Locale,
    Roll,
    identity_log,
    log_text,
    phrase,
)
from digline.store import Listing
from digline.wire import log_json, runs_json

T1 = "2026-09-01T10:00:00.000000+00:00"
T2 = "2026-09-02T10:00:00.000000+00:00"
T3 = "2026-09-03T10:00:00.000000+00:00"
T4 = "2026-09-04T10:00:00.000000+00:00"
T5 = "2026-09-05T10:00:00.000000+00:00"
T6 = "2026-09-06T10:00:00.000000+00:00"


def config(
    model: str = "claude-haiku-4-5",
    *,
    resolved: str | None = None,
    provider: str = "anthropic",
    **extra: str,
) -> SystemConfig:
    values: dict[str, str] = {"provider": provider, "model": model, **extra}
    if resolved is not None:
        values["resolved_model"] = resolved
    return SystemConfig(values=values)


def a_run(
    created_at: str,
    *,
    target: SystemConfig | None = None,
    judge: SystemConfig | None = None,
    version: str = "0.13.0",
    rejudged_from: str | None = None,
    passing: bool | None = None,
    git_commit: str | None = None,
) -> tuple[str, Run]:
    results: tuple[CaseResult, ...] = ()
    if passing is not None:
        output = "The capital is Rome." if passing else "The capital is Paris."
        verdict = Contains(needle="Rome")(EvaluatorInputs(output=output))
        results = (CaseResult("capital", (verdict,)),)
    run = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="abc",
        created_at=created_at,
        git_commit=git_commit,
        results=results,
        target_config=target if target is not None else SystemConfig(),
        judge_config=judge if judge is not None else SystemConfig(),
        digline_version=version,
        rejudged_from=rejudged_from,
    )
    return f"key-{created_at[:10]}", run


def read(*rows: tuple[str, Run], **options: object) -> IdentityLog:
    return identity_log(rows, tenant="acme", suite="qa", **options)  # type: ignore[arg-type]


def target_spans(log: IdentityLog) -> list[IdentitySpan]:
    return [span for span in log.spans if span.side == "target"]


# --------------------------------------------------------------------------- #
# §1 — a roll, and only that
# --------------------------------------------------------------------------- #


def test_a_roll_is_the_same_sent_model_answering_as_another() -> None:
    log = read(
        a_run(T1, target=config(resolved="claude-haiku-4-5-20251001")),
        a_run(T2, target=config(resolved="claude-haiku-4-5-20260301")),
    )
    assert log.rolls == (
        Roll(
            side="target",
            provider="anthropic",
            sent="claude-haiku-4-5",
            before="claude-haiku-4-5-20251001",
            after="claude-haiku-4-5-20260301",
            last_before=T1,
            first_after=T2,
            silent_between=0,
        ),
    )


def test_a_changed_sent_model_is_a_suite_edit_and_not_a_roll() -> None:
    log = read(
        a_run(T1, target=config("claude-haiku-4-5", resolved="claude-haiku-4-5")),
        a_run(T2, target=config("claude-sonnet-5", resolved="claude-sonnet-5")),
    )
    assert log.rolls == ()
    assert [span.sent for span in target_spans(log)] == [
        ("claude-haiku-4-5",),
        ("claude-sonnet-5",),
    ]


@pytest.mark.parametrize(
    ("answers", "passing", "rolls"),
    [
        # The scores collapse and the record says the same model answered.
        (("snapshot-a", "snapshot-a"), (True, False), 0),
        # The scores are identical and the record says two models answered.
        (("snapshot-a", "snapshot-b"), (True, True), 1),
    ],
)
def test_the_scores_decide_nothing(
    answers: tuple[str, str], passing: tuple[bool, bool], rolls: int
) -> None:
    """The pair, because only the pair shows the reading ignores the scores."""
    log = read(
        a_run(T1, target=config(resolved=answers[0]), passing=passing[0]),
        a_run(T2, target=config(resolved=answers[1]), passing=passing[1]),
    )
    assert len(log.rolls) == rolls


def test_a_roll_across_a_silence_carries_a_window_and_no_moment() -> None:
    silent = config()  # no answering model, and no writer named below
    log = read(
        a_run(T1, target=config(resolved="snapshot-a")),
        a_run(T2, target=silent, version=""),
        a_run(T3, target=silent, version=""),
        a_run(T4, target=silent, version=""),
        a_run(T5, target=config(resolved="snapshot-b")),
    )
    (roll,) = log.rolls
    assert (roll.last_before, roll.first_after, roll.silent_between) == (T1, T5, 3)
    rendered = json.dumps(log_json(log))
    roll_part = json.dumps(log_json(log)["rolls"])
    for silent_at in (T2, T3, T4):
        assert silent_at not in roll_part, "a roll is never pinned inside its window"
    # The silence is still a span of its own, bounded by its first and last run.
    assert T2 in rendered
    assert T4 in rendered
    text = "\n".join(log_text(log, locale="en"))
    assert "3 run(s) between them recorded no answering model." in text


def test_a_silence_is_never_collapsed_into_its_neighbours() -> None:
    log = read(
        a_run(T1, target=config(resolved="snapshot-a")),
        a_run(T2, target=config(), version=""),
        a_run(T3, target=config(resolved="snapshot-a")),
    )
    assert [span.answered for span in target_spans(log)] == [
        "snapshot-a",
        None,
        "snapshot-a",
    ]
    assert log.rolls == ()


# --------------------------------------------------------------------------- #
# §2 — a replay is never a sighting of the target
# --------------------------------------------------------------------------- #


def test_a_replay_is_not_a_target_sighting_and_is_a_judge_sighting() -> None:
    source_key, source = a_run(
        T1, target=config(resolved="snapshot-a"), judge=config("judge", resolved="j")
    )
    replay = a_run(
        T3,
        target=config(resolved="snapshot-a"),
        judge=config("judge", resolved="j"),
        rejudged_from=source_key,
    )
    log = read((source_key, source), replay)

    (target,) = target_spans(log)
    assert (target.last_seen, target.runs) == (T1, 1)
    (judge,) = [span for span in log.spans if span.side == "judge"]
    assert (judge.last_seen, judge.runs) == (T3, 2)
    assert [r.source for r in log.replays] == [source_key]
    text = "\n".join(log_text(log, locale="en"))
    assert "asked the target nothing" in text


# --------------------------------------------------------------------------- #
# §3 — the six absences
# --------------------------------------------------------------------------- #

ABSENT = [
    ("declared_nothing", SystemConfig(), "0.13.0", "target"),
    (
        "several_judges",
        SystemConfig(identities=("anthropic/judge-a", "openai/judge-b")),
        "0.13.0",
        "judge",
    ),
    (
        "withheld",
        config(resolved="acme-prod-v3", base_url="https://gw.example"),
        "",
        "target",
    ),
    ("not_reported", config(), "0.13.0", "target"),
    ("not_recorded", config(), "", "target"),
]


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize(("kind", "side_config", "version", "side"), ABSENT)
def test_every_absence_is_named_for_what_it_is(
    kind: str, side_config: SystemConfig, version: str, side: str, locale: Locale
) -> None:
    """One fixture per row, in both locales. `withheld` is written with no
    writer named, so it is also the precedence case: a withheld model is not
    reported as *not recorded* merely because the document is undated."""
    options = {"target": side_config} if side == "target" else {"judge": side_config}
    log = read(a_run(T1, version=version, **options))  # type: ignore[arg-type]
    (span,) = [s for s in log.spans if s.side == side]
    assert span.absence == kind
    assert span.answered is None
    text = "\n".join(log_text(log, locale=locale))
    assert phrase(locale, f"log.absence.{kind}") in text


@pytest.mark.parametrize("locale", LOCALES)
def test_what_was_not_read_is_counted_and_said(locale: Locale) -> None:
    log = read(a_run(T1, target=config(resolved="a")), skipped={9: 2}, unreadable=1)
    text = "\n".join(log_text(log, locale=locale))
    assert phrase(locale, "log.not_read.schema", count=2, version=9) in text
    assert phrase(locale, "log.not_read.unreadable", count=1) in text
    assert log_json(log)["skipped"] == {"9": 2}


def test_a_recorded_model_is_a_sighting_even_where_the_writer_is_not_named() -> None:
    """A file from 0.8 or 0.9 carries the model and not the writer."""
    log = read(a_run(T1, target=config(resolved="snapshot-a"), version=""))
    (span,) = target_spans(log)
    assert (span.answered, span.absence) == ("snapshot-a", None)


def test_an_undated_run_stays_undated() -> None:
    """ADR 0020 §3, row 6: no release is derived from anywhere else — not from
    the dependency pin at `git_commit`, and certainly not on a dirty tree."""
    log = read(a_run(T1, target=config(), version="", git_commit="a462ff3-dirty"))
    rendered = json.dumps(log_json(log)) + "\n".join(log_text(log, locale="en"))
    assert not re.search(r"\b\d+\.\d+\.\d+\b", rendered), rendered


# --------------------------------------------------------------------------- #
# §4 — the row has no score, by type
# --------------------------------------------------------------------------- #


def test_the_types_have_no_field_a_measurement_could_occupy() -> None:
    assert {f.name for f in fields(IdentitySpan)} == {
        "side",
        "provider",
        "sent",
        "answered",
        "absence",
        "first_seen",
        "last_seen",
        "runs",
        "environments",
    }
    assert {f.name for f in fields(Roll)} == {
        "side",
        "provider",
        "sent",
        "before",
        "after",
        "last_before",
        "first_after",
        "silent_between",
    }


# --------------------------------------------------------------------------- #
# §5 — the window, and the words
# --------------------------------------------------------------------------- #


def test_the_window_is_inclusive_and_compared_as_a_day() -> None:
    rows = (
        a_run("2026-09-13T23:59:59.000000+00:00", target=config(resolved="a")),
        a_run("2026-09-14T10:00:00.000000+00:00", target=config(resolved="a")),
        a_run("2026-09-15T00:00:01.000000+00:00", target=config(resolved="a")),
    )
    assert read(*rows, since="2026-09-14", until="2026-09-14").runs == 1
    assert read(*rows, since="2026-09-14T10:00:00").runs == 2
    assert read(*rows, until="2026-09-14T09:59:59").runs == 1


@pytest.mark.parametrize(
    ("given", "normalised"),
    [
        ("2026-09-14", "2026-09-14"),
        ("2026-09-14T10:00:00+02:00", "2026-09-14T08:00:00"),
        ("2026-09-14T08:00:00.123456+00:00", "2026-09-14T08:00:00"),
        (None, ""),
    ],
)
def test_a_bound_is_normalised_to_utc(given: str | None, normalised: str) -> None:
    assert instant(given, name="--since") == normalised


@pytest.mark.parametrize("given", ["2026-09-14T08:00:00", "yesterday", "2026-02-30"])
def test_a_bound_that_names_no_instant_is_refused(given: str) -> None:
    with pytest.raises(UsageError):
        instant(given, name="--since")


@pytest.mark.parametrize("locale", LOCALES)
def test_no_log_string_advises_or_speculates(locale: Locale) -> None:
    keys = [key for key in TEXT[locale] if key.startswith("log.")]
    assert len(keys) > 20, keys
    for key in keys:
        text = TEXT[locale][key]
        assert not spoken(ADVICE, text), f"{key} in {locale} advises: {text!r}"
        assert not spoken(SPECULATION, text), f"{key} in {locale} speculates"


def test_an_empty_store_is_not_a_history_without_a_roll() -> None:
    log = read()
    text = "\n".join(log_text(log, locale="en"))
    assert phrase("en", "log.rolls.none") not in text
    assert log_json(log)["runs"] == 0


# --------------------------------------------------------------------------- #
# §6 — the boundary
# --------------------------------------------------------------------------- #

GATEWAY = "llm-gateway.internal.rossi.example"


def test_a_named_endpoint_keeps_its_answering_model_and_declares_no_roll() -> None:
    """Two runs behind a customer's gateway, answering as two different models.
    The reading withholds both and cannot declare the roll — the cost ADR 0020
    §6 states — and neither value reaches any rendering."""
    log = read(
        a_run(
            T1, target=config(resolved="rossi-prod-v3", base_url=f"https://{GATEWAY}")
        ),
        a_run(
            T2, target=config(resolved="rossi-prod-v4", base_url=f"https://{GATEWAY}")
        ),
    )
    (span,) = target_spans(log)
    assert (span.absence, span.runs) == ("withheld", 2)
    assert log.rolls == ()
    rendered = json.dumps(log_json(log))
    for locale in LOCALES:
        rendered += "\n".join(log_text(log, locale=locale))
    for marker in ("rossi-prod-v3", "rossi-prod-v4", GATEWAY):
        assert marker not in rendered


def test_runs_json_carries_the_aggregate_and_nothing_a_verdict_merely_carried() -> None:
    """ADR 0020 §7: decision 9's crossing list, and no reason, no metadata."""
    secret = "Mario Rossi's IBAN is overdrawn"

    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=0.9, reason=secret)

    rubric = LlmRubric(rubric="leaks?", judge=judge, threshold=0.7, tolerance=0.05)
    verdict = rubric(EvaluatorInputs(output="…"))
    _key, bare = a_run(T1)
    run = Run(
        tenant=bare.tenant,
        environment=bare.environment,
        suite=bare.suite,
        config_hash=bare.config_hash,
        created_at=bare.created_at,
        aggregate=(verdict,),
    )
    document = runs_json(
        [("k", run)], tenant="acme", suite="qa", baseline_key=None, listing=Listing(())
    )
    (row,) = cast("list[dict[str, Any]]", document["runs"])
    (aggregate,) = cast("list[dict[str, Any]]", row["aggregate"])
    assert set(aggregate) == {
        "name",
        "assertion_id",
        "status",
        "score",
        "threshold",
        "tolerance",
    }
    assert secret not in json.dumps(document)


# --------------------------------------------------------------------------- #
# §10 — the shape of the dogfood's store, rebuilt without its content
# --------------------------------------------------------------------------- #


def dogfood() -> list[tuple[str, Run]]:
    """Sixteen documents with the identities and absences of the store ADR 0020
    was checked against, and none of its cases."""
    haiku = [f"2026-09-0{d}T0{h}:00:00.000000+00:00" for d in (8, 9) for h in range(4)]
    silent_sonnet = [f"2026-09-{d}T08:00:00.000000+00:00" for d in ("09", "10")] + [
        "2026-09-09T12:00:00.000000+00:00",
        "2026-09-10T12:00:00.000000+00:00",
    ]
    rows = [a_run(at, target=config("claude-haiku-4-5"), version="") for at in haiku]
    rows += [
        a_run(at, target=config("claude-sonnet-5"), version="") for at in silent_sonnet
    ]
    answered = config("claude-sonnet-5", resolved="claude-sonnet-5")
    recorded = ["2026-09-11T14:51:30.000000+00:00", "2026-09-11T15:09:23.000000+00:00"]
    rows += [
        (f"k-{at}", a_run(at, target=answered, version="0.11.0")[1]) for at in recorded
    ]
    rows.append(
        (
            "k-replay",
            a_run(
                "2026-09-14T14:36:01.000000+00:00",
                target=answered,
                version="0.12.1",
                rejudged_from=f"k-{recorded[1]}",
            )[1],
        )
    )
    rows.append(
        ("k-last", a_run("2026-09-14T15:03:21.000000+00:00", target=answered)[1])
    )
    return rows


def test_the_dogfood_shape_reads_as_the_record_says() -> None:
    rows = dogfood()
    assert len(rows) == 16
    _key, last = rows[-1]
    baseline = Run(
        tenant=last.tenant,
        environment=last.environment,
        suite=last.suite,
        config_hash=last.config_hash,
        created_at=last.created_at,
        target_config=last.target_config,
        digline_version=last.digline_version,
        promoted_at="2026-09-14T15:53:17+00:00",
    )
    log = read(*rows, baseline=("k-last", baseline))

    assert [(s.sent, s.answered, s.absence, s.runs) for s in target_spans(log)] == [
        (("claude-haiku-4-5",), None, "not_recorded", 8),
        (("claude-sonnet-5",), None, "not_recorded", 4),
        (("claude-sonnet-5",), "claude-sonnet-5", None, 3),
    ]
    assert log.rolls == ()
    assert len(log.replays) == 1
    lines = log_text(log, locale="en")
    assert lines[0].startswith("qa · 16 run(s) read in this store")
    assert phrase("en", "log.rolls.none") in lines
    assert any(
        "declared no configuration" in line and "16 run(s)" in line for line in lines
    )
    assert any("approved 2026-09-14T15:53:17+00:00" in line for line in lines)


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #


def test_log_is_never_a_gate(repo: Path) -> None:
    run_key(repo)
    shown = cli(repo, "log", "--suite", "suite_qa.py")
    assert shown.returncode == EXIT_OK, shown.stderr
    assert "Target" in shown.stdout
    emitted = cli(repo, "log", "--suite", "suite_qa.py", "--json")
    assert emitted.returncode == EXIT_OK, emitted.stderr
    document = json.loads(emitted.stdout)
    assert document["output_version"] == 1
    assert document["runs"] == 1
    assert "exit_code" not in document


def test_log_refuses_an_instant_without_a_zone(repo: Path) -> None:
    refused = cli(repo, "log", "--suite", "suite_qa.py", "--since", "2026-09-14T08:00")
    assert refused.returncode == EXIT_USAGE
    assert "time zone" in refused.stderr
