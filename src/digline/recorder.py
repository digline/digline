"""The recorder: a provider's client that records the calls an application
makes through it, so they can become a suite's cases. (ADR 0058)

    client = digline.recorder.wrap(anthropic.Anthropic(), app="support", tenant="acme")
    client.messages.create(model=..., messages=..., suite="triage")

`suite=` on the call names the suite the call belongs to, the same name as
that suite's `Suite(name=...)`. A call that names none is recorded under
`_unassigned`, with the function it was made from.

**One call, recorded or let through**, and **an episode**: a context around
one turn of an agent, whose calls are attached to it.

    with digline.recorder.episode(client, suite="support-agent", case={...}) as ep:
        ...  # calls through wrapped clients, tools run by the application
        ep.output(result)

A synchronous, non-streaming client. Streaming and asynchronous clients are
not recorded yet. The recordings become cases with `digline record import`,
and `docs/record.md` walks through the whole of it.

**How a provider is found, without importing it.** A plugin declares, under the
entry point group `digline.recording_maps`, a name that says which client it
maps and which method of it is the call: `anthropic.Anthropic:messages.create`
is the client class `Anthropic` of the package `anthropic`, and its
`messages.create`. The name is read without importing anything; the map the
entry point loads is imported only when a call is recorded. A client no plugin
names is refused when it is wrapped, by name, never at the call.

**The rule that is not negotiated: the application's call never fails because
of the recorder.** Whatever goes wrong while recording — a value JSON cannot
carry, the writer's `OSError`, a reply the map does not recognise, the tenant
function raising — the call's own result is returned, and a *not recorded* is
counted with its reason. A call with `stream=True` passes and counts *not
recorded: streaming*. An exception of the provider's SDK propagates as it is,
and nothing is recorded.

**Two regimes, read from `tenant=`** (§4, §10). A name is **development**: one
tenant, fixed. A function is **production**: the tenant is resolved at every
call, and each tenant's recordings are filed under its own directory.

**The switch is `.digline/<tenant>/recorder.toml`**, written by `digline record
on` and `digline record off`. Its keys are `on`, `sample`, `redact`,
`ceiling` and `interval`, and any other key is refused by name:

- `sample`, above 0 and at most 1, is the share of calls recorded, drawn per
  call; an episode is drawn once, when the outermost one is entered, and its
  children follow it, in or out together;
- `redact` is `"none"`, the one this release implements; any other value is
  refused as not implemented;
- `ceiling` is the size in bytes the tenant's recordings may reach. At the
  ceiling the recorder stops recording for that tenant, counts `ceiling`, and
  writes a marker beside the recordings that `digline record status` reads
  from any process. It does not rotate and does not delete;
- `interval` is how often, in seconds, the file is looked at again.

**The file wins over the environment where it exists.** In development,
without a file, `DIGLINE_RECORD=1` switches recording on with the defaults
below. In production the variable may only be off: on, it would declare no
redaction and no sampling, and it is refused when the client is wrapped.

**In production, three refusals, loud, when the client is wrapped** (§10): a
file that switches a tenant on without `redact`, without `sample`, or without
`ceiling` and a writable directory to put the recordings in. In development
the three have defaults: `sample` 1, `redact` `"none"`, `ceiling` 100 MiB.
A file that says `production = true`, which `digline record on --production`
writes, is held to the three wherever it is read.

**An invalid switch file stops an application only in production.** In
development the recorder says why on standard error, once, stays off for
that tenant, and counts `config invalid`: a typo in a local, ignored file is
not a reason for the application not to start.

**Read again at an interval, without a restart.** Each call compares a
monotonic clock with the time the next look is due, which is one comparison;
when it is due the file is looked at with `stat` and read again if it changed.
Production looks for every tenant's file with one listing of `.digline/` at
each look, never at a call. A file that turns invalid while the application
runs switches its tenant off and counts `config invalid`; it never fails the
application. The size against the ceiling is the bytes this process wrote,
plus a listing of the tenant's recordings at each look, which counts what other
processes wrote.

The clock is `time.monotonic`, read here and not through `digline.host`: this
module sits at the host's level, and a monotonic clock is a duration, which
says how long and never what time it is.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from importlib.metadata import entry_points
from pathlib import Path
from time import monotonic, perf_counter
from typing import TYPE_CHECKING, Any, Protocol, cast

# Where this module sits: at the level of `digline.host`, the layer that may
# read files, the environment and the clock, and nothing imports it. Not
# *inside* `digline.host`, because that package's `__init__` imports the whole
# host, and the host imports the core: switched off, the wrapper must not
# (ADR 0058 §10). So this module imports the standard library alone at the
# top, and everything of digline's lazily, at the first call it records.
if TYPE_CHECKING:
    from types import TracebackType

    from digline.core.recording import RecordedStep
    from digline.core.run import RecordedToolCall
    from digline.store.file_store import RecordingWriter
    from digline.targets import Completion

__all__ = [
    "DEFAULT_CEILING",
    "DEFAULT_INTERVAL",
    "DEFAULT_SAMPLE",
    "ENVIRONMENT_VARIABLE",
    "SWITCH_KEYS",
    "Switch",
    "MAP_GROUP",
    "UNASSIGNED",
    "RecordedClient",
    "RecorderStartError",
    "Episode",
    "RecordingMap",
    "attach",
    "episode",
    "parse_switch",
    "wrap",
]

#: The variable that switches recording on for this process, in development
#: and where no switch file exists, read when a client is wrapped.
ENVIRONMENT_VARIABLE = "DIGLINE_RECORD"

#: The keys a switch file may hold, and nothing else. (ADR 0058 §10)
#: `production` declares the file is for production, and holds it to the
#: three refusals in any regime.
SWITCH_KEYS = ("on", "sample", "redact", "ceiling", "interval", "production")

#: What a development switch leaves out, it gets: every call, no redaction,
#: 100 MiB. Production declares the first three, or is refused.
DEFAULT_SAMPLE = 1.0
DEFAULT_CEILING = 100 * 1024 * 1024
#: Seconds between two looks at the switch file and the recordings' size.
DEFAULT_INTERVAL = 5.0

#: The layout's names, as `digline.store.file_store` has them; restated here
#: because this module does not import the store until it records, and a test
#: holds the two equal.
_STORE = ".digline"
_SWITCH_FILE = "recorder.toml"
_RECORDINGS = "recordings"
_CEILING_MARKER = "ceiling-reached.json"

#: The clock the interval is read on. Looked up through the module at each
#: call, so a test can put a clock of its own here.
_clock: Callable[[], float] = monotonic

#: The draw a sample is decided by, in [0, 1). `None` is `random.random`,
#: imported at the first draw. A test puts a seeded generator here.
_draw: Callable[[], float] | None = None

#: The entry point group a plugin declares its map under.
MAP_GROUP = "digline.recording_maps"

#: The suite a call that names none is recorded in. It enters no gate until a
#: person assigns it. (ADR 0058 §2)
UNASSIGNED = "_unassigned"

#: digline's two keywords, taken out of every intercepted call before the SDK
#: sees it, recording or not.
_SUITE = "suite"
_VARS = "digline_vars"


class RecorderStartError(ValueError):
    """Raised when a client cannot be wrapped: a client no plugin maps, an
    empty `app`, or a switch value that is neither on nor off.

    Raised by `wrap`, when the application starts, and never by a call.
    Defined here and not as a `RefusedError`, because importing that class
    would import the core, which this module must not do while off.
    """


#: The id of the episode the current context is inside, or `None`. A context
#: variable reaches an asyncio task and `asyncio.to_thread`, and does not reach
#: a `threading.Thread` or a `ThreadPoolExecutor` worker: there `attach` carries
#: it, by hand (ADR 0058 §5).
_CURRENT: ContextVar[str | None] = ContextVar("digline_episode", default=None)

#: The episodes open in this process, by id. A call made inside one, through any
#: wrapped client, adds its step to it.
_OPEN: dict[str, _Collector] = {}
_OPEN_LOCK = threading.Lock()


class Switch:
    """One tenant's switch, as read from its file or from the environment.

    `declared` names the keys the file wrote, so a reader can tell a value
    written from a default.
    """

    __slots__ = (
        "ceiling",
        "declared",
        "interval",
        "on",
        "production",
        "redact",
        "sample",
    )

    def __init__(
        self,
        *,
        on: bool,
        sample: float = DEFAULT_SAMPLE,
        redact: str = "none",
        ceiling: int = DEFAULT_CEILING,
        interval: float = DEFAULT_INTERVAL,
        production: bool = False,
        declared: frozenset[str] = frozenset(),
    ) -> None:
        self.on = on
        self.production = production
        self.sample = sample
        self.redact = redact
        self.ceiling = ceiling
        self.interval = interval
        self.declared = declared

    def __repr__(self) -> str:
        return (
            f"Switch(on={self.on}, sample={self.sample}, redact={self.redact!r}, "
            f"ceiling={self.ceiling}, interval={self.interval})"
        )


def _number(value: object) -> bool:
    # `True` is an `int` in Python, and `sample = true` is not a share.
    return type(value) in (int, float)


def parse_switch(text: str, *, where: str, production: bool) -> Switch:
    """A switch file's text as a `Switch`, or a refusal naming `where`.

    Unknown keys are refused by name, a `redact` other than `"none"` is
    refused as not implemented, and in production a file that switches
    recording on must declare `redact`, `sample` and `ceiling`: the three
    refusals of ADR 0058 §10, all the missing ones in one sentence.
    """
    import tomllib

    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        # Not the parser's sentence: it quotes the file. (ADR 0043)
        raise RecorderStartError(f"{where} is not valid TOML") from None
    unknown = sorted(set(raw) - set(SWITCH_KEYS))
    if unknown:
        raise RecorderStartError(
            f"{where} has keys the recorder does not read: {', '.join(unknown)}. "
            f"It reads {', '.join(SWITCH_KEYS)}"
        )
    on = raw.get("on")
    if type(on) is not bool:
        raise RecorderStartError(f"{where} must say on = true or on = false")
    sample = raw.get("sample")
    if sample is not None and not (_number(sample) and 0 < sample <= 1):
        raise RecorderStartError(
            f"{where}: sample must be a number above 0 and at most 1"
        )
    redact = raw.get("redact")
    if redact is not None and redact != "none":
        raise RecorderStartError(
            f"{where}: redact = {str(redact)[:40]!r} is not implemented. This "
            'release implements redact = "none" alone (ADR 0058 §4)'
        )
    ceiling = raw.get("ceiling")
    if ceiling is not None and (type(ceiling) is not int or ceiling < 1):
        raise RecorderStartError(
            f"{where}: ceiling must be a whole number of bytes, at least 1"
        )
    interval = raw.get("interval")
    if interval is not None and not (_number(interval) and interval > 0):
        raise RecorderStartError(
            f"{where}: interval must be a number of seconds above 0"
        )
    declared_production = raw.get("production", False)
    if type(declared_production) is not bool:
        raise RecorderStartError(f"{where}: production must be true or false")
    production = production or declared_production
    if production and on:
        missing: list[str] = []
        if redact is None:
            missing.append(
                'no declared redaction (write redact = "none", the one this '
                "release implements)"
            )
        if sample is None:
            missing.append(
                "no declared sampling (write sample = p, above 0 and at most 1)"
            )
        if ceiling is None:
            missing.append(
                "no ceiling on the size of its recordings (write ceiling = N, in bytes)"
            )
        if missing:
            raise RecorderStartError(
                f"{where} switches recording on in production with "
                + "; ".join(missing)
                + ". In production all three are declared (ADR 0058 §10)"
            )
    return Switch(
        on=on,
        sample=DEFAULT_SAMPLE if sample is None else float(sample),
        redact="none",
        ceiling=DEFAULT_CEILING if ceiling is None else ceiling,
        interval=DEFAULT_INTERVAL if interval is None else float(interval),
        production=declared_production,
        declared=frozenset(raw),
    )


class RecordingMap(Protocol):
    """What a plugin's map provides, loaded only to record a call.

    `split` divides the request into the case and the setup (ADR 0058 §3): the
    messages are the case, everything else the call decides with is the setup,
    and what the plugin names as transport or as a per-request identifier is
    neither. `completion` reads the reply with the code the plugin's target
    already uses.
    """

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]: ...

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion: ...


class _State:
    """What every intercepted call of one wrapped client shares."""

    def __init__(
        self,
        *,
        app: str,
        tenant: str | Callable[[], str],
        root: Path,
        entry: Any,
    ) -> None:
        self.app = app
        self.tenant = tenant
        self.root = root
        self.entry = entry
        self.lock = threading.Lock()
        self.recorded = 0
        self.not_recorded: dict[str, int] = {}
        self.orphan = 0
        self.map: RecordingMap | None = None
        self.writer: RecordingWriter | None = None
        #: Production: the tenant comes from a function, at every call.
        self.production = callable(tenant)
        #: Each tenant's switch, replaced whole at each look, never edited.
        self.switches: dict[str, Switch] = {}
        #: Whether any tenant records: the one test an off client makes.
        self.any_on = False
        #: Each switch file's `(mtime_ns, size)` at the last look.
        self.stamps: dict[str, tuple[int, int]] = {}
        self.interval = DEFAULT_INTERVAL
        #: When the next look is due, on `_clock`.
        self.next_look = 0.0
        self.look_lock = threading.Lock()
        #: Each tenant's recordings, in bytes: listed at each look, and grown
        #: by what this process writes in between.
        self.sizes: dict[str, int] = {}
        #: The tenants this process stopped recording at their ceiling.
        self.stopped: set[str] = set()
        #: The commit an episode's setup is read with, cached until the next
        #: look: reading it is two `git` processes.
        self.commit: tuple[str | None] | None = None
        #: Per tenant and suite, what this process recorded and did not, as
        #: its counts file holds it; the tenants whose file exists.
        self.tallies: dict[str, dict[str, dict[str, Any]]] = {}
        self.tallied: set[str] = set()
        #: The tenants counted since their file was last written.
        self.dirty: set[str] = set()
        self.tally_lock = threading.Lock()

    def count(self, reason: str | None) -> None:
        with self.lock:
            if reason is None:
                self.recorded += 1
            else:
                self.not_recorded[reason] = self.not_recorded.get(reason, 0) + 1

    def count_orphan(self) -> None:
        with self.lock:
            self.orphan += 1


class _Seen:
    """What one recorded call adds to the episode it was made in."""

    __slots__ = ("calls", "digest", "finish", "text")

    def __init__(
        self,
        digest: str,
        text: str,
        finish: str | None,
        calls: tuple[RecordedToolCall, ...] | None,
    ) -> None:
        self.digest = digest
        self.text = text
        self.finish = finish
        self.calls = calls


class _Collector:
    """An open episode's children, as they arrive, from any thread.

    `events` keeps them in the order they were seen: a call is one `_Seen`, a
    nested episode that closed is its own collector, whose steps are spliced in
    where it closed. `sampled_out` is the draw the outermost episode made, and
    every child follows it.
    """

    def __init__(self, *, sampled_out: bool = False) -> None:
        self.sampled_out = sampled_out
        self.lock = threading.Lock()
        self.events: list[_Seen | _Collector] = []
        self.unrecorded = 0
        self.digest: str | None = None

    def add(self, event: _Seen | _Collector | None) -> None:
        with self.lock:
            if event is None:
                self.unrecorded += 1
            else:
                self.events.append(event)

    def calls(self) -> list[_Seen]:
        """Every call seen, a nested episode's in place, in order."""
        with self.lock:
            events = list(self.events)
        found: list[_Seen] = []
        for event in events:
            found.extend(event.calls() if isinstance(event, _Collector) else [event])
        return found

    def children_unrecorded(self) -> int:
        with self.lock:
            events = list(self.events)
            own = self.unrecorded
        return own + sum(
            event.children_unrecorded()
            for event in events
            if isinstance(event, _Collector)
        )

    def digests(self) -> set[str]:
        """The setup digests of the direct children: each call's, and each
        nested episode's own."""
        with self.lock:
            events = list(self.events)
        return {event.digest for event in events if event.digest is not None}


