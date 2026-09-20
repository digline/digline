# Has my MCP server's tool descriptions changed?

A tool description is not documentation. It is text placed in the model's
context that decides **when the model calls the tool** — so it is
configuration, and an upgrade can rewrite it without changing a single tool
name, a single signature, or anything your tests look at.

That this happens is measured, and the measurement is not ours.
[EvalSeal](https://github.com/maurathat/evalseal) read 10 published MCP server
packages across 79 installed versions and 63 consecutive version pairs, and
found **51 tool descriptions rewritten with the tool name unchanged**, a net
**+2,401 characters** of model-facing instruction. Of 38 material changes, 20
kept the names identical. One release added a conditional clause telling the
model when *not* to call the tool. Every one of those is a behaviour change
that a name-based check reads as no change at all.

digline has no feature for this, and does not need one. What follows is a
recipe built out of [declared artifacts](api.md), which already record a file's
content and SHA-256 in every run and diff it against the baseline.

## Dump it canonically, or the recipe does not work

Do this part first, because it is the part that decides whether the rest is
useful.

```python
# tools/dump_tools.py
import json
from pathlib import Path

tools = await session.list_tools()          # your MCP client
payload = [
    {
        "name": t.name,
        "description": t.description,
        "inputSchema": t.inputSchema,
    }
    for t in sorted(tools.tools, key=lambda t: t.name)
]
Path("tools.json").write_text(
    json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
```

Three things matter and all three are in that call. **Sort the tools by name**,
because a server is under no obligation to return them in a stable order.
**`sort_keys=True`**, because a JSON object has no order and your client library
is not promising you one. **`indent=2`**, because the diff you will read is
line-oriented: a single-line blob reports `+1 −1` for every change, from a typo
to a rewritten instruction, and tells you nothing about which.

Skip any of them and here is what you get: the SHA moves on **every run**, the
report says the file under test changed every time, and within a week you have
taught yourself to scroll past the one line that was supposed to be the alarm.
A check that cries wolf is worse than no check, and this one cries wolf by
default unless you make the dump canonical.

### The asymmetry, so you do not think it is a bug

digline canonicalises tool-call *arguments* and does not canonicalise
*artifacts*. `ToolCalledWith` compares what the model sent through
`canonical()`, so `{"b": 2, "a": 1}` and `{"a": 1, "b": 2}` are one call.
`Suite.artifacts` hashes the bytes on disk, exactly as they are.

Both are deliberate. An assertion is comparing two values and knows it is
comparing JSON. An artifact is any file a suite declares — a prompt, a rubric,
a YAML config, a Python module — and a hash that "helpfully" reformatted its
subject would be hashing something other than the file under test. The file is
the evidence; normalising evidence is how you lose it.

The consequence is just that the canonicalising is **yours** to do, on the way
in. That is what the `sort_keys` above is.

## Declare it

```python
from pathlib import Path
from digline.run import Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="agent",
    artifacts=[Path("tools.json")],
    ...
)
```

From then on every run records the file's SHA-256 and its full text;
`digline compare` reports it as changed against the baseline and the HTML
report renders the unified diff **above** the score deltas, because a change to
what was under test changes how every number below it reads.

## Nobody fetches `tools/list` for you

This is the limit of the recipe and it is worth its own paragraph, because
getting it wrong produces a check that looks like it passed.

digline never runs your dump script. It reads a file off disk at the moment the
run starts, and `Suite.artifacts` discovers nothing by convention — a file that
is evidence is a file somebody named. If `tools.json` is three weeks old
because the dump ran once and then stopped running, digline records its SHA
faithfully, `compare` reports **unchanged**, and that word is true of the file
and false of your server. A stale dump is worse than no artifact at all: no
artifact is a visible absence, whereas a stale one reads as a verification that
happened.

So the refresh is the **suite author's** job, and it belongs wherever the suite
runs — the same CI step, immediately before `digline run`, not a cron job on
somebody's laptop and not a manual step in a runbook. If the dump cannot be
refreshed at run time, say so in the suite and do not declare the artifact,
because a check you cannot trust is a liability dressed as a control.

## What this does and does not do

It **records**, and recording is most of the value: the change is in the run
file, in the baseline you committed, and in the diff a reviewer reads.

It does **not gate**. A changed artifact is a fact, never an exit code —
`digline` exits non-zero on a regression, a moved canary, an unjudged case or a
lost scale, and an artifact is none of those. Artifacts are also deliberately
outside `config_hash`, so a rewritten description does not invalidate your
baseline or block a promotion. That is the right default for a prompt, where
changing the file *is* the experiment. Whether a tool definition wants the
opposite default — an opt-in assertion that fails when a declared SHA moves —
is an open question and not yet answered.

## Withholding it

Artifacts do not travel by default. `Disclosure(artifacts=True)` is what lets
them cross a boundary, and a redacted run withholds the **digest as well as the
text** — a digest is a verifier, and a tool list is not drawn from a large
space, so an attacker who can enumerate plausible variants can hash each
against a leaked digest and recover it. If your tool descriptions carry a
customer's vocabulary, leave the default alone: the count of files that moved
still travels, and what moved does not.
