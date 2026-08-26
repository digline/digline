"""Comparison between a run and the recorded baseline.

A pure function, no I/O, callable without a driver. A threshold check only
catches "below 0.7"; this catches "was 0.91, now 0.78, still above the
threshold". See `docs/adr/0001-verdict-not-score.md`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from digline.core.run import Run
from digline.core.types import Verdict

__all__ = ["AssertionDelta", "Comparison", "Outcome", "Scope", "compare"]

type Outcome = Literal[
    "regressed", "improved", "unchanged", "new", "missing", "errored"
]

type Scope = Literal["case", "run"]

type _Key = tuple[Scope, str, str, int]


@dataclass(frozen=True, slots=True)
class AssertionDelta:
    """The comparison outcome for one assertion on one case."""

    case_id: str
    assertion: str
    outcome: Outcome
    #: `"run"` for a verdict about the whole run — precision, recall — which
    #: belongs to no case and carries an empty `case_id`.
    scope: Scope
    current: Verdict | None
    baseline: Verdict | None
    delta: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class Comparison:
    """The full comparison. `deltas` is ordered by (case, assertion) so two
    equivalent comparisons read identically."""

    tenant: str
    suite: str
    config_changed: bool
    #: Where each side ran. Reported, never constrained: comparing staging
    #: against a production baseline is the pre-release check, not a mistake.
    #: A reader who needs to know they are looking across environments can; a
    #: caller who does not care is not stopped.
    environment: str = ""
    baseline_environment: str = ""
    deltas: Sequence[AssertionDelta] = ()

    def of(self, *outcomes: Outcome) -> Sequence[AssertionDelta]:
        wanted = frozenset(outcomes)
        return tuple(d for d in self.deltas if d.outcome in wanted)

    @property
    def regressed(self) -> Sequence[AssertionDelta]:
        return self.of("regressed")

    @property
    def errored(self) -> Sequence[AssertionDelta]:
        return self.of("errored")

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressed)

    @property
    def counts(self) -> dict[Outcome, int]:
        tally: Counter[Outcome] = Counter(d.outcome for d in self.deltas)
        return dict(tally)


def _index(run: Run) -> dict[_Key, Verdict]:
    """Index by (case, assertion identity, occurrence).

    Keying on `Verdict.assertion_id` rather than on the name is what keeps the
    pairing honest. Position is not identity: with two `contains` on one case,
    pairing by order would turn a reordering of the suite into a fabricated
    `regressed` plus a fabricated `improved`, and deleting the first of three
    would report the third as `missing` while silently comparing the second
    against the first's baseline.

    The occurrence counter survives, but only as a tiebreaker between verdicts
    that share an identity — the same assertion, identically configured, applied
    twice to the same case. There, order is the only thing left to pair on, and
    pairing by order is correct because the two are interchangeable.
    """
    out: dict[_Key, Verdict] = {}
    for case in run.results:
        seen: Counter[str] = Counter()
        for verdict in case.verdicts:
            key = verdict.assertion_id
            out[("case", case.case_id, key, seen[key])] = verdict
            seen[key] += 1

    # Aggregates belong to no case, so they carry an empty `case_id` and are
    # kept in a scope of their own rather than filed under a sentinel name that
    # would one day collide with a real one.
    seen_run: Counter[str] = Counter()
    for verdict in run.aggregate:
        key = verdict.assertion_id
        out[("run", "", key, seen_run[key])] = verdict
        seen_run[key] += 1
    return out


def compare(run: Run, baseline: Run) -> Comparison:
    """Compare `run` against `baseline`.

    Rule order is deliberately non-commutative:

    1. present on one side only -> `new` / `missing`
    2. either side in error -> `errored`
    3. the outcome flipped (pass <-> fail) -> `regressed` / `improved`,
       **regardless of tolerance**: a flipped outcome is never noise
    4. otherwise a numeric comparison against the tolerance

    Rule 2 upholds the constraint that `error` is neither green nor a
    regression: an error reported as a regression would fail a PR for the wrong
    reason, and one reported as `unchanged` would hide a suite that stopped
    working.

    The tolerance used is the current run's. Comparing two runs with different
    tolerances is legitimate and is in fact the interesting case — seeing the
    effect of a configuration change — but `promote_baseline` will refuse to
    promote the result until the configuration matches again.

    Comparing across tenants raises. Two perimeters produce numbers on the same
    scale, so the mistake is arithmetically valid and factually nonsense — one
    end customer's results read as another's history.

    Comparing across *environments* does not raise, and must not: running the
    staging suite against the production baseline is the pre-release check the
    whole product exists for. Both environments are reported on the
    `Comparison` so a reader can see what was held against what.

    A redacted run compares against a complete baseline: everything read here —
    score, status, threshold, tolerance, identity — survives redaction. The
    `Comparison` returned, however, holds the verdicts it was given, so it
    inherits the payload of its inputs.
    """
    if run.tenant != baseline.tenant:
        raise ValueError(
            f"cannot compare across tenants: run is {run.tenant!r}, "
            f"baseline is {baseline.tenant!r}"
        )
    current, previous = _index(run), _index(baseline)
    deltas: list[AssertionDelta] = []

    for key in sorted(current.keys() | previous.keys()):
        scope, case_id, _identity, _ = key
        now, before = current.get(key), previous.get(key)
        # The key carries identity; the delta carries the readable name.
        named = now if now is not None else before
        assert named is not None
        assertion = named.score.name

        if before is None:
            assert now is not None
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "new",
                    scope,
                    now,
                    None,
                    None,
                    "absent from the baseline",
                )
            )
            continue
        if now is None:
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "missing",
                    scope,
                    None,
                    before,
                    None,
                    "present in the baseline but not in this run",
                )
            )
            continue

        if now.status == "error" or before.status == "error":
            side = "in this run" if now.status == "error" else "in the baseline"
            culprit = now if now.status == "error" else before
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "errored",
                    scope,
                    now,
                    before,
                    None,
                    f"assertion errored {side}: {culprit.reason}",
                )
            )
            continue

        # Past this point both statuses are pass or fail, so both scores are
        # numeric: Verdict.__post_init__ guarantees it.
        assert now.score.score is not None and before.score.score is not None
        delta = now.score.score - before.score.score
        was, is_now = f"{before.score.score:.6f}", f"{now.score.score:.6f}"

        if now.status != before.status:
            outcome: Outcome = "regressed" if before.status == "pass" else "improved"
            # A flip caused by a moved threshold reads exactly like a flip
            # caused by a worse model. Saying so is the difference between a
            # reviewer blaming the prompt and a reviewer checking the config.
            if now.threshold != before.threshold:
                why = (
                    f"outcome flipped from '{before.status}' to '{now.status}', "
                    f"but the threshold moved from {before.threshold:.6f} to "
                    f"{now.threshold:.6f} — the score went from {was} to {is_now}"
                )
            else:
                why = f"outcome flipped from '{before.status}' to '{now.status}'"
            deltas.append(
                AssertionDelta(
                    case_id, assertion, outcome, scope, now, before, delta, why
                )
            )
            continue

        if abs(delta) <= now.tolerance:
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "unchanged",
                    scope,
                    now,
                    before,
                    delta,
                    f"delta {delta:+.6f} within tolerance {now.tolerance:.6f}",
                )
            )
        elif delta < 0:
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "regressed",
                    scope,
                    now,
                    before,
                    delta,
                    f"score dropped from {was} to {is_now}",
                )
            )
        else:
            deltas.append(
                AssertionDelta(
                    case_id,
                    assertion,
                    "improved",
                    scope,
                    now,
                    before,
                    delta,
                    f"score rose from {was} to {is_now}",
                )
            )

    return Comparison(
        tenant=run.tenant,
        environment=run.environment,
        baseline_environment=baseline.environment,
        suite=run.suite,
        config_changed=run.config_hash != baseline.config_hash,
        deltas=tuple(deltas),
    )
