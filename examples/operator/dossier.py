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


def _dossier(cycle: Mapping[str, Any]) -> list[str]:
    """Layer 2. What the operator did and saw — deterministic, no model."""
    rule = cast("Mapping[str, Any]", cycle["stopping_rule"])
    budget = cast("Mapping[str, Any]", cycle["budget"])
    runs = _runs(cycle)
    reruns = len(runs) - 1

    lines = [
        "## 2. The dossier",
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


def evidence(cycle: Mapping[str, Any]) -> str:
    """Layers 1 and 2 alone — the deterministic half of the document.

    Exported because `judgment.py` shows the model exactly this and nothing
    else. One rendering of the facts, so the layer that opines and the layer a
    human reads cannot come to be about two different runs.
    """
    return "\n".join([*_fact(cycle), "", *_dossier(cycle)]) + "\n"


def alert_body(cycle: Mapping[str, Any], *, judgment: str | None) -> str:
    """The whole document. `judgment` is layer 3, or `None` when it did not run."""
    verdict = str(cycle["verdict"])
    escalate = bool(cycle["escalate"])
    lines = [
        f"# digline operator: {verdict}",
        "",
        f"**{HEADLINES[verdict]}** {BECAUSE[verdict]}",
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
        *_dossier(cycle),
        "",
        *_judgment(cycle, judgment),
        "",
        "---",
        "",
        "No baseline was promoted, and none can be: `promote` is absent from "
        "the operator's surface by construction. A baseline is an approved "
        "reference, and the approval is a person's.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", default="cycle.json", type=Path)
    parser.add_argument("--judgment", type=Path, help="layer 3, when it ran")
    parser.add_argument("--out", default="alert.md", type=Path)
    args = parser.parse_args(argv)

    cycle = cast(
        "Mapping[str, Any]",
        json.loads(Path(args.cycle).read_text(encoding="utf-8")),
    )
    judgment: str | None = None
    if args.judgment is not None and Path(args.judgment).is_file():
        judgment = Path(args.judgment).read_text(encoding="utf-8")

    Path(args.out).write_text(alert_body(cycle, judgment=judgment), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
