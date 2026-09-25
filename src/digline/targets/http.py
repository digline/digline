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

import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from time import perf_counter
from typing import Any, cast
from urllib.parse import urlsplit

from digline.core import ConfigValue, Output, Usage
from digline.run import Case, Response
from digline.targets.completion import ToolCall
from digline.targets.config import (
    declared_config,
    endpoint_host,
    expected_config,
    refuse_config_mismatch,
)

__all__ = ["USAGE_FIELDS", "HttpTarget"]

#: What `urlopen` can raise about an endpoint. `OSError` covers the network;
#: `http.client.HTTPException` is where `InvalidURL` lives and is **not** an
#: `OSError`; `ValueError` is what a malformed URL raises before any socket is
#: opened. All three can quote the URL, which is why they are caught together
#: and answered through `_spoken`.
_ENDPOINT_ERRORS = (OSError, http.client.HTTPException, ValueError)


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


#: What a leaf has to start with to be a reference into the case rather than a
#: literal. One level, no expressions: ADR 0007 §5 draws the line here on
#: purpose, and `request=` is what a computed body remains for.
REFERENCE = "case."

#: The case fields a body may read. `context` and `metadata` are here because a
#: retrieval-augmented endpoint is posted its context, and `label` is not,
#: because a body carrying the answer would be posting the mark to the thing
#: being marked.
READABLE = ("id", "vars", "expected", "context", "metadata")


def check_references(body: Mapping[str, object], *, at: str = "body") -> None:
    """Refuse a reference nothing can resolve, at construction.

    A path that names no case field would otherwise fail once per case, during
    the run, with the suite already half executed — and the mistake is in the
    file, so it belongs to load time.
    """
    for key, value in body.items():
        where = f"{at}.{key}"
        if isinstance(value, Mapping):
            check_references(cast("Mapping[str, object]", value), at=where)
        elif isinstance(value, str) and value.startswith(REFERENCE):
            _check_path(value, where)


def _check_path(reference: str, where: str) -> None:
    _, _, path = reference.partition(REFERENCE)
    head, _, rest = path.partition(".")
    if head not in READABLE:
        raise ValueError(
            f"{where} is {reference!r}, and a case has no {head!r}. "
            f"Readable: {', '.join('case.' + name for name in READABLE)}"
        )
    if head in ("vars", "metadata") and not rest:
        raise ValueError(
            f"{where} is {reference!r}, which names the whole mapping rather "
            f"than a value in it. Write case.{head}.<key>"
        )
    if head not in ("vars", "metadata") and rest:
        raise ValueError(
            f"{where} is {reference!r}: case.{head} is a value, so nothing follows it"
        )


def render_body(body: Mapping[str, object], case: Case) -> dict[str, object]:
    """The declared table, with its references replaced by this case's values.

    The table *is* the payload: nesting, arrays and non-string types survive
    because nothing is being formatted into a string. Only a leaf that starts
    with `case.` is read as a reference, so a literal is anything else — which
    is why a literal string that genuinely starts with "case." cannot be
    written here, and is the one shape this form gives up.
    """
    out: dict[str, object] = {}
    for key, value in body.items():
        if isinstance(value, Mapping):
            out[key] = render_body(cast("Mapping[str, object]", value), case)
        elif isinstance(value, str) and value.startswith(REFERENCE):
            out[key] = _read(value, case)
        else:
            out[key] = value
    return out


def _read(reference: str, case: Case) -> object:
    _, _, path = reference.partition(REFERENCE)
    head, _, rest = path.partition(".")
    if head == "vars" or head == "metadata":
        holder = case.vars if head == "vars" else case.metadata
        if rest not in holder:
            available = ", ".join(sorted(holder)) or "nothing"
            raise ValueError(
                f"case {case.id!r} has no {head}[{rest!r}], which the body "
                f"asks for as {reference!r}. It has: {available}"
            )
        return holder[rest]
    return getattr(case, head)


