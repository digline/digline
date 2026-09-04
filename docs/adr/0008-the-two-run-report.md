# ADR 0008 — The two-run report (`digline diff`)

- Status: accepted — implementation on `adr-0008`; ships in 0.6.0. The document
  landed first and the code was written against it, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) and
  [ADR 0007](0007-the-declarative-suite-format.md) were
- Date: 2026-09-04
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states, and an error
  is neither green nor a regression) and §3 (`compare()` is a pure function of
  the core), [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter) and §8 (a baseline is an approved reference and
  promotion has three conditions),
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4–5
  (withheld rather than absent, `unknown` rather than a guess),
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §3–§5
  (`target_config` beside the hash, the judge's identity set, the named delta,
  and `unknown` is never reported as a change),
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5–§7 and §9 (the
  measured interval, where it does not reach, the aggregate's own interval, and
  "within noise" as a fact beside the verdict)
- Touches: nothing in the *fixed* section of `CLAUDE.md`. Decision 8 (the tenant
  is the perimeter) is reaffirmed here rather than amended: `diff()` refuses a
  crossed perimeter for the same reason `compare()` does
- Closes: the deviation in `digline view`'s `/compare?against=` screen, which
  shipped in 0.4.0 and has been answering this ADR's question with the previous
  one's semantics ever since (§6)

## Context

digline answers one question well: **did it get worse?** A run is held against
the baseline, the baseline is an *approved reference* — ADR 0002 §8 makes the
approval the whole of its meaning — and the answer gates a pipeline through
`exit_code()`.

There is a second question, and people have been asking it since the second
week. **Should I switch?** Prompt A or prompt B. `claude-haiku-4-5` or
`gpt-5-mini`. Temperature 0.3 or 0.7. The old rubric or the rewritten one. Two
candidates, both measured, **neither approved by anybody** — because approving
one of them is the decision being made, and it has not been made yet.

Today that question is asked with the wrong instrument, in two ways.

**In the view, with the verdict's semantics.** `digline view` ships a screen at
`/compare?run=X&against=Y` that calls `compare(run, against)` and renders
`render_html`. So a developer who picks two candidate runs off the list gets a
document headed *"Did it get worse?"*, a section called *"What got worse"*, a
column labelled *"Reference"*, and a tally of `regressed` and `improved`. Every
one of those words is a claim that one side is the standard. Neither side is.
That screen is this ADR's question served by the previous ADR's answer, and §6
is where it is closed rather than excused.

**In the CLI, not at all.** `digline compare` reads the baseline and only the
baseline (`_need_baseline()`), so the terminal cannot ask the question in any
form. The workaround in the field is to promote a candidate, compare, and
promote back — which writes into `.digline/<tenant>/baselines/`, which is
committed, which puts a decision nobody made into somebody's pull request.
`AGENTS.md` §1 exists partly because that workaround is so easy to reach for.

The two questions are not the same question at two confidence levels. They have
different inputs (an approved reference against a candidate; two candidates),
different outputs (a verdict; a report), and different consequences (a gate; a
decision a human takes). Serving the second with the first's machinery produces
a document that is *arithmetically correct and rhetorically false* — every
number in it is right, and every word around the numbers claims an authority
nothing conferred.

## Decision

### 1. `diff` is a report, never a verdict

**`digline diff` exits 0 on a completed report, whatever the report contains.**
Not "0 unless something got worse", not "0 unless the intervals are disjoint" —
0, because the command completed and produced its document. Nothing about
`diff` gates anything.

Usage errors keep the CLI's existing conventions: a bad flag, an unreadable
run, a refused pair (§3) exit `EXIT_USAGE` (64) through the `UsageError` and
`ValueError` handlers `main()` already has. The distinction is the ordinary one
— *the report could not be produced* against *the report says something you do
not like* — and only the first is a non-zero exit.

The reason, stated plainly because it is the whole ADR: **a verdict exists only
against an approved reference.** `compare()` can say "worse" because somebody
looked at the baseline and signed it; `exit_code()` can turn that into a 1
because a pipeline is entitled to act on a signed reference. Neither side of a
diff was approved by anyone. A tool that exited 1 because run B scored lower
than run A would be asserting that A was the standard, which is exactly the
thing nobody decided — and it would be asserting the opposite the moment the
arguments were swapped.

