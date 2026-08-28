"""The client half: the Converse call, shared by the target and the two judges.

Two things here are not like the other two plugins, and both are deliberate.

**The client is built at construction, not on first use.** `digline-openai` and
`digline-anthropic` build theirs lazily; here the client *is* where the region
comes from — `client.meta.region_name` is the value the AWS chain actually
resolved, and the price list follows from it. Deferring that would defer a
configuration error into the middle of a run, which is what `preflight` exists
to prevent. Building a client touches no network: botocore resolves credentials
on the first call, not on the constructor.

**Nothing here reads the environment.** No `os.environ`, no `getenv`, and no
credential parameter of any kind — the chain (env, profile, IAM role, IMDS) is
boto3's job, and a key a suite could set is a key that ends up in a repository.

**An AWS error is scrubbed before it escapes.** `scrub` exists because of where
a target's exception ends up: the driver quotes it into the `reason` of every
verdict of the case, and a `reason` lands in a committed run artifact. A
botocore `ClientError` routinely carries `arn:aws:sts::<account>:assumed-role/…`
— not a credential, but the customer's account, and it has no business in a file
that goes through code review on someone else's laptop.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from digline.targets import Pricing, Usage

__all__ = [
    "ACCOUNT_RE",
    "ARN_RE",
    "CACHE_READS_ARE_INSIDE_INPUT_TOKENS",
    "BedrockCallFailed",
    "BedrockChat",
    "build_client",
    "resolve_region",
    "scrub",
    "text_of",
    "usage_of",
]

#: Which convention Converse follows for cached input tokens. **Measured, not
#: assumed** — against the API on 2026-08-28, in eu-south-1:
#:
#:     inputTokens=10  outputTokens=4  totalTokens=12016
#:     cacheReadInputTokens=12002  cacheWriteInputTokens=0
#:
#: `total == input + output + cacheRead`, so the cached reads are **outside**
#: `inputTokens`: the Anthropic convention, and they are added rather than
#: subtracted. The two providers already in this workspace disagree on exactly
#: this — OpenAI counts them *inside* `prompt_tokens` — and the difference is
#: money in the direction of good news, which is why this was measured instead
#: of inferred from the field names (friction 25).
#:
#: The live test in `test_bedrock_judge.py` re-measures it and fails loudly if
#: this constant ever stops matching the API.
CACHE_READS_ARE_INSIDE_INPUT_TOKENS = False

#: Any ARN, in any partition. Deliberately greedy to the first whitespace or
#: quote: an ARN's own separators are all inside it.
ARN_RE = re.compile(r"arn:aws[a-z0-9-]*:[^\s\"']+")

#: A bare account id, for the messages that name one without an ARN around it.
#: Twelve digits is a shape nothing else in an AWS error has — a token count is
#: never twelve digits, and a model id has none.
ACCOUNT_RE = re.compile(r"\b\d{12}\b")


class BedrockCallFailed(RuntimeError):
    """A Converse call that failed, with the account scrubbed out of the message.

    The original exception is kept as `__cause__` — in-process, for a debugger —
    while what travels into a `Verdict.reason` is the scrubbed text.
    """


def scrub(text: str) -> str:
    """ARNs and account ids out of a message that is about to be recorded."""
    return ACCOUNT_RE.sub("<account>", ARN_RE.sub("<arn>", text))


def build_client(region: str | None) -> Any:
    """A `bedrock-runtime` client, region from the argument or from the chain.

    `region_name=None` lets botocore resolve it the way it resolves everything
    else — `AWS_REGION`, the profile, the instance metadata. When it cannot,
    botocore raises at construction, and that is turned into a sentence naming
    the argument that fixes it.
    """
    # boto3 ships no type information — the same upstream limitation the
    # jsonschema call site in the core carries, and the same remedy: name it
    # here rather than loosen the checker for the whole package.
    import boto3  # pyright: ignore[reportMissingTypeStubs]
    from botocore.exceptions import (  # pyright: ignore[reportMissingTypeStubs]
        NoRegionError,
    )

    try:
        # `cast` rather than an annotation: an untyped SDK yields `Unknown`, and
        # `Any | Unknown` is still partially unknown under strict.
        return cast(
            "Any",
            boto3.client(  # pyright: ignore[reportUnknownMemberType]
                "bedrock-runtime", region_name=region
            ),
        )
    except NoRegionError as exc:
        raise ValueError(
            "no AWS region: the environment, the profile and the instance "
            "metadata gave none. Pass `region=` to the target, set AWS_REGION, "
            "or pass a `client=` that already has one — the region is not a "
            "detail here, it is what the price list is chosen by"
        ) from exc


def resolve_region(client: Any) -> str:
    """The region the client actually has, which is the one that will be billed.

    Read from the client rather than defaulted, because a default would price a
    call at a region nobody made it in. **What was priced is what was called.**
    """
    region = getattr(getattr(client, "meta", None), "region_name", None)
    if not region:
        raise ValueError(
            "the client carries no region (`client.meta.region_name` is empty), "
            "so there is no price list to choose and no way to say where the "
            "call went. Pass `region=`, or a client built with one"
        )
    return str(region)


def text_of(reply: Mapping[str, Any]) -> str:
    """Only the text blocks of the assistant message.

    A Converse content block may be `toolUse` or `reasoningContent`, neither of
    which has a `text` key. Joining them in would put a repr — or the model's
    private reasoning — into the output the assertions read.
    """
    output = reply.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("the reply carries no `output`: there is nothing to judge")
    # `isinstance` against a bare `Mapping` narrows to `Mapping[Unknown, Unknown]`:
    # the check is real, the parameters are what the cast puts back.
    message = cast("Mapping[str, Any]", output).get("message")
    if not isinstance(message, Mapping):
        raise ValueError("the reply carries no `output.message`")
    blocks: Sequence[Any] = cast("Mapping[str, Any]", message).get("content") or ()
    return "".join(
        str(cast("Mapping[str, Any]", block)["text"])
        for block in blocks
        if isinstance(block, Mapping) and "text" in block
    )


def usage_of(reply: Mapping[str, Any], model: str, pricing: Pricing) -> Usage:
    """Tokens out of a Converse reply.

    Cached reads are reported **outside** `inputTokens` — measured against the
    API on 2026-08-28, where a call answering from a warm cache reported
    `inputTokens=10` beside `cacheReadInputTokens=12002` and a `totalTokens` of
    12016, which is the sum of the three. So they are added, not subtracted:
    the Anthropic convention, and the opposite of OpenAI's.

    `CACHE_READS_ARE_INSIDE_INPUT_TOKENS` keeps that answer in one place, so a
    provider that changes its mind is a one-line change and not an archaeology
    exercise.

    A reply with no usage block is refused, unless the model is priced at zero
    anyway — which is to say unless you said, with `free()`, that this one is
    billed by the hour rather than by the token.
    """
    raw_usage = reply.get("usage")
    if not isinstance(raw_usage, Mapping):
        if _is_free(model, pricing):
            return Usage(input_tokens=0, output_tokens=0)
        raise ValueError(
            f"the reply carries no usage for model {model!r}, so this call "
            "cannot be priced. If it is billed by the hour rather than by the "
            "token — an imported model, provisioned throughput — say so: "
            "`pricing=free(...)`"
        )
    usage = cast("Mapping[str, Any]", raw_usage)
    reported_input = _count(usage, "inputTokens")
    cache_read = _count(usage, "cacheReadInputTokens")
    cache_write = _count(usage, "cacheWriteInputTokens")
    input_tokens = (
        max(reported_input - cache_read, 0)
        if CACHE_READS_ARE_INSIDE_INPUT_TOKENS
        else reported_input
    )
    return Usage(
        input_tokens=input_tokens,
        output_tokens=_count(usage, "outputTokens"),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )


def _count(usage: Mapping[str, Any], key: str) -> int:
    value = usage.get(key, 0) or 0
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"usage.{key} is {value!r}, which is not a token count")
    return int(value)


def _is_free(model: str, pricing: Pricing) -> bool:
    price = pricing.per_model.get(model)
    return price is not None and not any(
        (
            price.input_per_mtok,
            price.output_per_mtok,
            price.cache_read_per_mtok,
            price.cache_write_per_mtok,
        )
    )


class BedrockChat:
    """A `bedrock-runtime` client with its region resolved, and one Converse call.

    Held by the target and by both judges, so the region, the price list and the
    scrubbing are decided once for the whole package rather than three times.
    """

    def __init__(self, *, region: str | None = None, client: Any = None) -> None:
        self.client: Any = client if client is not None else build_client(region)
        #: Resolved **now**, at construction. Read-only on purpose: what was
        #: priced is what was called, and a region that could be reassigned
        #: after the price list was chosen would break that sentence quietly.
        self._region = resolve_region(self.client)
        if region is not None and region != self._region:
            raise ValueError(
                f"the client is in {self._region!r} but `region={region!r}` was "
                "asked for: two answers to where the call goes is one too many"
            )

    @property
    def region(self) -> str:
        return self._region

    def __repr__(self) -> str:
        """Region only. No session, no credentials, no client repr."""
        return f"{type(self).__name__}(region={self._region!r})"

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None,
        max_tokens: int,
        pricing: Pricing,
        temperature: float | None = None,
        additional_request_fields: Mapping[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        """One Converse call: the text and what it cost in tokens."""
        inference: dict[str, Any] = {"maxTokens": max_tokens}
        if temperature is not None:
            inference["temperature"] = temperature
        request: dict[str, Any] = {
            "modelId": model,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": inference,
        }
        if system is not None:
            request["system"] = [{"text": system}]
        if additional_request_fields:
            request["additionalModelRequestFields"] = dict(additional_request_fields)

        try:
            reply = self.client.converse(**request)
        except Exception as exc:
            # Broad on purpose, and it is the scrub that justifies it: every
            # botocore failure — `ClientError`, `EndpointConnectionError`, a
            # throttle — carries a message that the driver will quote into a
            # committed artifact, and they do not share a base class worth
            # naming. The original stays on `__cause__` for a debugger.
            raise BedrockCallFailed(f"{type(exc).__name__}: {scrub(str(exc))}") from exc

        return text_of(reply), usage_of(reply, model, pricing)
