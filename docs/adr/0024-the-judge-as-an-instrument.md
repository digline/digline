# ADR 0024 — The judge as an instrument

- Status: proposed — the text first, checkpointed before any code, the way
  [ADR 0020](0020-the-reading-across-runs.md) and
  [ADR 0022](0022-the-declared-price.md) were
- Date: 2026-09-16
- Amended: 2026-09-17 — evidence added to the Context, no decision revisited:
  **a miss of the house's own, in pilot-zero's fourth cycle.** Its judgment
  layer told the reader to look at the model first, on a dossier whose own
  facts had already ruled the model out. It had been handed `AGENTS.md` §3's
  likelihood order, which was never measured, and across four cycles it
  answered the same shape both ways. Whether that order should be measured is
  left open. The canary, which had ruled the model out, is the motivating case.
  The run-to-run spread is recorded as a finding against §7.1's aggregate-only
  scope: a suite-level reading stays inside the noise while one case alternates
  underneath it. §7 is unchanged
- Amended: 2026-09-17 — §4, what building the calibration case found, in
  §4.8. Four places where the code resisted the text, each ruled at a
  checkpoint rather than decided in the code: a calibration delta is out of
  `counts` and `worse` (§4.4's `Headline.counts` row was the canary's, copied);
  `Calibration` gains `input` and its refusal (§4.2); the §4.2 refusal reads the
  `KIND` that 0.13.3 already ships, and §6.1 is left to shape; and §9's bump
  boards one passenger first, which leaves 12 an open train
- Amended: 2026-09-17 — §5, what building `judge_samples` found, in §5.5. Four
  rulings the text left open: the verdict records the first judgement; the
  bounds are the widest answer's own, with a tie rule; an errored judgement is
  counted, not escalated; and the sentence belongs to `rejudge` alone.
  `Run.judge_samples` boards schema 12 second
- Amended: 2026-09-17 — §6.1, in §6.4: the scale is `KIND`'s. `AssertionBase.scale`
  is not added; shape's passenger is `Verdict.judged`, written only when true,
  and it boards schema 12 third, which fills the train. Undeclared is announced
  and never guessed, which makes `KIND` optional but no longer unread, and
  `FromAutoevals` is named as the known hole in the reading
- Amended: 2026-09-17, after the 0.14.0 release — §4.7, what the delta-pass
  found. The calibration answer's *fields* are never written, and a judge's own
  reason may still quote them inside the perimeter. The promise is corrected,
  not the reason scrubbed. Nothing crosses a boundary
- Amended: 2026-09-17, after the 0.14.0 release — §6.2, what the delta-pass
  found. A `Repeated` check in a sampled suite stores per-answer means, not its
  judgements, so shape reads a fold there and cannot tell. The limit is stated
  now, and the fix — a stamp, left out and counted — is ruled onto the next
  schema bump as its first passenger
- Amended: 2026-09-17 — §6.2's stamp, in §6.5. The fold of folds happens in
  three places, not one (a nested `Repeated` at suite `samples=1` included), so
  it is stamped in `combine_samples`. The key is `"sample_means": true`, on
  `Score`, written only when true. It boards schema 13 second. The migration
  writes nothing, and absent means *not stamped*, never *judgements*; the
  reading carries that difference by pairing, and names the one residue it
  cannot reach
- Amended: 2026-09-22 — §7.4, and this one **withdraws a pending decision
  instead of taking it.** The floor on N was measured on scout's first kept
  operator history — twelve runs, four days, one `config_hash`, eight
  comparable — and no floor exists: a min–max range is monotone in N, so it
  cannot converge and *outside* reports a value not seen before rather than a
  change, observed at 4 of 12 readings at N≥6 with every firing becoming the
  next reading's new high. The clause is withheld **because the range describes
  and cannot gate**, not because a number is missing; the range stays as the
  reading, on §7.3's own reasons, which are reasons for describing. A
  statistic that converges is named as the open door and left as its own
  decision. Three findings ride along — a floor could not be one number across
  aggregates whose denominators differ by 7×, the effective N grows at 67% of
  the cycle count, and §7.3's between-vs-within reproduces with the between-run
  range the narrower on three of four. The reading's exclusion clause is
  repaired in both locales: it elided its verb after the first reason and
  printed a fragment on the real store
- Amended: 2026-09-22 — §7.5, the distinction it ruled without stating. It made
  the spread **silent** in three places and never said what silence prints, and
  the section's heading is unconditional, so silence printed whatever sentence
  was already there. `log.spread` is empty for four reasons — no run read, the
  suite declaring no run-level check, every aggregate flipped, every aggregate
  scoreless — and only the second is a fact about the suite, while it was the
  sentence printed for all four. Silent on a flip means **do not report a
  range**, not print nothing: naming the flip is not printing an interval. Four
  sentences for four facts, counted by cause the way §7.2 counts exclusions,
  both sentences where both hold, and `declares_none` keeps its own wording
  because it was the only one that was ever right. `--json` gains
  `spread_absence`, an added key
