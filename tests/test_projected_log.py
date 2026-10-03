"""The identity reading on a projected document, in both regimes. (#402)

A projection tokenises every configuration key (ADR 0034 §4), and `sighting`
read the keys by their text. On a projected baseline `digline log` ended in a
traceback, `KeyError: 'provider'`, with exit 1, which is `EXIT_WORSE` on a
command that is never a gate. The membership tests after the subscript have
#275's shape. Measured on a repair that only made the subscript tolerant: both
shapes below read "no answering model was reported", which is false for both.
So the repair is row 8 of ADR 0020 §3, *projected*, checked after the two rows
that stay true on a projection. A lookup that does not raise would not do.

Both halves are held: the projected sentence is the absence, and the clear one
keeps its sighting.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from tests._helpers import cli, configured_repo

from digline.cli import EXIT_OK
from digline.core import (
    ConfigValue,
    Run,
    Score,
    SystemConfig,
    Verdict,
    project,
    project_served,
)
from digline.report import LOCALES, Locale, identity_log, log_text, phrase
from digline.report.log import UNIDENTIFIED, IdentityLog, sighting
from digline.wire import log_json
from test_projection import Table

type Values = Mapping[str, ConfigValue]

FIRST_PARTY: Values = {
    "provider": "openai",
    "model": "gpt-5",
    "resolved_model": "gpt-5-2026",
}
#: Behind a named endpoint `resolved_model` is withheld, and then tokenised:
#: on the projection it is a token in `withheld`.
NAMED: Values = {**FIRST_PARTY, "base_url": "https://gw.example.invalid/v1"}

SHAPES = [
    pytest.param(FIRST_PARTY, "answered", id="first-party"),
    pytest.param(NAMED, "withheld", id="named-endpoint"),
]


def a_run(target: SystemConfig, judge: SystemConfig | None = None) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="c0ffee00c0ffee00",
        created_at="2026-09-01T00:00:00+00:00",
        promoted_at="2026-09-02T00:00:00+00:00",
        digline_version="0.20.0",
        target_config=target,
        judge_config=judge if judge is not None else SystemConfig(),
    )


def reference(values: Values, *, projected: bool) -> Run:
    run = a_run(SystemConfig(values=values))
    return project(run, Table()) if projected else run


@pytest.mark.parametrize(("values", "clear"), SHAPES)
def test_a_projected_configuration_is_read_as_projected(
    values: Values, clear: str
) -> None:
    """The first assertion is #402's: it raised `KeyError` before row 8."""
    projected = reference(values, projected=True)
    found = sighting(projected.target_config, writer=projected.digline_version)
    assert found.absence == "projected"
    assert (found.provider, found.sent, found.answered) == ("", (), None)


@pytest.mark.parametrize(("values", "clear"), SHAPES)
def test_the_clear_reading_keeps_its_sighting(values: Values, clear: str) -> None:
    """The other regime. Row 8 is keyed on what the document declares, so a
    clear document never meets it."""
    plain = reference(values, projected=False)
    found = sighting(plain.target_config, writer=plain.digline_version)
    assert (found.provider, found.sent) == ("openai", ("gpt-5",))
    if clear == "answered":
        assert (found.answered, found.absence) == ("gpt-5-2026", None)
    else:
        assert (found.answered, found.absence) == (None, "withheld")


def test_the_two_rows_that_stay_true_on_a_projection_come_first() -> None:
    """Emptiness and the number of judges survive tokenisation, so rows 2 and 3
    still say what they say. Row 8 does not stand in for them."""
    nothing = project(a_run(SystemConfig()), Table())
    assert sighting(nothing.target_config, writer="0.20.0").absence == (
        "declared_nothing"
    )
    judges = project(
        a_run(SystemConfig(), SystemConfig(identities=("judge-a", "judge-b"))),
        Table(),
    )
    found = sighting(judges.judge_config, writer="0.20.0")
    assert found.absence == "several_judges"
    assert len(found.sent) == 2


def test_any_projected_document_is_read_by_row_8_not_only_a_reference() -> None:
    """The row is keyed on the configuration's own flag, so a served projection
    of a run nobody promoted reads the same."""
    served = project_served(
        replace(a_run(SystemConfig(values=FIRST_PARTY)), promoted_at=""), Table()
    )
    assert sighting(served.target_config, writer="").absence == "projected"


@pytest.mark.parametrize("locale", LOCALES)
def test_the_reference_line_says_projected_and_names_no_token(
    locale: Locale,
) -> None:
    table = Table()
    projected = project(a_run(SystemConfig(values=NAMED)), table)
    log = identity_log((), tenant="acme", suite="qa", baseline=("k", projected))
    text = "\n".join(log_text(log, locale=locale))
    assert phrase(locale, "log.absence.projected") in text
    for token in table.rows.values():
        assert token not in text


def test_the_wire_carries_the_absence_in_row_2s_shape() -> None:
    projected = project(a_run(SystemConfig(values=FIRST_PARTY)), Table())
    log = identity_log((), tenant="acme", suite="qa", baseline=("k", projected))
    # Through `json`, as a consumer reads it: `log_json` is typed to its top
    # level only.
    document = json.loads(json.dumps(log_json(log)))
    assert document["reference"]["target"] == {
        "provider": "",
        "sent": [],
        "answered": None,
        "absence": "projected",
    }


def test_projected_is_not_among_the_absences_beneath_the_canary_sentence() -> None:
    """A projected document may identify the answering model under a token:
    that is not *not identified*. (ADR 0020 §3, amended 2026-10-03)"""
    assert "projected" not in UNIDENTIFIED


