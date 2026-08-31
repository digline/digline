"""`BedrockTarget`, with the Converse call replaced by a stand-in.

What is checked is the one method the plugin writes — the request it builds and
the tokens it reads back — plus the three things Bedrock brings with it: the
region resolved at construction, the price list chosen by that region, and an
AWS failure whose message must not carry an account out of `_complete`.

The live test at the bottom is the only one that spends money, and it does not
run unless credentials are present *and* somebody asked.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest
from _bedrock_fakes import FakeClient, converse_reply

from digline.run import Case
from digline.targets import ModelPrice, Pricing, Usage
from digline_bedrock import (
    BASE_PRICES,
    PRICES_READ_ON,
    SEEDED_REGIONS,
    BedrockCallFailed,
    BedrockTarget,
    bedrock_pricing,
    free,
    scrub,
)
from digline_bedrock.client import resolve_region, text_of, usage_of

SONNET = "anthropic.claude-sonnet-4-20250514-v1:0"
EU_SONNET = f"eu.{SONNET}"


def a_target(prompt: Path, client: FakeClient, **kwargs: Any) -> BedrockTarget:
    return BedrockTarget(prompt, EU_SONNET, 1024, client=client, **kwargs)


def a_case() -> Case:
    return Case(id="it", vars={"country": "Italy"})


# -- the request ------------------------------------------------------- #


def test_the_request_is_a_converse_call_with_what_was_declared(
    prompt: Path, client: FakeClient
) -> None:
    a_target(prompt, client, temperature=0.2)(a_case())

    (request,) = client.requests
    assert request["modelId"] == EU_SONNET
    assert request["messages"] == [
        {"role": "user", "content": [{"text": "What is the capital of Italy?\n"}]}
    ]
    assert request["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0.2}
    # Absent rather than empty: an unset option is not an option set to nothing.
    assert "system" not in request
    assert "additionalModelRequestFields" not in request


def test_an_unset_temperature_is_not_sent(prompt: Path, client: FakeClient) -> None:
    a_target(prompt, client)(a_case())
    assert client.requests[0]["inferenceConfig"] == {"maxTokens": 1024}


def test_a_system_file_is_rendered_sent_and_recorded(
    tmp_path: Path, prompt: Path, client: FakeClient
) -> None:
    system = tmp_path / "system.md"
    system.write_text("Answer for {country} in one line.", encoding="utf-8")
    target = a_target(prompt, client, system_file=system)

    target(a_case())
    assert client.requests[0]["system"] == [{"text": "Answer for Italy in one line."}]
    assert set(target.artifacts()) == {prompt, system}


def test_additional_request_fields_reach_the_request(
    prompt: Path, client: FakeClient
) -> None:
    """They change what the model does, and they reach neither `config_hash`
    nor `target_config`: the fingerprint covers the rules that judge (ADR 0003
    §3), and the record covers what the plugin's own signature names (ADR 0005
    §1). The two tests below pin both halves."""
    a_target(prompt, client, additional_request_fields={"top_k": 20})(a_case())
    assert client.requests[0]["additionalModelRequestFields"] == {"top_k": 20}


def test_the_fields_do_not_reach_the_recorded_config_hash(prompt: Path) -> None:
    """The stated contract, pinned end to end so nobody has to trust prose.

    `Run.config_hash` comes from `Suite.config_hash()`, which is built from the
    assertions, their thresholds and tolerances, and `samples` — never from the
    target. Two runs of the same suite against targets that differ in
    `additional_request_fields` therefore record the **same** hash, and
    `compare()` will say the configuration is unchanged. That is ADR 0003 §3 and
    it is what the argument's docstring promises; this test fails the day it
    stops being true, which is the day ADR 0005 has to have been written.
    """
    from digline.core import Contains
    from digline.run import Suite, execute

    suite = Suite(
        tenant="t",
        environment="test",
        name="s",
        assertions=[Contains("Rome")],
        cases=[a_case()],
    )
    plain = execute(
        suite, a_target(prompt, FakeClient()), created_at="2026-08-28T00:00:00Z"
    )
    with_fields = execute(
        suite,
        a_target(prompt, FakeClient(), additional_request_fields={"top_k": 20}),
        created_at="2026-08-28T00:00:00Z",
    )
    assert plain.config_hash == with_fields.config_hash


def test_the_fields_do_not_reach_the_recorded_target_config(prompt: Path) -> None:
    """The sibling ADR 0005 §1 promised, and the other half of the contract.

    Recording the configuration of the system under test does **not** mean
    recording everything sent to it. `additional_request_fields` is the escape
    hatch — whatever Converse takes and this signature does not name — so it is
    outside the contract, and what is outside the contract is outside the
    record. What *is* recorded is named, closed and diffable by value.
    """
    from digline.core import Contains
    from digline.run import Suite, execute

    suite = Suite(
        tenant="t",
        environment="test",
        name="s",
        assertions=[Contains("Rome")],
        cases=[a_case()],
    )
    with_fields = execute(
        suite,
        a_target(prompt, FakeClient(), additional_request_fields={"top_k": 20}),
        created_at="2026-08-31T00:00:00Z",
    )
    assert "top_k" not in with_fields.target_config.values
    assert with_fields.target_config.values == {
        "provider": "bedrock",
        "model": EU_SONNET,
        "max_tokens": 1024,
        "region": "eu-west-1",
    }


def test_the_config_declares_the_region_it_was_priced_in(prompt: Path) -> None:
    """The region is part of the answer, not decoration: the same model id in
    two regions is two price lists and, behind an inference profile, two
    systems."""
    target = a_target(prompt, FakeClient(region="us-east-1"), temperature=0.2)
    assert target.config["region"] == "us-east-1"
    assert target.config["temperature"] == 0.2


def test_an_unset_parameter_is_absent_rather_than_none(prompt: Path) -> None:
    """ "We did not send it, so the provider's default applied" and "we sent
    nothing for it" are different facts, and only absence states the first."""
    assert "temperature" not in a_target(prompt, FakeClient()).config


