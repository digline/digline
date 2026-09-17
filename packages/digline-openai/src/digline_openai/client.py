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

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from digline.core import Finish
from digline.targets import Completion, Pricing, ToolCall, Usage, finish_of

__all__ = [
    "CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS",
    "FINISH",
    "NO_KEY",
    "OpenAIChat",
    "TokenParam",
    "build_client",
    "tool_calls_of",
    "tools_of",
    "usage_of",
]

#: Whether `prompt_tokens_details.cache_write_tokens` is counted **inside**
#: `prompt_tokens`, as `cached_tokens` is, or beside it. **Unmeasured**, and
#: `None` says so: until it is a `bool`, `usage_of` reports no cache writes.
#:
#: The field exists — the SDK's `PromptTokensDetails` declares it, "the
#: unadjusted number of prompt tokens written to cache" — and from GPT-5.6 the
#: price list carries a
#: cache-write rate. But its convention decides whether the tokens are
#: subtracted from the input or added to it, and a guess is money in one
#: direction or the other (friction 25). Reading it from the neighbouring field
#: is the inference that friction was about. So a call that writes a cache is
#: **undercounted today, in the good-news direction**: the written tokens are
#: billed at the input rate if they sit inside `prompt_tokens`, and not at all if
#: they sit beside it.
#:
#: What settles it is arithmetic, not field names — three calls with the same
#: long prompt: caching off (`prompt_cache_options={"mode": "explicit"}` and no
#: breakpoint) gives the prompt's size `N`; a cold call writes `W`; `prompt_tokens
#: == N` there is **inside**, `prompt_tokens + W == N` is **beside**. The live
#: test `test_cache_writes_say_which_convention_chat_completions_follows` is that
#: measurement, one command, and fails with the answer until this is set.
CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS: bool | None = None

