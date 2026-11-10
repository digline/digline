# From the IDE's agent, over MCP: from recordings to a gate

This page shows an IDE's agent reading recordings and measuring over
MCP, while the person decides, from the first suite to a gate.

## Who this is for

A developer whose IDE has an agent that speaks MCP, working on an application
that calls a model, and who wants the agent to help turn what the application
answered into a suite that gates it. The agent reads and measures through
`digline-mcp`; the person decides.

Everything on this page was run, on 2026-11-07, with digline, `digline-mcp`
and `digline-anthropic` installed from this repository at `1b5cf083`, the
`mcp` SDK 2.3.0 and `anthropic` 2.4.0. It was first run at `37d5c1dd`, and
run again at `1b5cf083`, where `where` says the next step in words and
`run`'s `notes` say a contradiction; what it shows is the second run. The
line `promote` prints when it refuses the second day's run was run a third
time, at `d746ec12`, after #958 took the class's name out of it, against the
same stand-in; the run key in it is the second run's, where the third named
its own. **No call reached a model.** A
stand-in for Anthropic's Messages API on 127.0.0.1 answered the application
and the judge, and every answer, score and token count below is the
stand-in's. **No IDE was driven**: the tool calls were made by a client of the
`mcp` SDK that starts the server as `.mcp.json` declares it, over stdio, the
way `.github/mcp_tools.py` does. Paths are shortened to `…`. The stand-in and
the client are `tests/_story_ide_stand_in.py` and
`tests/_story_ide_mcp_client.py`, and `tests/test_story_from_the_ide.py`
replays this page against them.

## Day one: from recordings to a suite