# -- the reply --------------------------------------------------------- #


def test_the_reply_becomes_a_priced_response(prompt: Path, client: FakeClient) -> None:
    client.reply = converse_reply(input_tokens=1_000_000, output_tokens=0)
    response = a_target(prompt, client)(a_case())

    assert response.output == "Rome."
    assert response.cost_usd == pytest.approx(3.0)
    assert response.metadata["model"] == EU_SONNET
    assert response.latency_ms is not None and response.latency_ms >= 0


def test_blocks_without_text_are_skipped(prompt: Path, client: FakeClient) -> None:
    """A `reasoningContent` block has no `text` key, and joining it in would put
    the model's private reasoning into the output the assertions read."""
    client.reply = converse_reply()
    client.reply["output"]["message"]["content"] = [
        {"text": "Rome"},
        {"reasoningContent": {"reasoningText": {"text": "let me think"}}},
        {"text": ", in Italy."},
    ]
    assert a_target(prompt, client)(a_case()).output == "Rome, in Italy."


def test_a_reply_with_no_usage_is_refused(prompt: Path, client: FakeClient) -> None:
    client.reply = converse_reply(usage=False)
    with pytest.raises(ValueError, match="no usage"):
        a_target(prompt, client)(a_case())


def test_a_reply_with_no_usage_is_fine_when_the_model_has_no_token_price(
    prompt: Path, client: FakeClient
) -> None:
    """Provisioned throughput and imported models are billed by the hour: zero
    is not an undercount there, it is the per-token price."""
    client.reply = converse_reply(usage=False)
    target = BedrockTarget(
        prompt,
        "my-imported-model",
        64,
        client=client,
        pricing=free("my-imported-model"),
    )
    assert target(a_case()).cost_usd == 0.0


def test_a_reply_with_no_output_is_an_error(prompt: Path, client: FakeClient) -> None:
    client.reply = {"usage": {"inputTokens": 1, "outputTokens": 1}}
    with pytest.raises(ValueError, match="no `output`"):
        a_target(prompt, client)(a_case())