class HttpTarget:
    """Post a body built from the case, read the answer out of the response.

        target = HttpTarget(
            "http://localhost:8080/answer",
            request=lambda case: {"question": case.vars["question"]},
            output_path="data.answer",
            cost_path="usage.cost_usd",
            config_path="config",
            expect_config={"provider": "gemini", "model": "gemini-2.5-flash"},
            tool_calls_path="trajectory.calls",
            usage_path="usage.tokens",
        )

    The application can be written in anything. What digline needs is a body it
    can post and a field it can read.

    **`tools_path` and `tool_calls_path` are what make a trajectory check
    answerable over HTTP.** Without them `ToolsCalled` and `ToolCalledWith` load
    from a TOML suite and then *error* on every case — the honest third outcome,
    for a question nothing could answer. Declaring only `tool_calls_path` is the
    ordinary case: the names are derived from the calls, so the two cannot
    disagree.

    **`usage_path` reads the counts by `Usage`'s own names** (`USAGE_FIELDS`),
    closed the way a reported configuration is closed. Absent, `Response.usage`
    is `None` — a target that reports no counts, which is an honest answer and
    not a zero.

    **`expect_config` is what makes the configuration in the record reviewed.**
    Over HTTP the application writes every field it reports, so without a
    declaration the `provider` and `model` in a run are values nobody checked —
    and they cross a boundary in clear. Declare the ones you expect and the
    application's part is reduced to agreeing with them: a reported value that
    contradicts the declaration errors its case, naming both. Partial on
    purpose — the keys you name are the keys checked (ADR 0030 §4, §7).
    """

    #: Every `*_path` here is a **dotted path into the answer's JSON**, never a
    #: file, and the annotations say so on purpose: `str`, never `str | Path`.
    #: The declarative loader decides what to resolve against the suite's
    #: directory by testing for the word `Path` in the annotation string
    #: (`host/toml_suite.py`, `_resolve_paths`), so annotating one of these with
    #: `Path` would turn `data.answer` into a filename beside the suite, hand it
    #: to the perimeter check, and refuse the suite for a file nobody named.
    #: A parameter added below inherits the TOML form for free, and inherits
    #: this too.
    def __init__(
        self,
        url: str,
        *,
        request: Callable[[Case], Mapping[str, object]] | None = None,
        body: Mapping[str, object] | None = None,
        output_path: str,
        cost_path: str | None = None,
        latency_from_response: str | None = None,
        config_path: str | None = None,
        expect_config: Mapping[str, ConfigValue] | None = None,
        tools_path: str | None = None,
        tool_calls_path: str | None = None,
        usage_path: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        if (request is None) == (body is None):
            raise ValueError(
                "HttpTarget needs `request` or `body`, and not both: they are "
                "two ways of saying what to post, and two would be a question "
                "about which one was sent"
            )
        self.url = url
        #: What every message about this endpoint says instead of `url`.
        #: `https://user:sk-secret@gateway/v1` is a URL somebody really does
        #: write — and it used to reach stderr, and in CI a build log, whole.
        #: ADR 0005 §2 already reduced `base_url` to its host for exactly this
        #: reason; a target that took its endpoint under another name was not
        #: covered by that decision, only by the fact that nobody had looked.
        spoken = endpoint_host(url)
        if spoken is None:
            # No `or url` fallback. That fallback is what made the reduction
            # conditional on the URL being well formed — exactly the case where
            # a person is most likely to have mistyped a secret into it.
            raise ValueError(
                "url names no host. An endpoint is recorded and spoken about "
                "by host, so a value without one cannot be reduced to one, and "
                "printing the value instead is what this refuses. Check the "
                "url in the suite; it is not repeated here on purpose."
            )
        self._spoken = spoken
        #: The literals this URL's own userinfo could put into somebody else's
        #: error text. `urllib` quotes the authority back — `InvalidURL` says
        #: `nonnumeric port: 'sk-live-…@gateway'` — so knowing the exact
        #: secrets is what lets the text be kept and the credential removed.
        parsed = urlsplit(url if "//" in url else f"//{url}")
        self._userinfo = tuple(
            part for part in (parsed.password, parsed.username) if part
        )
        #: The declarative half (ADR 0007 §5): the payload's own shape, with
        #: leaves that name case fields. Kept as the table it was written as, so
        #: `repr` and a debugger show what the suite said.
        self.body = None if body is None else dict(body)
        if self.body is not None:
            check_references(self.body)
        self.request = request if request is not None else self._from_body
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
        #: What the suite declares the application should report (ADR 0030 §4).
        #: The value in the record is then one a reviewer wrote — the
        #: application's part is reduced to agreeing with it — which is the
        #: provenance ADR 0005 §9 separates the two model names by, and which
        #: over HTTP exists only because this key does.
        self.expect_config = (
            None
            if expect_config is None
            else expected_config(expect_config, where="`expect_config`")
        )
        if self.expect_config is not None and config_path is None:
            # A gate on a value nothing reads passes everything. Refused at
            # construction rather than left to be noticed, because the run it
            # would produce is green and means nothing (fixed decision 3).
            raise ValueError(
                "`expect_config` declares the configuration this endpoint "
                "should report, and without `config_path` no configuration is "
                "ever read: the check never runs, and the run is green whatever "
                "the application answered. Name the object in the answer with "
                "`config_path`, or drop `expect_config`"
            )
        self.tools_path = tools_path
        self.tool_calls_path = tool_calls_path
        self.usage_path = usage_path
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
        # Before the run's own configuration is kept, and on every answer rather
        # than only the first: what the suite declared is the reviewed value, so
        # an answer that contradicts it is refused rather than recorded. Nothing
        # earlier can do this — `preflight()` sends a HEAD and the driver's
        # pre-run read is empty for an `HttpTarget`, which learns its
        # configuration by answering (ADR 0030 §7).
        if self.expect_config is not None:
            refuse_config_mismatch(declared, self.expect_config, spoken=self._spoken)
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
                f"{self._spoken} answered under a different configuration part way "
                f"through the run ({changes}). One run measures one system, so "
                "there is no single configuration to record: pin the "
                "application's model and parameters for the run, or evaluate "
                "each set-up as its own run"
            )

    def _said(self, exc: BaseException) -> str:
        """`urllib`'s own words, minus anything this URL's userinfo put in them.

        The text is worth keeping — "connection refused" is the whole
        diagnosis — but the exception may quote the endpoint back, and for
        `https://user:secret@gateway/answer` the part it quotes is the
        credential. Replacing the known literals is exact: the secret is not
        guessed from the message, it is read from the URL this target was
        built with.
        """
        said = str(exc)
        for secret in self._userinfo:
            said = said.replace(secret, "***")
        return said

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
        except _ENDPOINT_ERRORS as exc:
            raise ValueError(
                f"nothing answered at {self._spoken}: {self._said(exc)}. The "
                f"suite declares {len(cases)} case(s) and every one of them "
                "would fail the same way — start the application, or point the "
                "target at it"
            ) from exc

    def _from_body(self, case: Case) -> Mapping[str, object]:
        """`request` when the suite declared a body instead of a function."""
        assert self.body is not None  # noqa: S101 — guarded in __init__
        return render_body(self.body, case)

    def __call__(self, case: Case) -> Response:
        sent = json.dumps(dict(self.request(case)), sort_keys=True)
        headers = {"Content-Type": "application/json", **self.headers}
        posted = urllib.request.Request(
            self.url, data=sent.encode("utf-8"), headers=headers, method="POST"
        )

        started = perf_counter()
        try:
            with urllib.request.urlopen(posted, timeout=self.timeout) as answer:
                raw = answer.read().decode("utf-8")
        except _ENDPOINT_ERRORS as exc:
            # Unguarded until 0.7.2, which meant `http.client.InvalidURL` — not
            # an `OSError`, so `preflight`'s handler never saw it either —
            # reached stderr as a traceback with the authority it was quoting,
            # credential and all.
            raise ValueError(
                f"{self._spoken} could not be called: {self._said(exc)}"
            ) from exc
        elapsed_ms = (perf_counter() - started) * 1000.0

        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self._spoken} answered something that is not JSON: {raw[:120]!r}"
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

        calls = (
            None
            if self.tool_calls_path is None
            else reported_tool_calls(
                _dig(payload, self.tool_calls_path), self.tool_calls_path
            )
        )
        if self.tools_path is not None:
            names = reported_tools(_dig(payload, self.tools_path), self.tools_path)
            if calls is not None and tuple(c.tool for c in calls) != names:
                # Two readers, one trajectory: `ToolsCalled` reads the names and
                # `ToolCalledWith` the calls, and an application whose two lists
                # disagreed would have them judge different trajectories of the
                # same answer. `Completion` enforces this for a plugin; the same
                # invariant, checked where the values arrive instead.
                raise ValueError(
                    f"{self.tools_path!r} and {self.tool_calls_path!r} name "
                    f"different trajectories: {names!r} against "
                    f"{tuple(c.tool for c in calls)!r}. They are two readings of "
                    "one answer and must agree, in the same order"
                )
        elif calls is not None:
            # **Derived, not required.** Declaring only the calls is the common
            # case, and making the suite repeat the names in a second path would
            # be asking for the one thing that can then disagree. Nothing is
            # invented: the names come from the calls.
            names = tuple(call.tool for call in calls)
        else:
            names = None

        metadata: dict[str, object] = {}
        if names is not None:
            found_tools: list[object] = list(names)
            metadata["tools"] = found_tools
        if calls is not None:
            metadata["tool_calls"] = [call.as_reported() for call in calls]

        return Response(
            output=output,
            # What was sent, not what came back: `input` is the question a judge
            # is shown, and the answer is already in `output`.
            input=sent,
            cost_usd=cost,
            latency_ms=latency,
            usage=(
                None
                if self.usage_path is None
                else reported_usage(_dig(payload, self.usage_path), self.usage_path)
            ),
            # A key here means the application said something, which is what lets
            # `ToolsCalled` tell *called nothing* from *nobody reported*. An
            # undeclared path writes no key, exactly as `Completion.as_metadata`
            # omits what a provider did not report.
            metadata=metadata,
        )


