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

## The eight tools

| tool | arguments | what it answers |
|---|---|---|
| `list_runs` | `suite` | which runs exist, newest first, baseline marked, with each run's aggregates |
| `get_run` | `suite`, `run` | what one run measured |
| `get_baseline` | `suite` | what the approved reference measured |
| `log` | `suite`, `since`, `until` | which model answered, down the stored runs — never a gate |
| `compare` | `suite`, `run` | did it get worse? |
| `diff` | `suite`, `run1`, `run2` | should I switch? |
| `explain` | `suite`, `run` | the same run read back as typed facts, with the exit code |
| `run` | `suite`, `acknowledge_calls` | measure it now |

`explain` and `log` arrived together, so the surface moved once, from six to
eight ([ADR 0020](adr/0020-the-reading-across-runs.md)). Neither writes.

**What `get_run` and `get_baseline` say about the instrument.** Since 0.16.0 the
run document marks a judged check (`judged`), a canary (`canary`), a calibration
case (`calibration`, with its band), a run judged from stored answers
(`rejudged_from`, the key of the run it replayed) and scores that are means of
judgements rather than judgements (`sample_means`, beside `samples`). They are
facts about our own instrument, they carry none of the measured system's data,
and a caller reading **one run with no reference** had no way to get them:
`compare` and `explain` need a baseline, and two of the five were carried by
neither. ([ADR 0011](adr/0011-the-mcp-server.md) §5, amended 2026-09-19.)

**The one that does not travel** is `Run.judge_samples` — how many times a replay
asked the judge per answer. It is ruled out rather than pending: the numbers it
qualifies live in each verdict's metadata, which crosses only where the suite's
`Disclosure` names it, so the count would arrive with nothing to count against.

*Corrected 2026-09-19.* Until that date this paragraph said the five absent
facts could be had by calling `explain` or `compare`, *"which carry each as a
fact"*. That was true of `rejudged` and, with a reference, of `canary` and
`calibration`; it was **not** true of `judged`, which no surface carried as a
per-check fact, nor of `judge_samples`, which no surface carried at all. The
sentence is replaced rather than quietly deleted, so the page shows it was
checked.

`promote`, `migrate`, `view` and `report` are absent. The first is the thesis;
the second is upgrade maintenance somebody chose the moment for; the last two
are documents written for a person, and an agent that wants the facts behind the
report calls `compare`, which carries them.

`delete` is absent for the first one's reason, and further from review than it:
`promote` writes a committed file, which arrives in somebody's diff, while a
delete removes artifacts that are gitignored, with no diff, no review and no way
back. A destructive hint would not stand in for the absence: a hint is not
enforcement. ([ADR 0044](adr/0044-the-run-delete.md) §2)

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
      "args": ["--root", "/Users/you/src/northwind", "--names", "clear"]
    },
    "digline-acme": {
      "command": "digline-mcp",
      "args": [
        "--root", "/Users/you/src/acme",
        "--names", "project", "--name-table", "acme_names:TABLE"
      ]
    }
  }
}
```

`--tenant` and `--env` are accepted and **verify**; they never override. The
suite decides, as it does everywhere else — a flag that could override one is
how a run ends up filed under the wrong customer.

### Whether the names may leave: `--names`

**Required, with no default.** Whether a store's names may leave in clear
depends on whose cases are in it, and nothing in a store says, so the server
asks whoever starts it ([ADR 0054](adr/0054-the-names-a-server-lets-out.md)):

- **`--names clear`**: the case ids, check names, configuration and paths leave
  as they are. Your own project, or a store whose cases are yours.
- **`--names project`**: every answer is projected before it leaves. Those
  names become **tokens** from the name table, the same tokens a projected
  reference carries ([ADR 0036](adr/0036-the-name-table-and-the-process-that-owns-it.md)),
  and the sentences an answer carries are composed from the tokens. `tenant`
  and `suite` stay in clear, as they do in a projection. **A refusal is not
  projected yet**: one the core raises is a sentence, and the ones measured
  quote no name the table minted, which is a measurement and not a guarantee
  (ADR 0054 §8 is not complete).

Under `project`, `--name-table module:attribute` names the table, in the
syntax `--target` and `--suite` take: an object, or a module, with the two
callables `mint(kind, text)` and `lookup(token)`. The server mints through it
and reads nothing else of it. `--names project` without a table does not start,
and its message names what is missing and nothing in the store. A table given
under `clear` is refused, because the line would say two things.

A configuration that passes `--root` alone, as every one did before the
declaration, no longer starts: add `--names clear` to keep what it did.

The transport is stdio: the client launches the process, so there is no bound
port and no listening socket.

### In Claude Code, as a plugin

`digline@digline` is the Claude Code plugin, installed from this repository's
own marketplace. It ships the `operating-digline` skill beside this server,
started on the project it is installed in, and a hook that asks a person before
`digline promote` or `digline register`: two lines plus one dependency, and
what they install is described in
[`plugins/digline/README.md`](https://github.com/digline/digline/blob/main/plugins/digline/README.md).

## What `run` costs, before it costs it

`AGENTS.md` §7 is an obligation to speak: say what a hunt will cost before
starting it. The CLI discharges it by printing to stderr and trusting the
reader. There is no stderr here and no reader, so it is discharged by making the
number a parameter that cannot be guessed past.

```
run(suite="suite.py")
  → refused: this suite plans 100 calls to the target.
    tenant 'northwind' · 20 cases × 5 samples = 100 calls to the target; each answer
    is judged 3 times by llm_rubric.
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

