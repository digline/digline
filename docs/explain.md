# `digline explain` — the run, read back at length

`digline compare` gives you a sentence and at most twenty lines.
`digline report` gives a customer a document with an answer in a box. Both are
**compressions**: the report's whole craft is deciding what fits on the first
screen.

`digline explain` is the other direction. Same facts, same numbers, expanded —
what ran, what moved and by how much, inside or outside which measured
interval, what was set aside, what could not be judged, and which of the three
configurations differed underneath it all.

It **states, and never advises.** There is no "you should re-run this", no
"this looks promotable". That boundary is deliberate and is the reason the
command has a decision record of its own,
[ADR 0012](adr/0012-the-reading.md): whether a red run is a regression or a
wobble, and which run deserves to be the reference, is judgment digline leaves
to a person. Where you want the counsel it is in
[`AGENTS.md`](https://github.com/digline/digline/blob/main/AGENTS.md), written
for the purpose and marked as judgment.

## Using it

One run key, and the presence of a baseline decides the rest:

```console
$ digline explain --suite suite.py --run latest
What ran
5 cases ran.
10 checks ran.
Every case could be judged.
No case is suspended.
The suite is unchanged from the reference.

What differed underneath
prompts/system.txt changed: +1 −0 lines.

What moved
gift-wrap · llm_rubric got worse: 1.000000 to 0.700000, a drop of 0.300000. That is outside the interval its reference measured, 1.000000–1.000000 across 3 samples.
opening-hours · levenshtein got worse: 1.000000 to 0.636364, a drop of 0.363636.
```

A comparison states no threshold, and the report is why: its case tables are
about movement against a reference and print no bars, so a reading of one
prints none either. The number is on the fact and in `--json`, and the run
document shows `score / threshold` on every row. That rule has a name — every
value this command prints appears in the same run's report — and it is a test,
not a convention.

With **no baseline** it reads the run alone, and says so by what it does not
say — no "reference", no "got worse", no comparison of any kind:

```console
$ digline explain --suite suite.py --run latest
What ran
5 cases ran.
10 checks ran.
Every case could be judged.
No case is suspended.

How it was set up
prompts/system.txt was under test.
The system under test answered with model claude-haiku-4-5.

What it found
opening-hours · levenshtein is under its bar at 0.636364. The bar is 0.750000.
```

There is no mode flag, and there is not going to be one. Making you name the
scope means making you know, before you type, which of two documents you are
entitled to — and the first person to hit that is always somebody on their
first run, who has no baseline and does not yet know what one is.

## The exit code

`explain` **gates**, exactly as `report` does: `0` fine, `1` got worse, `2`
could not be judged. It is reading the same comparison, against the same
approved reference, that `compare` gates on.

With no baseline it can never exit `1` — "worse" is a relation and there is
nothing here to be worse than — but `2` survives, because a case the suite
could not judge is a fact about the harness rather than about a reference.

This is the opposite of [`digline diff`](diff.md), which always exits 0, and
the difference is the reference: a verdict exists only against one that a
person approved.

## `--json`: the facts, not the prose

```console
$ digline explain --suite suite.py --run latest --json
```

emits the **fact list the prose is rendered from** — typed facts with case and
assertion references — and no sentences at all:

```json
{
  "output_version": 1,
  "scope": "comparison",
  "exit_code": 1,
  "facts": [
    {"about": "run", "kind": "cases", "count": 5, "state": null},
    {"about": "setting", "kind": "artifact", "name": "prompts/system.txt",
     "outcome": "changed", "before": null, "after": null,
     "withheld": false, "added": 1, "removed": 0},
    {"about": "check", "kind": "regressed", "scope": "case",
     "case_id": "gift-wrap", "assertion": "llm_rubric",
     "assertion_id": "llm_rubric:…", "before": 1.0, "after": 0.7,
     "delta": -0.3, "threshold": 0.7,
     "noise_min": 1.0, "noise_max": 1.0, "noise_samples": 3}
  ]
}
```

Three shapes, and you discriminate on `about` first and then on `kind`: two of
them have a kind called `within_noise` and they mean different things — one
check that moved inside its interval, and the count of every check that did.

`scope` is `"comparison"` or `"run"` and is stated rather than left to be
inferred: a run whose comparison found nothing and a run with no reference at
all produce different readings, and the difference must not be something you
deduce from an absence.

`exit_code` is the number the process exits with, carried as a field for the
same reason it is on `compare --json`.

## Shape: judged scores at the extremes

Against a reference, the reading adds one line per judged check — a check whose
class declares `KIND = "judged"`, written into the run as `"judged": true`:

```text
faithfulness: 97.1% of 208 judged scores at 0 or 1, against 41.3% of 204 in the reference.
```

It reads **raw per-sample scores**, never a folded mean, over the cases that
count: not a canary, not a calibration case, not a verdict that errored. A
`Faithfulness` verdict with a single claim can only score 0 or 1, so it is left
out, and the line says how many were. At `samples > 1` the run keeps only the
mean claim count, so a sampled verdict averaging two or more is read, and the
line says its per-sample counts were not recorded. Against a reference written
before 0.14.0, which carries no `"judged"` key, the line says there is nothing to
set beside the share.

**A known limit: `Repeated` in a sampled suite.** At `samples > 1`, a check
wrapped in `Repeated` stores the per-answer **means** of its judgements, not the
judgements themselves. A judge that alternates 0 and 1 inside `Repeated` is
stored as `0.5, 0.5` and reads as **0%** at 0 or 1 — the opposite of what it
is. The run document cannot yet say which verdicts are such folds, so the line
cannot leave them out. Until it can, **do not read a shape line for a `Repeated`
check in a sampled suite**. At `samples=1` the reading is exact. The fix is ruled
for the next schema change: those verdicts will be left out and counted, as
single-claim verdicts are. ADR 0024 §6.2, amended.

**It says nothing about which share is larger**, and that is not an omission.
*More than the reference* needs a threshold, and on a suite of twenty cases one
verdict moves a share by five points. The threshold is sized on data and added
by a dated amendment to [ADR 0024](adr/0024-the-judge-as-an-instrument.md) §6.3.
Until then this is a measurement, not a verdict. It is never in the headline and
never an exit code: the [calibration case](api.md#casecalibration-watching-the-judges-scale)
is the gate, and shape is the diagnosis.

In `--json` it is a fact with `"kind": "shape"`, carrying its counts under
`shape` — `check`, `assertion_id`, and `run` and `reference`, each with
`extremes`, `scores`, `single_claim` and `claims_unrecorded` (`reference` is
`null` where there is none). `compare --json full` carries the same list as
`shape`.

A check whose class declares no `KIND` is not read, and `digline run` names it.
An autoevals scorer wrapped in `FromAutoevals` is not read either, and is **not**
named — the known hole, described in the
[API reference](api.md#custom-assertions).

## What it will not tell you

**The judge's words.** No fact carries a `reason` — the field does not exist on
the types, which is what makes the payload boundary something no later edit can
open by accident. **For the judge's words, `digline report` is one command
away**, and it renders them in a Reason column.

The same rule takes the stated reason a case was suspended: that a case was set
aside travels, because it is a fact about coverage; *why* somebody set it aside
does not, because a developer writes things like "fails on the Rossi account".

**Anything about a second run.** A reading is of one run and its reference, so
it will never tell you that a drop "did not repeat" or that a check is
"drifting". Those need a cycle of runs, and the thing that runs cycles is the
[operator loop](https://github.com/digline/digline/tree/main/examples/operator)
— whose alert keeps its own layers for exactly that, and marks the one a model
wrote as an opinion rather than as digline's verdict.

## `--locale`

`en` or `it`, defaulting to `en`. Terminal output is for you, so it follows the
runtime rule; a *document* — which is what `digline report --locale` writes —
has a recipient who did not choose English, and takes the flag as mandatory.

There is no `--out`, and its absence is what keeps that distinction honest
rather than an oversight: the moment a reading is written to a file it has a
recipient, and the locale would have to become mandatory too.
