"""What `explain` says to a program: the fact list, and no prose.

The other rendering of `digline.report.explain`'s list. The prose is one render
of it and this is the other; neither is the source, which is what stops a
terminal and a pipeline from coming to describe one run differently (ADR 0012
§3).

**No sentence crosses here.** `compare_json` ships `Headline.sentence` because a
gate and a customer's document must never word one run two ways, so the wire is
where that single wording lives. A reading's prose is derivable from the list
by construction, so shipping it would ship a derived value and invite a consumer
to parse English with the typed facts beside it.

**And no reason crosses here, because none exists.** The types in
`report/explain.py` have no field for one — that is ADR 0012 §4, and it is why
this module needs no filter and `tests/test_wire_boundary.py` has nothing to
catch on this surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import assert_never

from digline.core import (
    AgreementReading,
    AgreementTally,
    RubricComparison,
    Run,
    index_verdicts,
    key_of,
)
from digline.report.explain import CheckFact, Fact, SettingFact, TallyFact
from digline.wire.compare import before_interval_json, shape_json
from digline.wire.contract import OUTPUT_VERSION
from digline.wire.text import neutralised

__all__ = ["agreement_json", "explain_json", "fact_json"]


def fact_json(
    fact: Fact, *, before_interval: Mapping[str, object] | None = None
) -> dict[str, object]:
    """One fact, as a program reads it.

    `before_interval` is the range the reference's samples spanned for a
    check, which a fact does not carry: `explain_json` reads it off the
    reference and hands it in. `null` where it is not passed.

    `about` before `kind`, and both are emitted: the three shapes have kinds of
    their own and two of them share the word `within_noise`, so a consumer
    discriminates on `about` first and then on `kind`. Deriving the shape from
    which keys happen to be present would ask a consumer to know a convention
    instead of reading a field.
    """
    match fact:
        case CheckFact():
            return {
                "about": "check",
                "kind": fact.kind,
                "scope": fact.scope,
                "case_id": fact.case_id,
                "assertion": fact.assertion,
                "assertion_id": fact.assertion_id,
                "before": fact.before,
                "after": fact.after,
                "delta": fact.delta,
                "threshold": fact.threshold,
                # The interval flattened rather than nested, like `delta_json`'s:
                # a pipeline that already reads `noise_min` off a comparison
                # reads it the same way here.
                "noise_min": fact.noise.low,
                "noise_max": fact.noise.high,
                "noise_samples": fact.noise.count,
                # The inputs of a floor from the mean, as on `delta_json`, and
                # whose interval this is: the reference's floor in a
                # comparison, or the samples this run took, read alone, which
                # is not a floor at all. (ADR 0050, the fourth item)
                "noise_width": fact.noise.width,
                "noise_sd": fact.noise.sd,
                "noise_judged": list(fact.noise.judged),
                "noise_source": fact.noise_source,
                # The range the reference's samples spanned, as on
                # `delta_json` and under the same name. An added key. (#1)
                "before_interval": (
                    None if before_interval is None else dict(before_interval)
                ),
                # An added key, beside the kind rather than inside it: `kind`
                # keeps the six values a consumer already matches on, and a
                # check whose two sides counted different cases is now
                # distinguishable from one that moved. The two `considered`
                # numbers stay off the wire — they are on the row for the
                # sentence that states them, and a program has the flag and
                # `compare --json full` beside it.
                # (the delta-pass over 0.15.1)
                "denominator_moved": fact.denominator_moved,
                # Only on a contradiction, so every other check is byte for
                # byte what it was: what the person said. (ADR 0059 §1)
                **({} if fact.good is None else {"good": fact.good}),
            }
        case SettingFact():
            setting: dict[str, object] = {
                "about": "setting",
                "kind": fact.kind,
                "name": fact.name,
                # `None` where there was nothing to compare against, which is
                # not a sixth outcome: it is the absence of a comparison.
                "outcome": fact.outcome,
                "before": fact.before,
                "after": fact.after,
                "withheld": fact.withheld,
                "added": fact.added,
                "removed": fact.removed,
            }
            # Only on a rule that has one, so every configuration, judge and
            # artifact fact is byte for byte what it was — `shape`'s rule, one
            # shape over. An empty direction is *no verb*, which is a different
            # statement from *unchanged*, and a key that carried `""` on every
            # fact in the list would invite a reader to read it as the latter.
            # (ADR 0028 §4, §8)
            if fact.direction:
                setting["direction"] = fact.direction
            if fact.expansion:
                setting["expansion"] = fact.expansion
            return setting
        case TallyFact():
            payload: dict[str, object] = {
                "about": "run",
                "kind": fact.kind,
                "count": fact.count,
                "state": fact.state,
            }
            # Only on `shape`, so every other fact is byte for byte what it was.
            if fact.shape is not None:
                payload["shape"] = shape_json(fact.shape)
            # Only where a band was left, for the same reason: each case beside
            # the count, what the report's section shows. (ADR 0024 §4.5)
            if fact.bands:
                payload["bands"] = [
                    {
                        "case_id": item.case_id,
                        "check": item.check,
                        "score": item.score,
                        "low": item.low,
                        "high": item.high,
                        "side": item.side,
                    }
                    for item in fact.bands
                ]
            # And where the judge contradicted a person: each answer, its check
            # and the direction, beside the count. (ADR 0059 §1)
            if fact.contradictions:
                payload["contradictions"] = [
                    {
                        "case_id": item.case_id,
                        "check": item.check,
                        "direction": item.direction,
                    }
                    for item in fact.contradictions
                ]
            # And where a judged verdict is not firm: each check on its case,
            # why, and the margin with where it came from. Only on the
            # `uncertain` tally, so every other fact is byte for byte what it
            # was. (P-1685)
            if fact.uncertain:
                payload["uncertain"] = [
                    {
                        "case_id": item.case_id,
                        "check": item.check,
                        "score": item.score,
                        "threshold": item.threshold,
                        "margin": item.margin,
                        "margin_declared": item.declared,
                        "split": item.split,
                        "near": item.near,
                        "agreement": item.agreement,
                        "errored_samples": item.errored,
                    }
                    for item in fact.uncertain
                ]
            # And the agreement between the judge and the person, per check
            # and role. Only on the `agreement` tally. A held-out answer is
            # counted and never named: its composite disagreements are a
            # count beside the held-in ones. (ADR 0067 §1 (c), (e), §5)
            if fact.agreement is not None:
                payload["agreement"] = agreement_json(fact.agreement)
            # And a re-judge against the run it was made from. Only on the
            # `rubrics` tally. (ADR 0067 §1 (d))
            if fact.rubrics is not None:
                payload["rubrics"] = rubrics_json(fact.rubrics)
            return payload
    assert_never(fact)


def agreement_json(reading: AgreementReading) -> dict[str, object]:
    """The agreement reading, for a program. Counts, check names and
    identities, and the held-in composite disagreements by case: no reason,
    and no held-out case. (ADR 0067 §1 (c), (e), §5; ADR 0012 §4)"""
    return {
        "held_in": reading.held_in,
        "held_out": reading.held_out,
        "stability_measured": reading.stability_measured,
        "checks": [
            {
                "check": row.check,
                "assertion_id": row.assertion_id,
                "held_out": row.held_out,
                "blind": _tally_json(row.blind),
                "after": _tally_json(row.after),
                "revised": row.revised,
                "unjudged": row.unjudged,
            }
            for row in reading.rows
        ],
        "composites": [
            {
                "case_id": item.case_id,
                "composite": item.composite,
                "composite_passed": item.composite_passed,
                "failed": list(item.failed),
            }
            for item in reading.mismatches
            if not item.held_out
        ],
        "composites_held_out": sum(1 for item in reading.mismatches if item.held_out),
    }


def rubrics_json(comparison: RubricComparison) -> dict[str, object]:
    """A re-judge against the run it was made from, for a program: the source
    key, the checks paired and not, by name, identity and type, and the
    held-in answers that changed verdict by case. No reason crosses, and a
    held-out answer is counted, never named. (ADR 0067 §1 (d), (e))"""
    return {
        "source": comparison.source,
        "read": comparison.read,
        "answers": comparison.answers,
        "paired": [
            {
                "check": check.check,
                "check_type": check.check_type,
                "before_id": check.before_id,
                "after_id": check.after_id,
                "changed": check.changed,
            }
            for check in comparison.paired
        ],
        "unpaired": [
            {
                "check": item.check,
                "why": item.why,
                "before": item.before,
                "after": item.after,
            }
            for item in comparison.unpaired
        ],
        "changes": [
            {
                "case_id": change.case_id,
                "check": change.check,
                "before": change.before,
                "after": change.after,
                "toward": change.toward,
            }
            for change in comparison.changes
        ],
        "held_out_changes": comparison.held_out_changes,
    }


def _tally_json(tally: AgreementTally) -> dict[str, object]:
    return {
        "agree": tally.agree,
        "passed_no": tally.passed_no,
        "failed_yes": tally.failed_yes,
    }


def explain_json(
    facts: Sequence[Fact],
    *,
    reading: str,
    exit_code: int,
    note: str = "",
    run: Run | None = None,
    baseline: Run | None = None,
) -> dict[str, object]:
    """The whole reading, for a program.

    `reading` says which of the two documents this is — `"comparison"` or
    `"run"` — rather than leaving a consumer to infer it from which kinds
    turned up. A run whose comparison found nothing and a run
    with no reference at all produce different readings, and the difference
    must not be something you deduce from an absence.

    `note` is what resolving the run stepped over, `Resolved.note`, as on
    `compare --json`. An added key. (#433)

    `run_key` and `baseline_key` name the two documents the reading was made
    from, derived from them as `compare_json` derives its own: the run always,
    the reference only where there was one to hold the run against, which is
    the `"comparison"` scope. Each is absent where its document was not passed,
    which is a caller written before them. Added keys. (#448)
    """
    spans = _reference_spans(baseline)
    payload: dict[str, object] = {
        "output_version": OUTPUT_VERSION,
        "reading": reading,
        # The same number the process exits with, for the same reason it is on
        # `compare --json`: over MCP there is no process to exit, and the two
        # surfaces must not answer differently. (ADR 0011 §4)
        "exit_code": exit_code,
        "facts": [
            fact_json(fact, before_interval=_before_interval(fact, spans))
            for fact in facts
        ],
        "note": note,
    }
    if run is not None:
        payload["run_key"] = key_of(run.created_at, run.config_hash)
    if baseline is not None:
        payload["baseline_key"] = key_of(baseline.created_at, baseline.config_hash)
    return neutralised(payload)


type _Spans = Mapping[tuple[str, str, str], Sequence[dict[str, object] | None]]


def _reference_spans(baseline: Run | None) -> _Spans:
    """Every check of the reference, by scope, case and identity, with the
    range its samples spanned. A list, because one case can hold the same
    check twice."""
    spans: dict[tuple[str, str, str], list[dict[str, object] | None]] = {}
    if baseline is None:
        return spans
    for (scope, case_id, identity, _), verdict in index_verdicts(baseline).items():
        spans.setdefault((scope, case_id, identity), []).append(
            before_interval_json(verdict)
        )
    return spans


def _before_interval(fact: Fact, spans: _Spans) -> dict[str, object] | None:
    """The reference's range for one check fact, or `None`.

    `compare()` pairs two verdicts of the same check on one case by their
    order, and a fact carries no order. Where the reference's verdicts of such
    twins spanned the same range that range is the answer; where they differ
    the reading cannot say which is which, and says neither.
    """
    if not isinstance(fact, CheckFact):
        return None
    found = spans.get((fact.scope, fact.case_id, fact.assertion_id), ())
    if not found or any(span != found[0] for span in found):
        return None
    return found[0]
