# An agent in Python, from its first turns to a gate on its steps

This page records an agent's turns with the tools it calls, turns the
recordings into a suite, and ends with a gate on the agent's steps.

## Who this is for

An agent in Python that answers a customer's ticket in a loop: it asks the
model, runs the tool the model asks for, sends back the result, and asks
again until the model answers in text. Here it has three tools,
`lookup_order`, `issue_refund` and `escalate`, and calls the model through
the `anthropic` SDK.

Everything on this page was run, on 2026-11-09, with digline and
`digline-anthropic` installed from this repository at `1b5cf083`,
`anthropic` 2.4.0 and Python 3.14. **No call reached Anthropic or a model.**
A stand-in for the Messages API on 127.0.0.1,
`tests/_story_agent_stand_in.py` in this repository, answered the agent and
the judge: for the agent, first the tool calls its table names, then the
text that ends the turn. Every answer, tool call, score and token count below
is the stand-in's. The SDK and the judge were pointed at it with
`ANTHROPIC_BASE_URL`, which both read, and given `ANTHROPIC_API_KEY=fake`; on
your machine the first is left out and the second is your key. Paths are
shortened to `…`. Three outputs were run again, at `d746ec12`, after #958
changed their words, against the same stand-in: the refusal of the last
`promote`, and in the listing before the last yes the count of calls a turn
attached and of the interrupted episodes. The run key and the time in them
are those of the run the rest of the page shows, where the run again named
its own.

## Day one: recording

**The tools**, as the model is told of them and as the agent runs them:

```python
# tools.py
ORDERS = {
    "42": {"status": "shipped", "shipped_on": "2026-11-03"},
    "17": {"status": "packing"},
}

TOOLS = [
    {
        "name": "lookup_order",
        "description": "Read an order's status.",
        "input_schema": {
            "type": "object",
            "properties": {"order": {"type": "string"}},
            "required": ["order"],
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund an order in full.",
        "input_schema": {
            "type": "object",
            "properties": {"order": {"type": "string"}},
            "required": ["order"],
        },
    },
    {
        "name": "escalate",
        "description": "Hand the ticket to a person.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]


def run_tool(name: str, arguments: dict[str, str]) -> str:
    if name == "lookup_order":
        return str(ORDERS[arguments["order"]])
    if name == "issue_refund":
        return f"refunded {arguments['order']}"
    return "escalated"
```

**The agent: one client, wrapped once, and one episode per turn.** The
episode is the turn, from the ticket to the answer; every call made inside
it names the same suite:

```python
# agent.py
import anthropic
from digline import recorder
from tools import TOOLS, run_tool

client = recorder.wrap(anthropic.Anthropic(), app="support", tenant="acme")
MODEL = "claude-haiku-4-5"
SYSTEM = (
    "You answer a customer's ticket. Look the order up before you say anything "
    "about it, and before you refund it. Hand the ticket to a person when you "
    "cannot answer it."
)


def handle(ticket: str) -> str:
    with recorder.episode(client, suite="support", case={"ticket": ticket}) as ep:
        messages = [{"role": "user", "content": ticket}]
        while True:
            reply = client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
                suite="support",
            )
            if reply.stop_reason != "tool_use":
                answer = reply.content[0].text
                ep.output(answer)
                return answer
            messages.append({"role": "assistant", "content": reply.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": run_tool(block.name, block.input),
                }
                for block in reply.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})
```

