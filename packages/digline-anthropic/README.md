# digline-anthropic

An [Anthropic](https://www.anthropic.com) target **and judges** for
[digline](https://pypi.org/project/digline/): a prompt file goes in, a priced
`Response` comes out.

```python
from pathlib import Path
from digline_anthropic import AnthropicTarget

target = AnthropicTarget(
    prompt_file=Path(__file__).parent / "prompts/answer.md",
    system_file=Path(__file__).parent / "prompts/system.md",
    model="claude-sonnet-5",
    max_tokens=1024,
    prefill="{",  # put JSON in the model's mouth
)
```

Both files are recorded in every run, so the committed baseline carries the
prompt that produced it. Cost comes from a price list declared in code and
replaceable in one argument; an unknown model raises rather than costing
nothing. The key is never named here — the SDK reads `ANTHROPIC_API_KEY`.

## The judges

A plugin is a target **and** a judge ([ADR
0004](https://github.com/digline/digline/blob/main/docs/adr/0004-every-plugin-is-a-target-and-a-judge.md)):
whoever generates can judge, with the same key and the same price list, and the
twenty lines of SDK-and-JSON leave your suite.

```python
from digline.core import LlmRubric
from digline_anthropic import AnthropicJudge

judge = AnthropicJudge(model="claude-haiku-4-5")
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
from digline_anthropic import AnthropicClaimJudge

faithful = Faithfulness(
    judge=AnthropicClaimJudge(model="claude-haiku-4-5"),
    threshold=0.9,
    tolerance=0.05,
)
```

Both put `{` in the model's mouth and prepend it before parsing, and both read a
reply the model wrapped in a fence or a sentence. What judging cost is counted
on the judge and never reset:

```python
from digline_anthropic import AnthropicJudge

judge = AnthropicJudge(model="claude-haiku-4-5")
print(f"{judge.calls} judgements, {judge.spent_usd:.4f} USD, {judge.latency_ms:.0f} ms")
```

A suite with `samples=5` and `Repeated(n=3)` makes fifteen judging calls per
case, so this is not a rounding error. For a per-run figure, read it before and
after and subtract. It is in-process only today, and ADR 0004 §3 says what it
would take to put it in the report.

Apache-2.0. Docs: [digline/digline](https://github.com/digline/digline).
