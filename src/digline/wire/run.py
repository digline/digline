"""What the run tools say to a program.

`run_json` is what `digline run --json` prints and what the MCP `run` tool
returns: a run was written, and here is how to name it. It carries no verdict —
it reports that a run happened, not whether it was any good.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from digline.core import Disclosure, Run, RunUsage, SystemConfig, Verdict
from digline.run import CallPlan
from digline.store import Listing, RunRef
from digline.wire.contract import OUTPUT_VERSION
from digline.wire.text import neutralised

__all__ = ["run_document", "run_json", "runs_json", "usage_lines"]


def usage_lines(usage: RunUsage | None) -> list[str]:
    """The bill, one line per side, for a terminal.

    Here and not in the CLI because both front ends say it, and a sentence
    written twice is a sentence that drifts — the reason `digline.wire` exists.
    Pure, like everything in this package: no clock, no I/O.

    English and not localised: this is *terminal* output, which defaults to `en`
    like every other line the CLI prints, not a document with a recipient who
    did not choose the language.

    **The `counted` clause appears only when the totals are partial.** A
    parenthesis on every run is one a reader learns to skip, taking the rare one
    with it — and the rare one is the whole point, because it says the figure
    beside it is not the whole bill.

    `None` — a document that recorded no bill — produces no lines at all rather
    than a row of zeros, which would be a claim it never made.
    """
    if usage is None:
        return []
    lines: list[str] = []
    for side, line in (("target", usage.target), ("judge", usage.judge)):
        if not line.calls:
            continue
        counts = (
            f"{line.tokens.input_tokens} in / {line.tokens.output_tokens} out"
            if line.counted
            else "no counts reported"
        )
        partial = f" (counted {line.counted} of {line.calls})" if line.partial else ""
        lines.append(
            f"{side}: {line.calls} call{'s' if line.calls != 1 else ''}, "
            f"{counts}, {line.spent_usd:.6f} USD{partial}"
        )
    return lines


def run_json(
    ref: RunRef,
    plan: CallPlan,
    *,
    resumed: bool = False,
    judge_reading: str | None = None,
    usage: RunUsage | None = None,
) -> dict[str, object]:
    """The written run, named, with what it cost to make.

    `sentence` is `CallPlan.sentence()` — the line the CLI prints to stderr
    before the first call. Over MCP there is no stderr, and `AGENTS.md` §7 asks
    an agent to say what a hunt cost; the acknowledged integer covers the calls
    to the target only, so the sentence is what carries the judge repeats a
    caller has to include when it reports the spend. (ADR 0011 §2, §4)

    `resumed` and `reused` are facts about *this launch*, not about the run:
    the stored document carries no marker for having been resumed, because a
    resumed run asserts nothing untrue of either of its legs (ADR 0017 §10).
    They are here because a pipeline that launched the resume is entitled to
    know what its own call did, at the one moment the fact exists.
    """
    payload: dict[str, object] = {
        "output_version": OUTPUT_VERSION,
        "key": ref.key,
        "tenant": ref.tenant,
        "suite": ref.suite,
        "sentence": plan.sentence(),
        "resumed": resumed,
        "reused": plan.reused,
    }
    # Present only where a replay measured the judge's range: the sentence that
    # never states the range without the calibration beside it, for a pipeline
    # that reads this instead of stderr. An added key, and absent everywhere
    # else, so no existing consumer sees a byte change. (ADR 0024 §5.4)
    if judge_reading is not None:
        payload["judge_reading"] = judge_reading
    # What the run consumed, for the pipeline that reads this instead of
    # stderr — the same two lines, structured. Absent on a document that
    # recorded none, which is never a run that consumed nothing. (ADR 0025 §9)
    if usage is not None:
        payload["usage"] = _usage_document(usage)
    return neutralised(payload)


def runs_json(
    rows: Sequence[tuple[str, Run]],
    *,
    tenant: str,
    suite: str,
    baseline_key: str | None,
    listing: Listing,
) -> dict[str, object]:
    """Every stored run of a suite, newest first, with the baseline marked.

    The list `AGENTS.md` §2 is about: promote from the middle of several, never
    from the first one that goes green. A caller choosing a run needs to see the
    ones it is choosing between.

    Sorted on `created_at`, the recorded fact, and not on the filename that
    encodes it — the same rule `resolve_key` follows for `latest`.

    **What was left out is a field and not an aside.** In the CLI the note goes
    to stderr so it cannot break a pipeline reading stdout; over MCP there is no
    stderr, and a listing that quietly dropped half a suite's history would read
    exactly like a suite with a shorter history. `AGENTS.md` §8 tells a reader
    to propose a migration, and these are the fields it proposes from.

    `unreadable` is a **count and not a list of paths**: a path under
    `.digline/` is this machine's fact, and the count is what a caller needs in
    order to say something true. (ADR 0011 §4)
    """
    ordered = sorted(rows, key=lambda row: row[1].created_at, reverse=True)
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenant": tenant,
            "suite": suite,
            "baseline_key": baseline_key,
            "runs": [
                {
                    "key": key,
                    "created_at": run.created_at,
                    "environment": run.environment,
                    "git_commit": run.git_commit,
                    "cases": len(run.results),
                    # Which digline wrote each one. A caller choosing between runs
                    # can see that one of them came from a release it does not have,
                    # which is the same fact the CLI prints on stderr. (ADR 0014 §3)
                    "digline_version": run.digline_version,
                    # The column `digline view`'s grid already shows, so the machine
                    # surface is no thinner than the human one. Fixed decision 9's
                    # crossing list and nothing more: no `metadata`, so no
                    # `Disclosure` is needed here — the counts are one `get_run`
                    # away — and no `reason`, because none crosses. (ADR 0020 §7)
                    "aggregate": [
                        {
                            "name": verdict.score.name,
                            "assertion_id": verdict.assertion_id,
                            "status": verdict.status,
                            "score": verdict.score.score,
                            "threshold": verdict.threshold,
                            "tolerance": verdict.tolerance,
                        }
                        for verdict in run.aggregate
                    ],
                }
                for key, run in ordered
            ],
            "note": listing.note(),
            # What to do about what was left out, in the direction the versions say
            # — a list, because a store can owe both sentences at once. Beside the
            # note rather than inside it: the note is what happened, this is what
            # follows from it. (ADR 0014 §5)
            "advice": list(listing.advice()),
            "skipped": {
                str(version): n for version, n in sorted(listing.skipped.items())
            },
            "unreadable": len(listing.unreadable),
        }
    )


def _verdict_document(verdict: Verdict, disclosure: Disclosure) -> dict[str, object]:
    """What a verdict *is*, and nothing it merely carried.

    Fixed decision 9's list, exactly: name, identity, status, score, threshold,
    tolerance, and the metadata an assertion measured, where the suite disclosed
    it. `reason` is not here and cannot be added by a caller — the judge quotes
    the output, so the reason *is* the output.
    """
    return {
        "name": verdict.score.name,
        "assertion_id": verdict.assertion_id,
        "status": verdict.status,
        "score": verdict.score.score,
        "threshold": verdict.threshold,
        "tolerance": verdict.tolerance,
        # The instrument's own readings, as recorded. A score of 0.667 with no
        # interval beside it cannot say whether it was measured once or five
        # times, and telling a wobble from a drift — AGENTS.md §3 — is the
        # judgement this surface exists to support. (ADR 0006 §9)
        "samples": list(verdict.score.samples),
        "sample_min": verdict.score.sample_min,
        "sample_max": verdict.score.sample_max,
        # What those samples **are**, beside them. Absent, a reader cannot tell
        # two judgements from two means of judgements — the misreading schema 13
        # was spent to stop (ADR 0024 §6.5), shipped by the one surface built
        # for a model to read. It travels with `samples` because a reading of
        # the instrument that cannot say what its numbers are is not a reading.
        # (ADR 0011 §5, amended 2026-09-19)
        "sample_means": verdict.score.sample_means,
        # A model placed this score, so a movement here may be the judge's noise
        # and the same movement on a deterministic check cannot be. Not
        # derivable from anything else that crosses: the `shape` list needs a
        # reference and omits folds.
        "judged": verdict.judged,
        "metadata": {
            k: v
            for k, v in verdict.score.metadata.items()
            if k in disclosure.score_metadata
        },
    }


def run_document(run: Run, disclosure: Disclosure) -> dict[str, object]:
    """One stored run, as something outside the perimeter may read it.

    **An MCP response is a boundary crossing** and fixed decision 9 governs it.
    This does not go to a terminal or to a CI log inside the perimeter: it goes
    into a model's context, commonly a model hosted by somebody else, and from
    there into transcripts and caches nobody here controls. That is a worse
    destination than the CI stdout for which `delta_json` already refuses to
    emit a reason.

    **Chosen, not inherited.** The obvious alternative was
    `run_to_json(run, redacted=True, disclosure=…)`, which already omits rather
    than empties and already stamps `"redacted": true`. It was rejected because
    that document is under `SCHEMA_VERSION` — two contracts, two lifetimes.
    Inheriting the projection would mean the boundary moves whenever the storage
    document moves; choosing it means the boundary moves when ADR 0011 §5 does,
    and only then. `tests/test_wire_boundary.py` is what makes the difference
    real: a field added here without a decision fails a test.

    What crosses is the verdict. What does not: `Verdict.reason`, the stated
    reason a case was suspended, `Score.metadata` the suite did not disclose,
    artifact text without `Disclosure(artifacts=True)`, and the case inputs
    entirely — `Case.vars` and `Case.metadata` are the data.

    `suspended` is a **boolean**. That a case was set aside is a fact about
    coverage and belongs here; the sentence explaining it is payload and does
    not. A developer writes things like "fails on the Rossi account".

    **The instrument's own flags cross, since 0.16.0** — the decision the gap
    recorded here was waiting for (ADR 0011 §5, amended 2026-09-19). A caller
    can tell a replay, a canary, a calibration case and a judged check from
    their neighbours, and can tell two judgements from two means of them.

    **`Run.judge_samples` is the one that does not cross, and it is ruled out
    rather than pending.** The numbers it qualifies — `judge_min`, `judge_max`,
    `judge_errored`, `judge_answer` — live in `Score.metadata`, which this
    projection filters to the suite's `Disclosure` with no `travels()` fallback,
    so a bare count would arrive with nothing to count against. It waits for the
    decision that lets the range itself cross, and `tests/test_wire_boundary.py`
    asserts its absence so this reads as a ruling and not as a gap.
    """
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenant": run.tenant,
            "environment": run.environment,
            "suite": run.suite,
            "config_hash": run.config_hash,
            "created_at": run.created_at,
            "git_commit": run.git_commit,
            # A fact about our own instrument, never about the end company, so it
            # crosses like a measurement does. It is also what makes a document that
            # reaches a model's context traceable back to the release that wrote it.
            # (ADR 0014 §3)
            "digline_version": run.digline_version,
            # On a baseline, when a person approved it — `created_at` is when it was
            # measured. A fact about our own process, so it crosses; empty where it
            # was not recorded, and on any document that is not a baseline.
            # (ADR 0014 §3)
            "promoted_at": run.promoted_at,
            # The run whose recorded answers this one was judged from, or empty.
            # The sharpest of the six: a consumer that reads a replay as a fresh
            # measurement concludes the system improved on a day nothing was
            # asked of it. The **key** and not a boolean — `redact()` already
            # rules it travels, being a timestamp and a config hash, and a caller
            # can pass it straight back to `get_run`. `compare` carries the
            # boolean; a caller reading one run had nothing.
            # (ADR 0011 §5, amended 2026-09-19)
            "rejudged_from": run.rejudged_from or "",
            "results": [
                {
                    "case_id": case.case_id,
                    "suspended": case.suspended is not None,
                    # The two ways a case is an **instrument** rather than a
                    # measurement. A canary's score is a fingerprint of which
                    # model answered (ADR 0016) and a calibration case's score
                    # measures the judge against an answer the author wrote
                    # (ADR 0024 §4) — so a reader that averaged either into
                    # "quality" would be averaging the ruler into the thing
                    # measured. Both are the suite author's own declarations and
                    # carry no case data; the band is a check's name and two
                    # numbers. (ADR 0011 §5, amended 2026-09-19)
                    "canary": case.canary,
                    "calibration": (
                        None
                        if case.calibration is None
                        else {
                            "check": case.calibration.check,
                            "low": case.calibration.low,
                            "high": case.calibration.high,
                        }
                    ),
                    "verdicts": [
                        _verdict_document(v, disclosure) for v in case.verdicts
                    ],
                }
                for case in run.results
            ],
            "aggregate": [_verdict_document(v, disclosure) for v in run.aggregate],
            # Measurements of the system, by ADR 0005's ruling: a model id and a
            # temperature are what decided how it answered, and a document that
            # named neither could not say which model produced the run it describes.
            "target_config": _config_document(run.target_config),
            "judge_config": _config_document(run.judge_config),
            # The digest leaves **with** the text or not at all. A digest is a
            # verifier: prompts live in a small, guessable space, so a few thousand
            # candidates hashed against a leaked one recover the text in
            # milliseconds, and with it the end company's business rules. A digest
            # travelling beside a withheld prompt would defeat the withholding it
            # travelled beside (ADR 0003 §4).
            #
            # The path stays either way, and `withheld` says which absence it is:
            # "this suite kept it back" and "this run declared no artifacts" are
            # different facts and a reader is owed both.
            "artifacts": {
                path: (
                    {"sha": artifact.sha, "text": artifact.text}
                    if disclosure.artifacts
                    else {"withheld": True}
                )
                for path, artifact in sorted(run.artifacts.items())
            },
            # What the run consumed, as the two lines the document holds. It
            # crosses because of its **grain**: a run total is the software
            # house's own invoice for its own run — it names no case, no request
            # and nobody — and world 2 is defined by needing the signal without
            # holding the data. The per-call counts are payload and this
            # projection never learns their name, which is the same split
            # `redact()` makes. `null` where the document recorded none, which
            # is every document written before schema 14. (ADR 0025 §8, §9)
            "usage": None if run.usage is None else _usage_document(run.usage),
            "metadata": _disclosed(run.metadata, disclosure.run_metadata),
            # So a reader can tell what this document was allowed to carry, rather
            # than inferring it from what happens to be absent.
            "disclosure": {
                "run_metadata": sorted(disclosure.run_metadata),
                "score_metadata": sorted(disclosure.score_metadata),
                "artifacts": disclosure.artifacts,
            },
        }
    )


def _usage_document(usage: RunUsage) -> dict[str, object]:
    """The bill, both lines, with `partial` computed rather than left to be
    derived.

    A consumer that had to compare two integers to learn whether a total covers
    the whole run is a consumer that will forget to, and the one who forgets
    reads a partial total as a complete one — the failure this field exists to
    prevent. Same reason the CLI prints it rather than leaving it to be read off
    two numbers. (ADR 0025 §3, §9)
    """
    return {
        side: {
            "calls": line.calls,
            "counted": line.counted,
            "partial": line.partial,
            "input_tokens": line.tokens.input_tokens,
            "output_tokens": line.tokens.output_tokens,
            "cache_read_tokens": line.tokens.cache_read_tokens,
            "cache_write_tokens": line.tokens.cache_write_tokens,
            "spent_usd": line.spent_usd,
        }
        for side, line in (("target", usage.target), ("judge", usage.judge))
    }


def _config_document(config: SystemConfig) -> dict[str, object]:
    """One system's declared configuration, with ADR 0005's withholding applied.

    Through `SystemConfig.redacted()` and not through a rule written again here:
    one implementation of a perimeter is one place to get it wrong. It keeps
    back `base_url` — the client's topology — which was already reduced to a
    host by `endpoint_host` when it was recorded, so no credential was ever in
    the value to begin with.

    **Withheld is absent, never emptied**, and that is an invariant of the type
    rather than a promise of this function: `SystemConfig.__post_init__` refuses
    to hold a key as both present and withheld. The names travel so a reader can
    tell `unknown` from `unchanged` — ADR 0005 §2's distinction, which is the
    whole reason the flag exists.
    """
    kept = config.redacted()
    return {
        "values": dict(sorted(kept.values.items())),
        "withheld": sorted(kept.withheld),
        "identities": list(kept.identities),
    }


def _disclosed(
    values: Mapping[str, object], allowed: frozenset[str]
) -> dict[str, object]:
    """Nothing here travels on its own merit, numbers included: an amount copied
    out of a customer's request is their data wearing the same clothes as a
    measurement."""
    return {k: v for k, v in values.items() if k in allowed}