def _as_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{path!r} holds {value!r}, which is not a number")
    return float(value)


def _sequence(found: object, path: str, what: str) -> Sequence[object]:
    """A JSON array, and never a string — which is a `Sequence` and iterates."""
    if isinstance(found, str) or not isinstance(found, list | tuple):
        raise ValueError(
            f"{path!r} holds a {type(found).__name__}, not a list of {what}: "
            "there is no trajectory to read"
        )
    return cast("Sequence[object]", found)


def reported_tools(found: object, path: str) -> tuple[str | None, ...]:
    """The names the application said the model called, in order.

    `null` at a position is **a call it did not name**, kept at its position
    because that is what ADR 0018 §1 (amended 2026-09-17) makes it mean:
    `ToolsCalled` never passes over one. `""` is refused rather than read as
    that absence — an application that does not know says `null`, the same rule
    `ToolCall` applies one layer down.
    """
    names: list[str | None] = []
    for index, name in enumerate(_sequence(found, path, "tool names")):
        if name is None:
            names.append(None)
        elif isinstance(name, str) and name:
            names.append(name)
        else:
            raise ValueError(
                f"{path}[{index}] is {name!r}, which is not a tool name: a name "
                "is a non-empty string, and a call nobody named is null"
            )
    return tuple(names)


