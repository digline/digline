---
name: proposing-a-suite
description: How to propose a first digline suite to a developer who does not know how to set one up, by digline's method — read what was recorded and reviewed, choose the checks from the metrics tree, write the suite with a counterexample in it, run it, and hand it over as a proposal. USE WHEN a person asks you to write, set up, start or propose a digline suite, an evaluation or tests for their model's output, or when a repository has digline recordings or reviewed answers and no suite that reads them.
---

# Proposing a suite

You are proposing a suite; you are not deciding one. A suite says what
*correct* means for somebody's application, and that is theirs to say. Your
share is the method: read what is there, pick the checks the way digline's own
pages pick them, write the files, run them once, and say plainly what you
assumed. The person reads the diff and commits it, or does not.

Three rules hold through every step, and the last section says them again:

- **You propose, you never mark.** A yes or no about an answer is a person's,
  and so is a label, a promotion and an import (ADR 0023, ADR 0037).
- **A suite that cannot fail measures nothing.** Every suite you propose
  carries at least one case it fails on.
- **The commit is the person's.** You leave files in the working tree and a
  summary; you do not commit them.

Each step names the command or the page that does it. Where a step needs
something only the person knows, ask; do not guess it into a file. The pages
are in digline's repository, under `docs/`.

---

## 1. Read what is there

Before choosing anything, find out what the application answers and what a
person already said about it.

- **Start from `digline suggest`.** `digline suggest --suite <suite>`
  writes `suite.proposed.toml` beside the suite: the checks every recording
  holds, the limits the runs measured or a placeholder marked as one, a
  counterexample and a calibration skeleton, and on standard error what it
  assumed (`docs/suggest.md`). Where there is no suite yet, give its name with
  `--tenant <tenant>` and `--repository`, `private` or `public`: whether the
  cases stay inside the perimeter of whoever owns the text is the person's to
  say, so ask. It marks nothing, and no command of digline reads the file.
  It is your starting point and a proposal too: the steps below read what
  it could not, and the person adopts its lines.
- **The recordings.** `digline record status` says, per tenant, whether the
  recorder is on and how many calls it holds for each suite name
  (`docs/record.md`). No recordings is not a dead end: the suite can start
  from cases you write with the person, and the recorder can be switched on
  later. Switching it on is the person's decision, and the hook asks before
  `digline record on`.
- **The answers, grouped.** `digline record import --tenant <tenant> --suite <suite>`
  lists the recorded answers of one suite and writes nothing. It groups them
  by the **shape of their output** — `text`, `structured`, `conversation`, or
  for an episode the actors of its steps — and says how many answers and
  recordings each group holds. The shape is what step 2 chooses from, and the
  counts say how much evidence there is.
- **Where there is no suite yet, the listing needs one.** It reads the
  suite's `[capture]`, whose `check` must name a judged check of the suite. So
  write the skeleton of step 3 first, with the judged check you expect from
  how the application is used, list, and revise the checks once the shapes
  are in front of you.
- **The setup in force.** The listing prints it, the setup of the newest
  recording, and marks every answer recorded under an earlier one. A setup is
  everything a call decided besides the case: the model, the system prompt,
  the parameters (`docs/record.md`). Where there are two,
  `digline record compare --tenant <tenant> --suite <suite> --setup <a> <b> --show-setup`
  names the keys they differ on. The target you write in step 3 makes the
  call the setup in force makes, or it measures another application.
- **The reviewed cases.** In the cases file the suite's `[capture]` names,
  every case with a `reviewed_answer` is an answer a person said yes or no
  to: `good` is the person's word, `reviewed_by` their name. Count the yeses
  and the noes. They are the most valuable thing in the repository for you:
  the noes are where your counterexample comes from (step 3).
