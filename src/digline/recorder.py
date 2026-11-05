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

A client, synchronous or asynchronous, and a reply, whole or streamed: an
asynchronous client's call is awaited as the SDK's is, and a stream reaches
the application as the SDK built it, watched as it is read. The recordings
become cases with `digline record import`, and `docs/record.md` walks through
the whole of it.

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
counted with its reason. A stream closed or dropped before its end counts
*stream abandoned*, and a stream through a map that cannot read one counts
*streaming*. An exception of the provider's SDK propagates as it is,
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
import itertools
import os
import re
import sys
import threading
from collections.abc import Callable, Generator, Mapping, Sequence
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
# top, and everything of digline's lazily: in `wrap()` when the recorder is on
# there, otherwise at the first call it records (`_ready`).
if TYPE_CHECKING:
    from types import TracebackType

    from digline.core import Usage
    from digline.core.run import RecordedToolCall
    from digline.run.driver import Response
    from digline.store.file_store import RecordingWriter
    from digline.targets import Completion, ToolCall

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
    "RecordingWire",
    "StreamReading",
    "WIRE_GROUP",
    "WireRecorder",
    "attach",
    "collecting",
    "episode",
    "parse_switch",
    "running",
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
#: because this module does not import the store while it is off, and a test
#: holds the two equal.
_STORE = ".digline"
_SWITCH_FILE = "recorder.toml"
_RECORDINGS = "recordings"
_CEILING_MARKER = "ceiling-reached.json"

#: A tenant is a directory of the layout, so it is a name the store would take:
#: `checked_name`'s rule (GHSA-j878-2v6m-m4vx), restated for the reason above
#: and held equal to the store's by the same test.
_NAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _a_name(value: object) -> bool:
    return isinstance(value, str) and _NAME.fullmatch(value) is not None


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

#: The collection of the target's call the current context is inside, or
#: `None`: what `collecting()` opens, around one call of a run's target and
#: never anywhere else. It crosses what `_CURRENT` crosses and nothing more,
#: and `attach` does not carry it (ADR 0060 §3).
_COLLECTING: ContextVar[_Collected | None] = ContextVar(
    "digline_collecting", default=None
)

#: Whether the current context is inside a run, its target's calls and its
#: judges' alike: what `running()` opens around `execute()`. A run's calls are
#: the gate's, not the application's traffic, so nothing inside one is written
#: as a recording, and the counts do not move. `collecting()` says the same of
#: the target's calls on its own, for a library caller that passes it to
#: `execute()` without `running()`.
_RUNNING: ContextVar[bool] = ContextVar("digline_running", default=False)

#: The episodes open in this process, by id. A call made inside one, through any
#: wrapped client, adds its step to it.
_OPEN: dict[str, _Collector] = {}
_OPEN_LOCK = threading.Lock()

#: The episodes this process closed, most recent last, so that a call made
#: after its episode closed is told from one attached from another process,
#: whose episode was never open here. Bounded: past `_CLOSED_KEPT` the oldest
#: id is forgotten, and a call that late carries the id unmarked, as a call
#: from another process does, for the import to join.
_CLOSED: dict[str, None] = {}
_CLOSED_KEPT = 10_000


def _late(inside: str | None) -> bool:
    """Whether `inside` is an episode this process has closed."""
    return inside is not None and inside not in _OPEN and inside in _CLOSED


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


class StreamReading(Protocol):
    """How a map reads a streamed reply: each event as the application reads
    it, then the `Completion` the whole reply would have given, at its end.
    `stream` is the SDK's stream object, for a stream that keeps its own
    final reply."""

    def add(self, event: Any) -> None: ...

    def completion(self, stream: Any) -> Completion: ...


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


class RecordingWire(Protocol):
    """What a plugin provides for a call read off the wire, by `digline record
    proxy`: one route, its map, and the SDK's own types for its JSON.
    (ADR 0062 §3)

    Declared under `digline.recording_wire`, one entry per route, the entry's
    name being the route's (`openai`, `anthropic`), which `--upstream
    ROUTE=URL` names. Every entry is loaded when the proxy starts.

    - `matches(path)` says whether a request's path is this route's;
    - `base` is the part of the path the SDK's base URL ends in (`/v1` for
      OpenAI, nothing for Anthropic), taken off before the upstream's own;
    - `upstream` is where the route forwards when nothing else is said;
    - `claims(headers)` says whether the request's key is this provider's,
      which picks the upstream for a route `--upstream` does not name;
    - `reply` and `event` turn a reply's JSON, and one streamed event's, into
      the SDK's types, which `map` then reads as it reads an SDK's reply;
    - `load()` imports the SDK, at the start: two threads importing one SDK
      for the first time at once were measured to fail half-way.

    Seven more a route may provide, read with `getattr`, where its provider
    needs them:

    - `results(request)`: the tool results the request carries for the model
      turn before it, as `ToolCall`s in the order of that turn's calls, or
      `None` where it carries none. In an episode they close the tool steps
      of the call before (`WireRecorder`);
    - `request_of(path, request)`: the request as the SDK's own call names
      it, where the path carries part of it (Bedrock's model id);
    - `frames(content_type, data)`: the events of a streamed reply that is
      not server-sent events, or `None` where the type is not this route's
      framing (Bedrock's event stream);
    - `verify(method, path, headers, body)`: why the request as the
      application sent it may not be forwarded, or `None`; a 403 that says
      it where it is not `None` (Bedrock's: signed with this machine's AWS
      credentials, which `prepare` then signs with);
    - `prepare(method, url, headers, body)`: the headers sent upstream, where
      the route signs a request itself (Bedrock's SigV4, with the local
      credentials); it raises `ValueError` with the reason where it cannot;
    - `problem`: why the route cannot forward, said at the start and in the
      502 at a call, or `None`; and `variable`, the environment variable
      the SDK reads its address from, where it is not `<ROUTE>_BASE_URL`.
    """

    @property
    def map(self) -> RecordingMap: ...

    @property
    def base(self) -> str: ...

    @property
    def upstream(self) -> str: ...

    def matches(self, path: str) -> bool: ...

    def claims(self, headers: Mapping[str, str]) -> bool: ...

    def reply(self, raw: object) -> Any: ...

    def event(self, raw: object) -> Any: ...

    def load(self) -> None: ...


