"""The recorder's wrapper, on the three providers' own SDKs, with no network.
(ADR 0058 §2, §3, §6, §10)

The fakes are the real clients: `anthropic.Anthropic` and `openai.OpenAI` over
an `httpx2.MockTransport`, and a `bedrock-runtime` client behind botocore's
`Stubber`. So a keyword the SDK does not know is refused by the SDK itself,
which is what holds that digline's two keywords never reach it.

What is held here:

- off, the call passes, digline's keywords are taken out, and nothing of
  `digline.core` is imported (in a fresh interpreter);
- on, one recording per call, with the three compartments each plugin's map
  draws, a digest stable across one setup and different across two, filed under
  the tenant a function returns at each call;
- a call that names no suite is `_unassigned` and carries its call site;
- the application's call never fails because of the recorder, and an SDK's
  exception propagates with nothing recorded;
- off costs little per call, against a threshold stated below.
"""

from __future__ import annotations

import datetime
import importlib
import json
import subprocess
import sys
import timeit
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.recorder import UNASSIGNED, RecordedClient, RecorderStartError, wrap
from digline.store.file_store import RecordingWriter

ANTHROPIC_REPLY: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "Paris"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 3},
}
OPENAI_REPLY: dict[str, object] = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-test",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Paris"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
}
BEDROCK_REPLY: dict[str, object] = {
    "output": {"message": {"role": "assistant", "content": [{"text": "Paris"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15},
    "metrics": {"latencyMs": 5},
}
QUESTION = [{"role": "user", "content": "Capital of France?"}]


#: The SDKs this file imports, and only inside a test. The plugins' own tests
#: hold that their SDK is imported only when a call is made, in the same
#: session, so an SDK imported here at the top of the module would turn them
#: red; and one imported in a test is taken out again when this module is done.
SDKS = ("anthropic", "openai", "httpx2", "boto3", "botocore")


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


def sdk(name: str) -> Any:
    """An SDK module, imported when a test needs it."""
    return importlib.import_module(name)


def answering(reply: dict[str, object], status: int = 200) -> Any:
    httpx2 = sdk("httpx2")

    def handle(request: object) -> Any:
        return httpx2.Response(status, json=reply)

    return httpx2.Client(transport=httpx2.MockTransport(handle))


def an_anthropic(status: int = 200) -> Any:
    body: dict[str, object] = (
        ANTHROPIC_REPLY if status == 200 else {"type": "error", "error": {}}
    )
    return sdk("anthropic").Anthropic(
        api_key="test", http_client=answering(body, status), max_retries=0
    )


def an_openai() -> Any:
    return sdk("openai").OpenAI(
        api_key="test",
        base_url="http://openai.test/v1",
        http_client=answering(OPENAI_REPLY),
    )


def a_bedrock(replies: int = 1) -> tuple[Any, Any]:
    client = sdk("boto3").client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    stubber = sdk("botocore.stub").Stubber(client)
    for _ in range(replies):
        stubber.add_response("converse", BEDROCK_REPLY)
    stubber.activate()
    return client, stubber


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(recorder.ENVIRONMENT_VARIABLE, raising=False)


def recordings(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
    ]


def counts(client: RecordedClient) -> dict[str, Any]:
    return dict(client.digline_counts)


# -- off ---------------------------------------------------------------------- #


@pytest.mark.usefixtures("off")
def test_off_the_call_passes_without_digline_keywords(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    reply = client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=QUESTION,
        suite="triage",
        digline_vars={"country": "France"},
    )
    assert reply.content[0].text == "Paris"  # pyright: ignore[reportAttributeAccessIssue]
    assert not (tmp_path / ".digline").exists()
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("off")
def test_off_the_sdk_would_refuse_digline_keywords(tmp_path: Path) -> None:
    # The control: the fake really refuses a keyword it does not know.
    with pytest.raises(TypeError, match="unexpected keyword argument 'suite'"):
        an_anthropic().messages.create(  # pyright: ignore[reportCallIssue]
            model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
        )


def test_off_nothing_of_digline_core_is_imported() -> None:
    program = (
        "import sys, anthropic, httpx2\n"
        "import digline.recorder as r\n"
        "body = " + repr(ANTHROPIC_REPLY) + "\n"
        "http = httpx2.Client(transport=httpx2.MockTransport("
        "lambda q: httpx2.Response(200, json=body)))\n"
        "c = r.wrap(anthropic.Anthropic(api_key='t', http_client=http), "
        "app='a', tenant='acme')\n"
        "c.messages.create(model='m', max_tokens=5, messages=[], suite='s')\n"
        "print(sorted(m for m in sys.modules if m.startswith('digline')))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", program],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "['digline', 'digline.recorder']"


#: The most that being wrapped and off may add to one call, in microseconds.
#: Measured at 0.45 µs on the machine this was written on (see the pull
#: request); the threshold is wide so that a slow runner does not turn it red,
#: and narrow enough that an import or a file read per call would.
OFF_OVERHEAD_MICROSECONDS = 25.0


@pytest.mark.usefixtures("off")
def test_off_costs_little_per_call(tmp_path: Path) -> None:
    bare = an_anthropic()
    reply = object()
    resource = bare.messages

    def create(**_: object) -> object:
        return reply

    resource.create = create
    wrapped = wrap(bare, app="support", tenant="acme", root=tmp_path)

    def per_call(call: Callable[[], object]) -> float:
        number = 20_000
        return min(timeit.repeat(call, number=number, repeat=5)) / number * 1e6

    plain = per_call(lambda: resource.create(model="m", messages=QUESTION))
    through = per_call(
        lambda: wrapped.messages.create(model="m", messages=QUESTION, suite="s")
    )
    assert through - plain < OFF_OVERHEAD_MICROSECONDS, (plain, through)


# -- on: one recording per provider ------------------------------------------- #


@pytest.mark.usefixtures("on")
def test_anthropic_is_recorded_in_three_compartments(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    reply = client.messages.create(
        model="claude-test",
        max_tokens=10,
        system="Answer in one word.",
        stop_sequences=["."],
        messages=QUESTION,
        metadata={"user_id": "u-42"},
        suite="triage",
    )
    assert reply.content[0].text == "Paris"  # pyright: ignore[reportAttributeAccessIssue]
    [written] = recordings(tmp_path)
    assert written["source_tenant"] == "acme"
    assert written["app"] == "support"
    assert written["suite"] == "triage"
    assert written["case"] == {"messages": QUESTION}
    assert written["setup"] == {
        "model": "claude-test",
        "max_tokens": 10,
        "system": "Answer in one word.",
        "stop_sequences": ["."],
    }
    assert written["response"]["output"] == "Paris"
    assert written["response"]["usage"] == {"input_tokens": 12, "output_tokens": 3}
    assert "call_site" not in written
    assert counts(client) == {
        "recorded": 1,
        "not_recorded": {},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("on")
def test_openai_moves_the_leading_instructions_into_the_setup(tmp_path: Path) -> None:
    client = wrap(an_openai(), app="support", tenant="acme", root=tmp_path)
    system = {"role": "system", "content": "Answer in one word."}
    client.chat.completions.create(
        model="gpt-test",
        messages=[system, *QUESTION],  # pyright: ignore[reportArgumentType]
        temperature=0,
        user="u-42",
        suite="triage",
    )
    [written] = recordings(tmp_path)
    assert written["case"] == {"messages": QUESTION}
    assert written["setup"] == {
        "model": "gpt-test",
        "temperature": 0,
        "system": [system],
    }
    assert written["response"]["output"] == "Paris"


@pytest.mark.usefixtures("on")
def test_bedrock_is_recorded_in_three_compartments(tmp_path: Path) -> None:
    bedrock, stubber = a_bedrock()
    client = wrap(bedrock, app="support", tenant="acme", root=tmp_path)
    messages = [{"role": "user", "content": [{"text": "Capital of France?"}]}]
    client.converse(
        modelId="model-test",
        messages=messages,
        system=[{"text": "Answer in one word."}],
        inferenceConfig={"maxTokens": 10},
        suite="triage",
    )
    stubber.assert_no_pending_responses()
    [written] = recordings(tmp_path)
    assert written["case"] == {"messages": messages}
    assert written["setup"] == {
        "modelId": "model-test",
        "system": [{"text": "Answer in one word."}],
        "inferenceConfig": {"maxTokens": 10},
    }
    assert written["response"]["output"] == "Paris"


@pytest.mark.usefixtures("on")
def test_digline_vars_join_the_case(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=QUESTION,
        suite="triage",
        digline_vars={"country": "France"},
    )
    [written] = recordings(tmp_path)
    assert written["case"] == {"messages": QUESTION, "vars": {"country": "France"}}
    assert "digline_vars" not in written["setup"]


@pytest.mark.usefixtures("on")
def test_the_digest_follows_the_setup_and_nothing_else(tmp_path: Path) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    for question in ("A?", "B?"):
        client.messages.create(
            model="claude-test",
            max_tokens=10,
            messages=[{"role": "user", "content": question}],
            suite="triage",
        )
    client.messages.create(
        model="claude-test",
        max_tokens=20,
        messages=QUESTION,
        suite="triage",
    )
    first, second, third = recordings(tmp_path)
    assert first["setup_digest"] == second["setup_digest"]
    assert first["case"] != second["case"]
    assert third["setup_digest"] != first["setup_digest"]


@pytest.mark.usefixtures("on")
def test_the_first_recording_lays_out_the_generated_gitignore(tmp_path: Path) -> None:
    # An empty directory and the variable alone: no `digline record on` and
    # no run has laid `.digline/` out. A defect of #874, found in the next
    # piece: the recording landed with no `.gitignore` beside it.
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )
    gitignore = (tmp_path / ".digline" / ".gitignore").read_text(encoding="utf-8")
    assert "*/recordings/" in gitignore.splitlines()
    assert "*/recorder.toml" in gitignore.splitlines()
    assert len(recordings(tmp_path)) == 1


@pytest.mark.usefixtures("off")
def test_a_tenant_function_decides_each_recordings_directory(tmp_path: Path) -> None:
    # A function is production, switched on per tenant by its file.
    for name in ("acme", "globex"):
        (tmp_path / ".digline" / name).mkdir(parents=True)
        (tmp_path / ".digline" / name / "recorder.toml").write_text(
            'on = true\nsample = 1\nredact = "none"\nceiling = 1000000\n',
            encoding="utf-8",
        )
    served = iter(["acme", "globex"])
    client = wrap(
        an_anthropic(), app="support", tenant=lambda: next(served), root=tmp_path
    )
    for _ in range(2):
        client.messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
        )
    tenants = sorted(p.name for p in (tmp_path / ".digline").iterdir() if p.is_dir())
    assert tenants == ["acme", "globex"]
    assert sorted(r["source_tenant"] for r in recordings(tmp_path)) == tenants


@pytest.mark.usefixtures("on")
def test_a_call_that_names_no_suite_is_unassigned_with_its_call_site(
    tmp_path: Path,
) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)

    def answer_the_customer() -> None:
        client.messages.create(model="claude-test", max_tokens=10, messages=QUESTION)

    answer_the_customer()
    [written] = recordings(tmp_path)
    assert written["suite"] == UNASSIGNED
    assert written["call_site"] == (
        f"{__name__}:test_a_call_that_names_no_suite_is_unassigned_with_its_call_site"
        ".<locals>.answer_the_customer"
    )


# -- the application's call never fails because of the recorder --------------- #


@pytest.mark.usefixtures("on")
def test_a_broken_writer_lets_the_call_through_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: RecordingWriter, recording: object) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(RecordingWriter, "write", broken)
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    reply = client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )
    assert reply.content[0].text == "Paris"  # pyright: ignore[reportAttributeAccessIssue]
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {"writer": 1},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("on")
def test_a_value_json_cannot_carry_lets_the_call_through_and_counts(
    tmp_path: Path,
) -> None:
    # The SDK sends a date as its ISO text; a recording refuses to rewrite it,
    # and says where it sits and what it is, not "not JSON". (P-1588)
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    reply = client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=[
            {"role": "user", "content": "q", "when": datetime.date(2026, 11, 2)}  # pyright: ignore[reportArgumentType]
        ],
        suite="triage",
    )
    assert reply.content[0].text == "Paris"  # pyright: ignore[reportAttributeAccessIssue]
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {"messages[0].when holds a date": 1},
        "orphan": 0,
        "noted": {},
    }
    assert recordings(tmp_path) == []


