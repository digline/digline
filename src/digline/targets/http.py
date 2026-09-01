"""A target that calls an HTTP endpoint, for an application digline cannot import.

Friction 14: most applications worth evaluating are not Python. A JVM service, a
Go binary, something behind a gateway — the target is always "post a body, read
a field out of the answer", and every suite was writing those twenty lines
again.

`urllib` and nothing else: digline has one runtime dependency and this is not
where it acquires a second. If you need retries, connection pooling or auth
flows, pass your own callable as the target — that is what the protocol is for.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from time import perf_counter
from typing import Any, cast

from digline.core import ConfigValue, Output
from digline.run import Case, Response
from digline.targets.config import declared_config

__all__ = ["HttpTarget"]


def _dig(payload: object, path: str) -> object:
    """`data.answer.text` out of a decoded JSON body.

    Dotted, not a query language: a path that needs more than dots is a
    transformation, and a transformation belongs in your own callable where you
    can test it.
    """
    current = payload
    for step in path.split("."):
        if not isinstance(current, Mapping):
            raise ValueError(
                f"cannot read {path!r}: {step!r} was looked for in a "
                f"{type(current).__name__}, not an object"
            )
        entries = cast("Mapping[str, object]", current)
        if step not in entries:
            available = ", ".join(sorted(entries)) or "nothing"
            raise ValueError(f"cannot read {path!r}: no {step!r} in {available}")
        current = entries[step]
    return current


class HttpTarget:
    """Post a body built from the case, read the answer out of the response.

        target = HttpTarget(
            "http://localhost:8080/answer",
            request=lambda case: {"question": case.vars["question"]},
            output_path="data.answer",
            cost_path="usage.cost_usd",
            config_path="config",
        )

    The application can be written in anything. What digline needs is a body it
    can post and a field it can read.
    """

    def __init__(
        self,
        url: str,
        *,
        request: Callable[[Case], Mapping[str, object]],
        output_path: str,
        cost_path: str | None = None,
        latency_from_response: str | None = None,
        config_path: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.url = url
        self.request = request
        self.output_path = output_path
        self.cost_path = cost_path
        #: A path, not a flag: where in the answer the application reports the
        #: time it spent. Left `None`, the duration is measured here instead —
        #: which includes the network, and says so.
        self.latency_from_response = latency_from_response
        #: Symmetric with `cost_path`, and for the same reason: the model call
        #: happened on the other side of HTTP, so the only one who can say which
        #: model answered and how it was set up is the application. Left `None`,
        #: the target declares nothing — which is what it has always done, and
        #: absent is not a change (ADR 0005 §6, §8).
        self.config_path = config_path
        self.headers = dict(headers or {})
        self.timeout = timeout
        #: Learned from the answers rather than declared at construction, so it
        #: is empty until the first case has been answered. `execute()` reads it
        #: after the last one for exactly this reason.
        self._config: dict[str, ConfigValue] = {}

    @property
    def config(self) -> Mapping[str, ConfigValue]:
        """What the application said about the model that answered.

        Satisfies `HasConfig`, so `execute()` records it like any plugin's — and
        empty when no `config_path` was given, which reads as "this target
        declares nothing" exactly as a plain function does.
        """
        return dict(self._config)

    def _record(self, found: object) -> None:
        """Keep the first configuration reported, and hold every later answer
        to it.

        A target is bound once per run (ADR 0005 §6), and an endpoint that
        answers case 1 on one model and case 7 on another is not one system
        being measured. Recording either would be a fact nobody established, and
        merging them would describe a set-up nobody built — so the disagreeing
        case is errored, loudly and by name, while the run keeps what the first
        answer said.
        """
        declared = declared_config(found, where=str(self.config_path))
        if not self._config:
            self._config = declared
            return
        moved = sorted(
            key
            for key in set(self._config) | set(declared)
            if self._config.get(key) != declared.get(key)
        )
        if moved:
            changes = ", ".join(
                f"{k}: {self._config.get(k)!r} then {declared.get(k)!r}" for k in moved
            )
            raise ValueError(
                f"{self.url} answered under a different configuration part way "
                f"through the run ({changes}). One run measures one system, so "
                "there is no single configuration to record: pin the "
                "application's model and parameters for the run, or evaluate "
                "each set-up as its own run"
            )

    def preflight(self, cases: Sequence[Case]) -> None:
        """Is anything listening?

        Asked before the first case, because the alternative is discovering that
        the service is down one case at a time, with a run half written. It does
        not check behaviour — only that the address answers at all. A status
        code is an answer: a 404 or a 405 means something is there and the
        request was wrong, which is a different problem from nothing being there.
        """
        probe = urllib.request.Request(self.url, method="HEAD")
        try:
            with urllib.request.urlopen(probe, timeout=self.timeout):
                return
        except urllib.error.HTTPError:
            return
        except OSError as exc:
            raise ValueError(
                f"nothing answered at {self.url}: {exc}. The suite declares "
                f"{len(cases)} case(s) and every one of them would fail the "
                "same way — start the application, or point the target at it"
            ) from exc

    def __call__(self, case: Case) -> Response:
        sent = json.dumps(dict(self.request(case)), sort_keys=True)
        headers = {"Content-Type": "application/json", **self.headers}
        posted = urllib.request.Request(
            self.url, data=sent.encode("utf-8"), headers=headers, method="POST"
        )

        started = perf_counter()
        with urllib.request.urlopen(posted, timeout=self.timeout) as answer:
            raw = answer.read().decode("utf-8")
        elapsed_ms = (perf_counter() - started) * 1000.0

        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self.url} answered something that is not JSON: {raw[:120]!r}"
            ) from exc

        found = _dig(payload, self.output_path)
        if not isinstance(found, str | Mapping | Sequence):
            raise ValueError(
                f"{self.output_path!r} holds a {type(found).__name__}, which "
                "is not an Output"
            )
        output = cast("Output", found)
        cost = (
            None
            if self.cost_path is None
            else float(_as_number(_dig(payload, self.cost_path), self.cost_path))
        )
        latency = elapsed_ms
        if self.latency_from_response is not None:
            latency = _as_number(
                _dig(payload, self.latency_from_response), self.latency_from_response
            )
        # Read on every answer, not only the first: an endpoint that changes
        # model mid-run has to be caught, and the only way to catch it is to
        # keep asking. (ADR 0005 §8)
        if self.config_path is not None:
            self._record(_dig(payload, self.config_path))
        return Response(
            output=output,
            # What was sent, not what came back: `input` is the question a judge
            # is shown, and the answer is already in `output`.
            input=sent,
            cost_usd=cost,
            latency_ms=latency,
        )


def _as_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path!r} holds {value!r}, which is not a number")
    return float(value)
