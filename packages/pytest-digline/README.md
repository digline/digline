# pytest-digline

The digline comparison, as rows in pytest's own report.

```sh
pip install pytest-digline
pytest --digline-suite eval/suite.py
```

```
digline: comparing 1 suite(s) against the committed baseline

eval/suite.py::alpha::contains          .
eval/suite.py::alpha::llm_rubric        F
eval/suite.py::beta::contains           .
eval/suite.py::gamma                    s

=================================== FAILURES ===================================
digline: alpha · llm_rubric
  dropped from 0.910000 to 0.640000, below its threshold of 0.700000,
  and beyond the 0.880000–0.950000 this check measured across 5 samples
  reason: signed=True, concise=False

==================================== digline ===================================
1 check got worse; every case could be judged; 1 case is suspended; the rules
are unchanged.
```

One row per **check** — one assertion on one case — because that is digline's
unit of verdict. `-k` and `--last-failed` select them like any other test.

## What it does, and what it costs

By default it **compares and never runs**: it reads the latest stored run of
each suite, holds it against the baseline committed in your repository, and
makes no network call at all. Producing a run stays a separate act —
`digline run`, the official image, the GitHub Action.

`--digline-run` runs each suite first. That calls your provider and spends
money, so it is a flag on the command line where the cost is visible, it prints
the planned call count before the first call, and it **refuses under
`--collect-only`**: a command whose job is to list test names must never be able
to spend a hundred model calls.

## The four states

| digline | pytest |
|---|---|
| fine | passed |
| got worse | **FAILED** |
| could not be judged | **ERROR** — an error is neither green nor a regression |
| suspended | **SKIPPED**, with the reason the suite declared |

The suspension is the one digline state an exit code cannot express: it never
fails, so it disappears into `0`. pytest has had a state for *a decision rather
than an outcome* since it was written, and this is it.

**What pytest cannot carry**: the process exit code. `digline compare` exits `1`
for a regression and `2` for a run it could not judge; a pytest run exits `1`
for either. The distinction survives in the report — `F` and `E` are counted
separately, `-rE` lists the errored rows — and in `--junit-xml`. A job that
needs `1` versus `2` runs `digline compare`, which is one command away.

## Naming a suite

Nothing is discovered by convention: a suite is a file that *executes*, and a
file found by convention is a file that runs by accident. Name it, either way:

```sh
pytest --digline-suite eval/suite.py --digline-suite eval/billing.toml
```

```ini
# pyproject.toml
[tool.pytest.ini_options]
digline_suites = ["eval/suite.py"]
```

The command line replaces the ini list rather than adding to it, so narrowing a
run to one suite is expressible. `--digline-root` names the perimeter holding
`.digline/` and defaults to pytest's rootdir.

Select rows with `-k`; a node id passed as an argument is not supported.

## What it will not do

**It does not promote.** There is no flag, no fixture and no marker that makes
a run the new baseline — not refused, *absent*, and a test in this package
sweeps the sources to keep it that way. A baseline is an approved reference;
the approval is a person's, and a green pytest run is the single most likely
place for a promotion to happen by accident.

**It has no thresholds of its own.** Every bar it reports against was declared
in your suite and frozen in the baseline somebody promoted and committed.

**It depends on digline and pytest, and nothing else.**

Turn it off for one run with `-p no:digline`. With no suite named it collects
nothing, prints nothing and adds no header.

The reasoning is [ADR 0013](https://digline.dev/product/adr/0013-the-pytest-plugin/).
