"""`AnthropicTarget`, with the SDK replaced by a stand-in.

No `anthropic` import and no socket: the client is injected, so what is checked
is the one method the plugin actually writes — the request it builds and the
tokens it reads back. The live test at the bottom is the only one that spends
money, and it does not run unless a key is in the environment.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from digline.run import Case
from digline.targets import ModelPrice, Pricing, Usage
from digline_anthropic import ANTHROPIC_PRICING, PRICES_READ_ON, AnthropicTarget


@dataclass
class FakeBlock:
    text: str
    type: str = "text"


@dataclass
class FakeUsage:
    """Shaped from the real reply, checked against it on 2026-08-27.

    `cache_creation_input_tokens` is here because the live probe found it and
    found that it is *not* part of `input_tokens`: a call that wrote a
    9202-token cache reported `input_tokens=10`. The fake had been missing it,
    and so had the code. (friction 25)
    """

    input_tokens: int = 1200
    output_tokens: int = 300
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeReply:
    content: list[FakeBlock]
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.reply = FakeReply(content=[FakeBlock("Rome.")])

    def create(self, **kwargs: Any) -> FakeReply:
        self.requests.append(kwargs)
        return self.reply


class FakeClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    path = tmp_path / "answer.md"
    path.write_text("What is the capital of {country}?\n", encoding="utf-8")
    return path


def a_target(prompt: Path, **kwargs: Any) -> tuple[AnthropicTarget, FakeClient]:
    client = FakeClient()
    target = AnthropicTarget(prompt, "claude-sonnet-5", 1024, client=client, **kwargs)
    return target, client


def test_the_request_carries_what_was_declared_and_nothing_else(prompt: Path) -> None:
    target, client = a_target(prompt, temperature=0.2)
    target(Case(id="it", vars={"country": "Italy"}))

    (request,) = client.messages.requests
    assert request["model"] == "claude-sonnet-5"
    assert request["max_tokens"] == 1024
    assert request["temperature"] == 0.2
    assert request["messages"] == [
        {"role": "user", "content": "What is the capital of Italy?\n"}
    ]
    # Absent rather than None: an unset option is not an option set to nothing.
    assert "system" not in request


def test_an_unset_temperature_is_not_sent(prompt: Path) -> None:
    target, client = a_target(prompt)
    target(Case(id="it", vars={"country": "Italy"}))
    assert "temperature" not in client.messages.requests[0]


def test_the_config_is_what_was_sent_and_nothing_else(prompt: Path) -> None:
    """What the run records about the system that answered (ADR 0005 §1).

    No `top_p`, no `top_k`, no `seed`, no `base_url`: this target sends none of
    them, and a configuration naming a parameter nobody passed would be a record
    of a run that did not happen.
    """
    target, _client = a_target(prompt, temperature=0.2)
    assert dict(target.config) == {
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "max_tokens": 1024,
        "temperature": 0.2,
    }


def test_an_unset_temperature_is_absent_from_the_config_too(prompt: Path) -> None:
    """Absent rather than `None`, exactly as in the request above: the record
    says what was sent, so the day a suite starts pinning a temperature the
    comparison reports it as `new` instead of as a value that was always there."""
    target, _client = a_target(prompt)
    assert "temperature" not in target.config


def test_a_system_file_is_rendered_sent_and_recorded(
    tmp_path: Path, prompt: Path
) -> None:
    system = tmp_path / "system.md"
    system.write_text("Answer for {country} in one line.", encoding="utf-8")
    target, client = a_target(prompt, system_file=system)

    target(Case(id="it", vars={"country": "Italy"}))
    assert client.messages.requests[0]["system"] == "Answer for Italy in one line."
    # And it is under test, so it is in the run: the system prompt is the part
    # that moves most.
    assert set(target.artifacts()) == {prompt, system}


def test_the_reply_becomes_a_priced_response(prompt: Path) -> None:
    target, client = a_target(prompt)
    client.messages.reply = FakeReply(
        content=[FakeBlock("Rome"), FakeBlock(", in Italy.")],
        usage=FakeUsage(input_tokens=1_000_000, output_tokens=0),
    )
    response = target(Case(id="it", vars={"country": "Italy"}))

    assert response.output == "Rome, in Italy."
    assert response.cost_usd == pytest.approx(3.0)
    assert response.metadata["model"] == "claude-sonnet-5"


def test_blocks_that_are_not_text_are_skipped(prompt: Path) -> None:
    """A tool-use block has no `.text`, and joining it in would put a repr in
    the output the assertions read."""
    target, client = a_target(prompt)
    client.messages.reply = FakeReply(
        content=[FakeBlock("said", "text"), FakeBlock("ignored", "tool_use")]
    )
    assert target(Case(id="it", vars={"country": "Italy"})).output == "said"


def test_cached_reads_are_counted_and_priced(prompt: Path) -> None:
    target, client = a_target(prompt)
    client.messages.reply = FakeReply(
        content=[FakeBlock("x")],
        usage=FakeUsage(
            input_tokens=0, output_tokens=0, cache_read_input_tokens=1_000_000
        ),
    )
    response = target(Case(id="it", vars={"country": "Italy"}))
    assert response.cost_usd == pytest.approx(0.30)
    assert response.metadata["cache_read_tokens"] == 1_000_000


def test_preflight_refuses_a_model_the_list_does_not_carry(prompt: Path) -> None:
    target = AnthropicTarget(prompt, "claude-from-the-future", 512, client=FakeClient())
    with pytest.raises(ValueError, match="has no price"):
        target.preflight([Case(id="it", vars={"country": "Italy"})])


def test_a_price_the_list_got_wrong_is_corrected_in_the_suite(prompt: Path) -> None:
    """The reason the list is a value and not a constant: it is a fact about a
    day, and the day passes."""
    corrected = ANTHROPIC_PRICING.override(
        "claude-sonnet-5", ModelPrice(1.0, 5.0, 0.10)
    )
    target, client = a_target(prompt)
    target = AnthropicTarget(
        prompt, "claude-sonnet-5", 1024, pricing=corrected, client=client
    )
    client.messages.reply = FakeReply(
        content=[FakeBlock("x")], usage=FakeUsage(1_000_000, 0)
    )
    assert target(Case(id="it", vars={"country": "Italy"})).cost_usd == pytest.approx(
        1.0
    )


def test_max_tokens_below_one_is_refused(prompt: Path) -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        AnthropicTarget(prompt, "claude-sonnet-5", 0, client=FakeClient())


def test_the_price_list_says_when_it_was_read() -> None:
    """A copy of a price list can only honestly carry the day it was copied."""
    assert PRICES_READ_ON.count("-") == 2
    assert ANTHROPIC_PRICING.knows("claude-sonnet-5")
    assert isinstance(ANTHROPIC_PRICING, Pricing)


def test_no_key_is_read_or_passed_by_this_package() -> None:
    """A key a suite could set is a key that ends up in a repository.

    The SDK reads the environment on its own. This package must neither read it
    nor accept one, so there is no argument anybody can hardcode. Naming the
    variable in a docstring is fine and is the point of the docstring.
    """
    source = Path(__file__).resolve().parents[1] / "src" / "digline_anthropic"
    for path in source.glob("*.py"):
        code = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "os.environ" not in code and "getenv" not in code, path.name
        assert "api_key" not in code, path.name


def test_the_sdk_is_imported_only_when_a_call_is_made(prompt: Path) -> None:
    """`digline list`, a preflight and this whole file must work without it."""
    import sys

    assert "anthropic" not in sys.modules
    target = AnthropicTarget(prompt, "claude-sonnet-5", 16, client=FakeClient())
    target.preflight([Case(id="it", vars={"country": "Italy"})])
    assert "anthropic" not in sys.modules


def sdk_installed() -> bool:
    return importlib.util.find_spec("anthropic") is not None


#: Two gates, not one. A key is present on any machine that has ever talked to
#: the provider, including CI and including a laptop where somebody is running
#: the suite for an unrelated reason — so the key alone would make `pytest`
#: spend money by surprise. `DIGLINE_LIVE=1` is the deliberate half.
LIVE = (
    bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("DIGLINE_LIVE") == "1"
)


@pytest.mark.live
@pytest.mark.skipif(
    not LIVE or not sdk_installed(),
    reason="needs ANTHROPIC_API_KEY, DIGLINE_LIVE=1 and the anthropic SDK",
)
def test_a_real_call_answers_and_is_priced(prompt: Path) -> None:
    """The one test that spends money. Everything above proves the shape; this
    proves the shape is the one the SDK actually has."""
    target = AnthropicTarget(prompt, "claude-haiku-4-5-20251001", 64)
    response = target(Case(id="it", vars={"country": "Italy"}))
    assert "Rome" in str(response.output)
    assert response.cost_usd is not None and response.cost_usd > 0
    assert response.latency_ms is not None and response.latency_ms > 0


def test_cache_writes_are_counted_and_priced(prompt: Path) -> None:
    """The bug the live probe found, in the shape the API actually returns.

    A cached call reports the cached tokens under `cache_creation_input_tokens`
    and leaves `input_tokens` tiny. Reading only `input_tokens` priced that call
    at a three-hundredth of what it cost — the direction that reads as good
    news, which is the one that survives review.
    """
    target = AnthropicTarget(
        prompt, "claude-haiku-4-5-20251001", 8, client=(client := FakeClient())
    )
    client.messages.reply = FakeReply(
        content=[FakeBlock("Rome")],
        usage=FakeUsage(
            input_tokens=10,
            output_tokens=4,
            cache_creation_input_tokens=9202,
        ),
    )
    response = target(Case(id="it", vars={"country": "Italy"}))
    assert response.metadata["cache_write_tokens"] == 9202
    # 10 in + 4 out + 9202 written at 1.25/Mtok, not 10 in + 4 out.
    assert response.cost_usd == pytest.approx(0.011532, abs=1e-6)


def test_a_prefill_is_sent_and_prepended_to_the_reply(prompt: Path) -> None:
    """`"{"` in the assistant's mouth is how you get JSON out of a model, and
    the reply *is* the prefill plus the completion: a parser handed only the
    tail sees invalid JSON. (friction 27)"""
    target = AnthropicTarget(
        prompt,
        "claude-sonnet-5",
        64,
        prefill="{",
        client=(client := FakeClient()),
    )
    client.messages.reply = FakeReply(content=[FakeBlock('"score": 4}')])
    response = target(Case(id="it", vars={"country": "Italy"}))

    assert client.messages.requests[0]["messages"][-1] == {
        "role": "assistant",
        "content": "{",
    }
    assert response.output == '{"score": 4}'


def test_without_a_prefill_no_assistant_turn_is_sent(prompt: Path) -> None:
    target, client = a_target(prompt)
    target(Case(id="it", vars={"country": "Italy"}))
    roles = [m["role"] for m in client.messages.requests[0]["messages"]]
    assert roles == ["user"]


def test_the_alias_and_the_dated_id_are_both_priced() -> None:
    """A suite is written with whichever id its author had in front of them, and
    an alias missing from the list fails `preflight` for a reason that has
    nothing to do with the suite. (friction 28)"""
    assert ANTHROPIC_PRICING.knows("claude-haiku-4-5")
    assert ANTHROPIC_PRICING.knows("claude-haiku-4-5-20251001")
    assert ANTHROPIC_PRICING.cost(
        "claude-haiku-4-5", Usage(1_000_000, 0)
    ) == ANTHROPIC_PRICING.cost("claude-haiku-4-5-20251001", Usage(1_000_000, 0))