- Amended: 2026-09-22 — §1, the frame, **demonstrated on a real suite for the
  first time and in the direction this record did not argue.** brief's
  `brief-reason` suite ran the calibration case and `judge_samples` together on
  21 cases: the judge's range on a *fixed* answer reached **1.000** with 13 of
  21 cases ranging 0.5 or more, while the calibration case scored **0.500** five
  times out of five inside its 0.30–0.70 band. §1 argued the pairing one way —
  repeatability alone would call a collapsed judge stable. This is the converse:
  repeatability alone called an intact judge broken. No decision is revisited;
  the argument is now bidirectional, and one bullet of §1 was weaker than the
  data
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states, and an error
  is neither green nor a regression);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §4 (a judge
  that moved is louder than a target that did), §9 (what the provider *said*
  answered);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §1 (what is repeated
  is the target's answer, and repeating the judge was left open), §2 (the
  scalar stays the mean), §5 (the interval is the baseline's), §6 (a flip
  carries no interval), §7 (the aggregate's own interval);
  [ADR 0008](0008-the-two-run-report.md) §2 (the exit code is the contract);
  [ADR 0012](0012-the-reading.md) §3 (the fact list is closed), §5 (no advice,
  and no multi-run vocabulary in `explain`);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §6 (a replay
  declares itself), §7 (a replay is not promotable);
  [ADR 0016](0016-the-canary-case.md) §1–§7 (the case that watches rather than
  measures, whose shape the calibration case borrows);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §3 (the cause lives in the
  journal);
  [ADR 0020](0020-the-reading-across-runs.md) §3 (the absences), §4 (the row
  has no score), §5 (`log` is never a gate), §7 (aggregates in `runs_json`)
- Amends: [ADR 0020](0020-the-reading-across-runs.md) §4 — one dated sentence:
  a reading may group runs by identity and read their aggregates; identity
  decides which runs are grouped, scores never decide identity (§7);
  [ADR 0012](0012-the-reading.md) §3 — the closed `TallyKind` list gains
  `calibration` (§4) and `shape` (§6), each with the sentence that earns it;
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §6 — a
  calibration case needs no recorded answer to be re-judged, because it carries
  its own (§4)
- Turns into surface: [`AGENTS.md`](../../AGENTS.md) and the
  `operating-digline` skill gain rule §9 (§3); `digline rejudge
  --judge-samples` (§5); `digline log`'s spread section (§7); `docs/api.md`
  (`Calibration`, `AssertionBase.scale`); `docs/explain.md`, `docs/log.md`,
  `docs/rejudge.md`; `pytest-digline` (§4)
- Touches: fixed decision 3 is upheld and applied to the instrument — a
  calibration band that contains an extreme cannot detect the one thing it
  exists for, and is refused (§4); a judge's repeatability printed without its
  scale is the same vacuous green in a new place (§5). Decision 9 — the
  calibration case's fixed answer is payload and never enters the run document;
  what travels is numbers and one declared word. Decision 2 — the spread is a
  fact about *this store*, read where the store is, and never a property of a
  document (§7)
- Requires: `SCHEMA_VERSION` 11 → 12 for two passengers, both checked against
  ADR 0014 §1 in §9; no `OUTPUT_VERSION` (added keys only); no `config_hash`
  change for any suite; no baseline re-promoted
- Number: 0024. 0023 is claimed by capture on its branch

## Context

digline measures the system under test, and it treats the judge as a given.
Where the judge is concerned it records two things today: what the judge *was*
(`judge_config`, ADR 0005 §4 — a judge that moved makes every score less
comparable) and, through `Repeated`, how much one check's judgement wobbles on
one output. ADR 0006 §1 said so in as many words: whether a rubric should be
asked several times, and what its own noise floor would mean, was deliberately
left open.

An instrument needs measurements of its own. This record names four, and it
names them together because each is blind exactly where another sees.

### Two signals, and what they are not

**An r/Rag thread, 2026-09-16.** The author of a RAG over 27 books described
what a grading script surfaced on real data. The source is recorded in the
working material rather than reproduced here, as ADR 0015 did with its own
Reddit signal. Two findings, both as the author reported them and neither
verified here:

- The two controls — one answer that must pass, one that must fail — stayed
  fine while the mean moved from 0.77 to 0.97, and the distribution behind that
  mean was 202 answers at exactly 1.00 and 6 at 0.00. The judge had gone binary.
  Two poles are structurally blind to that: a binary judge passes both forever.
- The grading prompt fed the judge 600 characters of passages averaging 1,100.
  Faithfulness went from 57.6% to 82.1% by changing that one number. No amount
  of repetition would have found it: the error was configuration, identical on
  every call.

**Dan Luu, "Agentic test processes, LLM benchmarks…" (danluu.com/ai-coding),
the same day.** Two points as the reconnaissance summarised them: a summary
number is meaningless without the distribution behind it; and in his data one
standard deviation between runs of the *same* model exceeded the gap between
the best and worst conditions he tested — the delta being celebrated was smaller
than the measurer's own noise.

**The caveat, stated before the design.** That is two signals in one day, and
**neither comes from digline's own data.** They are independent of each other
and of this project, which is what makes them worth a record; they are not a
measurement of any suite digline runs. The house's own dogfood can test only
part of what follows:

- **scout can size the spread and cannot size the shape.** Its checks are
  binary per sample (`AgreesWithMark`, `AgreesOnComment`) and its aggregates are
  real, so it has a run-to-run spread to read and no judged scale to lose.
- **scout cannot size the spread on the material it holds today either** — §10
  says why, with the numbers. The instrument is designed here; its two
  thresholds are measured later, on data this record does not have.

### A miss of the house's own

*Amended 2026-09-17. Evidence only: nothing under Decision moves.*

The two signals above come from outside. This one comes from digline's own
dogfood, and it is a miss rather than a signal. Read from the artifacts of
pilot-zero's four cycles on scout (2026-09-14 to 2026-09-16): the alert, its
`cycle.json` and the decision. The run documents of the first three are gone,
for the reason §10 gives, and the fact lists in `cycle.json` are what survived.
Case identifiers are slugged from post titles and stay out of this record, as
ADR 0021 §7 rules for the ledgers.

**What layer 3 said.** In cycle 4, three runs at three seeds each regressed one
case's `agrees_on_comment`, from its reference 0.6 to 0.4, 0.0 and 0.0. The
dossier's judgment layer, the one part of the alert a model writes, opened with
*"The model moved"* and closed with *"Look first at the model: the
comment-agreement pattern is too consistent across seeds to be pure noise"*.

**It is wrong on two counts, both inside the same document:**

- **Layer 1 had already excluded it.** Rendered from `digline explain --json`,
  it read: *"The suite itself did not change. Underneath it, nothing differed:
  not the system under test, not the judge, not a file under test."* The
  same line refuses layer 3's third hypothesis, a subtly changed prompt under
  test, since the prompt is a file under test.
- **The canary had not moved.** None of the three runs carries a `canary`
  fact, and `explain` emits one only when `canary_moved` holds (ADR 0016).
  The canary is the instrument that exists to answer *is this still the same
  model*, and its answer was in the evidence and unread. *The model moved* was
  ruled out inside the cycle, by the case built to rule it out.

**The cause is structural, not a bad sentence.** Layer 3 is handed one cycle
and has no memory. The cycle before this one, cycle 3, was a single run that
exited 0, and the same case had no fact in it at all. `explain` omits an
unchanged check whose score did not move, so the case was back at 0.6 on its
own. A model that moved does not heal overnight. Over the four cycles the case
read 0.0, 0.2, 0.4; then 0.0, 0.4, 0.0; then 0.6; then 0.4, 0.0, 0.0. That is an
alternation, not a step, and no single cycle can show it.

**The order it was handed is a house rule nobody verified.** Layer 3's system
prompt asks it to say what it would look at first: *"the model, the judge, the
prompt, the dependency floor, in that order of likelihood"*. That sentence is
not an implementation slip in the operator. It is `AGENTS.md` §3, word for word,
copied into the prompt, the skill and the dossier's own drift sentence. It is
an a priori: the house wrote it and never measured it. Across the four cycles,
under the same prompt, it lost twice and won twice. Cycles 1 and 2 put the judge
first, and cycles 3 and 4 put the model first. The only attribution with numbers
under it points at the judge: in cycle 1 this case's measured floor spanned
0.0–1.0 across five samples, and scout's policy holds the case as one the judge
cannot score, with the rubric investigation still pending. Four cycles do not
condemn the order. They show it inconsistent with the one attribution that has
been measured, and that is why what follows is a question and not a decision:
**is an opinion steered by a declared likelihood order still an opinion, or is
the order itself something that should be measured?**

**A memoryless layer 3 is not merely incomplete; it is unstable.** Cycles 2 and
4 had the same shape: this case regressed at all three seeds, and the policy's
hold on it was in the evidence both times. Cycle 2 answered *"That pattern
points to the judge, not the model or prompt."* Cycle 4 answered *"The model
moved."* Cycle 1 contradicts itself inside one answer. It says *"Look at the
judge first"*, and closes with *"The model, not the system under test, is
drifting."* A reading that gives opposite answers to the same shape cannot be
corrected by handing it more of the same cycle.

**What that makes it evidence for.**

- **The canary**, whose shape §4's calibration case borrows. It is the
  motivating case here. The measurement existed, was correct, and was not read.
- **The run-to-run spread, as a finding against its own scope, and not as
  support.** §7.1 reads aggregates only, and across the same ten runs the
  aggregates did not follow the case. Accuracy read between 0.860 and 0.889,
  and was `unchanged` against its reference in every run, including the ones
  where the case fell to 0.0. The spread as §7 specifies it would have said
  *inside the noise* and been right about the suite. It would still have said
  nothing about this case. **Inside the noise at suite level does not imply
  inside the noise at case level**, and a case that alternates can stay
  invisible to any aggregate reading. §7.2 would also have dropped two of the
  ten runs, cycles 2 and 4 at seed 0, each with one unjudged case.

**Why §7 does not become per-case here.** Per-case spread is what this miss
motivates, and it is not wanted today. On scout it would be 145 cases × 4
checks, 580 ranges in one reading. A reading that long is not read row by row.
It is read through a summary, whether a person's or layer 3's, and that summary
is the one §7.1 refuses to invent. If a per-case spread is ever proposed, this
cycle is its motivation, and the proposal owes an answer to that objection
first.

## Decision

### 1. The frame: four measurements, and why together

|  | one known point | the whole suite |
|---|---|---|
| **noise** | repeatability — `judge_samples` (§5) | run-to-run spread (§7) |
| **scale** | the calibration case (§4) | shape (§6) |

The axes are not pure, and saying so costs nothing: `judge_samples` on a replay
isolates the judge, while the spread mixes target, judge and time. What the
table does hold is the argument for one record instead of four:

- **Repeatability is blind to collapse, and worse than blind.** A judge that has
  gone binary is *more* repeatable: 202 answers at 1.00 every time is a spread
  of zero. Printed alone, a repeatability figure would call the broken judge
  perfectly stable — the most reassuring sentence the instrument could produce,
  and the most wrong.
- **The calibration case sees collapse at one point** and is blind to noise,
  which its band absorbs, and to the population around that point.
- **And it reads the other way too, which this list under-argued until it was
  measured.** The bullet above says repeatability alone would call a broken
  judge stable. The converse is that repeatability alone calls an *intact* judge
  broken, and that is the case that actually occurred first. See the
  demonstration below.
- **Shape sees the population** and cannot tell a judge that lost its scale from
  a target that genuinely improved: 0.77 → 0.97 could have been either. The
  calibration case is what separates them — the shape moved and the calibration
  held means the target moved; the shape moved and the calibration landed at an
  extreme means the scale went.
- **The spread sees time** — provider weather, a silent roll, a dirty commit —
  and is blind inside one run, where the other three live.

#### The pairing, demonstrated (2026-09-22)

The first suite to run two of these four together. brief's `brief-reason` —
21 cases, a `Faithfulness` check over the one-sentence reason its digest prints
under each article title, judged by Haiku over the same two prompt files the
target is given.

| measurement | reading |
|---|---|
| `judge_samples 3`, on a replay | the judge's range on one **fixed** answer reaches **1.000**; 13 of 21 cases range 0.5 or more; not one case had its three judgements agree |
| the calibration case | **0.500**, five times out of five, inside its declared band 0.30–0.70, with five reasons that all named the same claim as the unsupported one |

**Read alone, the first is an instrument coming apart.** A range of the whole
scale, on an answer that did not move, is the reading you would stop a release
over. The calibration case says the opposite and says it without ambiguity: the
scale is intact, sitting exactly where a half-right answer belongs, and steadier
than any real case in the suite.

**What the range is measuring is the denominator, not the scale.**
`Faithfulness` asks for two counts and divides, and `total` is the judge's own
decision — the structural noise its own docstring warns about, here with a
number beside it for the first time. The suite's sentences are genuinely
ambiguous to decompose: *"rilevante per RAG in produzione"* is one claim or two
depending on the reading, and a denominator of 2 that becomes 3 moves the score
by 0.17 with the sentence untouched. The calibration answer is not ambiguous —
two claims, one supported, nothing to read two ways — and its range is zero.

So the two readings are not in tension and neither is wrong: **the instrument is
intact and the question is ambiguous.** That is a third state neither
measurement names on its own, and §1's table is what makes it readable. This is
the first time the material has said so rather than the text.

Two consequences, neither decided here. The five-sample fold already suppresses
0.5 of per-answer range to **0.073** of per-case movement between two judgings
of the same answers — so §5's isolation measures something real that the fold
then mostly absorbs, which is why a suite carrying this much instrument noise
gates usefully at all. And the repair for a case that does chatter is
`Repeated`, not a wider tolerance: the ambiguity is in the question, so it is
answered by asking more times, not by caring less.

### 2. The order, which is the order of this record

1. **The method rule** (§3). It costs nothing, and it comes before all four: it
   is the configuration check no measurement replaces.
2. **The calibration case** (§4) — the gate, and it needs no reference.
3. **`judge_samples`** (§5), which must report the calibration result beside
   the variance it measures.
4. **Shape** (§6) and **spread** (§7), whose thresholds are **measured later**
   and are not set in this text. What ships first is the measurement; the
   sentence that judges it waits for data.

### 3. Before any measurement: read what the judge reads

`AGENTS.md` and the skill gain one rule. It is numbered §9 and not inserted
earlier: `tests/test_agents.py` holds the two files to the same numbered
headings, and renumbering would break every reference to "`AGENTS.md` §3" and
"§6" already written into ADR 0016. §3 and §4 gain one pointer each — §3's
"in that order of likelihood" and §4's "look at what they have in common".

> ## 9. Read what the judge reads before measuring how it moves
>
> Before you spend anything on how much a judged score moves — re-runs,
> samples, a `Repeated`, a re-judge — print one rendered judge prompt per judged
> check, in full, and read it against its sources. Check that the context is the
> whole evidence the case is meant to be judged on and not a prefix of it
> (compare what was sent with what was retrieved, by length), that the rubric is
> the one the suite declares, and that the output is the answer rather than a
> wrapper around it.
>
> Repetition measures noise and nothing else. A judge shown 600 characters of a
> 1,100-character passage gives stable, repeatable, wrong scores, and no number
> of samples finds it: the error is configuration, identical on every call. One
> RAG author's faithfulness went from 57.6% to 82.1% by changing that one
> number.
>
> A run does not keep what the judge was sent — it records the input and the
> answer, not the context or the prompt — so this is done live, in a scratch
> script: wrap the judge in a function that prints its prompt and delegates. Not
> in the committed suite, where the wrapper changes the check's identity. The
> prompt is payload: to your terminal, never into a report, a commit or a pull
> request.

**Where the truncation lives, and why digline cannot see it.** digline cuts
nothing it sends a judge: `judge_prompt()` joins the sections whole. The context
is built by the suite's *mapper*, which is the user's code, is in no hash, and
is identified in a run only by `git_commit` — commonly `-dirty`. That is where
a 600-character slice sits, and it is why this is a rule for a person and not a
check in the engine: the engine would have to guess what "the whole evidence"
was.

**The gap, named and not closed here.** Even with `record_responses=True`, a
stored run cannot answer *what was this judge shown?* Recording the rendered
judge prompt is payload of the most sensitive kind — the context is the end
company's documents — and it is a separate decision under ADR 0015's rules.

### 4. The calibration case

**The canary watches whether the model is still that model; the calibration
case watches whether the scale is still a scale.**

#### 4.1 It is a fixed answer, not a flag on a generated one

A canary asks the target. A calibration case cannot: its whole premise is an
answer **known** to be partially correct, and an answer the target generates
today is not known. So the target is not called for it, and the judge grades an
answer the author wrote.

The mechanism already exists in one place. `Replay` (`digline/run/replay.py`)
is a target that answers from stored data and still passes through the suite's
mapper. A calibration case is a **one-case replay inside a live run**: the
driver builds the `Response` from the declared answer and hands it to the
mapper like any other. That the mapper is on the path is not incidental — it is
where `EvaluatorInputs.context` is built, and so where a truncation like §3's
would sit. A calibration case exercises the judge path the real cases use.

#### 4.2 The declaration

    Case.calibration: Calibration | None = None

    Calibration:
        output:  Output          # the known, partially correct answer — payload
        check:   str             # the name of the judged assertion it calibrates
        low:     float           # the band, inclusive at storage precision
        high:    float
        input:   str | None = None   # amended 2026-09-17, §4.8 — payload

Flag-shaped in how it is treated — §4.4 is ADR 0016 §2's table — and
declaration-shaped in what it carries, because the band and the answer are the
case's content and a `bool` cannot hold either.

It is case data, outside `config_hash` under ADR 0014 §1, as the canary is, and
it rides the declarative form: `calibration = { output = "…", check =
"faithfulness", low = 0.3, high = 0.7 }` in a cases file.

**Refusals at construction**, each cheaper met as a sentence than as a number:

- **Not a canary.** One watches the target and the other bypasses it; a case
  that is both is a case that asks the target and does not.
- **No `group`, no `label` required** — ADR 0016 §1's two refusals, for the
  same reasons: it is in no aggregate.
- **`0 < low <= high < 1`**, compared at storage precision. A band that contains
  0 or 1 counts an extreme as in band, so it cannot detect the one thing it
  exists for — fixed decision 3, applied to the instrument.
- **`check` names an assertion the suite declares, and that assertion declares
  `scale = "judged"`** (§6.1). A calibration of a deterministic check is a
  calibration of arithmetic.
- **`samples >= 2`** on a suite that declares one, refused at
  `Suite.__post_init__` in ADR 0016 §6's shape. On this case the target is not
  called, so `Suite.samples` repeats the *judge* alone — and a single judgement
  landing outside the band on a noisy judge is a red light nobody chose. The cost
  is lower than the canary's: judge calls only.

Whether an answer is a good calibration answer — four claims, two supported; a
reply that satisfies half a rubric — is the author's craft. The engine does not
check it, for the reason ADR 0016 §1 gives.

#### 4.3 What runs on it

**Only the named check.** Every other assertion is skipped for this case the way
a suspension skips a case: in the driver, not in the core (ADR 0001), and
recorded rather than hidden. This is not tidiness. `CostBudget` and
`LatencyBudget` read `cost_usd` and `latency_ms`, which a call nobody made does
not have; `ToolsCalled` reads a trajectory nobody produced. Run on this case,
each would error, and every suite with a budget and a calibration case would
exit 2 on every run for a reason that has nothing to do with the judge.

#### 4.4 Excluded from metrics, included in everything that reports

ADR 0016 §2's table applies row for row — excluded from every aggregate and
per-group aggregate, left out of `per_sample_outcomes`' length check (the §4
trap, which a calibration case walks into exactly as a canary does), counted in
`run_tally`, `Headline.counts` and every delta table — with three differences:

