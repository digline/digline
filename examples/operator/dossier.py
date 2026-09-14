"""`cycle.json` in, the three-layer alert out.

Pure: a parsed cycle and an optional judgment go in, a markdown document comes
out. No clock, no filesystem beyond the two files `main` names, no `gh`. That is
what lets the alert this example ships be compared against what this script
produces today, byte for byte, by a test — a captured alert that nothing checks
is a screenshot, and screenshots rot in the direction that flatters.

    python dossier.py --cycle cycle.json --out alert.md
    python dossier.py --cycle cycle.json --judgment judgment.md --out alert.md

The layers are the ones `DESIGN.md` fixes, and the typography is the part that
matters: layer 1 is machine truth, layer 2 is what the operator did, layer 3 is
the only thing a model wrote and it is labelled as an opinion. When there is no
layer 3 the heading is still printed, saying so. An absence is stated, never
faked.

Layers 1 and 2 are rendered from `digline explain --json`, which `loop.py`
keeps verbatim for every run: the typed facts digline renders its own reading
from. This file selects and lays them out; it derives none of them.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

#: What each verdict means, in the operator's own words. The wording is
#: deliberately about the *measurement*, never about the system: the operator
#: watches the measurement and does not diagnose the code.
HEADLINES: Mapping[str, str] = {
    "clean": "Nothing got worse.",
    "draw": "One check dipped and did not repeat. Treated as noise.",
    "drift": "A drop repeated past the declared stopping rule.",
    "structural": "Several cases moved together in one run.",
    "system-error": "The run could not be judged.",
}

#: Why each verdict does or does not wake somebody, quoting the rule it obeys.
BECAUSE: Mapping[str, str] = {
    "clean": "No escalation: there is nothing to decide.",
    "draw": (
        "No escalation. AGENTS.md §3: a dip that does not recur on re-run is "
        "sampling noise — documented here, and that is the whole of it."
    ),
    "drift": (
        "Escalated. AGENTS.md §3: a dip that recurs is drift, and drift is "
        "investigated — the model, the judge, the prompt, the dependency "
        "floor, in that order of likelihood."
    ),
    "structural": (
        "Escalated **without a re-run**. AGENTS.md §4: several cases flipping "
        "together is either a real regression or the judge itself moving, and "
        "retrying destroys the evidence either way."
    ),
    "system-error": (
        "Escalated. Exit code 2 means the run could not be judged, and nothing "
        "downstream of it is meaningful — including the green checks beside it."
    ),
}

#: The second line when a declared policy held a classification that would have
#: woken somebody.
#:
#: `BECAUSE` **asserts an outcome** — it opens with "Escalated." — so printing
#: it above a line reading *escalating: no* would make the document contradict
#: itself three lines apart. That is the arithmetically-correct-and-
#: rhetorically-false shape ADR 0008 refused for `diff`, and it is no more
#: acceptable here. The rule is still cited; what changes is that it is cited
#: in the conditional, because the conditional is what happened.
#:
#: Two entries and not five. `clean` and `draw` propose no escalation, so there
#: is nothing for a policy to hold; `system-error` is a floor no clause may
#: lower. Anything absent falls back to `BECAUSE`, which is then true.
HELD: Mapping[str, str] = {
    "drift": (
        "The classification would have woken somebody — AGENTS.md §3: a dip "
        "that recurs is drift — and a declared policy held it. The decision "
        "and the clause it cites are in the dossier below."
    ),
    "structural": (
        "The classification would have woken somebody without a re-run — "
        "AGENTS.md §4: several cases flipping together is investigated and "
        "never retried — and a declared policy held it. The decision and the "
        "clause it cites are in the dossier below."
    ),
}


#: Whose setting a `setting` fact names, in the words the dossier uses.
OWNERS: Mapping[str, str] = {
    "target": "the system under test",
    "judge": "the judge",
    "artifact": "a file under test",
}


def _runs(cycle: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return cast("Sequence[Mapping[str, Any]]", cycle["runs"])


def _facts(run: Mapping[str, Any], about: str) -> list[Mapping[str, Any]]:
    """One of the three shapes in `explain --json`, in the wire's own order.
    Discriminated on `about` first: two shapes have a kind called
    `within_noise`, and they mean different things."""
    facts = cast("Sequence[Mapping[str, Any]]", run["explain"]["facts"])
    return [fact for fact in facts if fact["about"] == about]


def _tally(run: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    """A run-level fact. `within_noise` is stated only when it is not zero,
    so an absent one reads as a zero count."""
    found = [f for f in _facts(run, "run") if f["kind"] == kind]
    return found[0] if found else {"count": 0, "state": None}


def _moved(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every check that moved, worst first — `explain` already drew that line.

    Its list holds the checks whose score moved, not only the ones that
    changed outcome: a movement the floor absorbed is what makes the floor
    readable, and a table of regressions alone would print the word "noise"
    without ever showing any. A suspension names a case and no check, so it
    has no row in a table of checks.
    """
    return [f for f in _facts(run, "check") if f["kind"] != "suspended"]