**So the `--json` structure has no `worse` field, and its absence is the
point.** `Headline` is not reused: it carries `worse`, `unjudged`, and a
`sentence` built from `fact.worse.*`, and `cmd_compare` serialises it whole with
`dataclasses.asdict`. A diff that emitted a `Headline` would ship the one field
this section exists to withhold, and a consumer would find it, read it, and gate
on it. The diff's payload carries counts, per-check rows and the two runs'
identities, and a pipeline that wants a gate is told, in the documentation, to
use `compare` — which is what a gate is for.

### 2. A new symmetric command, not a flag on `compare`

**`digline diff <run1> <run2>`.** Two positional arguments, a new subcommand.

Not `digline compare --against <key>`, and not `compare --no-gate`. `compare`
always gates and `diff` never does; **the exit code is the contract**, and a
contract selected by a flag is a contract a user has to remember they selected.
The failure mode is concrete and one-directional: somebody puts `compare
--against` in CI to answer "should I switch", and six weeks later the pipeline
is red because candidate B scored lower than candidate A on one check that
nobody ever approved. Two commands with two exit behaviours cannot produce that;
one command with two modes eventually will.

**Swapping the arguments swaps the columns and nothing else.** `diff X Y` and
`diff Y X` are the same report with the two columns exchanged: the same set of
differing checks, the same counts with the two "favours" figures exchanged, the
same intervals, the same refusals. This is a property, and §7 makes it a
property test rather than a promise.

It follows that **the report carries no perspective language**. There is no
"reference", no "before" and "after", no "regressed" and "improved", no "still",
no "already". The two runs are named by their **key**, with the configuration
delta that distinguishes them printed above everything else (§3), because
`2026-09-04T…-a1b2` means nothing to a reader while `temperature 0.3` against
`temperature 0.7` means everything. A check that differs is reported as
differing **in favour of one named run**, which is a statement about a number
and not about a direction of travel.

`latest` resolves on either positional argument, through the existing
`_resolve_key`: `digline diff latest <key>` is the shape the question is
actually asked in. A run diffed with itself is refused — the view already has
the sentence for it (`view.compare.same`), and a report of no differences
between one run and itself is a document whose every line is a tautology.

**`--locale` defaults to `en`.** `CLAUDE.md` splits the locale rule on
*document* against *terminal*, not on the word "report": `report --locale` is
mandatory because a rendered HTML file has a recipient who did not choose
English, and `compare --locale` defaults because terminal output is for the
developer. `diff` writes to a terminal, so it takes the terminal rule. Both
locales are written for its copy regardless (§5), so that **a future HTML diff
document — if one comes — takes the mandatory flag like every other document**
and finds its strings already there.

### 3. Same suite and same judge are mandatory; the target is free

A diff between two runs is only meaningful if the two runs were measured the
same way. Two conditions, both refusals, both checked in `diff()` itself so that
Plumbline gets them too:

**Same suite: the rules' `config_hash` must match.** `config_hash` is built from
the sorted `(identity, threshold, tolerance)` of every assertion, plus `samples`,
`min_agreement` and the aggregates. Equal hashes therefore guarantee the same
checks, the same bars and the same declared tolerances on both sides — which is
what §4 leans on. The refusal names what it is:

> the two runs were produced under different suites (`config_hash` `a1b2…`
> against `c3d4…`): a diff between them would compare the rulers, not the
> systems — re-run one side under the other's suite

**Same judge: the ADR 0005 identity set must match.** `Run.judge_config.
identities` is the sorted, de-duplicated set of `provider/model` labels that
graded the run. A judge that moved is a scale that moved, and ADR 0005 §4 is
already explicit that a difference measured on two scales is not a difference.
The refusal:

> the two runs were graded by different judges (`anthropic/claude-haiku-4-5`
> against `openai/gpt-5-mini`): the instruments differ, so a difference between
> these scores is not a difference in the systems — re-run one side under the
> other's judge