| site | canary | calibration case |
|---|---|---|
| `planned_calls` / `CallPlan` | target calls counted | **target calls not counted**; judge calls counted — the announced bill has to match the invoice |
| the checks that run | all of them | **the named check only** (§4.3) |
| `Matrix` | `canary_excluded` | `calibration_excluded`, beside it, silent at zero |

*Amended 2026-09-17 (§4.8): the calibration case is counted in `run_tally` and
kept in every delta table, and it is **not** counted in `Headline.counts` or in
`worse`. The row above was the canary's, copied without noticing that the canary
measures the system while the calibration case measures the instrument.*

#### 4.5 When it fires, and what it produces

It fires when the check's recorded score for the case — the folded mean, which
is what every other verdict is judged on — lies **outside `[low, high]`** at
storage precision. An errored verdict on the case does not fire it: that is
unjudged, and already exit 2.

It produces a run-only fact, `scale_lost(run) -> tuple[...]`, a pure function in
`digline.report` beside `unjudged_cases(run)` and read wherever that one is
read — including the two places a run is read **without a reference**:
`explain` in `host/reading.py`, and `report` in `cli/main.py`'s
`_report_single`. It needs no baseline because it compares a score with a
declared band, not with a past. A first run can be stopped by it.

**Exit 2, and why not 1.** ADR 0016 §5 kept the canary off exit 2 because a
changed model is an answer. A lost scale is the other case: the numbers exist
and are not measurements. `AGENTS.md` §6 defines 2 as *the run could not be
judged, and nothing downstream of it is meaningful, including any conclusion you
were about to draw from the green checks beside it* — which is the consequence
of a lost scale, word for word.

It is **not an errored verdict.** The score is real, it is the evidence, and it
has to stay visible. So `Headline` gains `scale_lost: bool`, and
`wire.exit_code()` returns `EXIT_UNJUDGED` when it or `unjudged` holds.

**Precedence is a choice, and this record makes it.** Nothing forces it: a run
can carry both facts — a check that got worse and a calibration case outside its
band — and one number has to be returned. **1 is returned before 2**, as it
already is for a regression beside an unjudged case, and **the calibration
clause leads the headline regardless** of which code is returned (§4.6).

The other choice was available and was weighed. A collapsed judge can
manufacture a flip, which argues for 2 first. It loses on two counts: a lost
scale disqualifies *judged* checks, while a regression on a binary check beside
them is still true and still the louder fact about the system; and both codes
stop a pipeline, so the precedence decides only which word the pipeline reads,
while the headline has already told the reader which fact is the instrument's.
Keeping 1 first also leaves `wire/contract.py`'s stated rule as it is.

**Not promotable** — the fifth condition, beside tenant, configuration, errored
verdicts and replay: `UncalibratedRunError`. A baseline scored by a judge that
has gone binary is a reference that makes §6 blind for as long as it stands.

**Not a draw.** `AGENTS.md` §3's one exception gains a sibling, for the canary's
own reason: running it again asks the same judge the same thing.

#### 4.6 The sentence, and where it sits

One clause, **first** in the headline — before the counts, not only before the
canary. ADR 0016 §7 already says *a moved scale makes even the canary's own
numbers less comparable*, and a reader who learns the scale is gone after
reading "2 checks got worse" has already believed the 2.

> the calibration case `half-supported` scored 1.000000 across 3 samples
> (1.000000, 1.000000, 1.000000), outside its declared band 0.300000–0.700000:
> the judged scores in this run are not placed on the scale they are compared on

No *likely*: that word is the canary's (`tests/_vocabulary.py`), and nothing here
is inferred — the band was declared and the score was observed. No advice word,
under ADR 0012 §5's gate. The raw samples are printed because *every one at an
extreme* and *a mean just outside the band* are different pictures, and the
reader is owed which one it is without a second sentence to choose between them.

#### 4.7 The front ends, and the replay

- **`explain`** gains `calibration` — ADR 0012 §3's closed list, amended by that
  section's own test: the report says it, and a reading that omitted it would
  describe a run whose exit code it could not account for.
- **The wire** gains `scale_lost` on the headline and `calibration` on each
  delta. `OUTPUT_VERSION` stays 1.
- **`pytest-digline`**: the calibration case's item is **ERROR** with the
  sentence, which is the plugin's unjudged state; other items are unchanged. It
  ships in the plugin release that follows, with its floor raised.
- **A replay** re-judges a calibration case from the case's own answer, not from
  the stored run: ADR 0015 §6's second refusal (*a case has no recorded answer*)
  does not apply to a case that carries one. The answer is never recorded into
  the run, recorded responses or not — it is in the committed cases file already,
  and a second copy under `runs/` is a second record of the same payload.

*Amended 2026-09-17, after the 0.14.0 release, by its delta-pass. The sentence
above promised more than the house has promised anywhere else, and it is
corrected rather than enforced. **The fields are never written**: no
`output`, no `input`, no `responses` entry, recorded responses or not, and that
holds. **A judge's own `reason` may quote them inside the perimeter, as any
reason may quote any answer.** The scored path does not carry one — a
calibration case samples at least twice, and the fold replaces the judge's
reason with the samples' scores. The path that does is the one where every
judgement errors: `_all_errored` keeps each sample's reason verbatim, and a
judge that replied in prose instead of JSON is refused with its reply quoted
(`the judge replied with no JSON object: …`). Probed per sink, that quote
reaches the run file, the journal, the complete report and the pytest row —
all inside the perimeter — and no boundary sink: `--redacted`, `compare
--json`, `explain --json`, the MCP run document and `run_to_json(redacted=True)`
carry no reason, so fixed decision 9 holds and nothing needed an advisory.
**The reason is not scrubbed**, because scrubbing it would delete the diagnosis
a mute judge gives, which is what 0.8.0 worked to get into the run file. This is
not specific to calibration: a reason has always been payload inside the
perimeter. A test pins every boundary sink for a calibration case on the
errored path, and that test is what keeps the corrected promise true.*

#### 4.8 Amendment, 2026-09-17: what building it found

*The calibration case was built first, as §2 orders. Four places resisted the
text. Each was taken to a checkpoint and ruled there; none was decided in the
code alone.*

**A calibration delta is not a verdict about the system.** `compare()` pairs
the calibration case's verdict like any other, so a score that moves 0.50 →
0.40, beyond tolerance and outside the reference's interval, is `regressed` —
inside its band. Counted as §4.4's table first said, that sets `worse` and
exits 1 with *1 check got worse* about a case the target was never asked. So
the delta is computed and kept: in `Comparison.deltas`, in `--json full` with
`calibration: true`, and in its own section of both documents, because movement
inside the band is information the other three measurements will read. It is
left out of `Comparison.counts`, of every outcome selection, of `within_noise`
and `on_the_line`, and so of `Headline.counts` and `worse`. Counting it in the
wire's `counts` while keeping it out of `worse` was weighed and refused: a
document whose `regressed: 1` sits beside *nothing got worse* contradicts
itself, and a machine consumer reads the number. **The rule, in one line: the
canary's row was copied without noticing that the canary measures the system
while the calibration case measures the instrument.** Its one gate is its band.

**The judge must see what the real cases' judge sees.** The target renders the
input, and the target is not called here, so an `LlmRubric` or a `Faithfulness`
would grade the known answer without its question. `Calibration` gains
`input: str | None = None`, payload like `output` and never written. `None` and
`""` stay different facts — not declared, declared empty — and where the check
is one of those two, `None` is refused by name: a control instrument that fails
for a reason unrelated to what it controls is worse than none. Named types, as
the replay's trajectory refusal is, because no check declares that it reads the
input; a third-party judged check is not refused.

**The refusal reads `KIND`.** This record was written without knowing that
0.13.3 had shipped `KIND: ClassVar[CheckKind]` on every check, with `LlmRubric`
and `Faithfulness` declared `judged`. Adding `AssertionBase.scale` now would
declare one fact twice, and the two would diverge the day one of them is edited.
So §4.2's refusal reads `KIND`, following `Repeated` to what it wraps, and
refuses a class that declares none. **§6.1 is not amended here.** The finding is
left for shape, stated as a question: `KIND` says who produces a verdict and
`scale` was meant to say what kind of number it is, and a judged check can be
binary or graded, so shape probably still needs a declaration — under another
name, and not repeating what `KIND` states.

