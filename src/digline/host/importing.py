"""The import: recorded answers made a suite's cases, by a person's yes or no.
(ADR 0058 §4, §7; ADR 0059 §1–§4; ADR 0023 §3, §4, §6, §7, §8, §9, §11)

**Two invocations, as ADR 0023 §4 has them.** `import_listing` reads and writes
nothing: every answer the recordings hold for one suite, grouped by the shape
of the output. `import_elect` writes the answers a person named, each as a
reviewed answer with their yes or no and their mark, and nothing else. There
is no dialogue, no default and no preselection: an answer nobody named stays
out.

**What it refuses before it shows anything**: recordings of another tenant
than the suite's, because bringing material across tenants is the bridge,
which is planned and not built (ADR 0058 §4, ADR 0034 §1); and a suite with no
capture source, `Suite.capture` or a `[capture]` table (ADR 0059 §4).

**What is named.** An answer is a pair, an input and a recorded answer to it:
its id is `capture_id(vars)` (ADR 0023 §6) and the first eight characters of
the answer's digest. That is the id the listing shows and `--good` and `--bad`
take, so a person says yes or no about an answer, not about an input. The case
written is a `ReviewedAnswer` under that id, for the check the source names
(ADR 0059 §1), with the person's mark in `metadata["reviewed_by"]`: given with
every writing invocation, never read from git or the environment. **Where the
suite declares `deterministic_output`, a yes also writes the answer as the
`expected` of an ordinary case**, under `capture_id(vars)`, with the same mark.
A no never does, and nowhere else is an expected written (ADR 0023 §11 as
amended).

**The declaration is printed at every use**: tenant, suite, `cases_file`,
`repository` and `check`, at the head of the listing and before the line of
each case written, so a copied declaration is in front of the person each time
(ADR 0059 §4).

**Under which setup.** The setup in force is the `setup_digest` of the newest
eligible recording **of the same form**: an episode's among the episodes, a
single call's among the single calls, the partition the groups are made in. An
answer recorded under it may be elected; one recorded only under earlier
setups is shown, and never elected: a yes about an answer the current setup
did not give says nothing about it. Per form, because an episode and the calls
an application makes outside one are two setups by construction: a turn that
was recorded last would otherwise put every single call under an earlier
setup, and the same answer would read as not electable in one listing and be
written from `--from _unassigned` in another (ADR 0059 §3).

**The listing groups and counts, and never ranks or proposes** (ADR 0059 §3).
A group is the shape of the output: the core's `OutputKind` for a single call,
and for an episode the actors of its steps in order and the last finish they
carry. Groups come in the order of their first answer, answers inside a group
in the files' order, each process's subdirectory and then the number the
writer gave. Nothing is sorted by a count, no answer is marked as likely, and
there is no way to elect them all.

**What is counted and said, and never a case**: orphans (ADR 0058 §5), calls
whose episode is not among the files, interrupted episodes, recordings over the
ceiling of what a recording keeps, and files that are not readable recordings.
Calls made inside an episode are part of that episode's case.

**The watermark** is the newest `recorded_at` among the recordings of the suite
the listing read, written on every case an election writes as
`examined_through` (ADR 0023 §9). It is the only memory the import keeps, and
it lives in the draft. An election of nothing writes nothing, so it moves no
watermark: that is 0023 §9's hole, stated there and left as it is.

**One view, two readers.** `ImportListing` is the structure the local page
reads, and `listing_lines` and `written_lines` are the text the CLI prints of
it, built here so that a front end lays it out and builds no sentence.

**It writes and stops**: no commit, no run, no promotion (ADR 0023 §7).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from digline.core.capture import capture_id
from digline.core.recording import Recording, RecordingRefusedError, instant_of
from digline.core.refused import RefusedError
from digline.core.run import RecordedResponse, restore_output
from digline.core.types import OutputKind
from digline.host.toml_suite import read_cases, within_perimeter
from digline.recorder import UNASSIGNED
from digline.run.suite import CaptureSource, Case, Suite
from digline.store.file_store import FileResultStore

__all__ = [
    "Declaration",
    "ImportAnswer",
    "ImportGroup",
    "ImportListing",
    "Shape",
    "SuiteRecorded",
    "answer_id",
    "answer_state",
    "capture_file",
    "closing_lines",
    "group_line",
    "import_elect",
    "import_listing",
    "imported_since",
    "input_line",
    "listing_lines",
    "read_recordings",
    "refuse_another_tenant",
    "group_setup_line",
    "setup_line",
    "split_recordings",
    "unloaded_capture",
    "written_lines",
]

#: What every case the import writes says about where it came from.
SOURCE = "recordings"

#: The first eight characters of a digest: how an answer and a setup are named.
SHORT = 8


@dataclass(frozen=True, slots=True)
class Declaration:
    """What the suite declares about where its captured cases go: printed in
    whole at every use, the same way each time. (ADR 0059 §4)"""

    tenant: str
    suite: str
    cases_file: Path
    repository: str
    check: str | None
    #: Where the recordings were read from when it is not the suite itself:
    #: `_unassigned`, the calls that named no suite. `None` is the suite's own.
    taken_from: str | None = None
    #: The directory that holds `.digline/`, which the file is said relative
    #: to. A `suite.py` resolves the file from its own path and a `suite.toml`
    #: from the one it was given, so one printed it whole and the other as
    #: typed; said from the repository, both read the same.
    root: Path | None = None

    @property
    def shown(self) -> str:
        """The cases file as the person reads it: relative to the repository
        where it is inside it, and whole otherwise."""
        if self.root is None:
            return str(self.cases_file)
        try:
            return str(self.cases_file.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(self.cases_file)

    def line(self) -> str:
        check = self.check if self.check is not None else "none declared"
        taken = "" if self.taken_from is None else f" · read from {self.taken_from}"
        return (
            f"tenant {self.tenant!r} · suite {self.suite}{taken} · writes to "
            f"{self.shown} · repository {self.repository} · check {check}"
        )


@dataclass(frozen=True, slots=True)
class Shape:
    """The shape of an output, which is what the listing groups by.

    `episode` is false for a single call, whose shape is its `OutputKind`
    alone until a call carries a finish (ADR 0057's schema 23). For an episode,
    `actors` are its steps' actors in order and `finish` the last finish they
    carry. `None` is *not recorded*, never a kind."""

    episode: bool
    kind: OutputKind | None
    actors: tuple[str, ...] = ()
    finish: str | None = None

    def says(self) -> str:
        kind = self.kind or "kind not recorded"
        if not self.episode:
            return f"a single call, {kind}"
        steps = " → ".join(self.actors) if self.actors else "no step recorded"
        return (
            f"an episode, {kind}, steps {steps}, finish {self.finish or 'not recorded'}"
        )


@dataclass(frozen=True, slots=True)
class ImportAnswer:
    """One recorded answer to one input: what a person names.

    `id` is the pair's, `capture_id(vars)` and the answer's digest; `case` is
    the input's. `times` is how many recordings gave this answer, `first_at`
    the earliest `recorded_at` among them, and `setups` the setups they were
    made under, in the order first met. `elected` is the person's yes or no the
    draft already holds for this answer, or `None`. `refusal` says why it
    cannot be elected, or is `None` where it can. `attached` is, for an
    episode, how many calls were found carrying its id. `call_sites` are the
    functions the calls were made from, where they named no suite, in the
    order first met: what a person reads to give them one.
    `case_from_first_call` is an episode the proxy read off the wire with no
    case given, whose case is its first call's (ADR 0062 §3)."""

    id: str
    case: str
    vars: Mapping[str, object]
    text: str
    kind: OutputKind | None
    input: str | None
    times: int
    first_at: str | None
    setups: tuple[str, ...]
    elected: bool | None
    refusal: str | None
    attached: int
    call_sites: tuple[str, ...] = ()
    case_from_first_call: bool = False
    #: The setup in force for this answer's form, an episode's or a single
    #: call's, or `None` where no recording of it is eligible.
    in_force: str | None = None

    @property
    def electable(self) -> bool:
        return self.refusal is None


@dataclass(frozen=True, slots=True)
class ImportGroup:
    """The answers whose output has one shape, in the files' order."""

    shape: Shape
    answers: tuple[ImportAnswer, ...]
    #: The setup in force for the group's form, which the listing says under
    #: its heading.
    setup: str | None = None

    @property
    def recordings(self) -> int:
        return sum(answer.times for answer in self.answers)


@dataclass(frozen=True, slots=True)
class ImportListing:
    """What one suite's recordings hold, as the person sees it before naming
    anything: the structure the CLI prints and the local page reads."""

    declaration: Declaration
    #: The setup in force per form: `True` for the episodes, `False` for the
    #: single calls, `None` where the form has no eligible recording.
    setups: Mapping[bool, str | None]
    deterministic_output: bool
    samples: int
    groups: tuple[ImportGroup, ...]
    recordings: int
    orphans: int
    detached: int
    interrupted: int
    oversize: int
    unreadable: int
    examined_through: str | None

    @property
    def answers(self) -> tuple[ImportAnswer, ...]:
        return tuple(answer for group in self.groups for answer in group.answers)


def answer_id(vars: Mapping[str, object], text: str) -> str:  # noqa: A002 — `Case.vars`
    """The id of an answer to an input: the input's `capture_id` and the first
    eight characters of the answer's SHA-256."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:SHORT]
    return f"{capture_id(vars)}-{digest}"


def capture_file(
    suite: Suite, module: ModuleType | None, root: Path
) -> tuple[CaptureSource, Path]:
    """The suite's capture source and its file, resolved from the suite file's
    directory and kept inside the perimeter, or a refusal that says why there
    is none."""
    source = suite.capture
    if source is None:
        raise RefusedError(
            f"suite {suite.name!r} declares no capture source: declare "
            "Suite.capture = CaptureSource(cases_file=..., repository="
            '"private" or "public", check=...) in a suite.py, or a [capture] '
            "table in a suite.toml, and load that file beside the suite's own "
            "cases (ADR 0059 §4)"
        )
    return source, within_perimeter(
        _beside(source, module, root),
        root.resolve(),
        "capture",
        f"suite {suite.name!r}",
    )


def _beside(source: CaptureSource, module: ModuleType | None, root: Path) -> Path:
    """`cases_file` read from the suite file's directory where it is relative.
    A `suite.toml` resolves it when it is loaded, so it arrives absolute."""
    if source.cases_file.is_absolute():
        return source.cases_file
    file = getattr(module, "__file__", None)
    return (Path(file).parent if file else root) / source.cases_file


def unloaded_capture(suite: Suite, module: ModuleType | None, root: Path) -> list[str]:
    """The ids in the suite's capture file that the suite did not load, in
    the file's order. Empty where the suite declares no capture source, or
    its file is absent or holds no case.

    A suite loads its capture file itself, with `read_cases` or in `cases`,
    and a suite that declared the file and forgot to load it would run without
    the cases a person elected, and say nothing. So `load_suite` asks this, for
    both forms, and refuses by name. (ADR 0023 §7)
    """
    if suite.capture is None:
        return []
    loaded = {case.id for case in suite.cases}
    return [
        case.id
        for case in read_cases(_beside(suite.capture, module, root))
        if case.id not in loaded
    ]


def refuse_another_tenant(
    tenant: str, suite: Suite, *, what: str = "imported into"
) -> None:
    """Refuse `tenant`'s recordings for a suite of another tenant, before
    anything is shown. Every reader of a suite's recordings asks it, the import
    and `digline record compare` alike; `what` is the verb of the sentence."""
    if tenant != suite.tenant:
        raise RefusedError(
            f"the recordings of tenant {tenant!r} are not {what} suite "
            f"{suite.name!r}, whose tenant is {suite.tenant!r}: bringing "
            "material made for one tenant into another's suite is the bridge, "
            "which is planned and not built, and until it exists the "
            "recordings stay in the perimeter they were made in (ADR 0058 §4, "
            "ADR 0034 §1)"
        )


def read_recordings(store: FileResultStore, tenant: str) -> tuple[list[Recording], int]:
    """Every readable recording of the tenant's application, in the files'
    order, and how many files were not readable recordings.

    A recording of the gate (`origin: "gate"`) is not the application's: it
    is a call a `digline run` made, recorded in another process while the run
    was in progress. It is left out here, which is every list, import, `where`
    and compare reads, and counted by `digline record status` alone. Never
    deleted. (ADR 0058, as amended 2026-11-05)"""
    found: list[Recording] = []
    unreadable = 0
    for path in sorted(store.recordings_dir(tenant).glob("*/*.json")):
        if path.name.startswith("."):
            continue
        try:
            recording = store.read_recording(path)
        except (ValueError, OSError):
            unreadable += 1
            continue
        if recording.origin is None:
            found.append(recording)
    return found, unreadable


def _draft(path: Path) -> dict[str, Case]:
    """The cases already in the draft, by id."""
    return {case.id: case for case in read_cases(path)}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _answer(response: RecordedResponse) -> str | None:
    return response.output


@dataclass(frozen=True, slots=True)
class SuiteRecorded:
    """One suite's recordings, split the way every reader of them splits them:
    those that are a case with an answer, in the files' order, and the counts
    of those that are not."""

    recordings: tuple[Recording, ...]
    eligible: tuple[Recording, ...]
    orphans: int
    detached: int
    interrupted: int
    oversize: int
    #: For an episode's own id, how many calls were found carrying it.
    attached: Mapping[str, int]


def split_recordings(everything: Sequence[Recording], suite: str) -> SuiteRecorded:
    """The recordings of `suite` among a tenant's, split into the eligible and
    the counted. A call made inside an episode is part of that episode's case;
    orphans, interrupted episodes, calls whose episode is not among the files
    and recordings with no answer kept are counted, and are not cases."""
    episodes = {r.id for r in everything if r.id is not None}
    attached: dict[str, int] = {}
    for recording in everything:
        if recording.episode is not None:
            attached[recording.episode] = attached.get(recording.episode, 0) + 1

    mine = [r for r in everything if r.suite == suite]
    orphans = detached = interrupted = oversize = 0
    eligible: list[Recording] = []
    for recording in mine:
        if recording.episode is not None:
            # Part of an episode's case, or a call whose episode is not here.
            if recording.episode not in episodes:
                detached += 1
            continue
        if recording.orphan:
            orphans += 1
        elif recording.interrupted:
            interrupted += 1
        elif recording.response.oversize or _answer(recording.response) is None:
            oversize += 1
        else:
            eligible.append(recording)
    return SuiteRecorded(
        recordings=tuple(mine),
        eligible=tuple(eligible),
        orphans=orphans,
        detached=detached,
        interrupted=interrupted,
        oversize=oversize,
        attached=attached,
    )


def _shape(recording: Recording) -> Shape:
    if not recording.is_episode:
        return Shape(episode=False, kind=recording.response.kind)
    steps = recording.response.steps or ()
    finishes = [step.finish for step in steps if step.finish is not None]
    return Shape(
        episode=True,
        kind=recording.response.kind,
        actors=tuple(step.actor for step in steps),
        finish=finishes[-1] if finishes else None,
    )


def shape_counts(
    everything: Sequence[Recording], suite: str
) -> tuple[tuple[Shape, int], ...]:
    """How many of `suite`'s eligible recordings have each output shape, in
    the order each shape is first met: the listing's groups, read by shape
    alone. It needs no capture declaration, because it decides nothing about
    a case: no draft is read, no answer is paired, nothing is said to be
    electable. For a suite whose recordings no suite declaration reads yet,
    which `import_listing` refuses (`capture_file`)."""
    counts: dict[Shape, int] = {}
    for recording in split_recordings(everything, suite).eligible:
        shape = _shape(recording)
        counts[shape] = counts.get(shape, 0) + 1
    return tuple(counts.items())


def setups_in_force(
    everything: Sequence[Recording], suite: str
) -> dict[bool, str | None]:
    """The setup in force for `suite` per form, as the listing says it: for
    the episodes, `True`, and for the single calls, `False`, the setup of the
    newest eligible recording of that form."""
    return _setups_in_force(split_recordings(everything, suite).eligible)


def _refusal(
    recordings: Sequence[Recording],
    setup: str | None,
    elected: bool | None,
    found: Case | None,
) -> str | None:
    """Why this answer cannot be elected, or `None` where it can."""
    first = recordings[0]
    if elected is not None or found is not None:
        return "already in the file"
    if all(r.setup_digest != setup for r in recordings):
        return (
            "recorded only under earlier setups: a yes or no about an answer "
            "the setup in force did not give says nothing about it"
        )
    if not first.response.input:
        return (
            "recorded with no input: the judge reads the question beside the "
            "answer, and there is none to give it"
        )
    if first.response.kind == "conversation":
        return (
            "a conversation, which a cases file cannot hold as an answer in "
            "this release"
        )
    return None


def import_listing(
    root: Path,
    suite: Suite,
    module: ModuleType | None,
    tenant: str,
    *,
    taken_from: str | None = None,
) -> ImportListing:
    """Everything the person sees before naming an answer. Writes nothing.

    `taken_from` is `_unassigned` to list the calls that named no suite as
    this suite's: eligible as its own are, under its capture declaration, and
    written into its cases file. The recordings stay where they are, and what
    was elected from them is read back by the pair, as for the suite's own.
    No other name is taken: a call that named another suite is that suite's.
    """
    if taken_from is not None and taken_from != UNASSIGNED:
        raise RefusedError(
            f"--from takes {UNASSIGNED}, the calls that named no suite, and "
            f"nothing else: a call that named suite {taken_from!r} is that "
            "suite's, and is imported from it"
        )
    refuse_another_tenant(tenant, suite)
    source, path = capture_file(suite, module, root)
    store = FileResultStore(root)
    draft = _draft(path)
    everything, unreadable = read_recordings(store, tenant)
    split = split_recordings(everything, taken_from or suite.name)
    in_force = _setups_in_force(split.eligible)

    by_answer: dict[str, list[Recording]] = {}
    for recording in split.eligible:
        text = cast(str, _answer(recording.response))
        by_answer.setdefault(answer_id(recording.case, text), []).append(recording)

    groups: dict[Shape, list[ImportAnswer]] = {}
    for pair, recordings in by_answer.items():
        first = recordings[0]
        held = draft.get(pair)
        elected = (
            None
            if held is None or held.reviewed_answer is None
            else held.reviewed_answer.good
        )
        dated = [r.recorded_at for r in recordings if r.recorded_at is not None]
        setup = in_force[first.id is not None]
        groups.setdefault(_shape(first), []).append(
            ImportAnswer(
                id=pair,
                case=capture_id(first.case),
                vars=first.case,
                text=cast(str, _answer(first.response)),
                kind=first.response.kind,
                input=first.response.input,
                times=len(recordings),
                first_at=min(dated, key=instant_of) if dated else None,
                setups=tuple(dict.fromkeys(r.setup_digest for r in recordings)),
                elected=elected,
                refusal=_refusal(recordings, setup, elected, held),
                attached=sum(split.attached.get(r.id, 0) for r in recordings if r.id),
                call_sites=tuple(
                    dict.fromkeys(r.call_site for r in recordings if r.call_site)
                ),
                case_from_first_call=first.case_from_first_call,
                in_force=setup,
            )
        )
    stamps = [r.recorded_at for r in split.recordings if r.recorded_at is not None]
    return ImportListing(
        declaration=Declaration(
            tenant=tenant,
            suite=suite.name,
            cases_file=path,
            repository=source.repository,
            check=source.check,
            taken_from=taken_from,
            root=root,
        ),
        setups=in_force,
        deterministic_output=suite.deterministic_output,
        samples=suite.samples,
        groups=tuple(
            ImportGroup(
                shape=shape, answers=tuple(answers), setup=in_force[shape.episode]
            )
            for shape, answers in groups.items()
        ),
        recordings=len(split.recordings),
        orphans=split.orphans,
        detached=split.detached,
        interrupted=split.interrupted,
        oversize=split.oversize,
        unreadable=unreadable,
        examined_through=max(stamps, key=instant_of) if stamps else None,
    )


def _setups_in_force(eligible: Sequence[Recording]) -> dict[bool, str | None]:
    """The setup in force per form, an episode's (`True`) and a single
    call's (`False`): each the newest of its own form."""
    return {
        form: _setup_in_force([r for r in eligible if (r.id is not None) == form])
        for form in (True, False)
    }


def _setup_in_force(eligible: Sequence[Recording]) -> str | None:
    """The setup of the newest eligible recording: by `recorded_at` as an
    instant where the recordings carry it, the later in the files' order
    among equal instants, and otherwise the last in the files' order."""
    if not eligible:
        return None
    dated = [(i, r) for i, r in enumerate(eligible) if r.recorded_at is not None]
    if dated:
        _, newest = max(
            dated,
            key=lambda pair: (instant_of(cast(str, pair[1].recorded_at)), pair[0]),
        )
        return newest.setup_digest
    return eligible[-1].setup_digest


def import_elect(
    found: ImportListing,
    *,
    good: Iterable[str] = (),
    bad: Iterable[str] = (),
    by: str | None,
) -> tuple[str, ...]:
    """Write the answers named, each as a reviewed answer with the person's yes
    or no and mark, after the draft's last case, and return the ids written.
    Every refusal comes before anything is written: a regime that forbids the
    text, a source with no check, a suite that samples once, a missing mark,
    an id named twice or with both answers, an id the listing does not hold,
    an answer that cannot be elected, and, where the output is deterministic,
    two yeses about one input or an input whose expected the file holds."""
    declaration = found.declaration
    if declaration.repository == "public":
        raise RefusedError(
            f"suite {declaration.suite!r} declares repository = 'public': the "
            "import writes no third-party text there, and a recorded answer is "
            "that text. The derogation is a person writing the case by hand, "
            "and it is the owner of the text's to make: a software house "
            "hand-writing its client's text into its own repository is the act "
            "ADR 0023 §8 refuses"
        )
    if declaration.check is None:
        raise RefusedError(
            f"suite {declaration.suite!r} declares a capture source with no "
            "check: a yes or no at the import is a reviewed answer for one "
            "judged check, and the source names it, check=... (ADR 0059 §1)"
        )
    if found.samples < 2:
        raise RefusedError(
            f"suite {declaration.suite!r} samples {found.samples} time(s), and "
            "a reviewed answer needs at least 2: one judgement that disagrees "
            "with the person would fail the gate for noise nobody chose. Set "
            "samples (with min_agreement) before writing one (ADR 0059 §1)"
        )
    if by is None or not by.strip():
        raise RefusedError(
            "--by NAME is missing: the person who says yes or no puts their "
            "name to it, and it is never read from git or from the "
            "environment, because a name taken from a machine is inferred "
            "(ADR 0059 §1)"
        )
    named: dict[str, bool] = {}
    for verdict, ids in ((True, good), (False, bad)):
        for pair in ids:
            if pair in named:
                raise RefusedError(
                    f"{pair} is named twice: name each answer once, with "
                    "--good or --bad"
                )
            named[pair] = verdict
    if not named:
        raise RefusedError(
            "no answer named: --good ID or --bad ID, once for each answer to "
            "write. An answer not named stays out"
        )
    by_id = {answer.id: answer for answer in found.answers}
    for pair in named:
        answer = by_id.get(pair)
        if answer is None:
            raise RefusedError(
                f"{pair} is not an answer the recordings of suite "
                f"{declaration.suite!r} hold: nothing was written"
            )
        if answer.refusal is not None:
            raise RefusedError(f"{pair} cannot be written: {answer.refusal}")
    draft = _draft(declaration.cases_file)
    if found.deterministic_output:
        yes = [by_id[pair] for pair, verdict in named.items() if verdict]
        cases = [answer.case for answer in yes]
        twice = sorted({case for case in cases if cases.count(case) > 1})
        if twice:
            raise RefusedError(
                f"{', '.join(twice)}: two answers to one input are named --good, "
                "and the suite declares deterministic_output, where a yes is "
                "also the input's expected. One input has one expected answer"
            )
        held = sorted(case for case in cases if case in draft)
        if held:
            raise RefusedError(
                f"{', '.join(held)} is already in {declaration.cases_file.name}: "
                "the suite declares deterministic_output, a yes writes the "
                "input's expected, and the file holds one for it"
            )
    entries: list[dict[str, object]] = []
    for answer in found.answers:
        if answer.id not in named:
            continue
        entries.append(_reviewed(answer, named[answer.id], found, by))
        if named[answer.id] and found.deterministic_output:
            entries.append(_expected(answer, found, by))
    _append(declaration.cases_file, entries)
    return tuple(cast(str, entry["id"]) for entry in entries)


def _metadata(found: ImportListing, answer: ImportAnswer, by: str) -> dict[str, object]:
    metadata: dict[str, object] = {"source": SOURCE, "reviewed_by": by}
    if answer.in_force is not None:
        metadata["setup_digest"] = answer.in_force
    if found.examined_through is not None:
        metadata["examined_through"] = found.examined_through
    return metadata


def _output(answer: ImportAnswer) -> object:
    """The answer as a cases file holds it: the text, or the structure a
    structured answer was recorded as."""
    if answer.kind == "structured":
        return restore_output(answer.text, "structured")
    return answer.text


def _reviewed(
    answer: ImportAnswer, good: bool, found: ImportListing, by: str
) -> dict[str, object]:
    return {
        "id": answer.id,
        "reviewed_answer": {
            "output": _output(answer),
            "check": found.declaration.check,
            "good": good,
            "input": answer.input,
        },
        "metadata": _metadata(found, answer, by),
    }


def _expected(answer: ImportAnswer, found: ImportListing, by: str) -> dict[str, object]:
    """The case a yes also writes where the output is deterministic: the
    input, and the answer as its expected, with the person's mark. (ADR 0059
    §2)"""
    return {
        "id": answer.case,
        "vars": dict(answer.vars),
        "expected": _output(answer),
        "metadata": _metadata(found, answer, by),
    }


def _append(path: Path, entries: Sequence[Mapping[str, object]]) -> None:
    """Append, never rewrite (ADR 0023 §7): the bytes before the array's
    closing bracket stay as they were, and the new entries go after the last
    case. A file that does not parse is refused and left as it is."""
    written = [
        "  "
        + json.dumps(entry, indent=2, sort_keys=True, ensure_ascii=False).replace(
            "\n", "\n  "
        )
        for entry in entries
    ]
    if path.exists():
        read_cases(path)  # refuses, by name, a file that does not parse
        before = path.read_text(encoding="utf-8")
        closing = before.rstrip().rfind("]")
        head = before[:closing].rstrip()
        separator = "" if head.endswith("[") else ","
        text = head + separator + "\n" + ",\n".join(written) + "\n]\n"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "[\n" + ",\n".join(written) + "\n]\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def imported_since(
    root: Path, suite: Suite, module: ModuleType | None, tenant: str
) -> tuple[int | None, int]:
    """For `digline record status --suite`: how many of the suite's recordings
    were written after the newest `examined_through` its draft holds, and how
    many it has in all. `None` for the first is *never imported*: no case of
    the draft came from the recordings. A recording with no `recorded_at` is
    never counted as after the watermark. Both are compared as instants."""
    _, path = capture_file(suite, module, root)
    marks = [
        mark
        for case in _draft(path).values()
        if (mark := _text(case.metadata.get("examined_through"))) is not None
    ]
    store = FileResultStore(root)
    everything, _ = read_recordings(store, tenant)
    mine = [r for r in everything if r.suite == suite.name]
    if not marks:
        return None, len(mine)
    try:
        newest = max(instant_of(mark) for mark in marks)
    except RecordingRefusedError:
        raise RefusedError(
            f"{path}: a case's examined_through is not in the form the import "
            "writes it, a recorded_at in UTC with +00:00"
        ) from None
    return sum(
        1
        for r in mine
        if r.recorded_at is not None and instant_of(r.recorded_at) > newest
    ), len(mine)


