# digline

**Regression testing for LLM applications — with the baseline in your repository, not on someone's server.**

[![PyPI 0.1.0](https://img.shields.io/badge/pypi-0.1.0-blue)](https://pypi.org/project/digline/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Your prompt worked on Tuesday. On Thursday it works a little less — not enough
to break, enough for a user to notice in two weeks. No ordinary test catches it,
because there is no correct output to compare against, only a better or a worse
one.

digline gives you an **approved reference** — the baseline — and on every change
tells you whether you are below it: which case, which check, by how much. The
baseline is a JSON file in your repository, so it goes through code review and
it rolls back with `git`. No server, no account, no network call you have not
configured yourself.

```console
$ digline compare --suite suite.py --run latest
2 checks got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.

how-do-i-return · llm_rubric · Score fell from 1.000000 to 0.700000.
how-do-i-return · contains · Went from passing to failing (1.000000 → 0.000000).
```

## Why digline

Most evaluation tools tell you whether an output is below a threshold. digline
also tells you whether it is *worse than it was* — the drift from 0.91 to 0.78
that trips no threshold and is the first thing a user feels.

The suite is **Python, not YAML**: a judge is an object, a target is a function,
and what may leave a perimeter is declared in code — none of which a
configuration file expresses without reinventing a language. Built for teams
shipping LLM features for someone else, who have to show a customer what was
tested, when, under which commit, and who approved it.

## Quickstart

```bash
uv add digline        # or: pip install digline
```

`suite.py` — complete and runnable, no API key:

```python
"""suite.py — complete and runnable: no API key, nothing else to install."""

from digline.core import Contains, CostBudget, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Thursday. — Northwind Support",
    "how-do-i-return": "Any item, within 30 days, unused. — Northwind Support",
}


def judge(prompt: str) -> JudgeReply:
    """Your judge. digline composes `prompt` from the rubric, the question and
    the answer; it wants a score in [0, 1] and a reason back."""
    signed = "Northwind Support" in prompt
    concise = len(prompt.split()) <= 60
    return JudgeReply(
        score=0.4 + 0.3 * signed + 0.3 * concise,
        reason=f"signed={signed}, concise={concise}",
    )


def target(case: Case) -> Response:
    """Your application, called once per case. Canned here so this runs as is."""
    text = ANSWERS[case.id]
    return Response(output=text, cost_usd=0.004 + 0.001 * len(text) / 100)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        LlmRubric(
            rubric="Does the reply answer the question in at most three sentences?",
            judge=judge,
            threshold=0.7,
            tolerance=0.05,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
    ],
    cases=[Case(id="where-is-my-order"), Case(id="how-do-i-return")],
)
```

```console
$ digline run --suite suite.py
2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8

$ digline promote --suite suite.py --run latest
support baseline set to 2026-08-26T15-44-09-282929-00-00-e7421ec503ccefe8
```

Now change the prompt, the model, an answer — anything — and ask again:

```console
$ digline run --suite suite.py
2026-08-26T15-44-09-492722-00-00-e7421ec503ccefe8

$ digline compare --suite suite.py --run latest
2 checks got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.

how-do-i-return · llm_rubric · Score fell from 1.000000 to 0.700000.
how-do-i-return · contains · Went from passing to failing (1.000000 → 0.000000).

$ echo $?
1
```

The exit code is the answer: `0` fine, `1` got worse, `2` could not be judged.
Everything lands in `.digline/<tenant>/` — `baselines/` committed, `runs/`
git-ignored through a `.gitignore` digline writes for you.

## What it checks

**Per case** — pure functions `(inputs) -> Verdict`, no I/O, callable on their own:

| Assertion | Use it when |
|---|---|
| `Equals`, `Contains`, `NotContains`, `Affix`, `Regex` | the output must, or must not, contain something specific |
| `IsJson`, `JsonSchema` | the output is structured |
| `Length` | answers are growing, or must fit a channel |
| `Levenshtein` | "close enough" to `Case.expected`, graded rather than binary |
| `LlmRubric` | the criterion is a judgement — is it polite, does it stay on policy |
| `Faithfulness` | RAG: is the answer supported by the retrieved context |
| `FromAutoevals` | you already have an `autoevals` scorer and want it under a baseline |
| `PiiAbsent` | the output reaches a person — IBAN, codice fiscale, partita IVA, email, phone, checksum-verified where one exists |
| `CostBudget`, `LatencyBudget` | always. Graded, so a cost creeping up *within* budget is still visible |
| `Repeated` | the judge oscillates: grade the same output `n` times and fold the votes |

**Per run** — one verdict on the whole suite, the kind that goes in a contract:

| Aggregate | Use it when |
|---|---|
| `Precision` | false positives are what your users see |
| `Recall` | what is missed is what your users miss |
| `Accuracy`, `F1` | you need a single number for both |

Every assertion carries a **threshold that can fail** — there is no default that
passes vacuously, and `Contains("")` is a `ValueError` when the suite loads
rather than a green run — and a **tolerance** below which a difference from the
baseline is noise. Where a number is really "k out of n", write it as one:
`min_agreement="2/3"`, and a float no `k/n` can produce is refused at
construction.

One card each — parameters, typical values, what to watch out for — in
[`docs/metrics.md`](docs/metrics.md). Custom assertion? Subclass
`AssertionBase`, or `RunAssertionBase` for an aggregate: [`docs/api.md`](docs/api.md).

## How it thinks

- **The judge is yours.** digline never calls a model API: you inject a
  function, and in your tests you inject a deterministic one.
- **Three states, not two** — `pass`, `fail`, `error`. An error is neither green
  nor a regression: it means *could not judge*, and a run containing one cannot
  become the baseline.
- **Two kinds of noise, two answers.** `Suite.samples` asks the target more than
  once — the same input answered differently. `Repeated` grades the same output
  more than once — the judge changing its mind. `min_agreement` becomes
  mandatory as soon as you sample.
- **Set the threshold where the system measurably is**, not where you want it:
  the gate protects against getting worse, and raising the bar is a visible
  change in a pull request.
- **Promote the median of several runs**, not the first green one — `digline
  view` is the table you pick it from. Cases diagnose, aggregates gate.

Worked through with real numbers in [`docs/guide.md`](docs/guide.md); the
reasoning behind every fixed decision is in [`docs/adr/`](docs/adr/).

## Commands

| Command | |
|---|---|
| `digline run` | execute the suite, write the run, print its key |
| `digline compare` | headline plus the lines that got worse; `--json`, `--json full` for CI |
| `digline promote` | make a run the baseline — refused if the tenant differs, the configuration changed, or any check errored |
| `digline report` | self-contained HTML for readers who do not read code; `--locale` mandatory, `--redacted` keeps the verdicts and drops the payload |
| `digline list` | stored runs, newest first, baseline marked |
| `digline view` | local browser UI — [`docs/view.md`](docs/view.md) |
| `digline migrate` | bring stored runs forward across schema versions — [`docs/migrate.md`](docs/migrate.md) |

## What digline is not

- **Not an observability platform.** Dashboards over production traces are a
  served market. What is designed and not yet built is narrower: evaluating
  production responses inside *your* perimeter, and turning a failure into a
  committed test case.
- **Not a red-teaming tool.** digline generates no attacks. Once one is found,
  it becomes a `Case`, and the suite makes sure it never works again.
- **Not YAML.** Cases are data and may come from files; the suite is Python.

## Status

`0.1.0`, alpha. The offline cycle — write the suite, run, promote, compare,
report — is complete, covered by tests, and used daily on a real project. The
production store, the bridge from production failures back to committed cases,
and the reactive side are designed in
[ADR 0002](docs/adr/0002-three-worlds-and-where-the-data-lives.md) and not
written yet.

Python 3.12+. One runtime dependency: `jsonschema`.

## Docs

- [`docs/guide.md`](docs/guide.md) — how to reason with digline, in eight chapters
  and the order the problems arrive: baseline, judge noise, sampling, tolerance,
  threshold, which run to promote, what to gate on, what to maintain
- [`docs/metrics.md`](docs/metrics.md) — a card per assertion and aggregate: when
  to reach for it, what it produces, what it will do to you if you are not looking
- [`docs/api.md`](docs/api.md) — what is imported from where, every assertion
  and its parameters, custom assertions, and the complete example in
  [`examples/quickstart/`](examples/quickstart/), which a test runs on every build
- [`docs/view.md`](docs/view.md) · [`docs/migrate.md`](docs/migrate.md) — the two commands with a surface of their own
- [`docs/adr/`](docs/adr/) — the architectural decisions, numbered, with the reasoning

## License

Apache-2.0.
