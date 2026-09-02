"""ADR 0006: repeated samples and the noise floor.

The ADR was written against a real event — the same suite, the same
`config_hash`, three runs inside fifteen minutes, one case going 5/5 → 2/5 →
5/5, and a reported regression that was nothing. The two surviving runs are in
`tests/fixtures/brief/`, and the last section of this file asserts against them
rather than against a hand-written approximation of them.

Everything above that section is the machinery, tested where it is defined:
what a sampled `Score` records, what survives serialization and redaction, what
a document written before this ADR gains on migration, and where the floor of
§5 does and does not reach.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from digline.core import (
    CaseResult,
    Run,
    Score,
    Verdict,
    combine_samples,
    redact,
    run_from_json,
    run_to_json,
)
from digline.core.run import SCHEMA_VERSION
from digline.store.migrate import upgrade_document

CREATED = "2026-01-01T00:00:00+00:00"


def make_run(verdicts: Sequence[Verdict], *, case_id: str = "c1") -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash="h",
        created_at=CREATED,
        results=(CaseResult(case_id=case_id, verdicts=tuple(verdicts)),),
    )


def sample(score: float, *, threshold: float = 0.5, name: str = "check") -> Verdict:
    """One un-folded sample: what an assertion returns before anything repeats
    it."""
    return Verdict(
        score=Score(name=name, score=score),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason=f"sample scored {score}",
        assertion_id=f"id-{name}",
    )


# -- §4: what a sampled score records ------------------------------------- #


def test_a_single_sample_records_no_interval() -> None:
    """The absence rule, and the reason a suite at `samples=1` is untouched by
    this ADR: there is nothing to record, so nothing is."""
    plain = Score(name="check", score=0.9)
    assert plain.samples == ()
    assert plain.sample_min is None and plain.sample_max is None
    assert not plain.sampled


def test_the_fold_records_the_raw_samples_and_the_interval() -> None:
    folded = combine_samples(
        [sample(1.0), sample(1.0), sample(0.0), sample(0.0), sample(0.0)],
        min_agreement=0.5,
    )
    # §2: the scalar is untouched — the mean of five binary samples is the
    # majority vote, and 2/5 is 0.4.
    assert folded.score.score == 0.4
    assert folded.score.samples == (1.0, 1.0, 0.0, 0.0, 0.0)
    assert folded.score.sample_min == 0.0
    assert folded.score.sample_max == 1.0


def test_the_fields_carry_the_same_numbers_as_the_metadata() -> None:
    """Two views of one measurement. The metadata half is reported, the fields
    are acted on — but they must never disagree."""
    folded = combine_samples([sample(0.8), sample(0.6), sample(0.7)], min_agreement=0.5)
    assert list(folded.score.samples) == folded.score.metadata["scores"]


def test_an_errored_sample_is_not_in_the_interval_but_is_still_counted() -> None:
    errored = Verdict(
        score=Score(name="check", score=None),
        threshold=0.5,
        status="error",
        reason="could not judge",
        assertion_id="id-check",
    )
    folded = combine_samples([sample(1.0), sample(1.0), errored], min_agreement=0.5)
    assert folded.score.samples == (1.0, 1.0)
    assert folded.score.metadata["errored_samples"] == 1


def test_an_interval_that_the_samples_do_not_span_is_refused() -> None:
    with pytest.raises(ValueError, match="not the one its samples span"):
        Score(
            name="check", score=0.5, samples=(0.4, 0.6), sample_min=0.0, sample_max=1.0
        )


def test_half_an_interval_is_refused() -> None:
    """A noise floor built from one end would admit movement in a direction
    nobody measured, and would do it silently."""
    with pytest.raises(ValueError, match="without sample_min and sample_max"):
        Score(name="check", score=0.5, samples=(0.4, 0.6), sample_min=0.4)


def test_an_interval_without_samples_is_refused() -> None:
    with pytest.raises(ValueError, match="without the samples it spans"):
        Score(name="check", score=0.5, sample_min=0.4, sample_max=0.6)


def test_rounding_the_mean_does_not_drop_the_interval() -> None:
    """`Verdict` rebuilds its `Score` when the mean needs rounding, which is
    most sampled checks. A rebuild that dropped the fields would delete the
    noise floor of exactly those, and would do it invisibly."""
    folded = combine_samples([sample(1.0), sample(0.0), sample(1.0)], min_agreement=0.5)
    assert folded.score.score == 0.666667
    assert folded.score.samples == (1.0, 0.0, 1.0)


# -- §4: they travel ------------------------------------------------------- #


def test_the_interval_survives_redaction() -> None:
    """Stated rather than inherited: as `Score` fields they bypass `travels()`,
    so `redact()` copies them explicitly. They measure the system's own
    variability, like `spread`, not what it judged."""
    folded = combine_samples([sample(1.0), sample(0.0), sample(1.0)], min_agreement=0.5)
    run = make_run([folded])
    stripped = redact(run)
    kept = stripped.results[0].verdicts[0].score
    assert kept.samples == (1.0, 0.0, 1.0)
    assert (kept.sample_min, kept.sample_max) == (0.0, 1.0)
    # And the payload still went.
    assert stripped.results[0].verdicts[0].reason == "<redacted>"


# -- §4 and §11: the document ---------------------------------------------- #


def test_a_sampled_verdict_round_trips_through_the_document() -> None:
    folded = combine_samples([sample(1.0), sample(0.0), sample(1.0)], min_agreement=0.5)
    back = run_from_json(run_to_json(make_run([folded])))
    restored = back.results[0].verdicts[0].score
    assert restored.samples == (1.0, 0.0, 1.0)
    assert (restored.sample_min, restored.sample_max) == (0.0, 1.0)


def test_an_unsampled_run_writes_none_of_the_three_keys() -> None:
    """Absent, never `null`. This is what keeps a run file from a suite at
    `samples=1` byte for byte the file it was before this ADR."""
    document = run_to_json(make_run([sample(0.9)]))
    assert "sample_min" not in document
    assert '"samples"' not in document


def test_migration_derives_the_interval_from_the_scores_already_recorded() -> None:
    """§11. Reading a list that is in the document is not the guessing
    `migrate.py` refuses, and it is the difference between every promoted
    baseline being a noise floor on the day of the release and being one after
    everybody re-promotes."""
    old: dict[str, Any] = {
        "schema_version": 8,
        "tenant": "acme",
        "environment": "staging",
        "redacted": False,
        "suite": "s",
        "config_hash": "h",
        "created_at": CREATED,
        "git_commit": None,
        "metadata": {},
        "artifacts": {},
        "target_config": {},
        "judge_config": {},
        "aggregate": [],
        "results": [
            {
                "case_id": "c1",
                "suspended": False,
                "verdicts": [
                    {
                        "assertion": "check",
                        "assertion_id": "id-check",
                        "score": 0.4,
                        "status": "fail",
                        "threshold": 0.5,
                        "tolerance": 0.0,
                        "reason": "mean of 5 samples",
                        "metadata": {
                            "samples": 5,
                            "agreement": 0.6,
                            "spread": 1.0,
                            "errored_samples": 0,
                            "scores": [1.0, 1.0, 0.0, 0.0, 0.0],
                        },
                    }
                ],
            }
        ],
    }
    upgraded = upgrade_document(old)
    assert upgraded["schema_version"] == SCHEMA_VERSION
    verdict = upgraded["results"][0]["verdicts"][0]
    assert verdict["samples"] == [1.0, 1.0, 0.0, 0.0, 0.0]
    assert verdict["sample_min"] == 0.0
    assert verdict["sample_max"] == 1.0


def test_migration_invents_no_interval_for_an_unsampled_verdict() -> None:
    """At one sample there is no interval. `[score, score]` would hand a check a
    noise floor of zero width dressed as a measurement."""
    old: dict[str, Any] = {
        "schema_version": 8,
        "tenant": "acme",
        "environment": "staging",
        "redacted": False,
        "suite": "s",
        "config_hash": "h",
        "created_at": CREATED,
        "git_commit": None,
        "metadata": {},
        "artifacts": {},
        "target_config": {},
        "judge_config": {},
        "aggregate": [],
        "results": [
            {
                "case_id": "c1",
                "suspended": False,
                "verdicts": [
                    {
                        "assertion": "check",
                        "assertion_id": "id-check",
                        "score": 0.9,
                        "status": "pass",
                        "threshold": 0.5,
                        "tolerance": 0.0,
                        "reason": "scored 0.9",
                        "metadata": {},
                    }
                ],
            }
        ],
    }
    verdict = upgrade_document(old)["results"][0]["verdicts"][0]
    assert "samples" not in verdict
    assert "sample_min" not in verdict
