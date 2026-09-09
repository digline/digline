"""The command line: the last layer, and one of the front ends.

It no longer *is* the layer that touches the world — `digline.host` is, and this
composes it. The clock and git are still read once per command and passed down
as values; they are now read through `digline.host` so that a second front end
reads them the same way rather than growing its own. (ADR 0011 §7)

Nine commands, each doing one thing, and nothing promoting as a side effect of
anything else: `run` writes a run and prints its key, `compare` reads and
judges, `diff` reads two runs and judges neither, `promote` promotes, `report`
renders, `explain` reads the same facts back at length, `migrate` brings stored
documents up to the current schema, `list` and `view` show.

`compare` and `diff` are two commands and not one with a flag, because **the
exit code is the contract**: `compare` gates and `diff` never does, and a user
must never have to remember which mode they selected (ADR 0008 §2).

**None of this is `--help`.** What a reader of the source needs — why the layer
exists, what it is allowed to touch — is not what someone typing `digline -h`
needs, and this docstring used to be printed to them: argparse rewrapped an
architecture note into a paragraph, and told them there were four commands while
listing seven. The help text is written where the parser is built; the reasons
live here and in `docs/adr/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from digline import __version__
from digline.cli.view import serve
from digline.core import (
    Run,
    compare,
    diff,
    redact,
    withhold_artifacts,
)
from digline.host import (
    Loaded,
    UsageError,
    git_commit,
    load_suite,
    load_target,
    need_baseline,
    read_artifacts,
    read_run,
    resolve_key,
    utc_now_iso,
)
from digline.report import (
    artifact_lines,
    config_lines,
    explain_text,
    facts,
    headline,
    render_html,
    render_run_html,
    summary_lines,
    unjudged_cases,
)
from digline.report import diff as diff_report
from digline.run import Suite, execute, planned_calls
from digline.store import (
    ConfigMismatchError,
    ErroredRunError,
    FileResultStore,
    RunRef,
    TenantMismatchError,
    migrate_paths,
)
from digline.wire import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    OUTPUT_VERSION,
    compare_json,
    diff_json,
    exit_code,
    explain_json,
    run_json,
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

LOCALES: tuple[str, ...] = ("en", "it")

RUN_HELP = "a run key, or 'latest' for the most recent run of this suite"


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


def _load(args: argparse.Namespace) -> tuple[Suite, Loaded, FileResultStore]:
    """Loaded once per command: a Python suite imported twice would execute the
    user's module twice, and a module with a side effect would perform it twice.

    `Loaded` carries whichever half the form still owes — the module for a
    suite.py, the declared target for a suite.toml.
    """
    suite, loaded = load_suite(args.suite)
    _check_perimeter(suite, args.tenant, args.env)
    return suite, loaded, FileResultStore(args.root)


def _resolve(store: FileResultStore, suite: Suite, key: str) -> str:
    """`resolve_key` for a terminal: the key, and the note on stderr.

    The host returns what the scan stepped over rather than printing it
    (ADR 0011 §7). Here that becomes a line on stderr — `latest` is resolved
    inside commands whose stdout may be JSON, and a note that broke a pipeline
    would teach people to ignore it.
    """
    resolved = resolve_key(store, suite, key)
    if resolved.note:
        print(f"note: {resolved.note}", file=sys.stderr)
    return resolved.key


def cmd_run(args: argparse.Namespace) -> int:
    # The clock and git are read here and nowhere else, then passed down as
    # plain values so everything below stays reproducible.
    #
    # Read *before* the suite is imported: importing a Python module writes
    # `__pycache__`, so asking git afterwards would report a tree our own import
    # had just dirtied. The marker describes the repository as the user left it.
    commit = git_commit(Path(args.root))
    created_at = utc_now_iso()

    suite, loaded, store = _load(args)
    target = load_target(args.target, loaded, args.suite)

    # Announced before the first call, on stderr so a shell capturing the key
    # still captures only the key. Arithmetic over the declared suite: no
    # provider is asked, nothing is priced, and the figure that surprises people
    # is the multiplication itself. (ADR 0006 §8)
    plan = planned_calls(suite)
    print(f"digline: {plan.sentence()}", file=sys.stderr)

    run = execute(
        suite,
        target,
        created_at=created_at,
        git_commit=commit,
        run_metadata=_meta(args.meta),
        artifacts=read_artifacts(suite, target, Path(args.suite).resolve().parent),
    )
    ref = store.write_run(run)

    if args.json:
        print(json.dumps(run_json(ref, plan)))
    else:
        # Only the key on stdout, so a shell can capture it:
        #   KEY=$(digline run --suite …)
        print(ref.key)
    return EXIT_OK


#: How many regressions a terminal shows before pointing at the report. Not a
#: silent cut: `summary_lines` says how many it left out.
SUMMARY_LIMIT = 20


def cmd_compare(args: argparse.Namespace) -> int:
    suite, _loaded, store = _load(args)
    run = read_run(store, suite, _resolve(store, suite, args.run))
    baseline = need_baseline(store, suite)

    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale=args.locale)

    if args.json:
        payload = compare_json(comparison, head, full=args.json == "full")
        print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
        return exit_code(head)

    print(head.sentence)
    # What was under test, before what it did: a prompt that moved changes how
    # every line below it reads, and learning that afterwards is learning it too
    # late. The tally only — the diff is in the report, one command away.
    moved = artifact_lines(comparison, locale=args.locale)
    # The named deltas beside the file tally, and unlike the file tally they are
    # the whole fact rather than a pointer to the document: `temperature
    # 0.3 → 0.7` fits on one line and is what the reader would have gone to the
    # report for. (ADR 0005 §5)
    moved = (*moved, *config_lines(comparison, locale=args.locale))
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


def cmd_diff(args: argparse.Namespace) -> int:
    """Two runs, neither of them a reference. Always exits 0 on a report.

    `exit_code()` is deliberately not called and must never be: a verdict exists
    only against an approved reference, and neither side of a diff was approved
    by anybody (ADR 0008 §1). The refusals below are usage errors — the report
    could not be produced — which is a different thing from a report whose
    contents somebody dislikes, and only the first is a non-zero exit.
    """
    suite, _loaded, store = _load(args)
    left_key, right_key = (_resolve(store, suite, k) for k in args.runs)
    if left_key == right_key:
        raise UsageError(
            f"both arguments resolve to the run {left_key}: a run diffed with "
            "itself has nothing to report, because every line of the answer "
            "would be a tautology"
        )
    left = read_run(store, suite, left_key)
    right = read_run(store, suite, right_key)

    difference = diff(left, right)
    keys = (left_key, right_key)
    labels = diff_report.run_labels(
        left.created_at, right.created_at, left_key=left_key, right_key=right_key
    )
    sentence = diff_report.sentence(difference, locale=args.locale, labels=labels)

    if args.json:
        print(
            json.dumps(
                diff_json(
                    difference,
                    left,
                    right,
                    keys=keys,
                    labels=labels,
                    sentence=sentence,
                    full=args.json == "full",
                ),
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK

    # The two runs bound to the labels everything below uses. No word in front
    # of either: "run 1" and "run 2" would be a rank, and the order of two
    # columns is not one. The key is dropped where the label already is the key.
    for key, label, run in ((left_key, labels[0], left), (right_key, labels[1], right)):
        stamp = "" if label == key else f"  {key}"
        print(f"{label}{stamp}  {run.environment}")

    # What differs about the systems, before what it did to the scores.
    opening = diff_report.header_lines(difference, locale=args.locale, labels=labels)
    if opening:
        print()
        for line in opening:
            print(f"  {line}")

    print()
    print(sentence)

    lines = diff_report.summary_lines(
        difference, locale=args.locale, labels=labels, limit=SUMMARY_LIMIT
    )
    if lines:
        print()
        for line in lines:
            print(line)
    return EXIT_OK


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
    suite, _loaded, store = _load(args)

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
    suite, _loaded, store = _load(args)
    key = _resolve(store, suite, args.run)
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
    suite, _loaded, store = _load(args)

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
    suite, _loaded, store = _load(args)
    serve(suite, store, host=args.host, port=args.port)
    return EXIT_OK


def cmd_explain(args: argparse.Namespace) -> int:
    """The run read back at length, and the comparison too where there is one.

    The scope follows the store, never a flag: `report`'s pattern, for
    `report`'s reason — making a reader name the scope means making them know,
    before they type, which of two documents they are entitled to (ADR 0012 §1).

    It gates like `report` and not like `diff`. Explain with a baseline holds a
    run against the same approved reference `compare` gates on, so withholding
    the exit code would mean exiting 1 on a one-line summary of a regression and
    0 on three paragraphs about it.
    """
    suite, _loaded, store = _load(args)
    run = read_run(store, suite, _resolve(store, suite, args.run))
    baseline = store.read_baseline(suite.tenant, suite.name)

    if baseline is None:
        # `_report_single`'s rule, and for its reason: "worse" is a relation,
        # and there is nothing here to be worse than. An unjudged case survives
        # — that is a fact about the harness rather than about a reference.
        reading = facts(run)
        code = EXIT_UNJUDGED if unjudged_cases(run) else EXIT_OK
        scope = "run"
    else:
        comparison = compare(run, baseline)
        reading = facts(run, comparison)
        code = exit_code(headline(comparison, run, baseline, locale=args.locale))
        scope = "comparison"

    if args.json:
        print(
            json.dumps(
                explain_json(reading, scope=scope, exit_code=code),
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
        )
        return code

    for line in explain_text(reading, locale=args.locale):
        print(line)
    return code


def cmd_report(args: argparse.Namespace) -> int:
    suite, _loaded, store = _load(args)
    run = read_run(store, suite, _resolve(store, suite, args.run))
    baseline = store.read_baseline(suite.tenant, suite.name)

    if baseline is None:
        # Not a refusal, and this is the whole point of the command existing.
        # `need_baseline` — which `compare` still uses, rightly — says "run it,
        # look at the result, then promote", and `report` *was* the only way to
        # look. Naming looking as the prerequisite for looking is a dead end,
        # and the first person to hit it is always someone on their first run.
        #
        # Automatic rather than a flag, for the reason `--redacted` is not a
        # choice about what the document says: complete or redacted follows
        # from `run.redacted`, and comparative or not follows from whether a
        # reference exists. A flag would have to be an error when a baseline is
        # present, and would leave the dead end intact for whoever has not yet
        # learned the flag.
        return _report_single(run, suite, args)

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


def _report_single(run: Run, suite: Suite, args: argparse.Namespace) -> int:
    """The run on its own, and an exit code that claims no more than it can.

    Never `EXIT_WORSE`: "worse" is a relation and there is nothing here to be
    worse than. `EXIT_UNJUDGED` survives, because a case the suite could not
    judge is a fact about the harness rather than about a reference — the
    partial contract mirrors what the document itself claims.
    """
    if args.redacted:
        # No artifact-outcome rescue here, unlike the comparison path: those
        # outcomes are computed from two runs, and the reason that code exists
        # — a redacted run compared alone reports `unknown` — cannot arise
        # where nothing is compared.
        run = redact(run, suite.disclosure)

    document = render_run_html(run, locale=args.locale)
    if args.out:
        Path(args.out).write_text(document, encoding="utf-8")
    else:
        print(document, end="")
    return EXIT_UNJUDGED if unjudged_cases(run) else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digline",
        # Not `__doc__`. A module docstring is written for whoever opens the
        # file; `--help` is read by somebody who wants to know what to type.
        description=(
            "Check that an LLM's answers have not got worse, against a baseline "
            "committed in your own repository."
        ),
        epilog="Options for one command: digline <command> -h",
    )
    # Right after the parser and before the subcommands, so it is reachable as
    # `digline --version` and not only as a flag on one of them. `action=
    # "version"` prints and exits 0 inside argparse, which is why nothing in
    # `main()` dispatches on it.
    parser.add_argument(
        "--version",
        action="version",
        version=f"digline {__version__}",
        help="print the version and exit",
    )
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

    diff_p = subparsers.add_parser(
        "diff", help="report what differs between two runs; judges neither"
    )
    common(diff_p)
    # The terminal rule, not the document one: this writes to a terminal, and
    # `CLAUDE.md` splits the locale grade on document-against-terminal rather
    # than on the word "report". A future HTML diff document takes the mandatory
    # flag like every other document. (ADR 0008 §2)
    terminal_locale(diff_p)
    diff_p.add_argument("runs", nargs=2, metavar="RUN", help=RUN_HELP)
    # The value is **mandatory here and optional on `compare`**, and the
    # difference is forced rather than chosen. `compare` takes its run through
    # `--run`, so a bare `--json` has no positional to be confused with; `diff`
    # takes two positionals, and an optional-valued flag in front of them makes
    # argparse swallow the first run key as the flag's value — `digline diff
    # --json A B` becomes "invalid choice: A". Found by running it. A required
    # value is the one shape with no trap in it, at the cost of a shorthand.
    diff_p.add_argument(
        "--json",
        choices=("counts", "full"),
        help="emit JSON: 'counts' for the figures, 'full' to add every check",
    )
    diff_p.set_defaults(func=cmd_diff)

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

    exp_p = subparsers.add_parser(
        "explain", help="read a run back at length; compares if there is a baseline"
    )
    common(exp_p)
    # The terminal rule, like `compare` and `diff`. There is no `--out`, and
    # that is what keeps the rule honest rather than an oversight: a reading
    # written to a file has a recipient who did not choose English, and the
    # locale becomes mandatory the way `report`'s is. (ADR 0012 §7)
    terminal_locale(exp_p)
    exp_p.add_argument("--run", required=True, metavar="KEY", help=RUN_HELP)
    exp_p.add_argument(
        "--json",
        action="store_true",
        help="emit the fact list the prose is rendered from, instead of the prose",
    )
    exp_p.set_defaults(func=cmd_explain)

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
