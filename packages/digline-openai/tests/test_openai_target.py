"""`OpenAITarget`, with the SDK replaced by a stand-in.

What is checked is the one method the plugin actually writes — the request it
builds and the tokens it reads back — plus the two things `base_url` brings with
it: which argument carries the output cap, and how a key is resolved when there
may not be one. The live test at the bottom is the only one that spends money,
and it does not run unless a key is in the environment *and* somebody asked.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from _fakes import (
    FakeChoice,
    FakeClient,
    FakeDetails,
    FakeMessage,
    FakeReply,
    FakeUsage,
)

from digline.run import Case
from digline.targets import ModelPrice, Pricing, Usage
from digline_openai import (
    NO_KEY,
    OPENAI_PRICING,
    PRICES_READ_ON,
    OpenAITarget,
    free,
)
from digline_openai.client import build_client, usage_of

OLLAMA = "http://localhost:11434/v1"


def a_target(prompt: Path, client: FakeClient, **kwargs: Any) -> OpenAITarget:
    return OpenAITarget(prompt, "gpt-5", 1024, client=client, **kwargs)


def a_case() -> Case:
    return Case(id="it", vars={"country": "Italy"})


# -- the request --------------------------------------------------------------- #


def test_the_request_carries_what_was_declared_and_nothing_else(
    prompt: Path, client: FakeClient
) -> None:
    a_target(prompt, client, temperature=0.2)(a_case())

    (request,) = client.completions.requests
    assert request["model"] == "gpt-5"
    assert request["messages"] == [
        {"role": "user", "content": "What is the capital of Italy?\n"}
    ]
    assert request["temperature"] == 0.2
    # Absent rather than None: an unset option is not an option set to nothing.
    assert "response_format" not in request
    assert not any(m["role"] == "system" for m in request["messages"])


def test_an_unset_temperature_is_not_sent(prompt: Path, client: FakeClient) -> None:
    """gpt-5 refuses a temperature that is not 1, so sending a default would
    make the plugin unusable on the model in its own README."""
    a_target(prompt, client)(a_case())
    assert "temperature" not in client.completions.requests[0]


def test_a_system_file_is_rendered_sent_and_recorded(
    tmp_path: Path, prompt: Path, client: FakeClient
) -> None:
    system = tmp_path / "system.md"
    system.write_text("Answer for {country} in one line.", encoding="utf-8")
    target = a_target(prompt, client, system_file=system)

    target(a_case())
    assert client.completions.requests[0]["messages"][0] == {
        "role": "system",
        "content": "Answer for Italy in one line.",
    }
    # And it is under test, so it is in the run.
    assert set(target.artifacts()) == {prompt, system}


def test_the_official_endpoint_gets_max_completion_tokens(
    prompt: Path, client: FakeClient
) -> None:
    """The official API rejects `max_tokens` for GPT-5 and the o-series."""
    a_target(prompt, client)(a_case())
    request = client.completions.requests[0]
    assert request["max_completion_tokens"] == 1024
    assert "max_tokens" not in request


def test_a_custom_endpoint_gets_max_tokens(prompt: Path, client: FakeClient) -> None:
    """The failure the other way round is the expensive one: a compatible
    server that does not know `max_completion_tokens` ignores it and generates
    without a cap, which does not raise — it bills."""
    a_target(prompt, client, base_url=OLLAMA, pricing=free("gpt-5"))(a_case())
    request = client.completions.requests[0]
    assert request["max_tokens"] == 1024
    assert "max_completion_tokens" not in request


def test_the_token_argument_can_be_named_explicitly(
    prompt: Path, client: FakeClient
) -> None:
    a_target(prompt, client, token_param="max_tokens")(a_case())
    assert "max_tokens" in client.completions.requests[0]


def test_extra_body_reaches_the_request(prompt: Path, client: FakeClient) -> None:
    """Compatible providers have arguments the SDK never heard of — a routing
    preference on OpenRouter, `num_ctx` on Ollama."""
    a_target(prompt, client, extra_body={"top_p": 0.1})(a_case())
    assert client.completions.requests[0]["top_p"] == 0.1


# -- the reply ----------------------------------------------------------------- #


def test_the_reply_becomes_a_priced_response(prompt: Path, client: FakeClient) -> None:
    client.completions.reply = FakeReply(
        usage=FakeUsage(prompt_tokens=1_000_000, completion_tokens=0)
    )
    response = a_target(prompt, client)(a_case())

    assert response.output == "Rome."
    assert response.cost_usd == pytest.approx(1.25)
    assert response.metadata["model"] == "gpt-5"
    assert response.latency_ms is not None and response.latency_ms >= 0


def test_cached_tokens_are_subtracted_before_they_are_priced(
    prompt: Path, client: FakeClient
) -> None:
    """The convention that is the opposite of Anthropic's, and the one that is
    invisible in the direction of good news if you get it wrong.

    OpenAI counts cached prompt tokens **inside** `prompt_tokens`. Adding the
    two straight would bill the cached 800k at the full rate *and* again at the
    discounted one — 1.10 USD instead of 0.35.
    """
    client.completions.reply = FakeReply(
        usage=FakeUsage(
            prompt_tokens=1_000_000,
            completion_tokens=0,
            prompt_tokens_details=FakeDetails(cached_tokens=800_000),
        )
    )
    response = a_target(prompt, client)(a_case())

    assert response.metadata["input_tokens"] == 200_000
    assert response.metadata["cache_read_tokens"] == 800_000
    # 200k at 1.25 + 800k at 0.125.
    assert response.cost_usd == pytest.approx(0.35)


def test_a_reply_with_no_usage_is_refused(prompt: Path, client: FakeClient) -> None:
    """A compatible server that reports nothing would otherwise price the run
    at zero, and a zero passes every budget there is."""
    client.completions.reply = FakeReply(usage=None)
    with pytest.raises(ValueError, match="no usage"):
        a_target(prompt, client)(a_case())


def test_a_reply_with_no_usage_is_fine_when_the_model_is_free(
    prompt: Path, client: FakeClient
) -> None:
    """Because then zero is not an undercount, it is the price."""
    client.completions.reply = FakeReply(usage=None)
    target = OpenAITarget(
        prompt, "llama3.2", 64, base_url=OLLAMA, pricing=free("llama3.2"), client=client
    )
    assert target(a_case()).cost_usd == 0.0


def test_no_choices_is_an_error_and_empty_content_is_not(
    prompt: Path, client: FakeClient
) -> None:
    """Two different failures. Nothing to read is a broken call; a model that
    said nothing is an output the assertions get to fail."""
    client.completions.reply = FakeReply(choices=[])
    with pytest.raises(ValueError, match="no choices"):
        a_target(prompt, client)(a_case())

    client.completions.reply = FakeReply(choices=[FakeChoice(FakeMessage(None))])
    assert a_target(prompt, client)(a_case()).output == ""


# -- pricing -------------------------------------------------------------------- #


def test_preflight_refuses_a_model_the_list_does_not_carry(
    prompt: Path, client: FakeClient
) -> None:
    target = OpenAITarget(prompt, "gpt-6-from-the-future", 512, client=client)
    with pytest.raises(ValueError, match="has no price"):
        target.preflight([a_case()])


def test_a_price_the_list_got_wrong_is_corrected_in_the_suite(
    prompt: Path, client: FakeClient
) -> None:
    corrected = OPENAI_PRICING.override("gpt-5", ModelPrice(1.0, 5.0, 0.10))
    client.completions.reply = FakeReply(
        usage=FakeUsage(prompt_tokens=1_000_000, completion_tokens=0)
    )
    target = a_target(prompt, client, pricing=corrected)
    assert target(a_case()).cost_usd == pytest.approx(1.0)


def test_free_prices_a_self_hosted_model_at_zero_and_says_so(
    prompt: Path, client: FakeClient
) -> None:
    pricing = free("llama3.2", "qwen3")
    assert pricing.knows("llama3.2") and pricing.knows("qwen3")
    assert pricing.cost("llama3.2", Usage(1_000_000, 1_000_000)) == 0.0
    target = OpenAITarget(
        prompt, "llama3.2", 64, base_url=OLLAMA, pricing=pricing, client=client
    )
    target.preflight([a_case()])
    assert target(a_case()).cost_usd == 0.0


def test_free_with_no_model_is_refused() -> None:
    """An empty price list knows nothing, and every model would fail preflight
    with a message about a list that was never filled in."""
    with pytest.raises(ValueError, match="at least one model"):
        free()


def test_the_price_list_says_when_it_was_read() -> None:
    assert PRICES_READ_ON.count("-") == 2
    assert OPENAI_PRICING.knows("gpt-5") and OPENAI_PRICING.knows("gpt-5-mini")
    assert isinstance(OPENAI_PRICING, Pricing)


def test_the_alias_and_the_dated_id_are_both_priced() -> None:
    """A suite is written with whichever id its author had in front of them."""
    assert OPENAI_PRICING.cost("gpt-4o", Usage(1_000_000, 0)) == OPENAI_PRICING.cost(
        "gpt-4o-2024-08-06", Usage(1_000_000, 0)
    )


def test_cache_writes_are_not_a_tier_this_provider_has(
    prompt: Path, client: FakeClient
) -> None:
    """`None` rather than `0.0` in the price list: a rate of zero would price a
    counted token at nothing, where `None` makes it raise. Nothing counts them
    here, and that is the point — the list does not claim a tier that does not
    exist."""
    assert OPENAI_PRICING.per_model["gpt-5"].cache_write_per_mtok is None
    assert a_target(prompt, client)(a_case()).metadata["cache_write_tokens"] == 0


# -- the key -------------------------------------------------------------------- #


def test_no_key_is_read_by_this_package() -> None:
    """The convention `digline-anthropic` set, kept in substance.

    This package accepts an `api_key` argument — Azure and OpenRouter name their
    variable something else, so there has to be a way to say it — but it never
    goes looking in the environment. What the SDK reads on its own is the SDK's
    business, and its message for a missing key is better than ours would be.

    Read as **code**, not as text: the docstrings in this package say
    "no `os.environ`" on purpose, and a substring search would be a test that
    forbids explaining the rule it enforces.
    """
    import ast

    source = Path(__file__).resolve().parents[1] / "src" / "digline_openai"
    checked = 0
    for path in sorted(source.glob("*.py")):
        checked += 1
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"environ", "getenv"}, path.name
            elif isinstance(node, ast.Name):
                assert node.id not in {"environ", "getenv"}, path.name
            elif isinstance(node, ast.Import):
                assert all(a.name != "os" for a in node.names), path.name
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "os", path.name
    assert checked >= 4, "no sources were read; this test would prove nothing"


def test_the_key_never_appears_in_a_repr(prompt: Path, client: FakeClient) -> None:
    """A `repr` ends up in a traceback, a pytest failure and a log line."""
    secret = "sk-do-not-print-me"
    target = a_target(prompt, client, api_key=secret, base_url=OLLAMA)
    assert secret not in repr(target) and secret not in str(target)
    assert secret not in repr(target.chat) and secret not in str(target.chat)


def test_the_key_never_reaches_the_response(prompt: Path, client: FakeClient) -> None:
    secret = "sk-do-not-print-me"
    response = a_target(prompt, client, api_key=secret)(a_case())
    assert secret not in repr(response)


@dataclass
class FakeSdk:
    """How the SDK was constructed, and the error it raises for a missing key."""

    built: list[dict[str, Any]]
    error: type[Exception]


def fake_sdk(monkeypatch: pytest.MonkeyPatch, *, has_env_key: bool) -> FakeSdk:
    """A stand-in for the `openai` module, recording how it was constructed.

    Built here rather than imported: these five cases are about *what this
    package passes to the SDK*, and the real SDK would answer them by reading
    the environment of whoever is running the tests.
    """
    built: list[dict[str, Any]] = []

    class OpenAIError(Exception):
        pass

    class OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            if "api_key" not in kwargs and not has_env_key:
                raise OpenAIError("api_key client option must be set")
            built.append(kwargs)

    module = types.ModuleType("openai")
    module.OpenAI = OpenAI  # type: ignore[attr-defined]
    module.OpenAIError = OpenAIError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    return FakeSdk(built, OpenAIError)


def test_an_explicit_key_is_the_one_that_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = fake_sdk(monkeypatch, has_env_key=False)
    build_client(None, "sk-explicit")
    assert sdk.built == [{"api_key": "sk-explicit"}]


def test_the_official_endpoint_lets_the_sdk_resolve_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`None` goes to the SDK and the SDK reads `OPENAI_API_KEY` itself."""
    sdk = fake_sdk(monkeypatch, has_env_key=True)
    build_client(None, None)
    assert sdk.built == [{}]