**"Recorded as skipped" has no state to record into.** ADR 0001 §1 has three
statuses and none of them is *skipped*. The case's checks other than the named
one produce no verdict, and the band's `check` is what the document says ran:
the skip is declared by the band rather than by a fourth status.

**§9's bump boards one passenger first.** `CaseResult.calibration` changes what
a document means — a 0.13.x reader would count the case as ordinary and exit 0
where 0.14.0 exits 2 — so `SCHEMA_VERSION` moves to 12 with it, and the version
moves to 0.14.0 with the schema. `Verdict.scale` and `Run.judge_samples` are
ruled onto the same bump, and ADR 0014 §1's economics decide the order: a bump
is paid once, so **0.14.0 is not tagged until both have boarded 12**, or each
needs a 13 of its own.

### 5. `judge_samples`: repeatability, and never without its scale

#### 5.1 What it is

    digline rejudge --suite … --run … --judge-samples M

A re-judge of a stored run in which **each judged check asks the judge M times
for each recorded answer.** The answers are fixed, so what varies across the M
is the judge alone — the decomposition of the band the roadmap queued it for,
and the first consumer of `rejudge` beyond re-scoring.

#### 5.2 What it is not, and two corrections to how it was queued

**It is not a replay at a different `samples`.** The queued note read *rejudge
with different samples changes `config_hash`, so it is already not promotable*.
Both halves are wrong against the code. A replay whose `Suite.samples` differs
from the recorded count is **refused** — ADR 0015 §6's fourth refusal,
`replay.py` `_check` — because `samples` there means *how many answers*, and
the answers are the stored ones. And a replay is unpromotable by `rejudged_from`
(ADR 0015 §7), not by its hash. `--judge-samples` leaves `Suite.samples` and the
hash alone and adds a dimension the replay did not have.

**It is not `Repeated` applied from outside.** Wrapping changes an assertion's
identity (the `Repeated` docstring says so on purpose), so a re-judge that
wrapped every judged check would compare as `new` plus `missing` against its own
source — a replay unable to say what moved.

#### 5.3 Where the figure lives, and what it must never feed

Per judged verdict, in **`Score.metadata`**: `judge_samples`, `judge_min`,
`judge_max`, the widest single-answer judge range across the recorded answers,
and the answer index where it was widest. All numbers, all crossing a boundary.
`Run` gains `judge_samples: int`, written only when set.

**Metadata, and not `Score` fields**, and the distinction is
`combine_samples`' own: the metadata half is reported, the fields are acted on.
`compare()`'s noise floor reads `sample_min` and `sample_max`, and the judge's
range **must not reach it** — it would widen the baseline's excuse with an
interval measured on a run that asked the target nothing, which is ADR 0015 §7's
*noise floor measured without the noise* by a different door.

#### 5.4 The calibration result beside the variance, always

A `judge_samples` reading carries the calibration result **in the same breath**,
and where the suite has no calibration case it says so:

> the judge's own range on these answers is at most 0.100000 across 5
> judgements (`faithfulness`, answer 3 of case `refund-policy`); the calibration
> case `half-supported` scored 0.500000, inside its declared band

> the judge's own range on these answers is at most 0.000000 across 5
> judgements; this suite declares no calibration case, and a judge that has
> lost its scale reads as perfectly repeatable

The second sentence is the reason §1 exists. A repeatability figure of zero is
the one reading that means either *a stable instrument* or *a collapsed one*,
and without the calibration beside it the reading cannot say which. Printing it
alone would be fixed decision 3's vacuous green, measured on the judge.

It is a replay, so it inherits everything ADR 0015 decided: not promotable, the
headline says re-judged, and it needs `record_responses=True` on the source.

#### 5.5 Amendment, 2026-09-17: what building it found

*Four places the text left open, each ruled at a checkpoint before the code.*

**The verdict records the first judgement.** Of an answer's M judgements, the
one its verdict is built from is the **first in execution order** — the calls
are serial, and the order is the order they were made, never the order they
returned, so parallelising them later must not change which one is first. A
`--judge-samples` replay therefore records the same quantity as a plain replay
and as its source run, which judged each answer once. Recording the mean of the
M would produce two documents that look alike, carry the same field names and
measure different things. The flag is a measuring instrument, not a better way
to judge: comparing a plain replay with a `--judge-samples` one isolates exactly
the flag — the same scores, and metadata beside them.

**The bounds are the widest answer's own.** §5.3's list reads as though
`judge_min` and `judge_max` could be taken across answers, and they are not: a
minimum on one answer and a maximum on another describe two different
questions, not an unstable judge — the confusion §7.3 already forbids between
the two noise intervals. So the keys are `judge_samples`, `judge_errored`,
`judge_min` and `judge_max` of the one answer whose judgements spread widest,
and `judge_answer`, its position from 1. There is no separate range key: it is
`judge_max - judge_min`, and two copies of one number drift. **On a tie the
lowest position wins**, within a verdict and, for the sentence, in the run's own
order, so identical data names the same answer on every run.

**An errored judgement is counted, not escalated.** An error in one of M
measurements is a fault of the instrument, not of the case, and the chance of
at least one grows with M: escalating it to an unjudged case and exit 2 would
make the tool less usable exactly when it is used properly. It is counted in
`judge_errored`. **Where the first judgement is the one that errored**, the
verdict is built from the first judgement that returned a score — "first" means
first to score, not first attempted. Where no judgement of an answer scored,
that answer is unjudged under the existing rule. An answer with fewer than two
scores contributes no range, and where no answer has two the range keys are
absent and the sentence says the range was not measured.

**The sentence belongs to `rejudge`.** It is printed on stderr beside the
planned-calls line, and is `judge_reading` in `rejudge --json`. It is not a fact
in `explain` or a line in the report. The measurement belongs to the command
that produced it, not to every later reading of a re-judged run, and amending
ADR 0012 §3's closed list a third time, for a place this record does not ask
for, would make the list stop being closed. If the measurement ever earns a
place in the report, it gets a decision of its own.

**What it reads, and the second passenger.** Which checks are judged is `KIND`,
read through `Repeated` — the definition §4.8 gave the calibration refusal, now
one function both measurements share. `Run.judge_samples` boards schema 12
beside `CaseResult.calibration`, checked against ADR 0014 §1 as §9's table
does: outside `config_hash`, absent on every older run (none asked a judge twice
per answer), a count of our own calls. It is refused unless `rejudged_from` is
set, and `execute` refuses the parameter on any target but a replay, before the
first call: on a live target the range would be the target's and the judge's
together under the judge's name.

### 6. Shape: the distribution across the suite

#### 6.1 The code cannot tell graded from binary, so the assertion declares it

Found in the reconnaissance, and each shortcut fails concretely:

- `_binary(ok)` is `_graded(1.0 if ok else 0.0)`, and `PiiAbsent`, `IsJson` and
  `ToolsCalled` call `_graded` with 0 or 1 directly. Grepping the helper
  misclassifies them.
- `Verdict` and `Score` record no kind. `assertion_id` is a truncated sha256;
  the type name is not recoverable. `Score.name` is what the author typed.
- **Folding hides it.** scout's `AgreesWithMark` is 0/1 per sample, and at
  `samples=5` its recorded score is 0, 0.2, … 1 — which reads as graded.
- **`Faithfulness` is judged and graded by type, and binary per verdict** when
  `claims_total == 1`: `supported / total` reaches only 0 and 1. That is
  arithmetic.
- `Levenshtein`, `Length` and the budget proxies are graded and **not judged**.
  They have no scale to lose.

**Inferring the kind from the data is refused**, and not for taste. A judge that
had already gone binary when its baseline was promoted would classify itself as
binary and exempt itself from this reading for good. The detector would switch
itself off in exactly the case it exists for.

So the assertion **declares** it, on the class, the way `accepts` is declared:

    AssertionBase.scale: ClassVar[Literal["binary", "graded", "judged"] | None] = None

`judged` — a judge places the value on a scale: `LlmRubric`, `Faithfulness`.
`graded` — deterministic and continuous: `Levenshtein`, `Length`, the budgets.
`binary` — 0 or 1 by construction. `Repeated` copies its inner's. A class-level
`ClassVar` is not a dataclass field, so `identity` is untouched.

**Undeclared is `None` and is announced, never guessed.** A third-party
assertion written before this record — scout's two — is undeclared, and it is
excluded from the shape. Defaulting to `graded` would make every binary
third-party check fire daily, which is noise by design; defaulting to `binary`
would silence a third-party judge without saying so. The honest third answer is
to say it where the author is: `digline run` names the undeclared assertions on
stderr before the first call, beside the planned-call line, because that is the
one moment the suite is loaded and its author is reading.

`compare()` reads run files without the suite, so what the reading needs has to
be **in the document** — and the reading needs one value only. `scale: "judged"`
is written on a verdict whose assertion declares it, and nothing is written
otherwise: `binary`, `graded` and undeclared stay declarations in code, because
no reading distinguishes them. That keeps the document change to the checks the
record is about. §9 checks it against the passenger rule.

#### 6.2 What is read

For each check declared `judged`, over the cases that count — not suspended,
not errored, not a canary, not a calibration case — the **share of raw
per-sample scores at exactly 0.0 or 1.0**, at storage precision:

- raw, meaning `Score.samples` where `samples > 1` and the score itself at one
  sample — never the folded mean, which is §6.1's third bullet;
- for `Faithfulness`, leaving out the scores that can only be 0 or 1 by
  arithmetic — `claims_total == 1` — with the count left out stated in the
  reading. It is the one place this reads a metadata key by name, and a reading
  may: nothing gates on it.

  **Exact at one sample, and not at more — the code resists here.** The fold
  averages numeric metadata (`_folded_metadata`), so a verdict at `samples=5`
  keeps the *mean* claim count and not the five. A mean below 2 proves some
  sample made one claim, and the verdict is left out. A mean of 2 or more does
  not prove that none did: `(1, 3)` averages to 2. Those verdicts are read, and
  the reading says their per-sample counts were not recorded. Recording them is
  a document change and is not decided here.

*Amended 2026-09-17, after the 0.14.0 release, by its delta-pass: **a second
fold the reading cannot see.** A `Repeated` check folds its own judgements into
one verdict per answer, and in a suite with `samples > 1` the driver then folds
those verdicts across the answers. What `Score.samples` keeps is the per-answer
**means**, not the judgements: a judge that alternates 0 and 1 inside
`Repeated(samples=2)` is stored as `(0.5, 0.5)` and reads as 0% at 0 or 1 — a
fully collapsed judge shown as the opposite, which is the one picture this
reading exists to catch. At suite `samples=1` the judgements are stored and the
reading is exact.*

