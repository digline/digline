# digline for Claude Code

digline tells you what happened to your model's output. What it deliberately
does not encode is how to behave about it: whether a red run is a regression or
a wobble, which run deserves to become the reference, when to stop re-running
and start reading. That judgement is written down, in
[`AGENTS.md`](../../AGENTS.md) and in the `operating-digline` skill. Until this
plugin it reached nobody outside this repository.

This plugin is how it reaches you. It ships:

- **the `operating-digline` skill** — the judgement layer, loaded when the
  agent is about to run a suite, read a comparison, or decide which run should
  become the baseline;
- **the digline MCP server**, started on your project — it measures, reads and
  explains, and **cannot promote a baseline, because approval is a person's
  commit**. `promote` is not disabled there; it is absent, and there is no tool
  that could do it ([`docs/mcp.md`](../../docs/mcp.md));
- **a hook that asks you before `digline promote`** — see below for what it is
  and what it is not.

## Install: two lines plus one dependency

The server imports your suite and the provider packages it declares, so it has
to run in your project's environment. That dependency is yours to add; the
plugin cannot add it for you:

```sh
uv add --dev digline-mcp          # or pip install digline-mcp into the project's .venv
```

Then, from a terminal (or the same two as `/plugin marketplace add` and
`/plugin install` inside Claude Code):

```sh
claude plugin marketplace add digline/digline
claude plugin install digline@digline --scope project
```

`--scope project` records the plugin in `.claude/settings.json`, which you
commit: the plugin belongs to the repository that uses digline, like
everything else digline keeps. Installed at user scope it would start in every
repository you open.

The marketplace installs the plugin from the tag of the digline release it
describes, never from `main`, so the skill does not describe anything your
installed digline cannot do yet. Its version is digline's version.

## What the launcher needs

The server is started from `<project>/.venv/bin/digline-mcp` and from nowhere
else. Not from `PATH` and not from an activated environment, which can belong
to another project at another version. Not through `uv run` either, which in a
repository without the dependency writes a `uv.lock` and creates a `.venv`
before failing. The plugin starts with every session, so it must write nothing.

Without it, the server does not start, and Claude Code's MCP log carries one
line saying what to add. With it and no runs yet, the tools answer and say
there is nothing to read: `compare` says to run the suite first.

This means **a virtual environment at `.venv` in the project root**, which is
what `uv` and `python -m venv .venv` make. An environment elsewhere, such as
Poetry's default, is not found. The scripts are POSIX `sh`, so Windows is not
supported.

## The hook is a preference, not a wall

When a shell command runs `digline promote`, the hook stops and asks you. It
**asks**, and never refuses outright, because a person may tell the agent to
promote, and then the prompt is where that person approves.

It guarantees nothing. You, or anybody who can edit your settings, can disable
the plugin. A command spelled in a way the pattern does not read goes through.
It only makes the honest path the easy one. **The wall is the reviewed diff
under `.digline/<tenant>/baselines/`**: a baseline is committed, so it reaches
a reviewer as a change nobody can make silently. That is where approval lives,
with or without this plugin.

The skill says the same from the other side: never promote on your own
initiative, assemble the evidence, recommend, and let the human run the
command or tell you to.