def _interval(fact: Mapping[str, Any]) -> str:
    """The measured floor this check moved against, or why there is none.

    On a **flip** — passing to failing — the comparison reports no interval at
    all: a flip is a regression whatever the noise said, so the floor is never
    consulted and never carried. Said out loud rather than left as an empty
    column, because the reader is entitled to know the difference between "the
    interval was wide" and "there is no interval here".
    """
    low, high = fact["noise_min"], fact["noise_max"]
    if low is None or high is None:
        if fact["kind"] == "regressed":
            return "no interval (a flip is a regression whatever the noise said)"
        return "no interval"
    return f"{low:.4f}–{high:.4f} across {fact['noise_samples']} samples"


def _fact(cycle: Mapping[str, Any]) -> list[str]:
    """Layer 1. The wire's own facts, selected and not re-worded."""
    lines = [
        "## 1. The fact",
        "",
        "Machine truth, from `digline explain --json`: the fact list digline "
        "renders its own reading from. Reproducible, and not prose.",
        "",
        "| run | seed | exit | unjudged | within noise |",
        "| --- | ---: | ---: | -------: | -----------: |",
    ]
    for run in _runs(cycle):
        lines.append(
            f"| `{run['key']}` | {run['seed']} | {run['exit_code']} | "
            f"{_tally(run, 'unjudged')['count']} | "
            f"{_tally(run, 'within_noise')['count']} |"
        )
    first = _runs(cycle)[0]
    changed = bool(_tally(first, "suite_config")["state"])
    # `explain` states a setting only where it differs, so none stated is the
    # fact "nothing did" rather than an absence of information.
    settings = [
        f"{OWNERS[s['kind']]} `{s['name']}` ({s['outcome']})"
        for s in _facts(first, "setting")
    ]
    lines += [
        "",
        "Exit `0`: nothing got worse. `1`: something did. `2`: the run could "
        "not be judged. That is digline's contract, AGENTS.md §6.",
        "",
        f"Suite `{cycle['suite']}`, output version "
        f"{first['explain']['output_version']}. The suite itself "
        f"{'**changed**' if changed else 'did not change'}. Underneath it, "
        + (
            f"**differed**: {', '.join(settings)}."
            if settings
            else "nothing differed: not the system under test, not the judge, "
            "not a file under test."
        ),
    ]
    return lines


