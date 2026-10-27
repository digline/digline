"""The eight tools, and the one that is missing.

`promote` is not here. Not disabled, not permission-gated, not refused with a
message: **absent by construction.** There is no function, no name in the tool
list, nothing for a model to attempt and be told no about. A refusal is a
conversation — it can be argued with, retried, worked around by a model that has
decided the refusal is a bug. An absence is not a conversation.

That is the whole thesis, and it is why `AGENTS.md` §1 stops being a rule an
agent is asked to follow and becomes a fact about what the agent can reach. A
baseline is an *approved reference*; `promote` writes into
`.digline/<tenant>/baselines/`, which is committed, so anything landing there
arrives in somebody's diff and must arrive because they put it there.

`migrate`, `view` and `report` are absent on their own reasoning: upgrade
maintenance somebody chose the moment for, and two human-facing documents.
An agent that wants the facts behind the report calls `compare`, which carries
them. (ADR 0011 §1)
"""

from __future__ import annotations

import argparse
import functools
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

# Aliased so `digline_mcp.server.version` does not read as something this
# module exports.
from importlib.metadata import version as _distribution_version
from pathlib import Path
from typing import Any, Literal, NoReturn, get_args

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from digline.core import (
    Minter,
    Run,
    key_of,
    project_check_name,
    project_declared,
    project_served,
)
from digline.core import compare as compare_runs
from digline.core import diff as diff_runs
from digline.core.run import DocumentRefusedError
from digline.host import (
    Loaded,
    NameTable,
    Resolved,
    UsageError,
    explained,
    git_commit,
    history,
    instant,
    load_name_table,
    load_suite,
    load_target,
    measure,
    need_baseline,
    one_table,
    prepare,
    read_artifacts,
    read_pinned,
    read_run,
    refuse_unreadable_baseline,
    resolve_key,
    suite_runs,
    unignored,
    unignored_notes,
    utc_now_iso,
)
from digline.report import diff as diff_report
from digline.report import errored_verdicts, headline
from digline.run import CallPlan, Suite, suite_notes
from digline.store import FileResultStore
from digline.wire import (
    EXIT_USAGE,
    compare_json,
    diff_json,
    explain_json,
    log_json,
    run_document,
    run_json,
    runs_json,
)
from digline_mcp.descriptions import DESCRIPTIONS
from digline_mcp.errors import refuse, translated

__all__ = ["Names", "build_server", "main"]

#: Whether the store's names may leave in clear. **No default**: whose cases are
#: in a store is written nowhere in it, so the operator says. `clear` lets them
#: leave as they always have; `project` projects every answer, and the names
#: leave as tokens. *Refuse* is not a value: not starting a server is a state
#: the operator already has. (ADR 0054 §1, §2)
type Names = Literal["clear", "project"]

#: Read from the installed distribution rather than written here, for the same
#: reason `digline.__version__` is: this is the version the server advertises to
#: every client in its initialize response, and it is a number nobody looks at
#: until it is wrong. Hand-written it also sat outside `test_versions.py`'s
#: sweep, which reads `src/` and not `packages/` — so it was a copy that was
#: neither derived nor gated. The sweep reaches here now too, and this line
#: means it has nothing left to catch.
__version__ = _distribution_version("digline-mcp")

#: Every reading tool declares it. A hint and not enforcement — the enforcement
#: is the absence of `promote` — but a client that surfaces these shows the user
#: the same shape this package describes.
#: This server's log, on its standard error: the person who started the server
#: reads it, and an agent never does. `errors.py` writes to the same one.
_LOG = logging.getLogger("digline_mcp")

READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, open_world_hint=False
)
#: `run` calls a provider, so it is neither read-only nor idempotent, and the
#: world it reaches is open.
MEASURES = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)


@dataclass(frozen=True, slots=True)
class _Opened:
    """A suite spec, resolved against the perimeter and loaded exactly once.

    The three things a tool can need from a spec, kept together so that no
    caller is tempted to recover one of them by loading the file again:
    `loaded` is the `Loaded` — the suite, and the module `load_target` looks
    in; `spec` is the verified form, the path that was actually loaded; `path`
    is the file itself, whose directory is what a suite's declared artifacts
    resolve against.
    """

    loaded: Loaded
    spec: str
    path: Path