class _Shared:
    """What every wrapped client of this process shares under one root: the
    writer, so that the process has one subdirectory per tenant whatever the
    number of clients it wraps (ADR 0058 §4, §10), and the counts its counts
    file holds."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()
        self.writer: RecordingWriter | None = None
        #: Per tenant and suite, what this process recorded and did not, as
        #: its counts file holds it; the tenants whose file exists.
        self.tallies: dict[str, dict[str, dict[str, Any]]] = {}
        self.tallied: set[str] = set()
        #: The tenants counted since their file was last written.
        self.dirty: set[str] = set()
        self.tally_lock = threading.Lock()


#: One `_Shared` per root this process wraps clients under, by the root
#: resolved: two spellings of one directory are one place.
_SHARED: dict[Path, _Shared] = {}
_SHARED_LOCK = threading.Lock()


def _shared(root: Path) -> _Shared:
    where = root.resolve()
    with _SHARED_LOCK:
        found = _SHARED.get(where)
        if found is None:
            found = _SHARED[where] = _Shared(root)
        return found


class _State:
    """What every intercepted call of one wrapped client shares."""

    def __init__(
        self,
        *,
        app: str,
        tenant: str | Callable[[], str],
        root: Path,
    ) -> None:
        self.app = app
        self.tenant = tenant
        self.root = root
        self.lock = threading.Lock()
        self.recorded = 0
        self.not_recorded: dict[str, int] = {}
        self.orphan = 0
        #: Recorded, with something said beside it: `usage not reported`,
        #: `ended after its episode`.
        self.noted: dict[str, int] = {}
        #: The writer and the counts file, shared with every client of this
        #: process wrapped under the same root.
        self.shared = _shared(root)
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

    def count(self, reason: str | None) -> None:
        with self.lock:
            if reason is None:
                self.recorded += 1
            else:
                self.not_recorded[reason] = self.not_recorded.get(reason, 0) + 1

    def count_orphan(self) -> None:
        with self.lock:
            self.orphan += 1

    def note(self, what: str) -> None:
        with self.lock:
            self.noted[what] = self.noted.get(what, 0) + 1


class _Slot:
    """One intercepted method: the entry point that names it, and its map,
    loaded the first time a call through it is recorded."""

    __slots__ = ("entry", "lock", "map")

    def __init__(self, entry: Any) -> None:
        self.entry = entry
        self.map: Any = None
        self.lock = threading.Lock()

    def mapped(self) -> Any:
        with self.lock:
            if self.map is None:
                self.map = self.entry.load()
            return self.map


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
        #: Streams opened inside the episode and not yet ended. When the
        #: episode closes, each is a child it did not see, said as one.
        self.pending = 0
        self.digest: str | None = None

    def begin(self) -> None:
        with self.lock:
            self.pending += 1

    def settle(self) -> None:
        with self.lock:
            self.pending -= 1

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
            own = self.unrecorded + self.pending
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


class _Collected:
    """The calls a run's target made through wrapped clients, inside one
    `collecting()` block, recorder on or off. (ADR 0060 §3)

    Each call read is its `Completion` and the time the reply took, in the
    order the replies were read. `missed` counts a call made and not read: a
    reply the map could not read, a call made with positional arguments, a
    stream through a map that cannot read one, a stream that ended before its
    end. `pending` counts the streams begun and not yet ended. Either makes the
    collection incomplete, and an incomplete collection gives no steps.

    Closed when its block ends: a stream that ends after that reaches nothing.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.calls: list[tuple[Completion, float]] = []
        self.missed = 0
        self.pending = 0
        self.closed = False

    def add(self, completion: Completion, elapsed_ms: float) -> None:
        with self.lock:
            if not self.closed:
                self.calls.append((completion, elapsed_ms))

    def miss(self) -> None:
        with self.lock:
            if not self.closed:
                self.missed += 1

    def begin(self) -> None:
        with self.lock:
            if not self.closed:
                self.pending += 1

    def end(self, completion: Completion | None, elapsed_ms: float) -> None:
        """A stream begun inside the block has ended, read or not."""
        with self.lock:
            if self.closed:
                return
            self.pending -= 1
            if completion is None:
                self.missed += 1
            else:
                self.calls.append((completion, elapsed_ms))

    def close(self) -> None:
        with self.lock:
            self.closed = True


class RecordedClient:
    """The client, with its mapped methods intercepted and everything else its
    own.

    Attribute access goes to the client, except along the paths to the
    intercepted methods: one per entry point a plugin declares for the
    client, `messages.create` and `messages.stream` sharing `messages`.
    `digline_counts` says how many calls were recorded and, per reason, how
    many were not; it lives in memory, on this object.
    """

    __slots__ = (
        "_digline_branches",
        "_digline_state",
        "_digline_target",
        "_digline_tree",
    )
    _digline_branches: dict[str, RecordedClient]
    _digline_tree: dict[str, Any]
    _digline_state: _State
    _digline_target: Any

    def __init__(self, target: Any, tree: dict[str, Any], state: _State) -> None:
        object.__setattr__(self, "_digline_target", target)
        object.__setattr__(self, "_digline_tree", tree)
        object.__setattr__(self, "_digline_state", state)
        object.__setattr__(self, "_digline_branches", {})

    def __getattr__(self, name: str) -> Any:
        tree: dict[str, Any] = self._digline_tree
        value = getattr(self._digline_target, name)
        node = tree.get(name)
        if node is None:
            return value
        if isinstance(node, _Slot):
            return _intercepted(value, self._digline_state, node)
        branches: dict[str, RecordedClient] = self._digline_branches
        branch = branches.get(name)
        if branch is None or branch._digline_target is not value:
            branch = RecordedClient(
                value, cast(dict[str, Any], node), self._digline_state
            )
            branches[name] = branch
        return branch

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._digline_target, name, value)

    def __repr__(self) -> str:
        return f"<recorded {self._digline_target!r}>"

    @property
    def digline_counts(self) -> Mapping[str, object]:
        """`{"recorded": n, "not_recorded": {reason: n, ...}, "orphan": n,
        "noted": {what: n, ...}}`, as of now. `noted` counts recordings
        written with something said beside them: `usage not reported`, a
        stream whose provider gave no counts, and `ended after its episode`.
        `recorded` counts the calls, and the episodes opened on this client.
        `orphan` counts the calls recorded with no episode while one was open
        in this process: a child whose thread was not attached, or a call that
        belongs to none.
        The recorder cannot tell which, and attaches neither (ADR 0058 §5)."""
        state: _State = self._digline_state
        with state.lock:
            return {
                "recorded": state.recorded,
                "not_recorded": dict(state.not_recorded),
                "orphan": state.orphan,
                "noted": dict(state.noted),
            }


def _intercepted(
    method: Callable[..., Any], state: _State, slot: _Slot
) -> Callable[..., Any]:
    def call(*args: Any, **kwargs: Any) -> Any:
        suite = kwargs.pop(_SUITE, None)
        variables = kwargs.pop(_VARS, None)
        if _clock() >= state.next_look:
            _look(state)
        # Read before the one test an off client makes: a run's collection is
        # open whether or not the recorder is on (ADR 0060 §3).
        collected = _COLLECTING.get()
        # Inside a run the wrapper collects and never writes: the target's
        # and the judges' calls are the gate's, not the application's traffic,
        # and a recording of them would be filed as the application's suite.
        records = state.any_on and collected is None and not _RUNNING.get()
        if collected is None and not records:
            return method(*args, **kwargs)
        inside = _CURRENT.get() if records else None
        known = None if state.production else cast(str, state.tenant)
        if args:
            if records:
                _joined(state, inside, "positional arguments", None)
                _tally(state, known, suite, "positional arguments")
            if collected is not None:
                collected.miss()
            return method(*args, **kwargs)
        mapped = _map_or_none(slot)
        streamed = _streams(mapped, kwargs)
        if streamed and not hasattr(mapped, "reading"):
            if records:
                _joined(state, inside, "streaming", None)
                _tally(state, known, suite, "streaming")
            if collected is not None:
                collected.miss()
            return method(**kwargs)
        site = _call_site() if records and suite is None else None
        started = perf_counter()
        reply = method(**kwargs)
        if _awaitable(reply):
            # An asynchronous client's call: what the application awaits is
            # the SDK's own awaitable, awaited here and handed on as it came.
            return _awaited(
                reply,
                state,
                slot,
                mapped,
                kwargs,
                streamed,
                suite,
                variables,
                site,
                inside,
                known,
                collected,
                records,
            )
        if streamed:
            # The application gets the stream the SDK built, the same object;
            # it is watched as the application reads it, and recorded at its
            # end. (ADR 0058 §13)
            _watch(
                state,
                slot,
                mapped,
                kwargs,
                reply,
                started,
                suite,
                variables,
                site,
                inside,
                known,
                collected,
                records,
            )
            return reply
        elapsed_ms = (perf_counter() - started) * 1000.0
        if records:
            _ended(
                state,
                slot,
                kwargs,
                reply,
                elapsed_ms,
                suite,
                variables,
                site,
                inside,
                known,
            )
        if collected is not None:
            _collect(collected, mapped, kwargs, reply, elapsed_ms)
        return reply

    return call