**The application records.** It is `app.py`, a call through Anthropic's
client, wrapped ([the recorder](../record.md#wrapping-the-client)):

```python
import anthropic
import digline.recorder as recorder

client = recorder.wrap(anthropic.Anthropic(), app="helpdesk", tenant="acme")


def category(ticket: str) -> str:
    reply = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=20,
        system="Answer with the category of the ticket: refund, delivery, account or other.",
        messages=[{"role": "user", "content": ticket}],
        suite="category",
    )
    return reply.content[0].text
```

```console
$ digline record on --tenant acme
recording on for tenant 'acme': …/helpdesk/.digline/acme/recorder.toml
  values: on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  development: what the file leaves out is a default; an application that resolves its tenant per request is production (wrap(tenant=callable) in Python, DiglineRecorder.production in Java and Node; the proxy's --tenant is never production), and refuses this file unless it declares sample, redact and ceiling
```

It answered four tickets, with `ANTHROPIC_BASE_URL` at the stand-in:
*refund* to *"Where is my refund for the blue jacket?"*, *delivery* to *"The
parcel never arrived."*, *account* to *"How do I change my password?"*, and
*other* to *"I want my money back for the shoes."*, which is wrong.

**The server**, in the project's `.mcp.json`:

```json
{
  "mcpServers": {
    "digline": {
      "command": "digline-mcp",
      "args": ["--root", ".", "--names", "clear"],
      "env": {
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:18791",
        "ANTHROPIC_API_KEY": "fake"
      }
    }
  }
}
```

`--names clear` says the store's names may leave as they are: the cases are
the project's own ([whether the names may leave](../mcp.md#whether-the-names-may-leave-names)).
`env` points the judge, which the server runs, at the stand-in; on your
machine those two lines are left out, and the judge's key reaches the server
however your client passes an environment to the servers it starts.

**Where am I?** The agent asked `where` for the suite it meant to write:

```json
{"tenant": "acme", "suite": "eval/suite.toml"}
```

It was refused, and the refusal says why: *"the suite 'eval/suite.toml' names
no file inside …/helpdesk (looked at …/helpdesk/eval/suite.toml). This server
takes a path to a suite within its own repository — not a module to import,
because a module resolves through `sys.path` and could be anywhere."* Asked
with the tenant alone, `{"tenant": "acme"}`, it answered:

```json
{
  "output_version": 5,
  "tenant": "acme",
  "suite": "category",
  "state": "no_suite_yet",
  "count": 4,
  "shapes": [
    {
      "episode": false,
      "kind": "text",
      "actors": [],
      "finish": null,
      "recordings": 4
    }
  ],
  "run_key": null,
  "run_exit_code": null,
  "last_import": null,
  "capture": null,
  "proposal": null,
  "next": {
    "say": "The recordings name suite category, and no suite declares where its captured cases go, so nothing reads them as cases. Write the suite with a capture declaration, or let an agent propose one by digline's method.",
    "command": null,
    "docs": [
      {
        "page": "proposing-a-suite.md",
        "anchor": "",
        "url": "https://digline.dev/product/proposing-a-suite/"
      },
      {
        "page": "declarative.md",
        "anchor": "capture",
        "url": "https://digline.dev/product/declarative/#capture"
      }
    ]
  }
}
```

Four recordings name suite `category`, and no suite reads them. There is no
command for the next step, `"command": null`, because the step is a suite to
write. `next.say` says it, in the sentence the command line prints under its
title:

```console
$ digline where --tenant acme
4 recording(s) in category, no suite yet
The recordings name suite category, and no suite declares where its captured cases go, so nothing reads them as cases. Write the suite with a capture declaration, or let an agent propose one by digline's method.
  a single call, text · 4
The page that says more: https://digline.dev/product/proposing-a-suite/
The page that says more: https://digline.dev/product/declarative/#capture
```

**A proposal, as facts.** The agent asked `suggest` for a suite that does not
exist yet, `{"name": "category", "tenant": "acme", "repository":
"private"}`. Of its answer:

```json
{
  "tenant": "acme",
  "suite": "category",
  "repository": "private",
  "proposal": "suite.proposed.toml",
  "written": false,
  "command": "digline suggest --suite category --tenant acme --repository private",
  "setups": {
    "single_calls": [
      "6d20afaa"
    ],
    "episodes": []
  },
  "judge": {
    "check": "llm_rubric",
    "declared": false,
    "plugins": [
      "anthropic",
      "bedrock",
      "openai"
    ]
  },
  "checks": [
    {
      "number": 1,
      "type": "length",
      "name": "length",
      "placeholders": 1
    },
    {
      "number": 2,
      "type": "latency_budget",
      "name": "latency_budget",
      "placeholders": 2
    },
    {
      "number": 3,
      "type": "repeated",
      "name": "llm_rubric",
      "placeholders": 4
    }
  ],
  "placeholders": 7,
  "groups": [
    {
      "episode": false,
      "kind": "text",
      "actors": [],
      "finish": null,
      "answers": 4,
      "recordings": 4,
      "waiting": null
    }
  ],
  "assistant": {
    "asked": false,
    "sentence": "no assistant over this surface: what one costs is said before its call, and a tool has no before. Run the command by hand to ask one",
    "command": "digline suggest --suite category --tenant acme --repository private --model provider/model"
  }
}
```

`"written": false`, and the call added no file to the project.
The command is the person's, run by hand from the project's root:

```console
$ digline suggest --suite category --tenant acme --repository private
digline suggest: wrote …/helpdesk/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: 6d20afaa for single calls
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic, bedrock, openai
  each check: 1. length, every one of 4 recordings answers text; maximum is a placeholder, the strictest the check accepts: no run measured it
  each check: 2. latency_budget, every one of 4 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 3. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 7 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · single calls, text · 4 answers from 4 recordings
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
```

**Adopting it** is copying the file to `suite.toml` and writing where the
suite runs, the rubric and the judge:

```console
$ diff suite.proposed.toml suite.toml
11c11
< # environment = WRITE: mandatory, with no default: where it runs
---
> environment = "dev"
55,56c55,56
<   rubric = "WRITE: one question a good answer says yes to"  # placeholder: yours to write
<   judge = "provider/model"  # placeholder: yours to write, docs/declarative.md#the-judge-by-coordinates
---
>   rubric = "Is the category right for the ticket?"
>   judge = "anthropic/claude-haiku-4-5"
```

**What there is to review.** The agent asked `record_listing`,
`{"suite": "suite.toml"}`:

```json
{
  "output_version": 5,
  "tenant": "acme",
  "suite": "category",
  "declaration": {
    "cases_file": "captured.json",
    "repository": "private",
    "check": "llm_rubric",
    "taken_from": null
  },
  "setups": {
    "single_calls": "6d20afaa",
    "episodes": null
  },
  "samples": 3,
  "deterministic_output": false,
  "groups": [
    {
      "shape": {
        "episode": false,
        "kind": "text",
        "actors": [],
        "finish": null
      },
      "setup": "6d20afaa",
      "answers": 4,
      "recordings": 4,
      "waiting": 4,
      "good": 0,
      "bad": 0,
      "refused": {
        "already_in_the_file": 0,
        "earlier_setups": 0,
        "no_input": 0,
        "conversation": 0
      }
    }
  ],
  "recordings": 4,
  "not_shown": {
    "orphans": 0,
    "detached": 0,
    "interrupted": 0,
    "oversize": 0,
    "unreadable": 0
  },
  "examined_through": "2026-11-07T10:30:05.292758+00:00",
  "review": {
    "sentence": "to review an answer, open digline view: the address is its page at the default port, 7373, and a view started with another --port serves it there",
    "command": "digline view --suite suite.toml",
    "address": "http://127.0.0.1:7373/recordings/acme/category/"
  }
}
```

Four answers waiting, counted, and none of them quoted. `review` is where
they are read.

**The yes and the no are the person's**, on the page `digline view` serves,
with `--allow-record` for the page to write them:

```console
$ digline view --suite suite.toml --allow-record
digline view on http://127.0.0.1:7373/?launch=… — the recorder's writes enabled, for the first browser that opens this address; --allow-promote to promote — ctrl-c to stop
```

The page at the address `review` gave lists the four answers, `refund`,
`delivery`, `account` and `other`, each with its id and with `--good` and
`--bad`. Three yes, a no to `other`, and *Ada Lovelace* in *Your name, the
mark each case carries (--by)*; *Write the answers named* wrote
`captured.json`, and the page then read *already in the file, --good* beside
the three and *already in the file, --bad* beside `other`. Under the button
is the command that does what it does:

```console
$ digline record import --tenant acme --suite suite.toml --good cap-b4d31f002325c701-1d630127 --good cap-c9c4382ee542663e-b4af39d5 --good cap-ee0ce4060b13a8c5-9af21132 --bad cap-cb302b3d659efb86-d9298a10 --by 'Ada Lovelace'
tenant 'acme' · suite category · writes to captured.json · repository private · check llm_rubric
  wrote cap-b4d31f002325c701-1d630127
tenant 'acme' · suite category · writes to captured.json · repository private · check llm_rubric
  wrote cap-c9c4382ee542663e-b4af39d5
tenant 'acme' · suite category · writes to captured.json · repository private · check llm_rubric
  wrote cap-ee0ce4060b13a8c5-9af21132
tenant 'acme' · suite category · writes to captured.json · repository private · check llm_rubric
  wrote cap-cb302b3d659efb86-d9298a10
4 cases written to captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

Run on a copy of the project taken before the button, it wrote the same
`captured.json`, byte for byte.

**The run.** The agent asked `run`, `{"suite": "suite.toml"}`, and was
refused until it said the count back: *"this suite plans 0 calls to the
target. tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 4
reviewed answers judged 36 times, with no call to the target; each answer is
judged 3 times by llm_rubric. Call again with acknowledge_calls=0 to run it.
The count is calls to the target; where an assertion judges each answer
several times the sentence above names the multiplier, and that is the figure
to report."* With `"acknowledge_calls": 0` it ran: 36 calls to the judge,
none to the application. Its answer names the run's key and its usage, and no
verdict; `get_run` has them. Of its `results`, the no, with the keys that
say nothing here left out:

```json
{
  "case_id": "cap-cb302b3d659efb86-d9298a10",
  "reviewed": {
    "check": "llm_rubric",
    "good": false
  },
  "verdicts": [
    {
      "assertion": "llm_rubric",
      "status": "fail",
      "score": 0.0,
      "threshold": 1.0,
      "samples": [
        0.0,
        0.0,
        0.0
      ]
    }
  ]
}
```

The three yes passed at 1.0, and the no failed at 0.0: the judge agreed with
the person on all four. `length` and `latency_budget` produced no verdict:
every case is a reviewed answer, which is asked its judged check alone.

**The reference is the person's too.** There is no `promote` tool
([why](../mcp.md#why-the-surface-has-this-shape)), so it was typed:

```console
$ digline promote --suite suite.toml --run latest --replacing none
tenant 'acme' · category baseline set to 2026-11-07T14-18-35-151704-00-00-5540731bb0925c86
```

A second `run`, then `compare`, answered *"Nothing got worse compared with
the reference. Every case could be judged. No case is suspended. The suite is
unchanged from the reference."*, with `"exit_code": 0`.

## Day two: when the judge contradicts a person

The application answered a fifth ticket, *"Can I return a gift without the
receipt?"*, with *refund*. `where` on the suite answered `"state":
"to_import"`, `"count": 1`, and the command for the next step,
`"digline record import --tenant acme --suite suite.toml"`. The person read
the answer, judged it right, and said yes:

```console
$ digline record import --tenant acme --suite suite.toml --good cap-9886a52f697cd007-1d630127 --by 'Ada Lovelace'
tenant 'acme' · suite category · writes to captured.json · repository private · check llm_rubric
  wrote cap-9886a52f697cd007-1d630127
1 case written to captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

The agent ran the suite again, with `"acknowledge_calls": 0` after the same
refusal, now for 5 answers judged 45 times. Of its answer:

```json
{
  "key": "2026-11-07T14-18-40-132240-00-00-5540731bb0925c86",
  "sentence": "tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 5 reviewed answers judged 45 times, with no call to the target; each answer is judged 3 times by llm_rubric",
  "notes": [
    "the judge contradicted a person on 1 reviewed answer"
  ],
  "errored_checks": 0,
  "usage": {
    "judge": {
      "calls": 45,
      "input_tokens": 945,
      "output_tokens": 270,
      "spent_usd": 0.002295
    }
  }
}
```

Its `notes` say what `digline run` says on standard error beside the bill:
the judge contradicted a person. Which answer, and which way, `compare`
says. Of its answer:

```json
{
  "sentence": "The judge contradicted a person on 1 reviewed answer, and the case fails: cap-9886a52f697cd007-1d630127 for llm_rubric, failed where the person said yes. Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite is unchanged from the reference.",
  "worse": false,
  "exit_code": 1,
  "reviewed_passed_no": 0,
  "reviewed_failed_yes": 1
}
```

And `explain`, the same run read back as facts, with the exit code. Of its
facts, the one about the reviewed answers:

```json
{
  "exit_code": 1,
  "facts": [
    {
      "about": "run",
      "kind": "reviewed",
      "count": 1,
      "state": null,
      "contradictions": [
        {
          "case_id": "cap-9886a52f697cd007-1d630127",
          "check": "llm_rubric",
          "direction": "failed_yes"
        }
      ]
    }
  ]
}
```

The command a person types for the same reading says the same, in prose:

```console
$ digline explain --suite suite.toml --run latest
What ran
The judge contradicted a person on 1 reviewed answer, and the case fails: cap-9886a52f697cd007-1d630127 for llm_rubric, failed where the person said yes. It is counted in no aggregate, and the target was not asked for it.
5 cases ran.
5 checks ran.
Every case could be judged.
No case is suspended.
The suite is unchanged from the reference.

What differed underneath
Nothing in this group.

What moved
cap-9886a52f697cd007-1d630127 · llm_rubric failed at 0.000000, and a person said yes to the answer: the judge contradicts the person, and the case fails.
```

The person said a return is a refund, and the judge, asked three times, said
it was not. Which of the two is wrong, the rubric or the yes, is the
person's to say. Until it is said, the run is not a reference:

```console
$ digline promote --suite suite.toml --run latest --replacing 2026-11-07T14-18-35-151704-00-00-5540731bb0925c86
digline: run 2026-11-07T14-18-40-132240-00-00-5540731bb0925c86: the judge contradicted a person on 1 reviewed answer, by answer cap-9886a52f697cd007-1d630127 (failed a yes). The person's yes or no is the expected verdict, and a baseline where a check contradicts the person is not a baseline. Promote a run whose every check agreed with every person
```

## What you get, and what stays out

- **Facts and counts cross MCP, never the recorded text.** None of the
  answers above, from `where`, `suggest`, `record_listing`, `run`, `get_run`,
  `compare` and `explain`, holds a ticket or an answer the application gave.
  Searched for *refund*, *delivery*, *password*, *shoes*, *parcel*, *gift* and
  *receipt*, the eleven answers and three refusals the agent received held
  none of them, and the recordings held them. Cases are named by their id.
- **No tool calls a model of its own accord.** `suggest` asks no assistant and
  says so; the command with `--model` is the person's. `run` calls the judge
  the suite declares, and only after the agent has said back the number of
  calls to the target; its sentence names the judge's calls too.
- **The yes and the no stay with the page.** No tool writes them:
  `record_listing` counts what waits and gives the page's address, and the
  page, or the command under its button, writes `captured.json`.
- **No tool writes what the repository commits.** `run` writes its run under
  `.digline/acme/runs/`, which the `.digline/.gitignore` digline writes
  leaves out. `promote` is a person's command, and `suggest` over MCP returns
  the command that writes the proposal, which a person runs.
- **No call in this story reached a model.** The application's answers, the
  judge's scores and the token counts the costs are printed from are a
  stand-in's.

The pages this one leans on: [the MCP server](../mcp.md),
[`digline record`](../record.md), [`digline suggest`](../suggest.md) and
[`digline view`](../view.md#-allow-record).