def build_server(
    root: str,
    tenant: str | None,
    environment: str | None,
    *,
    names: Names,
    table: NameTable | None,
) -> MCPServer:
    """One server, one repository. The perimeter is the repo. (ADR 0011 §8)

    `names` is the declaration, and `table` the name table it needs under
    `project`. Both keywords are required, with no default, for the
    declaration's own reason. Under `project` with no table this raises a
    `UsageError` that names what is missing and nothing from the store, which
    has not been opened; under `clear`, a table is refused, because a command
    line that hands over a table and says not to use it says two things.
    (ADR 0054 §4)

    `tenant` and `environment` **verify** and never override, exactly as the
    CLI's flags do: they are properties of the declared suite, and a command
    line that could override one is how a run ends up filed under the wrong
    customer. As a check they earn their keep — a client config can state what
    it believes it is pointed at and be told when it is wrong.
    """
    if names not in get_args(Names.__value__):
        raise UsageError(f"--names takes clear or project, not {names!r}")
    if names == "project" and table is None:
        raise UsageError(
            "--names project needs --name-table: under project every answer "
            "is projected, and the tokens come from the name table, which was "
            "not given (ADR 0054 §4)"
        )
    if names == "clear" and table is not None:
        raise UsageError(
            "--name-table is read only under --names project: under clear the "
            "names leave as they are, and a table handed over and not used is "
            "a command line saying two things"
        )
    mint = None if table is None else table.mint
    perimeter = Path(root).resolve()

    def answering() -> Minter | None:
        """The minter for one answer, held to one token per name across every
        document the answer projects, so two runs held against each other
        pair. `None` in clear. (ADR 0054 §7)"""
        return None if mint is None else one_table(mint, where="answer")

    def within_root(spec: str) -> tuple[str, Path]:
        """The spec to load, and the file it names — both inside this root.

        ADR 0011 §8 said "one server, one repository" and nothing enforced it:
        `spec` arrived from a tool call and went straight to `load_suite`, which
        **executes** a `.py`. So every tool here — including the ones annotated
        `read_only_hint=True`, which are the READS below — was a way to run a
        file from anywhere on the disk. The annotation is what a client reads
        to decide it may call something without asking, which is precisely why
        this had to become a boundary rather than a caution in a docstring.

        The rule is stricter than the loader's on purpose: **the spec must name
        a file inside the root.** That refuses the traversal, and it also
        refuses the dotted-module form, which resolves through `sys.path` and
        therefore names something this server cannot place inside the
        repository at all. A suite reachable only as an installed module is
        reachable by the CLI, which is a person's tool and has no perimeter to
        keep.
        """
        # Same rule as the loader's own `_split`: only a trailing `:name`
        # counts, and only when `name` is an identifier — so a Windows path
        # like `C:\suites\qa.py` keeps its drive letter.
        head, sep, tail = spec.rpartition(":")
        stem, attr = (head, tail) if sep and tail.isidentifier() else (spec, "")
        # An absolute `stem` wins over `perimeter` here, which is what makes the
        # containment check below meaningful rather than decorative.
        path = (perimeter / stem).resolve()
        if not path.is_relative_to(perimeter):
            refuse(
                f"the suite {spec!r} resolves to {path}, which is outside "
                f"{perimeter}: one server, one repository (ADR 0011 §8). "
                "Name a suite inside this repository, or start a second "
                "server rooted where that one lives."
            )
        if not path.is_file():
            refuse(
                f"the suite {spec!r} names no file inside {perimeter} "
                f"(looked at {path}). This server takes a path to a suite "
                "within its own repository — not a module to import, because "
                "a module resolves through `sys.path` and could be anywhere."
            )
        return (f"{path}:{attr}" if attr else str(path)), path

    server = MCPServer(
        name="digline",
        version=__version__,
        instructions=(
            "Read digline results and measure new ones. There is no tool that "
            "promotes a baseline: a baseline is an approved reference, and the "
            "approval is a person's. Assemble the evidence and recommend."
        ),
    )
    store = FileResultStore(root)

    def opened(spec: str) -> _Opened:
        """Resolve the spec and load it — **once**, whatever the caller needs.

        A suite is a `.py` this server executes, so loading it twice ran the
        user's module twice: two sets of import-time side effects for one tool
        call. `run` used to take the suite from here and then load the file
        again for the module, which is why this returns the whole `Loaded`
        rather than only the `Suite`.
        """
        verified, path = within_root(spec)
        form = load_suite(verified, root=perimeter)[1]
        suite = form.suite
        if tenant is not None and tenant != suite.tenant:
            refuse(
                f"--tenant {tenant!r} does not match the suite, which declares "
                f"{suite.tenant!r}. The suite decides; this only verifies."
            )
        if environment is not None and environment != suite.environment:
            refuse(
                f"--env {environment!r} does not match the suite, which declares "
                f"{suite.environment!r}. The suite decides; this only verifies."
            )
        return _Opened(loaded=form, spec=verified, path=path)

    def loaded(spec: str) -> Suite:
        """The suite alone, for the tools that only read."""
        return opened(spec).loaded.suite

    def named(suite: Suite, key: str) -> tuple[Run, Resolved]:
        """A run by key or by `latest`, and what resolving it stepped over.

        The note goes into the answer of every tool that resolves a run.
        `list_runs` carries the scan's part of it and not the part that
        depends on which run `latest` picked: a baseline or a register line
        naming a run newer than the pick. Without it, `compare` on that pick
        holds an older run against a newer reference, and its `worse` is the
        past rather than a regression. (#433)
        """
        resolved = resolve_key(store, suite, key)
        return read_run(store, suite, resolved.key), resolved

    @translated
    def list_runs(suite: str) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        # A run the store refuses is left out and counted, rather than failing
        # the tool for every run beside it. (#314)
        listed = suite_runs(store, loaded_suite.tenant, loaded_suite.name, mint=mint)
        # In clear the scan is there and `runs_json` reads it whole. Projected
        # it is withheld, because it holds file names, and the counts stand in
        # its place. (#362; ADR 0054 §7)
        counts: dict[str, Any] = (
            {}
            if listed.listing is not None
            else {
                "skipped": listed.skipped,
                "unreadable": listed.unreadable_count,
                "misfiled": listed.misfiled,
            }
        )
        return runs_json(
            listed.runs,
            tenant=loaded_suite.tenant,
            suite=loaded_suite.name,
            baseline_key=listed.baseline_key,
            listing=listed.listing,
            note=listed.note(),
            refused=len(listed.refused),
            baseline_unreadable=bool(listed.baseline_refused),
            **counts,
        )

    @translated
    def get_run(suite: str, run: str = "latest") -> dict[str, Any]:
        loaded_suite = loaded(suite)
        found, resolved = named(loaded_suite, run)
        shown = _projected(found, answering())
        return {
            **run_document(shown, loaded_suite.disclosure, note=resolved.note),
            "key": resolved.key,
        }

    @translated
    def get_baseline(suite: str) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        baseline = need_baseline(store, loaded_suite)
        return {
            **run_document(_projected(baseline, answering()), loaded_suite.disclosure),
            "key": key_of(baseline.created_at, baseline.config_hash),
        }

    @translated
    def compare(suite: str, run: str = "latest") -> dict[str, Any]:
        loaded_suite = loaded(suite)
        found, resolved = named(loaded_suite, run)
        baseline = need_baseline(store, loaded_suite)
        declared = loaded_suite.declared()
        # Every input through one table before anything is composed from it,
        # so the headline's sentence names checks and cases by the tokens the
        # runs carry. (ADR 0054 §7)
        table_ = answering()
        if table_ is not None:
            found = project_served(found, table_)
            baseline = project_served(baseline, table_)
            declared = project_declared(declared, table_)
        comparison = compare_runs(found, baseline)
        # `en` and not a parameter: the sentence is a *document* string with a
        # recipient, and an agent is not that recipient. A caller who wants the
        # customer's sentence renders the report, which takes a mandatory locale.
        head = headline(
            comparison,
            found,
            baseline,
            locale="en",
            declared=declared,
        )
        return compare_json(
            comparison,
            head,
            baseline=baseline,
            full=True,
            note=resolved.note,
            run=found,
        )

    @translated
    def diff(suite: str, run1: str, run2: str) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        left, left_side = named(loaded_suite, run1)
        right, right_side = named(loaded_suite, run2)
        left_key, right_key = left_side.key, right_side.key
        if left_key == right_key:
            refuse(
                f"both arguments resolve to the run {left_key}: a run diffed "
                "with itself has nothing to report, because every line of the "
                "answer would be a tautology"
            )
        table_ = answering()
        if table_ is not None:
            left = project_served(left, table_)
            right = project_served(right, table_)
        difference = diff_runs(left, right)
        labels = diff_report.run_labels(
            left.created_at, right.created_at, left_key=left_key, right_key=right_key
        )
        return diff_json(
            difference,
            left,
            right,
            keys=(left_key, right_key),
            labels=labels,
            sentence=diff_report.sentence(difference, locale="en", labels=labels),
            full=True,
            notes=(left_side.note, right_side.note),
        )

    @translated
    def explain(suite: str, run: str = "latest") -> dict[str, Any]:
        # The CLI's composition, from the host, so the two cannot come to read
        # one run differently. No locale: the fact list ships no prose, so there
        # is nothing to localise and nothing to choose. (ADR 0020 §8)
        loaded_suite = loaded(suite)
        resolved = resolve_key(store, loaded_suite, run)
        read = explained(store, loaded_suite, resolved.key, mint=mint)
        return {
            **explain_json(
                read.reading,
                scope=read.scope,
                exit_code=read.exit_code,
                note=resolved.note,
                run=read.run,
                baseline=read.baseline,
            ),
            # Before `run_key`, which now names the same run from inside the
            # document. Kept because an agent reads it: removing a key is a
            # change, not an addition, and waits for a bump. (#448)
            "key": resolved.key,
        }

    @translated
    def log(
        suite: str, since: str | None = None, until: str | None = None
    ) -> dict[str, Any]:
        # A read, and never a gate: there is no exit code in the answer because
        # a roll is not a verdict. The configuration was reduced inside the
        # fold, so nothing a named endpoint keeps back reaches this response.
        # (ADR 0020 §5, §6)
        loaded_suite = loaded(suite)
        return log_json(
            history(
                store,
                loaded_suite,
                since=instant(since, name="since"),
                until=instant(until, name="until"),
                mint=mint,
            )
        )

    @translated
    def run(
        suite: str,
        acknowledge_calls: int | None = None,
        accepting_baseline_schema: int | None = None,
    ) -> dict[str, Any]:
        # One `opened` for the whole tool: the plan below needs the suite and
        # the target needs the module, and they come from the same load.
        open_ = opened(suite)
        loaded_suite = open_.loaded.suite

        # The clock and git are read here, once, and passed down as values, so
        # the run is a function of them rather than of when it happened to look.
        commit = git_commit(Path(root))
        created_at = utc_now_iso()
        # The verified spec and its path, not the raw one: `read_artifacts`
        # resolves the suite's declared files against this directory, and
        # taking it from a string that may still carry a `:attribute` was how
        # it could differ from the file that was actually loaded.
        target = load_target(None, open_.loaded, open_.spec)
        artifacts = read_artifacts(
            loaded_suite, target, open_.path.parent, root=perimeter
        )
        # And the pins, by the same reading: `execute` refuses a pinning suite
        # handed no pin set, so this front end cannot record a control that
        # cannot fire. (ADR 0029 §4)
        pinned = read_pinned(
            loaded_suite, open_.path.parent, root=perimeter, artifacts=artifacts
        )

        # The composition the CLI already sits on, and that is the whole point
        # of it being here: journalling is wired once in `digline.host` rather
        # than once per front end, so a killed MCP-launched run now leaves a
        # journal the CLI can finish. Wired here rather than with the release
        # that built it because a floor cannot name a version that does not
        # exist yet. (ADR 0017 §11)
        #
        # **`resume=None`, and no verb can make it anything else.** This surface
        # gains no `resume` tool: it would be a second way to spend money
        # without the acknowledged count, which is the one thing ADR 0011 §2
        # refuses. One consequence is worth stating rather than discovering —
        # every refusal `prepare` carries lives on the resume branch, so it
        # cannot raise `JournalRefusedError` here, and `errors.TRANSLATED` needs
        # nothing added for it.
        # Before the plan and before the count: a run whose comparison cannot
        # be read is refused before an agent is asked to type back a number of
        # calls that will not be made. The way through is the schema by number,
        # which expires by itself, and over this server it is this tool's
        # parameter; the core's sentence names the command line's flag, so the
        # parameter is named after it. (#707; ADR 0014 §5)
        try:
            refuse_unreadable_baseline(
                store, loaded_suite, accepting_schema=accepting_baseline_schema
            )
        except DocumentRefusedError as exc:
            if exc.declared_schema is None or accepting_baseline_schema is not None:
                raise
            refuse(
                f"{exc}. Over this server the same acceptance is "
                f"accepting_baseline_schema={exc.declared_schema} on this tool, "
                "and it is the person's decision, never yours to take on your "
                "own initiative"
            )
        prepared = prepare(
            loaded_suite,
            target,
            now=created_at,
            git_commit=commit,
            artifacts=artifacts,
            pinned=pinned,
        )
        # The plan as this answer may name it: its sentence names the checks
        # it repeats and judges, and under `project` they are the tokens the
        # run will carry, in the refusal below as in the answer. (ADR 0054 §8)
        table_ = answering()
        # Still before anything is opened or called, and still the same number:
        # `prepare` plans the calls it is about to make, so the count a caller
        # has to type back is read off the plan rather than computed twice.
        _acknowledge(_plan_named(prepared.plan, table_), acknowledge_calls)
        measured = measure(
            loaded_suite,
            target,
            store=store,
            prepared=prepared,
            artifacts=artifacts,
            pinned=pinned,
            # The process this server is, long-lived, is the case ADR 0052 was
            # written for. (decision 2)
            modules_unchecked=open_.loaded.modules_unchecked,
            accepting_baseline_schema=accepting_baseline_schema,
        )
        # In this server's log, which the person who started it reads, and not
        # in the answer: whether a directory is committed is the operator's
        # business, not a fact about the run. After the write, as the CLI asks
        # it, so the first run's generated rules exist. (#523)
        for note in unignored_notes(
            loaded_suite.tenant, unignored(perimeter, loaded_suite.tenant)
        ):
            _LOG.warning("digline: %s", note)
        # `usage=` as the CLI passes it: what the run consumed is one fact, and
        # a caller must not have to know which front end it asked. The parity
        # test in this package is what noticed it was missing. (ADR 0011 §6)
        # `notes=` as the CLI passes it, and for the same reason as `usage=`:
        # over MCP there is no stderr, so the lines `digline run` prints there
        # before the first call reach an agent only as a field. (#396; ADR 0011
        # §4, ADR 0024 §6.4)
        return run_json(
            measured.ref,
            _plan_named(measured.plan, table_),
            usage=measured.run.usage,
            notes=suite_notes(loaded_suite, mint=table_),
            # The count `digline run --json` carries, from the same function,
            # so the two key sets stay equal. (#654)
            errored_checks=len(errored_verdicts(measured.run)),
        )

    # Registered here rather than through `@server.tool(...)` on each
    # definition. The decorator form leaves every tool a function that is
    # defined and never referenced, which pyright strict reports and which is
    # also, read literally, true — the registration is a side effect. Listing
    # them makes the surface one thing to read: **eight entries, and none of
    # them writes.** `explain` and `log` arrived together so the count moved
    # once. (ADR 0020 §9)
    for name, fn, hints in (
        ("list_runs", list_runs, READS),
        ("get_run", get_run, READS),
        ("get_baseline", get_baseline, READS),
        ("log", log, READS),
        ("compare", compare, READS),
        ("diff", diff, READS),
        ("explain", explain, READS),
        ("run", run, MEASURES),
    ):
        server.add_tool(
            _flushed(fn),
            name=name,
            description=DESCRIPTIONS[name],
            annotations=hints,
        )
    return server


