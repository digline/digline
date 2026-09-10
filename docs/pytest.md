# `pytest-digline` — the comparison as rows in pytest

digline's gate is an exit code: `digline run` writes a run, `digline compare`
holds it against the committed baseline, and the process exits `0`, `1` or `2`.
That is the primary route and nothing here replaces it.

This package is for the repository that already has a `tests/` directory, a CI
job that says `pytest -q`, and a developer whose muscle memory is
`pytest -k thing --lf`. It puts the comparison in that report, one row per
check.

```sh
pip install pytest-digline
pytest --digline-suite eval/suite.py
```

```console
$ pytest --digline-suite eval/suite.py -v
digline: comparing 1 suite(s) against the committed baseline

eval/suite.py::alpha::contains       PASSED
eval/suite.py::alpha::llm_rubric     FAILED
eval/suite.py::beta::contains        PASSED
eval/suite.py::beta::llm_rubric      PASSED
eval/suite.py::gamma                 SKIPPED (the refund API is down, ticket 412)

=================================== FAILURES ===================================
digline: alpha · llm_rubric
  Dropped from 1.000000 to 0.000000, below its threshold of 0.700000.
  reason: looked

==================================== digline ===================================
1 check got worse compared with the reference. Every case could be judged.
1 case is suspended. The suite is unchanged from the reference.
```

The reasoning is in [ADR 0013](adr/0013-the-pytest-plugin.md).

## One row per check

A row is **one assertion on one case**, because that is digline's unit of
verdict: `compare` counts checks, the report lists checks, and one case can hold
a regression and an error at once. A row per *case* would have to fold those
together and pick one to show.

Run-scope verdicts — precision, recall, the per-group aggregates — are rows too,
named `<run>::precision`, because they belong to no case.

`-k` and `--last-failed` select them like any other test.

## The four states

| digline | pytest | |
|---|---|---|
| fine | `PASSED` | |
| got worse | `FAILED` | a statement about behaviour that got worse |
| could not be judged | `ERROR` | an error is neither green nor a regression ([ADR 0001](adr/0001-verdict-not-score.md)) |
| suspended | `SKIPPED` | a decision somebody made, not an outcome — with the reason the suite declared |

The last one is the reason this bridge is worth crossing. A suspension never
fails, so on the exit-code route it disappears into `0`: the run is smaller than
the suite and nothing in the number says so. pytest has had a state for *a
decision rather than an outcome* since it was written.

### What pytest cannot carry

**The process exit code.** `digline compare` exits `1` for a regression and `2`
for a run it could not judge; a pytest run exits `1` for either — that is
pytest's own behaviour and not something a plugin can change.

The distinction survives where you can act on it: `F` and `E` are counted
separately, `-rE` lists the errored rows on their own, and `--junit-xml` keeps
them apart. A job that needs `1` versus `2` runs `digline compare`, which is one
command away.

One counting note: the headline sentence counts unjudged **cases**, while the
rows are **checks**. A case with two errored checks reads as "1 case could not
be judged" beside two `E`s. Both are right.

## What a pytest run costs

**Nothing, by default.** The plugin compares the latest stored run against the
committed baseline: two documents read off disk and a pure function. No provider
is called. pytest is a command people run on a keystroke, and a gate that
charged for it would be a gate people switch off.

Producing the run is a separate act — `digline run`, the
[official image](https://digline.dev/product/docker/), a CI job.

`--digline-run` runs each suite first:

```sh
pytest --digline-suite eval/suite.py --digline-run
```

It calls your provider and spends money, so it is a flag on the command line
where the cost is visible in the log; it prints the planned call count on stderr
before the first call (`20 cases × 5 samples = 100 calls to the target`); and it
**refuses under `--collect-only`**, because a command whose job is to list test
names must never be able to spend a hundred model calls.

## Naming a suite

Nothing is discovered by convention. A suite is a file that *executes*, and
pytest walks directories nobody enumerated — a file found by convention is a
file that runs by accident.

```sh
pytest --digline-suite eval/suite.py --digline-suite eval/billing.toml
```

or, so that a bare `pytest` gates:

```toml
[tool.pytest.ini_options]
digline_suites = ["eval/suite.py"]
```

The command line **replaces** the ini list rather than adding to it, so
narrowing a run to one suite is expressible. `--digline-root` names the
perimeter holding `.digline/` and defaults to pytest's rootdir.

Select rows with `-k`. A node id passed as a positional argument is not
supported: these rows are added to the session rather than collected from a path,
which is what keeps pytest from importing your suite a second time.

## What it will not do

**It does not promote.** There is no flag, no fixture and no marker that makes a
run the new baseline. Not refused — *absent*, and a test in the package sweeps
its own sources to keep it that way. A baseline is an approved reference and the
approval is a person's; a green pytest run is the likeliest place for a
promotion to happen by accident, because "the tests pass" is a sentence people
act on without reading. The same construction as
[the MCP server's](adr/0011-the-mcp-server.md) missing `promote`, for the same
reason: a refusal is a conversation, an absence is not.

**It has no thresholds of its own.** Every bar it reports against was declared
in your suite and frozen in the baseline somebody promoted and committed. This
is the difference from tools whose thresholds live in the test file: there, the
test file is the reference and it moves when somebody edits it.

**It has no locale.** pytest's report is a terminal, and terminal output is
English here like every other terminal output. For the document with a
recipient, `digline report --locale` is one command away.

**It depends on digline and pytest, and nothing else.**

## Turning it off

`pytest -p no:digline` for one run. With no suite named it collects nothing,
prints nothing and adds no header line — installing it changes nothing about a
repository that has not asked for it.

## In CI

```yaml
- run: pip install digline pytest-digline
- run: digline run --suite eval/suite.py      # the calls happen here, once
- run: pytest --digline-suite eval/suite.py   # the gate, free and offline
```

Two steps rather than `--digline-run`, on purpose: the spend is one line in the
log with its own duration and its own failure, and the gate re-runs without
re-spending.
