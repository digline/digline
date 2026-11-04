"""The recorder's switch and its status, for a front end. (ADR 0058 §10)

`switch_on` and `switch_off` write `.digline/<tenant>/recorder.toml`;
`recorder_status` reads it back with the tenant's recordings. The recorder
itself, in the application, reads the same file with the same function,
`digline.recorder.parse_switch`, so the file a command writes is never one the
recorder reads otherwise.

**The regime is said by the command, not inferred.** The recorder knows it is
in production when `wrap()` is given a tenant function; a command has no
function to look at, so `switch_on(..., production=True)` says it, and then
refuses the file the recorder would refuse, with the same sentences.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

from digline.recorder import SWITCH_KEYS, RecorderStartError, Switch, parse_switch
from digline.store.file_store import (
    COUNTS_FILENAME,
    RECORDER_FILENAME,
    RECORDINGS_DIRNAME,
    STORE_DIRNAME,
    FileResultStore,
)
from digline.wire.recorder import SuiteRecordings, TenantRecorder

__all__ = ["recorder_status", "switch_off", "switch_on"]


def switch_on(
    root: Path,
    tenant: str,
    *,
    production: bool,
    sample: float | None = None,
    redact: str | None = None,
    ceiling: int | None = None,
    interval: float | None = None,
) -> Path:
    """Write `on = true` for `tenant`, with the values given over the ones the
    file already declared. Refused, before anything is written, where the
    recorder would refuse the file: in production without `redact`, `sample`
    or `ceiling`."""
    store = FileResultStore(root)
    path = store.recorder_path(tenant)
    values = _declared(path)
    values["on"] = True
    if production:
        # Said in the file, so the file is held to production wherever it is
        # read, and the status can say so. (ADR 0058 §10)
        values["production"] = True
    for key, value in (
        ("sample", sample),
        ("redact", redact),
        ("ceiling", ceiling),
        ("interval", interval),
    ):
        if value is not None:
            values[key] = value
    text = _toml(values)
    parse_switch(text, where=str(path), production=production)
    store.ensure_layout(tenant)
    _write(path, text)
    return path


def switch_off(root: Path, tenant: str) -> Path:
    """Write `on = false` for `tenant`, and keep every other value the file
    declared. A tenant without a file gets one that says off."""
    store = FileResultStore(root)
    path = store.recorder_path(tenant)
    values = _declared(path)
    values["on"] = False
    store.ensure_layout(tenant)
    _write(path, _toml(values))
    return path


def _declared(path: Path) -> dict[str, object]:
    """What the file at `path` declares, read as development reads it; empty
    where there is no file. An invalid file is refused rather than written
    over: whoever runs the command sees what is wrong with it, and an invalid
    file already keeps the recorder from recording."""
    if not path.exists():
        return {}
    switch = parse_switch(_text(path), where=str(path), production=False)
    return {key: getattr(switch, key) for key in SWITCH_KEYS if key in switch.declared}


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise RecorderStartError(f"{path} cannot be read as text") from None


def _toml(values: dict[str, object]) -> str:
    """The file, one key a line, in `SWITCH_KEYS`' order. Booleans, numbers
    and the one string `redact` takes are all it holds, so no TOML library is
    needed to write it."""
    lines: list[str] = []
    for key in SWITCH_KEYS:
        if key not in values:
            continue
        value = values[key]
        if isinstance(value, bool):
            written = "true" if value else "false"
        elif isinstance(value, str):
            written = json.dumps(value)
        else:
            written = repr(value)
        lines.append(f"{key} = {written}")
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    """Whole or not at all: written beside it and renamed over it, so the
    recorder, which may read it at any moment, never reads half a file."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def recorder_status(
    root: Path,
    tenant: str | None = None,
    imports: Mapping[str, tuple[int | None, int]] | None = None,
) -> tuple[TenantRecorder, ...]:
    """Each tenant's switch and recordings: `tenant` alone, or every tenant
    under `.digline/` with a switch file or a `recordings/` directory.

    `imports` is, per suite name, what `digline.host.importing.imported_since`
    read from that suite's draft; a suite not in it says *not read*."""
    store = FileResultStore(root)
    if tenant is not None:
        names = [tenant]
    else:
        base = root / STORE_DIRNAME
        names = sorted(
            entry.name
            for entry in (base.iterdir() if base.is_dir() else ())
            if entry.is_dir()
            and (
                (entry / RECORDER_FILENAME).is_file()
                or (entry / RECORDINGS_DIRNAME).is_dir()
            )
        )
    return tuple(_tenant(store, name, imports or {}) for name in names)