def test_cache_tokens_are_counted_under_the_stated_convention(
    prompt: Path, client: FakeClient
) -> None:
    """Cached reads are counted **beside** `inputTokens`, not inside them.

    Measured against the API on 2026-08-28 (eu-south-1): a call answering from
    a warm cache reported `inputTokens=10` beside `cacheReadInputTokens=12002`,
    with `totalTokens=12016` — the sum of the three. So nothing is subtracted:
    the Anthropic convention, and the opposite of OpenAI's, where the same test
    in `digline-openai` asserts a subtraction.

    The full million is therefore billed at the input rate *plus* the cached
    800k at the cache-read rate. Getting this backwards would report the call
    at a fifth of its cost — the direction that reads as good news, which is
    the one that survives review (friction 25).
    """
    client.reply = converse_reply(
        input_tokens=1_000_000, output_tokens=0, cache_read=800_000
    )
    response = a_target(prompt, client)(a_case())

    assert response.metadata["input_tokens"] == 1_000_000
    assert response.metadata["cache_read_tokens"] == 800_000
    # 1M at 3.00 + 800k at 0.30.
    assert response.cost_usd == pytest.approx(3.0 + 0.24)


def test_cache_writes_are_priced(prompt: Path, client: FakeClient) -> None:
    client.reply = converse_reply(
        input_tokens=0, output_tokens=0, cache_write=1_000_000
    )
    assert a_target(prompt, client)(a_case()).cost_usd == pytest.approx(3.75)


# -- the region -------------------------------------------------------- #


def test_the_region_comes_from_the_client_and_is_read_only(
    prompt: Path, client: FakeClient
) -> None:
    target = a_target(prompt, client)
    assert target.region == "eu-west-1"
    with pytest.raises(AttributeError):
        target.region = "us-east-1"  # type: ignore[misc]


def test_a_client_with_no_region_fails_at_construction(prompt: Path) -> None:
    """Not at the first call: a configuration error must surface before the
    first paid call, which is the whole point of `preflight`."""
    with pytest.raises(ValueError, match="no region"):
        BedrockTarget(prompt, EU_SONNET, 64, client=FakeClient(region=None))


def test_a_region_that_contradicts_the_client_is_refused(prompt: Path) -> None:
    with pytest.raises(ValueError, match="one too many"):
        BedrockTarget(
            prompt, EU_SONNET, 64, client=FakeClient("eu-west-1"), region="us-east-1"
        )


def test_the_price_list_is_the_one_of_the_region_that_was_called(
    prompt: Path,
) -> None:
    """`eu.` and `us.` profile ids are not interchangeable in a price list: the
    list a target gets is built for the region its client is in."""
    eu = a_target(prompt, FakeClient("eu-west-1"))
    assert eu.pricing.knows(EU_SONNET) and eu.pricing.knows(SONNET)
    assert not eu.pricing.knows(f"us.{SONNET}")

    us = BedrockTarget(prompt, f"us.{SONNET}", 64, client=FakeClient("us-east-1"))
    assert us.pricing.knows(f"us.{SONNET}")
    assert not us.pricing.knows(EU_SONNET)


def test_resolve_region_refuses_a_client_that_has_none() -> None:
    with pytest.raises(ValueError, match="no region"):
        resolve_region(FakeClient(region=None))


# -- pricing ----------------------------------------------------------- #


def test_an_unseeded_region_says_it_is_the_region_that_is_missing() -> None:
    """Not "unknown model": the thing that is missing is a region, and a
    message about the model would send the reader to fix the wrong line."""
    with pytest.raises(ValueError, match="no seeded price list for region"):
        bedrock_pricing("sa-east-1")


def test_every_seeded_region_prices_every_base_model() -> None:
    for region in SEEDED_REGIONS:
        pricing = bedrock_pricing(region)
        for model in BASE_PRICES:
            assert pricing.knows(model), (region, model)