class RecordedClient:
    """The client, with one method intercepted and everything else its own.

    Attribute access goes to the client, except along the path to the
    intercepted method. `digline_counts` says how many calls were recorded and,
    per reason, how many were not; it lives in memory, on this object.
    """

    __slots__ = (
        "_digline_branches",
        "_digline_path",
        "_digline_state",
        "_digline_target",
    )
    _digline_branches: dict[str, RecordedClient]
    _digline_path: tuple[str, ...]
    _digline_state: _State
    _digline_target: Any

    def __init__(self, target: Any, path: tuple[str, ...], state: _State) -> None:
        object.__setattr__(self, "_digline_target", target)
        object.__setattr__(self, "_digline_path", path)
        object.__setattr__(self, "_digline_state", state)
        object.__setattr__(self, "_digline_branches", {})

    def __getattr__(self, name: str) -> Any:
        path: tuple[str, ...] = self._digline_path
        value = getattr(self._digline_target, name)
        if name != path[0]:
            return value
        if len(path) == 1:
            return _intercepted(value, self._digline_state)
        branches: dict[str, RecordedClient] = self._digline_branches
        branch = branches.get(name)
        if branch is None or branch._digline_target is not value:
            branch = RecordedClient(value, path[1:], self._digline_state)
            branches[name] = branch
        return branch

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._digline_target, name, value)

    def __repr__(self) -> str:
        return f"<recorded {self._digline_target!r}>"

    @property
    def digline_counts(self) -> Mapping[str, object]:
        """`{"recorded": n, "not_recorded": {reason: n, ...}, "orphan": n}`,
        as of now. `recorded` counts the calls, and the episodes opened on
        this client. `orphan` counts the
        calls recorded with no episode while one was open in this process: a
        child whose thread was not attached, or a call that belongs to none.
        The recorder cannot tell which, and attaches neither (ADR 0058 §5)."""
        state: _State = self._digline_state
        with state.lock:
            return {
                "recorded": state.recorded,
                "not_recorded": dict(state.not_recorded),
                "orphan": state.orphan,
            }