The identity set has **four** states, not two, and the fourth is where this
section had to make a choice:

1. **Both sets empty** — allowed. A suite of `Contains`, `Regex` and
   `JsonSchema` declares no instrument, and so does a plain-function judge in a
   test. Refusing here would exclude every non-LLM suite from the feature, which
   is most suites.
2. **Both non-empty and equal** — allowed. The ordinary case.
3. **Both non-empty and different** — refused, as above.
4. **One empty, one not** — **refused**, with a message that says which side
   recorded nothing.

State 4 needs its defense, because ADR 0005 §5 forbids reporting `unknown` as a
change and this looks like doing exactly that. It is not. **Refusing is not
reporting unknown-as-a-change; it is declining to report** — which is precisely
what §5 protects. §5's rule exists so that a baseline promoted before ADR 0005
does not have to be re-promoted: a *comparison* that fabricated a `judge:
changed` row would put a fact nobody established in front of a customer, so it
says `unknown` and carries on. Here nothing is put in front of anybody: the
command says it cannot establish that the two runs were graded by the same
instrument, and stops.

The second half of the defense is why `diff()` may do this where `compare()` may
not. **`compare()` must never fail.** It is the gate; a `compare` that refused
would be a pipeline that went red for a reason having nothing to do with the
model, and the only cure would be re-promoting a baseline — the expensive,
committed, human-approved act. **`diff()` may fail, because the cure is one
re-run.** Neither side is approved, nothing is committed, and re-running one
candidate under the other's judge costs what a run costs. A refusal whose remedy
is cheap and whose alternative is a misleading document is the right refusal.

**Two further refusals, both from the same premise.** `diff()` is a *public
function of the core*, so its guarantees have to hold for Plumbline and not only
for the CLI, where the argument parser happens to make the mistake impossible:

- **Crossed tenants raise**, exactly as in `compare()`. Fixed decision 8 is not
  negotiable and does not become negotiable because the output is a report:
  one end customer's numbers read as another's is arithmetically valid and
  factually nonsense whichever document it lands in.
- **Different suite *names* raise**, even at an equal `config_hash`. Two suites
  can legitimately share a fingerprint — the same checks at the same bars over
  different cases — and a report that named one suite while diffing two would be
  wrong in its header and nowhere else, which is the worst place to be wrong.

**The target is free, and that freedom is the feature.** Two models, two
temperatures, two prompts, two endpoints: that is the question. So the report
**opens by naming what does differ between the systems**, using ADR 0005's
delta-by-name machinery — `_config_deltas` over the two `target_config`s, and
`_artifact_deltas` over the two artifact sets. `temperature 0.3` against
`temperature 0.7`, `prompt.md` differing, before a single score is shown.
ADR 0003 §5 and ADR 0005 §5 both put what changed above what it did; here the
ordering is even more load-bearing, because *what differs about the systems* is
the whole reason the reader opened the report.

### 4. "Differs" reuses the semantics the runs already carry

No new numbers, no new knobs, no `--threshold` on `diff`. A run file already
carries everything this needs, and inventing a second definition of "different
enough" would give the product two answers to one question.

**A score difference counts when it exceeds the declared tolerance.** By §3 the
two sides share a `config_hash`, so for any paired check the two tolerances are
the same value. There is one crack, and it is closed rather than ignored: a
suite may declare the *same assertion identity twice with different tolerances*,
which leaves the multiset equal on both sides while `index_verdicts`' occurrence
counter could pair them across. So the rule is `max(left.tolerance,
right.tolerance)`, which is swap-invariant — a requirement of §2 — and which
reads, in the only way the data supports: **a difference counts only if it
exceeds both declared tolerances.**

**A pass↔fail flip always counts, whatever the delta.** ADR 0001 put rule 3
above rule 4 and ADR 0006 §6 kept it there; the same ordering holds here. Two
runs where one passes a check and the other fails it differ, and by exactly the
amount that matters — a tolerance is a statement about scores, and a flip is a
statement about outcomes. A flip carries **no interval**, for ADR 0006 §6's
reason unchanged: the intervals did not decide it, and printing them beside it
would invite a reader to check the scores against them and find, quite often,
that both are inside.