def test_the_official_endpoint_raises_the_sdk_s_own_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No sentinel here: a missing key against api.openai.com is a mistake, and
    the SDK's message says so better than we would."""
    sdk = fake_sdk(monkeypatch, has_env_key=False)
    with pytest.raises(sdk.error):
        build_client(None, None)


def test_a_local_endpoint_without_a_key_falls_back_to_the_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = fake_sdk(monkeypatch, has_env_key=False)
    build_client(OLLAMA, None)
    assert sdk.built == [{"base_url": OLLAMA, "api_key": NO_KEY}]
    assert "digline" in NO_KEY, "the sentinel has to be obviously not a credential"


def test_a_custom_endpoint_still_prefers_the_key_the_sdk_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order is the whole trick: the sentinel is only reached *after* the
    SDK has looked, so OpenRouter with `OPENAI_API_KEY` set still
    authenticates."""
    sdk = fake_sdk(monkeypatch, has_env_key=True)
    build_client("https://openrouter.ai/api/v1", None)
    assert sdk.built == [{"base_url": "https://openrouter.ai/api/v1"}]


# -- laziness -------------------------------------------------------------------- #


def test_the_sdk_is_imported_only_when_a_call_is_made(prompt: Path) -> None:
    """`digline list`, a preflight and this whole file must work without it."""
    assert "openai" not in sys.modules
    target = OpenAITarget(prompt, "gpt-5", 16, client=FakeClient())
    target.preflight([a_case()])
    assert "openai" not in sys.modules


def test_max_tokens_below_one_is_refused(prompt: Path, client: FakeClient) -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        OpenAITarget(prompt, "gpt-5", 0, client=client)


def test_usage_of_reads_what_it_is_given() -> None:
    """The one function that touches the SDK's shape, called directly."""
    reply = FakeReply(
        usage=FakeUsage(
            prompt_tokens=100,
            completion_tokens=7,
            prompt_tokens_details=FakeDetails(cached_tokens=40),
        )
    )
    assert usage_of(reply, "gpt-5", OPENAI_PRICING) == Usage(
        input_tokens=60, output_tokens=7, cache_read_tokens=40, cache_write_tokens=0
    )


# -- the one that spends money ---------------------------------------------------- #


def sdk_installed() -> bool:
    return importlib.util.find_spec("openai") is not None


#: Two gates, not one. A key is present on any machine that has ever talked to
#: the provider, including CI and including a laptop where somebody is running
#: the suite for an unrelated reason — so the key alone would make `pytest`
#: spend money by surprise. `DIGLINE_LIVE=1` is the deliberate half.
LIVE = bool(os.environ.get("OPENAI_API_KEY")) and os.environ.get("DIGLINE_LIVE") == "1"


@pytest.mark.live
@pytest.mark.skipif(
    not LIVE or not sdk_installed(),
    reason="needs OPENAI_API_KEY, DIGLINE_LIVE=1 and the openai SDK",
)
def test_a_real_call_answers_and_is_priced(prompt: Path) -> None:
    """The one test that spends money. Everything above proves the shape; this
    proves the shape is the one the SDK actually has."""
    target = OpenAITarget(prompt, "gpt-4o-mini", 64)
    response = target(a_case())
    assert "Rome" in str(response.output)
    assert response.cost_usd is not None and response.cost_usd > 0
    assert response.latency_ms is not None and response.latency_ms > 0
