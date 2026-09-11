"""The comparison, as rows in pytest's own report. (ADR 0013)

One item per check — one assertion on one case — because that is digline's own
unit of verdict. Anything coarser would fold several verdicts into one here, in
a front end, under a rule no record governs and no test in `digline.core` can
see.

Four states, and the fourth is the reason this is worth doing at all:

    fine              passed
    worse             FAILED
    could not judge   ERROR      (raised in setup(): an exception in runtest()
                                  is a failure whatever its type)
    suspended         SKIPPED    with the reason the suite declared

The exit code cannot express a suspension — it never fails, so it disappears
into `0`. pytest has carried exactly that idea since it was written.

**Nothing here computes a number or composes a sentence.** Every score comes
from `digline.core`, every line from `digline.report`, every file from
`digline.host`. If that stops being true this package has become a fork of the
product with a nicer report, which is the thing ADR 0013 exists to prevent.

There is no promote surface. Not disabled, not gated: absent, the way it is
absent from `digline-mcp` (ADR 0011 §1), and `tests/test_no_promote.py` sweeps
these sources to keep it that way.
"""

from __future__ import annotations

import sys
from collections.abc import Generator, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from digline.core import AssertionDelta, Comparison, Verdict
    from digline.run import Suite
    from digline.store import FileResultStore

# **digline is imported inside the hooks, not here**, and the reason is
# measured rather than tidy-minded.
#
# A `pytest11` entry point is loaded at pytest startup in *every* environment
# where this package is installed, including projects that never name a suite.
# Importing digline at module level pulled 44 modules — the core, the store,
# the driver, the report, the host, and `jsonschema` behind the assertions —
# into every one of those runs: 138 ms against 88 ms for a bare collection on
# an unrelated project, a 50 ms tax on a command people press hundreds of times
# a day. ADR 0013 §8 says this plugin is inert when no suite is named, and
# inert has to mean the startup too, not only the output.
#
# So the imports live inside the four functions that actually reach for
# them, all of which run only once a suite has been named. `from __future__
# import annotations` makes every annotation in this file a string, so the
# TYPE_CHECKING block above is all a type checker needs.

__all__: list[str] = []

#: The locale of everything this plugin prints. Fixed, and not a flag.
#:
#: `CLAUDE.md` draws the line between a *document* and a *terminal*: `report
#: --locale` is mandatory because a document has a recipient who did not choose
#: English, and `compare --locale` defaults to `en` like every other terminal
#: output. pytest's report is a terminal. `digline-mcp` made the same call for
#: the same reason — a caller who wants the customer's sentence renders the
#: report, which takes a mandatory locale.
LOCALE = "en"

#: The suite-scope name a run-level verdict carries, since it belongs to no case.
RUN_SCOPE = "<run>"

#: Set by `pytest_collection_modifyitems`, read by `pytest_terminal_summary`.
#: On the config's stash rather than a module global: a module global is shared
#: by every `Config` in the process, and `pytester` runs several in one.
HEADLINES: pytest.StashKey[list[str]] = pytest.StashKey()


# --------------------------------------------------------------------------- #
# The options: pointing at the suite, and nothing else
# --------------------------------------------------------------------------- #


def pytest_addoption(parser: pytest.Parser) -> None:
    """Two ways to name a suite and one flag that spends money. (ADR 0013 §5)

    No threshold, no tolerance, no locale: the committed baseline is the only
    reference this plugin has, and a flag that could move a bar would dissolve
    that in the one place it is least visible — a CI invocation line.

    An ini option rather than a `[tool.digline]` block because this *is* pytest
    configuration: it lives where the rest of a project's pytest settings live,
    and a reader who knows pytest knows where to look.
    """
    group = parser.getgroup("digline", "digline: gate on a committed baseline")
    group.addoption(
        "--digline-suite",
        action="append",
        default=[],
        metavar="PATH",
        dest="digline_suite",
        help="a digline suite to gate on; repeatable. Overrides digline_suites",
    )
    group.addoption(
        "--digline-root",
        default=None,
        metavar="DIR",
        dest="digline_root",
        help="the perimeter holding .digline/ (default: pytest's rootdir)",
    )
    group.addoption(
        "--digline-run",
        action="store_true",
        default=False,
        dest="digline_run",
        help=(
            "run each suite before comparing. THIS CALLS YOUR PROVIDER AND "
            "SPENDS MONEY: the planned call count is printed before the first "
            "call. Without it, this plugin compares the latest stored run and "
            "makes no network call at all"
        ),
    )
    parser.addini(
        "digline_suites",
        type="paths",
        default=[],
        help="digline suites this repository gates on, one per line",
    )


