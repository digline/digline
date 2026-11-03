"""The recorder's wrapper: a provider's client that records the calls an
application makes through it. (ADR 0058 §2, §3, §6, §10)

    client = digline.recorder.wrap(anthropic.Anthropic(), app="support", tenant="acme")
    client.messages.create(model=..., messages=..., suite="triage")

**One call, recorded or let through**, and **an episode**: a context around
one turn of an agent, whose calls are attached to it (§5, §8, §9).

    with digline.recorder.episode(client, suite="support-agent", case={...}) as ep:
        ...  # calls through wrapped clients, tools run by the application
        ep.output(result)

A synchronous client. The switch file and its refusals, the ceiling, the status
command, the import, streaming and asynchronous clients are later pieces of the
same ADR.

**Where it sits.** At the level of `digline.host`, the layer that may read
files, the environment and the clock, and nothing imports it. Not *inside*
`digline.host`, because that package's `__init__` imports the whole host, and
the host imports the core: switched off, the wrapper must not (§10). So this
module imports the standard library alone at the top, and everything of
digline's lazily, at the first call it records.

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

**Switched by the environment alone, in this piece**: `DIGLINE_RECORD=1` is on;
unset, empty or `0` is off. It is read when the client is wrapped. Off, the
wrapper takes digline's two keywords out of the call and passes it through.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from importlib.metadata import entry_points
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from types import TracebackType

    from digline.core.recording import RecordedStep
    from digline.core.run import RecordedToolCall
    from digline.store.file_store import RecordingWriter
    from digline.targets import Completion

__all__ = [
    "ENVIRONMENT_VARIABLE",
    "MAP_GROUP",
    "UNASSIGNED",
    "RecordedClient",
    "RecorderStartError",
    "Episode",
    "RecordingMap",
    "attach",
    "episode",
    "wrap",
]

#: The variable that switches recording on for this process, read when a
#: client is wrapped. The switch file is a later piece (ADR 0058 §10).
ENVIRONMENT_VARIABLE = "DIGLINE_RECORD"

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
        on: bool,
        app: str,
        tenant: str | Callable[[], str],
        root: Path,
        entry: Any,
    ) -> None:
        self.on = on
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
    where it closed.
    """

    def __init__(self) -> None:
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
        if not state.on:
            return method(*args, **kwargs)
        inside = _CURRENT.get()
        if kwargs.get("stream"):
            _joined(state, inside, "streaming", None)
            return method(*args, **kwargs)
        if args:
            _joined(state, inside, "positional arguments", None)
            return method(*args, **kwargs)
        site = _call_site() if suite is None else None
        started = perf_counter()
        reply = method(**kwargs)
        elapsed_ms = (perf_counter() - started) * 1000.0
        reason, seen = _record(
            state, kwargs, reply, elapsed_ms, suite, variables, site, inside
        )
        _joined(state, inside, reason, seen)
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
    """
    try:
        from digline.core.recording import Recording, setup_digest_of
        from digline.core.run import record_trajectory
        from digline.run.driver import Response, recorded
        from digline.store.file_store import FileResultStore, RecordingWriter
    except Exception as exc:  # noqa: BLE001 — the rule of this module
        return f"unexpected: {type(exc).__name__}", None

    stage = "map"
    try:
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
        stage = "tenant"
        tenant = state.tenant() if callable(state.tenant) else state.tenant
        if not isinstance(tenant, str) or not tenant:  # pyright: ignore[reportUnnecessaryIsInstance]
            return stage, seen

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
        )

        stage = "writer"
        _write(state, recording, RecordingWriter, FileResultStore)
    except Exception:  # noqa: BLE001 — the rule of this module
        return stage, seen
    return None, seen


def _write(state: _State, recording: Any, writer: Any, store: Any) -> None:
    with state.lock:
        if state.writer is None:
            state.writer = writer(store(state.root))
    cast("RecordingWriter", state.writer).write(recording)


class attach:  # noqa: N801 — read as a function at the call site, like `episode`
    """Put the calls made inside it in the episode `id`. (ADR 0058 §5)

    For a thread or a process that does not inherit the context the episode
    was opened in: a `ThreadPoolExecutor` worker, a `threading.Thread`, a
    process. The id is `ep.id`, passed by the application.

        pool.submit(lambda: run_in(attach(ep.id)))

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
        if self._state.on:
            self._output = (result,)

    def __enter__(self) -> Episode:
        if not self._state.on:
            return self
        self.id = os.urandom(16).hex()
        self._parent = _CURRENT.get()
        self._collector = _Collector()
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
        self._state.count(
            _record_episode(
                self, self._collector, elapsed_ms, interrupted=kind is not None
            )
        )
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
    object is refused, by name, recording or not. `suite=` names the suite; an
    episode that names none is `_unassigned`, with its call site (§2)."""
    if not isinstance(client, RecordedClient):
        raise RecorderStartError(
            "episode() takes a client wrap() returned, so that the episode is "
            "filed under its app and tenant"
        )
    state: _State = client._digline_state  # pyright: ignore[reportPrivateUsage]
    site = _call_site() if state.on and suite is None else None
    return Episode(state, suite, case, setup, site)


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
            from digline.host.environment import git_commit

            setup: dict[str, object] = {"child_setups": sorted(collector.digests())}
            commit = git_commit(state.root)
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
        tenant = state.tenant() if callable(state.tenant) else state.tenant
        if not isinstance(tenant, str) or not tenant:  # pyright: ignore[reportUnnecessaryIsInstance]
            return stage

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
        )

        stage = "writer"
        _write(state, recording, RecordingWriter, FileResultStore)
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
    """The client, recording its calls when `DIGLINE_RECORD=1`.

    `tenant` is a name, or a function called at every recording whose value is
    the recording's `source_tenant` and the directory it is filed under (ADR
    0058 §4). `root` is the directory that holds `.digline/`, the current
    directory when this is called if not given.
    """
    if not isinstance(app, str) or not app:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise RecorderStartError("wrap() needs app=, a non-empty name")
    if not callable(tenant) and (not isinstance(tenant, str) or not tenant):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise RecorderStartError(
            "wrap() needs tenant=, a non-empty name or a function that returns one"
        )
    entry, path = _find(client)
    state = _State(
        on=_switched_on(),
        app=app,
        tenant=tenant,
        root=Path(root) if root is not None else Path.cwd(),
        entry=entry,
    )
    return RecordedClient(client, path, state)