def _not_recorded(
    directory: Path, key: str = "not_recorded"
) -> dict[str, dict[str, int]]:
    """Per suite and reason, what every process said it did not record, or
    with `key="noted"` what it recorded with something said beside it: the
    sum of the counts file each process keeps in its subdirectory. A file
    that does not read as counts is left out."""
    found: dict[str, dict[str, int]] = {}
    for path in sorted(directory.glob(f"*/{COUNTS_FILENAME}")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            suites = document["suites"]
            for name, counts in suites.items():
                reasons = found.setdefault(str(name), {})
                for reason, n in counts.get(key, {}).items():
                    if type(n) is int:
                        reasons[str(reason)] = reasons.get(str(reason), 0) + n
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return found


def _suite(
    name: str,
    counts: list[int],
    imported: tuple[int | None, int] | None,
    missed: Mapping[str, int],
    noted: Mapping[str, int],
) -> SuiteRecordings:
    since, total = imported if imported is not None else (None, 0)
    return SuiteRecordings(
        suite=name,
        calls=counts[0],
        episodes=counts[1],
        orphans=counts[2],
        inside_episodes=counts[3],
        interrupted=counts[4],
        not_recorded=dict(sorted(missed.items())),
        noted=dict(sorted(noted.items())),
        imported=None if imported is None else since is not None,
        since_last_import=None
        if imported is None
        else total
        if since is None
        else since,
    )


def _tenant(
    store: FileResultStore,
    tenant: str,
    imports: Mapping[str, tuple[int | None, int]],
) -> TenantRecorder:
    path = store.recorder_path(tenant)
    switch: Switch | None = None
    refusal: str | None = None
    production_refusal: str | None = None
    if path.exists():
        try:
            text = _text(path)
            switch = parse_switch(text, where=str(path), production=False)
            try:
                parse_switch(text, where=str(path), production=True)
            except RecorderStartError as exc:
                production_refusal = str(exc)
        except RecorderStartError as exc:
            refusal = str(exc)
    directory = store.recordings_dir(tenant)
    # calls, episodes, orphans, calls inside an episode, interrupted episodes
    suites: dict[str, list[int]] = {}
    unreadable = 0
    size = 0
    for item in sorted(directory.glob("*/*.json")):
        if item.name.startswith("."):
            continue
        with contextlib.suppress(OSError):
            size += item.stat().st_size
        try:
            recording = store.read_recording(item)
        except (ValueError, OSError):
            unreadable += 1
            continue
        counts = suites.setdefault(recording.suite, [0, 0, 0, 0, 0])
        if recording.steps is None:
            counts[0] += 1
            counts[2] += recording.orphan
            # An orphan that carries an id ended after its episode closed: it
            # is not part of that episode's case.
            counts[3] += recording.episode is not None and not recording.orphan
        else:
            counts[1] += 1
            counts[4] += recording.interrupted
    missed = _not_recorded(directory)
    noted = _not_recorded(directory, "noted")
    for name in (*missed, *noted):
        suites.setdefault(name, [0, 0, 0, 0, 0])
    return TenantRecorder(
        tenant=tenant,
        switch_path=str(path),
        switch="absent"
        if not path.exists()
        else "invalid"
        if switch is None
        else "valid",
        on=switch is not None and switch.on,
        sample=None if switch is None else switch.sample,
        redact=None if switch is None else switch.redact,
        ceiling=None if switch is None else switch.ceiling,
        interval=None if switch is None else switch.interval,
        declared=()
        if switch is None
        else tuple(k for k in SWITCH_KEYS if k in switch.declared),
        refusal=refusal,
        production_refusal=production_refusal,
        recordings_path=str(directory),
        suites=tuple(
            _suite(
                name,
                counts,
                imports.get(name),
                missed.get(name, {}),
                noted.get(name, {}),
            )
            for name, counts in sorted(suites.items())
        ),
        unreadable=unreadable,
        size=size,
        stopped_at_ceiling=store.ceiling_marker_path(tenant).is_file(),
    )