def _projected(run: Run, mint: Minter | None) -> Run:
    """`run` as this answer may show it: as read in clear, `project_served`
    under `project`. (ADR 0054 §7)"""
    return run if mint is None else project_served(run, mint)


def _plan_named(plan: CallPlan, mint: Minter | None) -> CallPlan:
    """`plan` with the checks it names by their tokens under `project`, so its
    sentence is composed from them: the fields first, the sentence after.
    The tenant stays, as a projection leaves it. (ADR 0054 §8, §9)"""
    if mint is None:
        return plan
    return replace(
        plan,
        repeats=tuple(
            (project_check_name(check, mint), count) for check, count in plan.repeats
        ),
        judged=tuple(project_check_name(check, mint) for check in plan.judged),
    )


def _flushed(tool: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """The tool, with what the user's code printed during it written out before
    it answers.

    Standard output is the protocol here (ADR 0011 §8), and what the suite,
    the application it imports, a target or a judge prints is assigned to
    standard error (ADR 0043 §8, amended 2026-10-18). While it serves, the SDK
    points descriptor 1 at standard error and writes the protocol to a private
    copy. What Python holds in `sys.stdout`'s buffer is written to descriptor 1
    when it is flushed, so flushed here, at the end of every call, it reaches
    standard error. Left to the interpreter's exit, it was written after the
    SDK had pointed the descriptor back, onto the protocol.

    At the one place every tool is registered, so a tool added to the list is
    covered without anybody remembering it. The signature is the tool's own
    (`functools.wraps`), and the SDK builds each tool's schema from it.
    **What it does not reach** is written after the last call's flush and
    before the interpreter exits: a thread of the user's printing later, an
    `atexit` handler, a `__del__`. The amendment declares those.
    """

    @functools.wraps(tool)
    def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return tool(*args, **kwargs)
        finally:
            sys.stdout.flush()

    return call


def _acknowledge(plan: CallPlan, acknowledged: int | None) -> None:
    """The refusal that carries its own answer. (ADR 0011 §2)

    `AGENTS.md` §7 is an obligation to *speak*: say what a hunt will cost before
    starting it. The CLI discharges it by printing to stderr and trusting the
    reader; there is no stderr here and no reader, so it is discharged by making
    the number a parameter that cannot be guessed past.

    **The first call is the probe.** There is deliberately no extra tool
    returning the plan: a tool an agent could call, read, and never act on the
    number of would make the acknowledgement a courtesy again. Here the only way
    to learn the number is to be refused for not knowing it, and the only way to
    proceed is to type it back.

    It is `target_calls` and nothing else. `CallPlan` does not fold judge
    repeats into one multiplier, because nothing in the core claims to know
    which assertions call a model — so the scope is stated rather than guessed,
    and `sentence()` carries the repeats a caller has to include when reporting
    the spend.
    """
    expected = plan.target_calls
    if acknowledged == expected:
        return
    if acknowledged is None:
        refuse(
            f"this suite plans {expected} calls to the target. {plan.sentence()}. "
            f"Call again with acknowledge_calls={expected} to run it. The count "
            "is calls to the target; where an assertion judges each answer "
            "several times the sentence above names the multiplier, and that is "
            "the figure to report."
        )
    refuse(
        f"acknowledge_calls={acknowledged} does not match this suite, which "
        f"plans {expected} calls to the target. {plan.sentence()}. A suspended "
        "case is not counted, because it is never called."
    )


#: Where `_Once` keeps every value an option was given while a command line is
#: read. `_Parser.parse_known_args` removes it before the namespace is
#: returned, so no reader ever sees it.
_GIVEN = "_digline_given_"


class _Once(argparse.Action):
    """`store`, keeping every value an option was given on the way.

    The value is stored as `store` stores it, so an option reads as it always
    did. Each one is also kept, under a reserved name, for
    `_Parser.parse_known_args` to compare once the line is read. (#567)
    """

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: Any = None,
        const: Any = None,
        **kwargs: Any,
    ) -> None:
        # The checks `store`'s own class makes, which this one does not inherit.
        if nargs == 0:
            raise ValueError(
                f"{dest}: an option that stores a value cannot take zero of them; "
                "a flag is `store_true` or `store_const`"
            )
        if const is not None and nargs != argparse.OPTIONAL:
            raise ValueError(
                f"{dest}: a `const` is the value of an option given with none, "
                f"so it needs `nargs={argparse.OPTIONAL!r}`"
            )
        super().__init__(option_strings, dest, nargs=nargs, const=const, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, values)
        key = _GIVEN + self.dest
        given: list[tuple[str, object]] = getattr(namespace, key, [])
        # A positional has no option string, and is consumed once anyway.
        name = self.option_strings[-1] if self.option_strings else self.dest
        setattr(namespace, key, [*given, (name, values)])


