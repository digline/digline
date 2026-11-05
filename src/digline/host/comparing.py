"""A suite's recorded answers, by case and by setup: `digline record compare`.
(ADR 0058; the piece D4 of 1.1)

**It shows, and it judges nothing.** For each case, the recordings with the
same input, `capture_id(vars)` as the import has it (ADR 0023 §6), the answers
under each setup in the order they were recorded, each with the digest of its
text and its date. Equal answers recorded one after the other under the same
setup are one line with how many times it came back, never hidden. No answer
is ranked, and no word says one is better.

**It reads what the import reads, and writes nothing.** The recordings are the
tenant's, read and split by the import's own functions, so a case here is a
case there, and what is not a case is counted the same way. It moves no
`examined_through`: the import's watermark is what a person was shown at an
import, and this is not one.

**Two setups side by side.** `setups` names two setups by the first eight
characters of their digest, and only those two are shown, each case's answers
under one beside its answers under the other. `show_setup` then says which keys
of the two setups differ, each value shown by its first line and its length,
never a prompt whole.

**One structure.** What this returns is what the CLI lays out and what the
local page reads. It is built here once, so the two say the same thing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from digline.core.capture import capture_id
from digline.core.recording import Recording
from digline.core.refused import RefusedError
from digline.host.importing import (
    read_recordings,
    refuse_another_tenant,
    split_recordings,
)
from digline.run.suite import Suite
from digline.store.file_store import FileResultStore
from digline.wire.record_compare import (
    SHORT,
    ComparedAnswer,
    ComparedCase,
    ComparedSetup,
    RecordComparison,
    SetupKey,
    SetupValue,
)

__all__ = ["record_compare"]

#: How much of a setup's value is shown: its first line, up to this many
#: characters, and then how many characters the whole value has.
PREVIEW_CHARS = 60


def record_compare(
    root: Path,
    suite: Suite,
    tenant: str,
    *,
    case: str | None = None,
    since: str | None = None,
    setups: Sequence[str] | None = None,
    show_setup: bool = False,
) -> RecordComparison:
    """The suite's recorded answers, by case and by setup. Writes nothing.

    `case` keeps one case, by the id the import gives it. `since` keeps the
    recordings made at or after an instant, written as `recorded_at` is, with
    its offset; a recording with no `recorded_at` is then left out, and
    counted. `setups` names two setups, and `show_setup`, only with them, adds
    the keys they differ on. Every refusal comes before anything is read into
    the result."""
    refuse_another_tenant(tenant, suite, what="compared for")
    if show_setup and setups is None:
        raise RefusedError(
            "--show-setup says how two setups differ, and needs the two: name "
            "them with --setup A B, by the eight characters the listing prints"
        )
    if setups is not None and len(setups) != 2:
        raise RefusedError(
            f"--setup names two setups, and was given {len(setups)}: "
            "--setup A B, by the eight characters the listing prints"
        )
    after = None if since is None else _since(since)

    everything, unreadable = read_recordings(FileResultStore(root), tenant)
    split = split_recordings(everything, suite.name)
    eligible = sorted(
        enumerate(split.eligible),
        key=lambda item: _when(item[1], item[0]),
    )
    known = _setups_in_order([recording for _, recording in eligible])
    pair = None if setups is None else _pair(setups, known)

    if case is not None and case not in {capture_id(r.case) for r in split.eligible}:
        raise RefusedError(
            f"{case} is not a case the recordings of suite {suite.name!r} hold: "
            "a case is named by the id `digline record compare` and `digline "
            "record import` print"
        )

    undated = 0
    kept: list[Recording] = []
    for _, recording in eligible:
        if case is not None and capture_id(recording.case) != case:
            continue
        if after is not None:
            instant = _instant(recording.recorded_at)
            if instant is None:
                undated += 1
                continue
            if instant < after:
                continue
        if pair is not None and recording.setup_digest not in pair:
            continue
        kept.append(recording)

    setup_keys: tuple[SetupKey, ...] | None = None
    same_keys: int | None = None
    if show_setup and pair is not None:
        setup_keys, same_keys = _differ(
            _setup_of(split.eligible, pair[0]), _setup_of(split.eligible, pair[1])
        )

    return RecordComparison(
        tenant=tenant,
        suite=suite.name,
        case=case,
        since=since,
        setups=known,
        pair=pair,
        setup_keys=setup_keys,
        same_keys=same_keys,
        cases=_cases(kept, pair),
        recordings=len(split.recordings),
        orphans=split.orphans,
        detached=split.detached,
        interrupted=split.interrupted,
        oversize=split.oversize,
        unreadable=unreadable,
        undated=undated,
    )


def _instant(text: str | None) -> datetime | None:
    """`recorded_at` as an instant, or `None` where there is none to read."""
    if text is None:
        return None
    try:
        instant = datetime.fromisoformat(text)
    except ValueError:
        return None
    return instant if instant.tzinfo is not None else None


def _since(text: str) -> datetime:
    """`--since`, in the form `recorded_at` has: an instant with its offset.
    Compared as an instant, never as text, so two offsets compare right."""
    instant = _instant(text)
    if instant is None:
        raise RefusedError(
            f"--since {text}: not an instant with its offset. Write it as the "
            "recordings write recorded_at, 2026-11-03T08:00:00+00:00"
        )
    return instant


def _when(recording: Recording, index: int) -> tuple[int, float, int]:
    """The order of the view: by `recorded_at` as an instant, and the files'
    order among equal ones and after them for a recording with none."""
    instant = _instant(recording.recorded_at)
    if instant is None:
        return (1, 0.0, index)
    return (0, instant.timestamp(), index)


def _setups_in_order(recordings: Sequence[Recording]) -> tuple[str, ...]:
    """Every setup, in the order of its first recording."""
    return tuple(dict.fromkeys(r.setup_digest for r in recordings))


def _pair(given: Sequence[str], known: Sequence[str]) -> tuple[str, str]:
    """The two setups `--setup` names, each resolved to the one digest it
    begins, or a refusal that says which setups there are."""
    shown = ", ".join(setup[:SHORT] for setup in known) or "none"
    found: list[str] = []
    for prefix in given:
        if len(prefix) < SHORT:
            raise RefusedError(
                f"--setup {prefix}: a setup is named by at least the "
                f"{SHORT} characters the listing prints. The suite's: {shown}"
            )
        matches = [setup for setup in known if setup.startswith(prefix)]
        if not matches:
            raise RefusedError(
                f"--setup {prefix}: no answer of the suite was recorded under "
                f"a setup with that digest. The suite's: {shown}"
            )
        if len(matches) > 1:
            raise RefusedError(
                f"--setup {prefix}: {len(matches)} setups begin with it; give "
                "more of the digest"
            )
        found.append(matches[0])
    if found[0] == found[1]:
        raise RefusedError(
            f"--setup names {found[0][:SHORT]} twice: two setups are compared, "
            "and a setup beside itself is one"
        )
    return found[0], found[1]


def _cases(
    recordings: Sequence[Recording], pair: tuple[str, str] | None
) -> tuple[ComparedCase, ...]:
    """The recordings, already in the view's order, by case and by setup. With
    a pair, every case shows both setups, the one with nothing recorded
    included, so the two stand side by side."""
    by_case: dict[str, list[Recording]] = {}
    for recording in recordings:
        by_case.setdefault(capture_id(recording.case), []).append(recording)
    cases: list[ComparedCase] = []
    for case_id, mine in by_case.items():
        by_setup: dict[str, list[Recording]] = {}
        for setup in pair or ():
            by_setup[setup] = []
        for recording in mine:
            by_setup.setdefault(recording.setup_digest, []).append(recording)
        first = mine[0]
        cases.append(
            ComparedCase(
                id=case_id,
                vars=first.case,
                kind="episode" if first.is_episode else "call",
                setups=tuple(
                    ComparedSetup(setup=setup, answers=_runs(answers))
                    for setup, answers in by_setup.items()
                ),
            )
        )
    return tuple(cases)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:SHORT]


def _runs(recordings: Sequence[Recording]) -> tuple[ComparedAnswer, ...]:
    """Equal answers recorded one after the other: one line, and how many."""
    runs: list[ComparedAnswer] = []
    for recording in recordings:
        text = recording.response.output or ""
        digest = _digest(text)
        if runs and runs[-1].digest == digest and runs[-1].text == text:
            last = runs[-1]
            runs[-1] = ComparedAnswer(
                digest=digest,
                text=text,
                first_at=last.first_at,
                last_at=recording.recorded_at,
                times=last.times + 1,
            )
            continue
        runs.append(
            ComparedAnswer(
                digest=digest,
                text=text,
                first_at=recording.recorded_at,
                last_at=recording.recorded_at,
                times=1,
            )
        )
    return tuple(runs)


def _setup_of(recordings: Sequence[Recording], digest: str) -> Mapping[str, object]:
    """The setup a digest names, read from the first recording made under it."""
    return next(r.setup for r in recordings if r.setup_digest == digest)


def _value(value: object) -> SetupValue:
    """A value as far as it is shown: its first line, clipped, and its length.
    A list of messages is shown by its first message's text and how many there
    are; any other value that is not text, as JSON."""
    messages = _messages(value)
    if messages is not None:
        whole = _text_of(messages[0])
        line = whole.split("\n", 1)[0]
        preview = line[:PREVIEW_CHARS]
        return SetupValue(
            preview=preview,
            chars=len(whole),
            clipped=preview != whole,
            messages=len(messages),
        )
    whole = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False)
    )
    line = whole.split("\n", 1)[0]
    preview = line[:PREVIEW_CHARS]
    return SetupValue(preview=preview, chars=len(whole), clipped=preview != whole)


def _messages(value: object) -> list[Mapping[str, object]] | None:
    """`value` as a list of messages, each a mapping with a `content`, or
    `None` where it is not one."""
    if not isinstance(value, list) or not value:
        return None
    items = cast(list[object], value)
    if not all(isinstance(m, Mapping) and "content" in m for m in items):
        return None
    return [cast(Mapping[str, object], m) for m in items]


def _text_of(message: Mapping[str, object]) -> str:
    """A message's text: its `content` where that is text, its text blocks
    joined where it is a list of them, and JSON otherwise."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = cast(list[object], content)
        texts = [
            str(cast(Mapping[str, object], b)["text"])
            for b in blocks
            if isinstance(b, Mapping) and "text" in b
        ]
        if texts:
            return "".join(texts)
    return json.dumps(content, sort_keys=True, ensure_ascii=False)


def _differ(
    a: Mapping[str, object], b: Mapping[str, object]
) -> tuple[tuple[SetupKey, ...], int]:
    """The keys two setups do not share or hold different values under, in
    the order of the keys' names, and how many they share equal. Keys of the
    setup's top level: a nested value that differs is one key that differs."""
    differ: list[SetupKey] = []
    same = 0
    for key in sorted(set(a) | set(b)):
        if key in a and key in b and a[key] == b[key]:
            same += 1
            continue
        differ.append(
            SetupKey(
                key=key,
                a=_value(a[key]) if key in a else None,
                b=_value(b[key]) if key in b else None,
            )
        )
    return tuple(differ), same
