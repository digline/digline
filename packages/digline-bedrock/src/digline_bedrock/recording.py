"""How the recorder reads a call made through a `bedrock-runtime` client.
(ADR 0058 §3, §6)

Declared under `digline.recording_maps` as `botocore.BedrockRuntime:converse`:
boto3 builds the client's class at run time, in `botocore.client`, under the
service's name. Loaded only when a call is recorded.

**`converse_stream` is another method**, declared under its own entry point,
`botocore.BedrockRuntime:converse_stream` (ADR 0058 §13). Its reply is a dict
whose `stream` is botocore's `EventStream`; the events are folded into the
Converse reply the whole answer would have been — `output.message` from
`messageStart` and the `contentBlock*` events, `stopReason` from
`messageStop`, `usage` from `metadata` — and read by `completion_of` like any
other. The SDK offers no accumulator of its own for these events, so this one
is the plugin's.

**The case is the messages.** The setup is everything else the call decides
with: `modelId`, `system`, `inferenceConfig`, `toolConfig`, `guardrailConfig`,
`additionalModelRequestFields`, `promptVariables`, `performanceConfig`. Not
`requestMetadata`, which names who or what the request is for.

**The reply is read by `completion_of`**, the function the target already uses.
A recording does not price: the price list passed is empty, so a reply without
a usage block is recorded as *not recorded*, never as zero.

**`invoke_model` and `invoke_model_with_response_stream`** (P-1541, P-1543)
carry a model family's own body. Anthropic's is the Messages API, read with
the map `digline-anthropic` reads a direct call with, so there is one reading
of Messages: the body's `messages` are the case, the setup is `modelId` and
the body's other keys but those Anthropic's map leaves out, and the reply,
or each stream chunk's `bytes`, is a Messages reply or event. Another family
is not read: `family_of` tells it from the model id, a cross-region prefix
(`us.`, `eu.`, `apac.`, `global.`) taken off first, and the call is counted
as not recorded, with a sentence said once a family (`Refusal`). An
embedding model is said apart.

**Off the wire**, for `digline record proxy`, `WIRE` reads the same two
calls, `/model/<id>/converse` and `/model/<id>/converse-stream`, with the same
maps (ADR 0062 §3). The application's AWS SDK signed its request for the
proxy's address, so the proxy signs it again here, with SigV4 and the
credentials and region botocore finds on this machine, as boto3 would: the
environment first, then `~/.aws/config` and `~/.aws/credentials`. Only after
checking that the application signed it with those same credentials
(`verify`): a process on this machine without them spends nothing. The model
id the SDK passes as `modelId` travels in the path, and is put back. The
streamed reply is an AWS event stream, decoded by botocore's own buffer.
"""

from __future__ import annotations

import base64
import calendar
import hmac
import importlib
import io
import json
import re
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast
from urllib.parse import unquote

from digline.targets import Completion, Pricing, ToolCall
from digline_bedrock.client import completion_of

if TYPE_CHECKING:
    from digline.recorder import StreamReading

__all__ = [
    "INVOKE_MAP",
    "INVOKE_STREAM_MAP",
    "MAP",
    "NOT_SETUP",
    "REGION_PREFIXES",
    "STREAM_MAP",
    "WIRE",
    "BedrockInvokeRecording",
    "BedrockRecording",
    "BedrockWire",
    "family_of",
]

#: The keywords of `converse` that are neither the case nor the setup, beside
#: the messages themselves.
NOT_SETUP: frozenset[str] = frozenset({"messages", "requestMetadata"})

_NO_PRICES = Pricing(per_model={})


class BedrockRecording:
    """The map digline's recorder loads for a `bedrock-runtime` client."""

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        case: dict[str, object] = {"messages": request.get("messages")}
        setup = {key: value for key, value in request.items() if key not in NOT_SETUP}
        return case, setup

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        return completion_of(reply, str(request.get("modelId", "")), _NO_PRICES)


