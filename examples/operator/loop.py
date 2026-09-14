"""The operator's deterministic half: run, re-run within the declared rule,
classify, and write down what happened.

No model is called here and no key is read. Everything this file produces is
layer 1 and layer 2 of the alert — the machine facts and the record of what the
operator did — and it is reproducible: given the same suite and the same seeds,
it writes the same `cycle.json` twice.

    python loop.py --config operator.toml --out cycle.json

The classification is the judgment `AGENTS.md` writes down, and nothing beyond
it. It cannot promote a baseline and it cannot edit a prompt: it watches the
measurement, and the alert is the handover to whoever repairs the system. And it
does not take the first of those on trust: before it compares anything, it
proves it cannot promote — see "The probe" below.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TextIO, cast

from digline.host import load_suite
from digline.run import planned_calls
from mcp import ClientSession, MCPError, StdioServerParameters, stdio_client
from mcp.types import TextContent

from policy import Policy, digest_of, load_policy

#: The shape of `cycle.json`, so a consumer can tell when it moved. The same
#: idea as digline's own `output_version`, and separate from it: this is the
#: example's file, not the tool's. 2 since each run carries `explain --json`
#: where it carried `compare --json full`; 3 since the cycle carries the probe;
#: 4 since it carries the tenant and the identity of the policy that ruled it —
#: which is what `decide.py` takes a decision under, and what the probe's
#: fourth check compares against the file on disk.
CYCLE_FORMAT = 4

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
    #: The perimeter this cycle belongs to, read off the suite. It is a
    #: directory everywhere else in digline, and it is what says where the
    #: decision journal lives.
    tenant: str = ""


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


def read_policy(path: Path) -> Policy | None:
    """The `[policy]` table, parsed from the same file `load_config` reads.

    Parsed here rather than handed down from `load_config`, and the digest is
    taken over the parsed document by the one function `decide.py` also calls:
    a second spelling of the digest is how a cycle comes to report a policy it
    did not apply, which is the failure the fourth check exists to catch.
    """
    with path.open("rb") as handle:
        document = cast("Mapping[str, Any]", tomllib.load(handle))
    policy = load_policy(document)
    # Asserted rather than assumed: the two have to agree, and they are built
    # by the same call on the same table.
    if policy is not None and policy.digest != digest_of(document["policy"]):
        raise SystemExit("the policy digest is not stable over its own table")
    return policy


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
# The probe: the wall, proved each cycle rather than trusted on its paperwork
# --------------------------------------------------------------------------- #

#: The tool the operator's surface must not have. This is the one place the loop
#: names it, and it names it to the MCP server, expecting to hear that there is
#: no such thing: absence verified at the wire, not read out of a config file.
ABSENT_TOOL = "promote"

#: What the SDK answers for a name the server does not have — and the text of
#: the specification's own example of that error. The one answer that counts
#: as refused.
UNKNOWN = f"Unknown tool: {ABSENT_TOOL}"

PROBE_TIMEOUT = 60

#: What the call to the absent tool came back as. `refused` is `UNKNOWN` and
#: nothing else. `reached` is any other answer from the server — a success, and
#: also a refusal: on this surface the wall *is* the absence, and a `promote`
#: that says no is a policy where the design put nothing to ask. `unobserved`
#: is no answer at all, which is about the instrument and not the wall.
Negative = Literal["refused", "reached", "unobserved"]

#: digline's own trichotomy, applied to the wall instead of a check: it held,
#: it did not, or it could not be judged — and the third is not the first.
Wall = Literal["intact", "collapsed", "inconclusive"]

#: The second wall, and it is a different kind of thing from the first. The
#: operator reads `operator.toml` and never writes it — but on a developer's
#: checkout that file is plainly writable, and reporting *collapsed* every time
#: somebody runs the example would be a probe that cried wolf on its own
#: machine.
#:
#: So it is reported for what it is. `enforced` is a wall this identity cannot
#: cross. `unenforced` is the honest answer on a checkout and on a repository
#: whose owner holds every key: measured against that identity the protection
#: is a **latch**, not a constraint, and DESIGN.md's three rungs already say so
#: out loud. The real wall in a deployment is the push — branch protection and
#: CODEOWNERS on this path — which an example with no protected remote can
#: document and cannot exercise, exactly as it documents the push probe.
PolicyWall = Literal["enforced", "unenforced", "inconclusive"]


@dataclass(frozen=True)
class Probe:
    """One write that must be refused, beside one that must succeed.

    The positive half is what makes the negative mean anything. Refusal alone
    proves nothing: an operator with a broken token, a full disk or a dead
    server is refused everything, and would read that as a wall standing.

    It proves the wall **for the identity that ran it** and for no other. The
    loop runs with the operator's own environment, which is the point: a probe
    run with an administrator's credentials is vacuous by construction.
    """

    negative: Negative
    #: The cycle file, written — an operation the loop owns and must be able to
    #: do.
    positive: bool
    #: Whether anything under `.digline/*/baselines/` or `operator.toml`
    #: differed after the negatives, and was put back before the comparison
    #: could read it.
    rolled_back: bool
    #: The second negative: whether this identity can write the policy it
    #: reads. Reported beside the first rather than folded into it — the two
    #: are different kinds of wall, and an absent tool is not a file mode.
    policy_wall: PolicyWall = "inconclusive"
    #: The fourth check: whether the digest this cycle reports is the digest of
    #: the policy actually on disk. `None` where there is no policy to check.
    #: A cycle that named a policy nobody can produce would be worse than a
    #: cycle that named none.
    digest_matches: bool | None = None

    @property
    def wall(self) -> Wall:
        if self.negative == "reached":
            return "collapsed"
        if self.negative == "refused" and self.positive:
            return "intact"
        return "inconclusive"


def surface(root: Path) -> tuple[str, ...]:
    """The server `.mcp.json` starts, started the way `digline()` starts the
    CLI: from this interpreter, so it needs nothing on PATH."""
    return (sys.executable, "-m", "digline_mcp", "--root", str(root))


def _ask_for_the_absent_tool(server: Sequence[str]) -> Negative:
    async def ask(log: TextIO) -> Negative:
        params = StdioServerParameters(
            command=server[0], args=[*server[1:]], env=dict(os.environ)
        )
        async with asyncio.timeout(PROBE_TIMEOUT):
            async with (
                stdio_client(params, errlog=log) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                # No arguments: a tool that exists and wants some answers with
                # a validation error, and that is still an answer — `reached`.
                try:
                    answer = await session.call_tool(ABSENT_TOOL, {})
                except MCPError as error:  # the specification's shape for it
                    said = error.message
                else:  # the SDK's shape for it: a result flagged as an error
                    if not answer.is_error:
                        return "reached"
                    said = "".join(
                        b.text for b in answer.content if isinstance(b, TextContent)
                    )
                return "refused" if said == UNKNOWN else "reached"

    # The server logs every refusal it makes, so on an intact wall its stderr
    # would put a line saying the tool call failed into a green job's log. Kept,
    # and shown only when there was no answer — the one time it diagnoses
    # anything.
    with tempfile.TemporaryFile("w+", encoding="utf-8") as log:
        try:
            return asyncio.run(ask(log))
        except Exception:  # noqa: BLE001 - no answer at all is the finding
            log.seek(0)
            sys.stderr.write(log.read())
            return "unobserved"


def _baselines(root: Path) -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in root.glob(".digline/*/baselines/**/*")
        if path.is_file()
    }


def _can_write(path: Path) -> PolicyWall:
    """Whether this identity could write `path`, established by trying.

    Opened for **append and closed without writing**, so the test costs the
    file nothing: it is a question about permission, and the answer is not
    worth mutating the policy to learn. Read out of the filesystem rather than
    out of a configuration key, which is the same move the first negative makes
    at the MCP wire.
    """
    try:
        with path.open("a", encoding="utf-8"):
            return "unenforced"
    except PermissionError:
        return "enforced"
    except OSError:
        return "inconclusive"


def probe(
    root: Path,
    out: Path,
    server: Sequence[str],
    *,
    config: Path | None = None,
    expected_digest: str = "",
) -> Probe:
    """Run every half, and undo whatever a negative managed to write.

    Before the comparison, so that a wall which let a baseline through is
    rolled back before anything is measured against it: comparing with a
    reference the operator could have written is the same vacuous green as
    promoting before comparing in CI.

    Four questions, and the last one is new in kind. Three ask whether a wall
    stands; the fourth asks whether the **record is honest** — whether the
    digest this cycle is about to report describes the policy that actually
    ruled it. Without it, a policy swapped between the read and the write would
    produce a cycle naming a policy nobody applied, which is worse than a cycle
    naming none.
    """
    before = _baselines(root)
    kept = None if config is None or not config.is_file() else config.read_bytes()

    negative = _ask_for_the_absent_tool(server)
    policy_wall: PolicyWall = "inconclusive" if config is None else _can_write(config)
    try:
        # Claimed now, written in full when the cycle ends.
        out.write_text("", encoding="utf-8")
        positive = True
    except OSError:
        positive = False

    # The fourth check, against the file as it stands *now* rather than as it
    # was parsed: the two differ exactly when somebody moved it underneath.
    matches: bool | None = None
    if config is not None and expected_digest:
        try:
            with config.open("rb") as handle:
                document = cast("Mapping[str, Any]", tomllib.load(handle))
            found = load_policy(document)
            matches = found is not None and found.digest == expected_digest
        except (OSError, ValueError):
            matches = False

    after = _baselines(root)
    for path in after.keys() - before.keys():
        path.unlink()
    for path, data in before.items():
        if after.get(path) != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    moved = after != before
    if kept is not None and config is not None and config.read_bytes() != kept:
        config.write_bytes(kept)
        moved = True

    return Probe(
        negative,
        positive,
        rolled_back=moved,
        policy_wall=policy_wall,
        digest_matches=matches,
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
        return Cycle(
            tuple(runs),
            "system-error",
            True,
            frozenset(),
            plan.target_calls,
            tenant=suite.tenant,
        )
    if first.exit_code == EXIT_OK:
        return Cycle(
            tuple(runs),
            "clean",
            False,
            frozenset(),
            plan.target_calls,
            tenant=suite.tenant,
        )

    if len(first.cases_regressed) >= config.structural_flip_cases:
        return Cycle(
            tuple(runs),
            "structural",
            True,
            first.regressions,
            plan.target_calls,
            tenant=suite.tenant,
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
        tenant=suite.tenant,
    )


def cycle_json(
    config: Config, done: Cycle, wall: Probe, policy: Policy | None = None
) -> dict[str, Any]:
    """`cycle.json`: layer 1 verbatim, plus the record layer 2 is written from.

    `escalate` is what the **classification** alone concludes, and it keeps
    that meaning: the decision is a separate file, taken by `decide.py` under a
    policy, and a reader comparing the two is reading the whole point — what
    the measurement said, and what somebody's declared rules did about it.
    """
    return {
        "cycle_format": CYCLE_FORMAT,
        "tenant": done.tenant,
        # The identity a decision is taken under, never in `config_hash` and
        # never in a run document: a policy judges the measurement, it does not
        # change what was measured.
        "policy": {
            "name": None if policy is None else policy.name,
            "digest": "" if policy is None else policy.digest,
        },
        "probe": {
            "wall": wall.wall,
            "negative": wall.negative,
            "positive": wall.positive,
            "rolled_back": wall.rolled_back,
            "policy_wall": wall.policy_wall,
            "digest_matches": wall.digest_matches,
        },
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
    policy = read_policy(args.config)

    wall = probe(
        root,
        Path(args.out),
        surface(root),
        config=Path(args.config),
        expected_digest="" if policy is None else policy.digest,
    )
    print(
        f"wall {wall.wall}: {ABSENT_TOOL!r} {wall.negative} at the MCP wire, "
        f"cycle file {'written' if wall.positive else 'NOT written'}"
        + (", baselines rolled back" if wall.rolled_back else "")
    )
    print(
        f"policy wall {wall.policy_wall}: {args.config} is "
        + ("not writable" if wall.policy_wall == "enforced" else "writable")
        + " by this identity"
        + (
            ""
            if wall.digest_matches is None
            else f", digest {'matches' if wall.digest_matches else 'DOES NOT match'}"
        )
    )

    done = cycle(config, root=root)
    document = cycle_json(config, done, wall, policy)
    Path(args.out).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"{done.verdict}: {len(done.runs)} run(s), escalate={done.escalate}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