> **Corrected 2026-09-17, in §6.5: the last sentence above is false.** A nested
> `Repeated` folds means at suite `samples=1` too. Measured through the driver,
> `Repeated(Repeated(check, samples=2), samples=2)` stores `(0.5, 0.5)` at suite
> `samples=1` for a check that alternates 0 and 1, the same as `Repeated` at
> suite `samples=2`, and with the same keys. A `--judge-samples` replay of a
> `Repeated` check reaches it by a third road.
>
> **This paragraph was written before there was data, and a reader should know
> that is why it keeps narrowing.** This is the third time. §6.2 first said the
> raw per-sample scores are read. Then *exact at one sample, and not at more*,
> for `Faithfulness`'s claim count. Then this amendment, for `Repeated` in a
> sampled suite. Now it narrows again, for a nested `Repeated`. Each time the
> sentence described the cases its author had in mind, not the mechanism. §6.5
> stamps the mechanism — a fold whose inputs were themselves folds — so the
> reading no longer depends on a list of cases being complete.

*The document cannot say which verdicts are such a fold. The inner fold writes
`samples`, `agreement`, `spread`, `errored_samples` and `scores`, and the outer
fold overwrites those same keys, so the stored verdicts of `LlmRubric` and
`Repeated(LlmRubric)` carry identical key sets. Only the values differ, and the
values are what is in question. **So the fix is a document change, and a patch
does not move documents.** It is ruled onto the next schema bump as that bump's
first passenger: a stamp saying the verdict's samples are folds. The reading
then treats those verdicts the way this section treats single-claim ones —
left out of the shares, counted, and the line saying their per-judgement scores
were not recorded. An absence stated, never a zero. Until the stamp exists, the
limit is stated in `docs/explain.md` beside the reading, so nobody reads such a
0% and believes it.*

The same share for the reference, and both printed.

#### 6.3 Where it goes, and what is measured later

A fact in **`explain`** — `shape`, the second amendment to ADR 0012 §3's list —
and in `compare --json full`. It is a comparison of one run with its reference,
so it sits inside ADR 0012 §5's scope. It is **not** in the headline, which is
the report's sentence to world 3 and carries only what gates or qualifies a
gate.

> `faithfulness`: 97.1% of 208 judged scores at 0 or 1, against 41.3% of 204 in
> the reference

**The threshold is measured later.** The candidate sentence — *graded scores
concentrate at the extremes more than they did in the reference* — needs a
rule for *more than*, and on a suite of twenty cases one verdict moves the share
by five points. Choosing that number in this text would be inventing a statistic
before anybody has read one on data. What ships is the two shares and their
counts; the sentence that judges them is added by an amendment to this section
once it has been sized. **The r/Rag author's data is the first candidate for
sizing it, and it is not ours. scout cannot size it:** it declares no judged
check.

**Never an exit code**, before or after the threshold exists. The calibration
case is the gate; the shape is the diagnosis — the same split as the aggregate
and the cases in `docs/guide.md` §7.

#### 6.4 Amendment, 2026-09-17: the scale is `KIND`'s, and the key is `judged`

*Ruled 2026-09-17, before any code. It answers the question §4.8 left open:
`KIND` says who produces a verdict, `scale` was meant to say what kind of
number it is, and a judged check can be binary or graded — so is `scale` a
second axis, or the same fact declared twice?*

**The declaration is redundant; the document key is not.** They were one
proposal in §6.1 and they separate cleanly.

**What §6.1 wanted `scale` to do, and what already does it.** It named three
values and one reading. The reading, §6.2, reads **one** of them: shape is read
over checks declared `judged`, and §6.1's own last paragraph writes nothing for
`binary`, `graded` or undeclared, "because no reading distinguishes them". The
other two values were there to keep deterministic checks out of the shape
reading: `PiiAbsent` and `ToolsCalled`, graded by helper and binary by
construction, and the budgets, graded and not judged. `KIND` already separates
those: every one of them is `deterministic` or `budget`, and only `LlmRubric`
and `Faithfulness` are `judged`. Adding `scale` would state `judged` a second
time and add two values nothing reads, and §4.8 already refused one fact
declared twice.

**The case that looked like a second axis is not one.** *A judged check can be
binary* was argued from scout's `agrees_with_mark`. Read from scout's source,
that check compares the target's structured answer with the action Mark took,
through `_binary(agrees(said, wanted))`. The model inside it is the **system
under test**, not an instrument grading it. In digline's terms it is
deterministic and binary, and the §6.1 bullet that already said "scout declares
no judged check" was right. No suite the house runs has a check that is judged
and binary by design.

**And where one exists, shape does not need to be told.** A judge asked for yes
or no puts every raw score at an extreme, in the run and in the reference.
§6.2's reading is a comparison — the run's share against the reference's — so a
check binary by design reads 100% against 100%. That is true, it cannot become
*more than the reference*, and so it cannot fire whatever threshold §6.3 later
sets. Declaring it `binary` would only remove a row that says nothing new. It
would also let a declaration exempt a check from the one reading that watches
it, which is the self-exemption §6.1 refused when it refused inference. A
hedging judge that starts returning 0.5 on a yes/no rubric is the one movement
such a row can show, and it is a true fact about that judge.

**What stays: the reading needs the fact in the document.** `compare()` and
`explain` are functions of the documents they are handed, which is §7.1's own
argument, so which verdicts are judged cannot be looked up in the suite at
read time. A verdict whose assertion is `judged` — `judged()`, read through
`Repeated` — is written with **`"judged": true`**, and nothing is written
otherwise. That is the canary's convention, a flag written only when true, and
not `"scale": "judged"` or `"kind": "judged"`: a key named for a vocabulary that
only ever holds one value invites a reader to expect the others.

**So the train is not full with two pieces.** Shape keeps its passenger, renamed
and sourced from `KIND`: `Verdict.judged`. Against ADR 0014 §1, as §9's table
does: outside `identity` and `config_hash`, since `KIND` is a `ClassVar`;
absent means *not recorded as judged*, which is true of every older verdict,
and nothing is derived from a check's name; one boolean about the check, never
about the case. §9's cost is unchanged — one key per judged verdict, and no
byte for any other.

**What follows for the rest of §6.1.**

- `AssertionBase.scale` is not added. §6.1's declaration, and its test-plan
  line *every assertion in `digline.core` declares one, by set*, are replaced by
  `KIND`, which 0.13.3 already declares and tests by set.
- **Undeclared stays announced, never guessed.** A check whose class declares no
  `KIND`, read through `Repeated`, is left out of shape, and `digline run` names
  it on stderr beside the planned-calls line, as §6.1 decided for `scale`. That
  reverses one sentence of 0.13.3's documentation. `KIND` stays optional —
  nothing fails without it — but it is no longer unread, and scout's two checks
  are the first that will be named until they declare `deterministic`.
- **`FromAutoevals` is the known hole in the reading, and this record says so at
  that weight.** It declares `wrapper` and wraps a scorer, not an assertion, so
  there is nothing to read through. An autoevals scorer that calls a model is
  therefore **neither judged nor announced**: shape cannot see it, and the
  author is not told. The rule this amendment rests on is that a declaration
  must never let a check escape the reading that exists to watch it, in either
  direction, and `FromAutoevals` escapes it by having no declaration to read.
  Closing that needs the adapter to declare what its scorer is — a decision of
  its own, not taken here. A test pins the hole, so closing it is a decision
  someone makes rather than a side effect.

##### Amendment, 2026-09-19: the hole is closed in two halves

*The decision the bullet above said someone would have to make. It is here
rather than in a record of its own, because that bullet named the hole and a
reader chasing two texts for one fact is the cost of tidiness.*

**Two halves, and the order between them is the argument.** The silence is
closed for everyone; the reading is closed for whoever declares.

- **The floor: a wrapper that wraps no assertion is announced as undeclared.**
  `undeclared_kinds()` names a check whose class declares no `KIND`; it stays
  silent for this one, because `wrapper` *is* a declaration. But `wrapper`
  means *read my nature through what I wrap*, and here there is nothing to read
  through — so the declaration is **unresolvable, not absent**, and the
  machinery was treating unresolvable as answered. It is now named in the same
  breath as a check that declared nothing, on stderr beside the planned-calls
  line, for the reason that channel exists: defaulting either way guesses, and
  the author is the only one who knows.
- **The declaration: the adapter takes the author's word for what its scorer
  is.** `FromAutoevals` gains a field saying whether the scorer asks a model,
  and `judged()` consults the instance for this class. That is not a new kind
  of lookup — `judged()` already walks `.inner` instances through `Repeated`;
  what is new is that a wrapper's nature can be an instance fact, because the
  thing wrapped is not a digline value with a `KIND` to read.

**Why the floor comes first, and why neither alone.** An announcement with no
way to act on it is a nag; a declaration nobody is prompted for is a feature
with no users. The author who is never told has no reason to declare, and the
author who declares silences the line — which is the same bargain `KIND` offers
every other check: optional, and no longer unread.

**Defaulted, not mandatory.** A mandatory field would break every existing
`FromAutoevals(...)`, which is defensible before 1.0 and buys too little: the
announcement already puts the question in front of the author on every run,
which is most of the benefit at none of the cost.

**And the default is `None`, meaning *undeclared* — not `False`.** Found while
building it: a defaulted boolean cannot be told from an author who answered, so
`undeclared_kinds()` would have fallen silent the moment the field existed and
the floor would have closed nothing. Three states, and each is a different
sentence: *undeclared* reads as not judged everywhere and is named until
somebody answers; `False` is a declaration too, and silences the line for a
scorer that computes rather than asks; `True` puts the check in the reading.
Undeclared is safe **only because it is announced** — the default never decides
anything in silence.

**The `IDENTITY_EXCLUDED` widening, ruled here and not discovered later.**
`AssertionBase.identity` is `dataclass_identity(self, IDENTITY_EXCLUDED)` over
the **declared fields**, so a new field on `FromAutoevals` would enter
`identity`, and `identity` is in `config_hash`. Every stored baseline of every
suite using an autoevals check would stop pairing and need re-promoting — for a
declaration that changed no number. `KIND` escapes this by being a `ClassVar`,
which is why §9 could say that declaring it leaves every baseline promotable.

So `FromAutoevals` widens `IDENTITY_EXCLUDED` to hold the new field, on the
rationale already written for `threshold` and `tolerance`: **they describe how
a result is judged, not what is checked**, and they already travel in every
verdict. Whether a scorer asks a model is the same kind of fact — it says who
produces the number, not which number is produced. A suite that declares it
compares, pairs and promotes exactly as before.

**The limit this does not close, stated rather than papered over.** Declaring
makes the check **judged**; nothing here makes it **identified**. An autoevals
scorer holds its own client and exposes no configuration digline can read, so
`judge_config` stays empty whatever the author declares, and `digline log` goes
on reading *declared no configuration* for that side. A declared-judged
autoevals check is therefore **judged but unidentified**: it enters the shape
reading, it may be calibrated, `--judge-samples` will repeat it — and ADR 0005
§4's *the instrument moved*, the check that exists to catch a judge changing
under you, cannot see it. That is a true limit of adapting a scorer whose
client is its own business, and the honest thing is to carry it in the record.