def _wall(cycle: Mapping[str, Any]) -> str:
    """The probe, first because it ran first: one write that must be refused
    beside one that must succeed. A cycle written before the probe existed
    says so — an absence is stated, never faked."""
    probe = cast("Mapping[str, Any] | None", cycle.get("probe"))
    if probe is None:
        return "The wall was not probed: this cycle predates the probe."
    if probe["wall"] == "intact":
        return (
            "Before comparing anything, proved the wall: `promote`, called by "
            "name on the operator's own MCP surface, came back *unknown tool*, "
            "and beside it the cycle file — a write the operator owns — "
            "succeeded. **Intact**, for the identity that ran this cycle."
        )
    if probe["wall"] == "collapsed":
        return (
            "**The separation collapsed.** `promote`, called by name on the "
            "operator's MCP surface, answered — and on that surface the wall is "
            "the absence, so an answer of any kind is a collapse. "
            + (
                "What it wrote under the baselines was rolled back before the "
                "comparison below read them."
                if probe["rolled_back"]
                else "Nothing under the baselines changed."
            )
        )
    return (
        "**The probe was inconclusive: the instrument, not the wall.** "
        + (
            "The MCP server gave no answer to a call to `promote`, and silence "
            "is not a refusal."
            if probe["negative"] == "unobserved"
            else "`promote` came back *unknown tool*, but the cycle file beside "
            "it could not be written, and a refusal alone proves nothing."
        )
        + " Nothing is known about the wall this cycle."
    )


def _policy_wall(cycle: Mapping[str, Any]) -> str:
    """The second negative and the fourth check, in one sentence each.

    Reported beside the first wall rather than folded into it: an absent tool
    and a file mode are different kinds of protection, and a reader is owed
    which one is being described.
    """
    probe = cast("Mapping[str, Any] | None", cycle.get("probe"))
    if probe is None or "policy_wall" not in probe:
        return ""
    matched = probe.get("digest_matches")
    fourth = (
        ""
        if matched is None
        else (
            " The digest this cycle reports is the digest of the policy on "
            "disk, so it was ruled by the policy it names."
            if matched
            else " **The digest this cycle reports is not the digest of the "
            "policy on disk**, so the policy moved between the run and this "
            "document: no hold taken under it can be reproduced."
        )
    )
    if probe["policy_wall"] == "enforced":
        return (
            "The policy wall held: `operator.toml` is not writable by the "
            "identity that ran this cycle, so the operator reads its policy "
            "and cannot edit it." + fourth
        )
    if probe["policy_wall"] == "unenforced":
        return (
            "**The policy wall is a latch, not a constraint, for this "
            "identity:** `operator.toml` is writable here. That is the honest "
            "answer on a checkout and on a repository whose owner holds every "
            "key — the wall a deployment relies on is the push, not the file "
            "mode, and it is protected by branch rules rather than by "
            "permissions." + fourth
        )
    return (
        "Whether the policy is writable by this identity could not be "
        "established, so nothing is known about the second wall this cycle." + fourth
    )


def _decision(
    cycle: Mapping[str, Any], decision: Mapping[str, Any] | None
) -> list[str]:
    """Why somebody was woken, or why nobody was.

    Layer 2 and not layer 3: the seat is deterministic given a cycle and a
    policy, so this is a record of what was decided rather than an opinion
    about it. A model interprets this below; it does not produce it.
    """
    proposed = bool(cycle["escalate"])
    if decision is None:
        return [
            "",
            "**No decision was recorded for this cycle.** The seat is where a "
            "declared policy decides whether a classification wakes anybody, "
            "and it did not run here — so what stands is the classification "
            "itself, which "
            + ("wakes somebody" if proposed else "wakes nobody")
            + ". An absence is stated, never faked.",
        ]

    policy = cast("Mapping[str, Any] | None", decision["policy"])
    named = (
        "under no policy"
        if policy is None
        else f"under policy `{policy['name']}` (`{policy['digest']}`)"
    )
    lines = [
        "",
        f"**Decision: {'escalate' if decision['escalate'] else 'hold'}**, "
        f"{named}. {decision['reason']}",
    ]
    if decision["clause"] is not None:
        lines.append("")
        lines.append(
            f"The clause is cited by name — `{decision['clause']}` — because a "
            "reason that cites no clause is an opinion, and one that cites a "
            "clause is the policy being exercised."
        )
    if decision["floor"] is not None:
        lines.append("")
        # `policy-moved` is **not** a floor and must not be described as one: it
        # says no policy was in force to do the holding, which is a different
        # fact from a clause having been forbidden. The two share a field
        # because a reader asking *why was this not held* wants one answer;
        # they do not share a sentence. `decide.py` owns the vocabulary — this
        # renders it and never invents a member of it.
        lines.append(
            "No clause was consulted: the digest this cycle reports is not the "
            "digest of the policy on disk, so there was no policy in force to "
            "hold it."
            if decision["floor"] == "policy-moved"
            else f"No clause could have held this cycle: the "
            f"`{decision['floor']}` floor is one the policy may never lower."
        )
    if decision["in_quiet_hours"] is not None and policy is not None:
        window = cast("Mapping[str, Any]", policy["quiet_hours"])
        inside = "inside" if decision["in_quiet_hours"] else "outside"
        lines.append("")
        lines.append(
            f"Decided at {decision['evaluated_at']}, which is {inside} the "
            f"declared quiet window {window['from']}–{window['to']} "
            f"{window['tz']}. The window is recorded because a decision that "
            "turns on the hour is reviewable only if the hour is written down."
        )
    return lines


