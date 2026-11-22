# ADR 0067 — Calibrating the judge against a person: a blind verdict, a held-out set, and a rubric changed one round at a time

- Status: accepted 2026-11-14, by Alessandro Prandini, proposed the same day
  from a first use outside the project, on an application with a judged
  suite. Three decisions were taken by Alessandro
  Prandini on 2026-11-14, before this record was written, and are stated
  here in its own words: `--accept-contradiction` is allowed only where the
  judge's samples disagreed, and is recorded (§6); the judges' `max_tokens`
  defaults to 1024 (built in #1010, and assumed here); runs stay in the
  repository, in `.digline/<tenant>/runs/` as today. The flow of §1 and the
  points it decides were set out by the brief that asked for this record.
  **What this record proposed beyond them is marked *decided here***, with
  the alternative beside it. Accepted as proposed, at 17:34, with the seven
  choices marked *decided here* that the report of its proposal set out,
  six in this record and one in ADR 0068. Not built yet: the construction
  is the five pull requests of §10, in an order still to be decided.
  *The first of §10's pull requests built 2026-11-19*, with Alessandro
  Prandini's rulings of that day (P-1710), each noted where it applies:
  the reviewed answer's new shape, the choice, the blind review, the rule,
  the revision, schema 25 and `OUTPUT_VERSION` 6. The agreement (2), the
  re-judge of the reviewed answers (3), the accepted contradiction (4) and
  `at_least` (5) are in no file.
  *The second built 2026-11-19*, with Alessandro Prandini's rulings of that
  day (P-1713), each noted where it applies: the agreement reading per check,
  blind and after review, held in and held out, and the composite against the
  criteria a suite declares, in `explain`, the report and `--json`. The
  re-judge (3), stability and the accepted contradiction (4), and `at_least`
  (5) are in no file.
  *The third built 2026-11-22*, with Alessandro Prandini's rulings of that
  day (P-1715), each noted where it applies: `rejudge --reviewed`, the
  comparison of two rubrics paired by name, and the type each verdict records
  so a change of type is not paired. Stability and the accepted contradiction
  (4) and `at_least` (5) are in no file
- Shipped: unreleased
- Date: 2026-11-14
- Opens: *Noted 2026-11-19, by Alessandro Prandini's ruling of that day
  (P-1710); the line below is kept as written.* **`OUTPUT_VERSION` 6 as
  well.** The line says no bump was needed, every key added to `--json` being
  an added key. Two are not: the run document's `reviewed` carried `check`,
  always a string, and `good`, always a boolean, and §1 (a) and §4 add answers
  with neither. A key a consumer has read as a string or a boolean that may
  now be `null` is a change it can see, and by the rule beside `_BASE` in
  `src/digline/wire/contract.py` that is a bump; `"reviewed": null` on those
  answers would say the case is not a reviewed answer. `revised` and
  `held_out` are new keys beside them.
  `SCHEMA_VERSION`, by keys on a reviewed answer's record in the run
  (§2, §4) and on the reference (§6), under
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1's passenger rule. No
  `OUTPUT_VERSION`: every key added to `--json` and to an MCP response is an
  added key. No `RECORDING_VERSION`, and no entry in the layout of
  `.digline/<tenant>/`. `config_hash` moves only for a suite that declares
  §7's `at_least`
- Amends, each by a dated note beside the place it amends, which points
  here, the text kept as written:
  [ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md)
  §1, *"only the judged check it names runs on it"* and `good` as the one
  verdict (§2, §4); [ADR 0066](0066-the-state-of-a-suite-and-a-review-one-answer-at-a-time.md)
  *Not decided here*, its first item, reviewing an answer that is already a
  case (§2); [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §8,
  condition 12, the contradiction that refuses a promotion (§6)
- Assumes: [ADR 0024](0024-the-judge-as-an-instrument.md) §4 (the
  calibration case) and §5 (`--judge-samples`, the judge's repeatability on
  fixed answers); [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md), the re-judge;
  [ADR 0063](0063-suggest-a-first-suite-proposed-and-never-marked.md) §3 (an
  assistant proposes into a file of its own and never writes the suite);
  [ADR 0065](0065-a-case-excluded-at-promotion-and-the-cases-a-run-was-made-with.md)
  §1, the shape of a promotion that accepts something by name with `--by`;
  [ADR 0012](0012-the-reading.md) §3, the fact list
- Touches: nothing in `CLAUDE.md`'s *fixed* section moves. Decision 3 is
  upheld: §6 accepts a contradiction only by a person's name, and §7's
  `at_least` has no default. Decision 9 is upheld: a reviewed answer's text
  and the judge's reasons stay payload, and the person's name is classified
  by the projection gate where it is built (§10)
- Number: 0067, and [ADR 0068](0068-a-judge-set-up-in-the-suite-toml.md)
  beside it. Swept on 2026-11-14 at 16:02Z across `origin/main`
  (`b3ea7e5b`), whose highest record is 0066, the fifteen branches on the
  remote, every worktree of this repository, and the one open pull request,
  #1007, a dependency bump
- Owed: the three lines on digline.dev that every new record needs

**How to read the clauses.** *Dictated* is a decision taken before this
record and transcribed. *Decided here* is this record's proposal, each with
the alternative it was weighed against, and each was accepted with the
record.

## Context

**What happened.** On an application with a judged suite, the defects that
mattered were found by the person reading the answers, not by the judge.
Bringing the judge to agree with her took four runs and a day, and the
diagnosis of each round, which answers the judge got wrong and for which
criterion, was written by hand outside digline. The sequence is as reported
from that use, in the brief that asked for this record; no file of that use
is held here.

**What digline already holds**, read at `b3ea7e5b`:

- **the reviewed answer**: an answer the application gave, a person's yes or
  no, and the judged check it is about (`ReviewedAnswer`,
  `src/digline/run/suite.py:222`). The target is never called for it; only
  that check runs on it, plus the suite's checks on the steps for an
  episode; a verdict that is not the person's fails the case, exit `1`
  (`contradicted`, `src/digline/core/reviewed.py:106`), and `promote` refuses
  the run (ADR 0002 §8, condition 12). The person's mark is the import's
  `--by`, in the case's `metadata["reviewed_by"]`
  (`src/digline/host/importing.py:908`);
- **the review, one answer at a time**, in `digline view` under
  `--allow-record` (ADR 0066 §2), for recorded answers that are not cases
  yet;
- **the judge's reason for each verdict**, kept in the run, and each
  sample's reason where a judged check's samples disagreed;
- **the re-judge** (`digline rejudge`), which judges a stored run's answers
  again under the suite as it is declared now, and re-judges reviewed
  answers from their declaration (`src/digline/run/replay.py:229`);
- **the judge's repeatability on fixed answers**, `rejudge --judge-samples
  M`, with the widest range per verdict in `judge_min` and `judge_max`
  (ADR 0024 §5; `src/digline/core/sampling.py:738`);
- **a verdict that is not firm**, the `uncertain` fact: the samples split, or
  the mean is within a margin of the threshold (built in #1010);
- **the fold**: the mean of a check's judgements against its threshold, with
  `min_agreement` as a floor, below which the verdict is `error`
  (`src/digline/core/sampling.py:237`).

**What none of it does.** It does not say how far the judge agrees with the
person before anyone tuned anything; it does not keep apart the answers a
rubric was tuned on from the ones that test it; it does not compare a rubric
with the one before it on the same answers; a person's verdict is one yes or
no about one check, so *good on everything but the tone* is four reviewed
answers or none; and a contradiction on a verdict the judge itself could not
hold steady is treated as one on a verdict it gives every time.

**The risk this record makes visible** is the one a day of tuning creates:
a rubric tuned on the same answers it is then measured on agrees with the
person by construction, and the agreement it reports says nothing about the
next answer.

## Decision

### 1. The flow, first after recording and choosing the answers

*Dictated: the five steps, and the held-out measure that decides whether
the suite is ready to gate.* The steps, with what each uses and what this
record adds:

**(a) The judge judges the new answers.** *Decided here:* the answers chosen
for review are imported **awaiting a verdict**, `record import --choose ID`,
a reviewed answer whose `good` is absent. A run judges them like any
reviewed answer: the target is not called, and the check's verdict is
written. A case awaiting a verdict is in no gate and no aggregate, and the
run says how many there are. The judge's verdict is therefore fixed in a
stored run **before the person's exists**, so nothing the person said can
have reached it, and nothing tuned since can have produced it.

*Noted 2026-11-19, by Alessandro Prandini's ruling of that day (P-1710),
the paragraph above kept as written.* **The exits.** A judge's error on an
answer awaiting a verdict is no cause of exit `2`: that answer is in no gate,
and the document says it, *"N awaiting answers were not judged"*. A run whose
only cases await a verdict is exit `2`, fixed decision 3, with a sentence
saying why: every case awaits a verdict, and nothing was judged. And **the
first press** on an answer awaiting a verdict is `digline record import
--good|--bad ID --by NAME`, which fills its verdict in place: the page shows
it as the command, and ADR 0066 §2 holds.

*The alternative not taken:* the person reviews first, as today, and the run
comes after. It is also blind, trivially, but the judge's verdict is then
produced after the person's is on disk, and a second, third or fourth run
until the two agree is indistinguishable from the first.

**(b) The person judges blind**, in the review page of ADR 0066 §2. The page
never shows the judge's verdict, score or reason for an answer awaiting a
verdict, nor any count from which one could be read. A press writes `good`,
and the suite's **review rule** above the buttons (§2) says what a yes means.

**(c) The agreement, criterion by criterion.** A reading, in `explain`, the
report and `--json` (§5 decides its shape across criteria): for each judged
check, how many reviewed answers the judge agreed with and the two
directions it disagreed in, and for each disagreement the person's verdict
beside the judge's reasons, which the run already keeps. *Decided here:* it
is read from a run made **after** (b), `digline rejudge --reviewed` on (a)'s
run (§1 (d)), at the same rubric. The two runs judged the same answers under
the same rules, so every verdict that differs between them is the judge's
own instability, read for free and carried into §3.

**(d) A rubric corrected, and a new round on the reviewed answers alone.**
*Decided here:* `digline rejudge --reviewed --run KEY` judges again the
run's reviewed answers, and nothing else, under the suite as declared now:
the target is not called and no recorded response is needed. The re-judge
then **compares the two rubrics**: which reviewed answers changed verdict,
for which check, and whether each change moved toward the person or away.
The rubric's text is part of a check's identity, so a corrected rubric is a
new identity and `diff` would read it as one check gone and one arrived. The
comparison pairs by **check name and case** instead, between a run and the
re-judge made from it, and says so in its first line: *"the rubric of
`addressee` changed; verdicts paired by name"*. It never pairs a check whose
type changed.

*Noted 2026-11-22, by Alessandro Prandini's rulings of that day (P-1715), the
paragraph above kept as written.*
- **The type is recorded on each verdict.** A run recorded a check's name
  and its identity, a digest, and nothing from which its type could be read,
  so *a check whose type changed* could not be told from two runs. From
  schema 25 each verdict carries `check_type`, the word the check is built
  from in a `suite.toml` (`llm_rubric`, `contains`, `faithfulness`, …),
  stamped by the driver beside `judged`, read through `Repeated` as `judged`
  is, and outside every identity and `config_hash`. A check digline has no
  word for, a suite's own class or a plugin's, records none.
- **Not paired, and said.** A verdict with no type recorded, which is every
  verdict of a run written before 25, is not paired: the comparison says *the
  type of the run it was re-judged from is not recorded*. A check whose type
  differs between the two runs is not paired either, a check digline names
  replaced by one it has no word for included, and nor is a name two checks
  share on one answer. No migration writes a type: absent is *not recorded*,
  and nothing is invented.
- **Where it is said.** At the end of `rejudge --reviewed`, on stderr; in
  `explain` of a run that declares `rejudged_from`, which reads the run it
  names, and in its `--json` as a tally kind, `rubrics` (ADR 0012 §3, the
  fourteenth amendment); and in the report, in a section of its own. `compare`
  is unchanged. A source the store no longer holds is said, not passed over.
- **The first line, as measured.** The sentence above, *"the rubric of
  `addressee` changed"*, says more than two runs show: a check's identity
  holds its rubric and its other settings, the judge it names among them, so
  a moved identity is a changed check, not always a changed rubric. The
  reading says *"`addressee` changed since that run, its rubric or another of
  its settings; verdicts paired by name"*.
- **Held out.** A held-out answer whose verdict changed is counted and never
  named, as §1 (e) has the reading of (c) do.
- **The round is the run's reviewed answers, all of them.** A reviewed answer
  the run holds and the suite no longer declares is refused by name; one the
  suite declares and the run does not hold is not judged, and counted. The
  run it writes declares `rejudged_from`, and ADR 0015 §7 refuses its
  promotion as written.

**(e) Held-in and held-out, and the readiness that reads only the second.**
Every reviewed answer is **held-in** or **held-out**. *Decided here:* the
role is chosen when the answer is chosen, `--choose ID --held-out`, and
recorded on the reviewed answer as `held_out = true`; the default is
held-in. The agreement reading of (c) gives the two figures apart, and
**the line that says whether the suite can gate reads the held-out figure
alone**: *"held-out: 9 of 10 agree, criterion by criterion; 23 held-in
answers served the tuning and are not counted here"*. Where no answer is
held out it says so: *"no reviewed answer is held out: the agreement above
was measured on the answers the rubric was tuned on"*.

*Why held-in by default.* A default of held-out means a person who forgets
to mark the answers she tuned on reports her tuning as a test. A default of
held-in means one who forgets reports no test at all, which the line above
says out loud. The first error is silent and flattering; the second is
loud.

*The limit, said where it applies.* The record of the role is the person's
statement. A rubric edited after reading a held-out answer's disagreement
has been tuned on it, and digline cannot see that. The reading of (c) lists
held-out disagreements **by count only**; their cases and reasons are shown
on request, `--show-held-out`, and the reading that shows them says *"read
before the rubric is frozen, these answers are no longer held out"*. A
person who reads them then moves them to held-in, by the write of §2.

*Noted 2026-11-19, by Alessandro Prandini's ruling of that day (P-1713), the
paragraph above kept as written.* **`--show-held-out` comes with the fourth
pull request of §10**, beside stability; the second gives the held-out
disagreements by count alone. One thing names a held-out answer before then,
and it is not the reading of (c): the gate's own sentence names every answer
whose judge contradicted the person, held out or not, as §3 keeps the gate
what it is today.

*Noted 2026-11-22, by Alessandro Prandini's ruling of that day (P-1715), the
note above kept as written.* **Two things name a held-out answer, not one.**
Beside the gate's sentence, the report's section *What the judge said of the
reviewed answers* names every reviewed answer and quotes the judge's reason
for it, held out or not. Both were read after the second pull request was
built, on the run its tests make. Neither is changed before the fourth, which
decides with `--show-held-out` what names a held-out answer and where. Until
then the count of the reading of (c) is not the only thing that reaches a
person about a held-out disagreement.

### 2. Two verdicts per reviewed answer, and the review rule

*Dictated: both verdicts are kept. The blind agreement is the measure of the
judge; the agreement after the disagreements were reviewed is the quality of
the suite. A labelling rule, written in the suite, says what the human
verdict judges, and the review page shows it.*

- **`good`** stays what it is: the person's verdict, given blind (§1 (b)).
  A reviewed answer written before this record is read as a blind verdict:
  nothing it carries says otherwise, and nothing can be learned now.
- **`revised`**, *decided here*, is the verdict after the person read the
  disagreements: an object with `good`, an optional `failing` (§4), `by`, and
  `at`. It is written only where the person changes her mind, never copied
  from `good`, and never removes it. Written by a second press on the review
  page, for an answer that is already a case, which ADR 0066 left undecided,
  and by the command that does the same, `digline record revise --case ID
  --good|--bad --by NAME`, so the page and the command leave one store.
  *Noted 2026-11-19 (P-1710), the text kept as written:* on an answer about
  the whole answer the command takes `--failing CHECK` too, once per check,
  as the import does (§4), since a revised no names what failed. And the
  run keeps the blind verdict beside a revision, `blind_failing` for the
  whole answer, so the blind agreement of this section is read from the run
  without moving the schema again.
- **The gate holds the newest verdict**: `revised` where it is, else `good`.
  The person's considered verdict is the expected one.
- **The reading gives both figures**, *blind agreement* and *agreement after
  review*, per criterion, with the count of revised answers between them: a
  judge that agrees only after the person revised toward it is a judge that
  persuaded her, and the gap says how often.

**The review rule.** *Decided here:* `Suite.review_rule`, a text, settable
as `review_rule` in `[suite]` and in Python, outside `config_hash` as
`capture` is. The review page shows it above the two buttons of every
answer, and `explain` quotes it under the agreement reading. A suite with
reviewed answers and no rule loads, and the page says *"this suite does not
say what a yes means"*. A rule edited after verdicts were given is not
detected by digline: the verdicts were given under the text the page showed
then, and the record of which text that was is the suite's history in git.

### 3. Stability at a fixed rubric

*Dictated: a way to repeat the run without changes and say which cases
change verdict from one run to the next; a contradiction with the person
counts only on stable cases.*

*Decided here:* a reviewed answer's verdict is **stable** when every
judgement of its check reached the same verdict: within a run, its samples
(`samples`, `Repeated`) all on one side of the threshold and none errored;
across a run and a re-judge at the same rubric (§1 (c)), the same verdict
in both; under `--judge-samples M`, `judge_min` and `judge_max` on the same
side of the threshold. Otherwise it is **unstable**. The way to repeat
without changes is what exists, `digline rejudge --reviewed --run KEY`,
which costs the judge alone, with `--judge-samples M` for more judgements
per answer. The reading names each unstable answer and its check.

**What "counts only on stable cases" means here**, decided here, and the one
place this record reads the dictation rather than transcribing it:

- **in the agreement figures of §1 (c) and (e)**, an unstable answer is not
  counted as agreeing or disagreeing; it is counted apart: *"3 answers are
  unstable and are counted in neither"*;
- **in the gate**, a contradiction on a stable verdict is what it is today:
  exit `1`, and `promote` refuses it, with no way past but a corrected rubric
  or a revised verdict. A contradiction on an unstable verdict is exit `1`
  too, and `promote` refuses it **unless accepted by name** (§6).

*The alternative, and why not:* an unstable contradiction that changes no
exit code. It would turn red runs green for every existing suite whose judge
splits, with no person deciding it: a gate loosened by a release. §6 is the
door through which a person decides it instead.

**A split below `min_agreement` is not a contradiction**, today or here: the
fold makes it `error`, unjudged, exit `2`. So the unstable contradiction of
this section is a split the floor admitted, two of three at `"2/3"`, whose
mean fell on the side the person did not choose.

### 4. A reviewed answer about the whole answer, with an expected verdict per check

*Dictated: an overall verdict, with optional expected verdicts per check
("good on everything but X"); its form, its compatibility with today's
`reviewed_answer`, and the cost of the two forms.*

**The form.** *Decided here:* `check` becomes optional.

- **With `check`**, today's form, unchanged in meaning: the person's yes or
  no is about that one judged check, and only it runs, with the steps' checks
  on an episode.
- **Without `check`**, the verdict is about **the whole answer**, and every
  judged check of the suite runs on it. `good = true` expects each to pass.
  `good = false` requires `failing`, a non-empty list of check names, which
  are expected to fail, and **every other judged check is expected to pass**:
  *good on everything but `tone`* is `good = false, failing = ["tone"]`. A
  `good = false` without `failing` is refused by name: a no about the whole
  answer that does not say which part was wrong expects nothing of any
  check, and ADR 0059 §1's amendment already refuses to guess that for the
  steps.

```json
{"id": "refund-tone",
 "reviewed_answer": {"output": "…", "input": "…",
                     "good": false, "failing": ["tone"]}}
```

`failing` names checks of the suite, each judged, refused by name otherwise,
as `check` is today. A contradiction is counted per check, with its
direction, as today. `revised` (§2) takes the same two keys.

**Compatibility with today's `reviewed_answer`.** Every file written today
carries `check` and loads with the meaning it has. Nothing is rewritten.
`record import` keeps writing `check` from the source; `--whole` writes the
form without it, and `--failing CHECK`, repeatable, gives the list.

**The cost of the two forms.** *Per reviewed answer*, the per-check form asks
the judge *samples* times; the whole-answer form asks it *judged checks ×
samples* times, four times as many in a suite of four criteria. *Per
person*, the per-check form asks one decision per answer **per check**, four
for four criteria; the whole-answer form asks one decision and, on a no, the
names of what failed. The whole-answer form is the cheaper for the person and
the dearer for the judge, and in the use this record comes from the scarce
one was the person's day.

### 5. A composite rubric against separate criteria

*Dictated: choose between a composite that reports a score per criterion,
and the tool that compares the two forms on the same reviewed answers and
says where they disagree; give the reason.*

*Decided here:* **the comparison**, and no score per criterion from a
composite.

- **What it is.** A suite that declares both forms, the composite check and
  one check per criterion, judges both on every whole-answer reviewed answer
  (§4). The agreement reading of §1 (c) then has a row per check, composite
  included, and one more line: the answers where the composite's verdict is
  not the conjunction of the criteria's, *"composite passed, `tone`
  failed"*, each named. Once a person has chosen, she deletes the other form;
  nothing in digline keeps both.
- **Why not a score per criterion from one call.** It changes the judge's
  reply from one score to several, so the parser, the check that a reason
  agrees with its score (#1010), the fold and the pairing all change: one
  assertion would produce several verdicts, and every reader of a run assumes
  one verdict per check and case. It also measures something weaker: a judge
  scoring four criteria in one reply sees its own first three scores when it
  writes the fourth, so the four are not four measurements. And it saves
  only what the composite already saves, the calls, at the price of the one
  thing separate checks give, a fall that names its criterion
  ([calibration](../calibration.md), *Choosing the judge*).

*Noted 2026-11-19, by Alessandro Prandini's ruling of that day (P-1713), the
text above kept as written.* **How a suite says which check is the composite
and which are its criteria**, which the text above leaves unsaid:
`criteria = ["a", "b", …]` on the composite check's own table in a
`suite.toml`, and `Suite(criteria={"composite": ["a", "b"]})` in Python.
- **Refused by name:** a name that is not a judged check of the suite, a
  check listed as a criterion of itself, and a check listed under two
  composites.
- **Outside every identity and `config_hash`**, as `review_rule` is: it
  changes how a run is read, not what is checked.
- **Read where?** The reading reads it from the suite the front end loaded,
  because a run does not record it. A disagreement is passed over where the
  composite or one of its criteria errored.

### 6. `promote --accept-contradiction CASE --by NAME`

*Dictated: allowed only where the samples disagreed, recorded in the
reference, and said by `compare`.*

- **Accepted only on an unstable contradiction** (§3), refused by name on a
  stable one: *"`refund-tone`'s judge contradicted the person on every
  judgement: correct the rubric or revise the verdict"*. Refused, too, for a
  case the run does not carry, as ADR 0065 §1's first limit refuses it.
- **`--by NAME` is mandatory**, never read from git or the environment, for
  ADR 0059 §1's reason.
- **Recorded in the reference** as `accepted_contradictions`, a list of
  `{case_id, check, direction, agreement, by, at}`: the direction and the
  share of judgements that went the other way, as they stood at the
  acceptance, beside `excluded_at_promotion`'s shape.
- **`compare` says it** while that reference is in force, in every front
  end, as ADR 0065 says an exclusion: *"1 contradiction accepted at
  promotion: refund-tone, `tone`, passed where the person said no, 2 of 3
  judgements, by NAME, 2026-11-14"*. **It does not carry over to a later
  run**: a later run whose verdict on that case contradicts the person is
  refused at its own promotion until accepted again. An acceptance is about
  one run's judgements, and the next run's are new ones.

*The alternative, and why not:* an acceptance that holds for later runs
until the rubric changes. It would let one acceptance stand for judgements
nobody looked at, and a stable contradiction arriving later would hide under
it.

### 7. At least k of n

*Dictated: a threshold "at least k of n" for a judged check with samples,
beside the mean; its form in TOML and in Python.*

*Decided here:* `at_least`, on a judged check and on `Repeated`, written as
a count: `at_least = "2/3"` in TOML, `at_least="2/3"` in Python, the form
`min_agreement` already takes. With it, the check passes when at least k of
its n judgements each reached its threshold, and the mean is still written
and still read by `compare`'s tolerance. `n` must equal the number of
judgements the check gets, *samples × repeats*, and a mismatch is refused at
load, naming both. No default: a check without it folds by the mean, as
today.

- **Identity**: untouched, as `threshold` is untouched: it is how a result
  is judged, not what is checked, so a run before and after it still pairs.
- **`config_hash`**: it joins, as `threshold` does, so a reference is not
  promoted across it. Appended only where declared, the pattern
  `floor_standard_errors` follows, so no existing hash moves.
- **The verdict** records `at_least` in its metadata beside `scores`.

*Why not the six-decimal threshold that works today* (the
[declarative](../declarative.md) page measures `0.666667` for two of three):
it is exact only for a judge that answers 0 or 1, and reads as a mean to
anyone who did not write it.

### 8. The judge declared in a `suite.toml`

Decided in [ADR 0068](0068-a-judge-set-up-in-the-suite-toml.md), apart,
because it amends what ADR 0007 §3 rules for every judged check and not the
flow.

### 9. What stays out

*Dictated.*

- **No automatic change to a rubric.** An assistant may propose one, as
  `suggest --assist` proposes a suite: into a file of its own, from the
  disagreements of §1 (c), and never into the suite, as ADR 0063 §3 rules
  for `suggest`'s file of proposal. The
  rubric the gate uses is written by a person.
- **Nothing through MCP beyond reading.** The agreement reading, the
  stability and the comparison of rubrics are read through the MCP server's
  existing tools, as facts; the choice of answers, the verdicts, the revision,
  `--held-out` and `--accept-contradiction` are not reachable there.
- **The judge never sees the person's verdict**, nor whether an answer is
  held out, nor the review rule: what reaches the judge is what reaches it
  today, the rubric, the input, the context and the answer.

*Decided here, beside them:* no verdict the person gave is ever inferred
from the judge's, and no held-out answer is chosen by digline.

### 10. The alternatives not taken, compatibility, and the plan

**Alternatives not taken**, beyond those beside each section:

- *A calibration command of its own*, `digline calibrate`, running the five
  steps. It would hide the stored runs each step reads, and a step that is a
  run can be read, compared and re-judged like every other.
- *Held-out chosen at random by digline.* A random split is honest only once
  the answers exist; the person who chose them knows which ones are the
  cases she wants tested, and the default of §1 (e) makes an unchosen split
  loud.

**Compatibility.** By `RELEASING.md`'s *Choosing the version*, a minor:

- `ReviewedAnswer` gains optional fields (`failing`, `revised`,
  `held_out`), and `check` and `good` become optional on load under the
  rules of §1 (a) and §4. No signature breaks: each field has a default that
  means what a reviewed answer means today.
- `SCHEMA_VERSION` moves: a reviewed answer's record in the run, `Reviewed`,
  carries the verdict the gate held, whether it was revised, `held_out`, and
  the checks expected to fail; the reference carries
  `accepted_contradictions`. The migration step invents nothing: absent is
  *a blind verdict, held-in, about its check, nothing accepted*.
  *Noted 2026-11-22 (P-1715), the item kept as written:* and each verdict
  carries `check_type`, the type its check was declared with (§1 (d)). The
  step invents nothing for it either: absent is *not recorded*.
- `config_hash` moves only for a suite that declares `at_least`. No
  assertion identity moves.
- New options: `record import --choose`, `--held-out`, `--whole`,
  `--failing`; `record revise`; `rejudge --reviewed`; `promote
  --accept-contradiction`; `explain --show-held-out`. A new key in `[suite]`,
  `review_rule`, and one on a judged check, `at_least`.
  *Noted 2026-11-19 (P-1713), the item kept as written:* and a second on a
  judged check, `criteria`, which names a composite's criteria (§5). It is
  outside `config_hash`, so the line below on `config_hash` holds.
- **No exit code changes for a suite that declares none of it.** §3 leaves
  every exit as it is today.

**The plan, in five pull requests at most**, each with what it measures and
the friction it closes:

1. **The reviewed answer's new shape and the blind review.** `failing`,
   `revised`, `held_out`, `--choose`, `review_rule`, `record revise`, the
   review page's second press and its rule; the schema. *It measures*: an
   answer awaiting a verdict is in no gate and is never shown with the
   judge's verdict; a press and the command leave identical stores; today's
   files load unchanged; *good on everything but X* expects what it says,
   check by check. *It closes* the four reviewed answers needed for one
   person's verdict about one answer, and the verdict changed in place.
2. **The agreement reading.** Per check, blind and after review, held-in and
   held-out, unstable apart, the composite against its criteria, in
   `explain`, the report and `--json`. *It measures* each figure against a
   count made by hand on a fixture of known verdicts, with a mutation per
   figure. *It closes* the diagnosis written by hand outside the tool, and
   the agreement reported on the answers the rubric was tuned on.
   *Noted 2026-11-19 (P-1713), the item kept as written:* *unstable apart*
   waits for the fourth, which measures stability. Until then the reading
   says that no answer is set apart, because none is measured.
   `--show-held-out` moves to the fourth as well (§1 (e)).
3. **A new round on the reviewed answers alone.** `rejudge --reviewed`, and
   the comparison of two rubrics paired by name. *It measures* that no target
   is called, that a rubric edit is paired and named, and that a change of
   type is not paired. *It closes* the four full runs of a day, where one
   round per rubric on the reviewed answers was what was needed.
4. **Stability and the accepted contradiction.** The stable and unstable
   reading, `promote --accept-contradiction`, its record in the reference,
   and `compare`'s sentence. *It measures* the acceptance refused on a
   stable contradiction and taken on an unstable one, and that it does not
   carry to a later run. *Noted 2026-11-19 (P-1713):* and
   `explain --show-held-out` (§1 (e)). *It closes* a contradiction that a judge which
   cannot hold its own verdict makes unpromotable for ever.
5. **`at_least`, and ADR 0068's judge.** *It measures* two of three passing
   and one of three failing at `"2/3"`, `n` refused when it does not match,
   and the hash unmoved for a suite without it. *It closes* the threshold
   that reads as a mean and is exact only for a judge that answers 0 or 1.

## Consequences

A person's work on a judged suite has a shape digline can read: answers
chosen, judged by the instrument before she says anything, judged by her
without seeing it, compared check by check, corrected one round at a time on
the answers she reviewed, and tested on answers she set aside. The figure
that decides whether the suite gates is one nobody tuned toward.

The run document carries more about a reviewed answer, and the reference can
carry a person's acceptance of a contradiction, which compare repeats for as
long as it stands.

## Not decided here

- How a projected reference carries `by` in `accepted_contradictions`, and a
  revised verdict's `by`: the projection gate classifies them with the change
  that builds them, as ADR 0065 left its own `by`. The proposal is a token.
- Which schema train the keys ride: the cut's, by ADR 0014.
- A target-answered case's review. This record reviews recorded answers, as
  ADR 0066 does.
- Whether a suite may declare that it gates only once a held-out agreement
  is reached. The line of §1 (e) says the figure; holding a gate on it is a
  later decision.