- **A yes on an episode is a yes to its steps too.** An answer the import
  took from an episode carries that episode's `steps`, and the suite's checks
  on the steps run on it beside the check it names. On a yes, a red one is a
  contradiction, as the named check's is: the person read a turn, and a turn
  is its answer and the steps it took to it. On a no they decide nothing,
  because a no does not say which part of the turn was wrong (`docs/api.md`;
  ADR 0059). Say this to the person before they mark an episode: a yes given
  for the text alone also vouches for every call the agent made.
- **How the application calls the model.** An HTTP endpoint, a provider
  called with a prompt file, or a call inside the application's own code:
  this decides the form of the suite in step 3 (`docs/declarative.md`, *What
  it cannot say*).

## 2. Choose the checks from the metrics tree

The tree is in `docs/metrics.md`, *Choosing one*. Walk it with the shape you
read in step 1, not with what you would like to measure.

- **The shape of the output picks the family.** A fragment that must or must
  not be there: `Contains`, `NotContains`, `Equals`, `Affix`. A shape rather
  than a value: `IsJson`, `JsonSchema`, `Regex`, `Length`. An episode's steps:
  `ToolsCalled`, `Subsequence`, `Before`, `Never`, `MaxSteps`, and
  `ToolCalledWith` for the arguments. A judgement only words can state:
  `LlmRubric`; supported by a retrieved context: `Faithfulness`.
- **For an episode, the checks on the steps go where the others go.**
  `Subsequence`, `Before`, `Never` and `MaxSteps` are assertions like the
  checks on the output, in the same block: the `assertions` list of a
  `suite.py`, or `[[assertions]]` entries of a `suite.toml` named
  `subsequence`, `before`, `never` and `max_steps` (`docs/api.md`, *Four
  checks on the steps*; ADR 0060). They read the steps the target reports, so
  the target runs the agent and reports its steps.
- **Every case is asked every check.** No form narrows a check to some of the
  cases or to one group (ADR 0010 §5), so propose only a check that holds for
  every case of the suite. `Subsequence(["lookup_order", "issue_refund"])` in
  a suite that also holds questions with no refund fails each of them;
  `Before(first="lookup_order", then="issue_refund")` states the rule and
  passes where no refund was made. Where the cases need rules that contradict
  each other, say so: they are two suites, and that is the person's call.
- **Deterministic first, judged after.** Whatever a deterministic check can
  state, state with one: it costs nothing, never wobbles, and its failure needs
  no interpretation. A judged check is for what is left.
- **The judge is the person's to choose.** Which judge, and which model
  behind it, decides what every judged number means and what each call costs.
  Propose the judge of the provider plugin the application already uses
  (`docs/api.md`), name its model, and ask.
- **Every judged check is wrapped in `Repeated` with a `min_agreement`.** One
  judgement is a sample of one (`docs/metrics.md`, *`Repeated`*). Start where
  `docs/guide.md` chapter 3 starts, three samples and `"2/3"`, and say it is a
  starting point; its table says what each floor catches. A suite with
  reviewed answers also asks the target at least twice, `samples` and its
  own `min_agreement`, which a reviewed answer needs (`docs/record.md`).
- **Where there is a judge, propose one calibration case** (ADR 0024): an
  answer partly right, with a band strictly between `0` and `1` where a judge
  that still has its scale places it (`docs/calibration.md`, *Does the judge
  use the scale?*). Take the answer from the recordings where one reads as
  partly right, quoted whole, rather than writing one. Whether it is partly
  right, and where the band sits, is the person's call: propose the case,
  mark it as proposed in the suite and in your summary, and let them move
  the band.
- **Starting numbers follow the precision rule.** Every limit is compared at
  six decimals and is inclusive (ADR 0009). A count is written as the
  fraction: `min_agreement = "2/3"`, never `0.67`, which is above two votes in
  three and errors every split (`docs/guide.md`, chapter 3).
- **A threshold goes where the system measurably is**, never where you wish
  it were (`docs/guide.md`, chapters 4 and 5): the lowest score seen across
  several runs, read from the whole suite and not from the top of a file. One
  run is not that. Write the first threshold as a placeholder, say so, and
  propose how many runs would set it and what they cost; running them is the
  person's decision.
