"""`digline suggest`: a first suite proposed from what a suite's recordings,
reviewed answers and runs hold, written into one file and never marked.
(ADR 0063)

**What it reads** (§1): the recordings whose `suite` names the suite, across
the tenant's process directories, through the functions `digline record
import` reads them with; the reviewed answers in the cases file the suite's
capture names; and the suite's runs, where there are any. The calls no suite
named are counted, and never read for anything else.

**What it writes** (§2, §5): `suite.proposed.toml`, beside the suite, or in
the working directory where there is no suite yet, always TOML, and nothing
else. A file of that name already there is refused by name: what a person
wrote in it is not the command's to throw away. The rules are
`digline.core.suggest`'s.

**What it never does** (§3): write a reviewed answer, a `good`, a `--by`, a
label or a promotion, or choose a case. No command of digline reads the file
it writes.

**What it says** (§5, §6): what it assumed, on standard error, in the words of
the fifth step of the `proposing-a-suite` skill, and counts. Digline's own
words alone: no recorded text reaches standard output or standard error, and
the lines are built here so that a front end lays them out.

**The assistant** (§4), where one is declared, is `digline.host.assistant`'s:
what it costs is said through `say` before the call, and what it wrote is
merged into the file by `digline.core.suggest.merged`. Its words reach the
file and no stream.
"""

from __future__ import annotations

import dataclasses
import json
import re
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from digline.core.recording import Recording
from digline.core.refused import RefusedError
from digline.core.run import RecordedResponse, Run
from digline.core.suggest import (
    PLACEHOLDER,
    Merged,
    Proposed,
    budget_checks,
    declared_tools,
    judged_check,
    measured,
    merged,
    shape_checks,
    step_checks,
)
from digline.host.assistant import (
    MAX_CHARS,
    MAX_RECORDINGS,
    announcement,
    ask,
    assistant,
    material,
    refused_by,
)
from digline.host.importing import (
    Shape,
    answer_counts,
    capture_file,
    import_listing,
    read_recordings,
    setups_recorded,
    split_recordings,
)
from digline.host.recording import recorder_status
from digline.host.toml_suite import PROPOSAL, read_cases
from digline.recorder import UNASSIGNED
from digline.run.suite import Case, Suite
from digline.store.file_store import FileResultStore, checked_name
from digline.store.protocol import PathRefusedError
from digline.targets.registry import installed
from digline.wire.suggest import ProposedCheck, SuggestGroup, Suggestion

__all__ = ["PROPOSAL", "SUITE_RULE", "Suggested", "suggest_for", "suggest_new"]

#: How `--suite` is read, said whole wherever it resolves to nothing.
SUITE_RULE = (
    "--suite is a suite when it is a file that is there, a path ending in .py "
    "or .toml, or module:attribute; anything else is the name of a suite that "
    "does not exist yet, given with --tenant and --repository private|public"
)

#: The capture file a suite that does not exist yet is proposed with.
CAPTURED = "captured.json"

#: The judged check a suite that does not exist yet is proposed with.
JUDGED = "llm_rubric"


@dataclass(frozen=True, slots=True)
class Suggested:
    """What the command did: the file it wrote, or `None` where it proposed
    nothing, and the lines it says on standard error."""

    path: Path | None
    lines: tuple[str, ...]
    #: What the lines are rendered from, and what the MCP server returns.
    facts: Suggestion | None = None


@dataclass(frozen=True, slots=True)
class _Source:
    """What the proposal is made for: the suite, where one exists, and the
    facts it is read under either way."""

    tenant: str
    name: str
    repository: str
    check: str | None
    cases_file: str
    suite: Suite | None
    module: ModuleType | None
    #: The form of the suite that exists, `"suite.toml"` or `"suite.py"`.
    form: str | None
    #: Every case the suite loads, and the cases its capture file holds.
    cases: tuple[Case, ...]
    captured: tuple[Case, ...]
    #: The assistant's coordinates, where one is declared, and where.
    model: str | None = None
    model_from: str = ""
    #: The suite's file, where the suite exists.
    suite_file: Path | None = None