class BedrockStreamRecording(BedrockRecording):
    """The map for `converse_stream`: the same request, and a reply whose
    `stream` carries the events."""

    def streams(self, request: Mapping[str, Any]) -> bool:
        return True

    def stream_of(self, reply: Any) -> Any:
        return reply["stream"]

    def reading(self, request: Mapping[str, Any]) -> StreamReading:
        return _Events(str(request.get("modelId", "")))


class _Events:
    """The events of one `converse_stream`, folded into a Converse reply."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._role = "assistant"
        #: Per content block index: its kind, and what has arrived of it.
        self._blocks: dict[int, dict[str, Any]] = {}
        self._stop: str | None = None
        self._usage: Mapping[str, Any] | None = None

    def add(self, event: Any) -> None:
        if not isinstance(event, Mapping):
            return
        found = cast("Mapping[str, Any]", event)
        if "messageStart" in found:
            self._role = str(found["messageStart"].get("role", "assistant"))
        elif "contentBlockStart" in found:
            start = found["contentBlockStart"]
            tool = start.get("start", {}).get("toolUse")
            if tool is not None:
                self._blocks[int(start["contentBlockIndex"])] = {
                    "toolUse": {**tool, "input": ""}
                }
        elif "contentBlockDelta" in found:
            delta = found["contentBlockDelta"]
            index = int(delta["contentBlockIndex"])
            change = delta.get("delta", {})
            block = self._blocks.setdefault(index, {})
            if "text" in change:
                block["text"] = block.get("text", "") + str(change["text"])
            elif "toolUse" in change:
                use = block.setdefault("toolUse", {"input": ""})
                use["input"] = use.get("input", "") + str(
                    change["toolUse"].get("input", "")
                )
        elif "messageStop" in found:
            self._stop = found["messageStop"].get("stopReason")
        elif "metadata" in found:
            self._usage = found["metadata"].get("usage")

    def completion(self, stream: Any) -> Completion:
        content: list[dict[str, Any]] = []
        for index in sorted(self._blocks):
            block = self._blocks[index]
            if "toolUse" in block:
                use = dict(block["toolUse"])
                raw = use.get("input") or "{}"
                use["input"] = json.loads(raw) if isinstance(raw, str) else raw
                content.append({"toolUse": use})
            elif "text" in block:
                content.append({"text": block["text"]})
        reply: dict[str, Any] = {
            "output": {"message": {"role": self._role, "content": content}},
            "stopReason": self._stop,
        }
        if self._usage is not None:
            reply["usage"] = self._usage
        return completion_of(reply, self._model, _NO_PRICES)


MAP = BedrockRecording()
STREAM_MAP = BedrockStreamRecording()


#: A cross-region inference profile's prefix, before the vendor's name: taken
#: off before the family is read, so `us.anthropic.claude-…` is Anthropic's.
REGION_PREFIXES: tuple[str, ...] = ("us.", "eu.", "apac.", "global.")

type Family = Literal["messages", "embeddings", "other"]


def family_of(model_id: str) -> tuple[str, Family]:
    """The vendor a model id names, and what its body is to the recorder:
    Anthropic's Messages, an embedding model, or another family. Read from the
    id, never the body: the body of another family may look like anything.
    An ARN is read by its last segment."""
    name = model_id.rsplit("/", 1)[-1]
    for prefix in REGION_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    vendor = name.split(".", 1)[0]
    if "embed" in name:
        return vendor, "embeddings"
    if vendor == "anthropic":
        return vendor, "messages"
    return vendor, "other"


def _refusal(method: str, model_id: str) -> Any:
    """The `Refusal` for a model family not read, or `None` for Anthropic's."""
    vendor, family = family_of(model_id)
    if family == "messages":
        return None
    from digline.recorder import Refusal

    if family == "embeddings":
        return Refusal(
            reason="embeddings not recorded",
            family=f"bedrock embeddings {vendor}",
            said=f"{method} on {model_id}: embeddings are not recorded",
        )
    return Refusal(
        reason="model family not recorded",
        family=f"bedrock {vendor}",
        said=f"{method} on {model_id}: this model family is not recorded",
    )