def _collect(
    collected: _Collected,
    mapped: Any,
    request: Mapping[str, Any],
    reply: Any,
    elapsed_ms: float,
) -> None:
    """Hand one call's reply to the run's collection, read by the plugin's
    map, or count it missed. Never raises: the application's call is not
    failed by the collection any more than by the recorder."""
    try:
        completion = cast("Completion", mapped.completion(reply, request))
    except Exception:  # noqa: BLE001 — the rule of this module
        collected.miss()
        return
    collected.add(completion, elapsed_ms)


def _awaitable(value: object) -> bool:
    """Whether `value` is to be awaited. `inspect`, imported here, at a call
    the recorder is on for: switched off, this module imports nothing it can
    do without."""
    import inspect

    return inspect.isawaitable(value)


def _awaitable_function(value: object) -> bool:
    import inspect

    return inspect.iscoroutinefunction(value)


async def _awaited(
    pending: Any,
    state: _State,
    slot: _Slot,
    mapped: Any,
    request: Mapping[str, Any],
    streamed: bool,
    suite: object,
    variables: object,
    site: str | None,
    inside: str | None,
    known: str | None,
    collected: _Collected | None,
    records: bool,
) -> Any:
    """An asynchronous call: the SDK's reply, awaited, recorded and collected
    as a synchronous one is, and returned as it came. A streamed reply is the
    SDK's asynchronous stream, watched as the application reads it. An
    exception of the SDK propagates as it was raised."""
    started = perf_counter()
    reply = await pending
    if streamed:
        _watch(
            state,
            slot,
            mapped,
            request,
            reply,
            started,
            suite,
            variables,
            site,
            inside,
            known,
            collected,
            records,
        )
        return reply
    elapsed_ms = (perf_counter() - started) * 1000.0
    if records:
        _ended(
            state,
            slot,
            request,
            reply,
            elapsed_ms,
            suite,
            variables,
            site,
            inside,
            known,
        )
    if collected is not None:
        _collect(collected, mapped, request, reply, elapsed_ms)
    return reply


def _ended(
    state: _State,
    slot: _Slot,
    request: Mapping[str, Any],
    reply: Any,
    elapsed_ms: float,
    suite: object,
    variables: object,
    site: str | None,
    inside: str | None,
    known: str | None,
    *,
    completion: Completion | None = None,
    drawn: bool | None = None,
    unread: bool = False,
) -> None:
    """A call that has ended, whole or streamed: recorded, or said why not,
    and counted, in its episode where that is still open.

    **A call whose episode this process has closed** — a stream that ended
    after it, or a call made in a task attached to it that ran on — is
    recorded with the episode's id, marked an orphan, and noted `ended after
    its episode`: the episode is already written without it, and the recorder
    neither waits nor guesses where it belonged. `unread` is a stream whose
    reading gave no reply, which is the map's failure."""
    late = _late(inside)
    _LAST.tenant = known
    _LAST.notes = []
    if unread:
        reason, seen = "map", None
    else:
        reason, seen = _record(
            state,
            slot,
            request,
            reply,
            elapsed_ms,
            suite,
            variables,
            site,
            inside,
            completion=completion,
            late=late,
            drawn=drawn,
        )
    if reason is None and late:
        state.note("ended after its episode")
        _LAST.notes.append("ended after its episode")
    _joined(state, None if late else inside, reason, seen)
    _tally(state, _LAST.tenant, suite, reason, tuple(_LAST.notes))


def _map_or_none(slot: _Slot) -> Any:
    """The slot's map, or `None` where it cannot be loaded; the failure is
    then said by the recording's own `map` stage."""
    try:
        return slot.mapped()
    except Exception:  # noqa: BLE001 — the rule of this module
        return None


def _streams(mapped: Any, request: Mapping[str, Any]) -> bool:
    """Whether this call answers with a stream: the map says, where it says;
    otherwise `stream=True` on the call does."""
    says = getattr(mapped, "streams", None)
    if callable(says):
        with contextlib.suppress(Exception):
            return bool(says(request))
    return bool(request.get("stream"))


#: Each stream class the SDKs build, and the subclass of it that watches.
_WATCHED: dict[type, type] = {}
_WATCHED_LOCK = threading.Lock()


def _watching(kind: type) -> type:
    """A subclass of the SDK's own stream class that hands every event to its
    watch as the application reads it, and on to the application unchanged:
    no buffer, no reordering, nothing withheld. Made once per class.

    The stream keeps being the object the SDK built: its class becomes this
    subclass, so `isinstance` holds and every attribute is its own."""
    base: Any = kind
    with _WATCHED_LOCK:
        made = _WATCHED.get(kind)
        if made is not None:
            return made

        def __iter__(self: Any) -> Any:  # noqa: N807
            watch: _Watch = self.__dict__["_digline_watch"]
            try:
                for item in base.__iter__(self):
                    watch.item(item)
                    yield item
            except GeneratorExit:
                raise
            except BaseException as exc:
                watch.failed(exc)
                raise
            watch.finished(self)

        def __next__(self: Any) -> Any:  # noqa: N807
            watch: _Watch = self.__dict__["_digline_watch"]
            try:
                item = base.__next__(self)
            except StopIteration:
                watch.finished(self)
                raise
            except BaseException as exc:
                watch.failed(exc)
                raise
            watch.item(item)
            return item

        def close(self: Any, *args: Any, **kwargs: Any) -> Any:
            self.__dict__["_digline_watch"].closing()
            return base.close(self, *args, **kwargs)

        async def __aiter__(self: Any) -> Any:  # noqa: N807
            watch: _Watch = self.__dict__["_digline_watch"]
            try:
                async for item in base.__aiter__(self):
                    watch.item(item)
                    try:
                        yield item
                    except BaseException:
                        # Thrown in where the application holds the stream,
                        # never by the SDK: `GeneratorExit` or `CancelledError`
                        # from a loop closing a generator left half read.
                        watch.abandoned()
                        raise
            except BaseException as exc:
                _ended_early(watch, exc)
                raise
            await watch.finished_async(self)

        async def __anext__(self: Any) -> Any:  # noqa: N807
            watch: _Watch = self.__dict__["_digline_watch"]
            try:
                item = await base.__anext__(self)
            except StopAsyncIteration:
                await watch.finished_async(self)
                raise
            except BaseException as exc:
                _ended_early(watch, exc)
                raise
            watch.item(item)
            return item

        async def aclose(self: Any, *args: Any, **kwargs: Any) -> Any:
            self.__dict__["_digline_watch"].closing()
            return await base.close(self, *args, **kwargs)

        namespace: dict[str, Any] = {}
        if hasattr(kind, "__aiter__"):
            # An asynchronous stream: the same watch, awaited.
            namespace["__aiter__"] = __aiter__
            if hasattr(kind, "__anext__"):
                namespace["__anext__"] = __anext__
            if _awaitable_function(getattr(kind, "close", None)):
                namespace["close"] = aclose
        else:
            namespace["__iter__"] = __iter__
            if hasattr(kind, "__next__"):
                namespace["__next__"] = __next__
            if hasattr(kind, "close"):
                namespace["close"] = close
        made = type(kind.__name__, (kind,), namespace)
        made.__module__ = kind.__module__
        made.__qualname__ = kind.__qualname__
        _WATCHED[kind] = made
        return made


def _ended_early(watch: _Watch, exc: BaseException) -> None:
    """An asynchronous stream that ended before its end. A cancellation, or a
    generator closed, is the application leaving the stream, which is
    *stream abandoned*; anything else came from the SDK, and is counted by
    its class's name. `asyncio` is read from `sys.modules`: a loop that is
    not asyncio's has none of its cancellations to tell apart."""
    loop = sys.modules.get("asyncio")
    if isinstance(exc, GeneratorExit) or (
        loop is not None and isinstance(exc, loop.CancelledError)
    ):
        watch.abandoned()
    else:
        watch.failed(exc)