# --------------------------------------------------------------------------- #
# From the front end, which is where #402 asked for it to be reproduced
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("values", "clear"), SHAPES)
def test_digline_log_reads_a_projected_baseline(
    tmp_path: Path, values: Values, clear: str
) -> None:
    root = configured_repo(tmp_path, values, projected=True)
    shown = cli(root, "log", "--suite", "suite_qa.py")
    assert shown.returncode == EXIT_OK, shown.stderr
    assert "Traceback" not in shown.stderr
    assert phrase("en", "log.absence.projected") in shown.stdout
    assert phrase("en", "log.absence.not_reported") not in shown.stdout
    emitted = cli(root, "log", "--suite", "suite_qa.py", "--json")
    assert emitted.returncode == EXIT_OK, emitted.stderr
    document = json.loads(emitted.stdout)
    assert document["reference"]["target"]["absence"] == "projected"


@pytest.mark.parametrize(("values", "clear"), SHAPES)
def test_digline_log_reads_the_same_baseline_in_clear(
    tmp_path: Path, values: Values, clear: str
) -> None:
    root = configured_repo(tmp_path, values, projected=False)
    emitted = cli(root, "log", "--suite", "suite_qa.py", "--json")
    assert emitted.returncode == EXIT_OK, emitted.stderr
    target = json.loads(emitted.stdout)["reference"]["target"]
    assert (target["provider"], target["sent"]) == ("openai", ["gpt-5"])
    if clear == "answered":
        assert (target["answered"], target["absence"]) == ("gpt-5-2026", None)
    else:
        assert (target["answered"], target["absence"]) == (None, "withheld")


# --------------------------------------------------------------------------- #
# The spread against a projected reference (ADR 0024 §7.5, amended 2026-10-03)
# --------------------------------------------------------------------------- #

#: A projection refuses an `assertion_id` that is not a digest, so the
#: aggregate carries one.
DIGEST_ID = "b" * 16


def aggregate(
    score: float | None, status: str = "pass", name: str = "accuracy"
) -> Verdict:
    return Verdict(
        score=Score(name=name, score=score),
        threshold=0.5,
        status=status,  # pyright: ignore[reportArgumentType]
        reason="r",
        assertion_id=DIGEST_ID,
    )


def scored(when: str, *aggregates: Verdict) -> tuple[str, Run]:
    run = replace(
        a_run(SystemConfig()), created_at=when, promoted_at="", aggregate=aggregates
    )
    return f"k-{when[:10]}", run


def flipped_history() -> list[tuple[str, Run]]:
    """`test_a_flip_is_silent`'s shape: two passing runs, then one that
    failed, against a reference that passed."""
    return [
        scored("2026-01-01T00:00:00+00:00", aggregate(0.71)),
        scored("2026-01-02T00:00:00+00:00", aggregate(0.86)),
        scored("2026-01-09T00:00:00+00:00", aggregate(0.2, "fail")),
    ]


def spread_reference(
    aggregates: tuple[Verdict, ...] = (), *, projected: bool
) -> tuple[str, Run]:
    run = replace(
        a_run(SystemConfig()),
        created_at="2025-12-01T00:00:00+00:00",
        aggregate=aggregates or (aggregate(0.76),),
    )
    return ("kb", project(run, Table()) if projected else run)


def spread_of(rows: list[tuple[str, Run]], baseline: tuple[str, Run]) -> IdentityLog:
    return identity_log(rows, tenant="acme", suite="qa", baseline=baseline)


def test_a_flip_against_a_projected_reference_prints_no_range() -> None:
    """The measured case. Before the guard the lookup by name missed, the flip
    check never ran, and a range 0.71-0.86 was printed with `reference: None`."""
    log = spread_of(flipped_history(), spread_reference(projected=True))
    assert log.spread == ()
    assert log.spread_absence == {"projected": 1}


def test_the_same_flip_against_the_reference_in_clear_is_still_a_flip() -> None:
    """The other regime: the guard is keyed on the document's own flag."""
    log = spread_of(flipped_history(), spread_reference(projected=False))
    assert log.spread == ()
    assert log.spread_absence == {"flipped": 1}


def test_no_range_against_a_projected_reference_even_without_a_flip() -> None:
    """Whether there was a flip cannot be decided, so a run that did not flip
    is read the same way. In clear the same history reads a range."""
    rows = flipped_history()[:2] + [scored("2026-01-09T00:00:00+00:00", aggregate(0.8))]
    projected = spread_of(rows, spread_reference(projected=True))
    assert (projected.spread, projected.spread_absence) == ((), {"projected": 1})
    clear = spread_of(rows, spread_reference(projected=False))
    assert [item.reference for item in clear.spread] == [0.76]


def test_scoreless_stays_true_on_a_projection_and_both_are_said() -> None:
    rows = [
        scored(
            "2026-01-09T00:00:00+00:00",
            aggregate(0.8),
            aggregate(None, "error", name="recall"),
        )
    ]
    log = spread_of(rows, spread_reference(projected=True))
    assert log.spread_absence == {"projected": 1, "scoreless": 1}


@pytest.mark.parametrize("locale", LOCALES)
def test_the_projected_cause_is_said_in_words(locale: Locale) -> None:
    log = spread_of(flipped_history(), spread_reference(projected=True))
    text = "\n".join(log_text(log, locale=locale))
    assert phrase(locale, "log.spread.projected", count=1) in text
    # The floor is printed beneath a range and nowhere else, so its absence
    # says no range was printed, whatever the numbers would have looked like.
    assert phrase(locale, "log.spread.floor") not in text


def test_the_wire_names_the_projected_cause() -> None:
    log = spread_of(flipped_history(), spread_reference(projected=True))
    document = log_json(log)
    assert document["spread"] == []
    assert document["spread_absence"] == {"projected": 1}