def test_an_application_inference_profile_arn_is_not_priced(
    prompt: Path, client: FakeClient
) -> None:
    """Opaque by construction, so it can only be served with an explicit price —
    and `preflight` says so before the first paid call, which is the intended
    behaviour and not a gap."""
    arn = "arn:aws:bedrock:eu-west-1:123456789012:application-inference-profile/abc"
    target = BedrockTarget(prompt, arn, 64, client=client)
    with pytest.raises(ValueError, match="has no price"):
        target.preflight([a_case()])

    priced = BedrockTarget(
        prompt,
        arn,
        64,
        client=client,
        pricing=bedrock_pricing("eu-west-1").override(arn, ModelPrice(3.0, 15.0)),
    )
    priced.preflight([a_case()])


def test_free_prices_an_imported_model_at_zero() -> None:
    pricing = free("my-imported-model")
    assert pricing.cost("my-imported-model", Usage(1_000_000, 1_000_000)) == 0.0


def test_free_with_no_model_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        free()


def test_the_price_list_says_when_it_was_read() -> None:
    assert PRICES_READ_ON.count("-") == 2
    assert isinstance(bedrock_pricing("eu-west-1"), Pricing)


# -- credentials ------------------------------------------------------- #


def test_no_credential_is_read_or_accepted_by_this_package() -> None:
    """The convention the other two plugins set, in AWS's vocabulary.

    Read as **code**, not as text: the docstrings name these things on purpose,
    and a substring search would forbid explaining the rule it enforces.
    """
    source = Path(__file__).resolve().parents[1] / "src" / "digline_bedrock"
    forbidden_names = {
        "environ",
        "getenv",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
    }
    checked = 0
    for path in sorted(source.glob("*.py")):
        checked += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_names, path.name
            elif isinstance(node, ast.Name):
                assert node.id not in forbidden_names, path.name
            elif isinstance(node, ast.keyword):
                assert node.arg not in forbidden_names, path.name
            elif isinstance(node, ast.Import):
                assert all(a.name != "os" for a in node.names), path.name
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "os", path.name
    assert checked >= 4, "no sources were read; this test would prove nothing"


def test_the_repr_shows_the_model_and_the_region_and_nothing_else(
    prompt: Path, client: FakeClient
) -> None:
    target = a_target(prompt, client)
    printed = repr(target) + str(target) + repr(target.chat)
    assert "eu-west-1" in printed and EU_SONNET in printed
    assert "FakeClient" not in printed and "meta" not in printed


# -- the scrub --------------------------------------------------------- #


DENIED = (
    "An error occurred (AccessDeniedException) when calling the Converse "
    "operation: User: arn:aws:sts::123456789012:assumed-role/digline-ci/session "
    "is not authorized to perform: bedrock:InvokeModel on resource: "
    "arn:aws:bedrock:eu-west-1:123456789012:inference-profile/eu.anthropic.claude"
)


def test_an_arn_does_not_escape_the_call(prompt: Path, client: FakeClient) -> None:
    """The one that matters, and the reason this plugin has a scrub at all.

    The driver quotes a target's exception into the `reason` of every verdict of
    the case, and a `reason` lands in a committed run artifact. A botocore
    message names the assumed role — which is the customer's AWS account, in a
    file that goes through code review.
    """
    client.raises = RuntimeError(DENIED)
    with pytest.raises(BedrockCallFailed) as caught:
        a_target(prompt, client)(a_case())

    message = str(caught.value)
    assert "arn:aws" not in message
    assert "123456789012" not in message
    # What survives is what a reader needs: the failure and its shape.
    assert "AccessDeniedException" in message and "RuntimeError" in message
    # The original stays reachable in-process, for a debugger. It is never
    # serialised, so it never reaches the run file.
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "123456789012" in str(caught.value.__cause__)


