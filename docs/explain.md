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

The numbers below are an example of the shape. No scenario in this repository
produces them, so nothing here replays this block.

```console
$ digline explain --suite suite.py --run latest
What ran
5 cases ran.
10 checks ran.
Every case could be judged.
No case is suspended.
The suite changed since the reference, so these numbers compare different rules.
llm_rubric: 0.0% of 15 judged scores at 0 or 1, against 20.0% of 15 in the reference.

What differed underneath
prompts/system.txt changed: +1 −0 lines.
llm_rubric.threshold moved from 0.7 to 0.6, which is a looser bar than the reference was approved under.
The agreement floor is not recorded in a run, so whether it moved cannot be told from these two.

What moved
gift-wrap · llm_rubric got worse: 1.000000 to 0.700000, a drop of 0.300000.
opening-hours · levenshtein got worse: 1.000000 to 0.636364, a drop of 0.363636.
```

The shape line is there for every judged check, and it reports one thing: what
fraction of the judged scores sat at the ends of the scale, here and in the
reference. It never says which fraction is better — a rubric that has stopped
grading and started voting is something a reader has to weigh, not a verdict
(ADR 0024 §6.3). The reading itself is set out under *Shape*, below.

A comparison states no threshold, and the report is why: its case tables are
about movement against a reference and print no bars, so a reading of one
prints none either. The number is on the fact and in `--json`, and the run
document shows `score / threshold` on every row. That rule has a name — every
value this command prints appears in the same run's report — and it is a test,
not a convention.

With **no baseline** it reads the run alone, and says so by what it does not
say — no "reference", no "got worse", no comparison of any kind:

The numbers below are an example of the shape. No scenario in this repository
produces them, so nothing here replays this block.

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

## A verdict named otherwise than its assertion

A verdict carries the name of the assertion that produced it. Every shipped
assertion already does. A third-party one that names its verdict otherwise,
for example from the answer (`named_Rossi`), would put that name into every
document, redacted ones included, because a verdict's name always crosses. So
the driver compares each verdict's name with the one the assertion declared
before the first case, and refuses the mismatch. That check's verdict on that
case becomes an errored verdict under the declared name, marked `misnamed`. The
case's other checks stand. The reading says so directly before it counts the
cases that could not be judged:

```text
1 check returned a verdict under a name that is not its assertion's, and it was refused. The assertion is at fault, not the system under test. It is named below, among the checks that could not be judged.
```

The marker survives redaction, which the reason does not. So a redacted
document still tells this apart from an assertion that raised. It exits `2`
and cannot be promoted, like every errored verdict.
[ADR 0027](adr/0027-the-run-reconciles.md) §6, as amended, says why, and what it
does not close: an assertion *declared* with a name taken from client data
matches its verdicts, and passes.

## `--json`: the facts, not the prose

```console
$ digline explain --suite suite.py --run latest --json
```

emits the **fact list the prose is rendered from** — typed facts with case and
assertion references — and no sentences at all:

The numbers below are an example of the shape. No scenario in this repository
produces them, so nothing here replays this block.

```json
{
  "baseline_key": "2026-10-21T07-41-16-574186-00-00-8d81ff7740eae5b6",
  "exit_code": 1,
  "facts": [
    {
      "about": "run",
      "count": 5,
      "kind": "cases",
      "state": null
    },
    {
      "about": "run",
      "count": 10,
      "kind": "checks",
      "state": null
    },
    {
      "about": "run",
      "count": 0,
      "kind": "unjudged",
      "state": null
    },
    {
      "about": "run",
      "count": 0,
      "kind": "suspended",
      "state": null
    },
    {
      "about": "run",
      "count": 0,
      "kind": "suite_config",
      "state": true
    },
    {
      "about": "run",
      "count": 0,
      "kind": "shape",
      "shape": {
        "assertion": "llm_rubric",
        "assertion_id": "4e7ba5d3e226025c",
        "reference": {
          "claims_unrecorded": 0,
          "extremes": 3,
          "sample_means": 0,
          "scores": 15,
          "single_claim": 0
        },
        "run": {
          "claims_unrecorded": 0,
          "extremes": 0,
          "sample_means": 0,
          "scores": 15,
          "single_claim": 0
        }
      },
      "state": null
    },
    {
      "about": "setting",
      "added": 1,
      "after": null,
      "before": null,
      "kind": "artifact",
      "name": "prompts/system.txt",
      "outcome": "changed",
      "removed": 0,
      "withheld": false
    },
    {
      "about": "setting",
      "added": 0,
      "after": 0.6,
      "before": 0.7,
      "direction": "loosened",
      "kind": "rule",
      "name": "llm_rubric.threshold",
      "outcome": "changed",
      "removed": 0,
      "withheld": false
    },
    {
      "about": "setting",
      "added": 0,
      "after": null,
      "before": null,
      "kind": "rule",
      "name": "min_agreement",
      "outcome": "unknown",
      "removed": 0,
      "withheld": false
    },
    {
      "about": "check",
      "after": 0.7,
      "assertion": "llm_rubric",
      "assertion_id": "4e7ba5d3e226025c",
      "before": 1.0,
      "case_id": "gift-wrap",
      "delta": -0.3,
      "denominator_moved": false,
      "kind": "regressed",
      "noise_judged": [],
      "noise_max": null,
      "noise_min": null,
      "noise_samples": 0,
      "noise_sd": null,
      "noise_source": "",
      "noise_width": null,
      "scope": "case",
      "threshold": 0.6
    },
    {
      "about": "check",
      "after": 0.636364,
      "assertion": "levenshtein",
      "assertion_id": "9831ae8fdaf2e736",
      "before": 1.0,
      "case_id": "opening-hours",
      "delta": -0.363636,
      "denominator_moved": false,
      "kind": "regressed",
      "noise_judged": [],
      "noise_max": null,
      "noise_min": null,
      "noise_samples": 0,
      "noise_sd": null,
      "noise_source": "",
      "noise_width": null,
      "scope": "case",
      "threshold": 0.5
    }
  ],
  "note": "",
  "output_version": 6,
  "reading": "comparison",
  "run_key": "2026-10-21T07-41-16-853431-00-00-c9092e23876f6e60"
}
```