def _entering(kind: type) -> type:
    """A subclass of a stream manager whose `__enter__` watches the stream it
    returns: `messages.stream()` and `chat.completions.stream()` send the
    request when they are entered, and give the stream then."""
    base: Any = kind
    with _WATCHED_LOCK:
        made = _WATCHED.get(kind)
        if made is not None:
            return made

        def __enter__(self: Any) -> Any:  # noqa: N807
            stream: Any = base.__enter__(self)
            _attach(stream, self.__dict__["_digline_watch"])
            return stream

        async def __aenter__(self: Any) -> Any:  # noqa: N807
            stream: Any = await base.__aenter__(self)
            _attach(stream, self.__dict__["_digline_watch"])
            return stream

        namespace: dict[str, Any] = {}
        if hasattr(kind, "__enter__"):
            namespace["__enter__"] = __enter__
        if hasattr(kind, "__aenter__"):
            namespace["__aenter__"] = __aenter__
        made = type(kind.__name__, (kind,), namespace)
        made.__module__ = kind.__module__
        made.__qualname__ = kind.__qualname__
        _WATCHED[kind] = made
        return made


def _attach(stream: Any, watch: _Watch) -> None:
    """Watch `stream` in place. A stream dropped unread, closed or not, is
    abandoned when it is collected."""
    import weakref

    kind = cast(type, stream.__class__)
    stream.__dict__["_digline_watch"] = watch
    stream.__class__ = _watching(kind)
    weakref.finalize(stream, watch.abandoned)


def _watch(
    state: _State,
    slot: _Slot,
    mapped: Any,
    request: Mapping[str, Any],
    reply: Any,
    started: float,
    suite: object,
    variables: object,
    site: str | None,
    inside: str | None,
    known: str | None,
    collected: _Collected | None = None,
    records: bool = True,
) -> None:
    """Start watching a streamed reply, or say why not. Never raises."""
    watch: _Watch | None = None
    try:
        watch = _Watch(
            state,
            slot,
            mapped,
            request,
            started,
            suite,
            variables,
            site,
            inside,
            known,
            collected,
            records,
        )
        if getattr(mapped, "entered", False):
            manager: Any = reply
            kind = cast(type, manager.__class__)
            manager.__dict__["_digline_watch"] = watch
            manager.__class__ = _entering(kind)
        else:
            stream_of = getattr(mapped, "stream_of", None)
            _attach(stream_of(reply) if callable(stream_of) else reply, watch)
    except Exception:  # noqa: BLE001 — the rule of this module
        if watch is not None:
            # Begun in the collection and never to end there.
            watch.unwatched()
        elif collected is not None:
            collected.miss()
        if records:
            _joined(state, inside, "stream not watched", None)
            _tally(state, known, suite, "stream not watched")


class _Watch:
    """One streamed reply, watched as the application reads it.

    The events go to the map's reading as they pass. At the end of the
    stream the reading gives the `Completion` the whole reply would have
    given, and the call is recorded then, by the same path as any call. A
    stream closed before its end, or dropped unread, is **abandoned**: half a
    reply is not a reply, and it is not recorded. An exception inside the
    stream propagates as it was raised, and is counted by its class's name.

    Inside an episode the stream is pending until it ends. If the episode has
    closed by then, the call is recorded with the episode's id and marked an
    orphan, and `ended after its episode` is noted: the recorder neither
    waits for the stream nor guesses where it belonged.

    Inside a run's collection the stream is pending there too, and its end
    hands the `Completion` to it, recorder on or off; `records` is false
    where only the collection watches (ADR 0060 §3).
    """

    def __init__(
        self,
        state: _State,
        slot: _Slot,
        mapped: Any,
        request: Mapping[str, Any],
        started: float,
        suite: object,
        variables: object,
        site: str | None,
        inside: str | None,
        known: str | None,
        collected: _Collected | None = None,
        records: bool = True,
    ) -> None:
        self.state = state
        self.slot = slot
        self.request = request
        self.started = started
        self.suite = suite
        self.variables = variables
        self.site = site
        self.inside = inside
        self.known = known
        self.lock = threading.Lock()
        self.done = False
        self.broken = False
        self.reading = mapped.reading(request)
        collector = None if inside is None else _OPEN.get(inside)
        #: The episode's draw, read now: by the stream's end it may have closed.
        self.drawn = None if collector is None else not collector.sampled_out
        if collector is not None:
            collector.begin()
        self.collected = collected
        self.records = records
        if collected is not None:
            collected.begin()

    def item(self, event: Any) -> None:
        if self.done or self.broken:
            return
        try:
            self.reading.add(event)
        except Exception:  # noqa: BLE001 — the rule of this module
            self.broken = True

    def _settle(self) -> bool:
        with self.lock:
            if self.done:
                return False
            self.done = True
        collector = None if self.inside is None else _OPEN.get(self.inside)
        if collector is not None:
            collector.settle()
        return True

    def finished(self, stream: Any) -> None:
        if not self._settle():
            return
        completion: Any = None
        if not self.broken:
            with contextlib.suppress(Exception):
                completion = self.reading.completion(stream)
        self._recorded(completion)

    async def finished_async(self, stream: Any) -> None:
        """`finished`, for an asynchronous stream, whose final reply may be
        read with a coroutine (`get_final_message()` on `AsyncMessageStream`)."""
        if not self._settle():
            return
        completion: Any = None
        if not self.broken:
            with contextlib.suppress(Exception):
                completion = self.reading.completion(stream)
                if _awaitable(completion):
                    completion = await completion
        self._recorded(completion)

    def _recorded(self, completion: Any) -> None:
        elapsed_ms = (perf_counter() - self.started) * 1000.0
        if self.collected is not None:
            self.collected.end(completion, elapsed_ms)
        if not self.records:
            return
        _ended(
            self.state,
            self.slot,
            self.request,
            None,
            elapsed_ms,
            self.suite,
            self.variables,
            self.site,
            self.inside,
            self.known,
            completion=completion,
            drawn=self.drawn,
            unread=completion is None,
        )

    def failed(self, exc: BaseException) -> None:
        if not self._settle():
            return
        reason = type(exc).__name__
        if self.collected is not None:
            self.collected.end(None, 0.0)
        if self.records:
            _joined(self.state, self.inside, reason, None)
            _tally(self.state, self.known, self.suite, reason)

    def closing(self) -> None:
        self.abandoned()

    def abandoned(self) -> None:
        if not self._settle():
            return
        if self.collected is not None:
            self.collected.end(None, 0.0)
        if self.records:
            _joined(self.state, self.inside, "stream abandoned", None)
            _tally(self.state, self.known, self.suite, "stream abandoned")

    def unwatched(self) -> None:
        """The stream could not be watched after all: the collection counts it
        missed, and the caller says why on the recorder's side, as it did
        before the collection existed."""
        with self.lock:
            if self.done:
                return
            self.done = True
        if self.collected is not None:
            self.collected.end(None, 0.0)