def pytest_configure(config: pytest.Config) -> None:
    """The one refusal, and it is here rather than at collection so that it
    happens before anything can be called. (ADR 0013 §2)

    `--collect-only` exists to list test names. A plugin that spent a hundred
    model calls answering it would be the worst defect this package could ship,
    and the person who types `--co` after `--digline-run` is always doing it to
    find out what *would* happen.
    """
    config.stash[HEADLINES] = []
    if config.getoption("digline_run") and config.option.collectonly:
        raise pytest.UsageError(
            "--digline-run calls your provider and --collect-only exists to "
            "list test names without running anything. Drop one of the two: "
            "`--collect-only` alone lists the checks against the run already "
            "stored, and costs nothing."
        )


def pytest_report_header(config: pytest.Config) -> str | None:
    """One line, and only when a suite was named. (ADR 0013 §8)"""
    specs = _specs(config)
    if not specs:
        return None
    how = "running then comparing" if config.getoption("digline_run") else "comparing"
    return f"digline: {how} {len(specs)} suite(s) against the committed baseline"


def _specs(config: pytest.Config) -> Sequence[str]:
    """The suites to gate on. The command line wins, whole, over the ini.

    Whole and not merged: a developer narrowing a run to one suite means that
    suite instead of the configured set, and a flag that added to a list would
    make narrowing impossible to express.
    """
    given: list[str] = list(config.getoption("digline_suite") or [])
    if given:
        return given
    return [str(path) for path in config.getini("digline_suites")]