def suggest_new(
    root: Path,
    name: str,
    *,
    tenant: str | None,
    repository: str | None,
    here: Path,
    model: str | None = None,
    say: Callable[[str], None] | None = None,
    write: bool = True,
) -> Suggested:
    """The proposal for a suite that does not exist yet, read from the
    recordings filed under its name and written in `here`. `--tenant` and
    `--repository` are mandatory, with no default. (ADR 0063 §1, §5)
    Without `write`, nothing is written and no assistant is asked.

    A name that already has runs under the tenant is a suite whose file was
    not given: digline does not look for it, and stops."""
    if tenant is not None and _has_runs(root, tenant, name):
        raise RefusedError(
            f"{name[:40]!r} has runs under this tenant but no suite file here: "
            "give the path. Nothing was proposed"
        )
    missing = [
        flag
        for flag, value in (("--tenant", tenant), ("--repository", repository))
        if value is None
    ]
    if missing:
        raise RefusedError(
            f"no suite file is named {name!r}, so it is read as the name of a "
            f"suite that does not exist yet, and that needs {' and '.join(missing)}: "
            "--tenant because there is no declared tenant to find its "
            "recordings under, and --repository private|public because the "
            "regime the proposed [capture] declares is yours to say, with no "
            "default (ADR 0063 §1; ADR 0059 §4)"
        )
    assert tenant is not None and repository is not None
    if repository not in ("private", "public"):
        raise RefusedError(
            f"--repository takes 'private' or 'public', not {repository[:40]!r}"
        )
    checked_name(tenant, "tenant")
    try:
        checked_name(name, "suite")
    except PathRefusedError:
        raise RefusedError(
            f"--suite {name[:40]!r} is neither a suite's file nor a suite's "
            f"name: {SUITE_RULE}"
        ) from None
    return _propose(
        root,
        _Source(
            tenant=tenant,
            name=name,
            repository=repository,
            check=JUDGED,
            cases_file=CAPTURED,
            suite=None,
            module=None,
            form=None,
            cases=(),
            captured=(),
            model=model,
            model_from="--model",
        ),
        here / PROPOSAL,
        say,
        write=write,
    )


def suggest_for(
    root: Path,
    suite: Suite,
    *,
    suite_file: Path,
    module: ModuleType | None,
    repository: str | None,
    model: str | None = None,
    model_from: str = "",
    say: Callable[[str], None] | None = None,
    write: bool = True,
) -> Suggested:
    """The proposal for a suite that exists, written beside its file. Its
    capture is the one used, so `--repository` is refused: the regime is
    already declared. (ADR 0063 §1) Without `write`, nothing is written and
    no assistant is asked."""
    if repository is not None:
        raise RefusedError(
            f"--repository is refused where the suite exists: suite "
            f"{suite.name!r} declares its capture, and with it its regime "
            "(ADR 0063 §1)"
        )
    source, path = capture_file(suite, module, root)
    beside = suite_file.parent
    try:
        shown = str(path.resolve().relative_to(beside.resolve()))
    except ValueError:
        shown = str(path)
    return _propose(
        root,
        _Source(
            tenant=suite.tenant,
            name=suite.name,
            repository=source.repository,
            check=source.check,
            cases_file=shown,
            suite=suite,
            module=module,
            form="suite.toml" if suite_file.suffix == ".toml" else "suite.py",
            cases=tuple(suite.cases),
            captured=tuple(read_cases(path)),
            model=model,
            model_from=model_from,
            suite_file=suite_file,
        ),
        beside / PROPOSAL,
        say,
        write=write,
    )


def _has_runs(root: Path, tenant: str, name: str) -> bool:
    """Whether `name` has runs under `tenant`. A name that is no name has
    none: the refusal that says why is the caller's."""
    try:
        return bool(
            FileResultStore(root).list_runs(checked_name(tenant, "tenant"), name)
        )
    except PathRefusedError:
        return False


def _many(count: int, noun: str, plural: str | None = None) -> str:
    return f"{count} {noun if count == 1 else plural or noun + 's'}"


def _runs(store: FileResultStore, tenant: str, name: str) -> tuple[list[Run], int]:
    """The suite's runs that read back, and how many did not."""
    runs: list[Run] = []
    unread = 0
    for ref in store.list_runs(tenant, name):
        try:
            runs.append(store.read_run(ref))
        except (ValueError, OSError):
            unread += 1
    return runs, unread