`note` is what resolving `latest` stepped over, the line printed on stderr, and
empty here because nothing was. It is never a fact about the run: it says which
run was read, and why that may not be the newest one the store remembers.

`run_key` is the run that was read, and `baseline_key` the reference it was held
against. Both come from the documents read, not from what you typed, so they
name the run `latest` picked and confirm a key typed by hand. `baseline_key` is
there only where `reading` is `comparison`: where it is `run`, no reference was read.
`compare --json` carries `run_key` beside its `baseline_key` for the same reason.

Three shapes, and you discriminate on `about` first and then on `kind`: two of
them have a kind called `within_noise` and they mean different things — one
check that moved inside its interval, and the count of every check that did.

**`"kind": "rule"` is the odd setting**, and the discriminator is what keeps it
honest. The other three settings are things *under test* — how the system was
configured, which instrument graded, which file was the subject. A rule is the
bar they were held to, and it carries `direction`: `"loosened"` where this run
is held to less than the reference was approved under, `"tightened"` where it is
held to more. The key is **absent** for two different reasons, and neither is
*unchanged* (ADR 0028 §4). One row moved and has no direction to give: a
`samples` row on a run-level aggregate, because an aggregate's floor is still
the range of its own samples and nothing here can weigh them — a case check's
`samples` does carry a direction, since more samples steadies the score and
narrows the floor. The others are not known to have moved at all: a threshold, a
tolerance, a `samples` or a width comes through as `unknown` where one side's
own cases do not settle on a single value, by disagreeing or, for `samples`, by
erroring before it was counted. `min_agreement` is always one of those, because
a run does not record it; its row is there only where the configuration's
fingerprint moved, and it says that whether the floor changed cannot be read
from these two documents. `withheld` is always `false` here: nothing a rule is
made of can be kept back, which is why this is the one part of the reading that
is complete at a boundary.

`reading` is `"comparison"` or `"run"` and is stated rather than left to be
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
`shape` — `assertion`, `assertion_id`, and `run` and `reference`, each with
`extremes`, `scores`, `single_claim` and `claims_unrecorded` (`reference` is
`null` where there is none). `compare --json full` carries the same list as
`shape`.