#: OpenAI's `finish_reason` in the vocabulary every plugin translates into
#: (ADR 0004 §6). Read off `openai.types.chat.chat_completion.Choice`.
#:
#: There is **no refusal value here**, and that is not an omission in this
#: table: a refusal arrives one level down as `message.refusal` while
#: `finish_reason` stays `stop`. `_finish_of` below is therefore the one place
#: in this workspace where a plugin *composes* an answer rather than translating
#: one, and ADR 0004 §6 declares it so that it is not discovered in the code.
#:
#: A word this table does not know maps to `other`, never to `stop` — a
#: compatible endpoint inventing a finish reason must not turn a truncated run
#: green. See `finish_of`.
FINISH: dict[str, Finish] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "filtered",
}

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
    written = _cache_writes(details)
    inside = cached + (written if CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS else 0)
    return Usage(
        input_tokens=max(prompt_tokens - inside, 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        cache_read_tokens=cached,
        cache_write_tokens=written,
    )


def _cache_writes(details: Any) -> int:
    if CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS is None:
        # **A known undercount, not a tier this API lacks.** The SDK reports
        # `cache_write_tokens` and it is not read, because whether it sits
        # inside `prompt_tokens` is unmeasured and either guess misprices. What
        # settles it: the three-call arithmetic with caching off as the
        # baseline — see `CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS`.
        return 0
    return int(getattr(details, "cache_write_tokens", 0) or 0)


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
    ) -> Completion:
        """One chat completion, as the record `_complete` returns (ADR 0004 §6).

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

        choice = _first_choice(reply)
        message: Any = getattr(choice, "message", None)
        finish, raw = _finish_of(choice, message)
        calls = tool_calls_of(message)
        return Completion(
            text=_text_of(message),
            usage=usage_of(reply, model, pricing),
            finish=finish,
            finish_raw=raw,
            tools=None if calls is None else tuple(call.tool for call in calls),
            tool_calls=calls,
            model=str(getattr(reply, "model", "")) or None,
            fingerprint=str(getattr(reply, "system_fingerprint", "") or "") or None,
        )


def _first_choice(reply: Any) -> Any:
    choices: Any = getattr(reply, "choices", None) or []
    if not choices:
        raise ValueError(
            "the provider returned no choices: there is no output to judge or "
            "to assert on"
        )
    return choices[0]


def _text_of(message: Any) -> str:
    # `None` rather than missing when the model produced nothing — a refusal, or
    # a cap hit before the first token. Empty text is an output the assertions
    # can fail; an exception here would make it an `error` instead, which says
    # the run could not be judged rather than that the model said nothing.
    return str(getattr(message, "content", None) or "")


def _finish_of(choice: Any, message: Any) -> tuple[Finish | None, str | None]:
    """How the turn ended, with the refusal read out of the message.

    The composition ADR 0004 §6 declares: this API reports a refusal as
    `message.refusal` and leaves `finish_reason` at `stop`, so a run where the
    model declined every case would otherwise record five green `stop`s. The
    refusal wins, and `finish_raw` says `refusal` — which is the word to search
    the provider's own documentation for.

    It is deliberately the *only* thing read from outside `finish_reason`.
    Anything more would be this layer deciding what a provider meant.
    """
    if getattr(message, "refusal", None):
        return "filtered", "refusal"
    return finish_of(getattr(choice, "finish_reason", None), FINISH)


def tools_of(message: Any) -> tuple[str | None, ...] | None:
    """The functions the model called, in order — or `None` if none were named.

    `tool_calls` is absent on a reply that called nothing *and* on a compatible
    server that does not implement tools at all, and the two are different
    facts: one is the model calling nothing, the other is nobody reporting. This
    API cannot tell them apart, so it reports the honest half — `None` — and
    `ToolsCalled` errors rather than announcing that no tool was called.

    The deprecated `function_call` is read too. It is one call rather than a
    list, and a suite running against a server still speaking it should not be
    told the model called nothing.

    The names of `tool_calls_of`, so the two cannot disagree.
    """
    calls = tool_calls_of(message)
    return None if calls is None else tuple(call.tool for call in calls)


def tool_calls_of(message: Any) -> tuple[ToolCall, ...] | None:
    """The calls with their arguments, and nothing this API does not report.

    Chat Completions hands back what the model **asked** for and stops: the
    tool runs afterwards, in the application. So every call carries
    `status="not_reported"` and `result_absence="not_reported"` — the call may
    have succeeded or failed, and the reply cannot say. (ADR 0018 §1, amended
    2026-09-15)

    Two kinds, read by `type` as the SDK discriminates them:

    - **`function`** — `arguments` is a string the model wrote as JSON, and the
      SDK warns it is not always valid. Decoded to the object when it is one;
      kept verbatim when it is not, so `ToolCalledWith` says *not decodable*
      rather than the plugin deciding what the model meant.
    - **`custom`** — `input` is free-form text by design, never JSON, and is
      kept as written. Its name is `custom.name`: reading `function.name` here
      recorded the call as `""`.
    """
    calls: Any = getattr(message, "tool_calls", None)
    if calls:
        return tuple(_call_of(call) for call in calls)
    single: Any = getattr(message, "function_call", None)
    if single is not None:
        return (
            _asked(
                _name_of(getattr(single, "name", None)),
                _decoded(getattr(single, "arguments", None)),
            ),
        )
    return None


def _call_of(call: Any) -> ToolCall:
    if getattr(call, "type", None) == "custom":
        custom: Any = getattr(call, "custom", None)
        text = getattr(custom, "input", None)
        return _asked(
            _name_of(getattr(custom, "name", None)),
            text if isinstance(text, str) else None,
        )
    function: Any = getattr(call, "function", None)
    return _asked(
        _name_of(getattr(function, "name", None)),
        _decoded(getattr(function, "arguments", None)),
    )


def _name_of(value: object) -> str | None:
    """The function a call names, or `None` where it names none.

    The SDK declares `name: str` and does not validate a reply, so a compatible
    server that leaves the name out or sends `null` hands over `None`. That call
    used to become `ToolCall(tool="")`, which raised and errored the whole case,
    the named calls beside it included; it is now recorded as a call the
    provider did not name. `""` is not a name either. (ADR 0018 §1, amended
    2026-09-17)
    """
    return value if isinstance(value, str) and value else None


def _asked(name: str | None, arguments: Mapping[str, object] | str | None) -> ToolCall:
    return ToolCall(
        tool=name,
        arguments=arguments,
        status="not_reported",
        result_absence="not_reported",
    )


def _decoded(text: object) -> Mapping[str, object] | str | None:
    if not isinstance(text, str):
        return None
    try:
        found: object = json.loads(text)
    except ValueError:
        return text
    if isinstance(found, dict):
        return cast("dict[str, object]", found)
    return text
