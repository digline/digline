"""The command line: the last layer, and the only one that touches the world.

Four commands, each doing one thing:

    digline run     --suite S [--target T] [--meta k=v]…
    digline list    --suite S
    digline migrate --suite S [--dry-run]
    digline compare --suite S --run KEY|latest [--locale L] [--json [full]]
    digline promote --suite S --run KEY|latest
    digline report  --suite S --run KEY|latest --locale L [--out F] [--redacted]
    digline view    --suite S [--host H] [--port P]

`run` writes a run and prints its key. `compare` reads and judges. `promote`
promotes. `report` renders. `migrate` brings stored documents up to the current
schema. Nothing promotes as a side effect of anything else.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import ModuleType

from digline.cli.environment import git_commit, utc_now_iso
from digline.cli.loader import UsageError, load_suite, load_target
from digline.cli.view import serve
from digline.core import (
    Artifact,
    AssertionDelta,
    Run,
    compare,
    redact,
    withhold_artifacts,
)
from digline.report import (
    Headline,
    artifact_lines,
    headline,
    render_html,
    summary_lines,
)
from digline.run import Suite, execute
from digline.store import (
    ConfigMismatchError,
    ErroredRunError,
    FileResultStore,
    RunRef,
    TenantMismatchError,
    migrate_paths,
)

__all__ = [
    "EXIT_OK",
    "EXIT_UNJUDGED",
    "EXIT_USAGE",
    "EXIT_WORSE",
    "OUTPUT_VERSION",
    "exit_code",
    "main",
]

#: The shape of what `--json` prints, and nothing to do with `SCHEMA_VERSION`.
#:
#: Two contracts, two lifetimes. `SCHEMA_VERSION` is about documents already on
#: disk, which is why it comes with migrations: a file written last month must
#: still be readable. This one is about what a pipeline parses on stdout today,
#: where nothing needs migrating and the only question is whether the consumer
#: knows the shape moved. Tying them together would mean a reworded sentence
#: bumping the storage schema, and a new field inside a `Run` bumping the output
#: contract for consumers who saw no change.
#:
#: 1: `worse`, `unjudged`, `suspended`, `config_changed`, `artifacts_changed`,
#:    `counts`, `reasons_available`, `sentence`; `deltas` under `--json full`.
OUTPUT_VERSION = 1

EXIT_OK = 0
EXIT_WORSE = 1
EXIT_UNJUDGED = 2
EXIT_USAGE = 64

LOCALES: tuple[str, ...] = ("en", "it")

RUN_HELP = "a run key, or 'latest' for the most recent run of this suite"


def exit_code(head: Headline) -> int:
    """The one place a headline becomes a number.

    Precedence is deliberate: **a regression outranks an unjudged case.** Both
    need attention, but a regression is a statement about behaviour that got
    worse, while an unjudged case is a statement about the harness. When both
    are true the louder fact must be the one the pipeline reports, or a real
    regression would hide behind a flaky provider.

    A suspension never fails: it is a decision someone already made, not an
    outcome.
    """
    if head.worse:
        return EXIT_WORSE
    if head.unjudged:
        return EXIT_UNJUDGED
    return EXIT_OK


def read_artifacts(suite: Suite, base: Path) -> dict[str, Artifact]:
    """The declared files, as they are right now.

    Here rather than in the driver for the same reason the clock and git are
    here: this is the layer allowed to touch the world, and a driver that opened
    files would need one to be tested. Relative paths resolve against the
    suite's own directory, which is where a prompt sits next to the suite that
    names it.

    A declared file that is missing raises. It is the thing under examination —
    a run that quietly recorded no prompt would be a run whose evidence is
    absent exactly when it matters.
    """
    found: dict[str, Artifact] = {}
    for declared in suite.artifacts:
        path = declared if declared.is_absolute() else base / declared
        if not path.is_file():
            raise UsageError(
                f"suite {suite.name!r} declares the artifact {declared}, which "
                f"is not a file at {path}: the thing under test cannot be "
                "recorded, so the run would not say what produced it"
            )
        data = path.read_bytes()
        found[str(declared)] = Artifact(
            sha=hashlib.sha256(data).hexdigest(),
            text=data.decode("utf-8"),
        )
    return found


def _meta(pairs: Sequence[str]) -> Mapping[str, object]:
    """`--meta k=v`, repeatable. Values stay strings: a command line gives
    strings, and guessing at types would make `1499` arrive as a number that
    `travels()` would then wave through from `Score.metadata`."""
    out: dict[str, object] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise UsageError(f"--meta expects key=value, got {pair!r}")
        out[key] = value
    return out


def _check_perimeter(suite: Suite, tenant: str | None, environment: str | None) -> None:
    """`--tenant` and `--env` verify; they do not override.

    They are properties of the declared suite (ADR 0002 §1), and a command-line
    override is exactly how a run ends up filed under the wrong customer. As a
    check they earn their keep: a CI job can state what it believes it is
    running and be told when it is wrong.
    """
    if tenant is not None and tenant != suite.tenant:
        raise UsageError(
            f"--tenant {tenant!r} does not match the suite, which declares "
            f"{suite.tenant!r}. The suite decides; this flag only verifies."
        )
    if environment is not None and environment != suite.environment:
        raise UsageError(
            f"--env {environment!r} does not match the suite, which declares "
            f"{suite.environment!r}. The suite decides; this flag only verifies."
        )


def _load(args: argparse.Namespace) -> tuple[Suite, ModuleType, FileResultStore]:
    """Imported once per command: importing twice would execute the user's
    module twice, and a module with a side effect would perform it twice."""
    suite, module = load_suite(args.suite)
    _check_perimeter(suite, args.tenant, args.env)
    return suite, module, FileResultStore(args.root)


LATEST = "latest"


def _resolve_key(store: FileResultStore, suite: Suite, key: str) -> str:
    """`--run latest` means the most recent run of this suite in this perimeter.

    Not a guess and not a default: `--run` stays mandatory, and `latest` is a
    value the caller types. It exists because copying a key by hand right after
    `run` printed it is the friction of minute three, and a tool people abandon
    at minute three has no other qualities worth discussing.

    Resolved over a **scan**, which steps over documents this version cannot
    read. A stored history outlives the schema that wrote it, and the morning
    after a release `latest` used to fail on yesterday's files — a refusal about
    a run nobody had asked for. What was skipped is stated, never swallowed.

    Within what can be read, the newest is chosen on `created_at`, the recorded
    fact, rather than on the filename that encodes it.
    """
    if key != LATEST:
        return key
    listing = store.scan_runs(suite.tenant, suite.name)
    if not listing.runs:
        # Two different situations, and telling them apart is the whole value of
        # the message: an empty store needs a run, a store full of old schemas
        # needs a migration. "No readable runs" on an empty store would suggest
        # unreadable ones exist.
        if listing.skipped or listing.unreadable:
            raise UsageError(
                f"no readable runs stored for suite {suite.name!r} in tenant "
                f"{suite.tenant!r} — {listing.note()}. "
                "Run `digline migrate` to bring them up to date."
            )
        raise UsageError(
            f"no runs stored for suite {suite.name!r} in tenant {suite.tenant!r}, "
            "so there is no latest one. Run it first."
        )
    if listing.skipped:
        # On stderr: `latest` is resolved inside commands whose stdout may be
        # JSON, and a note that broke a pipeline would teach people to ignore it.
        print(f"note: {listing.note()}", file=sys.stderr)
    newest = max(
        (store.read_run(ref) for ref in listing.runs), key=lambda r: r.created_at
    )
    return store.key_for(newest)


def _read_run(store: FileResultStore, suite: Suite, key: str) -> Run:
    return store.read_run(RunRef(tenant=suite.tenant, suite=suite.name, key=key))


def _need_baseline(store: FileResultStore, suite: Suite) -> Run:
    baseline = store.read_baseline(suite.tenant, suite.name)
    if baseline is None:
        raise UsageError(
            f"suite {suite.name!r} has no baseline for tenant {suite.tenant!r} yet. "
            "Run it, look at the result, then 'digline promote --run <key>'."
        )
    return baseline


def cmd_run(args: argparse.Namespace) -> int:
    # The clock and git are read here and nowhere else, then passed down as
    # plain values so everything below stays reproducible.
    #
    # Read *before* the suite is imported: importing a Python module writes
    # `__pycache__`, so asking git afterwards would report a tree our own import
    # had just dirtied. The marker describes the repository as the user left it.
    commit = git_commit(Path(args.root))
    created_at = utc_now_iso()

    suite, module, store = _load(args)
    target = load_target(args.target, module, args.suite)

    run = execute(
        suite,
        target,
        created_at=created_at,
        git_commit=commit,
        run_metadata=_meta(args.meta),
        artifacts=read_artifacts(suite, Path(args.suite).resolve().parent),
    )
    ref = store.write_run(run)

    if args.json:
        print(
            json.dumps(
                {
                    "output_version": OUTPUT_VERSION,
                    "key": ref.key,
                    "tenant": ref.tenant,
                    "suite": ref.suite,
                }
            )
        )
    else:
        # Only the key on stdout, so a shell can capture it:
        #   KEY=$(digline run --suite …)
        print(ref.key)
    return EXIT_OK


#: How many regressions a terminal shows before pointing at the report. Not a
#: silent cut: `summary_lines` says how many it left out.
SUMMARY_LIMIT = 20


def _delta_json(delta: AssertionDelta) -> dict[str, object]:
    """The structured facts, and deliberately **not** the verdict's `reason`.

    A reason is payload, and stdout of a CI job is a place logs go and stay. A
    pipeline that genuinely needs the judge's words can read the run file, from
    inside the perimeter where it is allowed to.

    `scope` is emitted even though a run-scoped delta always carries
    `case_id == ""`: deriving the kind of a delta from an empty string asks the
    consumer to know a convention instead of reading a field, and an empty
    `case_id` is equally what a malformed one would look like.
    """
    before = None if delta.baseline is None else delta.baseline.score.score
    after = None if delta.current is None else delta.current.score.score
    return {
        "case_id": delta.case_id,
        "scope": delta.scope,
        "assertion": delta.assertion,
        "outcome": delta.outcome,
        "before": before,
        "after": after,
        "delta": delta.delta,
    }


def cmd_compare(args: argparse.Namespace) -> int:
    suite, _module, store = _load(args)
    run = _read_run(store, suite, _resolve_key(store, suite, args.run))
    baseline = _need_baseline(store, suite)

    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale=args.locale)

    if args.json:
        # The headline, not the document: a pipeline wants the facts, and the
        # sentence it carries is the same one a customer will read.
        payload: dict[str, object] = {"output_version": OUTPUT_VERSION}
        payload.update(dataclasses.asdict(head))
        if args.json == "full":
            payload["deltas"] = [_delta_json(d) for d in comparison.deltas]
        print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
        return exit_code(head)

    print(head.sentence)
    # What was under test, before what it did: a prompt that moved changes how
    # every line below it reads, and learning that afterwards is learning it too
    # late. The tally only — the diff is in the report, one command away.
    moved = artifact_lines(comparison, locale=args.locale)
    if moved:
        print()
        for line in moved:
            print(f"  {line}")
    # Then *which* ones. "1 check got worse" without naming it sends the reader
    # to open an HTML file to learn a fact that fits on one line.
    lines = summary_lines(
        comparison, run, baseline, locale=args.locale, limit=SUMMARY_LIMIT
    )
    if lines:
        print()
        for line in lines:
            print(line)
    return exit_code(head)


def _short_commit(commit: str | None) -> str:
    if commit is None:
        return "-"
    sha, dirty, _ = commit.partition("-dirty")
    return f"{sha[:7]}{'-dirty' if dirty else ''}"


def cmd_list(args: argparse.Namespace) -> int:
    """Every stored run of this suite, newest first, with the baseline marked.

    Deliberately without filters. `--run KEY` is mandatory everywhere else and
    only `run` prints a key, so without this a developer who came back the next
    day had no way to name yesterday's run. That is the whole job; anything more
    would be inventing a surface before knowing what it is for.
    """
    suite, _module, store = _load(args)

    baseline = store.read_baseline(suite.tenant, suite.name)
    baseline_key = None if baseline is None else store.key_for(baseline)

    listing = store.scan_runs(suite.tenant, suite.name)
    rows = [store.read_run(ref) for ref in listing.runs]
    # Sorted on the recorded fact, not on the filename that encodes it.
    rows.sort(key=lambda run: run.created_at, reverse=True)

    if not rows:
        print(f"no runs for suite {suite.name!r} in tenant {suite.tenant!r}")
        if listing.skipped or listing.unreadable:
            print(listing.note())
            print("run `digline migrate` to bring stored runs up to date")
        return EXIT_OK

    print(f"  {'KEY':<49}  {'CREATED':<33}  {'ENV':<12}  {'COMMIT':<14}  CASES")
    for run in rows:
        key = store.key_for(run)
        mark = "*" if key == baseline_key else " "
        print(
            f"{mark} {key:<49}  {run.created_at:<33}  {run.environment:<12}  "
            f"{_short_commit(run.git_commit):<14}  {len(run.results)}"
        )
    if baseline_key is not None:
        print("\n* = current baseline")
    if listing.skipped or listing.unreadable:
        # Below the table, because it is about what is *not* in it. Never
        # silent: a listing that quietly drops history reads exactly like a
        # listing of a shorter history.
        print(f"\n{listing.note()}")
        if listing.skipped:
            print("run `digline migrate` to bring them up to date")
    return EXIT_OK


def cmd_promote(args: argparse.Namespace) -> int:
    suite, _module, store = _load(args)
    key = _resolve_key(store, suite, args.run)
    ref = RunRef(tenant=suite.tenant, suite=suite.name, key=key)
    promoted = store.promote_baseline(ref, suite.config_hash())
    # The resolved key, never the literal "latest": what was promoted must be
    # nameable afterwards.
    print(f"{promoted.suite} baseline set to {key}")
    return EXIT_OK


def cmd_migrate(args: argparse.Namespace) -> int:
    """Bring the stored documents of this suite up to the current schema.

    Runs and the baseline together: a baseline left behind would be unreadable
    the moment anything compared against it, which is every command that
    matters.
    """
    suite, _module, store = _load(args)

    paths = list(store.run_paths(suite.tenant, suite.name))
    baseline_path = store.baseline_path(suite.tenant, suite.name)
    if baseline_path.exists():
        paths.append(baseline_path)

    if not paths:
        print(f"nothing stored for suite {suite.name!r} in tenant {suite.tenant!r}")
        return EXIT_OK

    report = migrate_paths(tuple(paths), dry_run=args.dry_run)
    verb = "would migrate" if args.dry_run else "migrated"
    for path, came_from in report.migrated:
        print(f"{verb} {Path(path).name} from schema {came_from}")
    print(
        f"{len(report.migrated)} {verb}, {report.already_current} already current, "
        f"{len(report.refused)} refused"
    )
    for path, why in report.refused:
        # The refusal is the interesting output, so it goes to stderr where a
        # script will see it even when stdout is being read for the counts.
        print(f"\nrefused {Path(path).name}: {why}", file=sys.stderr)
    return EXIT_OK if report.ok else EXIT_USAGE


def cmd_view(args: argparse.Namespace) -> int:
    """Serve the four screens over this suite's stored runs.

    It reads `.digline/` and writes only what `promote` writes. Nothing is
    remembered between requests, so there is no state to lose and none to
    migrate — the store is the only thing that persists, as everywhere else.
    """
    suite, _module, store = _load(args)
    serve(suite, store, host=args.host, port=args.port)
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    suite, _module, store = _load(args)
    run = _read_run(store, suite, _resolve_key(store, suite, args.run))
    baseline = _need_baseline(store, suite)
    comparison = compare(run, baseline)

    if args.redacted:
        # Applied to the input, so the document can never claim to be complete:
        # `render_html` reads `Run.redacted`, it is not told what to print.
        #
        # The artifact outcomes are the exception, and deliberately: they are
        # computed *here*, where both runs are in hand, then stripped of their
        # payload. A redacted run compared on its own reports `unknown` because
        # it has no digest and must not guess; this caller does not have to
        # guess, so the document can say that a file moved without saying what
        # it was. Decision 9 on a file instead of on a reason. (ADR 0003 §5)
        complete_artifacts = comparison.artifact_deltas
        run = redact(run, suite.disclosure)
        comparison = compare(run, baseline)
        if not suite.disclosure.artifacts:
            comparison = replace(
                comparison,
                artifact_deltas=withhold_artifacts(
                    replace(comparison, artifact_deltas=complete_artifacts)
                ).artifact_deltas,
            )

    document = render_html(comparison, run, baseline, locale=args.locale)
    if args.out:
        Path(args.out).write_text(document, encoding="utf-8")
    else:
        print(document, end="")
    return exit_code(
        headline(compare(run, baseline), run, baseline, locale=args.locale)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="digline", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--suite",
            required=True,
            help="path/to/suite.py[:attribute] or package.module[:attribute]",
        )
        sub.add_argument("--root", default=".", help="directory holding .digline/")
        sub.add_argument("--tenant", help="verify the suite's tenant; never overrides")
        sub.add_argument(
            "--env", help="verify the suite's environment; never overrides"
        )

    def document_locale(sub: argparse.ArgumentParser) -> None:
        # Mandatory for a *document*: its language has a recipient, and that is
        # not settled by omission.
        sub.add_argument("--locale", required=True, choices=LOCALES)

    def terminal_locale(sub: argparse.ArgumentParser) -> None:
        # Optional for *terminal output*, which is for the developer and follows
        # the runtime rule: English unless asked otherwise. The sentence stays
        # the same as the report's because both come from `headline()`; there is
        # no need to make the user restate it.
        sub.add_argument("--locale", default="en", choices=LOCALES)

    run_p = subparsers.add_parser("run", help="execute the suite and write a run")
    common(run_p)
    run_p.add_argument("--target", help="same syntax as --suite; defaults to 'target'")
    run_p.add_argument(
        "--meta",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="repeatable; recorded in Run.metadata, payload unless disclosed",
    )
    run_p.add_argument("--json", action="store_true")
    run_p.set_defaults(func=cmd_run)

    cmp_p = subparsers.add_parser("compare", help="compare a run with the baseline")
    common(cmp_p)
    terminal_locale(cmp_p)
    cmp_p.add_argument("--run", required=True, metavar="KEY", help=RUN_HELP)
    cmp_p.add_argument(
        "--json",
        nargs="?",
        const="headline",
        choices=("headline", "full"),
        help="emit JSON: the headline alone, or 'full' to add the deltas",
    )
    cmp_p.set_defaults(func=cmd_compare)

    list_p = subparsers.add_parser("list", help="list stored runs, newest first")
    common(list_p)
    list_p.set_defaults(func=cmd_list)

    mig_p = subparsers.add_parser(
        "migrate", help="bring stored runs and the baseline up to the current schema"
    )
    common(mig_p)
    mig_p.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing anything",
    )
    mig_p.set_defaults(func=cmd_migrate)

    prom_p = subparsers.add_parser("promote", help="make a run the baseline")
    common(prom_p)
    prom_p.add_argument("--run", required=True, metavar="KEY", help=RUN_HELP)
    prom_p.set_defaults(func=cmd_promote)

    view_p = subparsers.add_parser(
        "view", help="browse stored runs, compare any two, promote"
    )
    common(view_p)
    view_p.add_argument("--host", default="127.0.0.1", help="bind address")
    view_p.add_argument("--port", type=int, default=7373, help="bind port")
    view_p.set_defaults(func=cmd_view)

    rep_p = subparsers.add_parser("report", help="render the report")
    common(rep_p)
    document_locale(rep_p)
    rep_p.add_argument("--run", required=True, metavar="KEY", help=RUN_HELP)
    rep_p.add_argument("--out", help="write here instead of stdout")
    rep_p.add_argument(
        "--redacted", action="store_true", help="redact the run before rendering"
    )
    rep_p.set_defaults(func=cmd_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # No bytecode written anywhere for the duration of this process. Running an
    # evaluation must not leave artifacts in the user's tree — new untracked
    # files make a repository dirty, and digline would then report every run
    # of its own making as unreproducible.
    sys.dont_write_bytecode = True

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except UsageError as exc:
        print(f"digline: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (
        ValueError,
        FileNotFoundError,
        ConfigMismatchError,
        ErroredRunError,
        TenantMismatchError,
    ) as exc:
        # Refusals from the core and the store — a crossed perimeter, a moved
        # configuration, a run that could not judge. They are the user's to fix.
        print(f"digline: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