**Sampled sides show their recorded min–max beside the score.** `Score.samples`,
`sample_min` and `sample_max` are on the verdict already, on both sides, on case
verdicts and — by ADR 0006 §7 — on aggregates. Where **both** sides are sampled
and the two intervals overlap, the row carries an **"intervals overlap"** note.

That note is **evidence beside the count, and it excuses nothing.** This is the
one place where diff's semantics deliberately part from `compare()`'s, and the
asymmetry has a cause. In `compare()` the noise floor *decides*: a movement
inside the baseline's interval is reported `unchanged`, and it may do that
because the baseline is the promoted, reviewed measurement — it has the standing
to say "that much movement is what I do". **A diff has no baseline, so no
interval has the standing to command.** Neither run is entitled to declare the
other's difference noise. So the difference is counted, the note is printed, and
the reader — who is deciding whether to switch, not whether to merge — weighs
it. A row that both differs and overlaps is a row that says "these two are not
distinguishable by this check", which is a finding, not a dismissal.

**Aggregates participate under the same rules.** Precision, recall and accuracy
are paired by `index_verdicts` in the `"run"` scope with an empty `case_id`, and
they carry per-sample intervals of their own (ADR 0006 §7). They differ, or do
not, by the same tolerance-and-flip rule as everything else, and they are the
rows most likely to carry the overlap note — which is right, because an
aggregate over twenty-one cases is where "not distinguishable" is a real answer.

**The headline is counts, and one sentence.** The counts:

> 7 of 65 checks differ: 3 favour `2026-09-04T09-12-…`, 4 favour
> `2026-09-04T11-40-…`, 58 within tolerance

Symmetric, exhaustive, and free of any word that suggests a direction. The
strongest sentence the data supports is of the form:

> 2 of `<run2>`'s advantages exceed both runs' observed intervals

and it is the strongest *because* of what it withholds. It does not say run 2 is
better. It says that on two checks, run 2 scored higher and the two runs'
measured intervals do not overlap — so the difference is larger than the wobble
either run showed. That is a fact about four recorded numbers, and it is the
most a reader is entitled to take from two unapproved runs.

**Its population is the pairs where both sides are sampled.** A check sampled on
one side and not the other has one interval and no second one to be disjoint
from, so it is **excluded from the count** rather than counted as exceeding or
as not exceeding — the same discipline as ADR 0005's `unknown`. And when that
population is empty — a suite at `samples=1`, which is most suites — **the
sentence is not printed at all.** Silence is what "nobody measured this" sounds
like; a sentence reading "0 of run 2's advantages exceed both runs' observed
intervals" would report an absent measurement as a null result.

### 5. Where the code lives, and what it honestly reuses

**`digline/core/diff.py`**, a new module, pure, importable from Plumbline like
everything else in the core. Not a second function inside `compare.py`: that
module's docstring, its `Comparison`, its `Outcome` vocabulary and its whole
rule order are about a run held against a baseline, and widening it would make
one file answer two questions with one set of names.

Four helpers move out from behind their underscore in `compare.py`, because they
now serve two consumers rather than one:

- **`index_verdicts(run)`** — the `(scope, case_id, assertion_id, occurrence)`
  pairing. Its docstring says it now serves both, and *why the pairing rule is
  the same for both*: identity is identity whether or not one side was approved.
- **`config_deltas(now, before)`** and **`artifact_deltas(run, baseline)`** — the
  ADR 0005 and ADR 0003 delta-by-name computations §3's opening section needs.
- **`Noise`** — the interval value, read on both sides here instead of one.

**The computation reuses; the copy does not.** This is the line, and it is drawn
where it is because everything on the copy side of it carries the perspective
§2 forbids: `config_changes()` renders `{field} {before} → {after}`, the config
table's columns are `"This run"` and `"Reference"`, `SECTIONS` is headed *"What
got worse"*, and `Headline.sentence` is assembled from `fact.worse.*`. So
`diff` gets its own `diff.*` keys in `report/text.py`, in **both locales**, and
reuses the *layout* — the column shapes, `fmt_score`, `fmt_value`, the table
helpers — wherever the reuse is honest. Two renderings of one fact drift apart
the moment they have two sources; two renderings of two different facts must not
be forced through one string.