**A hand-written `judge_config` is refused.** The obvious close — let the suite
declare the provider and model beside the scorer — is a **second source of
truth for a value the scorer already holds**, kept in sync by memory. The first
time they diverge the document is confidently wrong about which instrument
graded, which is worse than the document saying it does not know: an empty
`judge_config` is an absence a reader can act on, and a stale one is a fact they
will act on wrongly. It is the same reason `digline_version` is stamped by the
driver and never inferred from a dependency pin (ADR 0020 §3).

**Against ADR 0014 §1**, since a field is added to a public value: the hash is
untouched by the widening above; nothing migrates, because no stored document
gains a key — `Verdict.judged` already exists and is written from `judged()`,
which now answers differently for a declared adapter; and nothing new crosses a
boundary, because what crosses is the boolean that already crossed.

**The pinning test moves rather than goes.** The test named for the known hole
asserted the silence — `undeclared_kinds(...) == ()` — and that assertion is now
false by design. It becomes two: an undeclared adapter **is** named, and a
declared one is judged and is not named. The hole was pinned so that closing it
would be a decision someone makes; this is that decision, and the test records
it instead of the hole.

#### 6.5 Amendment, 2026-09-17: the stamp, its key, and its three answers

*§6.2's amendment ruled the reading: a verdict whose `Score.samples` are folds
is left out of the shares, counted, and the line says its per-judgement scores
were not recorded. It left open the key's name and its answers to ADR 0014 §1.
This section answers both, and it boards schema 13 second, after ADR 0018 §1's
nameless tool call.*

**What building it found first: the fold is not where §6.2 put it.** §6.2 names
one case, `Repeated` in a suite with `samples > 1`. Measured through the
driver, with a judged check that alternates 0 and 1 and `min_agreement` at its
floor:

| declared | suite `samples` | stored `Score.samples` |
|---|---|---|
| the check | 2 | `(0.0, 1.0)`: judgements |
| `Repeated(check, samples=2)` | 1 | `(0.0, 1.0)`: judgements |
| `Repeated(check, samples=2)` | 2 | `(0.5, 0.5)`: means |
| `Repeated(Repeated(check, samples=2), samples=2)` | 1 | `(0.5, 0.5)`: means |

All four verdicts carry the same metadata keys. **So "at suite `samples=1` the
reading is exact" is false for a nested `Repeated`.** A `--judge-samples`
replay reaches the same state by a third road: `fold_judgements` records each
answer's first judgement, and for a `Repeated` check that judgement is already a
fold. What the cases share is not a declaration but a mechanism: **a fold whose
inputs were themselves folds.** So the stamp is placed on that mechanism, not on
a list of cases someone has to keep complete.

**1. Where it is stamped.** In `combine_samples`, the one function every fold
passes through, which is pure and in `digline.core`. The rule: a fold of two or
more verdicts, at least one of which carries samples of its own or the stamp,
is stamped. `Repeated` carries the stamp through when it re-stamps the fold
under its own name, and `fold_judgements` inherits it from `combine_samples`. A
fold of one verdict returns that verdict unchanged, as it always has, so a
`Repeated` check at suite `samples=1` is not stamped, because what it stores
are judgements. An all-errored fold has no samples and is not stamped: there is
nothing to read.

It sits on `Score`, beside the `samples` it qualifies, not on `Verdict` beside
`judged`. `judged` is a copy of a declaration and is stamped by the driver.
This is a fact about how these numbers were produced, and it has to hold
wherever the score is built, including inside a core function that never sees
a driver.

**2. The key: `"sample_means": true`.** Written only when true, beside
`samples`, by the canary's convention and `judged`'s. It says what the stored
samples *are*: each one is a mean of judgements. Two names were refused:

- **`folded`** — every sampled verdict is a fold of its samples. The key would
  be true of `(0.0, 1.0)` in the first row too, and a reader would have to
  already know which fold is meant.
- **`"samples": "means"`**, or any vocabulary key — refused by §6.4's reasoning:
  a key named for a vocabulary that only ever holds one value invites a reader to
  look for the others. `samples` is also already the number list.

In memory: `Score.sample_means: bool = False`, refused where it is true and
`samples` is empty.

**3. The reading, as §6.2's amendment ruled it.** `ShapeSide` gains
`sample_means`, a count of verdicts left out because their per-sample scores are
means. `explain` says *N verdicts left out: their per-judgement scores were not
recorded* (en and it). `compare --json full` carries the count as
`"sample_means"` inside each side of `shape`: an added key, which ADR 0011's
output contract admits without moving `OUTPUT_VERSION`. The `docs/explain.md`
limit is replaced by the sentence about what is left out, plus the residue
below.

**4. The passenger rule (ADR 0014 §1).**

| | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `Score.sample_means` | outside `identity` and `config_hash`: it follows from `Suite.samples` and the `Repeated` declarations, which are already in both, and it declares nothing new | the 12 → 13 step writes **nothing** — but here absent does **not** mean what it means in a schema-13 document. See below | one boolean about how the scores were stored, never about the case. It crosses with the verdict as `samples` does, and it adds no string. `redact()` keeps it, and `promote_baseline` keeps it, because a baseline is read by this very reading. `digline.wire`'s run projection does not emit it, which is the known gap already stated for `judged` |

**Answer 2 is where reality resists, and it is not the nameless call's
answer.** A schema-12 document *can* hold such folds, unstamped: every 0.14.x
run of a `Repeated` check in a sampled suite wrote one. The migration cannot
derive the stamp. The key sets are identical (the delta-pass proof), `Run` does
not record the suite's `samples` (it is only inside `config_hash`), and a
`Repeated`'s identity is a hash nobody can read back. Writing the stamp would be
a guess, and so would writing its absence as *these are judgements*.
`_NON_ADDITIVE` would refuse every schema-12 document for a fact most of them
do not involve. So the step writes nothing, and **absent means *not stamped*,
never *judgements*.** In a document written at 13 that is the same thing,
because the writer always stamps. In a migrated one it is not, and the reading
has to carry the difference, the way it carried `judged`'s absence in older
references.

**How the reading carries it.** Pairing is by `assertion_id`, which includes
`Repeated` and its count. Where the run's verdict for a check is stamped, a
reference verdict for the same identity that is sampled and unstamped is left
out of the reference side and counted, not read: it is either a fold nobody
stamped, or a fold at a different suite `samples`, and neither can be read as
judgements. That can leave out a reference verdict that really was judgements —
a reference at suite `samples=1` compared with a run at `samples > 1`, which
`config_changed` already announces.

**The criterion, not a detail of this case.** Where a document cannot say what
an absence means, and nothing in the comparison can resolve it, **the rule errs
toward leaving a verdict out, never toward misreading one.** A verdict left out
is counted and named in the reading, so the reader sees what is missing. A
verdict misread looks exactly like every verdict read correctly. Any later
reading that meets an unresolvable absence applies the same criterion, and says
so.

**The residue, stated.** One pairing stays unreadable: a run that is **not**
stamped, such as the same `Repeated` check now at suite `samples=1`, against a
reference promoted before 0.15.0 at `samples > 1`. Nothing in the run points at
the check, and nothing in the reference says what it holds. `config_changed` is
true for that comparison. `docs/explain.md` keeps one sentence for it: **a
reference promoted before 0.15.0, at a different sample count, may show means as
judgements; re-promote to read it.** It goes away as references are re-promoted,
and nothing here guesses.

**Old reader.** An unknown key on a verdict is ignored by 0.14.x, which would
read the means as judgements — the misreading this stamp exists to stop.
Nothing inside the verdict can refuse it by name. The refusal is the bump's:
0.14.x refuses a schema-13 run file on its version. A **journal**, whose version
does not move, gets no refusal. A 0.14.x resuming a leg that holds a stamped
verdict drops the key and writes a schema-12 run. That is the document 0.14.x
writes for that suite anyway, and one this reading already treats as *not
stamped*, so it adds no new misreading. So this passenger, unlike the nameless
call, **is** justified by the refusal the bump gives. Tested from v0.14.1's
source, in both directions, the journal leg included.

### 7. Spread: how much the suite moves between runs

#### 7.1 Where, and the amendment it needs

**Not in `compare` or `explain`, for two separate reasons.** Both are functions
of the documents they are handed; reading a gitignored, per-machine store would
make the same two runs read differently on a laptop and on a runner that has no
history (`docs/log.md`). And ADR 0012 §5 limits `explain` to one run and its
reference, which `tests/_vocabulary.py` enforces.

**In `digline log`**, which already scopes every word it says to *this store, in
this window*. That requires one amendment, to ADR 0020 §4 — *the row has no
score, by type* — whose hazard was a reader deducing a roll from scores printed
beside identities. The spread uses that juxtaposition in the one permitted
direction, and the amendment says so in these words:

> **Identity decides which runs are grouped; scores never decide identity.**

The spread is a new type, `AggregateSpread`, and it shares no row with
`IdentitySpan`. The test that asserts `IdentitySpan` and `Roll` by field set
stays exactly as it is.

**Aggregates only.** A suite with no `RunAssertion` gets no section, and says
so. A suite-wide number built out of the checks would be inventing the summary
Luu's complaint is about. `runs_json` already carries the aggregates (ADR 0020
§7), so the material is on the wire today.

#### 7.2 Which runs are comparable

A run is **excluded from the N, counted by reason, and the count printed** —
the seven absences' discipline, and ADR 0016 §3's: a number excluded silently is
a number nobody can check. Nothing here refuses the command.

| held equal | can the document verify it? | treatment |
|---|---|---|
| tenant and suite | yes — the store is keyed by them | free |
| `config_hash` | yes | excluded on mismatch |
| not a replay (`rejudged_from` unset) | yes | excluded: zero target variance would narrow the spread, ADR 0015 §7's reason |
| every case judged | yes — `unjudged_cases` | excluded: an errored case changes the denominator |
| not `scale_lost` | yes, after §4 | excluded: an uncalibrated run is not a measurement |
| the counted population | yes — case-id set, `suspended_excluded`, `canary_excluded`, `calibration_excluded` | excluded on mismatch |
| the prompt | yes — each artifact's `sha` (local runs are not redacted) | excluded on mismatch; a run declaring no artifacts is counted and said |
| target and judge configuration, as sent | yes — `SystemConfig.redacted()`, as `log` already reads it | excluded on mismatch |
| what answered | **mostly no** — ADR 0020 §3's rows 4–7 | never inferred: the set is the **latest identity span** only, and the reading says how many runs in it identified the answering model |
| case content under a stable id | **no** — `cases_digest` is a journal field and never reaches the document (ADR 0017 §6) | cannot be held; said |
| the mapper and all other code | **no** — `git_commit`, commonly `-dirty` | reported as the number of distinct commits; not excluded, or N collapses to one |
| `environment` | reported | never splits the set (decision 8) |
| `digline_version` | reported | the range printed; a release that changed no score changes no measurement |

