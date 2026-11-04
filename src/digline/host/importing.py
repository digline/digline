"""The narrow import: recordings made a suite's cases, by a person's yes or no.
(ADR 0058 §4, §7; ADR 0023 §3, §4, §6, §7, §8, §9, §11)

**Two invocations, as ADR 0023 §4 has them.** `import_listing` reads and writes
nothing: every case the recordings hold for one suite, with its input and the
answers recorded under the setup in force. `import_elect` writes the cases a person
named, each with the label they gave, and nothing else. There is no dialogue,
no default and no preselection: a case nobody named stays out.

**What it refuses before it shows anything**: recordings of another tenant
than the suite's, because bringing material across tenants is the bridge,
which is planned and not built (ADR 0058 §4, ADR 0034 §1); and a suite with no
`CaptureSource`, which a `suite.toml` cannot declare in this release
(ADR 0023 §3).

**What the recordings become.** A case is a recording's `case` compartment:
recordings with the same one are the same case, and its id is
`capture_id(vars)` (ADR 0023 §6). The case written carries `vars`, the label
and a little metadata; **the recorded answer is not its `expected`**, because
an expected inferred is the first thing ADR 0023 §11 forbids, and the answer
stays in the recording.

**Under which setup.** The setup in force is the `setup_digest` of the newest
eligible recording of the suite. A case's recordings under it are shown and
may be elected; its recordings under earlier setups are counted and shown, and
never elected: a person's yes about an answer the current setup did not give is
not a label for the current setup.

**What is counted and said, and never a case**: orphans (ADR 0058 §5), calls
whose episode is not among the files, interrupted episodes, recordings over the
ceiling of what a recording keeps, and files that are not readable recordings.
Calls made inside an episode are part of that episode's case.

**Nothing is ranked.** The order is the files' order: each process's
subdirectory, then the number the writer gave (ADR 0023 §4).

**The watermark** is the newest `recorded_at` among the recordings of the suite
the listing read, written on every case an election writes as
`examined_through` (ADR 0023 §9). It is the only memory the import keeps, and
it lives in the draft. An election of nothing writes nothing, so it moves no
watermark: that is 0023 §9's hole, stated there and left as it is.

**It writes and stops**: no commit, no run, no promotion (ADR 0023 §7).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from digline.core.aggregate import Label
from digline.core.capture import capture_id
from digline.core.recording import Recording
from digline.core.refused import RefusedError
from digline.core.run import RecordedResponse
from digline.host.toml_suite import SUITE_SUFFIX, read_cases, within_perimeter
from digline.run.suite import CaptureSource, Suite
from digline.store.file_store import FileResultStore

__all__ = [
    "ImportCase",
    "ImportListing",
    "SuiteRecorded",
    "import_elect",
    "imported_since",
    "import_listing",
    "capture_file",
    "read_recordings",
    "refuse_another_tenant",
    "refuse_data_suite",
    "split_recordings",
    "unloaded_capture",
]

#: What every case the import writes says about where it came from.
SOURCE = "recordings"


@dataclass(frozen=True, slots=True)
class ImportCase:
    """One case the recordings hold for the suite.

    `answers` are the outputs recorded under the setup in force, in the files'
    order. `earlier` is how many recordings of it were made under earlier
    setups, and `earlier_setups` how many distinct ones. `elected` is the label
    the draft already holds for it, or `None`. `attached` is, for an episode,
    how many calls were found carrying its id.
    """

    id: str
    vars: Mapping[str, object]
    kind: str
    answers: tuple[str, ...]
    earlier: int
    earlier_setups: int
    elected: Label | None
    attached: int

    @property
    def electable(self) -> bool:
        return bool(self.answers) and self.elected is None


@dataclass(frozen=True, slots=True)
class ImportListing:
    """What one suite's recordings hold, as the person sees it before naming
    anything."""

    tenant: str
    suite: str
    cases_file: Path
    repository: str
    setup: str | None
    cases: tuple[ImportCase, ...]
    recordings: int
    orphans: int
    detached: int
    interrupted: int
    oversize: int
    unreadable: int
    examined_through: str | None


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
            '"private" or "public") in its suite.py, and load that file beside '
            "its cases with read_cases (ADR 0023 §3)"
        )
    return source, within_perimeter(
        _beside(source, module, root),
        root.resolve(),
        "capture",
        f"suite {suite.name!r}",
    )


def _beside(source: CaptureSource, module: ModuleType | None, root: Path) -> Path:
    """`cases_file` read from the suite file's directory where it is relative."""
    if source.cases_file.is_absolute():
        return source.cases_file
    file = getattr(module, "__file__", None)
    return (Path(file).parent if file else root) / source.cases_file