def answer_state(answer: ImportAnswer) -> str:
    """Whether an answer can be named, said as the listing says it: already in
    the file with the flag that put it there, why it cannot be, or
    `electable`."""
    if answer.elected is not None:
        return f"already in the file, {'--good' if answer.elected else '--bad'}"
    if answer.refusal is not None:
        return f"not electable: {answer.refusal}"
    return "electable"


def input_line(answer: ImportAnswer) -> str:
    """The input an answer was given, as the listing prints it."""
    return json.dumps(answer.vars, ensure_ascii=False, sort_keys=True)


def _say_answer(answer: ImportAnswer) -> list[str]:
    setups = ", ".join(
        f"{s[:SHORT]}{'' if s == answer.in_force else ' (earlier)'}"
        for s in answer.setups
    )
    times = f" · ×{answer.times}" if answer.times > 1 else ""
    attached = f" · {answer.attached} calls attached" if answer.attached else ""
    made = [f"    made at: {', '.join(answer.call_sites)}"] if answer.call_sites else []
    return [
        f"  {answer.id} · {answer.first_at or 'undated'} · setup {setups}"
        f"{times}{attached}",
        *made,
        f"    input:  {input_line(answer)}"
        + (" (case from the first call)" if answer.case_from_first_call else ""),
        f"    answer: {answer.text}",
        f"    {answer_state(answer)}",
    ]