@pytest.mark.usefixtures("off")
def test_a_tenant_function_that_raises_lets_the_call_through(tmp_path: Path) -> None:
    (tmp_path / ".digline" / "acme").mkdir(parents=True)
    (tmp_path / ".digline" / "acme" / "recorder.toml").write_text(
        'on = true\nsample = 1\nredact = "none"\nceiling = 1000000\n',
        encoding="utf-8",
    )

    def tenant() -> str:
        raise LookupError("no customer on this request")

    client = wrap(an_anthropic(), app="support", tenant=tenant, root=tmp_path)
    client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {"tenant": 1},
        "orphan": 0,
        "noted": {},
    }


@pytest.mark.usefixtures("on")
def test_a_streamed_call_is_no_longer_streaming_not_recorded(tmp_path: Path) -> None:
    # The three plugins read a stream now (tests/test_recorder_streaming.py):
    # an empty one ends at once, unread, and is not recorded as "streaming".
    httpx2 = sdk("httpx2")

    def handle(request: object) -> Any:
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=b""
        )

    http = httpx2.Client(transport=httpx2.MockTransport(handle))
    client = wrap(
        sdk("anthropic").Anthropic(api_key="test", http_client=http),
        app="support",
        tenant="acme",
        root=tmp_path,
    )
    stream = client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, stream=True
    )
    assert isinstance(stream, sdk("anthropic").Stream)
    assert "streaming" not in counts(client)["not_recorded"]