`Comparison` and `AssertionDelta` are not reused as the result type, for the
same reason. `AssertionDelta` carries `current`/`baseline` and a **single**
interval, judged against the baseline's; a diff row needs two intervals and two
neutrally-named sides. Widening `AssertionDelta` to carry both would put fields
on the comparison path that `compare()` must never fill, which is how a value
starts meaning two things.

The `Run` values themselves do not know their own keys — the key is
`FileResultStore`'s rule, `_slug(created_at)-config_hash`, and the core must not
know it. So the **labels are passed in** by the caller that has them. The core
computes; the CLI names.

### 6. `digline view` stops answering this question with the other one's semantics

The screen at `/compare?run=X&against=Y` shipped in 0.4.0, before this ADR
existed. It was built because the second question was already being asked and
the machinery for the first one was in hand — the honest description is that it
served **the diff's need with the verdict's semantics**, and it has been doing
so on every run pair a developer picked off the list since.

It is closed here, in this branch, rather than noted as a known deviation.
Publishing an ADR that states a principle while knowingly leaving its violation
in the product is not what this repository's decision records are: **they
describe the product as it is.** A record that had to be read alongside a list
of places it is not true would stop being a record.

The rule, and it is a small one:

- **`against` is the baseline** — including when it is omitted, which is the
  screen's default — and the page stays the verdict. It is a run held against an
  approved reference; that is `compare()`'s question, and the existing document
  is the right answer to it.
- **`against` is any other stored run** and the page becomes the **diff report**:
  the same rules as the command, the same refusals, the same neutral copy.

The refusals of §3 reach the screen too, and they surface as the view's ordinary
400 rather than as a rendered report — a page that half-answered would be worse
than a page that says why it cannot answer. The self-diff case already has its
sentence (`view.compare.same`) and keeps it.

Nothing else about the view moves. It holds no state, it writes on one route,
and that route still writes exactly what `digline promote` writes.

### 7. Compatibility

**`SCHEMA_VERSION` stays at 9.** No run needs migrating, no baseline needs
re-promoting, no example needs re-recording. Everything §3 and §4 read —
`config_hash`, `judge_config.identities`, per-verdict `tolerance` and `status`,
`samples` / `sample_min` / `sample_max` on case verdicts and on aggregates,
`target_config`, `artifacts` — has been in the document since schema 9, which
0.4.0 shipped. A run recorded the week this ADR was written and one recorded
before it diff against each other with no ceremony.

The one thing an older pair loses is the interval, exactly as in ADR 0006: two
runs at `samples=1` produce a report with no intervals and no overlap notes, and
the sentence of §4 is suppressed rather than printed empty.

**`OUTPUT_VERSION` stays at 1.** The constant is the shape of what `--json`
prints for a consumer parsing stdout, and a *new command's* JSON breaks no
existing consumer: nothing that parses `compare --json` today sees a byte
change. `OUTPUT_VERSION`'s comment gains a line saying `diff --json` is under
the same contract from the start.

## Consequences

**The workaround that writes to a committed directory loses its reason to
exist.** "Promote the candidate, compare, promote back" was the only way to ask
the second question from a terminal, and it puts an unmade decision into a pull
request. `AGENTS.md` §1 tells an agent never to promote on its own initiative;
this is the command that makes that instruction followable rather than merely
correct.

**The product now has two exit-code contracts, and they are per-command.**
`compare` gates, `report` gates, `diff` does not, `run`/`list`/`promote`/`view`
never did. A reader of `digline --help` can see which is which without reading
a flag's documentation, and no invocation of either command can be turned into
the other by an option.

**A whole class of question becomes answerable without an approval.** Model
selection, prompt A/B, temperature sweeps, judge swaps at fixed target — the
work that happens *before* anything deserves to be a baseline. That work
produced runs already; what it lacked was a way to read two of them that did not
pretend one was blessed.

