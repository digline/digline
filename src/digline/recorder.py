"""The recorder's wrapper: a provider's client that records the calls an
application makes through it. (ADR 0058 §2, §3, §6, §10)

    client = digline.recorder.wrap(anthropic.Anthropic(), app="support", tenant="acme")
    client.messages.create(model=..., messages=..., suite="triage")

**One call, recorded or let through.** This is the narrow piece: a synchronous
client, one call at a time. An episode, the switch file and its refusals, the
ceiling, the status command and the import are later pieces of the same ADR.

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

import os
import threading
from collections.abc import Callable, Mapping
from importlib.metadata import entry_points
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from digline.store.file_store import RecordingWriter
    from digline.targets import Completion

__all__ = [
    "ENVIRONMENT_VARIABLE",
    "MAP_GROUP",
    "UNASSIGNED",
    "RecordedClient",
    "RecorderStartError",
    "RecordingMap",
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
        self.map: RecordingMap | None = None
        self.writer: RecordingWriter | None = None

    def count(self, reason: str | None) -> None:
        with self.lock:
            if reason is None:
                self.recorded += 1
            else:
                self.not_recorded[reason] = self.not_recorded.get(reason, 0) + 1


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
        """`{"recorded": n, "not_recorded": {reason: n, ...}}`, as of now."""
        state: _State = self._digline_state
        with state.lock:
            return {
                "recorded": state.recorded,
                "not_recorded": dict(state.not_recorded),
            }


def _intercepted(method: Callable[..., Any], state: _State) -> Callable[..., Any]:
    def call(*args: Any, **kwargs: Any) -> Any:
        suite = kwargs.pop(_SUITE, None)
        variables = kwargs.pop(_VARS, None)
        if not state.on:
            return method(*args, **kwargs)
        if kwargs.get("stream"):
            state.count("streaming")
            return method(*args, **kwargs)
        if args:
            state.count("positional arguments")
            return method(*args, **kwargs)
        site = _call_site() if suite is None else None
        started = perf_counter()
        reply = method(**kwargs)
        elapsed_ms = (perf_counter() - started) * 1000.0
        state.count(_record(state, kwargs, reply, elapsed_ms, suite, variables, site))
        return reply

    return call


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
) -> str | None:
    """Record one call, or say why not. `None` is *recorded*.

    Nothing here may raise: each stage is its own reason, and digline's own
    imports failing is `unexpected: <type>`. The reasons name a stage and
    never quote a value, because a value is the application's payload.
    """
    try:
        from digline.core.recording import Recording, setup_digest_of
        from digline.run.driver import Response, recorded
        from digline.store.file_store import FileResultStore, RecordingWriter
    except Exception as exc:  # noqa: BLE001 — the rule of this module
        return f"unexpected: {type(exc).__name__}"

    stage = "map"
    try:
        if state.map is None:
            state.map = state.entry.load()
        mapped: RecordingMap = state.map  # pyright: ignore[reportAssignmentType]
        case, setup = mapped.split(request)
        if variables is not None:
            if not isinstance(variables, Mapping):
                return "digline_vars is not a mapping"
            case = {**case, "vars": dict(cast(Mapping[str, object], variables))}
        completion = mapped.completion(reply, request)
        response = recorded(
            Response(
                output=completion.text,
                latency_ms=elapsed_ms,
                usage=completion.usage,
                metadata=completion.as_metadata(),
            )
        )

        stage = "tenant"
        tenant = state.tenant() if callable(state.tenant) else state.tenant
        if not isinstance(tenant, str) or not tenant:  # pyright: ignore[reportUnnecessaryIsInstance]
            return stage

        stage = "not JSON"
        recording = Recording(
            source_tenant=tenant,
            app=state.app,
            suite=suite if isinstance(suite, str) and suite else UNASSIGNED,
            case=case,
            setup=setup,
            setup_digest=setup_digest_of(setup),
            response=response,
            call_site=site,
        )

        stage = "writer"
        if state.writer is None:
            state.writer = RecordingWriter(FileResultStore(state.root))
        state.writer.write(recording)
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