def _names(suite: Suite | None) -> set[str]:
    if suite is None:
        return set()
    return {a.name for a in suite.assertions} | {a.name for a in suite.run_assertions}


def _name(check: Proposed) -> str:
    inner = check.params.get("inner")
    if isinstance(inner, Mapping):
        return str(inner.get("name", check.type))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return str(check.params.get("name", check.type))


def _propose(
    root: Path,
    source: _Source,
    target: Path,
    say: Callable[[str], None] | None = None,
    *,
    write: bool = True,
) -> Suggested:
    """The proposal's facts, the file written from them where `write`, and
    the lines standard error says, rendered from the facts. Without `write`
    nothing is written and no assistant is asked: what the MCP server
    returns. (ADR 0011 §1, as noted 2026-11-06)"""
    if write and target.exists():
        whose = _proposed_for(target)
        raise RefusedError(
            f"{target} is already there"
            + (f": {PROPOSAL} here is the proposal for {whose!r}" if whose else "")
            + ". digline suggest does not overwrite it, because what a person "
            "wrote in a proposal is not the command's to throw away. Move it or "
            "delete it, and run again (ADR 0063 §5)"
        )
    store = FileResultStore(root)
    everything, _ = read_recordings(store, source.tenant)
    split = split_recordings(everything, source.name)
    eligible = list(split.eligible)
    unassigned = len(split_recordings(everything, UNASSIGNED).recordings)
    reviewed = [c for c in source.captured if c.reviewed_answer is not None]
    common = Suggestion(
        tenant=source.tenant,
        suite=source.name,
        repository=source.repository,
        form=source.form,
        proposal=str(target),
        written=False,
        unassigned=unassigned,
    )
    if not eligible and not reviewed:
        # The recorder on, with no call naming the suite, is said instead of
        # `record on`: switching it on is not what is missing.
        on = not split.recordings and any(
            t.on for t in recorder_status(root, source.tenant)
        )
        nothing = dataclasses.replace(
            common,
            nothing=True,
            recorder_on=on,
            recorded_suites=tuple(sorted({r.suite for r in everything} - {UNASSIGNED}))
            if on
            else (),
        )
        return Suggested(path=None, lines=tuple(_lines(nothing, [])), facts=nothing)

    runs, unread = _runs(store, source.tenant, source.name)
    # A run with no case measured nothing, and is not counted as read.
    empty = sum(1 for run in runs if not run.results)
    found = measured([run for run in runs if run.results])
    responses: list[RecordedResponse] = [r.response for r in eligible]
    declared = declared_tools([r.setup for r in split.recordings])
    proposed = [
        *shape_checks(responses, found),
        *step_checks(
            responses,
            episodes=any(r.is_episode for r in eligible),
            declared=declared,
            found=found,
        ),
        *budget_checks(responses, found),
    ]
    held = _names(source.suite)
    judged = source.check if source.check is not None else JUDGED
    if judged not in held:
        proposed.append(judged_check(judged, found))
    kept = [check for check in proposed if _name(check) not in held]
    already = [check for check in proposed if _name(check) in held]

    noes = [
        c
        for c in reviewed
        if c.reviewed_answer is not None
        and not c.reviewed_answer.good
        and c.reviewed_answer.check == judged
    ]
    calibrated = any(
        c.calibration is not None and c.calibration.check == judged
        for c in source.cases
    )
    keys = list(dict.fromkeys(key for r in eligible for key in r.case))

    assisted: Merged | None = None
    told: list[str] = []
    if write and source.model is not None:
        assisted, told = _assist(
            source, kept, eligible, split.recordings, reviewed, declared, say
        )
        kept = list(assisted.checks)

    if write:
        text = _toml(source, kept, judged, noes, calibrated, keys, assisted)
        try:
            with target.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            raise RefusedError(
                f"{target} appeared while the proposal was being made, and is "
                "not overwritten (ADR 0063 §5)"
            ) from None

    facts = dataclasses.replace(
        common,
        written=write,
        setups={
            form: tuple(setup[:8] for setup in setups)
            for form, setups in setups_recorded(everything, source.name).items()
        },
        judged=judged,
        judge_declared=judged in held,
        plugins=() if judged in held else installed(),
        checks=tuple(
            ProposedCheck(
                number=number,
                type=check.type,
                name=_name(check),
                why=check.why,
                placeholders=len(check.placeholders),
            )
            for number, check in enumerate(kept, start=1)
        ),
        already=tuple(_name(check) for check in already),
        runs=found.runs,
        unread=unread,
        empty=empty,
        placeholders=sum(len(check.placeholders) for check in kept),
        suite_file=None if source.suite_file is None else source.suite_file.name,
        adopted=() if source.suite_file is None else tuple(_adopted(source.suite_file)),
        calibrated=calibrated,
        noes=len(noes),
        cases_file=source.cases_file,
        counterexample_by_assistant=assisted is not None
        and assisted.counterexample is not None,
        assisted=assisted is not None,
        groups=_groups(root, source, everything),
    )
    return Suggested(
        path=target if write else None, lines=tuple(_lines(facts, told)), facts=facts
    )