- **Never `Accuracy`, `Precision`, `Recall` or `F1` without a true label.** They
  count agreement with a `label` a person gave each case. A label you derived,
  from the judge, from the reviewed answers or from your own reading, makes
  the figure a measure of you. The reviewed answers are in no aggregate
  (`docs/metrics.md`, *What is left out of a denominator*).
- **`CostBudget` and `LatencyBudget` beside whatever you picked**, where the
  target reports what they read.

## 3. Write the suite, with a case it fails on

- **The form.** `suite.toml` when the target is an HTTP endpoint or a
  provider with a prompt file; `suite.py` when it is a function — an agent,
  a call inside the application's own code, or a body that must be computed
  (`docs/declarative.md`). Both build the same objects. A `suite.py` target
  makes the call of the setup in force (step 1).
- **The capture declaration**, `[capture]` in a `suite.toml` and `capture=`
  in a `suite.py`, with `cases_file`, `repository` and `check`, and the
  capture file among the suite's `cases`, so the reviewed answers run with it
  (`docs/declarative.md`, *`[capture]`*; `docs/record.md`). `repository` has
  no default on purpose: whether the file stays inside the perimeter of
  whoever owns the text is the person's to say, so ask.
- **The reviewed answers stay as they are.** You read them; you do not edit,
  add or remove one.
- **At least one case the suite fails on — a suite that cannot fail measures
  nothing.** Take it from the noes: a reviewed answer with `good: false` is an
  answer the judged check must fail, and its verdict, `fail`, is the proof
  that the check can say no. A no on an episode is that proof for the judged
  check alone: its steps decide nothing (step 1). Where there are no noes, or
  the check that must fail is deterministic, construct one: an input whose answer the check must
  refuse, with an id and a comment that say it is constructed —
  `counterexample-…` — so nobody mistakes it for a recorded answer. Say in
  your summary which case it is and which check it fails.

## 4. Run it, and read what it says

- `digline run --suite <suite>`, then
  `digline explain --suite <suite> --run latest` (`docs/explain.md`). `run`
  prints the planned calls before the first one: say that figure to the
  person before running a judged suite (the `operating-digline` skill,
  rule 7).
- **Read the counterexample first.** A constructed one is in `explain`, under
  its bar. A reviewed no the judge agreed with is not: `explain` names only
  the contradictions, so read it in the report,
  `digline report --suite <suite> --run latest --locale en --out report.html`,
  under *What the judge said of the reviewed answers*, where it reads `no` and
  `agrees` (`docs/calibration.md`). If the counterexample passed, the suite
  cannot fail on the case you put there for that purpose: say so before
  anything else.
- **If the judge contradicted a person, say so and stop there.** `explain`
  names the reviewed answer, the check and which way it went. On an episode's
  yes the check can be one on the steps: the person vouched for a call the
  check refuses, and that is theirs to read again. Do not touch the rubric,
  the threshold, the judge, the check or the case to make it agree: the person's
  yes or no is the expected verdict, and a judge tuned until it agrees has
  learned the answer key (ADR 0023; `docs/calibration.md`, *Does the judge
  agree with a person?*). Report it as a finding about the judge.
- A calibration case outside its band exits `2`: report it the same way.

## 5. Hand it over as a proposal

- The suite you wrote is a **proposal**. Say so in the first line of your
  summary, and list what you assumed: the form, the setup the target
  reproduces, the judge, each check and why, each starting number and where it
  came from, the calibration band, the counterexample.
- **You never mark, promote or import.** No `--good` or `--bad`, no
  `digline promote`, no `digline view --allow-promote`, no
  `digline record import` that writes. Each is a person's act, and the hook
  asks before them for that reason (ADR 0023, ADR 0037).
- **The commit is the person's.** Leave the files uncommitted.
- **Words you never write about your own work: "I labelled", "I promoted",
  "I imported".** If one of them would be true, a rule above was broken;
  if it would be false, it is the sentence a reader remembers.