def reported_tool_calls(found: object, path: str) -> tuple[ToolCall, ...]:
    """The trajectory with its arguments, checked before it is believed.

    **Stricter than `record_trajectory`, and that is the point.** The recorder
    casts `status` to `ToolStatus` without looking, which is right for a target
    written in this repository and reviewed with it; here the values arrive from
    an application nobody here reviews, so the vocabularies are closed at the
    boundary rather than downstream — `declared_config`'s rule, for
    `declared_config`'s reason (ADR 0005 §8).

    No default for `status`. A plain-function target defaults to `success`
    because that was its contract from the day the trajectory arrived; an
    application has no such history, and letting it write *success* by omission
    is the vacuously green report fixed decision 3 refuses.
    """
    calls: list[ToolCall] = []
    for index, entry in enumerate(_sequence(found, path, "tool calls")):
        at = f"{path}[{index}]"
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"{at} is a {type(entry).__name__}, not an object with a 'tool' in it"
            )
        call = cast("Mapping[str, object]", entry)
        if "tool" not in call:
            raise ValueError(
                f"{at} has no 'tool': a call whose tool nobody named says so "
                'with "tool": null'
            )
        tool = call["tool"]
        if not (tool is None or (isinstance(tool, str) and tool)):
            raise ValueError(
                f"{at}.tool is {tool!r}, which is not a tool name: a name is a "
                "non-empty string, and a call nobody named is null"
            )
        status = call.get("status")
        if status not in ("success", "error", "not_reported"):
            raise ValueError(
                f"{at}.status is {status!r}. Report 'success', 'error', or "
                "'not_reported' where the application does not know — there is "
                "no default, because a tool that failed must not be able to "
                "report as one that worked by saying nothing"
            )
        absence = call.get("result_absence")
        if absence is not None and absence not in ("not_reported", "not_recorded"):
            raise ValueError(
                f"{at}.result_absence is {absence!r}. Report 'not_reported', "
                "'not_recorded', or leave it out"
            )
        arguments = call.get("arguments")
        if not (arguments is None or isinstance(arguments, Mapping | str)):
            raise ValueError(
                f"{at}.arguments is a {type(arguments).__name__}: report the "
                "object the model sent, the string it sent if it was not an "
                "object, or null where the application does not report them"
            )
        result = call.get("result")
        calls.append(
            # `ToolCall` refuses a result beside a declared absence, and this
            # constructor is where that refusal is wanted: one rule, checked in
            # the place that already owns it.
            ToolCall(
                tool=tool,
                arguments=cast("Mapping[str, object] | str | None", arguments),
                # No cast on either: the membership checks above narrow these to
                # `ToolStatus` and `ResultAbsence` on their own, which is pyright
                # confirming that the refusal and the type say the same thing.
                status=status,
                result=None if result is None else str(result),
                result_absence=absence,
            )
        )
    return tuple(calls)


