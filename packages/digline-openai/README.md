# digline-openai

An [OpenAI](https://openai.com) target **and judges** for
[digline](https://pypi.org/project/digline/): a prompt file goes in, a priced
`Response` comes out — at any OpenAI-compatible endpoint.

```sh
pip install digline-openai
```

**Requires Python 3.12+**, like digline itself.

## One argument, three providers

The wire protocol is the same everywhere, so `base_url` is the only thing that
changes. **OpenAI** — the key is read by the SDK from `OPENAI_API_KEY`, and this
package never touches your environment:

```python
from digline_openai import OpenAITarget

target = OpenAITarget("prompts/answer.md", model="gpt-5", max_tokens=1024)
```

**Azure OpenAI** — your resource's v1 endpoint, with the key passed explicitly
because Azure names its variable something else:

```python
import os
from digline_openai import OpenAITarget

target = OpenAITarget(
    "prompts/answer.md",
    model="gpt-4.1",
    max_tokens=1024,
    base_url="https://my-resource.openai.azure.com/openai/v1",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
```

**Ollama** — no key at all, and a model that costs nothing because you are the
one hosting it:

```python
from digline_openai import OpenAITarget, free

target = OpenAITarget(
    "prompts/answer.md",
    model="llama3.2",
    max_tokens=1024,
    base_url="http://localhost:11434/v1",
    pricing=free("llama3.2"),
)
```

The same target covers OpenRouter, Groq, Together and a vLLM in your own VPC. Nothing here is a gateway or an abstraction layer: it is the `openai` SDK
with its own `base_url` argument, which is what that argument is for.

## The judge runs in your perimeter too

A plugin is a target **and** a judge ([ADR
0004](https://github.com/digline/digline/blob/main/docs/adr/0004-every-plugin-is-a-target-and-a-judge.md)).
The point is not convenience: what a judge is sent is the model's *output*, so a
judge that lives at somebody else's API takes the payload out of the perimeter
it was generated in, and no setting in the suite would say so.

```python
from digline.core import LlmRubric
from digline_openai import OpenAIJudge

judge = OpenAIJudge(model="gpt-5-mini")
rubric = LlmRubric(
    rubric="The answer is one sentence and cites the passage it came from.",
    judge=judge,
    threshold=0.8,
    tolerance=0.05,
)
```

`Faithfulness` asks a judge to decompose rather than to score — how many claims
the output makes, how many the context supports — so it takes the other one:

```python
from digline.core import Faithfulness
from digline_openai import OpenAIClaimJudge

faithful = Faithfulness(
    judge=OpenAIClaimJudge(model="gpt-5-mini"),
    threshold=0.9,
    tolerance=0.05,
)
```

Both take the same `base_url` and `api_key` as the target, so judging an Ollama
run on that same Ollama is one argument:

```python
from digline_openai import OpenAIJudge, free

local = OpenAIJudge(
    model="llama3.2",
    base_url="http://localhost:11434/v1",
    pricing=free("llama3.2"),
)
```

## What judging cost

The target's cost lands on the `Response` and in the run. A judge's does not —
it is counted on the judge, and it is not reset:

```python
from digline_openai import OpenAIJudge

judge = OpenAIJudge(model="gpt-5-mini")
print(f"{judge.calls} judgements, {judge.spent_usd:.4f} USD, {judge.latency_ms:.0f} ms")
```

A suite with `samples=5` and `Repeated(n=3)` makes fifteen judging calls per
case, so this is not a rounding error. For a per-run figure, read it before and
after and subtract. It is in-process only today, and ADR 0004 §3 says what it
would take to put it in the report.

## The details that bite

**Cached tokens.** OpenAI counts cached prompt tokens *inside* `prompt_tokens`.
They are subtracted before pricing, so the discounted half is not also billed at
the full rate — the opposite convention to Anthropic, and getting it wrong is
invisible in the direction of good news.

**`max_tokens` vs `max_completion_tokens`.** The official API rejects
`max_tokens` for GPT-5 and the o-series; most compatible servers accept it and
silently ignore `max_completion_tokens`, which generates without a cap and bills
for it. So: `max_completion_tokens` when `base_url` is unset, `max_tokens`
otherwise. Override with `token_param="max_tokens"` when your server disagrees.

**JSON.** The judges ask for `{"type": "json_object"}` where it is supported. A
provider that refuses it is retried once without it, the fallback is remembered,
and the reply is parsed leniently either way — a fenced block or a sentence in
front of the object both read correctly.

**Prices.** `OPENAI_PRICING` carries the day it was copied and is one argument
to replace; an unknown model raises at `preflight` rather than costing nothing.
`free("llama3.2")` is how you say a self-hosted model really is free, out loud.

**Keys.** Passed explicitly or resolved by the SDK from the environment — this
package contains no `os.environ` and no `getenv`, and a test enforces it. Only
when `base_url` is custom *and* the SDK found nothing does the client fall back
to the obviously-fake `digline-no-key`, for local servers that ignore it.

Apache-2.0. Docs: [digline/digline](https://github.com/digline/digline).