*Amended 2026-09-19, from building it: the **identity** row is subsumed by the
**target configuration** row in all but one corner, and the table is left as it
is. A sighting is derived from the configuration — `resolved_model` is a value
in it — so a run another model answered differs in `target_config` and is
excluded three rows earlier, under that name. What reaches the identity check is
the residue: equal configurations whose `digline_version` differs. The row's
intent is met, and more strictly; what it uniquely contributes is the count of
runs that identified the answering model, not the exclusion. Reordering would
relabel an exclusion that already happens and change no behaviour, so the next
reader meets this line rather than an apparent redundancy.*

**The latest run is never in the N.** ADR 0006 §5's asymmetry: a noisy new run
must not widen its own excuse.

**A silent roll is the danger this cannot fully close.** A roll inside the set
is absorbed into the spread and a real change reads as noise. The latest
identity span closes it where the provider names the model; where it does not,
the unidentified count is in the sentence, and the canary is the only instrument
that sees a roll there — `log` already says that line.

#### 7.3 The range, not the standard deviation

The house already reads noise as `sample_min`–`sample_max`: ADR 0006 §2 and §5
chose ranges. A standard deviation over four stored runs is itself noise, and it
would be a second definition of *inside the noise*, with a different rule from
the one `compare` applies per case. *The latest value lies inside the range of N
comparable runs* is that same rule, read across time.

**Two intervals that must not be read as one.** ADR 0006 §7 already records,
inside one run, the range of the aggregate evaluated per sample index — *what
would a single run at one sample have said, at this moment*. The stored spread
reads the recorded aggregate, which is computed from the **folded** verdicts. At
`samples > 1` those are different quantities: the folded aggregate is steadier
than any single-sample one, and on scout's store the between-run range is
*narrower* than the within-run interval (§10). The reading prints both where
both exist and labels each, and never compares one with the other.

#### 7.4 The sentence, and the floor that is measured later

> accuracy: the latest run scored 0.810000 against the reference's 0.760000, a
> difference of 0.050000. Across 9 comparable runs in this store, in this window
> — the latest not among them; 3 excluded as re-judged, 1 as not fully judged —
> accuracy ranged 0.710000 to 0.860000: the latest score is inside this suite's
> own run-to-run spread. 7 of the 9 runs did not identify the answering model.

The other branch ends *…is outside this suite's own run-to-run spread.* Both
branches exist, always: a fact that can only say *inside* is `AGENTS.md` §5's
excuse promoted to a feature. No *likely*, no advice word; *across* and *runs*
are in the multi-run vocabulary `log` alone is permitted.

**The floor on N is measured later.** A range over two runs is a single
difference, and some N is the least that makes *inside* mean anything. Until
that N is sized on real history, the reading prints the range, N and the
exclusion counts, and **withholds the inside/outside clause**. The amendment
that sets the floor adds the clause.

##### Amendment, 2026-09-22: the clause is withheld because the range cannot carry it

*The floor above was queued as a number to be measured. It was measured, on the
first history that could answer, and the answer is not a floor: the statistic
cannot carry the clause at any N. This replaces the pending framing rather than
supplying the number it promised.*

**The material.** scout's operator — pilot-zero — began keeping its run
documents on 2026-09-17, which is the upload step §10 named as a finding of its
own. Twelve runs over four days, 2026-09-17T10:33 to 2026-09-20T11:34, three
cycles a day at one `config_hash`, 145 cases each, none replayed. Eight are
comparable under §7.2, and the three exclusions are all *not fully judged*, one
errored case each. The reading, as the shipped code printed it:

| aggregate | latest | range over the 8 | width |
|---|---|---|---|
| accuracy | 0.861111 | 0.868056 – 0.888889 | 0.020833 |
| precision | 0.518519 | 0.538462 – 0.600000 | 0.061538 |
| recall | 0.700000 | 0.700000 – 0.800000 | 0.100000 |
| tool_majority | 0.916667 | 0.916667 – 0.937500 | 0.020833 |

**Why no N makes *outside* mean anything.** A min–max range over a growing
sample is monotone non-decreasing: it cannot converge, it can only stop moving
once both extremes have been drawn, and nothing in the record says when that has
happened. So *outside* reports **discovery** — a value not seen before — and not
a change. Replaying the reading after each of the twelve cycles shows it rather
than argues it: the range was still widening at N=8 (accuracy 0.006944 at N=3–5
to 0.020833 at N=7; precision 0.019705, 0.032967, 0.038461, 0.061538), *outside*
fired on 4 of 12 readings at N≥6, and every firing above the high became the next
reading's high. At N≤2 the range is degenerate — accuracy and recall both read
width 0.000000 across the first five readings — and a clause there would have
said *outside* four times in five about nothing.

More history does not repair that. It is a property of the statistic and not of
the sample, so §7.4's *until that N is sized on real history* was wrong in kind,
and it is withdrawn.

**Ruled: the clause is withheld because the range describes and cannot gate.**
Not pending a measurement. `log.spread.floor` says that in both locales, and
says what the range *is* instead of what it lacks.

**The range stays as the reading.** §7.3's three reasons are reasons for
*describing*, and they hold unchanged: the house already reads noise as a range,
a standard deviation over a handful of stored runs is itself noise, and a second
definition of *inside the noise* would answer with a different rule from the one
`compare` applies per case. A range is honest about what was seen, which is what
this reading is for. What it may not do is decide.

**The open door, named so that nobody infers a different one.** If a reading is
ever to say *inside* or *outside*, it needs a statistic that converges — and
which one, over what sample, at what cost, is a decision of its own with its own
reasons. It is not a threshold over this one, and nothing here reserves a number
for it.

Three findings from the same measurement, recorded because each would otherwise
be re-derived:

**A floor could not be one number across these four aggregates even if a floor
were the answer.** `recall` is computed over 20 positives, so it moves in steps
of 0.05 and its entire observed range is two steps wide; `accuracy` and
`tool_majority` run on 144. One width is one step for the first and seven for
the others, so what a given width means differs by 7× inside a single suite.

**The effective N grows at 67% of the cycle count.** Twelve cycles yielded eight
counted runs, and all three losses were a single errored case in a 145-case
suite. At that error rate a counted run costs about 1.5 cycles of calendar,
which is what any later decision about N is spending.

**§7.3's between-vs-within observation reproduces, in the direction worth
stating.** The between-run range is *narrower* than the latest run's own
within-run interval on three of the four aggregates — accuracy 0.020833 against
0.027778, precision 0.061538 against 0.108696, tool_majority 0.020833 against
0.027778 — and equal on recall, 0.100000 both. The folded aggregate is steadier
than any single-sample one, now measured on two different suites, which is why
the two intervals are printed apart and never set against each other.

**The sentence, as it now reads.** The exclusion clause above elided its verb
after the first reason, so a reading whose exclusions did not begin with
*re-judged* ended in a fragment — which is what scout's store printed: *"; 3 as
not fully judged."* The verb is carried once by the clause itself, and every
reason is a bare counted phrase after it:

> Across 8 comparable run(s) in this store, in this window — the latest not
> among them; excluded: 3 not fully judged.

#### 7.5 The guard: it never turns a pass into a fail

By construction, not by convention:

- **`log` exits 0** whenever it read the store, and its `--json` has no
  `exit_code` (ADR 0020 §5). The spread adds no path to any other code.
- **No field in `compare`**: it cannot feed `within_noise`, move an outcome or
  reach `promote`.
- **Silent on a flip.** Where the aggregate's status differs between the
  reference and the latest run, no spread is printed for it: ADR 0006 §6, a flip
  carries no interval, and printing one invites the reader to argue it away.
- **Both branches, always** (§7.4).

`--json` gains `spread` beside `spans` and `rolls`; the MCP `log` tool reads the
same value. Added keys, `OUTPUT_VERSION` 1 (ADR 0011 §4).

##### Amendment, 2026-09-22: what silence prints

*This section ruled the spread **silent** in three places and never said what
silence puts on the page. The reading has to print something — the section's
heading is unconditional — so "silent" was read as *whatever sentence is
already there*, and the sentence already there was a claim about the suite.*

`log.spread` is empty for **four** different reasons, and three of them were
borrowing the fourth's sentence:

| cause | what it means | whose fact it is |
|---|---|---|
| `no_runs` | no run was read in this store, in this window | the reading's |
| `declares_none` | the latest run recorded no run-level aggregate | **the suite's** |
| `flipped` | every aggregate's status differs from the reference (§7.5) | the reading's |
| `scoreless` | every aggregate recorded no score | the reading's |

Only `declares_none` is a fact about the suite, and it is the one that was
printed for all four. So a fresh clone was told that its suite declares no
run-level check, and so was a run whose every aggregate had flipped — in both
cases a **checkable sentence standing in for one that cannot be checked**,
which is the defect §7.4's amendment closed one level in, on the exclusion
clause.

**Ruled: silent on a flip means do not report a range, not print nothing.** Not
reporting an interval is the whole of ADR 0006 §6's rule — a flip carries no
interval, and printing one invites the reader to argue it away. Naming the flip
is not printing an interval. So the section prints, and names which of the four
it is: four sentences for four facts, and a cause is never inferred from
another's presence.

**Counted by cause, never as a total**, which is §7.2's discipline applied one
level out: the count is how many of the latest run's aggregates the cause
accounts for. It is genuinely `0` for the two causes that mean there were no
aggregates to account for, and above zero for the two that are facts about
aggregates that do exist. A run with one flipped aggregate and one scoreless
one prints **both** sentences, because both are true of it and picking one would
reintroduce exactly the substitution this amendment removes.

`declares_none` keeps its existing sentence unchanged. It was never the wrong
sentence; it was the only right one, asked to cover three cases it was not
about.

`--json` gains `spread_absence` beside `spread`: a consumer reading an empty
list could not tell the four apart either, and the seven absences of ADR 0020
§3 cross for the same reason. Added key, `OUTPUT_VERSION` 1 (ADR 0011 §4).

### 8. What this record does not touch

`Repeated` keeps its meaning and its identity rule. `Suite.samples` keeps
ADR 0006 §1's meaning. No noise floor in `compare()` moves. No exit code moves
except through §4, and §4 moves one only into the state that already means *the
instrument could not answer*.

### 9. Compatibility

`SCHEMA_VERSION` 11 → 12, for two passengers, each checked against ADR 0014 §1:

| field | 1. outside `config_hash` | 2. migrates without inventing | 3. does not widen what travels |
|---|---|---|---|
| `CaseResult.calibration` — `check`, `low`, `high`, never `output` | case data, as `canary` | absent: *not a calibration case*, which is what every older case was | a name and two numbers; the answer is payload and never written |
| `Verdict.scale` (ruled as `Verdict.judged`, §6.4) | a `ClassVar`, outside `identity` and so outside the hash | absent: *not recorded as judged* — not derived from the assertion's name, which would be the guess | one declared word about the check, never about the case |

`Run.judge_samples` rides the same bump, written only on a replay that set it.

*Amended 2026-09-17 (§4.8, §5.5, §6.4): the train is full. `Verdict.scale` is
`Verdict.judged` — `true` where the check's `KIND` is `judged`, absent otherwise
— and boarded third, after `Run.judge_samples`. `CaseResult.calibration` boarded
12 first, and alone. Checked against ADR 0014 §1 as the table above does — outside the hash,
migrates by writing nothing, a name and two numbers across a boundary — it
changes the example documents by their version field only. 12 stays open until
`Verdict.scale` and `Run.judge_samples` have boarded it.*