# --------------------------------------------------------------------------- #
# Collection: the comparison, once per suite
# --------------------------------------------------------------------------- #


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Add this repository's checks to whatever pytest already collected.

    **Inert when no suite is named** (ADR 0013 §8): `_specs` is empty, the loop
    does not run, and a repository that has not asked for this plugin cannot
    tell it is installed. That is not politeness — `uv sync --all-packages`
    installs this package into digline's own development environment, so its
    entry point is active for the suite that judges it.

    `tryfirst` because `-k`, `-m` and `--last-failed` are themselves
    implementations of this hook: items appended after they have run are items
    they never saw, and selection would silently stop applying to exactly the
    rows this plugin exists to add.

    Injected here rather than by making the suite an initial path, which would
    make pytest's own python plugin collect the file as a test module and
    **import the user's suite a second time** — a module with an import-time
    side effect would perform it twice.
    """
    for spec in _specs(config):
        opened = _open(spec, config)
        node = _child(session, DiglineSuite, path=opened.path, opened=opened)
        items.extend(node.collect())
        config.stash[HEADLINES].append(opened.headline)


def _child[N: pytest.Item | pytest.File](
    parent: pytest.Collector, cls: type[N], **kwargs: Any
) -> N:
    """`cls.from_parent(parent, **kwargs)`, with the waiver in one place.

    `from_parent` is pytest's constructor for a node — a node must never be
    instantiated directly — and its signature is `(parent, **kw)`, so under
    pyright strict every call site reports the type as partially unknown. That
    is a fact about pytest's annotations and not about this code, so the waiver
    is stated once here rather than four times where it would read as four
    separate concessions.
    """
    return cls.from_parent(parent, **kwargs)  # pyright: ignore[reportUnknownMemberType]


@dataclass(frozen=True, slots=True)
class _Opened:
    """One suite, loaded once, compared once.

    Loaded once for `digline-mcp`'s reason (ADR 0011): a suite is a Python file
    this plugin executes, so loading it twice runs the user's module twice.
    """

    path: Path
    suite: Suite
    comparison: Comparison
    #: `temperature 0.3 → 0.7`, or empty. Composed once and handed to every row,
    #: exactly as `summary_lines` composes it once for a whole listing.
    coincides: str
    headline: str
    #: Whether this run carries the judge's own words. False on a redacted run,
    #: where quoting a reason would be quoting something that is not there.
    reasons_available: bool


def _open(spec: str, config: pytest.Config) -> _Opened:
    """Load, run if asked, compare. Every refusal on the way is a usage error.

    `UsageError` becomes `pytest.UsageError`, which stops the session with
    pytest's exit code 4 — the front end refusing the request that was made,
    which is what digline's own `64` means (`AGENTS.md` §6). It is loud on
    purpose: a suite with no baseline yet, or a path with a typo, must not
    collect zero rows and let a green run mean "nothing to check". That is the
    vacuously green assertion fixed decision 3 refuses.
    """
    from digline.host import UsageError

    root = Path(config.getoption("digline_root") or config.rootpath)
    try:
        return _opened(spec, root, run_first=bool(config.getoption("digline_run")))
    except UsageError as exc:
        raise pytest.UsageError(f"digline: {exc}") from exc


def _opened(spec: str, root: Path, *, run_first: bool) -> _Opened:
    from digline.core import compare
    from digline.host import load_suite, need_baseline, read_run, resolve_key
    from digline.report import config_changes, headline
    from digline.store import FileResultStore

    suite, loaded = load_suite(spec, root=root)
    path = _path_of(spec)
    store = FileResultStore(str(root))

    if run_first:
        _measure(suite, loaded, spec, path, store, root=root)

    key = resolve_key(store, suite, "latest").key
    run = read_run(store, suite, key)
    baseline = need_baseline(store, suite)
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale=LOCALE)
    return _Opened(
        path=path,
        suite=suite,
        comparison=comparison,
        coincides=config_changes(comparison.config_changes, LOCALE),
        headline=head.sentence,
        reasons_available=head.reasons_available,
    )


def _measure(
    suite: Suite,
    loaded: Any,
    spec: str,
    path: Path,
    store: FileResultStore,
    *,
    root: Path,
) -> None:
    """`--digline-run`: the run, and the count said out loud before it.

    The sentence on stderr is `AGENTS.md` §7 and ADR 0006 §8, unchanged and not
    optional. Sampling multiplies spend, the multiplication is the part that
    surprises people, and a pytest invocation is a thing people run on a
    keystroke.

    The clock and git are read here and passed down as values, so the run is a
    function of them rather than of when it happened to look.
    """
    from digline.host import git_commit, load_target, read_artifacts, utc_now_iso
    from digline.run import execute, planned_calls

    target = load_target(None, loaded, spec)
    plan = planned_calls(suite)
    print(f"digline: {plan.sentence()}", file=sys.stderr)
    commit = git_commit(root)
    created_at = utc_now_iso()
    run = execute(
        suite,
        target,
        created_at=created_at,
        git_commit=commit,
        artifacts=read_artifacts(suite, target, path.parent, root=root),
    )
    store.write_run(run)


def _path_of(spec: str) -> Path:
    """The file a spec names, dropping a trailing `:attribute`.

    The loader's own rule (`host.loader._split`): only a trailing `:name`
    counts, and only when `name` is an identifier — so a Windows path like
    `C:\\suites\\qa.py` keeps its drive letter.
    """
    head, sep, tail = spec.rpartition(":")
    return Path(head if sep and tail.isidentifier() else spec).resolve()


# --------------------------------------------------------------------------- #
# The nodes
# --------------------------------------------------------------------------- #


class DiglineSuite(pytest.File):
    """One suite. Its children are its checks and its set-aside cases."""

    def __init__(self, *, opened: _Opened, **kwargs: Any) -> None:
        super().__init__(**kwargs)  # pyright: ignore[reportUnknownMemberType]
        self.opened = opened

    def collect(self) -> Iterator[pytest.Item]:
        for delta in self.opened.comparison.deltas:
            yield _child(
                self, Check, name=_name_of(delta), delta=delta, opened=self.opened
            )
        # Suspended cases come from the *run*, not from the comparison: a case
        # set aside produces no verdicts, so it produces no deltas, so the
        # comparison cannot report it at all. `SECTIONS` feeds the report's
        # suspended section the same way, from the same asymmetry.
        for case_id, reason in _suspensions(self.opened):
            yield _child(self, Suspended, name=case_id, reason=reason)


def _name_of(delta: AssertionDelta) -> str:
    """`how-do-i-return::llm_rubric`, or `<run>::precision`.

    A run-level verdict belongs to no case and says so, rather than opening the
    name with an empty field — the convention `summary_lines` already follows.
    """
    return f"{delta.case_id if delta.scope == 'case' else RUN_SCOPE}::{delta.assertion}"


def _suspensions(opened: _Opened) -> Sequence[tuple[str, str]]:
    """The set-aside cases of the suite, with the reason each declared.

    Read off the declared suite rather than off the run, so that a case
    suspended *since* the stored run was produced is still reported as the
    decision it is instead of vanishing between the two.
    """
    return tuple(
        (case.id, case.suspended)
        for case in opened.suite.cases
        if case.suspended is not None
    )


class Check(pytest.Item):
    """One assertion on one case, in the state the comparison found it."""

    def __init__(self, *, delta: AssertionDelta, opened: _Opened, **kwargs: Any):
        super().__init__(**kwargs)  # pyright: ignore[reportUnknownMemberType]
        self.delta = delta
        self.opened = opened

    def setup(self) -> None:
        """The unjudged half, and it has to be here.

        An exception raised in `runtest()` is a FAILURE whatever its type;
        only setup and teardown produce pytest's error state. ADR 0001 §1 says
        an error is neither green nor a regression, so a check that could not be
        judged has to raise from here or stop being distinguishable.

        Tested **after** the regression below, which is `exit_code()`'s
        precedence per row: a check that both regressed and errored is reported
        as the regression, because that is the louder fact.
        """
        if _failing(self.delta):
            return
        if _errored(self.delta.current):
            raise CouldNotJudge(self)

    def runtest(self) -> None:
        if _failing(self.delta):
            raise GotWorse(self)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.path, None, self.name

    def repr_failure(
        self, excinfo: pytest.ExceptionInfo[BaseException], style: Any = None
    ) -> str:  # noqa: E501, ARG002
        """The report's own sentence, and no traceback.

        There is no Python frame worth showing: the exception was raised one
        line from where the message was composed, and a stack trace through
        `_pytest/runner.py` says nothing about a rubric score.

        This covers the FAILED rows only — pytest consults `repr_failure` for
        the `call` phase alone (`_pytest/reports.py:_format_failed_longrepr`).
        The ERROR rows are covered by `pytest_runtest_makereport` below, and
        both halves are needed: either alone leaves one of the two states
        printing a traceback.
        """
        return self.message()

    def message(self) -> str:
        """What moved, in the words the report and `digline compare` use.

        `check_line` is the report's own function (ADR 0013 §6). Composing this
        sentence here instead would be a fourth prose rendering of one
        comparison, bound to the other three by nothing.
        """
        from digline.report import check_line

        where = f"{self.delta.case_id or RUN_SCOPE} · {self.delta.assertion}"
        line = check_line(self.delta, locale=LOCALE, coincides=self.opened.coincides)
        parts = [f"digline: {where}", f"  {line}"]
        if self.opened.reasons_available and (reason := _reason(self.delta)):
            parts.append(f"  reason: {reason}")
        return "\n".join(parts)


class Suspended(pytest.Item):
    """A case somebody set aside, with the reason they gave.

    A decision rather than an outcome, which is why it is a skip and not a pass:
    the run is smaller than the suite, and a reader has to be able to see that.
    """

    def __init__(self, *, reason: str, **kwargs: Any):
        super().__init__(**kwargs)  # pyright: ignore[reportUnknownMemberType]
        self.reason = reason

    def runtest(self) -> None:
        pytest.skip(self.reason)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.path, None, self.name


class DiglineOutcome(Exception):
    """Raised by an item about itself, and never printed as itself.

    It carries the item rather than a string so that the message is composed
    once, by `Check.message()`, whichever of the two phases the exception was
    raised in.
    """

    def __init__(self, item: Check) -> None:
        super().__init__(item.name)
        self.item = item


class GotWorse(DiglineOutcome):
    """A check that regressed against the approved reference."""


class CouldNotJudge(DiglineOutcome):
    """A check the suite could not judge. Neither green nor a regression."""


def _failing(delta: AssertionDelta) -> bool:
    """Whether this row is the one that fails the report.

    A regression, **or a canary that moved** — including one whose `Outcome` is
    `improved`, which is the one place this mapping cannot be read straight off
    `outcome == "regressed"`. A canary's score is a fingerprint rather than a
    quality: it moved, so the model behind the alias probably changed, and that
    is a reason to stop whichever way the number went.

    The rule is `exit_code()`'s, per row instead of per run, and it is written
    as one predicate so the two cannot drift: a front end that decided this for
    itself would be a second answer to what fails a release. (ADR 0016 §5, §8)
    """
    if delta.outcome == "regressed":
        return True
    return delta.canary and delta.outcome == "improved"


def _errored(verdict: Verdict | None) -> bool:
    """Whether this check could not be judged.

    **Not** `outcome == "errored"`, and the difference is a trap worth naming:
    rule 1 of `compare()` classifies an absent counterpart as `new` before rule
    2 can call it `errored`, so a case added since the baseline that fails on
    its first day is `new` *and* unjudged. `report._summarized()` holds the
    same rule, and the two must agree or the headline would count a case the
    rows do not.
    """
    return verdict is not None and verdict.status == "error"


def _reason(delta: AssertionDelta) -> str:
    """The judge's own words, from whichever side of the comparison has them."""
    source = delta.current if delta.current is not None else delta.baseline
    return "" if source is None else source.reason


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Keep the ERROR and SKIPPED rows honest, which `repr_failure` cannot.

    Two things pytest does that this undoes for this plugin's items alone:

    **A setup-phase exception prints a traceback.** `repr_failure` is consulted
    for the `call` phase only; setup and teardown go through `_repr_failure_py`
    with the `--tb` style. Since a check that could not be judged *must* raise
    in setup to be an error at all, without this every ERROR row would carry a
    stack trace through pytest's internals.

    **A skip is located where `pytest.skip()` was called**, which is this file.
    A reader looking at `SKIPPED [1] plugin.py:412` learns nothing; the suite
    that declared the suspension is what they want.
    """
    report = yield
    if not isinstance(item, (Check, Suspended)):
        return report
    if isinstance(item, Check) and call.excinfo is not None:
        if isinstance(call.excinfo.value, DiglineOutcome):
            report.longrepr = item.message()
        return report
    if isinstance(item, Suspended) and report.skipped:
        # `(path, line, reason)` is the shape pytest's own skip reports use, so
        # `-rs` renders this like any other skip. The line is the file's first:
        # the suspension is declared in the suite, and pointing at a line inside
        # it would be a guess — a `.toml` suite reads its cases from a third
        # file. What matters is that it names the suite and not this plugin.
        report.longrepr = (str(item.path), 1, item.reason)
    return report


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    """The headline sentence, once per suite. (ADR 0013 §6)

    Once, and not stamped on every failing row: it is a statement about the
    *run* — how many checks got worse, how many cases could not be judged,
    whether the rules moved — and forty copies of one sentence is forty lines a
    reader learns to skip, taking the row detail beside it.

    It is `headline().sentence`, byte for byte the sentence `digline compare`
    prints and the report shows, because a gate and a document must never say
    two different things about one run.
    """
    none: list[str] = []
    sentences = config.stash.get(HEADLINES, none)
    if not sentences:
        return
    terminalreporter.write_sep("=", "digline")
    for sentence in sentences:
        terminalreporter.write_line(sentence)