def _collapsed(cycle: Mapping[str, Any]) -> bool:
    probe = cast("Mapping[str, Any] | None", cycle.get("probe"))
    return probe is not None and probe["wall"] == "collapsed"


def _dossier(
    cycle: Mapping[str, Any], decision: Mapping[str, Any] | None = None
) -> list[str]:
    """Layer 2. What the operator did, saw and decided — deterministic, no
    model."""
    rule = cast("Mapping[str, Any]", cycle["stopping_rule"])
    budget = cast("Mapping[str, Any]", cycle["budget"])
    runs = _runs(cycle)
    reruns = len(runs) - 1

    second = _policy_wall(cycle)
    lines = [
        "## 2. The dossier",
        "",
        _wall(cycle),
        *(["", second] if second else []),
        *_decision(cycle, decision),
        "",
        f"Ran the suite once and re-ran it {reruns} time(s). The stopping rule "
        f"was `max_reruns = {rule['max_reruns']}`, declared in `operator.toml` "
        "before anything ran.",
        "",
        f"Spend: {budget['spent']} calls to the target across {len(runs)} run(s), "
        f"against a declared cycle budget of {budget['max_target_calls']}. "
        f"Each run: {runs[0]['spend']}.",
    ]
    if budget["stopped_the_loop"]:
        lines += [
            "",
            "**The budget stopped the loop before the stopping rule did.** The "
            "classification below rests on fewer re-runs than the rule allows, "
            "and is weaker than it would otherwise read.",
        ]

    for run in runs:
        moved = _moved(run)
        lines += [
            "",
            f"**Run `{run['key']}` (seed {run['seed']}, exit {run['exit_code']})**",
        ]
        if not moved:
            lines.append("")
            lines.append("No check moved at all.")
            continue
        lines += [
            "",
            "| case | check | outcome | before | after | measured floor |",
            "| ---- | ----- | ------- | -----: | ----: | -------------- |",
        ]
        for fact in moved:
            case = f"`{fact['case_id']}`" if fact["case_id"] else "_(whole run)_"
            before = "—" if fact["before"] is None else f"{fact['before']:.4f}"
            after = "—" if fact["after"] is None else f"{fact['after']:.4f}"
            lines.append(
                f"| {case} | `{fact['assertion']}` | {fact['kind']} | "
                f"{before} | {after} | {_interval(fact)} |"
            )

    repeated = cast("Sequence[Sequence[str]]", cycle["reproduced"])
    lines += [""]
    if repeated:
        named = ", ".join(f"`{case}` / `{check}`" for case, check in repeated)
        lines.append(f"Present in every run of this cycle: {named}.")
    else:
        lines.append("No regression was present in every run of this cycle.")
    return lines