def _intercepted(method: Callable[..., Any], state: _State) -> Callable[..., Any]:
    def call(*args: Any, **kwargs: Any) -> Any:
        suite = kwargs.pop(_SUITE, None)
        variables = kwargs.pop(_VARS, None)
        if _clock() >= state.next_look:
            _look(state)
        if not state.any_on:
            return method(*args, **kwargs)
        inside = _CURRENT.get()
        known = None if state.production else cast(str, state.tenant)
        if kwargs.get("stream"):
            _joined(state, inside, "streaming", None)
            _tally(state, known, suite, "streaming")
            return method(*args, **kwargs)
        if args:
            _joined(state, inside, "positional arguments", None)
            _tally(state, known, suite, "positional arguments")
            return method(*args, **kwargs)
        site = _call_site() if suite is None else None
        started = perf_counter()
        reply = method(**kwargs)
        elapsed_ms = (perf_counter() - started) * 1000.0
        _LAST.tenant = known
        reason, seen = _record(
            state, kwargs, reply, elapsed_ms, suite, variables, site, inside
        )
        _joined(state, inside, reason, seen)
        _tally(state, _LAST.tenant, suite, reason)
        return reply

    return call


def _joined(
    state: _State, inside: str | None, reason: str | None, seen: _Seen | None
) -> None:
    """Count the call, and give it to the episode it was made in.

    A call made in no episode while one is open in this process is counted an
    orphan, its file says `"orphan": true`, and it is attached to nothing:
    which episode it belongs to, if any, is
    not something the recorder can know, and it never guesses from timing
    (ADR 0058 §5). A call whose episode is not open here — attached by id from
    another process, or after its episode closed — carries the id, and the
    import joins it.
    """
    state.count(reason)
    if inside is None:
        if reason is None and _OPEN:
            state.count_orphan()
        return
    collector = _OPEN.get(inside)
    if collector is not None:
        collector.add(seen)


