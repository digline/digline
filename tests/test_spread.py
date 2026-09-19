"""How much the suite moves between runs — ADR 0024 §7, the fourth measurement.

The record rules ten things and this file asserts them one at a time. Two carry
the weight: the latest run is **never** in the range it is read against, and the
inside/outside clause is **withheld** until the floor on N is measured on real
history. A spread that contained its own value would make *inside* true by
construction, which is `AGENTS.md` §5's excuse promoted to a feature.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from digline.core import CaseResult, Run, Score, SystemConfig, Verdict
from digline.report.log import ExclusionKind, identity_log, log_text
from digline.report.text import LOCALES, Locale
from digline.wire.log import log_json

TENANT, SUITE = "acme", "qa"


def aggregate(
    name: str = "accuracy",
    score: float = 0.8,
    *,
    status: str = "pass",
    samples: tuple[float, ...] = (),
) -> Verdict:
    interval = (
        {"samples": samples, "sample_min": min(samples), "sample_max": max(samples)}
        if samples
        else {}
    )
    return Verdict(
        score=Score(name=name, score=score, **interval),  # pyright: ignore[reportArgumentType]
        threshold=0.5,
        status=status,  # pyright: ignore[reportArgumentType]
        reason="r",
        assertion_id=f"id-{name}",
    )


def a_run(
    when: str,
    score: float = 0.8,
    *,
    model: str = "m-1",
    commit: str | None = "abc123",
    version: str = "0.16.0",
    config_hash: str = "h",
    cases: tuple[str, ...] = ("c1",),
    suspended: str | None = None,
    canary: bool = False,
    rejudged_from: str | None = None,
    errored: bool = False,
    artifacts: dict[str, str] | None = None,
    judge: str = "j-1",
    samples: tuple[float, ...] = (),
    aggregates: tuple[Verdict, ...] | None = None,
) -> Run:
    from digline.core import Artifact

    results = tuple(
        CaseResult(
            case_id=case,
            verdicts=(
                (
                    Verdict(
                        score=Score(name="contains", score=None),
                        threshold=0.5,
                        status="error",
                        reason="broke",
                        assertion_id="id-c",
                    ),
                )
                if errored
                else ()
            ),
            suspended=suspended if case == cases[0] else None,
            canary=canary and case == cases[0],
        )
        for case in cases
    )
    return Run(
        tenant=TENANT,
        environment="staging",
        suite=SUITE,
        config_hash=config_hash,
        created_at=when,
        git_commit=commit,
        digline_version=version,
        rejudged_from=rejudged_from,
        results=results,
        aggregate=(
            aggregates
            if aggregates is not None
            else (aggregate(score=score, samples=samples),)
        ),
        artifacts={
            path: Artifact(sha=sha, text="x") for path, sha in (artifacts or {}).items()
        },
        target_config=SystemConfig(values={"provider": "fake", "model": model}),
        judge_config=SystemConfig(values={"provider": "fake", "model": judge}),
    )


def read(rows: list[tuple[str, Run]], baseline: tuple[str, Run] | None = None):
    return identity_log(rows, tenant=TENANT, suite=SUITE, baseline=baseline)


def history(*scores: float) -> list[tuple[str, Run]]:
    return [
        (f"k{i}", a_run(f"2026-01-{i + 1:02d}T00:00:00+00:00", score))
        for i, score in enumerate(scores)
    ]


# --------------------------------------------------------------------------- #
# The two that carry the weight
# --------------------------------------------------------------------------- #


def test_the_latest_run_is_never_in_its_own_range() -> None:
    """ADR 0006 §5's asymmetry: a noisy new run must not widen its own excuse.

    The latest score here is the extreme on both counts — far above every other
    run — and the range must not move to accommodate it. A range that contained
    the value it is read against would answer *inside* by construction.
    """
    rows = history(0.71, 0.86, 0.80, 0.99)
    [item] = read(rows).spread

    assert (item.low, item.high) == (0.71, 0.86)
    assert item.latest == 0.99
    assert item.runs == 3, "the latest is excluded from the count as well"


def test_the_inside_clause_is_withheld_and_the_reading_says_so() -> None:
    """Until the floor on N is measured, neither branch may be claimed — and
    the reading states that it is not claiming, rather than printing a range and
    leaving a reader to draw the conclusion it refused to draw."""
    lines = log_text(read(history(0.71, 0.86, 0.80)), locale="en")
    said = "\n".join(lines)

    assert "inside" in said, "the withholding is stated"
    assert "is inside this suite" not in said
    assert "is outside this suite" not in said


def test_no_inside_field_reaches_the_wire() -> None:
    """A boolean here would be read as the verdict the text declines to give."""
    payload = json.dumps(log_json(read(history(0.71, 0.86, 0.80))))
    assert "inside" not in payload
    assert "outside" not in payload


# --------------------------------------------------------------------------- #
# Which runs are comparable (§7.2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("reason", "odd"),
    [
        ("rejudged", {"rejudged_from": "k0"}),
        ("unjudged", {"errored": True}),
        ("config_hash", {"config_hash": "other"}),
        ("population", {"cases": ("c1", "c2")}),
        ("artifacts", {"artifacts": {"prompt.md": "deadbeef"}}),
        ("target_config", {"model": "m-2"}),
        ("judge_config", {"judge": "j-2"}),
    ],
)
def test_a_run_that_is_not_comparable_is_excluded_by_name(
    reason: ExclusionKind, odd: dict[str, object]
) -> None:
    """Counted by reason and printed: a number excluded silently is a number
    nobody can check (ADR 0016 §3). Nothing here refuses the command."""
    rows = history(0.71, 0.86, 0.80)
    rows.insert(0, ("k9", a_run("2025-12-31T00:00:00+00:00", 0.55, **odd)))  # pyright: ignore[reportArgumentType]
    [item] = read(rows).spread

    assert item.excluded.get(reason) == 1, item.excluded
    assert item.runs == 2, "the two comparable runs, the latest not among them"


def test_a_population_that_differs_only_by_a_suspension_is_excluded() -> None:
    """The counted population is the case ids *and* the three kinds of case that
    leave a denominator without being a failure."""
    rows = history(0.71, 0.86, 0.80)
    rows.insert(
        0,
        ("k9", a_run("2025-12-31T00:00:00+00:00", 0.55, suspended="ticket 412")),
    )
    [item] = read(rows).spread

    assert item.excluded.get("population") == 1


def test_a_run_another_model_answered_is_out_of_the_set() -> None:
    """The set stops at the run before what answered changed.

    **Named `target_config` rather than `identity`, and that is the finding.**
    A sighting is *derived* from the configuration — `resolved_model` is a value
    in it — so a run a different model answered differs in the configuration
    too, and §7.2's table checks that row first. The identity row is therefore
    subsumed in all but one corner: two runs whose configurations are equal and
    whose `digline_version` differs, where the absence reads `not_reported` on
    one and `not_recorded` on the other.

    The intent of the row is met either way, and more strictly. What the row
    contributes that nothing else does is the *reporting* half — how many of the
    counted runs identified the answering model — which `unidentified` carries.
    """
    rows = [
        ("k0", a_run("2026-01-01T00:00:00+00:00", 0.55, model="old")),
        ("k1", a_run("2026-01-02T00:00:00+00:00", 0.60, model="old")),
        ("k2", a_run("2026-01-03T00:00:00+00:00", 0.71)),
        ("k3", a_run("2026-01-04T00:00:00+00:00", 0.86)),
        ("k4", a_run("2026-01-05T00:00:00+00:00", 0.80)),
    ]
    [item] = read(rows).spread

    assert item.runs == 2
    assert (item.low, item.high) == (0.71, 0.86)
    assert item.excluded.get("target_config") == 2
    assert "identity" not in item.excluded


def test_nothing_comparable_is_a_reading_with_no_range() -> None:
    """The exclusions still print: that is exactly when a reader needs them."""
    rows = [
        ("k0", a_run("2026-01-01T00:00:00+00:00", 0.55, config_hash="other")),
        ("k1", a_run("2026-01-02T00:00:00+00:00", 0.80)),
    ]
    [item] = read(rows).spread

    assert (item.low, item.high, item.runs) == (None, None, 0)
    assert item.excluded.get("config_hash") == 1
    said = "\n".join(log_text(read(rows), locale="en"))
    assert "no range to read" in said


# --------------------------------------------------------------------------- #
# The guard (§7.5)
# --------------------------------------------------------------------------- #


def test_a_flip_is_silent() -> None:
    """ADR 0006 §6: a flip carries no interval, and printing one invites the
    reader to argue it away."""
    rows = history(0.71, 0.86)
    rows.append(
        (
            "k9",
            a_run(
                "2026-01-09T00:00:00+00:00",
                aggregates=(aggregate(status="fail", score=0.2),),
            ),
        )
    )
    reference = ("kb", a_run("2025-12-01T00:00:00+00:00", 0.76))

    assert read(rows, reference).spread == ()


def test_a_suite_with_no_run_level_check_says_so() -> None:
    """No suite-wide number invented out of the checks."""
    rows = [("k0", a_run("2026-01-01T00:00:00+00:00", aggregates=()))]
    log = read(rows)

    assert log.spread == ()
    assert "nothing to read across runs" in "\n".join(log_text(log, locale="en"))


# --------------------------------------------------------------------------- #
# The two intervals, which must not be read as one (§7.3)
# --------------------------------------------------------------------------- #


def test_the_within_run_interval_is_printed_and_labelled_apart() -> None:
    """The stored spread reads the folded aggregate; the within-run interval is
    the aggregate re-evaluated per sample index. Different quantities, so the
    reading names each and never sets them against each other."""
    rows = history(0.71, 0.86)
    rows.append(("k9", a_run("2026-01-09T00:00:00+00:00", 0.80, samples=(0.6, 0.95))))
    [item] = read(rows).spread

    assert (item.within_low, item.within_high) == (0.6, 0.95)
    said = "\n".join(log_text(read(rows), locale="en"))
    assert "not comparable with the range above" in said


# --------------------------------------------------------------------------- #
# What is reported rather than held (§7.2's last rows)
# --------------------------------------------------------------------------- #


def test_the_commits_are_counted_and_never_a_constraint() -> None:
    """`git_commit` is commonly `-dirty`; excluding on it collapses N to one."""
    rows = [
        ("k0", a_run("2026-01-01T00:00:00+00:00", 0.71, commit="aaa")),
        ("k1", a_run("2026-01-02T00:00:00+00:00", 0.86, commit="bbb")),
        ("k2", a_run("2026-01-03T00:00:00+00:00", 0.80, commit="ccc")),
    ]
    [item] = read(rows).spread

    assert item.runs == 2, "no run was excluded for its commit"
    assert item.commits == 2


def test_the_environment_never_splits_the_set() -> None:
    """Decision 8: the environment is inside the perimeter and out of every
    constraint."""
    import dataclasses

    rows = history(0.71, 0.86, 0.80)
    elsewhere = dataclasses.replace(
        a_run("2025-12-31T00:00:00+00:00", 0.75), environment="production"
    )
    rows.insert(0, ("k9", elsewhere))

    [item] = read(rows).spread
    assert item.runs == 3, "the production run counts with the staging ones"
    assert not item.excluded


def test_the_runs_that_did_not_identify_the_model_are_counted() -> None:
    """A roll inside the set is absorbed into the spread, and where the provider
    does not name the model the canary is the only instrument that sees one. So
    the count is said."""
    [item] = read(history(0.71, 0.86, 0.80)).spread

    assert item.unidentified == 2
    assert "did not identify the answering model" in "\n".join(
        log_text(read(history(0.71, 0.86, 0.80)), locale="en")
    )


# --------------------------------------------------------------------------- #
# The surfaces
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("locale", LOCALES)
def test_the_reading_exists_in_every_locale(locale: Locale) -> None:
    """A document with a recipient who did not choose English."""
    rows = history(0.71, 0.86, 0.80)
    lines = log_text(
        read(rows, ("kb", a_run("2025-12-01T00:00:00+00:00", 0.76))), locale=locale
    )

    assert any("0.710000" in line and "0.860000" in line for line in lines)


def test_the_wire_carries_every_number_the_sentence_uses() -> None:
    """One rendering of the truth: a consumer reading `--json` can rebuild the
    sentence, exclusions included, without parsing prose."""
    rows = history(0.71, 0.86, 0.80)
    rows.insert(0, ("k9", a_run("2025-12-31T00:00:00+00:00", 0.55, config_hash="x")))
    payload = log_json(read(rows, ("kb", a_run("2025-12-01T00:00:00+00:00", 0.76))))
    [row] = cast("list[dict[str, Any]]", payload["spread"])

    assert row["name"] == "accuracy"
    assert row["low"] == 0.71 and row["high"] == 0.86
    assert row["runs"] == 2
    assert row["excluded"] == {"config_hash": 1}
    assert row["reference"] == 0.76
    assert "commits" in row and "versions" in row


def test_the_output_version_did_not_move() -> None:
    """An added key beside `spans` and `rolls`: a consumer that ignores it
    parses the bytes it parsed before."""
    from digline.wire import OUTPUT_VERSION

    payload = log_json(read(history(0.71, 0.86)))
    assert payload["output_version"] == OUTPUT_VERSION
    assert "spread" in payload