def unloaded_capture(suite: Suite, module: ModuleType | None, root: Path) -> list[str]:
    """The ids in the suite's capture file that the suite did not load, in
    the file's order. Empty where the suite declares no capture source, or
    its file is absent or holds no case.

    A suite loads its capture file itself, with `read_cases`, and a suite
    that declared the file and forgot to load it would run without the cases
    a person elected, and say nothing. So `load_suite` asks this, and
    refuses by name. (ADR 0023 §7)
    """
    if suite.capture is None:
        return []
    loaded = {case.id for case in suite.cases}
    return [
        case.id
        for case in read_cases(_beside(suite.capture, module, root))
        if case.id not in loaded
    ]


def refuse_data_suite(spec: str) -> None:
    """A `suite.toml` cannot import in this release, said before it is loaded
    so the sentence is the reason and not a missing field."""
    if spec.endswith(SUITE_SUFFIX):
        raise RefusedError(
            f"{spec} is a data suite, and a data suite cannot declare where "
            "captured cases go in this release. Write a suite.py with "
            "Suite.capture = CaptureSource(cases_file=..., repository=...) "
            "and load that file beside its cases with read_cases. ADR 0023 §3 "
            "keeps the declaration in a suite.py, and whether recordings may "
            "be declared as data is a question ADR 0058 leaves open"
        )


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
    """Every readable recording of the tenant, in the files' order, and how
    many files were not readable recordings."""
    found: list[Recording] = []
    unreadable = 0
    for path in sorted(store.recordings_dir(tenant).glob("*/*.json")):
        if path.name.startswith("."):
            continue
        try:
            found.append(store.read_recording(path))
        except (ValueError, OSError):
            unreadable += 1
    return found, unreadable


def _draft(path: Path) -> dict[str, tuple[Label | None, str | None]]:
    """The cases already in the draft: label and watermark, by id."""
    return {
        case.id: (
            case.label,
            _text(case.metadata.get("examined_through")),
        )
        for case in read_cases(path)
    }


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
    episodes = {r.id for r in everything if r.steps is not None and r.id is not None}
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


def import_listing(
    root: Path, suite: Suite, module: ModuleType | None, tenant: str
) -> ImportListing:
    """Everything the person sees before naming a case. Writes nothing."""
    refuse_another_tenant(tenant, suite)
    source, path = capture_file(suite, module, root)
    store = FileResultStore(root)
    draft = _draft(path)
    everything, unreadable = read_recordings(store, tenant)
    split = split_recordings(everything, suite.name)
    mine, eligible, attached = split.recordings, split.eligible, split.attached

    setup = _setup_in_force(eligible)
    grouped: dict[str, list[Recording]] = {}
    for recording in eligible:
        grouped.setdefault(capture_id(recording.case), []).append(recording)
    cases: list[ImportCase] = []
    for case_id, recordings in grouped.items():
        current = [r for r in recordings if r.setup_digest == setup]
        earlier = [r for r in recordings if r.setup_digest != setup]
        first = recordings[0]
        cases.append(
            ImportCase(
                id=case_id,
                vars=first.case,
                kind="episode" if first.steps is not None else "call",
                answers=tuple(cast(str, _answer(r.response)) for r in current),
                earlier=len(earlier),
                earlier_setups=len({r.setup_digest for r in earlier}),
                elected=draft[case_id][0] if case_id in draft else None,
                attached=sum(attached.get(r.id, 0) for r in recordings if r.id),
            )
        )
    stamps = [r.recorded_at for r in mine if r.recorded_at is not None]
    return ImportListing(
        tenant=tenant,
        suite=suite.name,
        cases_file=path,
        repository=source.repository,
        setup=setup,
        cases=tuple(cases),
        recordings=len(mine),
        orphans=split.orphans,
        detached=split.detached,
        interrupted=split.interrupted,
        oversize=split.oversize,
        unreadable=unreadable,
        examined_through=max(stamps) if stamps else None,
    )