#: The tenant the last recording on this thread resolved, so that its outcome
#: is tallied under the tenant it was for. Per thread, because two threads
#: record at once.
_LAST = threading.local()


def _tally(
    state: _State, tenant: str | None, suite: object, reason: str | None
) -> None:
    """Count one outcome under its tenant and suite, in memory, for this
    process's counts file, which `digline record status` reads from any
    process.

    **Never a write per outcome.** The file is written at the first
    recording of the tenant in this process, so that it exists; at each look
    at the switch, the interval's tick; and when the process exits. Between
    two of those the counts are in memory, and a crash loses them since the
    last tick: they are counts, and a count a little short is accepted where
    a write per call is not.

    Not tallied: an outcome whose tenant is not known (a tenant function that
    raised, or a call refused before its tenant was asked, in production),
    and *off for this tenant*, which would make a directory for a tenant that
    records nothing. Never raises.
    """
    if tenant is None or reason == "off for this tenant":
        return
    name = suite if isinstance(suite, str) and suite else UNASSIGNED
    with state.tally_lock:
        if not state.tallies:
            import atexit

            atexit.register(_flush, state)
        suites = state.tallies.setdefault(tenant, {})
        bucket = suites.setdefault(name, {"recorded": 0, "not_recorded": {}})
        state.dirty.add(tenant)
        if reason is None:
            bucket["recorded"] += 1
            first = tenant not in state.tallied
        else:
            bucket["not_recorded"][reason] = bucket["not_recorded"].get(reason, 0) + 1
            first = False
    if first:
        _flush(state, tenant)


def _flush(state: _State, only: str | None = None) -> None:
    """Write the counts of every tenant counted since the last write, or of
    `only`. At the first recording, at each tick, and at exit. Never raises."""
    with state.tally_lock:
        tenants = [only] if only is not None else sorted(state.dirty)
        for tenant in tenants:
            suites = state.tallies.get(tenant)
            if suites is None:
                continue
            snapshot = {
                suite_name: {
                    "recorded": counts["recorded"],
                    "not_recorded": dict(counts["not_recorded"]),
                }
                for suite_name, counts in suites.items()
            }
            with contextlib.suppress(Exception):
                _write_counts(state, tenant, snapshot)
                state.tallied.add(tenant)
                state.dirty.discard(tenant)


def _write_counts(state: _State, tenant: str, suites: dict[str, Any]) -> None:
    import json

    from digline.store.file_store import (
        COUNTS_FILENAME,
        FileResultStore,
        RecordingWriter,
    )

    with state.lock:
        if state.writer is None:
            state.writer = RecordingWriter(FileResultStore(state.root))
        writer = state.writer
    place = writer.place(tenant)
    path = place / COUNTS_FILENAME
    temporary = place / f"{COUNTS_FILENAME}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps({"pid": os.getpid(), "suites": suites}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _call_site() -> str | None:
    """`module:function` of the frame that made the call, read only when a
    call that names no suite is recorded. Two frames up: past `call`, past
    this function."""
    import inspect

    frame = inspect.currentframe()
    caller = None if frame is None or frame.f_back is None else frame.f_back.f_back
    if caller is None:
        return None
    module = caller.f_globals.get("__name__")
    return f"{module}:{caller.f_code.co_qualname}"