def _lines(found: Suggestion, told: Sequence[str]) -> list[str]:
    """What standard error says, rendered from the facts and nothing else,
    with the assistant's lines, `told`, where they go."""
    if found.nothing:
        nothing = (
            f"digline suggest: suite {found.suite!r} of tenant "
            f"{found.tenant!r} has no recording and no reviewed answer, so "
            "nothing is proposed and nothing was written. "
        )
        return [
            nothing
            + (
                f"The recorder of tenant {found.tenant!r} is on, and no call "
                f"it recorded named {found.suite!r}: "
                + (
                    "the suites with recordings are "
                    + ", ".join(repr(n) for n in found.recorded_suites)
                    if found.recorded_suites
                    else "no recorded call named a suite"
                )
                if found.recorder_on
                else "A suite begins where the application is recorded: digline "
                f"record on --tenant {found.tenant}, which is yours to run"
            ),
            *_unassigned(found),
        ]
    judged = found.judged
    lines = [
        f"digline suggest: {'wrote' if found.written else 'would write'} "
        f"{found.proposal}. It is a proposal, not a suite: no "
        "command of digline reads it, nothing in it is a verdict, and no "
        "answer was marked. Adopt its lines into your suite, and the commit "
        "is yours",
        "assumed:",
        f"  the form: {_form(found.form)}",
        *_setups(found),
        f"  the judge: {_judge(found)}",
    ]
    if not found.checks:
        lines.append("  each check: none proposed beyond what the suite declares")
    for check in found.checks:
        lines.append(f"  each check: {check.number}. {check.name}, {check.why}")
    for name in found.already:
        lines.append(
            f"  each check: {name} is not proposed again: the suite "
            "declares a check of that name"
        )
    lines.append(f"  each starting number: {_numbers(found)}")
    if found.adopted:
        adopted = found.adopted
        lines.append(
            f"  each starting number: {_many(len(adopted), 'placeholder')} "
            "you adopted "
            + ("is still at its" if len(adopted) == 1 else "are still at their")
            + f" most severe value, in {found.suite_file} at "
            + ("line " if len(adopted) == 1 else "lines ")
            + ", ".join(str(n) for n in adopted)
            + ": each fails until a measured number replaces it"
        )
    lines.append(
        "  the calibration band: "
        + (
            f"the suite holds a calibration case for {judged}; none proposed"
            if found.calibrated
            else f"a skeleton for {judged}, with the answer to paste and the "
            "band to place, strictly between 0 and 1, both yours"
        )
    )
    built = found.counterexample_by_assistant
    lines.append(
        "  the counterexample: "
        + (
            f"{_many(found.noes, 'reviewed no', 'reviewed noes')} for {judged}, "
            f"already in {found.cases_file}: the check must fail each"
            + ("; and counterexample-1, constructed by the assistant" if built else "")
            if found.noes
            else "counterexample-1, constructed by the assistant and marked as "
            f"constructed: an input and the answer {judged} must refuse, both "
            "in the file"
            if built
            else f"counterexample-1, constructed and marked as constructed: "
            f"its input is yours to write, one whose answer {judged} must "
            "refuse, and nothing in it was recorded"
        )
    )
    lines.append(
        f"  the regime: repository = {found.repository!r}: "
        + (
            "the file holds the assistant's text, which may quote what it "
            "read, so it stands where the capture's cases may (ADR 0023 §8)"
            if found.assisted and found.repository == "private"
            else (
                "without an assistant, the file quotes no recorded input or answer"
                if not found.assisted
                else "under public the assistant read no recorded input or "
                "answer, so the file quotes none"
            )
            + "; the rules read from the recordings, a tool's name or a key, "
            "are in its checks"
        )
    )
    lines.extend(told)
    lines.extend(_examined(found))
    lines.extend(_unassigned(found))
    return lines