All three are written **only when present**. What that does and does not keep
byte-identical, said plainly:

- a suite with **no judged check** and no calibration case produces the document
  it produced before, modulo the version fields;
- a suite with an `LlmRubric` or a `Faithfulness` — which is most suites that
  have a judge — **gains one key per judged verdict** from the first run under
  this release. No score, status, reason or identity changes, so no comparison
  reports a delta and nothing needs re-promoting; but the next baseline promoted
  is a diff of one line per judged verdict, and that is the visible cost of §6.

The migration writes nothing: an older verdict with no key is *not recorded as
judged*, which is true of it. The shape reading, against such a reference, says
it has no declared scale to compare with, and stays silent until a reference
carries one.

### 10. What the material said

Read on 2026-09-16 from scout's local store (`../scout/.digline/alessandro/runs/
scout-judge/`) and its operator workflow, before this text was finished. It is
here because it is where the design met data it did not choose.

**The store holds 16 runs, and the largest comparable set under §7.2 is three.**
Same `config_hash`, same 17 case ids, same prompt digest, same target, none
replayed, none with an error: 2026-09-09T12:06, 2026-09-10T11:58,
2026-09-11T14:51. They are three genuine runs — their per-case verdicts differ —
and all three recorded accuracy 0.647059, precision 0.733333, recall 0.916667.
**A range of width zero, over three runs, at three different `-dirty`
commits.** The 144- and 145-case suites that followed have one comparable real
run each, and one replay that §7.2 excludes.

**The within-run interval of those same runs is wider than the between-run
range.** Accuracy's per-sample aggregate interval is 0.588235–0.647059 in each
of the three, while the recorded aggregate did not move at all. That is §7.3's
distinction, observed rather than argued: the folded aggregate over five samples
is steadier than any one-sample aggregate, and a reading that compared the two
intervals would conclude something false.

#### A finding of its own: pilot-zero discards the material this record needs

scout's operator — pilot-zero — runs the suite every day on a hosted runner, at
the configuration its `operator.toml` fixes: the same suite, the same cases, the
same target, the same sample count, cycle after cycle. That is **exactly** the
set of comparable runs §7.2 describes, produced on a schedule, which is more
than any laptop store will ever hold.

**And it throws every one of them away.** The workflow uploads two artifacts:
the decision journal, and the alert with its cycle and decision files. It does
not upload the run documents. Fixed decision 2 keeps `runs/` gitignored, so on a
hosted runner a run file lives exactly as long as the job, and the history that
could size §7.4's floor — and give the first real measurement of this suite's
run-to-run spread — is produced every day and discarded every day.

This is not a design flaw in this record, nor in ADR 0019: it is one missing
upload step in scout's workflow, and fixing it is not a release. It is written
here as a finding rather than a note because it is the precondition for
measuring the spread on digline's own data at all, and a precondition written as
a note is the kind that gets lost. The fix is queued separately.

**So the caveat of the Context is sharper than it was written.** scout can size
the spread *in principle*. On the material that exists today it cannot, and
nothing in this record changes that.

## Consequences

**The judge gains measurements of its own**, and the one that gates — the
calibration case — needs no history, no reference and no threshold nobody has
measured. It can stop a first run.

**Exit 2 gains a cause that is not an error.** The headline says which, and a
pipeline reading only the number sees no change in kind: *the instrument could
not answer* is what 2 already meant.

**A calibration case costs judge calls and an author's care.** The answer has to
be known to be partial, and a band has to be written down before the first run.
Suites that decline it keep today's behaviour exactly, and a `judge_samples`
reading says in its own sentence what declining costs.

**Two readings ship without their sentences.** Shape prints shares and spread
prints a range, and neither says *more* or *inside* until the data sizes it.

*Amended 2026-09-22: for spread, permanently. The data was read and it sized
nothing: a min–max range is monotone in N, so *outside* reports a value not
seen before rather than a change, and the clause is withheld because the
statistic cannot carry it (§7.4). Shape's sentence is still pending; spread's
is not coming back in this form.*
That will read as unfinished. It is the cost of not setting a threshold in text.

**Third-party assertions are undeclared** until their authors declare a scale,
and `digline run` names them each time. scout's two are the first.

**Every suite with a judge gains a key per judged verdict** (§9). Nothing
re-promotes, and the next promotion is a larger diff than its scores explain.

**The spread is a laptop's fact** unless a runner keeps its runs. A hosted
runner has no history of its own, and §10 shows the one operator producing the
right history is the one discarding it.

## Alternatives considered

**The standard deviation for the spread.** Rejected in §7.3: a second definition
of noise, unstable at the N a real store holds, and imported from the source
rather than from the house.

**The spread in `compare` or `explain`.** Rejected in §7.1: it would make a
document-reading command depend on a per-machine store, and `explain`'s
vocabulary is one run and its reference.

**Inferring binary from graded out of the recorded scores.** Rejected in §6.1:
a judge collapsed at promotion exempts itself for good.

**A default scale for undeclared assertions.** Rejected in §6.1, in both
directions: `graded` is daily noise on binary checks, `binary` is silence about a
judge.

**The calibration case as `calibration=True` over a generated answer.**
Rejected in §4.1: an answer generated today is not known to be partial.

**Exit 1 for a lost scale.** Rejected in §4.5: 1 means a statement about the
system, and a lost scale is a statement about the instrument.

**A lost scale outranking a regression.** Rejected in §4.5: a regression on a
binary check stays true, and both codes stop.

**A calibration band with an open end** — `low = 0` for a case expected to be
poor. Rejected in §4.2: an extreme in band cannot detect the extreme.

**`judge_samples` as a replay at a different `Suite.samples`, or as `Repeated`
applied from outside.** Rejected in §5.2: the first is refused by ADR 0015 §6
and means something else; the second changes every judged check's identity.

**The judge's range as a `Score` field.** Rejected in §5.3: fields are acted on,
and the noise floor would read it.

**Recording the rendered judge prompt** so §3 could be read after the fact.
Not decided here: it is the most sensitive payload a run could hold.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The calibration case fires, in both directions and not otherwise.** A score
above `high`, a score below `low`, a score on each bound (inside, inclusive at
storage precision), an errored verdict (unjudged, not `scale_lost`), and a suite
with none (no field, no clause, no row).

**It needs no reference.** A first run whose calibration fires exits 2 from
`report` and from `explain` without a baseline.

**Precedence.** `worse` with `scale_lost` → 1, with both clauses in the
sentence and the calibration clause first; `scale_lost` alone → 2.

**Only the named check runs**, on a fixture suite with a `CostBudget` and a
`ToolsCalled`: neither errors, both are recorded as skipped, `CallPlan` counts
no target call for the case and counts its judge calls.

**The refusals**: canary and calibration together; a band touching 0 or 1; a
`check` naming a missing or non-judged assertion; `samples=1`. Each beside the
construction that succeeds, so the refusal is visibly narrow.

**Not promotable**, and **a replay re-judges it** from a source run that
recorded no answer for it.

**`judge_samples`**: the metadata keys present and numeric; `sample_min` and
`sample_max` untouched; `compare()` against the replay's source unchanged by the
judge range; both §5.4 sentences, the second on a suite with no calibration case.

**The scale declaration**: every assertion in `digline.core` declares one, by
set; `Repeated` copies it; `identity` of each unchanged, asserted against the
committed baselines' ids; an undeclared third-party check named on stderr by `digline run` and excluded from the shape.

**Shape reads raw samples.** A binary check at `samples=5` whose folded scores
are all in `{0.2 … 0.8}` is still undeclared-or-binary and never read; a
`Faithfulness` verdict with `claims_total == 1` is left out and counted.

**Spread**, on a fixture store: each row of §7.2 excluding exactly one run and
naming it; the latest run absent from the range; a roll splitting the set; a
flip printing nothing; both branches of the clause withheld until the floor
exists; `IdentitySpan` and `Roll` field sets unchanged.

**Both locales**, and the no-advice gate over every new string, with *likely*
forbidden in all of them.

**What stays byte-identical, and what does not.** A suite with no judged check
and no calibration case produces the document it produced before, modulo the
version fields. A suite with an `LlmRubric` gains exactly one `scale` key per
judged verdict and no other byte, and `compare()` against its pre-release
baseline reports no delta.

## Not decided here

**The shape threshold**: *more than the reference* (§6.3). It arrives as a
dated amendment to its section, sized on data, with the data named.

*Amended 2026-09-22: there were two thresholds here, and the second one is
closed rather than pending. The floor on N for spread (§7.4) was measured and
the answer was that no floor exists — a min–max range cannot converge, so it
describes and cannot gate. What replaces it is not a number but a door: a
reading that says `inside` needs a statistic that converges, which is its own
decision with its own reasons and not a threshold over this one.*

**The upload step that keeps pilot-zero's runs** (§10). A change to scout's
workflow, queued separately; not a release and not a decision of this record.

**Instrument versus target, as named states.** Reconnoitred beside this record
and not in its scope. The finding, kept for the record that takes it up: the
driver knows the cause at the moment of the error — `target`, `mapper`,
`assertion` (`driver.py` `_run_case`) — and the document discards it (ADR 0017
§10); `assertion` itself mixes the instrument (a judge that raised, returned no
object, scored outside `[0, 1]`), the suite's configuration (`Equals` with no
expected value, an empty context) and the measured side (`JsonSchema` on text
that is not JSON); two cases cannot be attributed from the data at all
(`claims_total == 0`, and `min_agreement` under `Suite.samples`); and the judge
has no way to *declare* that it cannot judge, because the reply shape has no
abstention. Any heuristic for a malformed case is refused in advance.

**Recording what the judge was shown** (§3).

**Recording `Faithfulness`' claim count per sample** (§6.2), which would make the
shape exact on sampled suites. A metadata list per verdict, and a passenger
question for the next bump.

**Stamping a `Repeated` fold** (§6.2, amended 2026-09-17). Ruled: the first
passenger of the next schema bump. The shape it takes there is ruled too; only
the key's name and the passenger rule's three answers are left for that bump.

**What the MCP run document carries.** `get_run` and `get_baseline` return
`digline.wire.run_document`, a projection chosen under ADR 0011 §5 rather than
inherited from storage. It does not carry `Verdict.judged`,
`CaseResult.calibration`, `Run.judge_samples`, `CaseResult.canary` or
`Run.rejudged_from`. Those are facts about our own instrument, and none is a
leak by being absent; but a model reading `get_run` cannot tell a judged check,
a calibration case, a canary or a replay from their neighbours, and has to call
`explain` or `compare` for them. A known gap, found in the 0.14.0 delta-pass, to
be closed by a decision about the wire, not noticed by accident.

**A per-check calibration for more than one judged check** per suite. One
calibration case names one check; a suite with two judged checks declares two
cases. Whether one fixed answer may calibrate several checks at once is left to
the first suite that wants it.