def _body_of(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """The InvokeModel body as an object: the proxy hands it parsed, boto3's
    caller as JSON text or bytes. A file is not read, which would empty it."""
    body = request.get("body")
    if isinstance(body, Mapping):
        return cast(Mapping[str, Any], body)
    if isinstance(body, bytes | bytearray | str):
        found = json.loads(body)
        if isinstance(found, dict):
            return cast(Mapping[str, Any], found)
    raise ValueError("the body is not a JSON object the recorder can read")


def _reply_of(reply: Any) -> object:
    """The reply's Messages JSON. In process it is boto3's `body`, a stream the
    application has not read yet: read here, and put back as a new stream of
    the same bytes before anything else, so the application reads what it
    would have. Off the wire it is the JSON already."""
    if not isinstance(reply, dict):
        return cast(object, reply)
    found = cast(dict[str, Any], reply)
    if "body" not in found:
        return found
    data = found["body"].read()
    response: Any = importlib.import_module("botocore.response")
    found["body"] = response.StreamingBody(io.BytesIO(data), len(data))
    return json.loads(data)


class BedrockInvokeRecording:
    """The map for `invoke_model`: a body of the Anthropic Messages family,
    read with `digline-anthropic`'s map; any other family declined."""

    method = "invoke_model"

    def refusal(self, request: Mapping[str, Any]) -> Any:
        return _refusal(self.method, str(request.get("modelId", "")))

    def split(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, object], dict[str, object]]:
        from digline_anthropic.recording import NOT_SETUP as MESSAGES_NOT_SETUP

        body = _body_of(request)
        case: dict[str, object] = {"messages": body.get("messages")}
        setup: dict[str, object] = {"modelId": request.get("modelId")}
        setup.update({k: v for k, v in body.items() if k not in MESSAGES_NOT_SETUP})
        return case, setup

    def completion(self, reply: Any, request: Mapping[str, Any]) -> Completion:
        from digline_anthropic.recording import MAP as MESSAGES
        from digline_anthropic.recording import WIRE as MESSAGES_WIRE

        return MESSAGES.completion(MESSAGES_WIRE.reply(_reply_of(reply)), request)


class BedrockInvokeStreamRecording(BedrockInvokeRecording):
    """The map for `invoke_model_with_response_stream`: the same body, and a
    reply whose `body` is a stream of `chunk`s, each a Messages event's JSON
    in its `bytes`."""

    method = "invoke_model_with_response_stream"

    def streams(self, request: Mapping[str, Any]) -> bool:
        return True

    def stream_of(self, reply: Any) -> Any:
        return reply["body"]

    def reading(self, request: Mapping[str, Any]) -> StreamReading:
        if self.refusal(request) is not None:
            # Declined before its reply is read: the chunks of another family
            # are not Messages events, and nothing here reads them.
            return _Declined()
        from digline_anthropic.recording import MAP as MESSAGES

        return _Chunks(MESSAGES.reading(request))


class _Chunks:
    """Each `chunk`'s bytes, a Messages event, handed to the Messages reading."""

    def __init__(self, inner: StreamReading) -> None:
        self._inner = inner

    def add(self, event: Any) -> None:
        if not isinstance(event, Mapping):
            return
        chunk = cast(Mapping[str, Any], event).get("chunk")
        if not isinstance(chunk, Mapping):
            return
        data = cast(Mapping[str, Any], chunk).get("bytes")
        if not isinstance(data, bytes | bytearray | str):
            return
        from digline_anthropic.recording import WIRE as MESSAGES_WIRE

        self._inner.add(MESSAGES_WIRE.event(json.loads(data)))

    def completion(self, stream: Any) -> Any:
        return self._inner.completion(stream)