def _record(
    state: _State,
    request: Mapping[str, Any],
    reply: Any,
    elapsed_ms: float,
    suite: object,
    variables: object,
    site: str | None,
    inside: str | None,
) -> tuple[str | None, _Seen | None]:
    """Record one call, or say why not. `None` is *recorded*.

    Nothing here may raise: each stage is its own reason, and digline's own
    imports failing is `unexpected: <type>`. The reasons name a stage and
    never quote a value, because a value is the application's payload.

    The second value is what the call adds to its episode, read once the
    reply is: a call the writer then failed to file still happened, and its
    step stays in the episode's trajectory.

    Before anything is read: the tenant, its switch, the draw — skipped inside
    an episode, which drew for its children — and the ceiling.
    """
    try:
        from digline.core.recording import Recording, setup_digest_of
        from digline.core.run import record_trajectory
        from digline.run.driver import Response, recorded
        from digline.store.file_store import FileResultStore, RecordingWriter
    except Exception as exc:  # noqa: BLE001 — the rule of this module
        return f"unexpected: {type(exc).__name__}", None

    stage = "tenant"
    try:
        tenant = _tenant_of(state)
        _LAST.tenant = tenant
        if tenant is None:
            return stage, None
        switch = state.switches.get(tenant)
        if switch is None or not switch.on:
            return "off for this tenant", None
        collector = None if inside is None else _OPEN.get(inside)
        if collector is not None:
            if collector.sampled_out:
                return "sampled out", None
        elif not _sampled_in(switch):
            return "sampled out", None
        if _at_ceiling(state, tenant, switch):
            return "ceiling", None

        stage = "map"
        if state.map is None:
            state.map = state.entry.load()
        mapped: RecordingMap = state.map  # pyright: ignore[reportAssignmentType]
        case, setup = mapped.split(request)
        if variables is not None:
            if not isinstance(variables, Mapping):
                return "digline_vars is not a mapping", None
            case = {**case, "vars": dict(cast(Mapping[str, object], variables))}
        completion = mapped.completion(reply, request)
        metadata = completion.as_metadata()
        response = recorded(
            Response(
                output=completion.text,
                latency_ms=elapsed_ms,
                usage=completion.usage,
                metadata=metadata,
            )
        )

        stage = "not JSON"
        digest = setup_digest_of(setup)
        seen = _Seen(
            digest, completion.text, completion.finish, record_trajectory(metadata)
        )
    except Exception:  # noqa: BLE001 — the rule of this module
        return stage, None

    try:
        stage = "not JSON"
        recording = Recording(
            source_tenant=tenant,
            app=state.app,
            suite=suite if isinstance(suite, str) and suite else UNASSIGNED,
            case=case,
            setup=setup,
            setup_digest=digest,
            response=response,
            episode=inside,
            call_site=site,
            # Read as the file is written: whether an episode is open in this
            # process now is the one moment the definition can be known.
            orphan=inside is None and bool(_OPEN),
            recorded_at=_now(),
        )

        stage = "writer"
        _write(state, tenant, recording, RecordingWriter, FileResultStore)
    except Exception:  # noqa: BLE001 — the rule of this module
        return stage, seen
    return None, seen


def _write(state: _State, tenant: str, recording: Any, writer: Any, store: Any) -> None:
    with state.lock:
        if state.writer is None:
            state.writer = writer(store(state.root))
    path = cast("RecordingWriter", state.writer).write(recording)
    grown = path.stat().st_size
    with state.lock:
        state.sizes[tenant] = state.sizes.get(tenant, 0) + grown


def _tenant_of(state: _State) -> str | None:
    """The tenant of this call: the name given, or the function's answer.
    `None` where the function gave no name; its exception propagates to the
    caller's stage."""
    tenant = state.tenant() if callable(state.tenant) else state.tenant
    if not isinstance(tenant, str) or not tenant:  # pyright: ignore[reportUnnecessaryIsInstance]
        return None
    return tenant


def _sampled_in(switch: Switch) -> bool:
    """One draw against the switch's `sample`. At 1, no draw is made."""
    if switch.sample >= 1:
        return True
    draw = _draw
    if draw is None:
        import random

        draw = random.random
    return draw() < switch.sample


def _at_ceiling(state: _State, tenant: str, switch: Switch) -> bool:
    """Whether the tenant's recordings have reached its ceiling. The first
    time, the tenant is stopped and the marker is written; a recording already
    under way when the size crosses is kept, so the ceiling can be passed by
    one recording per process, never more."""
    with state.lock:
        if tenant in state.stopped:
            return True
        size = state.sizes.get(tenant, 0)
        if size < switch.ceiling:
            return False
        state.stopped.add(tenant)
    _mark_ceiling(state.root, tenant, switch.ceiling, size)
    return True


def _mark_ceiling(root: Path, tenant: str, ceiling: int, size: int) -> None:
    """The marker another process's `digline record status` reads. Written
    whole, by rename; a marker that cannot be written is not an error the
    application hears of."""
    import json

    directory = root / _STORE / tenant / _RECORDINGS
    marker = directory / _CEILING_MARKER
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".{_CEILING_MARKER}.{os.getpid()}"
        temporary.write_text(
            json.dumps({"ceiling": ceiling, "size": size}) + "\n", encoding="utf-8"
        )
        os.replace(temporary, marker)
    except OSError:
        pass


def _recordings_size(root: Path, tenant: str) -> int:
    """The bytes of a tenant's recordings, read from the disk: every file in
    every process's subdirectory. The marker and temporary files are not
    recordings and are not counted."""
    total = 0
    try:
        with os.scandir(root / _STORE / tenant / _RECORDINGS) as folders:
            for folder in folders:
                if not folder.is_dir(follow_symlinks=False):
                    continue
                with os.scandir(folder.path) as files:
                    for item in files:
                        if item.name.endswith(".json") and not item.name.startswith(
                            "."
                        ):
                            total += item.stat(follow_symlinks=False).st_size
    except OSError:
        return total
    return total


def _switch_files(state: _State) -> dict[str, Path]:
    """The switch files this client reads, by tenant: the one tenant's in
    development, every tenant's in production, found by listing `.digline/`."""
    store = state.root / _STORE
    if not state.production:
        return {cast(str, state.tenant): store / cast(str, state.tenant) / _SWITCH_FILE}
    found: dict[str, Path] = {}
    try:
        with os.scandir(store) as entries:
            for entry in entries:
                candidate = Path(entry.path) / _SWITCH_FILE
                if entry.is_dir() and candidate.is_file():
                    found[entry.name] = candidate
    except OSError:
        pass
    return found


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        seen = path.stat()
    except OSError:
        return None
    return (seen.st_mtime_ns, seen.st_size)