**Two runs that cannot be diffed will be more common than expected.** §3 refuses
on a `config_hash` difference, and a `config_hash` moves when a threshold moves.
A developer who tunes a bar between two candidate runs will hit the refusal. It
is the right refusal — the two runs measure against different bars — and its
message says the remedy, but it will be met.

**The overlap note will be printed and then argued with.** "These two are not
distinguishable by this check" is an unwelcome answer to somebody who has
already decided which candidate they prefer. That it is unwelcome is not a
reason to soften it into an excuse, and §4's refusal to let an interval command
anything is what keeps it from becoming one.

## Alternatives considered

**A `--baseline <key>` flag on `compare`.** The smallest possible change, and
rejected in §2: it makes the exit-code contract a function of a flag, and the
failure mode — a CI job gating on a comparison between two unapproved runs —
is silent, one-directional, and discovered six weeks later.

**A `diff` that gates on a declared direction: `diff --expect-better run2`.**
Rejected because it re-invents the baseline without the approval. If a run is
good enough to be the thing another run must beat, it is good enough to promote,
and `promote` is the reviewed, committed, human act that says so. A flag that
confers reference status at the command line dissolves the word exactly as an
agent promoting on its own initiative does.

**Reusing `Comparison` with a `symmetric: bool` on it.** Rejected in §5: the
type would carry `regressed`/`improved` outcomes that are meaningless under the
flag, and a single `noise_min`/`noise_max` where two are needed. A value whose
fields mean different things depending on a boolean is two values sharing a
name.

**Letting the overlap suppress the count — an interval-aware "unchanged".**
This is the tempting one, because it is what `compare()` does, and it is
rejected in §4 for the reason `compare()` may do it: the baseline's interval has
standing conferred by approval. Without approval, deciding that run A's wobble
excuses run B's difference is a judgement nobody authorised, and it would break
symmetry the moment the two intervals differed in width.

**Localising `diff`'s numbers or dates.** Never considered seriously, and noted
only so the next reader does not: `report/text.py` keeps ISO dates and the
decimal point in every locale so that two renderings of one run diff line by
line. A report about two runs has the same obligation twice over.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**Symmetry is a property test, not an example.** `diff(a, b)` and `diff(b, a)`
over the same pair must produce the same set of differing checks, the same
counts with the two "favours" figures exchanged, the same intervals, and the
same refusal or lack of one. Written over several constructed pairs — flips in
both directions, mixed sampled and unsampled sides, aggregates present and
absent — because §2's promise is that swapping the arguments swaps the columns
**and nothing else**, and a single example proves it for one shape only.

**Every refusal of §3 is tested by its message.** Four cases: different
`config_hash`, different non-empty identity sets, one empty identity set against
one non-empty, and a run diffed with itself — plus the two core-only refusals,
crossed tenants and different suite names, which the CLI cannot reach and
Plumbline can. A refusal whose message does not name the remedy is a refusal
that gets worked around.

**Mixed sampled and unsampled sides are their own test.** One side at
`samples=5` and the other at `samples=1` must produce a report that shows the
one interval it has, carries no overlap note, excludes the pair from the
"exceed both intervals" population, and — where that population is then empty —
prints no such sentence at all. The failing version of this test is the one that
prints "0 of …", which is the mistake §4 was written to prevent.

**Both locales, and the absence of perspective words.** The `diff.*` keys are
asserted present in `en` and `it` the way the existing table is, and the
rendered report is asserted not to contain the verdict vocabulary — no
"reference", no "regressed", no "worse". A copy change that reintroduces one
should fail here rather than in a reader's hands.

**The view's two modes.** `/compare?run=X` and `/compare?run=X&against=<the
baseline key>` render the verdict document; `/compare?run=X&against=<any other
key>` renders the diff. Asserted at the page level, where every other view test
lives, so what is tested is the page and not the socket.

**`digline diff` exits 0 on a report full of differences**, and 64 on each
refusal. This is the test that would catch decision 1 being quietly undone, and
it is the one to read first if this ADR ever looks like it stopped being true.
