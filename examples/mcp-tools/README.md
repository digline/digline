# My agent uses an MCP server I don't control: how do I know its tool descriptions haven't changed?

A tool description is not documentation. It is text placed in the model's
context that decides **when the model calls the tool** — so it is
configuration, and an upgrade can rewrite it without touching a single tool
name, a single schema, or anything a version pin or a name-based check would
notice.

That this happens is measured, and the measurement is not ours.
[EvalSeal](https://github.com/maurathat/evalseal) read 10 published MCP server
packages across 79 installed versions and 63 consecutive version pairs, and
found **51 tool descriptions rewritten with the tool name unchanged**, a net
**+2,401 characters** of model-facing instruction. Of 38 material changes, 20
kept the names identical. One release added a conditional clause telling the
model when *not* to call the tool.

This example is that last case, made small enough to run in a second.

## What is here

- `server.py` — the MCP server under test, standing in for one you did not
  write. `CAUTIOUS` is the switch: both settings offer the same two tools under
  the same names with the same schemas, and differ only in the wording of one
  description.
- `dump_tools.py` — writes `tools.json` **canonically**. This is the part that
  decides whether the whole recipe works; read its docstring.
- `app.py` — the agent, a stand-in that reads the descriptions and decides.
- `suite.py` — declares `tools.json` as an artifact *and* asserts the behaviour
  those definitions produce. Neither is enough alone.

## Run it

```
uv sync
uv run python dump_tools.py
KEY=$(uv run digline run --suite suite.py)
uv run digline compare --suite suite.py --run "$KEY"
```

Green, against the committed baseline. Now change one description and nothing
else — set `CAUTIOUS = True` in `server.py` — then re-dump and run again:

```
uv run python dump_tools.py
KEY=$(uv run digline run --suite suite.py)
uv run digline compare --suite suite.py --run "$KEY"
```

```
2 checks got worse compared with the reference. ... 1 file under test changed
since the reference.

  tools.json · +1 −1 lines

no-id · contains · Went from passing to failing (1.000000 → 0.000000).
no-id · tools_called · Went from passing to failing (1.000000 → 0.000000).
```

The file that changed is named above the scores that moved, which is the whole
point: without the artifact you would see two checks go red and have nothing in
the document saying why.

## The two things to copy

**Dump canonically.** Tools sorted by name, `sort_keys=True`, `indent=2`. A
server may return its tools in any order, a JSON object has no order, and the
report's diff is line-oriented. Skip any of the three and the SHA moves on
every run, the report says so every time, and within a week you have trained
yourself to scroll past the one line that was meant to be the alarm.

Note the asymmetry while you are here, so you do not read it as a bug: digline
canonicalises tool-call *arguments* inside `ToolCalledWith`, and does **not**
canonicalise artifacts — it hashes the bytes on disk, because an artifact is
any file a suite declares and a hash that reformatted its subject would be
hashing something other than the file under test. The normalising is yours, on
the way in.

**Re-dump in the same step that runs the suite.** digline never fetches
`tools/list`; it reads a file off disk. A dump that stopped running leaves a
stale SHA that `compare` reports as *unchanged* — true of the file, false of
your server, and worse than no check at all, because it reads as a
verification that happened. `.github/workflows/check.yml` here puts the dump
immediately before the run for that reason.

## What this does not do

It records; it does not gate. A changed artifact is a fact, never an exit code,
and artifacts are deliberately outside `config_hash` so a rewritten description
does not invalidate your baseline. What turns this red is the *behaviour*
assertions above — which is why the suite has both.

The full recipe, including withholding, is in `docs/tools.md`.
