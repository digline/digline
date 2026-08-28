"""The client half: one chat call, shared by the target and the two judges.

The SDK is imported on first use, not at module scope. A suite that only wants
to be *loaded* — `digline list`, a preflight, a test — should not need `openai`
installed, and lazy import is what makes that true.

**No key is read here.** There is no `os.environ` and no `getenv` in this
package, and the test suite enforces it. What the SDK reads on its own is the
SDK's business; see `build_client` for the one place where an absent key is
tolerated, and why it is only reachable behind a custom `base_url`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from digline.targets import Pricing, Usage

__all__ = ["NO_KEY", "OpenAIChat", "TokenParam", "build_client", "usage_of"]

#: Passed as the key when — and only when — a custom `base_url` is set and the
#: SDK found nothing in the environment. Ollama and most self-hosted servers do
#: not look at it; anything that does rejects it with an authentication error,
#: which is the right error. It is written to be unmistakably not a credential:
#: whoever finds it in a log has found a placeholder, not a leak.
NO_KEY = "digline-no-key"

#: Which argument carries the output cap. See `OpenAIChat.complete`.
TokenParam = Literal["auto", "max_tokens", "max_completion_tokens"]


def build_client(base_url: str | None, api_key: str | None) -> Any:
    """The SDK client, with the key resolution rule of ADR 0004 §5.

    Three cases, in this order, and the order is the whole trick:

    1. a key was passed — it is used;
    2. no key and the **official** endpoint — `None` goes to the SDK, which
       resolves `OPENAI_API_KEY` itself and raises its own message if there is
       none. That message is clearer than anything this package could write,
       and it keeps the environment out of our source;
    3. no key, a **custom** `base_url`, and the SDK found nothing — the client
       is rebuilt with `NO_KEY`, because a local server has no key to give.

    Case 3 is reached only *after* the SDK has looked, so pointing at OpenRouter
    with `OPENAI_API_KEY` set still authenticates with the real key. This
    function never learns whether one exists.
    """
    import openai

    kwargs: dict[str, Any] = {}
    if base_url is not None:
        kwargs["base_url"] = base_url
    if api_key is not None:
        kwargs["api_key"] = api_key
    try:
        return openai.OpenAI(**kwargs)
    except openai.OpenAIError:
        if api_key is not None or base_url is None:
            raise
        return openai.OpenAI(base_url=base_url, api_key=NO_KEY)


def usage_of(reply: Any, model: str, pricing: Pricing) -> Usage:
    """Tokens out of a chat completion, with the cached ones subtracted.

    OpenAI counts cached prompt tokens **inside** `prompt_tokens` — the opposite
    of Anthropic, where a cache write is not in `input_tokens` at all (friction
    25). Adding the two straight would bill the cached half twice, at the full
    rate and again at the discounted one, so the cached count comes off the
    input before the `Usage` is built.

    A provider that reports no usage at all is refused, unless the model is
    priced at zero anyway — which is to say unless you told us, with `free()`,
    that this one costs nothing. Anything else would report a run as cheaper
    than it was, and that is the failure that reads as good news.
    """
    usage = getattr(reply, "usage", None)
    if usage is None:
        if _is_free(model, pricing):
            return Usage(input_tokens=0, output_tokens=0)
        raise ValueError(
            f"the provider returned no usage for model {model!r}, so this call "
            "cannot be priced. If it is a model you host and it costs nothing, "
            "say so: `pricing=free(...)`"
        )
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0)
    return Usage(
        input_tokens=max(prompt_tokens - cached, 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        cache_read_tokens=cached,
        # No cache-write charge on this API: there is nothing to count, which
        # is why the price list leaves the rate at `None` rather than at zero.
        cache_write_tokens=0,
    )


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


class OpenAIChat:
    """A lazily built client and the one call every OpenAI-compatible server has.

    Held by the target and by both judges, so the key resolution, the token
    argument and the `response_format` fallback are decided once for the whole
    package rather than three times.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.base_url = base_url
        self._api_key = api_key
        self._injected = client
        #: Set once, the first time a provider refuses `response_format`. The
        #: fallback is remembered rather than rediscovered: one wasted call per
        #: process, not one per judgement.
        self.json_mode_refused = False

    def __repr__(self) -> str:
        """The endpoint, never the key.

        Explicit because the default `repr` is only safe by accident, and a
        `repr` is what ends up in a pytest failure, a log line and a traceback.
        """
        return f"{type(self).__name__}(base_url={self.base_url!r})"

    def client(self) -> Any:
        if self._injected is None:
            self._injected = build_client(self.base_url, self._api_key)
        return self._injected

    def token_argument(self, token_param: TokenParam) -> str:
        """Which of the two names carries the output cap.

        `"auto"` is `max_completion_tokens` on the official endpoint and
        `max_tokens` everywhere else, and the asymmetry is not ours: the
        official API **rejects** `max_tokens` for the GPT-5 and o-series
        models, while most compatible servers accept `max_tokens` and quietly
        *ignore* `max_completion_tokens` — which does not fail, it just
        generates without a cap and bills for it.

        A guess in one direction is an error you see; in the other, a cost you
        do not. Pass the name explicitly when your server disagrees.
        """
        if token_param != "auto":
            return token_param
        return "max_tokens" if self.base_url is not None else "max_completion_tokens"

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        max_tokens: int,
        pricing: Pricing,
        temperature: float | None = None,
        response_format: Mapping[str, Any] | None = None,
        token_param: TokenParam = "auto",
        extra_body: Mapping[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        """One chat completion: the text and what it cost in tokens.

        `response_format` is sent when asked for and **never required** (ADR
        0004 §4). A provider that rejects it — Ollama does, some vLLM builds do
        — is retried once without it, and the fallback is remembered. That
        means one call's worth of latency the first time, and a judge that
        works on an endpoint nobody tested it against.
        """
        request: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            self.token_argument(token_param): max_tokens,
        }
        if temperature is not None:
            request["temperature"] = temperature
        if extra_body:
            request.update(extra_body)

        wants_json = response_format is not None and not self.json_mode_refused
        if wants_json and response_format is not None:
            request["response_format"] = dict(response_format)

        try:
            reply = self.client().chat.completions.create(**request)
        except Exception:
            # Retried only when `response_format` was in the request: without
            # it there is nothing to fall back to, and swallowing the exception
            # would hide an auth or a rate-limit error behind a second identical
            # failure. With it, the second attempt either works or raises the
            # error that was really there.
            if not wants_json:
                raise
            self.json_mode_refused = True
            del request["response_format"]
            reply = self.client().chat.completions.create(**request)

        return _text_of(reply), usage_of(reply, model, pricing)


def _text_of(reply: Any) -> str:
    choices: Any = getattr(reply, "choices", None) or []
    if not choices:
        raise ValueError(
            "the provider returned no choices: there is no output to judge or "
            "to assert on"
        )
    message: Any = getattr(choices[0], "message", None)
    # `None` rather than missing when the model produced nothing — a refusal, or
    # a cap hit before the first token. Empty text is an output the assertions
    # can fail; an exception here would make it an `error` instead, which says
    # the run could not be judged rather than that the model said nothing.
    return str(getattr(message, "content", None) or "")
