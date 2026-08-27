# Working with digline

Eight chapters in the order the problems actually arrive. Every file on this
page is a file you can run, every terminal block came out of running them, and a
test replays the whole sequence top to bottom on every build — so if the page
and the tool ever disagree, the build is what breaks.

1. [A baseline is a photograph](#1-a-baseline-is-a-photograph)
2. [The judge's noise: one run, two runs](#2-the-judges-noise-one-run-two-runs)
3. [Sampling, and fractions](#3-sampling-and-fractions)
4. [Measuring the tolerance, and when a check is not a gate](#4-measuring-the-tolerance-and-when-a-check-is-not-a-gate)
5. [The threshold goes where the system is](#5-the-threshold-goes-where-the-system-is)
6. [Promote the median, not the first green run](#6-promote-the-median-not-the-first-green-run)
7. [The aggregate gates, the cases diagnose](#7-the-aggregate-gates-the-cases-diagnose)
8. [Keeping it alive: five triggers](#8-keeping-it-alive-five-triggers)

Three files to start. They live in one directory and nothing else is needed.

```python
# app.py
"""The system under test, and the judge. Both would be yours."""

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Thursday. — Northwind Support",
    "how-do-i-return": "Any item, within 30 days, unused. — Northwind Support",
    "is-it-waterproof": "Rated IPX4: splashes yes, swimming no. — Northwind Support",
}


def reply(question_id: str) -> tuple[str, float]:
    """Your model call. Canned, so this page needs no key."""
    text = ANSWERS[question_id]
    return text, 0.004 + 0.001 * len(text) / 100


def judge(prompt: str) -> float:
    """Your judge model. Steady, for now."""
    return 1.0 if "Northwind Support" in prompt else 0.4
```

```python
# rules.py
"""The calibrated numbers, in one place so a change is one line in a diff."""

THRESHOLD = 0.7
TOLERANCE = 0.05
```

```python
# support.py
"""The suite: who, where, what is checked, on what."""

import app
import rules
from digline.core import Contains, CostBudget, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=app.judge(prompt), reason="judged")


def target(case: Case) -> Response:
    text, cost = app.reply(case.id)
    return Response(output=text, cost_usd=cost)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        LlmRubric(
            rubric="Does the reply answer the question?",
            judge=judge,
            threshold=rules.THRESHOLD,
            tolerance=rules.TOLERANCE,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
    ],
    cases=[
        Case(id="where-is-my-order"),
        Case(id="how-do-i-return"),
        Case(id="is-it-waterproof"),
    ],
)
```

## 1. A baseline is a photograph

Run the suite, then declare that this is what "working" looks like.

```console
$ digline run --suite support.py
2026-08-26T16-06-38-334462-00-00-282b0c02d6511fb4

$ digline promote --suite support.py --run latest
support baseline set to 2026-08-26T16-06-38-334462-00-00-282b0c02d6511fb4

$ digline compare --suite support.py --run latest
Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.
```

`promote` wrote `.digline/northwind/baselines/support.json`. Commit it. From now
on every comparison is against that file, it is reviewed like any other change,
and `git revert` puts the old reference back.

A photograph, not a target: it records where the system **was**, measured, not
where you would like it to be. Everything below is about taking the photograph
at a moment worth keeping.

## 2. The judge's noise: one run, two runs

Nothing about the system has changed. Only the judge is now the one you actually
have — a model that does not vote the same way twice.

```python
# app.py
"""The system under test, and the judge. Both would be yours."""

import random
from pathlib import Path

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Thursday. — Northwind Support",
    "how-do-i-return": "Any item, within 30 days, unused. — Northwind Support",
    "is-it-waterproof": "Rated IPX4: splashes yes, swimming no. — Northwind Support",
}


def reply(question_id: str) -> tuple[str, float]:
    """Your model call. Canned, so this page needs no key."""
    text = ANSWERS[question_id]
    return text, 0.004 + 0.001 * len(text) / 100


def judge(prompt: str) -> float:
    """Your judge model — now with the mind it actually has.

    Reproducible on purpose: the vote depends on how many judgements have been
    asked for, never on the clock, so the numbers on this page are the numbers
    you will get. A real judge needs no such help to disagree with itself.
    """
    counter = Path("votes.txt")
    asked = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(asked + 1))
    if "Northwind Support" not in prompt:
        return 0.4
    return 0.6 if random.Random(asked).random() < 0.25 else 1.0
```

Run it twice. Same code, same cases, same baseline.

```console
$ digline run --suite support.py
2026-08-26T16-06-38-571702-00-00-282b0c02d6511fb4

$ digline compare --suite support.py --run latest
1 check got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.

how-do-i-return · llm_rubric · Went from passing to failing (1.000000 → 0.600000).

$ digline run --suite support.py
2026-08-26T16-06-38-761306-00-00-282b0c02d6511fb4

$ digline compare --suite support.py --run latest
2 checks got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.

how-do-i-return · llm_rubric · Went from passing to failing (1.000000 → 0.600000).
where-is-my-order · llm_rubric · Went from passing to failing (1.000000 → 0.600000).
```

Two red builds, on different cases, from a system nobody touched. A pipeline
wired to this exits `1` at random, and a pipeline that is red at random is a
pipeline everyone learns to ignore — which is worse than not having one, because
the day it is right nobody looks.

Everything in the next three chapters exists to turn that into a number.

### A word about the judge on this page

The judge above is a fake, and every fake carries the same trap: **one written
by reading the code confirms the code.** It returns what the code expects
because that is where it came from, so the tests it satisfies are a mirror, and
a field the code never reads is a field the fake never has.

That is not a hypothetical. digline's own Anthropic target was tested against a
fake whose `usage` carried `input_tokens`, `output_tokens` and
`cache_read_input_tokens` — the three the code read. The real API also returns
`cache_creation_input_tokens`, and the tokens written into a cache are **not**
part of `input_tokens`: a call that cached a 9202-token prompt reports
`input_tokens=10`. The target priced that call at `$0.00003` instead of
`$0.011532`, a factor of **384**, in the direction of "it costs almost nothing".
Every test was green, because the fake had exactly the same hole.

So a fake is built **from a real response, once per SDK**, not from the code it
will be used to test. Print the whole object — every field, including the ones
you have no use for — and shape the fake from that. What you do not print is
what the fake will not have, and therefore what your tests will never see.

`DIGLINE_LIVE=1` is how you go and look:

```text
# The default run never reaches a provider. Both gates, deliberately:
#   ANTHROPIC_API_KEY  — you have one
#   DIGLINE_LIVE=1     — you meant it today
$ DIGLINE_LIVE=1 pytest -m live
```

Do it when you adopt an SDK, and again when the provider ships a version. One
call, once, is cheaper than a cost report that has been wrong since March.

## 3. Sampling, and fractions

One judgement is a sample of size one. Ask three times and keep what the
majority says.

Agreement is a **count**, `k` out of `n`, and writing it as a decimal is how you
get the opposite of what you meant:

```python
# unreachable.py
"""An agreement written as a decimal, and what digline says about it."""

from digline.core import JudgeReply, LlmRubric, Repeated

rubric = LlmRubric(
    rubric="Does the reply answer the question?",
    judge=lambda prompt: JudgeReply(score=1.0, reason="stub"),
    threshold=0.7,
    tolerance=0.05,
)

try:
    Repeated(inner=rubric, samples=3, min_agreement=0.67)
except ValueError as exc:
    print(exc)
```

```console
$ python unreachable.py
Repeated.min_agreement is 0.670000, which 3 samples cannot produce: agreement is a count of samples, so it is one of 1/3 = 0.333333, 2/3 = 0.666667, 3/3 = 1.000000. Write the fraction if that is what you mean, e.g. "2/3".
```

`2/3` is `0.666…`, so `0.67` is *above* it: every case with two votes out of
three would have errored, silently, for the opposite of the intended reason.
digline refuses the value at construction rather than letting it run.

So write the fraction.

```python
# rules.py
"""The calibrated numbers, in one place so a change is one line in a diff."""

THRESHOLD = 0.7
TOLERANCE = 0.05
SAMPLES = 3
AGREEMENT = "2/3"
```

```python
# support.py
"""The suite: who, where, what is checked, on what."""

import app
import rules
from digline.core import Contains, CostBudget, JudgeReply, LlmRubric, Repeated
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=app.judge(prompt), reason="judged")


def target(case: Case) -> Response:
    text, cost = app.reply(case.id)
    return Response(output=text, cost_usd=cost)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        Repeated(
            inner=LlmRubric(
                rubric="Does the reply answer the question?",
                judge=judge,
                threshold=rules.THRESHOLD,
                tolerance=rules.TOLERANCE,
            ),
            samples=rules.SAMPLES,
            min_agreement=rules.AGREEMENT,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
    ],
    cases=[
        Case(id="where-is-my-order"),
        Case(id="how-do-i-return"),
        Case(id="is-it-waterproof"),
    ],
)
```

`Repeated` grades the **same output** several times: that is judge noise.
`Suite(samples=…)` asks the **target** several times: that is system noise. Two
different questions, and mixing them up measures neither.

```console
$ digline run --suite support.py
2026-08-26T16-06-48-447223-00-00-ec1ed2cb8ce70c26

$ digline compare --suite support.py --run latest
Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The configuration changed since the reference, so these numbers compare different rules.

$ digline promote --suite support.py --run latest
support baseline set to 2026-08-26T16-06-48-447223-00-00-ec1ed2cb8ce70c26
```

Note the last sentence of the headline. Sampling is part of the configuration,
so the old baseline no longer describes the rules in force and has to be
re-taken. That is trigger one of chapter 8, arriving early.

## 4. Measuring the tolerance, and when a check is not a gate

The tolerance is the difference small enough to be noise. It is **measured**,
never chosen, and measuring it means running the untouched system many times.

```python
# calibrate.py
"""Run the suite N times and keep every run: the measurement, not the gate.

Two things worth copying. `execute` is handed `created_at` rather than reading
the clock — the engine is pure, and the clock belongs to the caller. And the
suite is loaded the way `digline` loads it, never with a plain `import`: a
same-size edit inside the same second is exactly what a stale `.pyc` hides, and
what it would hide here is the change you are trying to measure.
"""

import sys
from datetime import UTC, datetime

from digline.cli.loader import load_suite, load_target
from digline.run import execute
from digline.store import FileResultStore

suite, module = load_suite("support.py")
target = load_target(None, module, "support.py")

times = int(sys.argv[1]) if len(sys.argv) > 1 else 8
store = FileResultStore(".")
for _ in range(times):
    store.write_run(execute(suite, target, created_at=datetime.now(UTC).isoformat()))
print(f"{times} runs recorded")
```

```python
# spread.py
"""How much each check moves when nothing changes.

Reads the stored runs through the store the CLI uses: digline is a library
before it is a command, and the run files are yours.

Only runs produced under the configuration in force are counted. Mixing in runs
judged by other rules would measure the rules, not the system.
"""

import statistics

from digline.cli.loader import load_suite
from digline.store import FileResultStore

suite, _module = load_suite("support.py")
store = FileResultStore(".")
runs = [
    run
    for ref in store.scan_runs(suite.tenant, suite.name).runs
    if (run := store.read_run(ref)).config_hash == suite.config_hash()
]

seen: dict[tuple[str, str], list[float]] = {}
for run in runs:
    for case in run.results:
        for verdict in case.verdicts:
            if verdict.score.score is not None:
                seen.setdefault((case.case_id, verdict.score.name), []).append(
                    verdict.score.score
                )

print(f"{len(runs)} runs under the configuration in force\n")
print(f"{'case':<18} {'check':<12} {'low':>6} {'median':>7} {'high':>6} {'spread':>7}")
for (case_id, check), v in sorted(seen.items()):
    print(
        f"{case_id:<18} {check:<12} {min(v):6.3f} {statistics.median(v):7.3f} "
        f"{max(v):6.3f} {max(v) - min(v):7.3f}"
    )
```

```console
$ python calibrate.py 8
8 runs recorded

$ python spread.py
9 runs under the configuration in force

case               check           low  median   high  spread
how-do-i-return    contains      1.000   1.000  1.000   0.000
how-do-i-return    cost_budget   0.815   0.815  0.815   0.000
how-do-i-return    llm_rubric    0.867   0.867  1.000   0.133
is-it-waterproof   contains      1.000   1.000  1.000   0.000
is-it-waterproof   cost_budget   0.814   0.814  0.814   0.000
is-it-waterproof   llm_rubric    0.733   0.867  1.000   0.267
where-is-my-order  contains      1.000   1.000  1.000   0.000
where-is-my-order  cost_budget   0.818   0.818  0.818   0.000
where-is-my-order  llm_rubric    0.867   1.000  1.000   0.133
```

Read it a column at a time. `contains` and `cost_budget` do not move at all: a
tolerance of zero is right for them, and any change they report is a real one.
`llm_rubric` moves by up to `0.267` on a system nobody touched.

The reflex is to widen the tolerance until the noise fits inside it. Try the
other lever first — more votes:

```python
# rules.py
"""The calibrated numbers, in one place so a change is one line in a diff."""

THRESHOLD = 0.7
TOLERANCE = 0.05
SAMPLES = 5
AGREEMENT = "3/5"
```

```console
$ python calibrate.py 8
8 runs recorded

$ python spread.py
8 runs under the configuration in force

case               check           low  median   high  spread
how-do-i-return    contains      1.000   1.000  1.000   0.000
how-do-i-return    cost_budget   0.815   0.815  0.815   0.000
how-do-i-return    llm_rubric    0.760   0.920  1.000   0.240
is-it-waterproof   contains      1.000   1.000  1.000   0.000
is-it-waterproof   cost_budget   0.814   0.814  0.814   0.000
is-it-waterproof   llm_rubric    0.840   0.920  0.920   0.080
where-is-my-order  contains      1.000   1.000  1.000   0.000
where-is-my-order  cost_budget   0.818   0.818  0.818   0.000
where-is-my-order  llm_rubric    0.680   0.920  1.000   0.320
```

Five votes did not fix it. One case tightened to `0.080`; another got worse, and
the widest spread is now `0.320` — on a score that only ever lives between `0.6`
and `1.0`.

That is the answer, and it is not a tolerance. **A tolerance wide enough to
absorb `0.320` would absorb every regression worth catching**, which is a gate
that is green by construction — fixed decision 3 says a check that cannot fail
is a bug, and one whose tolerance swallows everything is exactly that.

So the rule, in order:

1. measure the spread over enough runs that the widest one has shown up;
2. if the spread is small, set the tolerance just above it and you have a gate;
3. if it is not, **stop trying to make it one.** Stabilise the check — more
   votes, a tighter rubric, a stronger judge — and measure again. If it still
   will not sit still, keep it as a diagnosis and gate on something steadier.

Chapter 7 is what "something steadier" turns out to be.

## 5. The threshold goes where the system is

The tolerance is about movement. The threshold is about level, and it is decided
the same way: by looking.

```python
# rules.py
"""The calibrated numbers, in one place so a change is one line in a diff."""

THRESHOLD = 0.9
TOLERANCE = 0.10
SAMPLES = 5
AGREEMENT = "3/5"
```

```python
# standing.py
"""Where the system stands against the bar, in the latest run.

The score is a fact about the system; the threshold is a decision about it.
Printing them side by side is the only honest way to choose the second.
"""

from digline.cli.loader import load_suite
from digline.store import FileResultStore

suite, _module = load_suite("support.py")
store = FileResultStore(".")
latest = store.read_run(store.scan_runs(suite.tenant, suite.name).runs[-1])

for case in latest.results:
    for verdict in case.verdicts:
        if verdict.score.name == "llm_rubric" and verdict.score.score is not None:
            print(
                f"{case.case_id:<18} {verdict.score.score:.3f}  "
                f"{verdict.status:<4}  bar {verdict.threshold:.3f}"
            )
```

```console
$ digline run --suite support.py
2026-08-26T16-08-15-827300-00-00-5713087464da4dee

$ python standing.py
where-is-my-order  1.000  pass  bar 0.900
how-do-i-return    0.840  fail  bar 0.900
is-it-waterproof   0.920  pass  bar 0.900
```

`0.9` was a wish. Nothing is broken, and a third of the suite is red — and it
will be a *different* third tomorrow, which is chapter 2 all over again.

The measurement from chapter 4 says where this system actually lives: across the
eight runs at five votes the lowest score seen was `0.680`. So the bar goes
below it.

```python
# rules.py
"""The calibrated numbers, in one place so a change is one line in a diff."""

THRESHOLD = 0.65
TOLERANCE = 0.10
SAMPLES = 5
AGREEMENT = "3/5"
```

```console
$ digline run --suite support.py
2026-08-26T16-08-15-998299-00-00-2ba590fc617bbd5a

$ python standing.py
where-is-my-order  0.920  pass  bar 0.650
how-do-i-return    1.000  pass  bar 0.650
is-it-waterproof   1.000  pass  bar 0.650

$ digline promote --suite support.py --run latest
support baseline set to 2026-08-26T16-08-15-998299-00-00-2ba590fc617bbd5a
```

A threshold set where you wish you were makes the gate red by construction, so
it gets ignored, so it protects nothing. The threshold says "not below here";
the baseline says "not worse than this". You get better by improving the system
and *then* raising the bar — which is a change to the configuration, visible in
`config_hash` and in a pull request.

## 6. Promote the median, not the first green run

A baseline freezes one run. Freeze the wrong one and you freeze its luck with
its merit: a case recorded at `0.667` where three runs out of three say `1.000`
becomes a red line nobody can explain a fortnight later.

```console
$ python calibrate.py 5
5 runs recorded
```

```python
# median.py
"""The most typical run, which is the one to promote.

The first green run is the wrong one. It is green partly on merit and partly on
luck, and a baseline freezes the luck along with the merit: one unlucky case
recorded at 0.667 where three runs out of three say 1.000 becomes a red line
nobody can explain a fortnight later.

So: take the median score *per case*, then keep the run closest to that profile.
With `--key` it prints the key and nothing else, so a shell can hand it straight
to `digline promote`.
"""

import statistics
import sys

from digline.cli.loader import load_suite
from digline.store import FileResultStore

suite, _module = load_suite("support.py")
store = FileResultStore(".")
profiles = {
    ref.key: {
        case.case_id: verdict.score.score
        for case in run.results
        for verdict in case.verdicts
        if verdict.score.name == "llm_rubric" and verdict.score.score is not None
    }
    for ref in store.scan_runs(suite.tenant, suite.name).runs
    if (run := store.read_run(ref)).config_hash == suite.config_hash()
}

typical = {
    case_id: statistics.median(p[case_id] for p in profiles.values())
    for case_id in next(iter(profiles.values()))
}
ranked = sorted(
    (sum(abs(scores[c] - typical[c]) for c in typical), key)
    for key, scores in profiles.items()
)

if "--key" in sys.argv:
    print(ranked[0][1])
else:
    print(
        "typical run: " + "  ".join(f"{c} {v:.3f}" for c, v in sorted(typical.items()))
    )
    print()
    for distance, key in ranked[:5]:
        mark = "  <- promote this one" if key == ranked[0][1] else ""
        print(f"off by {distance:.3f}  {key}{mark}")
```

```console
$ python median.py
typical run: how-do-i-return 0.880  is-it-waterproof 0.960  where-is-my-order 0.920

off by 0.080  2026-08-26T16-08-16-214505-00-00-2ba590fc617bbd5a  <- promote this one
off by 0.080  2026-08-26T16-08-16-216801-00-00-2ba590fc617bbd5a
off by 0.160  2026-08-26T16-08-15-998299-00-00-2ba590fc617bbd5a
off by 0.160  2026-08-26T16-08-16-218356-00-00-2ba590fc617bbd5a
off by 0.240  2026-08-26T16-08-16-219738-00-00-2ba590fc617bbd5a

$ digline promote --suite support.py --run $(python median.py --key)
support baseline set to 2026-08-26T16-08-16-214505-00-00-2ba590fc617bbd5a
```

The bottom run is `0.240` away from typical. It was as green as the others and
it is the one you must not keep. Note also the third line: the run promoted in
chapter 5 — perfectly good, chosen because it happened to be there — is `0.160`
off. Choosing the median cost one command.

## 7. The aggregate gates, the cases diagnose

Chapter 4 ended with a check too noisy to gate on. This is the answer: when you
have ground truth, ask the question about the **run** instead of about the case.

```python
# triage.py
"""A second suite, with ground truth: is a ticket one to escalate?

Every case carries the human `label`. The per-case check asks whether the
system agreed with it; the aggregate turns those agreements into the one number
a release is decided on.
"""

from pathlib import Path

from digline.core import Contains, Precision
from digline.run import Case, Response, Suite

POSITIVE = ["refund-dispute", "service-outage", "suspected-fraud", "legal-threat"]
NEGATIVE = ["thanks-only", "duplicate-ticket"]

#: How many runs are already stored. Read, never written: importing a suite
#: must not change what the next run does.
RUN = len(list(Path(".digline/northwind/runs/triage").glob("*.json")))

#: One positive and one negative are misjudged every run — always the same
#: count, never the same pair. That is what judge wobble looks like from above.
WRONG = {POSITIVE[RUN % len(POSITIVE)], NEGATIVE[RUN % len(NEGATIVE)]}


def target(case: Case) -> Response:
    return Response(output="MISS" if case.id in WRONG else "MATCH", cost_usd=0.001)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="triage",
    assertions=[Contains(needle="MATCH", name="agrees_with_mark")],
    run_assertions=[
        Precision(over="agrees_with_mark", threshold="1/2", tolerance="1/6")
    ],
    cases=[
        *(Case(id=case_id, label="positive") for case_id in POSITIVE),
        *(Case(id=case_id, label="negative") for case_id in NEGATIVE),
    ],
)
```

`over` names the per-case check whose verdicts get counted, and from there the
matrix: positive + pass is a true positive, negative + fail is a false positive,
and `Precision` is `TP / (TP + FP)`. Every case needs a `label` the moment an
aggregate counts one, and `Suite` refuses to load without them.

```console
$ digline run --suite triage.py
2026-08-26T16-09-07-912456-00-00-9e780e13e9fa4f58

$ digline promote --suite triage.py --run latest
triage baseline set to 2026-08-26T16-09-07-912456-00-00-9e780e13e9fa4f58

$ digline run --suite triage.py
2026-08-26T16-09-08-076855-00-00-9e780e13e9fa4f58

$ digline compare --suite triage.py --run latest
2 checks got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.

duplicate-ticket · agrees_with_mark · Went from passing to failing (1.000000 → 0.000000).
service-outage · agrees_with_mark · Went from passing to failing (1.000000 → 0.000000).
```

Two regressions, and the system is exactly as good as it was: the same number of
tickets is misjudged, a different two of them. Ask the narrower question and the
answer is different.

```python
# gate.py
"""Red only when a verdict about the *run* got worse.

`compare` is a pure function in the core, so a pipeline can ask it the narrower
question directly: per-case verdicts move with judge noise, the aggregate does
not. The cases are for the person who then goes looking.
"""

import sys

from digline.cli.loader import load_suite
from digline.core import compare
from digline.store import FileResultStore

suite, _module = load_suite("triage.py")
store = FileResultStore(".")
latest = store.read_run(store.scan_runs(suite.tenant, suite.name).runs[-1])
baseline = store.read_baseline(suite.tenant, suite.name)
assert baseline is not None, "promote a run first"

result = compare(latest, baseline)
by_scope = {"run": [], "case": []}
for delta in result.deltas:
    if delta.outcome == "regressed":
        by_scope[delta.scope].append(delta)

for delta in by_scope["run"]:
    print(f"gate: {delta.assertion} {delta.before:.3f} -> {delta.after:.3f}")
print(
    f"{len(by_scope['run'])} run-level regressions, {len(by_scope['case'])} case-level"
)
sys.exit(1 if by_scope["run"] else 0)
```

```console
$ python gate.py
0 run-level regressions, 2 case-level
```

This is not a trick of the toy. It was measured: four runs of one unchanged
prompt agreed with the human mark on **14, 14, 15, 15 cases out of 21**, and
never the same fourteen. Per case that is a stream of regressions every week.
On the aggregate, `14/21` to `15/21` is `0.0476` — one case out of twenty-one,
inside a tolerance of `1/21` — so the gate never turned red on noise, and a
real drop of four cases still moved it well past the tolerance.

Hence the division of labour: **the aggregate is the gate, the per-case verdicts
are the diagnosis.** The first goes in the pipeline and, when you sell this, in
the contract. The second is what you read once the first goes red.

## 8. Keeping it alive: five triggers

A baseline is not maintenance-free, and it is not maintenance-heavy either.
Five moments call for a decision, and they divide in a way worth noticing.

The first three come from **inside**: you changed something, and digline says so
the next time you run it. Nothing is required of you but to answer.

The last two come from **outside**, and nothing announces them. The model moves
under you; a customer finds something you never thought to test. These are what
"maintenance" means to the person doing it, and each needs a *habit* rather than
a message — a schedule for one, a reflex for the other.

### Trigger one — the rules moved

Any change to a threshold, a tolerance, a sample count or an assertion changes
`config_hash`, and a run measured under the old rules cannot become the
reference for the new ones.

```python
# rules.py
"""The calibrated numbers, in one place so a change is one line in a diff."""

THRESHOLD = 0.70
TOLERANCE = 0.10
SAMPLES = 5
AGREEMENT = "3/5"
```

```console
$ digline promote --suite support.py --run latest
digline: ConfigMismatchError: run 2026-08-26T16-08-16-221095-00-00-2ba590fc617bbd5a was produced with config_hash 2ba590fc617bbd5a, the current configuration is ec1c0061f461d5e3: promoting it would record scores obtained under a configuration other than the one in force
```

The old runs stay readable and stay comparable — `digline view` lists them
attenuated, marked `OLDER CONFIG` — they simply cannot be frozen as the
reference. The response is chapter 4 and chapter 6 again: measure under the new
rules, promote the median. It costs one calibration and it is the only thing
that keeps the reference meaning what it says.

### Trigger two — the system got better, on purpose

An improvement you decided to keep has to be recorded, or every later comparison
is against a system you no longer ship, and the margin you worked for silently
becomes the new noise floor. `compare` tells you when this has happened: the
improvements are listed in the report exactly like the regressions.

Promote, commit, and say in the message what got better. The baseline diff in
that pull request is the whole argument.

### Trigger three — a case stopped being judged

A case that errors, or one you set aside, is coverage that shrank. It never
shows up as a failure, which is why it needs its own trigger.

```python
# support.py
"""The suite: who, where, what is checked, on what."""

import app
import rules
from digline.core import Contains, CostBudget, JudgeReply, LlmRubric, Repeated
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=app.judge(prompt), reason="judged")


def target(case: Case) -> Response:
    text, cost = app.reply(case.id)
    return Response(output=text, cost_usd=cost)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        Repeated(
            inner=LlmRubric(
                rubric="Does the reply answer the question?",
                judge=judge,
                threshold=rules.THRESHOLD,
                tolerance=rules.TOLERANCE,
            ),
            samples=rules.SAMPLES,
            min_agreement=rules.AGREEMENT,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
    ],
    cases=[
        Case(id="where-is-my-order"),
        Case(id="how-do-i-return"),
        Case(
            id="is-it-waterproof",
            suspended="the IPX rating is under review, ticket 412",
        ),
    ],
)
```

```console
$ digline run --suite support.py
2026-08-26T16-09-22-257722-00-00-ec1c0061f461d5e3

$ digline compare --suite support.py --run latest
Nothing got worse compared with the reference. Every case could be judged. 1 case is suspended. The configuration changed since the reference, so these numbers compare different rules.
```

The suspension is in the headline, with its reason, and it travels into the
report the customer reads. A suspension is mandatory-reason by construction: a
case that disappears quietly is the one failure mode a green suite cannot
survive. Set aside, fix, and put it back — the trigger is the sentence, and the
sentence does not go away on its own.

### Trigger four — the model changed under you

You changed nothing. The provider shipped a new version of the model, or
deprecated the one you were pinned to, or quietly adjusted a default. This is
the one trigger that arrives with no message at all, because from digline's side
nothing happened: same suite, same configuration, same cases.

So it has to be **asked** on a schedule. A weekly cron entry or a nightly CI job,
running the suite against the committed baseline and doing nothing else:

```text
# Monday 03:00, against the baseline in the repository.
0 3 * * 1  cd /srv/northwind && digline run --suite support.py \
           && digline compare --suite support.py --run latest
```

Take a fresh reference first, so what follows has nothing else in it:

```console
$ digline promote --suite support.py --run latest
support baseline set to 2026-08-26T16-24-18-627485-00-00-ec1c0061f461d5e3
```

Now the provider ships. Only `app.py` changes, and not by your hand —
`support.py` is not shown again below because it does not change, which is the
whole point of this trigger:

```python
# app.py
"""The system under test, and the judge.

Nothing here was edited by you. This is what the provider returns now.
"""

import random
from pathlib import Path

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Thursday.",
    "how-do-i-return": "Any item, within 30 days, unused.",
    "is-it-waterproof": "Rated IPX4: splashes yes, swimming no.",
}


def reply(question_id: str) -> tuple[str, float]:
    """Your model call. Canned, so this page needs no key."""
    text = ANSWERS[question_id]
    return text, 0.004 + 0.001 * len(text) / 100


def judge(prompt: str) -> float:
    """Your judge model — reproducible on purpose, see chapter 2."""
    counter = Path("votes.txt")
    asked = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(asked + 1))
    if "Northwind Support" not in prompt:
        return 0.4
    return 0.6 if random.Random(asked).random() < 0.25 else 1.0
```

```console
$ digline run --suite support.py
2026-08-26T16-24-18-887777-00-00-ec1c0061f461d5e3

$ digline compare --suite support.py --run latest
4 checks got worse compared with the reference. Every case could be judged. 1 case is suspended. The configuration is the same as the reference.

how-do-i-return · llm_rubric · Went from passing to failing (0.920000 → 0.400000).
how-do-i-return · contains · Went from passing to failing (1.000000 → 0.000000).
where-is-my-order · llm_rubric · Went from passing to failing (0.840000 → 0.400000).
where-is-my-order · contains · Went from passing to failing (1.000000 → 0.000000).
```

Read the last sentence of the headline: **the configuration is the same as the
reference.** Nothing in the repository moved, and four checks are red. That
sentence, on a run nobody launched by hand, is the provider's signature — and it
is the only way you find out on the Monday rather than from a customer on the
Thursday.

The response is not to re-promote. It is to decide: pin the old version if you
still can, or accept the new behaviour and take a new baseline under it — with
the diff of that baseline in the pull request, which is the record of what
changed and when.

### Trigger five — a real case went wrong in production

A customer asks something you never thought to test, gets a bad answer, and
tells you. The fix is ordinary work. What is not ordinary, and what this trigger
is about, is that **the case joins the suite and stays there for good.**

Today the gesture is by hand, and it is small. The reported question becomes a
`Case`, and the answer they should have had becomes its `expected`:

```python
# app.py
"""The system under test, and the judge.

The model is pinned again. The reported answer is still the wrong one.
"""

import random
from pathlib import Path

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Thursday. — Northwind Support",
    "how-do-i-return": "Any item, within 30 days, unused. — Northwind Support",
    "is-it-waterproof": "Rated IPX4: splashes yes, swimming no. — Northwind Support",
    "return-a-gift": "Any item, within 30 days of purchase. — Northwind Support",
}


def reply(question_id: str) -> tuple[str, float]:
    """Your model call. Canned, so this page needs no key."""
    text = ANSWERS[question_id]
    return text, 0.004 + 0.001 * len(text) / 100


def judge(prompt: str) -> float:
    """Your judge model — reproducible on purpose, see chapter 2."""
    counter = Path("votes.txt")
    asked = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(asked + 1))
    if "Northwind Support" not in prompt:
        return 0.4
    return 0.6 if random.Random(asked).random() < 0.25 else 1.0
```

```python
# support.py
"""The suite: who, where, what is checked, on what."""

import app
import rules
from digline.core import (
    Contains,
    CostBudget,
    JudgeReply,
    Levenshtein,
    LlmRubric,
    Repeated,
)
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=app.judge(prompt), reason="judged")


def target(case: Case) -> Response:
    text, cost = app.reply(case.id)
    return Response(output=text, cost_usd=cost)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        Repeated(
            inner=LlmRubric(
                rubric="Does the reply answer the question?",
                judge=judge,
                threshold=rules.THRESHOLD,
                tolerance=rules.TOLERANCE,
            ),
            samples=rules.SAMPLES,
            min_agreement=rules.AGREEMENT,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
        Levenshtein(threshold=0.85, tolerance=0.05),
    ],
    cases=[
        Case(id="where-is-my-order", expected=app.ANSWERS["where-is-my-order"]),
        Case(id="how-do-i-return", expected=app.ANSWERS["how-do-i-return"]),
        Case(
            id="is-it-waterproof",
            expected=app.ANSWERS["is-it-waterproof"],
            suspended="the IPX rating is under review, ticket 412",
        ),
        # Reported by a customer on 26 August: they asked about returning a
        # gift and were told the purchase-date policy. This is the answer they
        # should have had, and it stays here now.
        Case(
            id="return-a-gift",
            expected="Gifts can be returned within 30 days of delivery. — Northwind Support",
        ),
    ],
)
```

Two things came with the new case. `Levenshtein` joined the assertions, because
an `expected` nothing reads is a comment — and since every assertion applies to
every case, the other three cases need an `expected` too. That is the shape of
the suite talking: a check that compares against an expected value is a decision
about the whole suite, not about one case.

```console
$ digline run --suite support.py
2026-08-26T16-24-36-803385-00-00-e5881dce5cab0761

$ digline compare --suite support.py --run latest
1 check got worse compared with the reference. Every case could be judged. 1 case is suspended. The configuration changed since the reference, so these numbers compare different rules.

how-do-i-return · llm_rubric · Score fell from 0.920000 to 0.760000.
```

And there is the trap. The one line `compare` printed is chapter 2 again — judge
noise, inside nobody's tolerance but real — while the case you just added, the
one that reproduces the customer's complaint, **is not mentioned at all.** It is
`new`, not `regressed`: there is nothing in the baseline to compare it with, so
`compare` has nothing to say about it. On the day a case is added, the run is
what you read.

```python
# failing.py
"""Every check the latest run did not pass.

The day a case is added there is nothing in the baseline to compare it with, so
`compare` calls it `new` rather than `regressed` and says nothing about how it
went. The run itself says.
"""

from digline.cli.loader import load_suite
from digline.store import FileResultStore

suite, _module = load_suite("support.py")
store = FileResultStore(".")
latest = store.read_run(store.scan_runs(suite.tenant, suite.name).runs[-1])

short = 0
for case in latest.results:
    for verdict in case.verdicts:
        if verdict.status != "pass":
            short += 1
            score = "—" if verdict.score.score is None else f"{verdict.score.score:.3f}"
            print(
                f"{case.case_id:<18} {verdict.score.name:<12} {verdict.status:<5} {score}"
            )
print(
    f"{short} check{'' if short == 1 else 's'} not passing, over {len(latest.results)} cases"
)
```

```console
$ python failing.py
return-a-gift      levenshtein  fail  0.623
1 check not passing, over 4 cases
```

`0.623` is the customer's complaint, reproduced, in the repository, on demand.
Now fix the system — one string in `app.py`:

```python
# app.py
"""The system under test, and the judge.

The reported answer is fixed. The case that caught it stays in the suite.
"""

import random
from pathlib import Path

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Thursday. — Northwind Support",
    "how-do-i-return": "Any item, within 30 days, unused. — Northwind Support",
    "is-it-waterproof": "Rated IPX4: splashes yes, swimming no. — Northwind Support",
    "return-a-gift": "Gifts can be returned within 30 days of delivery. — Northwind Support",
}


def reply(question_id: str) -> tuple[str, float]:
    """Your model call. Canned, so this page needs no key."""
    text = ANSWERS[question_id]
    return text, 0.004 + 0.001 * len(text) / 100


def judge(prompt: str) -> float:
    """Your judge model — reproducible on purpose, see chapter 2."""
    counter = Path("votes.txt")
    asked = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(asked + 1))
    if "Northwind Support" not in prompt:
        return 0.4
    return 0.6 if random.Random(asked).random() < 0.25 else 1.0
```

```console
$ digline run --suite support.py
2026-08-26T16-24-37-046803-00-00-e5881dce5cab0761

$ python failing.py
0 checks not passing, over 4 cases

$ digline promote --suite support.py --run latest
support baseline set to 2026-08-26T16-24-37-046803-00-00-e5881dce5cab0761
```

The bug is fixed and, more to the point, it is now *guarded*: `return-a-gift` is
in the baseline, and the day some future prompt change breaks it again the
comparison will say so by name. A suite grows this way — one customer at a time
— and that growth is the part of it worth the most.

Doing it by hand is the part that will not last. A production failure carries
the customer's own text, which is exactly what must not be pasted into a
repository, and choosing an `id` by hand is how two cases end up sharing one.
Both are the job of the production-to-repository bridge — anonymisation
mandatory, `case_id` generated by digline and by nobody else — designed in
[ADR 0002](adr/0002-three-worlds-and-where-the-data-lives.md) and not yet built.
Until it is, the gesture above is the whole of it, and it is worth the minute it
takes.

### What the run remembers

Triggers four and five both end in the same question — *what was it, exactly,
that changed?* — and until now this guide could not answer it. The commit says
`-dirty`. The configuration says it did not move. Neither says which prompt
produced these verdicts, and by the time anyone asks, the working tree has moved
on.

So a suite can declare the files that **are** the thing under test, and every
run records their content and their digest:

```python
# support.py
"""The suite: who, where, what is checked, on what."""

from pathlib import Path

import app
import rules
from digline.core import (
    Contains,
    CostBudget,
    JudgeReply,
    Levenshtein,
    LlmRubric,
    Repeated,
)
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    return JudgeReply(score=app.judge(prompt), reason="judged")


def target(case: Case) -> Response:
    text, cost = app.reply(case.id)
    return Response(output=text, cost_usd=cost)


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        Contains(needle="Northwind Support"),
        Repeated(
            inner=LlmRubric(
                rubric="Does the reply answer the question?",
                judge=judge,
                threshold=rules.THRESHOLD,
                tolerance=rules.TOLERANCE,
            ),
            samples=rules.SAMPLES,
            min_agreement=rules.AGREEMENT,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
        Levenshtein(threshold=0.85, tolerance=0.05),
    ],
    # The file that *is* the thing under test. Its content and its digest go
    # into every run, so the baseline carries the system that produced it.
    artifacts=[Path("app.py")],
    cases=[
        Case(id="where-is-my-order", expected=app.ANSWERS["where-is-my-order"]),
        Case(id="how-do-i-return", expected=app.ANSWERS["how-do-i-return"]),
        Case(
            id="is-it-waterproof",
            expected=app.ANSWERS["is-it-waterproof"],
            suspended="the IPX rating is under review, ticket 412",
        ),
        # Reported by a customer on 26 August: they asked about returning a
        # gift and were told the purchase-date policy. This is the answer they
        # should have had, and it stays here now.
        Case(
            id="return-a-gift",
            expected="Gifts can be returned within 30 days of delivery. — Northwind Support",
        ),
    ],
)
```

```console
$ digline run --suite support.py
2026-08-26T16-41-23-002407-00-00-e5881dce5cab0761

$ digline promote --suite support.py --run latest
support baseline set to 2026-08-26T16-41-23-002407-00-00-e5881dce5cab0761
```

Now change one word of the answer — the provider shipping again, trigger four:

```python
# app.py
"""The system under test, and the judge.

Thursday became Friday. One word, nobody's edit, and the suite untouched.
"""

import random
from pathlib import Path

ANSWERS = {
    "where-is-my-order": "Order 4821 ships Friday. — Northwind Support",
    "how-do-i-return": "Any item, within 30 days, unused. — Northwind Support",
    "is-it-waterproof": "Rated IPX4: splashes yes, swimming no. — Northwind Support",
    "return-a-gift": "Gifts can be returned within 30 days of delivery. — Northwind Support",
}


def reply(question_id: str) -> tuple[str, float]:
    """Your model call. Canned, so this page needs no key."""
    text = ANSWERS[question_id]
    return text, 0.004 + 0.001 * len(text) / 100


def judge(prompt: str) -> float:
    """Your judge model — reproducible on purpose, see chapter 2."""
    counter = Path("votes.txt")
    asked = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(asked + 1))
    if "Northwind Support" not in prompt:
        return 0.4
    return 0.6 if random.Random(asked).random() < 0.25 else 1.0
```

```console
$ digline run --suite support.py
2026-08-26T16-41-23-184744-00-00-e5881dce5cab0761

$ digline compare --suite support.py --run latest
1 check got worse compared with the reference. Every case could be judged. 1 case is suspended. The configuration is the same as the reference. 1 file under test changed since the reference.

  app.py · +2 −2 lines

where-is-my-order · llm_rubric · Score fell from 0.920000 to 0.760000.
```

The headline now carries the sentence that was missing from trigger four:
**the configuration is the same, and one file under test changed.** Same rules,
different system. That is a different fact from either half alone, and it is the
one that tells you where to look — and the line under it says where, before the
score line says what it cost.

The terminal stops at the tally. `digline report` carries the diff itself, line
by line with context, and so does the comparison screen in `digline view`: a
prompt unrolled in a terminal would bury the regressions it is there to explain,
and both are one command away.

And it is not only a digest. The text is in the baseline, so what the reference
was actually running is recoverable long after the working tree has moved on:

```python
# recover.py
"""The system that produced the baseline, read back out of the baseline.

Not the digest — the text. A digest says two runs differ; the reader three weeks
later needs to know *what* the difference was, and by then the working tree has
moved on.
"""

from digline.cli.loader import load_suite
from digline.store import FileResultStore

suite, _module = load_suite("support.py")
baseline = FileResultStore(".").read_baseline(suite.tenant, suite.name)
assert baseline is not None

for path, artifact in sorted(baseline.artifacts.items()):
    text = artifact.text or ""
    print(f"{path}  {artifact.sha[:12]}  {len(text.splitlines())} lines")
    for line in text.splitlines():
        if "ships" in line:
            print(f"    baseline says: {line.strip()}")

for line in open("app.py", encoding="utf-8"):
    if "ships" in line:
        print(f"    the tree says: {line.strip()}")
```

```console
$ python recover.py
app.py  5f759f1c822b  31 lines
    baseline says: "where-is-my-order": "Order 4821 ships Thursday. — Northwind Support",
    the tree says: "where-is-my-order": "Order 4821 ships Friday. — Northwind Support",
```

A committed baseline is now the whole story: the verdicts, the configuration
that judged them, and the system that produced them.

One thing it is **not**, by default: something that leaves. A prompt is your
file, and it is also where an end company's rules end up — eligibility
conditions, thresholds, the phrasing legal insisted on. So a redacted run keeps
the path and drops both the text and the digest, and a suite that wants
otherwise says `Disclosure(artifacts=True)` in one line that goes through a
review, like every other widening of a perimeter.

The digest goes because a digest is a *verifier*. A prompt is not drawn from a
large space — you wrote the template, the customer tuned the numbers in it — so
a few thousand candidates hashed against a leaked digest give the text back, and
with it the rules. The cost of dropping it is real and stated: a comparison of a
redacted run says `unknown` about its artifacts rather than `same`, because it
genuinely cannot tell. The reasoning is
[ADR 0003](adr/0003-artifacts-travel-only-when-the-suite-says-so.md).

## Where to go next

- [`metrics.md`](metrics.md) — a card per assertion and aggregate: when to reach
  for it, what it produces, what to watch out for
- [`api.md`](api.md) — the reference: what is imported from where, every
  parameter, custom assertions
- [`view.md`](view.md) — the browser UI, which is where chapters 4 and 6 are a
  table instead of a script
- [`adr/`](adr/) — why the fixed decisions are fixed