class _Declined:
    """The reading of a stream whose family is declined: it reads nothing, and
    the call is counted by the map's `refusal` before any of it is used."""

    def add(self, event: Any) -> None:
        return None

    def completion(self, stream: Any) -> Completion:
        return Completion(text="", usage=None)


INVOKE_MAP = BedrockInvokeRecording()
INVOKE_STREAM_MAP = BedrockInvokeStreamRecording()


#: The calls the wire reads: `converse` and `converse-stream`, and `invoke`
#: and `invoke-with-response-stream`, the model id in the path as the SDK
#: writes it, percent-encoded.
_CALL = re.compile(
    r"/model/([^/]+)/(converse|converse-stream|invoke|invoke-with-response-stream)"
)

#: What the application's signature put in the headers, replaced by this one.
_SIGNATURE = frozenset(
    {"authorization", "x-amz-date", "x-amz-security-token", "x-amz-content-sha256"}
)

_EVENT_STREAM = "application/vnd.amazon.eventstream"

#: A SigV4 `Authorization` header: the key, the scope's date, region and
#: service, the headers signed and the signature.
_AUTHORIZATION = re.compile(
    r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/([^/]+)/aws4_request,"
    r" ?SignedHeaders=([a-z0-9;-]+), ?Signature=([0-9a-f]{64})"
)

#: How far a signature's time may be from this machine's clock, as AWS
#: allows: 15 minutes.
_SKEW = 15 * 60

#: This machine's clock, which a signature's time is held to.
_now = time.time

#: What a tool step's status may be, as `digline.core.ToolStatus` has it.
type _Status = Literal["success", "error", "not_reported"]

#: A `toolResult`'s `status`, where it says one.
_STATUS: Mapping[str, _Status] = {
    "error": "error",
    "success": "success",
}


class _Signing(Protocol):
    """What `verify` sets on botocore's request: the time it is signed at."""

    context: dict[str, object]