def _read_switches(state: _State, *, starting: bool) -> None:
    """Read every switch file again, and decide each tenant's switch.

    In production, starting, a file that is invalid is refused, loudly, and
    so is a tenant switched on with no writable directory. In development,
    and in production after the start, an invalid file switches its tenant
    off, counts `config invalid`, and says why on standard error, once for
    each version of the file."""
    files = _switch_files(state)
    switches: dict[str, Switch] = {}
    stamps: dict[str, tuple[int, int]] = {}
    for tenant, path in files.items():
        stamp = _stamp(path)
        if stamp is None:
            continue
        stamps[tenant] = stamp
        try:
            switch = parse_switch(
                path.read_text(encoding="utf-8"),
                where=str(path),
                production=state.production,
            )
            if state.production and switch.on and not _writable(path.parent):
                raise RecorderStartError(
                    f"{path} switches recording on in production, and "
                    f"{path.parent} is not a writable directory to put the "
                    "recordings in (ADR 0058 §10)"
                )
        except (RecorderStartError, OSError, UnicodeDecodeError) as exc:
            if starting and state.production:
                raise
            state.count("config invalid")
            if state.stamps.get(tenant) != stamp:
                _warn(exc, path)
            continue
        switches[tenant] = switch
    # The environment decides only where no file exists: a file that is
    # there and invalid switches recording off, never back to the variable.
    if not state.production and not stamps and _switched_on():
        switches[cast(str, state.tenant)] = Switch(on=True)
    state.stamps = stamps
    state.switches = switches
    state.any_on = any(switch.on for switch in switches.values())
    intervals = [switch.interval for switch in switches.values()]
    state.interval = min(intervals) if intervals else DEFAULT_INTERVAL


def _warn(exc: BaseException, path: Path) -> None:
    """The sentence a refusal would have raised, on standard error, and that
    the recorder is off. Never raises: a warning that failed would fail the
    application it exists to spare."""
    reason = (
        str(exc) if isinstance(exc, RecorderStartError) else f"{path} cannot be read"
    )
    with contextlib.suppress(Exception):
        print(  # noqa: T201 — the application's own stderr, once
            f"digline recorder: not recording for this tenant: {reason}",
            file=sys.stderr,
        )


def _writable(directory: Path) -> bool:
    """Whether recordings can be created under `directory`: it, or the
    nearest ancestor that exists, is a directory this process may write."""
    for candidate in (directory, *directory.parents):
        if candidate.exists():
            return candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK)
    return False


def _look(state: _State) -> None:
    """The look due at the interval: the switch files, read again if any
    changed, and each recording tenant's size, read from the disk. One thread
    looks; the others go on with what was there. Never raises."""
    if not state.look_lock.acquire(blocking=False):
        return
    try:
        files = _switch_files(state)
        stamps = {
            tenant: stamp
            for tenant, path in files.items()
            if (stamp := _stamp(path)) is not None
        }
        if stamps != state.stamps:
            _read_switches(state, starting=False)
        _measure(state)
        state.commit = None
        _flush(state)
    except Exception:  # noqa: BLE001 — the rule of this module
        state.count("config invalid")
    finally:
        state.next_look = _clock() + state.interval
        state.look_lock.release()


def _measure(state: _State) -> None:
    """Each recording tenant's size, from the disk, and a tenant stopped at
    its ceiling recording again once its recordings are under it: the
    ceiling was raised, or recordings were taken away. Its marker goes with
    the stop."""
    for tenant, switch in list(state.switches.items()):
        if not switch.on:
            continue
        size = _recordings_size(state.root, tenant)
        with state.lock:
            state.sizes[tenant] = size
            resumed = tenant in state.stopped and size < switch.ceiling
            if resumed:
                state.stopped.discard(tenant)
        if resumed:
            marker = state.root / _STORE / tenant / _RECORDINGS / _CEILING_MARKER
            with contextlib.suppress(OSError):
                marker.unlink()


class attach:  # noqa: N801 — read as a function at the call site, like `episode`
    """Put the calls made inside it in the episode `id`. (ADR 0058 §5)

    For a thread or a process that does not inherit the context the episode
    was opened in: a `ThreadPoolExecutor` worker, a `threading.Thread`, a
    process. The id is `ep.id`, passed by the application.

        def lookup(order: str, episode_id: str | None) -> str:
            with attach(episode_id):
                return client.messages.create(..., suite="lookup")

        with episode(client, suite="order-agent", case={"ticket": text}) as ep:
            pool.submit(lookup, "A1", ep.id).result()

    `None`, which is `ep.id` while the recorder is off, attaches nothing. The
    calls are recorded with the id whether or not the episode is open in this
    process; where it is not, the import joins them by the id.
    """

    __slots__ = ("_id", "_token")

    def __init__(self, id: str | None) -> None:  # noqa: A002 — the episode's id
        self._id = id if isinstance(id, str) and id else None
        self._token: Token[str | None] | None = None

    def __enter__(self) -> None:
        if self._id is not None:
            self._token = _CURRENT.set(self._id)

    def __exit__(self, *exc: object) -> None:
        _reset(self._token)


def _reset(token: Token[str | None] | None) -> None:
    """Undo a `set`, where it can be undone: a context left in another
    context than the one it entered cannot be, and the application never
    hears of it."""
    if token is None:
        return
    with contextlib.suppress(ValueError):
        _CURRENT.reset(token)


