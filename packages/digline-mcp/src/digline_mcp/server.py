"""The six tools, and the one that is missing.

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
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from digline.core import Run
from digline.core import compare as compare_runs
from digline.core import diff as diff_runs
from digline.host import (
    git_commit,
    load_suite,
    load_target,
    need_baseline,
    read_artifacts,
    read_run,
    resolve_key,
    utc_now_iso,
)
from digline.report import diff as diff_report
from digline.report import headline
from digline.run import CallPlan, Suite, execute, planned_calls
from digline.store import FileResultStore
from digline.wire import compare_json, diff_json, run_document, run_json, runs_json
from digline_mcp.descriptions import DESCRIPTIONS
from digline_mcp.errors import refuse, translated

__all__ = ["build_server", "main"]

#: Every reading tool declares it. A hint and not enforcement — the enforcement
#: is the absence of `promote` — but a client that surfaces these shows the user
#: the same shape this package describes.
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


def build_server(root: str, tenant: str | None, environment: str | None) -> MCPServer:
    """One server, one repository. The perimeter is the repo. (ADR 0011 §8)

    `tenant` and `environment` **verify** and never override, exactly as the
    CLI's flags do: they are properties of the declared suite, and a command
    line that could override one is how a run ends up filed under the wrong
    customer. As a check they earn their keep — a client config can state what
    it believes it is pointed at and be told when it is wrong.
    """
    perimeter = Path(root).resolve()

    def within_root(spec: str) -> tuple[str, Path]:
        """The spec to load, and the file it names — both inside this root.

        ADR 0011 §8 said "one server, one repository" and nothing enforced it:
        `spec` arrived from a tool call and went straight to `load_suite`, which
        **executes** a `.py`. So every tool here — including the five annotated
        `read_only_hint=True` — was a way to run a file from anywhere on the
        disk. The annotation is what a client reads to decide it may call
        something without asking, which is precisely why this had to become a
        boundary rather than a caution in a docstring.

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
        version="0.1.0",
        instructions=(
            "Read digline results and measure new ones. There is no tool that "
            "promotes a baseline: a baseline is an approved reference, and the "
            "approval is a person's. Assemble the evidence and recommend."
        ),
    )
    store = FileResultStore(root)

    def loaded(spec: str) -> Suite:
        verified, _path = within_root(spec)
        suite, _ = load_suite(verified)
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
        return suite

    def named(suite: Suite, key: str) -> tuple[Run, str]:
        """A run by key or by `latest`. The note the scan produced is dropped
        here and reported by `list_runs`, which is where a caller can act on
        it."""
        resolved = resolve_key(store, suite, key)
        return read_run(store, suite, resolved.key), resolved.key

    @translated
    def list_runs(suite: str) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        listing = store.scan_runs(loaded_suite.tenant, loaded_suite.name)
        baseline = store.read_baseline(loaded_suite.tenant, loaded_suite.name)
        rows = [(ref.key, store.read_run(ref)) for ref in listing.runs]
        return runs_json(
            rows,
            tenant=loaded_suite.tenant,
            suite=loaded_suite.name,
            baseline_key=None if baseline is None else store.key_for(baseline),
            listing=listing,
        )

    @translated
    def get_run(suite: str, run: str = "latest") -> dict[str, Any]:
        loaded_suite = loaded(suite)
        found, key = named(loaded_suite, run)
        return {**run_document(found, loaded_suite.disclosure), "key": key}

    @translated
    def get_baseline(suite: str) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        baseline = need_baseline(store, loaded_suite)
        return {
            **run_document(baseline, loaded_suite.disclosure),
            "key": store.key_for(baseline),
        }

    @translated
    def compare(suite: str, run: str = "latest") -> dict[str, Any]:
        loaded_suite = loaded(suite)
        found, _key = named(loaded_suite, run)
        baseline = need_baseline(store, loaded_suite)
        comparison = compare_runs(found, baseline)
        # `en` and not a parameter: the sentence is a *document* string with a
        # recipient, and an agent is not that recipient. A caller who wants the
        # customer's sentence renders the report, which takes a mandatory locale.
        head = headline(comparison, found, baseline, locale="en")
        return compare_json(comparison, head, full=True)

    @translated
    def diff(suite: str, run1: str, run2: str) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        left, left_key = named(loaded_suite, run1)
        right, right_key = named(loaded_suite, run2)
        if left_key == right_key:
            refuse(
                f"both arguments resolve to the run {left_key}: a run diffed "
                "with itself has nothing to report, because every line of the "
                "answer would be a tautology"
            )
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
        )

    @translated
    def run(suite: str, acknowledge_calls: int | None = None) -> dict[str, Any]:
        loaded_suite = loaded(suite)
        plan = planned_calls(loaded_suite)
        _acknowledge(plan, acknowledge_calls)

        # The clock and git are read here, once, and passed down as values —
        # before the suite's module is imported, because importing writes
        # __pycache__ and asking git afterwards would report a tree our own
        # import had just dirtied.
        commit = git_commit(Path(root))
        created_at = utc_now_iso()
        # The verified path, not the raw spec: `read_artifacts` resolves the
        # suite's declared files against this directory, and taking it from a
        # string that may still carry a `:attribute` was how it could differ
        # from the file that was actually loaded.
        verified, path = within_root(suite)
        _suite, module = load_suite(verified)
        target = load_target(None, module, verified)
        written = execute(
            loaded_suite,
            target,
            created_at=created_at,
            git_commit=commit,
            artifacts=read_artifacts(loaded_suite, target, path.parent, root=perimeter),
        )
        return run_json(store.write_run(written), plan)

    # Registered here rather than through `@server.tool(...)` on each
    # definition. The decorator form leaves every tool a function that is
    # defined and never referenced, which pyright strict reports and which is
    # also, read literally, true — the registration is a side effect. Listing
    # them makes the surface one thing to read: **six entries, and the sixth is
    # not `promote`.**
    for name, fn, hints in (
        ("list_runs", list_runs, READS),
        ("get_run", get_run, READS),
        ("get_baseline", get_baseline, READS),
        ("compare", compare, READS),
        ("diff", diff, READS),
        ("run", run, MEASURES),
    ):
        server.add_tool(
            fn, name=name, description=DESCRIPTIONS[name], annotations=hints
        )
    return server


def _acknowledge(plan: CallPlan, acknowledged: int | None) -> None:
    """The refusal that carries its own answer. (ADR 0011 §2)

    `AGENTS.md` §7 is an obligation to *speak*: say what a hunt will cost before
    starting it. The CLI discharges it by printing to stderr and trusting the
    reader; there is no stderr here and no reader, so it is discharged by making
    the number a parameter that cannot be guessed past.

    **The first call is the probe.** There is deliberately no seventh tool
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


def main(argv: list[str] | None = None) -> int:
    """One server, one repository, over stdio.

    stdio and not SSE or streamable-HTTP: the client launches the process, so
    there is no bound port and no listening socket. Fixed decision 5 is about
    network calls the user did not configure, and a server that listened by
    default would be that mistake facing outward.
    """
    parser = argparse.ArgumentParser(
        prog="digline-mcp",
        description=(
            "MCP server over one digline repository. Reads results and measures "
            "new ones; cannot promote a baseline."
        ),
    )
    parser.add_argument("--root", default=".", help="directory holding .digline/")
    parser.add_argument("--tenant", help="verify the suite's tenant; never overrides")
    parser.add_argument("--env", help="verify the suite's environment; never overrides")
    args = parser.parse_args(argv)
    build_server(args.root, args.tenant, args.env).run(transport="stdio")
    return 0