def _joined(
    state: _State, inside: str | None, reason: str | None, seen: _Seen | None
) -> None:
    """Count the call, and give it to the episode it was made in.

    A call made in no episode while one is open in this process is counted an
    orphan, its file says `"orphan": true`, and it is attached to nothing:
    which episode it belongs to, if any, is
    not something the recorder can know, and it never guesses from timing
    (ADR 0058 §5). A call attached by id to an episode that was never open
    here, opened in another process, carries the id, and the import joins
    it. One whose episode this process closed before it ended reaches here
    as `inside=None`: `_ended` marked it an orphan.
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
class _Last(threading.local):
    tenant: str | None = None
    notes: list[str]

    def __init__(self) -> None:
        self.notes = []


_LAST = _Last()


def _tally(
    state: _State,
    tenant: str | None,
    suite: object,
    reason: str | None,
    notes: tuple[str, ...] = (),
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
    shared = state.shared
    with shared.tally_lock:
        if not shared.tallies:
            import atexit

            atexit.register(_flush_shared, shared)
        suites = shared.tallies.setdefault(tenant, {})
        bucket = suites.setdefault(
            name, {"recorded": 0, "not_recorded": {}, "noted": {}}
        )
        for what in notes:
            bucket["noted"][what] = bucket["noted"].get(what, 0) + 1
        shared.dirty.add(tenant)
        if reason is None:
            bucket["recorded"] += 1
            first = tenant not in shared.tallied
        else:
            bucket["not_recorded"][reason] = bucket["not_recorded"].get(reason, 0) + 1
            first = False
    if first:
        _flush_shared(shared, tenant)


def _flush(state: _State, only: str | None = None) -> None:
    """`_flush_shared` for the counts `state`'s client shares."""
    _flush_shared(state.shared, only)


def _flush_shared(shared: _Shared, only: str | None = None) -> None:
    """Write the counts of every tenant counted since the last write, or of
    `only`. At the first recording, at each tick, and at exit. Never raises."""
    with shared.tally_lock:
        tenants = [only] if only is not None else sorted(shared.dirty)
        for tenant in tenants:
            suites = shared.tallies.get(tenant)
            if suites is None:
                continue
            snapshot = {
                suite_name: {
                    "recorded": counts["recorded"],
                    "not_recorded": dict(counts["not_recorded"]),
                    "noted": dict(counts["noted"]),
                }
                for suite_name, counts in suites.items()
            }
            with contextlib.suppress(Exception):
                _write_counts(shared, tenant, snapshot)
                shared.tallied.add(tenant)
                shared.dirty.discard(tenant)


def _write_counts(shared: _Shared, tenant: str, suites: dict[str, Any]) -> None:
    import json

    from digline.store.file_store import (
        COUNTS_FILENAME,
        FileResultStore,
        RecordingWriter,
    )

    with shared.lock:
        if shared.writer is None:
            shared.writer = RecordingWriter(FileResultStore(shared.root))
        writer = shared.writer
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
    slot: _Slot | _Loaded,
    request: Mapping[str, Any],
    reply: Any,
    elapsed_ms: float,
    suite: object,
    variables: object,
    site: str | None,
    inside: str | None,
    *,
    completion: Completion | None = None,
    late: bool = False,
    drawn: bool | None = None,
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

    A streamed call arrives here at its end with its `completion` already
    read from the events, `drawn` as its episode drew when the stream began,
    and `late` where that episode has closed since.

    The response's `input` is the case's `messages` as JSON text
    (`input_of`), the same for a call made, streamed or awaited: the question
    the import puts beside the answer for the judge. A map whose case holds no
    messages records none, and the import says so of its answers.
    """
    try:
        from digline.core.recording import Recording, input_of, setup_digest_of
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
        if drawn is not None:
            if not drawn:
                return "sampled out", None
        elif collector is not None:
            if collector.sampled_out:
                return "sampled out", None
        elif not _sampled_in(switch):
            return "sampled out", None
        if _at_ceiling(state, tenant, switch):
            return "ceiling", None

        stage = "map"
        mapped: RecordingMap = slot.mapped()
        case, setup = mapped.split(request)
        if variables is not None:
            if not isinstance(variables, Mapping):
                return "digline_vars is not a mapping", None
            case = {**case, "vars": dict(cast(Mapping[str, object], variables))}
        if completion is None:
            completion = mapped.completion(reply, request)
        metadata = completion.as_metadata()

        stage = "not JSON"
        digest = setup_digest_of(setup)
        # The question beside the answer, which the import copies into a
        # reviewed answer: the case's messages, not the request's, so the
        # instructions a map moved into the setup stay there.
        question = case.get("messages")
        response = recorded(
            Response(
                output=completion.text,
                input=None if question is None else input_of(question),
                latency_ms=elapsed_ms,
                usage=completion.usage,
                metadata=metadata,
            )
        )
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
            # process now is the one moment the definition can be known. A
            # stream that ended after its episode closed is an orphan too,
            # and keeps the id of the episode it began in.
            orphan=late or (inside is None and bool(_OPEN)),
            recorded_at=_now(),
        )

        stage = "writer"
        _write(state, tenant, recording, RecordingWriter, FileResultStore)
    except Exception:  # noqa: BLE001 — the rule of this module
        return stage, seen
    if completion.usage is None:
        # Recorded without counts, which a recorded response may be: `None` is
        # a target that reported none (`RecordedResponse.usage`). Said, so a
        # stream whose provider gives counts only when asked shows it.
        state.note("usage not reported")
        _LAST.notes.append("usage not reported")
    return None, seen


def _write(state: _State, tenant: str, recording: Any, writer: Any, store: Any) -> None:
    shared = state.shared
    with shared.lock:
        if shared.writer is None:
            shared.writer = writer(store(shared.root))
        made = shared.writer
    path = cast("RecordingWriter", made).write(recording)
    grown = path.stat().st_size
    with state.lock:
        state.sizes[tenant] = state.sizes.get(tenant, 0) + grown


def _tenant_of(state: _State) -> str | None:
    """The tenant of this call: the name given, or the function's answer.
    `None` where the function gave no name; its exception propagates to the
    caller's stage."""
    tenant = state.tenant() if callable(state.tenant) else state.tenant
    # A function's answer that is not a name is no tenant: it never becomes
    # a directory, and the call is not recorded, counted `tenant`.
    if not _a_name(tenant):
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
    process; where it was opened in another, the import joins them by the id.
    A call that ends after its episode closed in this process is recorded
    with the id, marked an orphan, and noted `ended after its episode`.
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

    async def __aenter__(self) -> None:
        self.__enter__()

    async def __aexit__(self, *exc: object) -> None:
        self.__exit__(*exc)


def _reset(token: Token[str | None] | None) -> None:
    """Undo a `set`, where it can be undone: a context left in another
    context than the one it entered cannot be, and the application never
    hears of it."""
    if token is None:
        return
    with contextlib.suppress(ValueError):
        _CURRENT.reset(token)


#: The keys of a response's metadata that say what its calls were. Where a
#: collection is read, they are its own and the target's are dropped: a target
#: that returns its last call's response reports its last call alone.
_TRAJECTORY_KEYS = frozenset(
    {
        "finish",
        "finish_raw",
        "tools",
        "tool_calls",
        "steps",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    }
)

#: What a collection's latency is, said beside it wherever it is read.
_COLLECTED_LATENCY = "model calls only, tool time excluded"

#: Why a collection's cost is not known, where nothing priced it.
_NO_PRICE_LIST = (
    "calls collected through a wrapped client: counts read, no price list "
    "declared by the target"
)