`run` also returns **`notes`**: the lines `digline run` prints on stderr before
the first call. One names the checks whose class declares no `KIND`, which
`explain`'s shape reading leaves out; one per check names a tolerance so wide
the check is reported only when it flips. Each is a sentence for whoever wrote
the suite, said and never refused. An empty list is a suite that was read and
had nothing to say. `digline run --json` carries the same list. (#396)

## What the responses are

Each tool returns a JSON object built by a function in `digline.wire`, the
package every `--json` of the CLI is built by. There is no second, LLM-shaped
rendering: two representations of one truth diverge, and the day they disagree
there is no answer to which one is digline's. What each tool returns today:

| tool | built by | the CLI's counterpart |
|---|---|---|
| `compare` | `compare_json`, the full form | `digline compare --json full --locale en`, held equal by a test |
| `diff` | `diff_json`, the full form, its `sentence` in English | `digline diff --json full --locale en`, held equal by a test |
| `explain` | `explain_json` | `digline explain --json`, held equal by a test |
| `log` | `log_json` | `digline log --json`, held equal by a test |
| `run` | `run_json`; `resumed` is always `false`, because the tool has no way to resume | `digline run --json`: a test holds the same keys except `unpriced`, which the tool does not carry. Its sentences name a model in clear, and under `--names project` nothing mints them |
| `list_runs` | `runs_json` | none: `digline list` has no `--json` |
| `get_run` | the run document, plus `key` | none |
| `get_baseline` | the run document, plus `key` | none |

The tests are in `packages/digline-mcp/tests/test_tools.py`.

**A verdict's check is named `assertion` in every tool**: `get_run`,
`get_baseline` and each aggregate row of `list_runs`, `compare`'s `deltas`,
`shape` and `suite_deltas`, `diff`'s `checks`, `explain`'s `facts` and `log`'s
`spread`, as the run file does. Until `output_version` 4 it went by `name`,
`check` and `rule` in some of them (#678). The fields
whose form still differs from one document to the next, `modules_unchecked`
and `promoted_at`, are listed in
[the API reference](api.md#the-same-fact-in-different-documents).

`compare` carries `exit_code` — `0` proceed, `1` stop and report what got worse,
`2` stop because the run could not be judged. It is a field because a tool has
no process to exit.

`diff` carries **no `worse` and no `exit_code`**. A verdict exists only against
an approved reference, and neither side of a diff was approved by anybody.

`get_run`, `compare`, `explain` and each side of `diff` carry **`note`**: what
resolving `latest` stepped over, the line the CLI prints on stderr, and empty for
a key typed by hand. Non-empty, it says the run read is not the newest this store
remembers, or that files were left out on the way. The case it exists for is a
baseline promoted from a run newer than `latest` whose file is gone. `compare`
then holds an older run against a newer reference, and a `worse` there is the
past, not a regression. It is a sentence, as `list_runs`'s `note` is, and not a
key to pass back: the run it names cannot be read here. `get_baseline` has no
`note`, because a baseline is never resolved. (#433)

`compare` and `explain` carry **`run_key`**, the run they read, and `explain`
carries **`baseline_key`** where its `reading` is `comparison`; `compare` always
does. Both are derived from the documents read, not copied from your argument,
so with `latest` they say which run was picked, and with a key they confirm it.
Quote and recommend the run by `run_key`: a second `get_run(run="latest")` can
resolve to a run that landed in between. (#448)

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
  `Disclosure(artifact_body=True)` — a digest is a verifier, and prompts live in a
  small enough space that one recovers the text (ADR 0003 §4);
  A declared file outside the perimeter is refused when the run is made; one
  under `.digline` or `.git` is refused by the command that would let it cross.
  Neither is dropped in silence.
- `base_url`, the client's topology, which leaves as a name in `withheld` and
  never as a value — no `Disclosure` widens that one;
- the case inputs entirely. `vars` and `metadata` are the data.

*What never crosses* holds for refusals too: a refusal that quotes code
digline did not write names the command that shows the message, and leaves
the message out ([ADR 0043](adr/0043-a-message-digline-did-not-write.md)).

The projection is **chosen and not inherited** from the stored run document,
which is under a different contract with a different lifetime. A field added to
it without a decision fails a test rather than shipping.
