# digline-anthropic

An [Anthropic](https://www.anthropic.com) target for
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

Apache-2.0. Docs: [digline/digline](https://github.com/digline/digline).
