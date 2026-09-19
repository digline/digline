# `digline rejudge` — judging stored answers again

Change the judge, or the rubric, or a threshold, and you want to know what the
*same answers* would have scored. Until 0.10.0 the only way to find out was to
pay the target for answers nobody doubted.

`rejudge` reads a stored run, replays the answers it recorded through the
**current** suite, and writes a run that says where the answers came from.

```console
$ digline rejudge --suite eval/suite.py --run latest
digline: 12 cases × 1 recorded answer = 12 answers replayed; no call to the target
2026-09-11T14-02-55-018244-00-00-6f2a1c4e5b7d9a01
```

## First, the suite has to record

Nothing is recorded unless the suite asks, and a run already produced cannot
gain answers nobody kept:

```python
suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[...],
    cases=[...],
    record_responses=True,
)
```

One line in `[suite]` for a data suite. It does **not** change `config_hash`, so
turning it on costs no baseline and no re-promotion — recording changes no
score, pairs no verdict differently and moves no bar.

What lands in the run file, per case and per sample: the answer, the rendered
prompt that produced it, and what that call cost in money, in milliseconds and
in tokens.

A replay's own bill says what the *replay* spent: its target line is a zero,
because it called no target, and its judge line is real, because the judging is
what a replay pays for. The recorded `cost_usd` it replays still feeds a
`CostBudget` — that is why it rides the record — and it never becomes this run's
total (ADR 0025 §3).
The prompt is recorded because most assertions that call a model read it — a
stored answer with no stored question cannot be judged again.

To tell whether a stored run recorded, look at its cases. There is no flag
restating what the data already shows: a case that recorded carries a
`responses` list, one entry per sample, each with its `output`, and a run that
recorded nothing has no `responses` key at all. A redacted document of a run
that did record keeps one `{"withheld": true}` per sample, so the count
survives. `{"oversize": true}` is an answer the recorder refused over the
ceiling described below.

## Why not a cache

The field's usual answer to this is a response cache: a hidden directory, keyed
by something like the request, consulted before the provider is called. It is a
good engineering trade and a bad instrument. A cache returns an old answer *as
though it were a new one* — nothing in the resulting document says the model was
never asked, so a suite can go green against answers produced by a model that
has since been replaced.

A re-judged run says so, in the document, in the headline sentence, in
`compare --json`, and on the report a customer reads:

> The answers in this run were replayed from a stored run, not measured: the
> target was not asked anything.

## What it carries, and what is fresh

| | |
|---|---|
| the judge's configuration | **measured now** — the judge really ran, and it is what is under examination |
| the target's configuration, the artifacts | **carried from the source** — they describe the system and the prompt that produced these answers |
| `created_at`, `git_commit`, `digline_version` | fresh: this evaluation is happening now |
| `config_hash` | the current suite's — the rules moving is the point |
| `rejudged_from` | the key of the run the answers came from |

## The five refusals

Each one arrives before the first judge is paid, and each names what is missing.

1. **The stored run recorded no answers.** Recording is opt-in, so this is the
   ordinary first encounter: set `record_responses=True` and run it again.