class Episode:
    """One turn of an agent, or one pass through a chain, recorded as one
    recording with its calls attached. (ADR 0058 §5, §8, §9)

    Made by `episode`. The recording is written when the `with` block ends:

    - **case**: the `case=` given, the message that started the turn;
    - **setup**: the `setup=` given, or else the distinct setup digests of its
      direct children, sorted, and the repository's `git_commit`, read as a
      run reads it (`digline.host.environment.git_commit`); `setup_digest` is
      the digest of that. Sorted and distinct, because a turn that loops once
      more through the same setup has not changed its setup;
    - **response**: the output given with `output()`; if the application gave
      none, **the text of the last call to a model made inside it**; with
      neither, the episode is not recorded and counts `no output`, because a
      recorded response has a text and an empty one would be an answer
      nobody gave. Its `tool_calls` are its children's, in order, and `None`
      if any child's plugin said nothing about tools;
    - **steps**: one `model` step per call, with the finish its reply
      reported, followed by a `tool` step per tool call it asked for. A tool's
      result is not visible to the wrapper — it is the application's, sent in
      the next request — so a tool step's result is absent and says
      `not_reported`, never filled in. A nested episode's steps are spliced in
      where it closed.

    Over `MAX_RECORDED_CHARS`, whole or nothing as a run's recorded response
    is: the response says `oversize` and the steps, which carry the calls'
    arguments, are written empty.

    **The episode never fails the application.** An exception raised inside
    the block propagates as it was raised; the recording is still written,
    with what was seen until then, and `interrupted: true`. What goes wrong
    while recording is counted on the wrapped client, by reason.

    Off, it is an empty context: `id` is `None`, `output()` keeps nothing, and
    nothing is imported.
    """

    __slots__ = (
        "_case",
        "_collector",
        "_output",
        "_parent",
        "_setup",
        "_site",
        "_started",
        "_state",
        "_suite",
        "_token",
        "id",
    )

    def __init__(
        self,
        state: _State,
        suite: str | None,
        case: Mapping[str, object],
        setup: Mapping[str, object] | None,
        site: str | None,
    ) -> None:
        self._state = state
        self._suite = suite
        self._case = case
        self._setup = setup
        self._site = site
        #: The episode's id: 32 hexadecimal characters, random, made when the
        #: block is entered. `None` while the recorder is off.
        self.id: str | None = None
        self._output: tuple[object] | None = None
        self._parent: str | None = None
        self._collector: _Collector | None = None
        self._token: Token[str | None] | None = None
        self._started = 0.0

    def output(self, result: object) -> None:
        """The turn's final output, as the application gives it. The last one
        given is the one recorded."""
        if self._state.any_on:
            self._output = (result,)

    def __enter__(self) -> Episode:
        if not self._state.any_on:
            return self
        self.id = os.urandom(16).hex()
        self._parent = _CURRENT.get()
        parent = None if self._parent is None else _OPEN.get(self._parent)
        self._collector = _Collector(
            sampled_out=(
                parent.sampled_out
                if parent is not None
                else not _episode_sampled_in(self._state)
            )
        )
        with _OPEN_LOCK:
            _OPEN[self.id] = self._collector
        self._token = _CURRENT.set(self.id)
        self._started = perf_counter()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.id is None or self._collector is None:
            return
        elapsed_ms = (perf_counter() - self._started) * 1000.0
        _reset(self._token)
        with _OPEN_LOCK:
            _OPEN.pop(self.id, None)
        state = self._state
        known = None if state.production else cast(str, state.tenant)
        if self._collector.sampled_out:
            state.count("sampled out")
            _tally(state, known, self._suite, "sampled out")
            return
        _LAST.tenant = known
        reason = _record_episode(
            self, self._collector, elapsed_ms, interrupted=kind is not None
        )
        state.count(reason)
        _tally(state, _LAST.tenant, self._suite, reason)
        if self._parent is not None:
            parent = _OPEN.get(self._parent)
            if parent is not None:
                parent.add(self._collector)


def episode(
    client: object,
    *,
    case: Mapping[str, object],
    suite: str | None = None,
    setup: Mapping[str, object] | None = None,
) -> Episode:
    """An episode whose recording is filed as `client`'s calls are: the same
    app, tenant and root. `client` is a client `wrap` returned, and any other
    object is refused, by name, recording or not.

    `case=` is required: the input that started the turn, a mapping of
    names to JSON values, as the case will hold it, for example
    `{"ticket": text}` or `{"messages": [...]}`. Two turns with the same
    `case` are the same case at the import. `suite=` names the suite, as
    `suite=` does on a call; an episode that names none is `_unassigned`,
    with its call site. `setup=` replaces the setup the episode derives
    from its calls, where the turn runs steps no model call shows.

        with episode(client, suite="order-agent", case={"ticket": text}) as ep:
            ...
            ep.output(answer)
    """
    if not isinstance(client, RecordedClient):
        raise RecorderStartError(
            "episode() takes a client wrap() returned, so that the episode is "
            "filed under its app and tenant"
        )
    state: _State = client._digline_state  # pyright: ignore[reportPrivateUsage]
    site = _call_site() if state.any_on and suite is None else None
    return Episode(state, suite, case, setup, site)


def _episode_sampled_in(state: _State) -> bool:
    """The outermost episode's draw, against its tenant's switch. Where the
    tenant or its switch cannot be read here, the episode is drawn in, and its
    close says why it is not recorded."""
    try:
        tenant = _tenant_of(state)
        switch = None if tenant is None else state.switches.get(tenant)
    except Exception:  # noqa: BLE001 — the rule of this module
        return True
    if switch is None or not switch.on:
        return True
    return _sampled_in(switch)


def _now() -> str:
    """The system time a recording is written at, read by the host's clock,
    imported here and not at the top: this module imports nothing of
    digline's until it records. (ADR 0058 §10, as amended 2026-11-03)"""
    from digline.host.environment import utc_now_iso

    return utc_now_iso()


def _commit(state: _State) -> str | None:
    """The repository's commit, read as a run reads it, once until the next
    look: two `git` processes are tens of milliseconds."""
    cached = state.commit
    if cached is None:
        from digline.host.environment import git_commit

        cached = (git_commit(state.root),)
        state.commit = cached
    return cached[0]