def test_the_scrubbed_message_is_what_reaches_the_verdicts(
    prompt: Path, client: FakeClient
) -> None:
    """End to end through the driver, because that is where the leak would
    happen: `execute()` writes the exception text into every verdict."""
    from digline.core import Contains
    from digline.run import Suite, execute

    client.raises = RuntimeError(DENIED)
    suite = Suite(
        tenant="t",
        environment="test",
        name="s",
        assertions=[Contains("Rome")],
        cases=[a_case()],
    )
    run = execute(suite, a_target(prompt, client), created_at="2026-08-28T00:00:00Z")

    reasons = [v.reason for r in run.results for v in r.verdicts]
    assert reasons, "the driver produced no verdict to inspect"
    for reason in reasons:
        assert "arn:aws" not in reason and "123456789012" not in reason


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("arn:aws:iam::123456789012:role/x said no", "<arn> said no"),
        ("account 123456789012 is not enabled", "account <account> is not enabled"),
        ("arn:aws-cn:sts::210987654321:assumed-role/y", "<arn>"),
        ("nothing to hide here", "nothing to hide here"),
        ("model anthropic.claude-3-5-haiku-20241022-v1:0", None),
    ],
)
def test_scrub_removes_accounts_and_leaves_the_rest(
    text: str, expected: str | None
) -> None:
    """The last case is the one that matters in the other direction: a model id
    carries digits and dashes and must come out untouched."""
    scrubbed = scrub(text)
    if expected is None:
        assert scrubbed == text
    else:
        assert scrubbed == expected


# -- construction ------------------------------------------------------ #


def test_construction_touches_no_network_and_needs_no_credentials(
    prompt: Path, client: FakeClient
) -> None:
    """**The difference from the other two plugins, stated in the name.**

    `digline-openai` and `digline-anthropic` build their client on first use, so
    their test asserts the SDK is not even imported until a call is made. Here
    the client exists at construction — it is where the region comes from, and
    the price list is chosen by the region. What is guaranteed instead is this:
    constructing reaches no network and asks for no credentials, so `digline
    list`, a preflight and this whole file work offline; and a missing region
    fails at construction rather than mid-run.
    """
    target = a_target(prompt, client)
    target.preflight([a_case()])
    assert target.region == "eu-west-1"
    assert client.requests == [], "constructing must not call the API"


def test_max_tokens_below_one_is_refused(prompt: Path, client: FakeClient) -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        BedrockTarget(prompt, EU_SONNET, 0, client=client)


def test_text_of_and_usage_of_read_a_dict_not_an_object() -> None:
    """Converse answers with a dict. Reading it with `getattr`, as the other two
    plugins read their SDKs, would pass against a fake built the wrong way and
    fail against AWS."""
    reply = converse_reply("Rome.", input_tokens=100, output_tokens=7, cache_read=40)
    assert text_of(reply) == "Rome."
    usage = usage_of(reply, SONNET, bedrock_pricing("eu-west-1"))
    assert usage.output_tokens == 7 and usage.cache_read_tokens == 40


# -- the one that spends money ----------------------------------------- #


#: Overridable with DIGLINE_BEDROCK_MODEL: which profiles an account has
#: enabled is an account's own business.
LIVE_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

LIVE = os.environ.get("DIGLINE_LIVE") == "1" and bool(
    os.environ.get("AWS_PROFILE")
    or os.environ.get("AWS_ACCESS_KEY_ID")
    or os.environ.get("AWS_ROLE_ARN")
)


@pytest.mark.live
@pytest.mark.skipif(not LIVE, reason="needs AWS credentials and DIGLINE_LIVE=1")
def test_a_real_call_answers_and_is_priced(prompt: Path) -> None:
    """The one target test that spends money. Everything above proves the
    shape; this proves the shape is the one Converse actually has."""
    model = os.environ.get("DIGLINE_BEDROCK_MODEL", LIVE_MODEL)
    target = BedrockTarget(prompt, model, 64)
    response = target(a_case())
    assert "Rome" in str(response.output)
    assert response.cost_usd is not None and response.cost_usd > 0
    assert response.latency_ms is not None and response.latency_ms > 0