class _Parser(argparse.ArgumentParser):
    """argparse's parser, refusing a command line with the usage code.

    `error()` is argparse's own body with one number changed: 64, `EXIT_USAGE`,
    where argparse exits 2, which is `EXIT_UNJUDGED`. The same rule as the
    `digline` command line's, where ADR 0008 §1 declares it: this is a second
    program with a parser of its own. `exit()` is left alone: `--help` ends
    the process through it with 0, and that is an answer, not a refusal.

    **And it refuses an option given different values.** argparse keeps the
    last value of a repeated option and drops the others without a word, so
    `--suite a.py --suite b.py` measured `b.py` and never said `a.py` was gone
    (#567). A command line that says two things at once is the person's
    mistake, and guessing which one they meant is deciding for them in silence.
    The same value twice drops nothing and passes; values are compared as
    stored, after `type=`. An option declared `append` is repeatable by
    choice, and a flag takes no value, so neither is touched.

    **One place, not a list.** The constructor makes `_Once` the default
    action, for every `add_argument` without an `action=` and for an explicit
    `"store"`. An option added tomorrow is covered without anybody remembering
    to mark it, where `action=` on each option would be a list that ages.
    `register` is a public method of argparse but not a documented one. If it
    went away the parser would fail on the first command with an
    `AttributeError`, not quietly; if it stayed and stopped being consulted,
    the tests that repeat every option would go red.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.register("action", None, _Once)
        self.register("action", "store", _Once)

    # This accepts any namespace and returns `Any`. argparse's stub overloads
    # the method on the namespace's type, and the checker cannot match this
    # one signature to those overloads.
    def parse_known_args(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, args: Sequence[str] | None = None, namespace: Any = None
    ) -> tuple[Any, list[str]]:
        parsed, extras = super().parse_known_args(args, namespace)
        for key in [name for name in vars(parsed) if name.startswith(_GIVEN)]:
            given: list[tuple[str, object]] = getattr(parsed, key)
            delattr(parsed, key)
            values = [value for _, value in given]
            if any(value != values[0] for value in values[1:]):
                named = ", ".join(repr(value) for value in values)
                self.error(
                    f"argument {given[0][0]}: given different values ({named}); "
                    "it takes one, so give it once"
                )
        return parsed, extras

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    """One server, one repository, over stdio.

    stdio and not SSE or streamable-HTTP: the client launches the process, so
    there is no bound port and no listening socket. Fixed decision 5 is about
    network calls the user did not configure, and a server that listened by
    default would be that mistake facing outward.
    """
    parser = _Parser(
        prog="digline-mcp",
        description=(
            "MCP server over one digline repository. Reads results and measures "
            "new ones; cannot promote a baseline."
        ),
    )
    # Required, with no `.` to fall back on: every tool, the reading ones
    # included, loads the suite it is named under this root, and a `suite.py`
    # is the project's code. An implicit `.` is the working directory the
    # client happened to launch from, which is how the suite of the wrong
    # directory gets run. `server.json` declares it required as well.
    parser.add_argument(
        "--root", required=True, help="directory holding .digline/ (required)"
    )
    parser.add_argument("--tenant", help="verify the suite's tenant; never overrides")
    parser.add_argument("--env", help="verify the suite's environment; never overrides")
    # Required, with no default: whether a store's names may leave in clear
    # depends on whose cases are in it, and nothing in a store says. A
    # configuration that passes `--root` alone no longer starts, as one that
    # left out `--root` stopped starting when it became required. (ADR
    # 0054 §1, §5)
    parser.add_argument(
        "--names",
        required=True,
        choices=get_args(Names.__value__),
        help="whether the store's names may leave in clear (required)",
    )
    parser.add_argument(
        "--name-table",
        help="module:attribute holding the name table's mint and lookup; "
        "required under --names project",
    )
    args = parser.parse_args(argv)
    # Before the store is opened, so neither refusal can name anything in it:
    # what is missing is configuration. (ADR 0054 §4)
    if args.names == "project" and args.name_table is None:
        parser.error(
            "--names project needs --name-table: the tokens come from the name "
            "table, and none was given"
        )
    if args.names == "clear" and args.name_table is not None:
        parser.error(
            "--name-table is read only under --names project; under clear the "
            "names leave as they are"
        )
    try:
        table = None if args.name_table is None else load_name_table(args.name_table)
    except UsageError as exc:
        parser.error(str(exc))
    build_server(args.root, args.tenant, args.env, names=args.names, table=table).run(
        transport="stdio"
    )
    return 0