#: The first line `_toml` writes, which names the suite as JSON writes it.
_FIRST_LINE = re.compile(
    r'^# \S+, written by `digline suggest` for suite ("(?:[^"\\]|\\.)*")'
)


def _proposed_for(target: Path) -> str | None:
    """The suite a proposal already there was written for, read from its
    first line, or `None` where that line is not the one digline writes."""
    try:
        with target.open(encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    found = _FIRST_LINE.match(first)
    if found is None:
        return None
    try:
        name = json.loads(found.group(1))
    except ValueError:
        return None
    return name[:40] if isinstance(name, str) else None


def _silent(line: str) -> None:
    """Where no front end is listening: a caller in code reads the lines."""


def _assist(
    source: _Source,
    kept: Sequence[Proposed],
    eligible: Sequence[Recording],
    recordings: Sequence[Recording],
    reviewed: Sequence[Case],
    declared: Sequence[str],
    say: Callable[[str], None] | None,
) -> tuple[Merged, list[str]]:
    """The assistant asked once, what it costs said first, and its reply
    merged. The lines it returns are counts and digline's words: what the
    assistant wrote reaches the file alone. (ADR 0063 §4, §6)"""
    assert source.model is not None
    judge = assistant(source.model, source.model_from)
    given = material(
        suite=source.name,
        regime=source.repository,
        eligible=eligible,
        reviewed=reviewed,
        checks=kept,
        declared=declared,
    )
    tell = say if say is not None else _silent
    tell(f"assistant: {source.model}, from {source.model_from}")
    tell(announcement(source.model, judge, given, recordings))
    reply = ask(judge, given.prompt)

    lines = ["the assistant:"]
    if given.regime == "private":
        # Two reasons, counted apart: a setup no longer in force is not the
        # bound, and was said as if it were. (P-1588)
        bound = given.recordings_left + given.reviewed_left
        earlier = given.recordings_earlier
        lines.append(
            f"  the regime: under private the assistant read the text: "
            f"{_many(given.recordings, 'recording')} and "
            f"{_many(given.reviewed, 'reviewed answer')}, the newest of the "
            "setups in force, each whole"
            + (
                f"; left out: {earlier} under earlier setups; {bound} at the "
                f"bound of {MAX_RECORDINGS} recordings and {MAX_CHARS:,} "
                "characters"
                if bound or earlier
                else ""
            )
        )
    else:
        lines.append(
            "  the regime: under public the assistant read the shape, not the "
            "text: kinds, finishes, tools, the checks proposed and counts"
        )
    spent = (
        f"${judge.spent_usd:.4f}"
        if judge.every_cost_known
        else "not known: the call was not priced"
    )
    lines.append(
        f"  what it cost: {spent}, for {judge.tokens.input_tokens:,} input and "
        f"{judge.tokens.output_tokens:,} output tokens"
        if judge.calls - judge.uncounted_calls
        else f"  what it cost: {spent}"
    )
    if reply is None:
        lines.append(
            "  its reply was no JSON object: none of it was used, and the "
            "proposal is the rules' alone"
        )
        return merged(kept, {}), lines
    done = merged(kept, reply)
    wrote = [
        _many(done.rubrics, "rubric"),
        _many(done.sentences, "sentence") + " of why",
        _many(done.limits, "limit"),
        "a counterexample" if done.counterexample else "no counterexample",
    ]
    lines.append(
        f"  what it wrote: {', '.join(wrote)}, each marked as the assistant's "
        "in the file"
    )
    for reason, count in sorted(done.discarded.items()):
        lines.append(f"  discarded: {count} × {reason}")
    if done.counterexample is not None:
        refusing = refused_by(done.checks, done.counterexample.answer)
        lines.append(
            "  its counterexample: "
            + (
                f"refused without a judge by {', '.join(refusing)}"
                if refusing
                else "refused by no check without a judge: only the judge can refuse it"
            )
        )
    return done, lines


def _form(form: str | None) -> str:
    if form is None:
        return (
            "suite.toml, the suite does not exist yet; the proposal is always "
            "TOML, and a target that is a function needs a suite.py "
            "(docs/declarative.md, What it cannot say)"
        )
    if form == "suite.py":
        return (
            "suite.py, as the suite is; the proposal is always TOML, so its "
            "lines are translated into the suite by hand"
        )
    return "suite.toml, as the suite is; its lines are added to it by hand"


def _setups(found: Suggestion) -> list[str]:
    """The setup in force per form, every earlier one of that form named
    beside it, and where more than one is named, the command that says how
    two of them differ. (`digline record compare`, ADR 0058 §10)"""
    forms: list[str] = []
    by_form = found.setups or {}
    named: list[tuple[str, str]] = []
    for form, said in ((False, "single calls"), (True, "episodes")):
        setups = list(by_form.get(form, ()))
        if not setups:
            continue
        *earlier, in_force = setups
        forms.append(
            f"{in_force} for {said}"
            + (
                f", the newest of {len(setups)} recorded, after " + ", ".join(earlier)
                if earlier
                else ""
            )
        )
        named.append((earlier[-1] if earlier else "", in_force))
    lines = [
        "  the setup its target reproduces: "
        + ("; ".join(forms) if forms else "none recorded")
    ]
    pairs = [(a, b) for a, b in named if a]
    pair = pairs[0] if pairs else (named[0][1], named[1][1]) if len(named) > 1 else None
    if pair is not None:
        lines.append(
            "  to read how two setups differ"
            + (", once the proposal is your suite" if found.form is None else "")
            + f": digline record compare --tenant {found.tenant} --suite "
            f"<your suite> --setup {pair[0]} {pair[1]} --show-setup"
        )
    return lines


def _judge(found: Suggestion) -> str:
    judged = found.judged
    if found.judge_declared:
        return f"the one suite {found.suite!r} declares for {judged}, unchanged"
    return (
        f'none read: {judged} is proposed with judge = "provider/model", a '
        "placeholder that is refused until you name the provider plugin and "
        "the model, which are yours to choose; "
        + (
            f"the provider plugins installed here: {', '.join(found.plugins)}"
            if found.plugins
            else "no provider plugin is installed here"
        )
    )


def _numbers(found: Suggestion) -> str:
    runs = (
        f"{_many(found.runs, 'run')} read"
        + (
            f", {_many(found.unread, 'run')} that did not read back"
            if found.unread
            else ""
        )
        + (
            f", {_many(found.empty, 'run')} with no case, not counted"
            if found.empty
            else ""
        )
        if found.runs or found.unread or found.empty
        else "no run read"
    )
    return (
        f"{runs}; {_many(found.placeholders, 'placeholder')}, each the strictest "
        "value its check accepts and marked in the file, failing until a "
        "measured number replaces it"
    )


#: Each limit's most severe value, by its last name: what a placeholder is
#: written with, and what one adopted and never replaced still holds.
_SEVERE: Mapping[str, float] = {
    key.rpartition(".")[2]: value for key, value in PLACEHOLDER.items()
}

#: A limit marked as a placeholder, as the proposal writes it in TOML and as
#: it reads translated into Python: `maximum = 0  # placeholder: …`.
_MARKED = re.compile(
    r"([A-Za-z_]+)[ \t]*=[ \t]*([-+0-9.eE_]+)[ \t]*\)?[ \t]*,?[ \t]*#[ \t]*placeholder"
)


def _adopted(suite_file: Path) -> list[int]:
    """The lines of the suite's file that hold a limit still marked as a
    placeholder and still at its most severe value. Read as text: a value
    the person replaced, or a mark they took off, is theirs."""
    try:
        text = suite_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        marked = _MARKED.search(line)
        if marked is None or marked.group(1) not in _SEVERE:
            continue
        try:
            value = float(marked.group(2))
        except ValueError:
            continue
        if value == _SEVERE[marked.group(1)]:
            found.append(number)
    return found


def _groups(
    root: Path, source: _Source, everything: Sequence[Recording]
) -> tuple[SuggestGroup, ...]:
    """The groups not yet examined: for a suite that exists, the import's
    own listing, with how many answers no person has named; for one that
    does not, the answers counted by shape, as the listing counts them."""
    if source.suite is not None:
        listing = import_listing(root, source.suite, source.module, source.tenant)
        return tuple(
            SuggestGroup(
                shape=group.shape,
                answers=len(group.answers),
                recordings=group.recordings,
                waiting=sum(1 for a in group.answers if a.elected is None),
            )
            for group in listing.groups
        )
    return tuple(
        SuggestGroup(shape=shape, answers=answers, recordings=count, waiting=None)
        for shape, answers, count in answer_counts(everything, source.name)
    )


def _examined(found: Suggestion) -> list[str]:
    """How many recordings and answers are not yet examined, by group, and
    the command that examines them. Counts alone: no answer is chosen."""
    lines: list[str] = []
    for number, group in enumerate(found.groups, start=1):
        lines.append(
            f"not yet examined: group {number} · {_said(group.shape)} · "
            + (
                f"{_many(group.waiting, 'answer')} of {group.answers}, from "
                f"{_many(group.recordings, 'recording')}"
                if group.waiting is not None
                else f"{_many(group.answers, 'answer')} from "
                f"{_many(group.recordings, 'recording')}"
            )
        )
    if found.form is not None:
        lines.append(
            "to examine them: digline record import --tenant "
            f"{found.tenant} --suite <your suite>"
        )
    elif found.groups:
        lines.append(
            "to examine them, once the proposal is your suite: digline record "
            f"import --tenant {found.tenant} --suite <your suite>"
        )
    return lines


def _said(shape: Shape) -> str:
    form = "episodes" if shape.episode else "single calls"
    return f"{form}, {shape.kind or 'kind not recorded'}"


def _unassigned(found: Suggestion) -> list[str]:
    count = found.unassigned
    if not count:
        return []
    return [
        f"{_many(count, 'call')} of tenant {found.tenant!r} named no suite "
        f"({UNASSIGNED}): counted, and read for nothing here. To give them "
        f"a suite: digline record import --tenant {found.tenant} --suite "
        f"<your suite> --from {UNASSIGNED}"
    ]


# The file.


def _key(key: str) -> str:
    bare = key and all(ch.isascii() and (ch.isalnum() or ch in "_-") for ch in key)
    return key if bare else json.dumps(key, ensure_ascii=False)


def _value(value: object) -> str:
    """A value as TOML writes it: a basic string is JSON's, whose escapes TOML
    reads the same; a table is written inline."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        # DEL is the one control character JSON leaves as it is and a TOML
        # string refuses; an assistant's rubric may hold one.
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    if isinstance(value, Mapping):
        table = cast(Mapping[str, object], value)
        items = ", ".join(f"{_key(k)} = {_value(v)}" for k, v in table.items())
        return "{ " + items + " }" if items else "{}"
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_value(v) for v in cast(Sequence[object], value)) + "]"
    raise TypeError(f"no TOML for {type(value).__name__}")


def _placeholder(key: str, check: Proposed, prefix: str = "") -> str:
    if f"{prefix}{key}" in check.assisted:
        return (
            "  # from the assistant: a draft, yours to read"
            if key == "rubric"
            else "  # from the assistant, not measured"
        )
    if f"{prefix}{key}" not in check.placeholders:
        return ""
    if key == "judge":
        return (
            "  # placeholder: yours to write, "
            "docs/declarative.md#the-judge-by-coordinates"
        )
    return "  # placeholder: yours to write"


def _check(check: Proposed) -> list[str]:
    why = textwrap.wrap(
        check.why, width=76, initial_indent="# ", subsequent_indent="# "
    )
    said = textwrap.wrap(
        f"the assistant: {check.said}",
        width=76,
        initial_indent="# ",
        subsequent_indent="#   ",
    )
    lines = [
        "",
        "[[assertions]]",
        *why,
        *(said if check.said else []),
        f'type = "{check.type}"',
    ]
    tables: list[tuple[str, Mapping[str, object]]] = []
    for key, value in check.params.items():
        if key == "inner" and isinstance(value, Mapping):
            tables.append((key, value))  # pyright: ignore[reportUnknownArgumentType]
            continue
        lines.append(f"{_key(key)} = {_value(value)}{_placeholder(key, check)}")
    for key, table in tables:
        lines.append("")
        lines.append(f"  [assertions.{key}]")
        for inner, value in table.items():
            lines.append(
                f"  {_key(inner)} = {_value(value)}"
                f"{_placeholder(inner, check, f'{key}.')}"
            )
    return lines


def _toml(
    source: _Source,
    kept: Sequence[Proposed],
    judged: str,
    noes: Sequence[Case],
    calibrated: bool,
    keys: Sequence[str],
    assisted: Merged | None = None,
) -> str:
    lines = [
        f"# {PROPOSAL}, written by `digline suggest` for suite "
        f"{json.dumps(source.name)} of tenant {json.dumps(source.tenant)}.",
        "#",
        "# A proposal, not a suite: no command of digline reads this file. Adopt",
        "# its lines into your suite by hand, and the commit is yours. Nothing",
        "# here is a verdict and no answer was marked. Every value marked",
        "# `placeholder` fails until you write a measured one. (ADR 0063)",
    ]
    if source.suite is None:
        lines += [
            "",
            "[suite]",
            f"tenant = {_value(source.tenant)}",
            f"name = {_value(source.name)}",
            "# environment = WRITE: mandatory, with no default: where it runs",
            f"# {source.cases_file} is written by digline record import; until",
            "# then the suite has no case.",
            f"cases = [{_value(source.cases_file)}]",
            "# A starting point: a reviewed answer needs the target asked at "
            "least twice.",
            "samples = 3",
            'min_agreement = "2/3"',
            "",
            "[capture]",
            f"cases_file = {_value(source.cases_file)}",
            f"repository = {_value(source.repository)}",
            f"check = {_value(judged)}",
            "",
            "# [target] is yours to write: the call the setup in force makes",
            "# (docs/declarative.md, [target]). A suite whose cases are all",
            "# reviewed answers may leave it out.",
        ]
    else:
        lines += [
            "#",
            f"# Suite {json.dumps(source.name)} declares [suite] and [capture]: "
            "these are the",
            "# checks to add, and the cases to paste into a file it reads.",
        ]
    for check in kept:
        lines += _check(check)
    lines.append("")
    built = assisted.counterexample if assisted is not None else None
    if noes:
        lines += [
            f"# The counterexample: the reviewed noes for {judged}, already in",
            f"# {source.cases_file}, which the check must fail:",
            *(f"#   {case.id}" for case in noes),
        ]
    if built is not None:
        constructed = {
            "id": "counterexample-1",
            "vars": dict(built.vars),
            "metadata": {
                "constructed": "by the assistant of digline suggest, not "
                f"recorded: an input whose answer {judged} must refuse",
                "answer": built.answer,
            },
        }
        if noes:
            lines.append("")
        lines += [
            "# The counterexample the assistant constructed, not recorded: paste",
            "# it into a cases file the suite reads. It is answered by the",
            "# target, so the suite needs a [target]. `metadata.answer` is the",
            "# answer the suite must refuse:",
            # ASCII: a model's text may hold a character a TOML comment may not.
            "# " + json.dumps(constructed),
        ]
    elif not noes:
        vars_ = {key: "WRITE" for key in keys}
        constructed = {
            "id": "counterexample-1",
            "vars": vars_,
            "metadata": {
                "constructed": "by digline suggest, not recorded: an input "
                f"whose answer {judged} must refuse"
            },
        }
        lines += [
            "# The counterexample, constructed and not recorded: a suite that",
            "# cannot fail measures nothing. Paste it into a cases file the",
            f"# suite reads, and write the input whose answer {judged} must",
            "# refuse. It is answered by the target, so the suite needs a",
            "# [target]:",
            "# " + json.dumps(constructed, ensure_ascii=False),
        ]
    if not calibrated:
        skeleton = {
            "id": f"calibration-{judged}",
            "calibration": {
                "check": judged,
                "output": "PASTE an answer you know is partly right",
                "input": "PASTE its question",
                "low": "PLACE",
                "high": "PLACE",
            },
        }
        lines += [
            "",
            "# The calibration skeleton (ADR 0024 §4.1): the answer and the band,",
            "# strictly between 0 and 1, are yours. Paste it into a cases file:",
            "# " + json.dumps(skeleton, ensure_ascii=False),
        ]
    return "\n".join(lines) + "\n"