@pytest.mark.usefixtures("on")
def test_an_sdk_error_propagates_and_nothing_is_recorded(tmp_path: Path) -> None:
    client = wrap(an_anthropic(status=400), app="support", tenant="acme", root=tmp_path)
    with pytest.raises(sdk("anthropic").BadRequestError):
        client.messages.create(
            model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
        )
    assert counts(client) == {
        "recorded": 0,
        "not_recorded": {},
        "orphan": 0,
        "noted": {},
    }
    assert not (tmp_path / ".digline").exists()


# -- refused when wrapped ----------------------------------------------------- #


def test_a_client_no_plugin_maps_is_refused_when_wrapped() -> None:
    # An aiobotocore client is one: no plugin declares it. Not installed here,
    # so a class of no plugin's stands for it.
    with pytest.raises(RecorderStartError, match="no installed plugin records"):
        wrap(object(), app="support", tenant="acme")


def test_a_switch_value_that_is_neither_on_nor_off_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "yes")
    with pytest.raises(RecorderStartError, match="neither 1"):
        wrap(an_anthropic(), app="support", tenant="acme")


@pytest.mark.parametrize(
    ("app", "tenant"), [("", "acme"), ("support", "")], ids=["app", "tenant"]
)
def test_an_empty_app_or_tenant_is_refused(app: str, tenant: str) -> None:
    with pytest.raises(RecorderStartError):
        wrap(an_anthropic(), app=app, tenant=tenant)


@pytest.mark.usefixtures("off")
def test_everything_else_is_the_clients_own(tmp_path: Path) -> None:
    bare = an_anthropic()
    client = wrap(bare, app="support", tenant="acme", root=tmp_path)
    assert client.api_key == "test"  # pyright: ignore[reportAttributeAccessIssue]
    assert client.messages.count_tokens == bare.messages.count_tokens  # pyright: ignore[reportAttributeAccessIssue]
