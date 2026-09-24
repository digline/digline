"""The seventh absence: the endpoint echoed the requested id. (ADR 0020 §3)

A `resolved_model` equal to the sent model *looks* like a confirmation and is
not one — the endpoint said what it was asked for, not what answered. Stated as
a fact and never as a diagnosis. Every rule here is a pair, because only the
pair shows which fact decided it.
"""

from __future__ import annotations

import json

import pytest

from digline.core import Run, SystemConfig, compare
from digline.report import (
    LOCALES,
    Locale,
    TallyFact,
    explain_text,
    facts,
    headline,
    identity_log,
    log_text,
    phrase,
)
from digline.report.log import sighting
from digline.wire import compare_json, log_json

GATEWAY = "https://llm-gateway.internal.example/v1"
T1 = "2026-09-01T10:00:00+00:00"
T2 = "2026-09-02T10:00:00+00:00"
T3 = "2026-09-03T10:00:00+00:00"


def config(model: str = "gpt-5.6-sol", **values: str) -> SystemConfig:
    return SystemConfig(values={"provider": "openai", "model": model, **values})


def a_run(created_at: str, target: SystemConfig) -> tuple[str, Run]:
    run = Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="abc",
        created_at=created_at,
        target_config=target,
        digline_version="0.13.0",
    )
    return f"key-{created_at[:10]}", run


# --------------------------------------------------------------------------- #
# The row, literally
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("answered", "absence"),
    [
        ("gpt-5.6-sol", "echoed"),
        # Nothing normalised: a prefix or a case is a different string, and
        # deciding they mean the same model would be interpretation.
        ("openai/gpt-5.6-sol", None),
        ("GPT-5.6-SOL", None),
        ("gpt-5.6-sol-2026-08-01", None),
    ],
)
def test_an_echo_is_literal_string_equality(answered: str, absence: str | None) -> None:
    found = sighting(config(resolved_model=answered), writer="0.13.0")
    assert found.absence == absence
    assert (found.answered is None) is (absence is not None)


def test_behind_a_named_endpoint_the_same_values_read_as_withheld() -> None:
    """Row 4 before row 7: the sent id travels in clear, so *echoed* about a
    withheld value would disclose it."""
    found = sighting(
        config(resolved_model="gpt-5.6-sol", base_url=GATEWAY), writer="0.13.0"
    )
    assert found.absence == "withheld"
    log = identity_log(
        [a_run(T1, config(resolved_model="gpt-5.6-sol", base_url=GATEWAY))],
        tenant="acme",
        suite="qa",
    )
    rendered = json.dumps(log_json(log)) + "".join(
        "\n".join(log_text(log, locale=locale)) for locale in LOCALES
    )
    assert "echoed" not in rendered
    for locale in LOCALES:
        assert phrase(locale, "log.absence.echoed") not in rendered


# --------------------------------------------------------------------------- #
# An echo cannot be one side of a roll
# --------------------------------------------------------------------------- #


def test_an_echo_then_a_snapshot_is_first_seen_not_a_roll() -> None:
    log = identity_log(
        [
            a_run(T1, config(resolved_model="gpt-5.6-sol")),
            a_run(T2, config(resolved_model="gpt-5.6-sol-2026-08-01")),
        ],
        tenant="acme",
        suite="qa",
    )
    assert log.rolls == ()
    assert [(s.absence, s.answered) for s in log.spans if s.side == "target"] == [
        ("echoed", None),
        (None, "gpt-5.6-sol-2026-08-01"),
    ]


def test_an_echo_between_two_snapshots_is_silence_inside_the_window() -> None:
    log = identity_log(
        [
            a_run(T1, config(resolved_model="gpt-5.6-sol-a")),
            a_run(T2, config(resolved_model="gpt-5.6-sol")),
            a_run(T3, config(resolved_model="gpt-5.6-sol-b")),
        ],
        tenant="acme",
        suite="qa",
    )
    (roll,) = log.rolls
    assert (roll.last_before, roll.first_after, roll.silent_between) == (T1, T3, 1)


# --------------------------------------------------------------------------- #
# The corollary belongs to four rows
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize(
    ("target", "version", "said"),
    [
        (config(resolved_model="gpt-5.6-sol"), "0.13.0", True),
        (config(resolved_model="x", base_url=GATEWAY), "0.13.0", True),
        (config(), "0.13.0", True),
        (config(), "", True),
        (config(resolved_model="gpt-5.6-sol-2026-08-01"), "0.13.0", False),
    ],
)
def test_the_canary_line_appears_only_where_nothing_is_identified(
    locale: Locale, target: SystemConfig, version: str, said: bool
) -> None:
    key, run = a_run(T1, target)
    run = Run(
        tenant=run.tenant,
        environment=run.environment,
        suite=run.suite,
        config_hash=run.config_hash,
        created_at=run.created_at,
        target_config=run.target_config,
        judge_config=config(resolved_model="judge-2026-08-01"),
        digline_version=version,
    )
    log = identity_log([(key, run)], tenant="acme", suite="qa")
    lines = log_text(log, locale=locale)
    assert (phrase(locale, "log.canary_only") in lines) is said


# --------------------------------------------------------------------------- #
# compare, the report and explain
# --------------------------------------------------------------------------- #


def compared(
    baseline_target: SystemConfig, run_target: SystemConfig
) -> tuple[Run, Run]:
    return a_run(T1, baseline_target)[1], a_run(T2, run_target)[1]


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize(
    ("run_target", "echoed"),
    [
        (config(resolved_model="gpt-5.6-sol"), True),
        (config(resolved_model="gpt-5.6-sol-2026-08-01"), False),
        (config(resolved_model="gpt-5.6-sol", base_url=GATEWAY), False),
    ],
)
def test_the_headline_and_the_reading_say_echoed_where_the_record_does(
    locale: Locale, run_target: SystemConfig, echoed: bool
) -> None:
    baseline, run = compared(run_target, run_target)
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale=locale)

    clause = phrase(locale, "fact.target_config.echoed", model="gpt-5.6-sol")
    assert (clause in head.sentence) is echoed
    assert head.target_echoed is echoed
    assert (
        compare_json(comparison, head, baseline=baseline, full=False)["target_echoed"]
        is echoed
    )

    reading = facts(run, comparison)
    tally = [f for f in reading if isinstance(f, TallyFact) and f.kind == "echoed"]
    assert bool(tally) is echoed
    text = "\n".join(explain_text(reading, locale=locale))
    assert (phrase(locale, "explain.tally.echoed") in text) is echoed


def test_an_echo_moves_no_exit_code() -> None:
    from digline.wire import exit_code

    target = config(resolved_model="gpt-5.6-sol")
    baseline, run = compared(target, target)
    head = headline(compare(run, baseline), run, baseline, locale="en")
    assert head.target_echoed is True
    assert exit_code(head) == 0