`case=` is what started the turn, and is what a case of the suite will hold.
`ep.output(...)` is the turn's answer
([an episode](../record.md#a-turn-of-an-agent-episode)).

**The model's reply goes back as it came**, `reply.content`, the SDK's own
objects. The wrapper writes each of them as the SDK sends it, so every call
of the turn is recorded. With digline at `1b5cf083` it did not: the next
call carried something a recording could not hold, `digline record status`
said `not recorded: not JSON 2`, the second call of each turn that used a
tool, and each of those turns was written with one model step where it took
two. The page was run then with the reply dumped by hand,
`block.to_dict()`. This agent was run again on 2026-11-09, with digline at
`d770ae2a`, through every ticket below: its thirteen recordings are the
ones the page was made from, but for their moments, the episodes' ids and
the latencies, and the two `record status` blocks came out the same.

**The day's tickets:**

```python
# traffic.py
from agent import handle

for ticket in (
    "Where is my order 42?",
    "Where is my order 17?",
    "How long do I have to return a jacket?",
):
    print(handle(ticket))
```

**Switch it on, and run it**, from the project's root:

```console
$ digline record on --tenant acme
recording on for tenant 'acme': …/support/.digline/acme/recorder.toml
  values: on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  development: what the file leaves out is a default; an application that resolves its tenant per request is production (wrap(tenant=callable) in Python, DiglineRecorder.production in Java and Node; the proxy's --tenant is never production), and refuses this file unless it declares sample, redact and ceiling
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18797 ANTHROPIC_API_KEY=fake python traffic.py
Order 42 shipped on 3 November and arrives on Friday.
Order 17 is being packed and ships tomorrow.
You can return it within 14 days of delivery.
```

```console
$ digline record status --tenant acme
tenant 'acme' · recording on
  switch:     …/support/.digline/acme/recorder.toml
  values:     on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  writes to:  …/support/.digline/acme/recordings
  size:       15876 bytes of recordings (as written; disk use is higher), ceiling 104857600
  suite support: 5 calls, 5 inside episodes, 0 orphans, 3 episodes; since the last import: not read (pass --suite)
```

Three turns, three episodes. The two that looked an order up made two model
calls each, and the one about returns made one: five calls, every one inside
its turn, and no orphan, a call made while a turn was open that was not in
it. The status counts; the steps of each turn are in its recording, and the
import below shows their shape.

**A turn that breaks.** A ticket for an order the shop does not have:

```python
# missing.py
from agent import handle

print(handle("Where is my order 99?"))
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18797 ANTHROPIC_API_KEY=fake python missing.py
Traceback (most recent call last):
  …
KeyError: '99'
```

The model asked for `lookup_order`, and the tool raised. The exception went
on to the program as it was raised, and the turn was still recorded:

```console
$ digline record status --tenant acme
tenant 'acme' · recording on
  switch:     …/support/.digline/acme/recorder.toml
  values:     on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  writes to:  …/support/.digline/acme/recordings
  size:       19431 bytes of recordings (as written; disk use is higher), ceiling 104857600
  suite support: 6 calls, 6 inside episodes, 0 orphans, 4 episodes, 1 interrupted; since the last import: not read (pass --suite)
```

## Day two: from recordings to a suite

**A first suite, proposed**, from a directory `eval/` in the project:

```console
$ digline suggest --suite support --tenant acme --repository private --root ..
digline suggest: wrote …/support/eval/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: 8eca4da7 for episodes
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic, bedrock, openai
  each check: 1. length, every one of 3 recordings answers text; maximum is a placeholder, the strictest the check accepts: no run measured it
  each check: 2. never, declared to the model and called in none of 3 recordings
  each check: 3. never, declared to the model and called in none of 3 recordings
  each check: 4. max_steps, the model's turns, in an agent's episode; limit is a placeholder, the strictest the check accepts: no run measured it
  each check: 5. latency_budget, every one of 3 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 6. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 8 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · episodes, text · 2 answers from 2 recordings
not yet examined: group 2 · episodes, text · 1 answer from 1 recording
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
```

It read three turns: the one that broke is not among them. The two `never`
checks are the two tools declared to the model and called in no turn,
`issue_refund` and `escalate`. `max_steps` counts the model's turns in an
episode, with the placeholder `limit = 1`.

**Adopting it** is copying the file to `suite.toml` and writing what it
leaves to you, here more than the place it runs, the rubric and the judge:

```console
$ diff suite.proposed.toml suite.toml
11c11
< # environment = WRITE: mandatory, with no default: where it runs
---
> environment = "dev"
36,38c36,39
< # declared to the model and called in none of 3 recordings
< type = "never"
< tool = "issue_refund"
---
> # a refund only after the order was looked up
> type = "before"
> first = "lookup_order"
> then = "issue_refund"
49c50
< limit = 1  # placeholder: yours to write
---
> limit = 4
72,73c73,74
<   rubric = "WRITE: one question a good answer says yes to"  # placeholder: yours to write
<   judge = "provider/model"  # placeholder: yours to write, docs/declarative.md#the-judge-by-coordinates
---
>   rubric = "Does the reply answer the ticket, and is what it says true?"
>   judge = "anthropic/claude-haiku-4-5"
```

- **`never` on `issue_refund` goes.** No turn of day one refunded, so the
  proposal read the refund as a tool never called; refunding is the agent's
  job. Kept beside the `before` below, the suite refused to load, naming
  `never` and `before` and saying to remove one of the two.
- **`before`, written by hand**: a refund only after the order was looked
  up. The proposal writes one only where the recordings hold it, every call
  to one tool with a call to the other before it, and no recording called
  `issue_refund`. It passes on a turn that never refunds.
- **`limit = 4`** is a number of the person's, not one a run measured. Kept
  at 1, the placeholder fails every turn that looks an order up, which takes
  two model calls: on a copy of this project, the first run with it
  contradicted both yeses below on `max_steps`.

**A person's yes or no**, on the page `digline view` serves with
`--allow-record`:

```console
$ digline view --suite eval/suite.toml --allow-record
digline view on http://127.0.0.1:7373/?launch=… — the recorder's writes enabled, for the first browser that opens this address; --allow-promote to promote — ctrl-c to stop
```

Its *Recordings* view lists the answers in two groups, by the shape of their
steps: *an episode, text, steps model → tool → model, finish stop*, the two
turns that looked an order up, and *an episode, text, steps model, finish
stop*, the one about returns. **The page shows the shape of a turn's steps,
not its tools**: each answer is a row with its id, how many calls it
attached, when it was first recorded, its setup and its answer, and no row
names `lookup_order` or its arguments. The turn that broke is counted under
the list, *1 interrupted episode*, and has no row.

Two yeses and a no, the no for the answer that gives 14 days to return a
jacket where the shop gives 30, written under the name *Ada Lovelace*, wrote
three cases to `eval/captured.json`. The form was sent as the button sends
it, by a client that runs no script. With the same choices written out, the
command is:

```console
$ digline record import --tenant acme --suite eval/suite.toml --good cap-f55d18ebe840ddf8-092facef --good cap-02f11dc89ad75297-29020d78 --bad cap-c5fdedf6071b2f80-e1861177 --by 'Ada Lovelace'
tenant 'acme' · suite support · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-f55d18ebe840ddf8-092facef
tenant 'acme' · suite support · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-02f11dc89ad75297-29020d78
tenant 'acme' · suite support · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-c5fdedf6071b2f80-e1861177
3 cases written to eval/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

Run against a copy of the same recordings, it wrote the same
`captured.json` as the button, byte for byte. Each case from a turn carries
the turn's steps, so the diff of `captured.json`, the review, shows them,
tools and arguments included. The first case's `steps`, on fewer lines than
the file writes them:

```json
[
  {"actor": "model", "finish": "tool_use", "index": 0},
  {"actor": "tool", "arguments": "{\"order\":\"42\"}", "index": 1, "result_absence": "not_reported", "status": "not_reported", "tool": "lookup_order"},
  {"actor": "model", "finish": "stop", "index": 2}
]
```

The tool's result is `not_reported`: in process, the recorder sees the call
the model asked for and not what the tool returned.

**The run, and the reference.** The suite's cases are reviewed answers, so
the run asks the judge and never the agent:

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18797 ANTHROPIC_API_KEY=fake digline run --suite eval/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 3 reviewed answers judged 27 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 27 calls · counts: 4860 in / 378 out · cost: 0.006750 USD
digline: recorded .digline/acme/runs/support/2026-11-09T07-33-58-931049-00-00-7aa9217a99f7b370.json
digline: next: digline promote --suite eval/suite.toml --run latest --replacing none  # keeps this run as the reference
2026-11-09T07-33-58-931049-00-00-7aa9217a99f7b370
```

Each turn was asked four checks: the judged one, and the three on the
steps, `before`, `never` and `max_steps`, which a reviewed answer of a turn
carries. `length` and `latency_budget` gave no verdict on these cases, and
wait for a case the agent answers. The judge said no to the 14 days, as the
person did. A person made the run the reference:

```console
$ digline promote --suite eval/suite.toml --run latest --replacing none
tenant 'acme' · support baseline set to 2026-11-09T07-33-58-931049-00-00-7aa9217a99f7b370
```

**A turn that refunds without looking.** A later ticket:

```python
# later.py
from agent import handle

print(handle("Order 42 arrived torn. I want my money back."))
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18797 ANTHROPIC_API_KEY=fake python later.py
I have refunded order 42. The money is back on your card in 5 days.
```

The model asked for `issue_refund` first, and never for `lookup_order`. The
listing puts the turn in the first group, beside the two lookups, because
its shape is theirs, *model → tool → model*:

```console
$ digline record import --tenant acme --suite eval/suite.toml
tenant 'acme' · suite support · writes to eval/captured.json · repository private · check llm_rubric
  deterministic_output false

group 1 · an episode, text, steps model → tool → model, finish stop · 3 answers from 3 recordings
  setup in force for episodes: 8eca4da7
  cap-f55d18ebe840ddf8-092facef · 2026-11-09T07:32:43.394154+00:00 · setup 8eca4da7 · 2 calls attached
    input:  {"ticket": "Where is my order 42?"}
    answer: Order 42 shipped on 3 November and arrives on Friday.
    already in the file, --good
  cap-02f11dc89ad75297-29020d78 · 2026-11-09T07:32:43.398308+00:00 · setup 8eca4da7 · 2 calls attached
    input:  {"ticket": "Where is my order 17?"}
    answer: Order 17 is being packed and ships tomorrow.
    already in the file, --good
  cap-1883cef159843149-84877bca · 2026-11-09T07:34:11.213354+00:00 · setup 8eca4da7 · 2 calls attached
    input:  {"ticket": "Order 42 arrived torn. I want my money back."}
    answer: I have refunded order 42. The money is back on your card in 5 days.
    electable

group 2 · an episode, text, steps model, finish stop · 1 answer from 1 recording
  setup in force for episodes: 8eca4da7
  cap-c5fdedf6071b2f80-e1861177 · 2026-11-09T07:32:43.399852+00:00 · setup 8eca4da7 · 1 call attached
    input:  {"ticket": "How long do I have to return a jacket?"}
    answer: You can return it within 14 days of delivery.
    already in the file, --bad

4 answers in 2 groups, from 13 recordings of the suite; not cases: 0 orphans, 0 calls whose episode is not among the files, 1 interrupted episode, 0 over the ceiling of a recording, 0 files that are not readable recordings
to write, name each answer with --good ID or --bad ID, and give --by NAME, your own name. An answer not named stays out
```

The answer reads right, and the person said yes to it:

```console
$ digline record import --tenant acme --suite eval/suite.toml --good cap-1883cef159843149-84877bca --by 'Ada Lovelace'
tenant 'acme' · suite support · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-1883cef159843149-84877bca
1 case written to eval/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18797 ANTHROPIC_API_KEY=fake digline run --suite eval/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 4 reviewed answers judged 36 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 36 calls · counts: 6480 in / 504 out · cost: 0.009000 USD
digline: a check on the steps contradicted a person on 1 reviewed answer: before, on case cap-1883cef159843149-84877bca.
digline: recorded .digline/acme/runs/support/2026-11-09T07-34-16-759642-00-00-7aa9217a99f7b370.json
digline: next: digline compare --suite eval/suite.toml --run latest  # says whether anything got worse
2026-11-09T07-34-16-759642-00-00-7aa9217a99f7b370
```

The run exited `0`, and named the contradiction. The judge
passed the answer, as the person did; `before` did not, because the turn
refunded an order it had not looked up.

```console
$ digline explain --suite eval/suite.toml --run latest
What ran
A check on the steps contradicted a person on 1 reviewed answer: before, on case cap-1883cef159843149-84877bca, and the case fails: cap-1883cef159843149-84877bca for before, failed where the person said yes. It is counted in no aggregate, and the target was not asked for it.
4 cases ran.
16 checks ran.
Every case could be judged.
No case is suspended.
The suite's checks are unchanged from the reference.

What differed underneath
Nothing in this group.

What moved
cap-1883cef159843149-84877bca · before failed at 0.000000, and a person said yes to the turn: its steps contradict the person, and the case fails.
```

> **Arrives with digline 1.3.** Before 1.3, the sentence reads *The suite is
> unchanged from the reference.*, here and below.

```console
$ digline compare --suite eval/suite.toml --run latest
A check on the steps contradicted a person on 1 reviewed answer: before, on case cap-1883cef159843149-84877bca, and the case fails: cap-1883cef159843149-84877bca for before, failed where the person said yes. Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
tenant 'acme', against baseline 2026-11-09T07-33-58-931049-00-00-7aa9217a99f7b370
```

`explain` and `compare` exited `1`. **A yes on a turn is a yes to its steps
too**, and the person vouched for a turn that refunded without looking. Which
of the two is wrong, the rule or the yes, is the person's to say; the run
cannot become the reference while they disagree:

```console
$ digline promote --suite eval/suite.toml --run latest --replacing 2026-11-09T07-33-58-931049-00-00-7aa9217a99f7b370
digline: run 2026-11-09T07-34-16-759642-00-00-7aa9217a99f7b370: a check on the steps contradicted a person on 1 reviewed answer: before, on case cap-1883cef159843149-84877bca, by answer cap-1883cef159843149-84877bca (failed a yes). The person's yes or no is the expected verdict, and a baseline where a check contradicts the person is not a baseline. Promote a run whose every check agreed with every person
```

It exited `64`, and the reference stayed the first run.

## What you get, and what stays out

- **An episode is a turn, and a turn is a case.** One recording holds the
  turn, from the `case=` that started it to the answer, with its steps. **A
  call inside it is a step, not a case**: the import read 13 recordings of the
  suite, eight calls and five turns, and listed four answers, one for each
  turn that ended.
- **A turn that raises is recorded, marked interrupted, and never a case.**
  The ticket for order 99 is counted by `record status` and by the import,
  and has no row anywhere a yes or a no is given.
- **In process, a turn ends with its `with` block.** There is no wait for
  it, and no idle time. `--episode-idle` belongs to
  [the proxy](../record.md#through-the-proxy-digline-record-proxy), for an
  application whose turns arrive as separate HTTP calls marked with one
  `X-Digline-Episode`: the proxy writes the turn once no call has carried
  that value for 30 seconds, or the value given, and a turn off the wire is
  never interrupted. Measured with this stand-in through the proxy and
  `--episode-idle 2`: right after the turn's second call, `record status`
  counted its two calls and no episode, and four seconds later the episode.
- **A call made inside a turn from another thread is not one of its
  steps.** Measured with this agent's client, a call from a
  `ThreadPoolExecutor` worker or a `threading.Thread` inside an open episode
  was counted as an orphan, and with `recorder.attach(ep.id)` around it, in
  the thread, as a call inside the episode.
- **digline records the agent through its own doors**: `wrap()` and
  `episode()` here, the proxy, and the Java and Node recorders. It does not
  read another tool's traces. OpenTelemetry is left for the production side,
  and is not decided
  ([ADR 0062](../adr/0062-the-recorder-out-of-process-and-in-other-processes.md)
  §6).
- **No call in this story reached Anthropic or a model.** The agent's tool
  calls and answers, the judge's scores and the token counts the costs are
  printed from are the stand-in's.

The pages this one leans on: [`digline record`](../record.md),
[`digline suggest`](../suggest.md), [the checks on the
steps](../api.md#four-checks-on-the-steps) and
[`digline view`](../view.md#-allow-record).