def _record_episode(
    ep: Episode, collector: _Collector, elapsed_ms: float, *, interrupted: bool
) -> str | None:
    """Write an episode's recording, or say why not. `_record`'s rule: nothing
    here raises, and each stage is its reason."""
    stage = "unexpected"
    try:
        from digline.core.recording import RecordedStep, Recording, setup_digest_of
        from digline.core.run import (
            MAX_RECORDED_CHARS,
            RecordedResponse,
            record_output,
            trajectory_chars,
        )
        from digline.store.file_store import FileResultStore, RecordingWriter

        state = ep._state  # pyright: ignore[reportPrivateUsage]
        calls = collector.calls()

        stage = "setup"
        given = ep._setup  # pyright: ignore[reportPrivateUsage]
        if given is not None:
            setup = dict(given)
        else:
            setup: dict[str, object] = {"child_setups": sorted(collector.digests())}
            commit = _commit(state)
            if commit is not None:
                setup["git_commit"] = commit

        stage = "not JSON"
        digest = setup_digest_of(setup)
        collector.digest = digest

        stage = "output"
        kept = ep._output  # pyright: ignore[reportPrivateUsage]
        if kept is not None:
            text, kind = record_output(cast(Any, kept[0]))
        elif calls:
            text, kind = calls[-1].text, "text"
        else:
            # A recorded response always has its text or says why not, and
            # an empty string would be an answer nobody gave.
            return "no output"

        steps: list[RecordedStep] = []
        trajectory: list[RecordedToolCall] | None = []
        for seen in calls:
            steps.append(
                RecordedStep(index=len(steps), actor="model", finish=seen.finish)
            )
            if seen.calls is None:
                # A call whose plugin said nothing about tools: the episode
                # cannot say what was called either.
                trajectory = None
                continue
            for call in seen.calls:
                steps.append(RecordedStep(index=len(steps), actor="tool", call=call))
                if trajectory is not None:
                    trajectory.append(call)
        oversize = len(text) > MAX_RECORDED_CHARS or (
            trajectory_chars(trajectory or ()) > MAX_RECORDED_CHARS
        )
        response = (
            RecordedResponse(oversize=True, latency_ms=elapsed_ms)
            if oversize
            else RecordedResponse(
                output=text,
                kind=kind,
                latency_ms=elapsed_ms,
                tool_calls=None if trajectory is None else tuple(trajectory),
            )
        )

        stage = "tenant"
        tenant = _tenant_of(state)
        _LAST.tenant = tenant
        if tenant is None:
            return stage
        switch = state.switches.get(tenant)
        if switch is None or not switch.on:
            return "off for this tenant"
        if _at_ceiling(state, tenant, switch):
            return "ceiling"

        stage = "not JSON"
        suite = ep._suite  # pyright: ignore[reportPrivateUsage]
        recording = Recording(
            source_tenant=tenant,
            app=state.app,
            suite=suite if isinstance(suite, str) and suite else UNASSIGNED,
            case=ep._case,  # pyright: ignore[reportPrivateUsage]
            setup=setup,
            setup_digest=digest,
            response=response,
            episode=ep._parent,  # pyright: ignore[reportPrivateUsage]
            call_site=ep._site,  # pyright: ignore[reportPrivateUsage]
            # Over the ceiling, whole or nothing: the steps carry the calls'
            # arguments, so they go with the text (ADR 0015 §3).
            steps=() if oversize else tuple(steps),
            interrupted=interrupted,
            unrecorded_children=collector.children_unrecorded(),
            id=ep.id,
            recorded_at=_now(),
        )

        stage = "writer"
        _write(state, tenant, recording, RecordingWriter, FileResultStore)
    except Exception:  # noqa: BLE001 — the rule of this module
        return stage
    return None


def _switched_on() -> bool:
    value = os.environ.get(ENVIRONMENT_VARIABLE, "")
    if value in ("", "0"):
        return False
    if value == "1":
        return True
    raise RecorderStartError(
        f"{ENVIRONMENT_VARIABLE} is set to a value that is neither 1 (record) nor "
        "0 or empty (do not record)"
    )


def _key_of(client: object) -> list[str]:
    """The names a plugin may declare this client under: the root package of
    each class in its MRO, a dot, and the class's name."""
    return [
        f"{kind.__module__.split('.', 1)[0]}.{kind.__name__}"
        for kind in type(client).__mro__
    ]


def _find(client: object) -> tuple[Any, tuple[str, ...]]:
    declared: dict[str, tuple[Any, tuple[str, ...]]] = {}
    for entry in entry_points(group=MAP_GROUP):
        kind, colon, method = entry.name.partition(":")
        path = tuple(part for part in method.split(".") if part)
        if colon and kind and path:
            declared[kind] = (entry, path)
    for key in _key_of(client):
        if key in declared:
            return declared[key]
    named = ", ".join(sorted(declared)) or "none"
    raise RecorderStartError(
        f"no installed plugin records a client of type {_key_of(client)[0]}. "
        f"The plugins installed record: {named}. An asynchronous client is not "
        "recorded yet"
    )


def wrap(
    client: object,
    *,
    app: str,
    tenant: str | Callable[[], str],
    root: str | Path | None = None,
) -> RecordedClient:
    """The client, recording its calls where its tenant's switch is on.

    `tenant` is a name, which is development, or a function called at every
    call whose value is the recording's `source_tenant` and the directory it
    is filed under, which is production (ADR 0058 §4). `root` is the
    directory that holds `.digline/`, the current directory when this is
    called if not given.

    Refused here, never at a call: in production, an invalid switch file,
    `DIGLINE_RECORD=1` and the three refusals of §10. In development an
    invalid switch file is said on standard error and leaves the recorder
    off.

    The client returned is the client, with its call intercepted: every
    other attribute is the client's own. `client.digline_counts` says how
    many calls this process recorded and, per reason, how many it did not;
    `digline record status` reads the same counts from every process.
    """
    if not isinstance(app, str) or not app:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise RecorderStartError("wrap() needs app=, a non-empty name")
    if not callable(tenant) and (not isinstance(tenant, str) or not tenant):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise RecorderStartError(
            "wrap() needs tenant=, a non-empty name or a function that returns one"
        )
    entry, path = _find(client)
    state = _State(
        app=app,
        tenant=tenant,
        root=Path(root) if root is not None else Path.cwd(),
        entry=entry,
    )
    # Read before the files, so a value that is neither on nor off is refused
    # in both regimes.
    environment = _switched_on()
    if state.production and environment:
        raise RecorderStartError(
            f"{ENVIRONMENT_VARIABLE}=1 with a tenant function, which is "
            "production: the variable declares no redaction and no sampling, "
            "so in production recording is switched on per tenant by its file "
            "(digline record on --production) (ADR 0058 §10)"
        )
    _read_switches(state, starting=True)
    _measure(state)
    state.next_look = _clock() + state.interval
    return RecordedClient(client, path, state)
