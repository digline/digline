"""What the run tools say to a program.

`run_json` is what `digline run --json` prints and what the MCP `run` tool
returns: a run was written, and here is how to name it. It carries no verdict —
it reports that a run happened, not whether it was any good.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from digline.core import Disclosure, Run, SystemConfig, Verdict
from digline.run import CallPlan
from digline.store import Listing, RunRef
from digline.wire.contract import OUTPUT_VERSION

__all__ = ["run_document", "run_json", "runs_json"]


def run_json(ref: RunRef, plan: CallPlan) -> dict[str, object]:
    """The written run, named, with what it cost to make.

    `sentence` is `CallPlan.sentence()` — the line the CLI prints to stderr
    before the first call. Over MCP there is no stderr, and `AGENTS.md` §7 asks
    an agent to say what a hunt cost; the acknowledged integer covers the calls
    to the target only, so the sentence is what carries the judge repeats a
    caller has to include when it reports the spend. (ADR 0011 §2, §4)
    """
    return {
        "output_version": OUTPUT_VERSION,
        "key": ref.key,
        "tenant": ref.tenant,
        "suite": ref.suite,
        "sentence": plan.sentence(),
    }


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
    return {
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
            }
            for key, run in ordered
        ],
        "note": listing.note(),
        "skipped": {str(version): n for version, n in sorted(listing.skipped.items())},
        "unreadable": len(listing.unreadable),
    }


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
    """
    return {
        "output_version": OUTPUT_VERSION,
        "tenant": run.tenant,
        "environment": run.environment,
        "suite": run.suite,
        "config_hash": run.config_hash,
        "created_at": run.created_at,
        "git_commit": run.git_commit,
        "results": [
            {
                "case_id": case.case_id,
                "suspended": case.suspended is not None,
                "verdicts": [_verdict_document(v, disclosure) for v in case.verdicts],
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
        "metadata": _disclosed(run.metadata, disclosure.run_metadata),
        # So a reader can tell what this document was allowed to carry, rather
        # than inferring it from what happens to be absent.
        "disclosure": {
            "run_metadata": sorted(disclosure.run_metadata),
            "score_metadata": sorted(disclosure.score_metadata),
            "artifacts": disclosure.artifacts,
        },
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