def _many(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def listing_lines(found: ImportListing) -> list[str]:
    """The listing as the person reads it: the declaration, then each group
    with its count, then what is not a case. Built here, laid out by the CLI,
    and in no order but the files'."""
    lines = [found.declaration.line(), f"  {setup_line(found)}"]
    for number, group in enumerate(found.groups, start=1):
        lines.append("")
        lines.append(group_line(number, group))
        lines.append(f"  {group_setup_line(group)}")
        for answer in group.answers:
            lines.extend(_say_answer(answer))
    lines.append("")
    lines.extend(closing_lines(found))
    return lines


def setup_line(found: ImportListing) -> str:
    """Whether the suite's output is deterministic. The setup in force is
    said under each group, since it is the group's form's."""
    return f"deterministic_output {'true' if found.deterministic_output else 'false'}"


def group_setup_line(group: ImportGroup) -> str:
    """The setup in force for a group's form: the episodes' or the single
    calls'."""
    form = "episodes" if group.shape.episode else "single calls"
    return f"setup in force for {form}: {(group.setup or 'none')[:SHORT]}"


def group_line(number: int, group: ImportGroup) -> str:
    """A group's heading: its number, its shape and what it counts."""
    return (
        f"group {number} · {group.shape.says()} · "
        f"{_many(len(group.answers), 'answer')} from "
        f"{_many(group.recordings, 'recording')}"
    )


def closing_lines(found: ImportListing) -> list[str]:
    """What the listing says after its groups: what it counted and what is not
    a case, then why nothing can be written or how to write."""
    lines = [
        f"{_many(len(found.answers), 'answer')} in "
        f"{_many(len(found.groups), 'group')}, from "
        f"{_many(found.recordings, 'recording')} of the suite; not cases: "
        f"{found.orphans} orphans, {found.detached} calls whose episode is not "
        f"among the files, {found.interrupted} interrupted episodes, "
        f"{found.oversize} over the ceiling of a recording, {found.unreadable} "
        "files that are not readable recordings"
    ]
    if found.declaration.repository == "public":
        lines.append(
            'repository = "public": this lists, and writing is refused, because '
            "a recorded answer is third-party text (ADR 0023 §8)"
        )
    elif any(answer.electable for answer in found.answers):
        lines.append(
            "to write, name each answer with --good ID or --bad ID, and give "
            "--by NAME, your own name. An answer not named stays out"
        )
    return lines


def written_lines(found: ImportListing, written: Sequence[str]) -> list[str]:
    """What a writing invocation says: before the line of each case written,
    the declaration it was written under, whole. (ADR 0059 §4)"""
    lines: list[str] = []
    for case_id in written:
        lines.append(found.declaration.line())
        lines.append(f"  wrote {case_id}")
    lines.append(
        f"{_many(len(written), 'case')} written to {found.declaration.shown}: "
        "the diff is the review and the commit is the signature; nothing was "
        "committed, run or promoted (ADR 0023 §7)"
    )
    return lines