2. **A case has no recorded answer.** A case added since the run was produced
   cannot be re-judged from it, and judging the rest would be a narrower
   measurement carrying the declared suite's name. A
   [calibration case](api.md#casecalibration-watching-the-judges-scale) is
   the exception: it carries its own answer, never records one, and is re-judged
   from its declaration exactly as a live run judges it.
3. **An answer is withheld or over the size ceiling.** A partial replay is a
   weaker measurement claiming to be the declared one — the rule the driver
   already applies when one call of a sampled case fails. The ceiling is 65 536
   characters per field, and over it the run records neither the answer nor the
   prompt rather than half of either: a clipped answer re-judged produces a
   score that looks like every other score.
4. **The sample count does not match.** A replay at one count over a run taken
   at another is a different measurement wearing the suite's name.
5. **The suite judges a trajectory and the run recorded none.** `tools_called`
   and `tool_called_with` read what the model called on the way to its answer,
   and a run produced before trajectories were recorded — or by a target that
   reports none — carries nothing for them to read. This one is a refusal rather
   than an errored check on purpose: an errored check is a declared gate quietly
   becoming a row nobody gated on, which is the thing recording the trajectory
   was for. Produce a new run with a target that reports one.

## A replay is not promotable

```console
$ digline promote --suite eval/suite.py --run 2026-09-11T14-02-55-…
digline: ReplayedRunError: run … was judged from the recorded answers of …,
not from the target.
```

A replay has **zero target variance** by construction: the answers are fixed, so
the interval it records is the judge's wobble alone. Promoted, it would become
the reference every future real run is measured against — and a movement is
judged against the *baseline's* interval, so every ordinary wobble of the target
would then read as a movement beyond the noise. A replay promoted as a reference
is a noise floor measured without the noise.

It is the fourth condition on promotion, beside the three that were already
there: the tenant must be the perimeter, the configuration must match, the run
must have judged every case — and the answers must have been measured.

## Measuring the judge: `--judge-samples`

A replay holds the answers still, so it is the one place the judge's own
variation can be measured without the target's mixed in:

```console
$ digline rejudge --suite eval/suite.py --run latest --judge-samples 5
digline: 12 cases × 1 recorded answer = 12 answers replayed; no call to the target; each recorded answer is judged 5 times by faithfulness
digline: the judge's own range on these answers is at most 0.100000 across 5 judgements (faithfulness, answer 1 of case refund-policy); the calibration case half-supported scored 0.500000, inside its declared band 0.300000–0.700000
2026-09-17T09-12-40-…
```

Each judged check — `KIND = "judged"`, read through `Repeated` — asks the judge
M times per recorded answer, in call order. Checks nothing judges run once, as
always.

**What each verdict records does not change.** An answer contributes its first
judgement — the first, in call order, that returned a score — exactly as a plain
replay does, so a `--judge-samples` replay and a plain one of the same run carry
the same scores, and comparing the two isolates the flag. The rest is
measurement, in each judged verdict's metadata:

| key | |
|---|---|
| `judge_samples` | M |
| `judge_errored` | judgements, across the case's answers, that returned no score |
| `judge_min`, `judge_max` | the lowest and highest score of **the one answer** whose judgements spread widest |
| `judge_answer` | that answer's position, from 1; on a tie, the lowest |

Both bounds come from one answer on purpose: a minimum on one answer and a
maximum on another describe two different questions, not an unstable judge. A
judgement that errors is counted, not escalated — it is the instrument's fault,
not the case's, and its chance grows with M. An answer with no scored judgement
at all is unjudged, as it would be anyway.

**Never on the noise floor.** `compare()` reads `sample_min` and `sample_max` as
the baseline's interval; the judge's range never reaches them, and a
`--judge-samples` replay is not promotable, like every replay.

**Never without the scale.** A judge that has gone binary is *more* repeatable:
every answer at 1.00, every time, is a range of zero. So the sentence always
carries the calibration result beside the range, and a suite with no
[calibration case](api.md#casecalibration-watching-the-judges-scale) is told
*this suite declares no calibration case, and a judge that has lost its scale
reads as perfectly repeatable*. The sentence is printed by `rejudge` on stderr,
and is `judge_reading` in `--json`; later reports of the run do not repeat it.
The run records the count as `judge_samples`. Reasoning in
[ADR 0024](adr/0024-the-judge-as-an-instrument.md) §5.

## Where the answers stay

In `.digline/<tenant>/runs/`, which is gitignored. They do not leave:

- `digline report --redacted` and every MCP response carry the verdicts and not
  the answers. No `Disclosure` releases them, and none can be added — a judge's
  `reason` is already withheld *because it quotes the output*.
- `digline promote` strips them. `baselines/` is committed, and a reference of
  verdicts has no business carrying the model's answers into a git history.

## See also

- [`api.md`](api.md) — `Suite.record_responses`, and what a re-judge needs
- [`adr/0015-the-recorded-output-and-the-declared-re-judge.md`](adr/0015-the-recorded-output-and-the-declared-re-judge.md) — the record
- [`adr/0002-three-worlds-and-where-the-data-lives.md`](adr/0002-three-worlds-and-where-the-data-lives.md) — the payload stays where it is born