@contextlib.contextmanager
def collecting(
    *,
    price: Callable[[Completion], tuple[float | None, str | None]] | None = None,
) -> Generator[Callable[[Response], Response]]:
    """Collect the calls a run's target makes through wrapped clients, and
    settle its response with them. (ADR 0060 §3)

    What `digline.host` passes as `execute(around_target=...)`, entered
    around each call of the target and left before the assertions run, so a
    judge's calls are never the agent's. A library caller that runs
    `execute()` itself passes it the same way:

        execute(suite, target, ..., around_target=digline.recorder.collecting)

    Every call made inside it through a client `wrap()` returned is read with
    the plugin's map, recorder on or off: off, nothing is written, and an
    `episode()` the application opens is the empty context it always is, its
    calls collected all the same. A stream is collected when it ends.

    **`settle`, given on entering, composes the response.** Where no call was
    made through a wrapped client, it returns the response as it came: the
    target's own `as_metadata()` is what the assertions read, as before. Where
    calls were made, the collection wins, so a provider target whose client is
    wrapped is not counted twice:

    - `steps`, by `steps_of`, and `tools` and `tool_calls` from the steps;
      `finish` and `finish_raw` from the last call;
    - `usage`, summed, and the four counts in `metadata` with it;
    - `latency_ms`, summed: **the time spent waiting for the model, excluding
      the time the tools took.** It is not the duration of the case, so a
      `LatencyBudget` on a target that wraps its client measures the model's
      time;
    - `cost_usd` by `price`, each call at the model it reports; `None` with
      `unpriced` saying why where `price` is `None`, which is a function
      target's case, or where any call cannot be priced: a partial cost is not
      a cost;
    - `metadata["collected"]`: `calls`, how many were made, and `latency`,
      which says what the latency is.

    **Incomplete is said, never filled in.** A call that could not be read, or
    a stream the target returned before its end, leaves the collection
    incomplete: then there are no steps, no trajectory, no counts, no latency
    and no cost, and `metadata["collected"]["unread"]` says how many calls
    were not read. A check that needs steps then errors, and never fails on
    what was not seen.

    **Limits.** A collection is a context variable: it does not reach a
    `threading.Thread` or a `ThreadPoolExecutor` worker, and `attach(id)` does
    not carry it.
    """
    collected = _Collected()
    token = _COLLECTING.set(collected)
    try:
        yield lambda response: _settled(collected, response, price)
    finally:
        with contextlib.suppress(ValueError):
            _COLLECTING.reset(token)
        collected.close()


@contextlib.contextmanager
def running() -> Generator[None]:
    """Mark the context as a run's: what `digline.host` enters around
    `execute()`, so that no call made inside it, by the target or by a judge,
    through a client `wrap()` returned, is written as a recording or moves a
    client's counts. A run's calls are the gate's, and recorded they were
    filed under whatever suite the call site named, as if the application had
    made them. `collecting()` still reads the target's calls inside it.

        with digline.recorder.running():
            run = execute(suite, target, ..., around_target=collecting)
    """
    token = _RUNNING.set(True)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            _RUNNING.reset(token)


def _settled(
    collected: _Collected,
    response: Response,
    price: Callable[[Completion], tuple[float | None, str | None]] | None,
) -> Response:
    """The target's response, with what its collection read. `collecting()`
    says the rules."""
    from dataclasses import replace

    from digline.core.run import steps_as_reported

    with collected.lock:
        calls = list(collected.calls)
        unread = collected.missed + collected.pending
    if not calls and not unread:
        return response
    metadata = {
        key: value
        for key, value in response.metadata.items()
        if key not in _TRAJECTORY_KEYS
    }
    said: dict[str, object] = {
        "calls": len(calls) + unread,
        "latency": _COLLECTED_LATENCY,
    }
    if unread:
        said["unread"] = unread
        metadata["collected"] = said
        return replace(
            response,
            metadata=metadata,
            usage=None,
            cost_usd=None,
            latency_ms=None,
            unpriced=None,
        )
    metadata["collected"] = said
    last = calls[-1][0]
    if last.finish is not None:
        metadata["finish"] = last.finish
    if last.finish_raw is not None:
        metadata["finish_raw"] = last.finish_raw
    steps = steps_as_reported(
        [
            (
                completion.finish,
                None
                if completion.tool_calls is None
                else [call.as_reported() for call in completion.tool_calls],
            )
            for completion, _ in calls
        ]
    )
    if steps is not None:
        metadata["steps"] = steps
        called = [step for step in steps if step["actor"] == "tool"]
        metadata["tools"] = [step["tool"] for step in called]
        metadata["tool_calls"] = [
            {key: value for key, value in step.items() if key not in ("index", "actor")}
            for step in called
        ]
    counts = [completion.usage for completion, _ in calls]
    usage: Usage | None = None
    if all(count is not None for count in counts):
        for count in counts:
            if count is not None:
                usage = count if usage is None else usage + count
    cost: float | None = None
    unpriced: str | None = None
    if usage is not None:
        metadata.update(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )
        cost, unpriced = _priced([completion for completion, _ in calls], price)
    return replace(
        response,
        metadata=metadata,
        usage=usage,
        cost_usd=cost,
        latency_ms=sum(elapsed for _, elapsed in calls),
        unpriced=unpriced,
    )


def _priced(
    calls: list[Completion],
    price: Callable[[Completion], tuple[float | None, str | None]] | None,
) -> tuple[float | None, str | None]:
    """The collection's cost, or `None` and why: every call priced, or no
    cost at all."""
    if price is None:
        return None, _NO_PRICE_LIST
    total = 0.0
    for completion in calls:
        cost, why = price(completion)
        if cost is None:
            return None, why or _NO_PRICE_LIST
        total += cost
    return total, None


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
    - **steps**, the response's, as a single call's are (ADR 0060 §6): one
      `model` step per call, with the finish its reply reported, followed by a
      `tool` step per tool call it asked for. A tool's result is not visible
      to the wrapper — it is the application's, sent in the next request — so
      a tool step's result is absent and says `not_reported`, never filled
      in. A nested episode's steps are spliced in where it closed. Where
      nothing inside it was recorded, the response carries no steps: absent
      is *not recorded*, never an empty list. Its `finish` is the last model
      step's, and its `tools` the tool steps' names in order, as a run reads
      them live;

    Over `MAX_RECORDED_CHARS`, whole or nothing as a run's recorded response
    is: the response says `oversize` and carries no steps, which carry the
    calls' arguments.

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
        "_from_first_call",
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
        #: Read off the wire with no case given: the case is the first call's.
        self._from_first_call = False

    def output(self, result: object) -> None:
        """The turn's final output, as the application gives it. The last one
        given is the one recorded."""
        if self._state.any_on:
            self._output = (result,)

    def __enter__(self) -> Episode:
        # Inside a run it is the empty context it is when the recorder is off:
        # a run's calls are not the application's traffic. (`running()`)
        if not self._state.any_on or _COLLECTING.get() is not None or _RUNNING.get():
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
            _CLOSED[self.id] = None
            if len(_CLOSED) > _CLOSED_KEPT:
                del _CLOSED[next(iter(_CLOSED))]
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

    async def __aenter__(self) -> Episode:
        """`async with`, the same as `with`: the id is a context variable,
        and every task the block creates inherits it. (ADR 0058 §5)"""
        return self.__enter__()

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.__exit__(kind, exc, traceback)


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
    `case` are the same case at the import, and the case, as JSON text, is
    the recorded answer's `input`: the question the import puts beside the
    turn's answer for the judge. `suite=` names the suite, as
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
    imported here and not at the top: off, this module imports nothing of
    digline's. (ADR 0058 §10, as amended 2026-11-03)"""
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
    here raises, and each stage is its reason.

    The response's `input` is the episode's whole case as JSON text
    (`input_of`), never a call's messages: the answer is the turn's, so its
    question is what started the turn. The first call's messages may be a
    step the turn makes on its way, a later one's carry the tools' results,
    and an episode may answer with no model call at all; the case is given,
    and is what the import groups the turn's answers by. Counted against the
    ceiling with the text and the trajectory, whole or nothing."""
    stage = "unexpected"
    try:
        from digline.core.recording import Recording, input_of, setup_digest_of
        from digline.core.run import (
            MAX_RECORDED_CHARS,
            RecordedResponse,
            record_output,
            steps_of,
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
        question = input_of(dict(ep._case))  # pyright: ignore[reportPrivateUsage]

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

        steps = steps_of((seen.finish, seen.calls) for seen in calls)
        # A call whose plugin said nothing about tools: the episode cannot say
        # what was called either.
        trajectory: list[RecordedToolCall] | None = (
            None
            if any(seen.calls is None for seen in calls)
            else [call for seen in calls for call in seen.calls or ()]
        )
        oversize = (
            len(text) > MAX_RECORDED_CHARS
            or len(question) > MAX_RECORDED_CHARS
            or trajectory_chars(trajectory or ()) > MAX_RECORDED_CHARS
        )
        response = (
            RecordedResponse(oversize=True, latency_ms=elapsed_ms)
            if oversize
            else RecordedResponse(
                output=text,
                kind=kind,
                input=question,
                latency_ms=elapsed_ms,
                tool_calls=None if trajectory is None else tuple(trajectory),
                # The response's, as a single call's are (ADR 0060 §6). Over
                # the ceiling there are none: the steps carry the calls'
                # arguments, so they go with the text (ADR 0015 §3).
                steps=tuple(steps) or None,
                # Read off the steps, as a run's collection reads them live
                # (`_settled`): why the turn ended is its last model step's
                # finish, and the names are its tool steps', one per call in
                # order, where every call said what it called. (ADR 0057; ADR
                # 0058 §5, §7)
                finish=_last_finish(steps),
                tools=None
                if trajectory is None
                else tuple(
                    step.call.tool
                    for step in steps
                    if step.actor == "tool" and step.call is not None
                ),
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
            interrupted=interrupted,
            unrecorded_children=collector.children_unrecorded(),
            id=ep.id,
            recorded_at=_now(),
            case_from_first_call=ep._from_first_call,  # pyright: ignore[reportPrivateUsage]
        )

        stage = "writer"
        _write(state, tenant, recording, RecordingWriter, FileResultStore)
    except Exception:  # noqa: BLE001 — the rule of this module
        return stage
    return None


def _last_finish(steps: Any) -> str | None:
    """The finish of the last model step: why the turn ended. `None` where it
    reported none, and never an earlier step's, which ended another reply."""
    models = [step for step in steps if step.actor == "model"]
    return models[-1].finish if models else None


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