A check whose class declares no `KIND` is not read, and `digline run` names it.
An autoevals scorer wrapped in `FromAutoevals` is not read either, and is **not**
named — the known hole, described in the
[API reference](api.md#custom-assertions).

## A verdict that is not firm

A judged check on a case is **uncertain** when its samples did not all reach
the same verdict, or when its mean sits within a margin of its threshold. The
margin is the check's tolerance where it declares one above 0, and 0.05 where
it does not, and each case says which:

```text
2 judged checks on cases are uncertain, and their verdicts could have gone the other way: torn · llm_rubric: the samples did not all agree, 0.67 of them on the majority verdict; close · llm_rubric: the mean 0.520000 is within 0.05 of the threshold 0.500000, a margin of 0.05, because the check declares no tolerance.
```

A check in error is not one: it gave no verdict. Two kinds of case are left
out whatever their samples: a **calibration case**, whose band says more,
and a **reviewed answer**, which `explain` says where the judge contradicted
the person. On the walkthrough from the IDE, three reviewed answers the judge
agreed with scored 1 against a threshold of 1, and each read as uncertain
until they were left out. It is read off the run alone, so it is said with
or without a reference; it moves no exit code and is not in `compare`'s
sentence. The run's report shows the same cases in a section of its own,
*Uncertain verdicts*, absent when there is none, and `--json` carries them
beside the count, on the `uncertain` tally, under the key `uncertain`: each
case's `case_id`, `check`, `score`, `threshold`, `margin`,
`margin_declared`, `split`, `near`, `agreement` and `errored_samples`. Under
`--names project` the MCP `explain` carries them with the case and the check
as tokens, as every fact does
([ADR 0012](adr/0012-the-reading.md) §3, as amended 2026-11-14).

## The judge against the person

*Arrives with digline 1.4.* Where the run holds reviewed answers with a
person's verdict, the reading closes its counts with *How the judge agrees
with the person*: one line per judged check and role, then the line that says
whether the suite can gate
([ADR 0067](adr/0067-calibrating-the-judge-against-a-person.md) §1 (c), (e),
§2, §5):

```text
accurate, held in: blind, 2 of 6 agree (3 passed a no, 1 failed a yes); after review, 4 of 6 agree (1 passed a no, 1 failed a yes). 2 answers were revised between the two. 1 answer could not be judged on it.
Held out: 4 of 6 verdicts agree after review, check by check; 7 held-in answers served the tuning and are not counted here.
Stability across runs was not measured: no other run of this suite holds these answers under these checks, so only a verdict whose samples split is set apart.
```

These lines come from the fixture in `tests/test_agreement.py`, which asserts
each one word for word, and not from a suite run end to end.

- **Blind and after review.** *Blind* reads the judge's verdicts against the
  person's verdict given before any disagreement was read. *After review*
  reads them against the verdict the gate holds, the `revised` one where
  there is one. The revised count is how many answers moved between the two:
  a judge that agrees only after the person revised toward it persuaded the
  person.
- **Held in and held out**, never summed. The `Held out:` line reads the
  held-out verdicts after review alone. Where no answer is held out, the line
  says so instead: *the agreement above was measured on the answers the
  rubric was tuned on*. Held-out answers are **counted, not named**, here
  and in `--json`, unless `--show-held-out` asks (below).
- **What is not counted.** An answer awaiting a verdict, a check the answer
  was not reviewed for, and a check on an episode's steps. A verdict that
  errored is counted apart, as *could not be judged*, in neither figure.
- **Stability.** *Arrives with digline 1.4.* A verdict the judge could not
  hold is **unstable**, counted in neither figure and named apart with why:
  its samples split, or one could not judge; its judgements under
  `--judge-samples` fall on the two sides of the threshold; or the runs read
  disagree. The runs read are this run and every other stored run of the
  suite that holds one of its reviewed answers judged by a check of the same
  identity, so `explain` reads the store here, as it reads a re-judge's
  source. The line says how many, and stability across runs is measured from
  two: *Stability was read across 3 runs of this suite with these checks:
  every verdict held.* With one, it says it was not measured, and only a
  verdict whose samples split is set apart
  ([ADR 0067](adr/0067-calibrating-the-judge-against-a-person.md) §3). A
  stored run of a schema this version does not read is passed over and
  said, *1 run not read: schema unknown to this version.*
- **The composite against its criteria.** Where the suite declares
  `criteria` on a composite check, the reading names each held-in answer about
  the whole answer on which the composite is not the conjunction of its
  criteria, *w1: overall passed, polite failed*, and counts the held-out ones.
  See [calibration](calibration.md#choosing-the-judge).
- **The review rule.** Under the agreement, the terminal reading quotes the
  suite's `review_rule`, or says the suite does not say what a yes means. It
  is the suite's own words, so it is text and not a fact, as the judge's words
  are: neither `--json` nor the MCP `explain` carries it.

Only the gate's own sentence, among the counts above, names a contradicted
answer whatever its role: a contradiction fails the run, held out or not.

**`--show-held-out`** *(arrives with digline 1.4)* names what the reading
otherwise counts of the held-out answers: each disagreement with the judge's
reason, each unstable verdict, each composite disagreement. It says first what
reading them costs
([ADR 0067](adr/0067-calibrating-the-judge-against-a-person.md) §1 (e)):

```text
The held-out answers, shown on request: read before the rubric is frozen, these answers are no longer held out.
aside-no, tone, held out: passed where the person said no. The judge said: mean of 3 samples (1.000000, 1.000000, 1.000000)
```

These lines come from `tests/test_stability.py`, which runs a suite end to
end and asserts them. The run's report has no options: its section
*What the judge said of the reviewed answers* counts the held-out answers
and says that `explain --show-held-out` shows them.

In `--json` it is a fact with `"kind": "agreement"`, whose `count` is the
reviewed answers with a verdict. Its `agreement` object carries:

- `held_in` and `held_out`;
- `stability_measured`, true from two runs read, `runs_read`, and
  `runs_unread`, the suite's stored runs of a schema this version does not
  read, passed over;
- `checks`, one entry per check and role, each with `check`, `assertion_id`,
  `held_out`, `blind` and `after` (each of `agree`, `passed_no`,
  `failed_yes`), `revised`, `unjudged` and `unstable`;
- `unstable`, the held-in unstable verdicts (`case_id`, `check`,
  `assertion_id`, `held_out`, `why`: `runs`, `samples` or
  `judge_samples`), and `unstable_held_out`, the count of the held-out ones;
- `composites`, the held-in disagreements (`case_id`, `composite`,
  `composite_passed`, `failed`, `held_out`);
- `composites_held_out`, the count of the held-out ones;
- `held_out_disagreed`, the count of the held-out verdicts that disagree
  with the person, and `held_out_disagreements`, empty.

Under `--show-held-out` the held-out entries join `unstable` and
`composites`, and `held_out_disagreements` names each (`case_id`, `check`,
`direction`). The counts are the same either way, and no reason is in
`--json`. The MCP `explain` reads as `explain` does without the option.

The run's report shows the same lines in a section of its own.

## A re-judge against the run it was made from

*Arrives with digline 1.4.* Where the run is a re-judge, `rejudged_from`, and
holds reviewed answers with a person's verdict, `explain` reads the run it was
made from and closes its counts with *What the re-judge changed, against the
run it was made from*
([ADR 0067](adr/0067-calibrating-the-judge-against-a-person.md) §1 (d)):

```text
Read against 2026-11-22T09-00-00-000000-00-00-0123456789abcdef, the run this was re-judged from, on 3 reviewed answers in both.
llm_rubric changed since that run, its rubric or another of its settings; verdicts paired by name.
no-bad · llm_rubric: passed → failed, toward the person.
1 held-out answer changed verdict on a paired check, counted and not named.
```

These lines come from the fixture in `tests/test_rejudge_reviewed.py`, which
asserts them word for word, and not from a suite run end to end.

- **Paired by name.** A corrected rubric is a new identity, so the two runs
  are paired by check name and case. Each check the person said something
  about is said *changed*, its identity moved, or *unchanged*.
- **Not paired.** A check whose type changed, *its type changed,
  llm_rubric → faithfulness*; one whose type the source did not record, which
  is every run written before schema 25; and a name two checks share on one
  answer. Their verdicts are listed nowhere.
- **Each change, with its direction.** A held-in answer whose verdict changed
  is named, toward the person's verdict or away; where one side could not be
  judged, toward neither. A held-out one is counted and never named.
- **A source the store no longer holds** is said, *could not be read: its
  verdicts are not compared*, rather than the block being left out.

`digline rejudge --reviewed` prints the same lines at its end
([rejudge](rejudge.md#a-round-on-the-reviewed-answers-alone-reviewed)). In
`--json` it is a fact with `"kind": "rubrics"`, whose `count` is the reviewed
answers read in both. Its `rubrics` object carries `source`, `source_held`,
`answers`, `paired` (`check`, `check_type`, `before_id`, `after_id`,
`changed`), `unpaired` (`check`, `why`, `before`, `after`), `changes`
(`case_id`, `check`, `before`, `after`, `toward`) and `held_out_changes`. The
run's report shows the same lines in a section of its own.

## What it will not tell you

**The judge's words.** No fact carries a `reason` — the field does not exist on
the types, which is what makes the payload boundary something no later edit can
open by accident. **For the judge's words, `digline report` is one command
away**, and it renders them in a Reason column.

**Except where its samples disagreed.** Where the samples of a judged check did
not all reach the same verdict, or one of them could not judge, the terminal
reading closes with *What the judge said, where its samples disagreed*: each
such case under its check, with what each sample said. It is read off the run
and printed after the facts; it is not a fact, `--json` and the MCP `explain`
do not carry it, and no sentence that sums the run up quotes the judge
([ADR 0012](adr/0012-the-reading.md) §4, as amended 2026-11-12).

**The cases, against a reference.** After the counts, the terminal reading
says the two sentences `compare` says when the cases changed: *the cases
changed since the reference*, with the added and the removed named, and the
cases a person *excluded at promotion* from the reference, with who
([ADR 0065](adr/0065-a-case-excluded-at-promotion-and-the-cases-a-run-was-made-with.md)). They are text, as the
judge's words are: not facts, not in `--json` or the MCP `explain`, and they
move no exit code.

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