def _judgment(cycle: Mapping[str, Any], judgment: str | None) -> list[str]:
    """Layer 3. The only layer a model writes, and it is labelled as such."""
    lines = ["## 3. The judgment", ""]
    if judgment is None:
        lines += [
            "**This layer was not run.** It is the only part of this document "
            "that a model writes, and it is an explicit opt-in: the key was "
            "not configured for this cycle. Layers 1 and 2 above are complete "
            "and were produced without one.",
            "",
            f"What stands in its place is the deterministic classification, "
            f"**{cycle['verdict']}**, and the rule it came from — both stated "
            "at the top of this document. Neither is an opinion; that is the "
            "difference.",
        ]
        return lines
    lines += [
        "> The operator's opinion, written by a model. It is **not** digline's "
        "verdict: the instrument measured layers 1 and 2, and this layer "
        "interprets them.",
        "",
        judgment.strip(),
    ]
    return lines


def evidence(
    cycle: Mapping[str, Any], decision: Mapping[str, Any] | None = None
) -> str:
    """Layers 1 and 2 alone — the deterministic half of the document.

    Exported because `judgment.py` shows the model exactly this and nothing
    else. One rendering of the facts, so the layer that opines and the layer a
    human reads cannot come to be about two different runs.
    """
    return "\n".join([*_fact(cycle), "", *_dossier(cycle, decision)]) + "\n"


def alert_body(
    cycle: Mapping[str, Any],
    *,
    decision: Mapping[str, Any] | None = None,
    judgment: str | None = None,
) -> str:
    """The whole document. `judgment` is layer 3, or `None` when it did not run."""
    verdict = str(cycle["verdict"])
    proposed = bool(cycle["escalate"])
    escalate = proposed if decision is None else bool(decision["escalate"])
    # The two can disagree, and the disagreement is the whole point of the
    # seat: what the measurement concluded, and what somebody's declared rules
    # did about it. Said in the opening line rather than left to be noticed.
    held = proposed and not escalate
    lines = [
        f"# digline operator: {verdict}",
        "",
        f"**{HEADLINES[verdict]}** "
        + (HELD.get(verdict, BECAUSE[verdict]) if held else BECAUSE[verdict]),
        "",
        f"Suite `{cycle['suite']}`, cadence `{cycle['cadence']}`, "
        f"escalating: {'yes' if escalate else 'no'}.",
        "",
        "The operator watches the measurement; it does not repair the system. "
        "Fixing this belongs to whoever owns the prompt — this document is the "
        "handover.",
        "",
        *_fact(cycle),
        "",
        *_dossier(cycle, decision),
        "",
        *_judgment(cycle, judgment),
        "",
        "---",
        "",
        (
            "`promote` answered on the operator's surface this cycle, where "
            "the design says there is nothing to answer. A baseline is an "
            "approved reference, and the approval is a person's: until the "
            "surface is repaired, that is a rule again rather than a fact."
            if _collapsed(cycle)
            else "No baseline was promoted, and none can be: `promote` is "
            "absent from the operator's surface by construction. A baseline is "
            "an approved reference, and the approval is a person's."
        ),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="cycle.json", type=Path)
    parser.add_argument("--decision", type=Path, help="the seat, when it ran")
    parser.add_argument("--judgment", type=Path, help="layer 3, when it ran")
    parser.add_argument("--out", default="alert.md", type=Path)
    args = parser.parse_args(argv)

    cycle = cast(
        "Mapping[str, Any]",
        json.loads(Path(args.cycle).read_text(encoding="utf-8")),
    )
    decision: Mapping[str, Any] | None = None
    if args.decision is not None and Path(args.decision).is_file():
        decision = cast(
            "Mapping[str, Any]",
            json.loads(Path(args.decision).read_text(encoding="utf-8")),
        )
    judgment: str | None = None
    if args.judgment is not None and Path(args.judgment).is_file():
        judgment = Path(args.judgment).read_text(encoding="utf-8")

    Path(args.out).write_text(
        alert_body(cycle, decision=decision, judgment=judgment), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
