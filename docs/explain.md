# `digline explain` — the run, read back at length

`digline explain` is the run read back at length: the same facts and the same
numbers as `digline compare`, expanded instead of compressed into a sentence
and at most twenty lines.

What it reads back: what ran, what moved and by how much, inside or outside
which measured interval, what was set aside, what could not be judged, and
which of the three configurations differed underneath it all. `digline report`
compresses the same facts the other way, into a document with a customer's
answer in a box, and its whole craft is deciding what fits on the first screen.

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
The system under test was configured with model claude-haiku-4-5.

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

## A run that does not reconcile

Before any aggregate is computed, the driver checks that every question the
suite put to the run came back as exactly one verdict. A suspended case is
asked nothing, a calibration case is asked its one check, and every other case
is asked every assertion. Where the answer is missing, or is an answer nobody
asked for, the run records an errored verdict in its place and names the case
and the check. The reading then opens with it:

```text
1 check does not reconcile with what the suite asked. This is not a regression: what the run measured is not known. It is named below, among the checks that could not be judged.
```

It exits `2` and cannot be promoted, and it is not a regression.
[ADR 0027](adr/0027-the-run-reconciles.md) says why,
and what it cannot see: a target that catches its own exception and returns an
empty answer is a case that was scored, and only a check on content can tell.

## `--json`: the facts, not the prose

```console
$ digline explain --suite suite.py --run latest --json
```

emits the **fact list the prose is rendered from** — typed facts with case and
assertion references — and no sentences at all:

```json
{
  "output_version": 2,
  "scope": "comparison",
  "exit_code": 1,
  "facts": [
    {"about": "run", "kind": "cases", "count": 5, "state": null},
    {"about": "setting", "kind": "artifact", "name": "prompts/system.txt",
     "outcome": "changed", "before": null, "after": null,
     "withheld": false, "added": 1, "removed": 0},
    {"about": "setting", "kind": "rule", "name": "llm_rubric.threshold",
     "outcome": "changed", "before": 0.7, "after": 0.6,
     "withheld": false, "added": 0, "removed": 0,
     "direction": "loosened"},
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

**`"kind": "rule"` is the odd setting**, and the discriminator is what keeps it
honest. The other three settings are things *under test* — how the system was
configured, which instrument graded, which file was the subject. A rule is the
bar they were held to, and it carries `direction`: `"loosened"` where this run
is held to less than the reference was approved under, `"tightened"` where it is
held to more. The key is **absent** where the movement has no direction, which
is every `samples` row and is a different statement from *unchanged*
(ADR 0028 §4). `withheld` is always `false` here: nothing a rule is made of can
be kept back, which is why this is the one part of the reading that is complete
at a boundary.

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

**Verdicts whose samples are means are left out and counted.** A judged check
in `Repeated` in a sampled suite, a nested `Repeated` at any sample count, and
a `--judge-samples` replay of a `Repeated` check all store the **means** of
their judgements where the judgements would be. Read as judgements, a judge that
alternates 0 and 1 would show 0% at the extremes, the opposite of what it is.
Since 0.15.0 such a verdict carries `"sample_means": true`. The line leaves it
out, and says how many were left out and that their per-judgement scores were
not recorded. On the reference side, a sampled verdict with no stamp is left out
as well wherever this run stamped the same check, because a reference written by
0.14.x holds these folds unstamped. When a document cannot say what an absence
means, the rule errs toward leaving a verdict out, never toward misreading one.

**The one case this cannot reach.** A run that stamps nothing for the check,
such as the same `Repeated` check now at `samples=1`, against a reference
promoted before 0.15.0 at a different sample count. Nothing in the run points
at the check, and nothing in the reference says what its samples are, so its
share may be means read as judgements. `config_changed` is true for that
comparison. **Re-promote the reference to read it.** ADR 0024 §6.5.

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
