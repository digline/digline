# digline-mcp

The [MCP](https://modelcontextprotocol.io) server for
[digline](https://github.com/digline/digline): it lets a coding agent **read** a
digline result and **measure** a new one, and it does not let the agent promote
a baseline.

Not because promotion is refused. Because there is no such tool.

## The six tools

| tool | what it does |
|---|---|
| `list_runs` | every stored run of a suite, newest first, with the baseline marked |
| `get_run` | one stored run — the verdicts, never the payload |
| `get_baseline` | the approved reference, same shape |
| `compare` | a run against the baseline: did it get worse? |
| `diff` | two runs, neither of them a reference: should I switch? |
| `run` | execute the suite, with the call count acknowledged first |

`promote` is **absent by construction**, and so are `migrate`, `view` and
`report`. A baseline is an *approved reference*, and `promote` writes into
`.digline/<tenant>/baselines/`, which is committed — anything landing there
arrives in somebody's diff and must arrive because they put it there. A refusal
would be a conversation an agent could argue with; an absence is not.

The reasoning is [ADR 0011](../../docs/adr/0011-the-mcp-server.md), and the
judgement layer it turns into surface is [`AGENTS.md`](../../AGENTS.md).

## Install and configure

```bash
uv pip install digline-mcp
```

One server serves **one repository**: the perimeter is the repo, and
multi-project is N named servers rather than a registry.

```json
{
  "mcpServers": {
    "digline-northwind": {
      "command": "digline-mcp",
      "args": ["--root", "/Users/you/src/northwind"]
    }
  }
}
```

`--tenant` and `--env` are accepted and **verify**; they never override. The
suite decides, as it does everywhere else in digline.

## What `run` costs, before it costs it

`run` takes a mandatory `acknowledge_calls` that must equal the suite's planned
calls to the target. Called without it, the tool refuses **and hands back the
number**:

```
run(suite="suite.py")
  → refused: this suite plans 100 calls to the target.
    20 cases × 5 samples = 100 calls to the target; each answer is judged
    3 times by llm_rubric.
    Call again with acknowledge_calls=100.

run(suite="suite.py", acknowledge_calls=100)   → executes
```

The first call is the probe. An agent cannot spend a hundred model calls without
having stated the number — `AGENTS.md` §7 as a contract rather than as advice.

## What never crosses

An MCP response goes into a model's context, and from there into transcripts and
caches nobody controls. So the run tools return a **verdict-only projection**:
the name, the identity, the status, the score, the threshold, the tolerance, the
measured interval, and the metadata a suite disclosed.

Never the judge's `reason` — the judge quotes the output, so the reason *is* the
output. Never the sentence explaining a suspension, never undisclosed metadata,
never a case's inputs, and never a prompt or its digest unless the suite
declares `Disclosure(artifacts=True)`.
