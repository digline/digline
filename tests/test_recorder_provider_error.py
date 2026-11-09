"""A call the provider refuses, on the three providers' own SDKs, with no
network: the fakes answer 403, as Bedrock answered a key it did not accept on
2026-11-09 (*The security token included in the request is invalid*).

What is held here:

- the SDK's exception reaches the application as the SDK raised it;
- nothing is recorded, because there is no reply;
- the call is counted `provider error 403`, in memory and, at the next tick,
  in the counts file `digline record status` reads;
- an exception that carries no provider's status, a connection that failed,
  is not counted, as before.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.host import recorder_status
from digline.recorder import RecordedClient, wrap

SDKS = ("anthropic", "openai", "httpx2", "boto3", "botocore")
QUESTION = [{"role": "user", "content": "Capital of France?"}]
REFUSED = {"message": "The security token included in the request is invalid."}


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


def sdk(name: str) -> Any:
    return importlib.import_module(name)


def recordings(root: Path) -> list[Path]:
    return sorted((root / ".digline").glob("*/recordings/*/*.json"))


def not_recorded(client: RecordedClient) -> dict[str, int]:
    return dict(client.digline_counts["not_recorded"])  # type: ignore[arg-type]


def refusing(request: Any) -> Any:
    return sdk("httpx2").Response(403, json={"error": REFUSED})


def unreachable(request: Any) -> Any:
    raise sdk("httpx2").ConnectError("no route to the provider", request=request)


def an_anthropic(handle: Any = refusing) -> Any:
    httpx2 = sdk("httpx2")
    return sdk("anthropic").Anthropic(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def an_openai(handle: Any = refusing) -> Any:
    httpx2 = sdk("httpx2")
    return sdk("openai").OpenAI(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def a_bedrock() -> Any:
    client = sdk("boto3").client(
        "bedrock-runtime",
        region_name="eu-central-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    awsrequest = sdk("botocore.awsrequest")

    def send(request: Any, **_: object) -> Any:
        body = json.dumps(REFUSED).encode()
        response = awsrequest.AWSResponse(
            request.url,
            403,
            {
                "content-type": "application/json",
                "x-amzn-ErrorType": "UnrecognizedClientException",
            },
            None,
        )
        response._content = body  # noqa: SLF001
        return response

    client.meta.events.register("before-send.bedrock-runtime.*", send)
    return client


def ask_anthropic(client: Any) -> Any:
    return client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )


def ask_openai(client: Any) -> Any:
    return client.chat.completions.create(
        model="gpt-test", messages=QUESTION, suite="triage"
    )


def ask_bedrock(client: Any) -> Any:
    return client.converse(
        modelId="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        messages=[{"role": "user", "content": [{"text": "Capital of France?"}]}],
        inferenceConfig={"maxTokens": 10},
        suite="triage",
    )


CASES = [
    ("anthropic", an_anthropic, ask_anthropic, "anthropic.PermissionDeniedError"),
    ("openai", an_openai, ask_openai, "openai.PermissionDeniedError"),
    ("bedrock", a_bedrock, ask_bedrock, "botocore.exceptions.ClientError"),
]


@pytest.mark.parametrize(
    ("name", "build", "ask", "raised"), CASES, ids=[case[0] for case in CASES]
)
def test_a_refused_call_raises_as_it_did_and_is_counted_by_its_status(
    tmp_path: Path, name: str, build: Any, ask: Any, raised: str
) -> None:
    client = wrap(build(), app="a", tenant="acme", root=tmp_path)
    module, kind = raised.rsplit(".", 1)
    with pytest.raises(getattr(sdk(module), kind)):
        ask(client)
    assert recordings(tmp_path) == []
    assert not_recorded(client) == {"provider error 403": 1}
    # The counts reach the file at the next tick; this is that tick.
    recorder._flush(client._digline_state)  # pyright: ignore[reportPrivateUsage]
    [status] = recorder_status(tmp_path, "acme")
    [triage] = status.suites
    assert triage.suite == "triage"
    assert dict(triage.not_recorded) == {"provider error 403": 1}
    assert triage.calls == 0


def test_an_asynchronous_refused_call_is_counted_the_same(tmp_path: Path) -> None:
    httpx2 = sdk("httpx2")
    client = wrap(
        sdk("anthropic").AsyncAnthropic(
            api_key="test",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(refusing)),
            max_retries=0,
        ),
        app="a",
        tenant="acme",
        root=tmp_path,
    )

    async def ask() -> None:
        await client.messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
        )

    with pytest.raises(sdk("anthropic").PermissionDeniedError):
        asyncio.run(ask())
    assert recordings(tmp_path) == []
    assert not_recorded(client) == {"provider error 403": 1}


def test_a_connection_that_failed_is_not_a_refusal_and_is_not_counted(
    tmp_path: Path,
) -> None:
    client = wrap(an_anthropic(unreachable), app="a", tenant="acme", root=tmp_path)
    with pytest.raises(sdk("anthropic").APIConnectionError):
        ask_anthropic(client)
    assert recordings(tmp_path) == []
    assert not_recorded(client) == {}