#: The counts a `usage` object may hold: `Usage`'s own field names, closed the
#: way `CONTRACT_FIELDS` closes a reported configuration and for the same
#: reason. An open mapping here would put an application's own vocabulary into
#: the run's totals, where nobody can check it.
USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "thinking_tokens",
)


def _count(value: object, at: str) -> int:
    """A token count, refused unless it is one.

    **This is where F-1 stops being unreachable.** `Usage` accepts a `bool` and
    a whole `float` — its own guards are ordering comparisons, which both
    satisfy — and the second 0.17.0 delta-pass recorded that as LOW precisely
    because nothing reachable could deliver one: the plugins coerce with
    `int()`, and their SDKs hand over integers. An application's JSON is the
    first path that can, so `usage_path` would make it reachable, and closing it
    here is cheaper than widening `Usage` for one boundary. `true` reads as `1`
    and rides into the document as `true`, which the document's own reader then
    refuses — written, listed and unreadable.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{at} is {value!r}, which is not a token count: report a whole "
            "number. A boolean is not a count, and a fraction of a token is not "
            "a thing an endpoint can have produced"
        )
    return value


def reported_usage(found: object, path: str) -> Usage:
    """The counts an application reported, by `Usage`'s own names.

    The names are digline's and not the application's, which is a real ask of
    whoever writes the endpoint — and it is the same ask ADR 0005 §8 already
    makes of the configuration. A per-field path each would spare them the
    rename and cost the reader the one thing that makes the counts checkable:
    that `input_tokens` means the same quantity in every run of every suite.

    `input_tokens` and `output_tokens` are mandatory. The rest default to `0`
    because that is what `Usage` means by them — `thinking_tokens` excepted,
    where `None` is *not reported* and is never guessed as a zero (ADR 0026 §2).
    """
    if not isinstance(found, Mapping):
        raise ValueError(
            f"{path!r} holds a {type(found).__name__}, not an object of counts"
        )
    counts = cast("Mapping[str, object]", found)
    unknown = sorted(set(counts) - set(USAGE_FIELDS))
    if unknown:
        raise ValueError(
            f"{path!r} declares {', '.join(unknown)}, which is not a count "
            f"digline records. Allowed: {', '.join(USAGE_FIELDS)}. A count "
            "under another name is a count nothing adds up"
        )
    for name in ("input_tokens", "output_tokens"):
        if counts.get(name) is None:
            raise ValueError(
                f"{path!r} gives no {name}: a usage that cannot say what the "
                "call consumed reports nothing. Leave the whole object out "
                "instead — no counts is an honest answer and a zero is not"
            )
    thinking = counts.get("thinking_tokens")
    return Usage(
        input_tokens=_count(counts["input_tokens"], f"{path}.input_tokens"),
        output_tokens=_count(counts["output_tokens"], f"{path}.output_tokens"),
        cache_read_tokens=_count(
            counts.get("cache_read_tokens", 0), f"{path}.cache_read_tokens"
        ),
        cache_write_tokens=_count(
            counts.get("cache_write_tokens", 0), f"{path}.cache_write_tokens"
        ),
        thinking_tokens=(
            None if thinking is None else _count(thinking, f"{path}.thinking_tokens")
        ),
    )