def _setup_in_force(eligible: Sequence[Recording]) -> str | None:
    """The setup of the newest eligible recording: by `recorded_at` where the
    recordings carry it, and otherwise the last in the files' order."""
    if not eligible:
        return None
    dated = [r for r in eligible if r.recorded_at is not None]
    if dated:
        return max(dated, key=lambda r: cast(str, r.recorded_at)).setup_digest
    return eligible[-1].setup_digest


def import_elect(
    found: ImportListing,
    *,
    positive: Iterable[str] = (),
    negative: Iterable[str] = (),
) -> tuple[str, ...]:
    """Write the named cases, each with its label, after the draft's last
    case, and return their ids. Every refusal comes before anything is
    written: a regime that forbids the text, an id named twice or with both
    labels, an id the listing does not hold, a case recorded only under an
    earlier setup, a case already in the draft."""
    if found.repository == "public":
        raise RefusedError(
            f"suite {found.suite!r} declares repository = 'public': the import "
            "writes no third-party text there, and a recorded case is that "
            "text. The derogation is a person writing the case by hand, and "
            "it is the owner of the text's to make: a software house "
            "hand-writing its client's text into its own repository is the "
            "act ADR 0023 §8 refuses"
        )
    named: dict[str, Label] = {}
    for label, ids in (("positive", positive), ("negative", negative)):
        for case_id in ids:
            if case_id in named:
                raise RefusedError(
                    f"{case_id} is named twice: name each case once, with one label"
                )
            named[case_id] = cast(Label, label)
    if not named:
        raise RefusedError(
            "no case named: --positive ID or --negative ID, once for each case "
            "to write. A case not named stays out"
        )
    by_id = {case.id: case for case in found.cases}
    for case_id in named:
        case = by_id.get(case_id)
        if case is None:
            raise RefusedError(
                f"{case_id} is not a case the recordings of suite "
                f"{found.suite!r} hold: nothing was written"
            )
        if case.elected is not None:
            raise RefusedError(
                f"{case_id} is already in {found.cases_file.name}, labelled "
                f"{case.elected}: a second label on one input is refused, and "
                "the first stays (ADR 0023 §6)"
            )
        if not case.answers:
            raise RefusedError(
                f"{case_id} was recorded only under earlier setups: it can be "
                "seen, and not elected, because a yes or no about an answer the "
                "current setup did not give is not a label for it"
            )
    entries = [
        _entry(case, named[case.id], found) for case in found.cases if case.id in named
    ]
    _append(found.cases_file, entries)
    return tuple(entry["id"] for entry in entries)  # pyright: ignore[reportReturnType]


def _entry(case: ImportCase, label: Label, found: ImportListing) -> dict[str, object]:
    metadata: dict[str, object] = {"source": SOURCE}
    if found.setup is not None:
        metadata["setup_digest"] = found.setup
    if found.examined_through is not None:
        metadata["examined_through"] = found.examined_through
    return {
        "id": case.id,
        "vars": dict(case.vars),
        "label": label,
        "metadata": metadata,
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
    never counted as after the watermark."""
    _, path = capture_file(suite, module, root)
    marks = [mark for _label, mark in _draft(path).values() if mark is not None]
    store = FileResultStore(root)
    everything, _ = read_recordings(store, tenant)
    mine = [r for r in everything if r.suite == suite.name]
    if not marks:
        return None, len(mine)
    newest = max(marks)
    return sum(
        1 for r in mine if r.recorded_at is not None and r.recorded_at > newest
    ), len(mine)
