# digline over MCP

`digline-mcp` is the [MCP](https://modelcontextprotocol.io) server for digline.
It lets a coding agent **read** a result and **measure** a new one, and it does
not let the agent promote a baseline.

Not because promotion is refused. Because there is no such tool.

## Why the surface has this shape

digline ships [`AGENTS.md`](../AGENTS.md) because agents already run it — they
shell out to the CLI, read text a person was meant to read, and act on it. Two
things are true at once, and the CLI cannot hold both.

Reading a digline result is real work and worth supporting. Assembling what
moved, by how much, and whether it exceeded the measured interval is exactly
what `AGENTS.md` asks an agent to do before recommending anything.

Promoting a baseline is the one thing `AGENTS.md` §1 forbids, and the CLI cannot
forbid it: `digline promote` exists, and an agent with a shell has it. That rule
is a sentence in a file the agent may not have read, asking it to decline
something it is fully able to do.

A baseline is an **approved reference**, and `promote` writes into
`.digline/<tenant>/baselines/`, which is committed. Anything landing there
arrives in somebody's pull request wearing the word *baseline*, and an
unattended process cannot supply the approval that word means.

So the surface settles it by construction. A refusal would be a conversation —
argued with, retried, worked around by a model that has decided the refusal is a
bug. An absence is not a conversation.

The reasoning in full is [ADR 0011](adr/0011-the-mcp-server.md).

## The six tools

| tool | arguments | what it answers |
|---|---|---|
| `list_runs` | `suite` | which runs exist, newest first, baseline marked |
| `get_run` | `suite`, `run` | what one run measured |
| `get_baseline` | `suite` | what the approved reference measured |
| `compare` | `suite`, `run` | did it get worse? |
| `diff` | `suite`, `run1`, `run2` | should I switch? |
| `run` | `suite`, `acknowledge_calls` | measure it now |

`promote`, `migrate`, `view` and `report` are absent. The first is the thesis;
the second is upgrade maintenance somebody chose the moment for; the last two
are documents written for a person, and an agent that wants the facts behind the
report calls `compare`, which carries them.

## Configuring it

One server serves **one repository**. The perimeter is the repo, and
multi-project is N named servers rather than a registry — a registry would be
the one file in this design that is not inside anybody's repository, and it
would name every tenant on the machine in one place.

```json
{
  "mcpServers": {
    "digline-northwind": {
      "command": "digline-mcp",
      "args": ["--root", "/Users/you/src/northwind"]
    },
    "digline-acme": {
      "command": "digline-mcp",
      "args": ["--root", "/Users/you/src/acme"]
    }
  }
}
```

`--tenant` and `--env` are accepted and **verify**; they never override. The
suite decides, as it does everywhere else — a flag that could override one is
how a run ends up filed under the wrong customer.

The transport is stdio: the client launches the process, so there is no bound
port and no listening socket.

## What `run` costs, before it costs it

`AGENTS.md` §7 is an obligation to speak: say what a hunt will cost before
starting it. The CLI discharges it by printing to stderr and trusting the
reader. There is no stderr here and no reader, so it is discharged by making the
number a parameter that cannot be guessed past.

```
run(suite="suite.py")
  → refused: this suite plans 100 calls to the target.
    20 cases × 5 samples = 100 calls to the target; each answer is judged
    3 times by llm_rubric.
    Call again with acknowledge_calls=100 to run it.

run(suite="suite.py", acknowledge_calls=100)
  → executes
```

**The first call is the probe.** There is deliberately no seventh tool returning
the plan — a tool an agent could call, read, and never act on the number of
would make the acknowledgement a courtesy again. Here the only way to learn the
number is to be refused for not knowing it, and the only way to proceed is to
type it back.

The integer counts **calls to the target**. Where an assertion judges each
answer several times, the returned `sentence` names the multiplier, and that is
the figure to report — `CallPlan` does not fold judge repeats into one number,
because nothing in the core claims to know which assertions call a model.

A suspended case is not counted, because it is never called.

## What the responses are

The same objects `--json` prints, field for field, under the same
`output_version`. There is no second, LLM-shaped rendering: two representations
of one truth diverge, and the day they disagree there is no answer to which one
is digline's. `compare` and `diff` are checked against the CLI's own output in
the test suite.

`compare` carries `exit_code` — `0` proceed, `1` stop and report what got worse,
`2` stop because the run could not be judged. It is a field because a tool has
no process to exit.

`diff` carries **no `worse` and no `exit_code`**. A verdict exists only against
an approved reference, and neither side of a diff was approved by anybody.

## What never crosses

An MCP response goes into a model's context, and from there into transcripts and
caches nobody controls. That is a worse destination than a CI log, which is
already inside the perimeter — so the run tools return a **verdict-only
projection**.

What travels is what a verdict *is*: the name, the assertion identity, the
status, the score, the threshold, the tolerance, the measured interval, and the
metadata a suite disclosed. The configuration travels too — a model id and a
temperature are measurements of the system (ADR 0005).

What does not, and is **absent rather than emptied**:

- the judge's `reason` — the judge quotes the output, so the reason *is* the
  output;
- the stated reason a case was suspended, which a developer writes about real
  data (*that* a case was suspended does travel: it is coverage);
- any `Score.metadata` key the suite's `Disclosure` does not cover;
- a prompt **and its digest** unless the suite declares
  `Disclosure(artifacts=True)` — a digest is a verifier, and prompts live in a
  small enough space that one recovers the text (ADR 0003 §4);
- `base_url`, the client's topology, which leaves as a name in `withheld` and
  never as a value — no `Disclosure` widens that one;
- the case inputs entirely. `vars` and `metadata` are the data.

The projection is **chosen and not inherited** from the stored run document,
which is under a different contract with a different lifetime. A field added to
it without a decision fails a test rather than shipping.
