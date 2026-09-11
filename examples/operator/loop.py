"""The operator's deterministic half: run, re-run within the declared rule,
classify, and write down what happened.

No model is called here and no key is read. Everything this file produces is
layer 1 and layer 2 of the alert — the machine facts and the record of what the
operator did — and it is reproducible: given the same suite and the same seeds,
it writes the same `cycle.json` twice.

    python loop.py --config operator.toml --out cycle.json

The classification is the judgment `AGENTS.md` writes down, and nothing beyond
it. It cannot promote a baseline and it cannot edit a prompt: it watches the
measurement, and the alert is the handover to whoever repairs the system.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from digline.host import load_suite
from digline.run import planned_calls

#: The shape of `cycle.json`, so a consumer can tell when it moved. The same
#: idea as digline's own `output_version`, and separate from it: this is the
#: example's file, not the tool's. 2 since each run carries `explain --json`
#: where it carried `compare --json full`.
CYCLE_FORMAT = 2

#: What one cycle concluded. A `Literal` rather than an enum because these
#: strings land in a markdown document and in a test assertion, and a plain
#: string a type checker still checks exhaustively is the smaller thing.
Verdict = Literal["clean", "draw", "drift", "structural", "system-error"]

#: digline's exit codes, which `AGENTS.md` §6 calls the contract.
EXIT_OK = 0
EXIT_WORSE = 1
EXIT_UNJUDGED = 2


@dataclass(frozen=True)
class Config:
    """`operator.toml`, parsed. Nothing here has a default: a stopping rule
    that defaulted would be a stopping rule nobody chose."""

    suite: str
    cadence: str
    max_reruns: int
    structural_flip_cases: int
    max_target_calls: int
    dry_run: bool
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    """One run of the suite, as the wire reports it.

    `explain` is `digline explain --json`, kept **verbatim**: the fact list
    digline renders its own reading from. It is layer 1 of the alert, and layer
    1 is the machine truth: this file reads facts out of it and never rewrites
    it.
    """

    key: str
    seed: int
    exit_code: int
    spend: str
    explain: Mapping[str, Any]

    @property
    def regressions(self) -> frozenset[tuple[str, str]]:
        """The `(case, check)` pairs that got worse. A run-scoped check carries
        an empty `case_id`, the same convention as everywhere else on the
        wire."""
        return frozenset(
            (str(f["case_id"]), str(f["assertion"]))
            for f in cast("Sequence[Mapping[str, Any]]", self.explain["facts"])
            if f["about"] == "check" and f["kind"] == "regressed"
        )

    @property
    def cases_regressed(self) -> frozenset[str]:
        return frozenset(case for case, _check in self.regressions)


@dataclass(frozen=True)
class Cycle:
    """What one pass of the loop did, saw and concluded."""

    runs: tuple[Observation, ...]
    verdict: Verdict
    escalate: bool
    #: The `(case, check)` pairs present in the first run *and* in every re-run.
    #: Non-empty is what "the drop repeated" means, stated as a set rather than
    #: as a feeling.
    reproduced: frozenset[tuple[str, str]]
    planned_per_run: int
    #: Set when the budget ran out before the stopping rule did. The dossier
    #: prints it: a loop that stopped early for a reason other than the signal
    #: has to say so, or the classification reads stronger than the evidence.
    budget_stopped: bool = False


# --------------------------------------------------------------------------- #
# The configuration, and the cadence it claims
# --------------------------------------------------------------------------- #


def load_config(path: Path) -> Config:
    with path.open("rb") as handle:
        # tomllib hands back `Any`; narrowed once here rather than trusted
        # throughout, which is the same shape the repository's own tests use.
        document = cast("Mapping[str, Any]", tomllib.load(handle))
    return Config(
        suite=str(document["operator"]["suite"]),
        cadence=str(document["operator"]["cadence"]),
        max_reruns=int(document["stopping_rule"]["max_reruns"]),
        structural_flip_cases=int(document["stopping_rule"]["structural_flip_cases"]),
        max_target_calls=int(document["budget"]["max_target_calls"]),
        dry_run=bool(document["escalation"]["dry_run"]),
        labels=tuple(str(label) for label in document["escalation"]["labels"]),
    )


CRON = re.compile(r"^\s*-\s*cron:\s*[\"'](?P<cron>[^\"']+)[\"']", re.MULTILINE)


def check_cadence(config: Config, workflow: Path) -> None:
    """Fail loudly when `operator.toml` and the workflow disagree about how
    often this runs.

    The cadence cannot live in the configuration file and be obeyed: GitHub
    reads `schedule:` from the YAML. So the file states it and this checks it —
    otherwise the one field a reader is most likely to change is the one field
    that does nothing.
    """
    if not workflow.is_file():
        raise SystemExit(
            f"no workflow at {workflow}: the cadence has nothing to agree with"
        )
    crons = CRON.findall(workflow.read_text(encoding="utf-8"))
    if config.cadence not in crons:
        raise SystemExit(
            f"operator.toml says the cadence is {config.cadence!r}, and "
            f"{workflow} schedules {crons or 'nothing'}. One of the two is "
            "wrong, and a configuration that disagrees with the scheduler is "
            "worse than no configuration: change both, together."
        )


# --------------------------------------------------------------------------- #
# One run
# --------------------------------------------------------------------------- #


def digline(*args: str, seed: int, root: Path) -> subprocess.CompletedProcess[str]:
    """digline, as a program.

    `-m digline.cli` rather than the `digline` script: it needs nothing on
    PATH, which is what makes this file run identically under `uv run` in a
    fork and under the repository's own tests.

    The seed goes in the environment because that is where `fake.py` reads it.
    It is the run's **index within this cycle** — 0 for the first, then 1 and 2
    for the re-runs — and it stands in for the variation a real system has on
    its own. A real target ignores it.
    """
    return subprocess.run(  # noqa: S603 - our own arguments, no shell
        [sys.executable, "-m", "digline.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "DIGLINE_OPERATOR_SEED": str(seed)},
    )


def observe(config: Config, *, seed: int, root: Path) -> Observation:
    """Run the suite once, then read it against the baseline somebody signed.

    `explain` rather than `compare`: it gates on the same comparison with the
    same exit codes, and hands back the facts already typed — which checks
    moved, against which interval, what differed underneath — so the dossier
    renders them instead of re-deriving them.
    """
    ran = digline("run", "--suite", config.suite, "--json", seed=seed, root=root)
    if ran.returncode != EXIT_OK:
        raise SystemExit(f"digline run failed:\n{ran.stderr}")
    written = cast("Mapping[str, Any]", json.loads(ran.stdout))

    read = digline(
        "explain",
        "--suite",
        config.suite,
        "--run",
        str(written["key"]),
        "--json",
        seed=seed,
        root=root,
    )
    if read.returncode not in (EXIT_OK, EXIT_WORSE, EXIT_UNJUDGED):
        raise SystemExit(f"digline explain refused the request:\n{read.stderr}")
    reading = cast("Mapping[str, Any]", json.loads(read.stdout))
    if reading["scope"] != "comparison":
        # Without a baseline `explain` reads the run alone, and alone it can
        # never exit 1: "worse" is a relation. A loop that went on would
        # report a clean week, every week, about a suite nobody had approved.
        raise SystemExit(
            f"{config.suite} has no baseline, so there is nothing to watch the "
            "system against. Promote one — a person does, never this loop."
        )

    return Observation(
        key=str(written["key"]),
        seed=seed,
        exit_code=read.returncode,
        # The sentence digline prints before the first call, which is the
        # figure `AGENTS.md` §7 asks an operator to report out loud.
        spend=str(written["sentence"]),
        explain=reading,
    )


# --------------------------------------------------------------------------- #
# The cycle
# --------------------------------------------------------------------------- #


def cycle(config: Config, *, root: Path) -> Cycle:
    """The stopping rule, honoured.

    Read it as the four events `AGENTS.md` separates, in the order they are
    decided:

    - the run could not be judged        -> system error, escalate, no re-run
    - nothing got worse                  -> clean
    - several cases moved together       -> structural, escalate, **no re-run**
    - one case moved                     -> re-run, then draw or drift
    """
    suite, _loaded = load_suite(str(root / config.suite))
    plan = planned_calls(suite)

    # Before the first call, which is the only moment a budget means anything.
    worst_case = plan.target_calls * (1 + config.max_reruns)
    if worst_case > config.max_target_calls:
        raise SystemExit(
            f"refusing to start: {plan.sentence()}, and the stopping rule "
            f"allows {config.max_reruns} re-runs, so this cycle could cost "
            f"{worst_case} calls to the target against a declared budget of "
            f"{config.max_target_calls}. Raise the budget or lower the rule — "
            "deliberately, in operator.toml, before anything is spent."
        )

    first = observe(config, seed=0, root=root)
    runs = [first]

    if first.exit_code == EXIT_UNJUDGED:
        return Cycle(tuple(runs), "system-error", True, frozenset(), plan.target_calls)
    if first.exit_code == EXIT_OK:
        return Cycle(tuple(runs), "clean", False, frozenset(), plan.target_calls)

    if len(first.cases_regressed) >= config.structural_flip_cases:
        return Cycle(
            tuple(runs), "structural", True, first.regressions, plan.target_calls
        )

    reproduced = first.regressions
    budget_stopped = False
    for attempt in range(config.max_reruns):
        if plan.target_calls * (len(runs) + 1) > config.max_target_calls:
            budget_stopped = True
            break
        again = observe(config, seed=1 + attempt, root=root)
        runs.append(again)
        reproduced &= again.regressions
        if not reproduced:
            # Stop at the signal: the dip did not recur, and further re-runs
            # would only be looking for the answer we want.
            break

    verdict: Verdict = "drift" if reproduced else "draw"
    return Cycle(
        tuple(runs),
        verdict,
        bool(reproduced),
        reproduced,
        plan.target_calls,
        budget_stopped=budget_stopped,
    )


def cycle_json(config: Config, done: Cycle) -> dict[str, Any]:
    """`cycle.json`: layer 1 verbatim, plus the record layer 2 is written from."""
    return {
        "cycle_format": CYCLE_FORMAT,
        "suite": config.suite,
        "cadence": config.cadence,
        "stopping_rule": {
            "max_reruns": config.max_reruns,
            "structural_flip_cases": config.structural_flip_cases,
        },
        "budget": {
            "max_target_calls": config.max_target_calls,
            "planned_per_run": done.planned_per_run,
            "spent": done.planned_per_run * len(done.runs),
            "stopped_the_loop": done.budget_stopped,
        },
        "escalation": {"dry_run": config.dry_run, "labels": list(config.labels)},
        "verdict": done.verdict,
        "escalate": done.escalate,
        "reproduced": sorted([case, check] for case, check in done.reproduced),
        "runs": [
            {
                "key": run.key,
                "seed": run.seed,
                "exit_code": run.exit_code,
                "spend": run.spend,
                "explain": run.explain,
            }
            for run in done.runs
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="operator.toml", type=Path)
    parser.add_argument("--out", default="cycle.json", type=Path)
    args = parser.parse_args(argv)

    root = Path(args.config).resolve().parent
    config = load_config(args.config)
    check_cadence(config, root / ".github" / "workflows" / "operator.yml")

    done = cycle(config, root=root)
    document = cycle_json(config, done)
    Path(args.out).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"{done.verdict}: {len(done.runs)} run(s), escalate={done.escalate}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