def _find(client: object) -> dict[str, Any]:
    """The tree of methods to intercept on `client`: every entry point a
    plugin declares for the first of its classes that has any, by path."""
    declared: dict[str, list[tuple[Any, tuple[str, ...]]]] = {}
    for entry in entry_points(group=MAP_GROUP):
        kind, colon, method = entry.name.partition(":")
        path = tuple(part for part in method.split(".") if part)
        if colon and kind and path:
            declared.setdefault(kind, []).append((entry, path))
    for key in _key_of(client):
        if key in declared:
            tree: dict[str, Any] = {}
            for entry, path in declared[key]:
                node = tree
                for part in path[:-1]:
                    node = node.setdefault(part, {})
                node[path[-1]] = _Slot(entry)
            return tree
    named = ", ".join(sorted(declared)) or "none"
    raise RecorderStartError(
        f"no installed plugin records a client of type {_key_of(client)[0]}. "
        f"The plugins installed record: {named}"
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
    if not callable(tenant) and not _a_name(tenant):
        # The store's sentence: a tenant is a directory, and one that is not a
        # name would read a switch file wherever it led. (GHSA-j878-2v6m-m4vx)
        raise RecorderStartError(
            f"invalid tenant name: {tenant[:40]!r} "
            "(letters, digits, dot, dash and underscore are allowed)"
        )
    tree = _find(client)
    state = _State(
        app=app,
        tenant=tenant,
        root=Path(root) if root is not None else Path.cwd(),
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
    if state.any_on:
        _ready(tree)
    state.next_look = _clock() + state.interval
    return RecordedClient(client, tree, state)


#: What a recording imports the first time, by name: the standard library's
#: modules this one imports where it uses them, and digline's own.
_AT_THE_FIRST_RECORDING = (
    "atexit",
    "inspect",
    "json",
    "random",
    "weakref",
    "digline.core.recording",
    "digline.core.run",
    "digline.host.environment",
    "digline.run.driver",
    "digline.store.file_store",
)


def _ready(tree: Mapping[str, Any]) -> None:
    """What the first recording would import, imported now, at the start: the
    core, the store, the host's clock and the maps of the client's methods.
    On at the start, so the first call pays nothing the second does not —
    and, for an asynchronous client, so no call holds the event loop for
    them. Off at the start, nothing: switched on later from the file, the
    first recording pays it, once. (ADR 0058 §10)

    Never raises: what fails to import here fails again at the recording,
    which says why, as a *not recorded*, and the call goes on."""
    import importlib

    for name in _AT_THE_FIRST_RECORDING:
        with contextlib.suppress(Exception):
            importlib.import_module(name)

    def maps(node: Mapping[str, Any]) -> None:
        for value in node.values():
            if isinstance(value, _Slot):
                _map_or_none(value)
            else:
                maps(cast(Mapping[str, Any], value))

    maps(tree)


#: The entry-point group of the plugins' readers of a call off the wire, one
#: entry per route (ADR 0062 §3).
WIRE_GROUP = "digline.recording_wire"


class _Loaded:
    """A map already loaded, where `_record` takes a `_Slot`: the proxy loads
    every reader when it starts, never at a call."""

    __slots__ = ("map",)

    def __init__(self, mapped: Any) -> None:
        self.map = mapped

    def mapped(self) -> Any:
        return self.map


class _WireEpisode:
    """An episode the proxy is gathering: the calls that carried one
    `X-Digline-Episode`, until none came for the idle interval."""

    __slots__ = (
        "carried",
        "case",
        "collector",
        "first",
        "from_first_call",
        "id",
        "last",
        "last_end",
        "site",
        "state",
        "suite",
    )

    def __init__(
        self,
        *,
        id: str,  # noqa: A002 — the episode's id
        state: _State,
        suite: str | None,
        case: Mapping[str, object],
        from_first_call: bool,
        site: str | None,
        drawn: bool,
        started: float,
    ) -> None:
        self.id = id
        self.state = state
        self.suite = suite
        self.case = case
        self.from_first_call = from_first_call
        self.site = site
        self.collector = _Collector(sampled_out=not drawn)
        #: Each call, in the order it ended: what it added to the episode,
        #: `None` where it was not recorded, and the tool results its request
        #: carried for the call before, `None` where it carried none.
        self.carried: list[tuple[_Seen | None, Sequence[ToolCall] | None]] = []
        self.first = started
        self.last = _clock()
        self.last_end = started


class WireRecorder:
    """The recorder `digline record proxy` records with: what `wrap` builds
    for a client, built for none, for one tenant named, which is development
    (ADR 0058 §4). The same switch file read the same way, at the same
    interval, the same writer, the same digest and the same counts file: the
    proxy is a Python process like any that wraps a client, and `digline
    record status` reads it as one. (ADR 0062 §3)

    **One state per app** the calls name, `X-Digline-App` or `app`, all under
    one root, so they share the writer and the process's directory, as two
    clients wrapped in one process do.

    **An episode off the wire** is the calls that carried one
    `X-Digline-Episode`, closed once none came for `episode_idle` seconds,
    or when the proxy stops, and then written as an episode is. Its id is the
    first 32 hexadecimal characters of the SHA-256 of the header's value, so
    one value gives one id in every process; a value used again after its
    episode closed opens another, whose id is taken from the value and how
    many came before it. Its case is the one `X-Digline-Case` gave, or the
    first call's, and then the recording says `case_from_first_call`. Its
    answer is the last call's text. It is never `interrupted`: an exception
    in the application does not cross the wire.

    Nothing here raises at a call, by this module's rule: what goes wrong is
    counted, by reason.
    """

    def __init__(
        self, *, tenant: str, app: str, root: Path, episode_idle: float
    ) -> None:
        if not isinstance(tenant, str) or not tenant:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise RecorderStartError("the proxy needs --tenant, a non-empty name")
        if not isinstance(app, str) or not app:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise RecorderStartError("the proxy needs an app name, a non-empty one")
        self.tenant = tenant
        self.app = app
        self.root = root
        self.episode_idle = episode_idle
        self._lock = threading.Lock()
        self._states: dict[str, _State] = {}
        self._episodes: dict[str, _WireEpisode] = {}
        self._opened: dict[str, int] = {}
        self._inflight: dict[str, int] = {}
        # Read before the files, as `wrap` does: a value that is neither on
        # nor off is refused.
        _switched_on()
        self._state(app)

    def _state(self, app: str | None) -> _State:
        name = app or self.app
        with self._lock:
            state = self._states.get(name)
            if state is None:
                state = _State(app=name, tenant=self.tenant, root=self.root)
                _read_switches(state, starting=True)
                _measure(state)
                state.next_look = _clock() + state.interval
                self._states[name] = state
        if _clock() >= state.next_look:
            _look(state)
        return state

    @property
    def switch(self) -> Switch | None:
        """The tenant's switch as the proxy read it, `None` where no file and
        no `DIGLINE_RECORD=1` switched it."""
        return self._state(None).switches.get(self.tenant)

    def on(self, app: str | None = None) -> bool:
        """Whether this tenant records now: read at each call, after the look
        the interval asks for."""
        return self._state(app).any_on

    def begin(self, episode: str | None) -> None:
        """A call that carries `episode` has begun: its episode is not idle
        while it lasts."""
        if episode is None:
            return
        with self._lock:
            self._inflight[episode] = self._inflight.get(episode, 0) + 1

    def end(self, episode: str | None) -> None:
        """A call that carried `episode` has ended, recorded or not."""
        if episode is None:
            return
        with self._lock:
            left = self._inflight.get(episode, 1) - 1
            if left > 0:
                self._inflight[episode] = left
            else:
                self._inflight.pop(episode, None)
            found = self._episodes.get(episode)
            if found is not None:
                found.last = _clock()

    def record(
        self,
        mapped: RecordingMap,
        request: Mapping[str, Any],
        *,
        reply: Any = None,
        completion: Completion | None = None,
        elapsed_ms: float,
        suite: str | None,
        app: str | None,
        site: str | None,
        episode: str | None,
        case: Mapping[str, object] | None,
        results: Sequence[ToolCall] | None = None,
    ) -> None:
        """One call that ended with a reply: recorded, or said why not, and
        counted. A streamed one arrives with its `completion` already read.
        `results` are the tool results its request carried for the call
        before it, which close that call's tool steps in its episode."""
        try:
            state = self._state(app)
            if not state.any_on:
                return
            _LAST.tenant = self.tenant
            _LAST.notes = []
            slot = _Loaded(mapped)
            if episode is None:
                reason, _ = _record(
                    state,
                    slot,
                    request,
                    reply,
                    elapsed_ms,
                    suite,
                    None,
                    site,
                    None,
                    completion=completion,
                )
            else:
                found = self._episode(
                    state, episode, suite, site, case, mapped, request, elapsed_ms
                )
                reason, seen = _record(
                    state,
                    slot,
                    request,
                    reply,
                    elapsed_ms,
                    suite,
                    None,
                    site,
                    found.id,
                    completion=completion,
                    drawn=not found.collector.sampled_out,
                )
                found.collector.add(seen)
                with self._lock:
                    found.carried.append((seen, results))
                found.last_end = perf_counter()
            state.count(reason)
            _tally(state, _LAST.tenant, suite, reason, tuple(_LAST.notes))
        except Exception:  # noqa: BLE001 — the rule of this module
            return
        finally:
            self.end(episode)

    def missed(
        self, reason: str, *, suite: str | None, app: str | None, episode: str | None
    ) -> None:
        """A call that was not recorded, said by its reason: a stream the
        application closed before its end is `stream abandoned`, as in
        process. In its episode it is a child that was not recorded."""
        try:
            state = self._state(app)
            if not state.any_on:
                return
            if episode is not None:
                with self._lock:
                    found = self._episodes.get(episode)
                if found is not None:
                    found.collector.add(None)
                    with self._lock:
                        found.carried.append((None, None))
            state.count(reason)
            _tally(state, self.tenant, suite, reason)
        except Exception:  # noqa: BLE001 — the rule of this module
            return
        finally:
            self.end(episode)

    def _episode(
        self,
        state: _State,
        key: str,
        suite: str | None,
        site: str | None,
        case: Mapping[str, object] | None,
        mapped: RecordingMap,
        request: Mapping[str, Any],
        elapsed_ms: float,
    ) -> _WireEpisode:
        import hashlib

        with self._lock:
            found = self._episodes.get(key)
            if found is not None:
                return found
            opened = self._opened.get(key, 0)
            self._opened[key] = opened + 1
        seed = key if opened == 0 else f"{key}\n{opened}"
        given = case
        if given is None:
            given = mapped.split(request)[0]
        found = _WireEpisode(
            id=hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32],
            state=state,
            suite=suite,
            case=given,
            from_first_call=case is None,
            site=site if suite is None else None,
            drawn=_episode_sampled_in(state),
            started=perf_counter() - elapsed_ms / 1000.0,
        )
        with self._lock:
            # Two first calls at once: the first to arrive is the episode.
            return self._episodes.setdefault(key, found)

    def close_idle(self) -> None:
        """Write every episode that has had no call for the idle interval."""
        now = _clock()
        with self._lock:
            idle = [
                key
                for key, found in self._episodes.items()
                if key not in self._inflight and now - found.last >= self.episode_idle
            ]
            closing = [self._episodes.pop(key) for key in idle]
        for found in closing:
            self._close(found)

    def close(self) -> None:
        """The proxy stops: every open episode is written, and the counts."""
        with self._lock:
            closing = list(self._episodes.values())
            self._episodes.clear()
            states = list(self._states.values())
        for found in closing:
            self._close(found)
        for state in states:
            _flush(state)

    def _close(self, found: _WireEpisode) -> None:
        state = found.state
        try:
            if found.collector.sampled_out:
                state.count("sampled out")
                _tally(state, self.tenant, found.suite, "sampled out")
                return
            _close_tool_steps(found.carried)
            written = Episode(state, found.suite, found.case, None, found.site)
            written.id = found.id
            written._collector = found.collector  # pyright: ignore[reportPrivateUsage]
            written._from_first_call = found.from_first_call  # pyright: ignore[reportPrivateUsage]
            _LAST.tenant = self.tenant
            reason = _record_episode(
                written,
                found.collector,
                (found.last_end - found.first) * 1000.0,
                interrupted=False,
            )
            state.count(reason)
            _tally(state, _LAST.tenant, found.suite, reason)
        except Exception:  # noqa: BLE001 — the rule of this module
            return


def _close_tool_steps(
    carried: Sequence[tuple[_Seen | None, Sequence[ToolCall] | None]],
) -> None:
    """The tool steps of each call, closed by the results the next call's
    request carried: what the wire sees that a call in process does not. A
    call in process ends where the tool starts, so its tool steps say
    `not_reported`; off the wire, the application's next call sends the
    tool's result back to the model, and that is the step's result.
    (ADR 0062 §3)

    Only where the next call is the very next one the episode saw, both
    recorded, and the results name the same tools in the same order as the
    calls the step before asked for: a result is never put on a step it may
    not be the answer to. What the tool said of itself is its status where
    the provider carries one (`error`, `success`), and `not_reported` where it
    does not. The steps' places, tools and arguments do not move."""
    import dataclasses

    for (before, _), (after, results) in itertools.pairwise(carried):
        if before is None or after is None or results is None or not before.calls:
            continue
        if tuple(call.tool for call in before.calls) != tuple(
            result.tool for result in results
        ):
            continue
        before.calls = tuple(
            dataclasses.replace(
                call,
                result=result.result,
                status=result.status,
                result_absence=result.result_absence,
            )
            for call, result in zip(before.calls, results, strict=True)
        )