class BedrockWire:
    """Converse and ConverseStream off the wire, for `digline record proxy`.

    `load()` reads the region and the credentials once, at the start. Where
    either is missing the route says so, at the start and at each call, and
    forwards nothing: a call signed with nothing would only fail upstream."""

    map = STREAM_MAP
    #: The AWS SDKs take the whole address, and the path starts at `/model`.
    base = ""
    #: Read by boto3 1.43, measured; another AWS SDK may need its own
    #: endpoint override.
    variable = "AWS_ENDPOINT_URL_BEDROCK_RUNTIME"

    def __init__(self) -> None:
        self._session: Any = None
        self._region: str | None = None
        self.problem: str | None = "not loaded"

    @property
    def upstream(self) -> str:
        return f"https://bedrock-runtime.{self._region or 'unknown'}.amazonaws.com"

    def matches(self, path: str) -> bool:
        return _CALL.fullmatch(path.partition("?")[0]) is not None

    def claims(self, headers: Mapping[str, str]) -> bool:
        """A request an AWS SDK signed for Bedrock: SigV4, its scope's service
        `bedrock`."""
        auth = headers.get("authorization", "")
        return auth.startswith("AWS4-HMAC-SHA256 ") and "/bedrock/aws4_request" in auth

    def reply(self, raw: object) -> Any:
        """The JSON is the dict boto3 returns, which the map reads."""
        return raw

    def event(self, raw: object) -> Any:
        return raw

    def load(self) -> None:
        for name in ("botocore.auth", "botocore.awsrequest", "botocore.eventstream"):
            importlib.import_module(name)
        # botocore ships no types, so what it gives is `Any`, as in `client.py`.
        session: Any = importlib.import_module("botocore.session")
        self._session = session.Session()
        self._region = self._session.get_config_variable("region")
        if self._region is None:
            self.problem = (
                "no AWS region: set AWS_REGION or AWS_DEFAULT_REGION, or a "
                "region in the profile"
            )
        elif self._session.get_credentials() is None:
            self.problem = (
                "no AWS credentials: the environment, ~/.aws/credentials or a "
                "profile, as boto3 finds them"
            )
        else:
            self.problem = None

    def verify(
        self, method: str, path: str, headers: Mapping[str, str], body: bytes
    ) -> str | None:
        """Why the request was not signed with this machine's credentials, or
        `None` where it was: the access key is this machine's, and the
        signature, computed again with its secret over the path, the query,
        the headers the request says it signed and the body, is the one the
        request carries. As AWS checks it, with its 15 minutes. So a process
        on this machine without its keys cannot spend with them.

        `path` is the path the application sent, `/suite/<name>/` and all,
        and `headers` the headers it sent, by lowercase name."""
        found = _AUTHORIZATION.fullmatch(headers.get("authorization", ""))
        if found is None:
            return "it carries no AWS signature"
        key, date, region, service, signed, given = cast(
            tuple[str, str, str, str, str, str], found.groups()
        )
        credentials = self._session.get_credentials()
        if credentials is None:
            return "this machine has no AWS credentials"
        frozen: Any = credentials.get_frozen_credentials()
        if not hmac.compare_digest(key, str(frozen.access_key)):
            return "it was signed with another access key"
        stamp = headers.get("x-amz-date", "")
        try:
            at = calendar.timegm(time.strptime(stamp, "%Y%m%dT%H%M%SZ"))
        except ValueError:
            return "it carries no signing time"
        if not stamp.startswith(date) or abs(_now() - at) > _SKEW:
            return "its signing time is not this machine's, within 15 minutes"
        names = signed.split(";")
        if "host" not in names or any(name not in headers for name in names):
            return "a header it signed is missing"
        auth: Any = importlib.import_module("botocore.auth")
        sent: Any = importlib.import_module("botocore.awsrequest")
        exact: Any = sent.HTTPHeaders()
        for name in names:
            exact[name] = headers[name]
        request: _Signing = sent.AWSRequest(
            method=method, url=f"http://{headers['host']}{path}", data=body
        )
        request.context["timestamp"] = stamp
        check: Any = auth.SigV4Auth(frozen, service, region)

        # The headers the request names as signed, exactly: botocore's own
        # choice leaves some out, which another SDK may sign.
        def signed_headers(request: object) -> Any:
            return exact

        check.headers_to_sign = signed_headers
        expected = check.signature(
            check.string_to_sign(request, check.canonical_request(request)), request
        )
        if not hmac.compare_digest(str(expected), given):
            return "its signature is not the one this machine's key gives"
        return None

    def prepare(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes
    ) -> dict[str, str]:
        """The headers, signed again for `url` with SigV4: the application's
        signature named the proxy. Credentials are read at each call, so a
        profile's that refresh do."""
        auth: Any = importlib.import_module("botocore.auth")
        sent: Any = importlib.import_module("botocore.awsrequest")
        credentials = self._session.get_credentials()
        if credentials is None:
            raise ValueError("no AWS credentials")
        kept = {k: v for k, v in headers.items() if k.lower() not in _SIGNATURE}
        request: Any = sent.AWSRequest(method=method, url=url, data=body, headers=kept)
        auth.SigV4Auth(
            credentials.get_frozen_credentials(), "bedrock", self._region
        ).add_auth(request)
        signed = cast(Mapping[str, object], request.headers)
        return {str(key): str(value) for key, value in signed.items()}

    def map_for(self, path: str) -> Any:
        """The map that reads the call the path names: Converse's, or
        InvokeModel's for `invoke` and `invoke-with-response-stream`."""
        found = _CALL.fullmatch(path.partition("?")[0])
        if found is not None and found.group(2) == "invoke":
            return INVOKE_MAP
        if found is not None and found.group(2) == "invoke-with-response-stream":
            return INVOKE_STREAM_MAP
        return self.map

    def request_of(self, path: str, request: Mapping[str, Any]) -> dict[str, Any]:
        """The request as boto3 takes it: `modelId` from the path, and for
        `converse` the body's keys beside it, for `invoke` the body whole, as
        `body`."""
        found = _CALL.fullmatch(path.partition("?")[0])
        model = unquote(found.group(1)) if found is not None else ""
        if found is not None and found.group(2).startswith("invoke"):
            return {"modelId": model, "body": dict(request)}
        return {"modelId": model, **request}

    def frames(self, content_type: str, data: bytes) -> list[object] | None:
        """The events of a ConverseStream reply, each as boto3 yields it:
        `{"contentBlockDelta": {...}}`. `None` for a reply that is not an
        event stream. An exception the stream carries raises."""
        if _EVENT_STREAM not in content_type:
            return None
        stream: Any = importlib.import_module("botocore.eventstream")
        buffer: Any = stream.EventStreamBuffer()
        buffer.add_data(data)
        events: list[object] = []
        for message in buffer:
            headers = cast(Mapping[str, object], message.headers)
            if headers.get(":message-type") != "event":
                raise ValueError(str(headers.get(":exception-type", "exception")))
            payload = cast(bytes, message.payload)
            kind = str(headers[":event-type"])
            found: Any = json.loads(payload) if payload else {}
            if kind == "chunk" and isinstance(found, dict):
                # InvokeModelWithResponseStream: the event in base64 under
                # `bytes`, decoded here as boto3 decodes it for its caller.
                chunk = cast(dict[str, Any], found)
                found = {
                    **chunk,
                    "bytes": base64.b64decode(str(chunk.get("bytes", ""))),
                }
            events.append({kind: found})
        return events

    def results(self, request: Mapping[str, Any]) -> Sequence[ToolCall] | None:
        """The `toolResult` blocks after the last assistant message that asked
        for tools, in the order it asked: a result's text, its `json` as
        canonical JSON, and its `status` where it says one. An InvokeModel
        body is Anthropic's Messages, whose results Anthropic's wire reads."""
        body = request.get("body")
        if isinstance(body, Mapping):
            from digline_anthropic.recording import WIRE as MESSAGES_WIRE

            return MESSAGES_WIRE.results(cast(Mapping[str, Any], body))
        messages = _mappings(request.get("messages"))
        asked: list[Mapping[str, Any]] = []
        at = -1
        for index, message in enumerate(messages):
            if message.get("role") == "assistant":
                uses = [
                    use
                    for block in _mappings(message.get("content"))
                    for use in _mappings([block.get("toolUse")])
                ]
                if uses:
                    asked, at = uses, index
        if at < 0:
            return None
        given: dict[str, Mapping[str, Any]] = {
            str(result.get("toolUseId")): result
            for message in messages[at + 1 :]
            for block in _mappings(message.get("content"))
            for result in _mappings([block.get("toolResult")])
        }
        if not given:
            return None
        return tuple(
            _result(use, given.get(str(use.get("toolUseId")))) for use in asked
        )


def _mappings(value: object) -> list[Mapping[str, Any]]:
    """The objects in a JSON list, in order; nothing where it is not one."""
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [
        cast(Mapping[str, Any], item) for item in items if isinstance(item, Mapping)
    ]


def _result(use: Mapping[str, Any], result: Mapping[str, Any] | None) -> ToolCall:
    name = use.get("name") or None
    arguments = cast(Mapping[str, object] | None, use.get("input"))
    if result is None:
        return ToolCall(
            tool=name,
            arguments=arguments,
            status="not_reported",
            result_absence="not_reported",
        )
    status: _Status = _STATUS.get(str(result.get("status")), "not_reported")
    parts: list[str] = []
    for block in _mappings(result.get("content")):
        if isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif "json" in block:
            parts.append(
                json.dumps(
                    block["json"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
        else:
            # An image or a document: bulk, never copied into a step.
            return ToolCall(
                tool=name,
                arguments=arguments,
                status=status,
                result_absence="not_recorded",
            )
    return ToolCall(
        tool=name, arguments=arguments, status=status, result="".join(parts)
    )


WIRE = BedrockWire()
