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


def _runs(cycle: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return cast("Sequence[Mapping[str, Any]]", cycle["runs"])


def _deltas(run: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return cast("Sequence[Mapping[str, Any]]", run["compare"]["deltas"])


def _interval(delta: Mapping[str, Any]) -> str:
    """The measured floor this check moved against, or why there is none.

    On a **flip** — passing to failing — `compare` reports no interval at all:
    a flip is a regression whatever the noise said, so the comparison never
    consults the floor and never carries it. Said out loud rather than left as
    an empty column, because the reader is entitled to know the difference
    between "the interval was wide" and "there is no interval here".
    """
    low, high = delta["noise_min"], delta["noise_max"]
    if low is None or high is None:
        return "no interval (a flip is a regression whatever the noise said)"
    return f"{low:.4f}–{high:.4f} across {delta['noise_samples']} samples"


def _fact(cycle: Mapping[str, Any]) -> list[str]:
    """Layer 1. The wire's own numbers, named and not re-worded."""
    lines = [
        "## 1. The fact",
        "",
        "Machine truth, from `digline compare --json full`. Reproducible, and "
        "not prose.",
        "",
        "| run | seed | exit | worse | unjudged | within noise |",
        "| --- | ---: | ---: | :---: | -------: | -----------: |",
    ]
    for run in _runs(cycle):
        head = cast("Mapping[str, Any]", run["compare"])
        lines.append(
            f"| `{run['key']}` | {run['seed']} | {run['exit_code']} | "
            f"{'yes' if head['worse'] else 'no'} | {head['unjudged']} | "
            f"{head['within_noise']} |"
        )
    first = cast("Mapping[str, Any]", _runs(cycle)[0]["compare"])
    lines += [
        "",
        f"Suite `{cycle['suite']}`, output version {first['output_version']}. "
        f"The configuration of the system under test "
        f"{'**changed**' if first['target_config_changed'] else 'did not change'}"
        f"; the judge's configuration "
        f"{'**changed**' if first['judge_config_changed'] else 'did not change'}"
        f"; the suite itself "
        f"{'**changed**' if first['config_changed'] else 'did not change'}.",
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
        # Every check whose score actually moved, not only the ones that
        # changed outcome. A movement the floor absorbed is what makes the
        # floor readable, and a table that showed only regressions would print
        # the word "noise" without ever showing any.
        moved = [
            d
            for d in _deltas(run)
            if d["outcome"] != "unchanged" or d["before"] != d["after"]
        ]
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
        for delta in sorted(
            moved, key=lambda d: (str(d["case_id"]), str(d["assertion"]))
        ):
            case = delta["case_id"] or "_(whole run)_"
            before = "—" if delta["before"] is None else f"{delta['before']:.4f}"
            after = "—" if delta["after"] is None else f"{delta['after']:.4f}"
            lines.append(
                f"| `{case}` | `{delta['assertion']}` | {delta['outcome']} | "
                f"{before} | {after} | {_interval(delta)} |"
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
