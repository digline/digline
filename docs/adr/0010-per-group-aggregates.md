# ADR 0010 — Per-group aggregates

- Status: accepted — implementation on `per-group-aggregates`; ships in 0.6.0.
  The document landed first and the code was written against it, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0007](0007-the-declarative-suite-format.md) and
  [ADR 0008](0008-the-two-run-report.md) were
- Date: 2026-09-08
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born, the verdict travels) and §10 (the aggregate is
  the gate, the per-case is the diagnosis, and where to put a threshold),
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5 (the noise floor
  is a rule of `compare()`) and §7 (an aggregate gets an interval of its own, by
  re-evaluation per sample index),
  [ADR 0007](0007-the-declarative-suite-format.md) §2 (aggregates are entries in
  the same list) and §4 (`cases.json` is a JSON array of objects whose keys are
  `Case`'s fields)
- Touches: nothing in the *fixed* section of `CLAUDE.md`. Decision 3 (no
  vacuously green assertion) is reaffirmed rather than amended — §10 is the
  place where honouring it costs something visible, and it is paid
- Extends: ADR 0006 §7 is **used unchanged**. The per-sample re-evaluation that
  gives an aggregate its interval is not modified here; it is handed a shorter
  list (§7)

## Context

An aggregate today is a statement about the whole run. `precision 0.727` is one
number over twenty cases, and ADR 0002 §10 established why it and not the
per-case verdict is what gates a release: four runs of one unchanged prompt
agreed with the human mark on 14, 14, 15, 15 cases out of 21 while individual
cases moved by three votes. The aggregate is stable exactly where the per-case
is not.

That stability has a cost, and it is the cost of every average. **A whole-run
aggregate hides a class that is broken.** The `classifier` example is a live
instance of it. Its committed baseline reports `precision 0.727` and
`accuracy 0.850`, both comfortably above their thresholds, both green in every
document the product produces. Split the same twenty cases by the expense
category their `vars` already carry, and the same baseline says:

| group | TP / FP / TN / FN | precision | accuracy |
|---|---|---|---|
| `hotel` | 2 / 0 / 1 / 0 | 1.000 | 1.000 |
| `meal` | 4 / 1 / 2 / 0 | 0.800 | 0.857 |
| `taxi` | 1 / 0 / 3 / 0 | 1.000 | 1.000 |
| `tools` | 1 / 1 / 1 / 0 | 0.500 | 0.667 |
| `travel` | 0 / 1 / 2 / 0 | **0.000** | 0.667 |

The classifier does not work on travel expenses. It has never worked on travel
expenses. Every run, every report, every green pipeline in that example's
history has been arithmetically correct and has not said so, because seventeen
cases the classifier gets right are enough to carry three it does not.

This is not a defect in the aggregate. It is what an aggregate is for, and
narrowing the denominator to fix it would give back the wobble ADR 0002 §10 was
written to remove — a three-case group moves by 0.333 when one case changes its
mind, which is the per-case noise wearing an aggregate's clothes. So the answer
is not to replace the whole-run figure. It is to **put the classes beside it**,
under the same machinery, with no new semantics anywhere.

Two things make that cheap, and they are why this is a small ADR rather than a
subsystem. A `RunAssertion` is a pure function from a list of `CaseOutcome` to a
`Verdict` — hand it a shorter list and it is already a group aggregate, with its
threshold, its tolerance and its noise interval intact. And `compare()` and
`diff()` pair on `Verdict.assertion_id`, so an aggregate that has a distinct
identity is an ordinary check to everything downstream, including a group that
appears or disappears between two runs.

## Decision

### 1. `group` is a field on `Case`, and it is descriptive

`Case` gains `group: str | None = None`. Absent means the case belongs to no
group.

**It is data, and it changes nothing about execution.** The driver does not read
it, no target sees it, no per-case assertion is given it, and a suite that
declares `by_group` nowhere behaves as though the field did not exist. It is
read in exactly one place — the expansion of §2 — and read there as a label,
never as a switch.

Being a field on `Case` is the whole of its implementation in data suites. ADR
0007 §4 made `cases.json` a JSON array of objects whose keys are `Case`'s
fields, and the loader builds them by splatting the object at the constructor
after refusing unknown keys against `fields(Case)`. So a `"group": "travel"` in
`cases.json` works the day the field exists, in the TOML form and the Python
form alike, with no line written in `cli/toml_suite.py`.

**An empty string is refused.** `None` already spells "no group", so `""`
would be a second spelling of it that expands into `precision[group=]` — a
public name with a hole in it, and a gate nobody can read. `Case` raises, for
the reason `Contains(needle="")` and an empty suspension reason do.

**A string and not a list.** A case belongs to one group or to none. Multiple
membership is a different feature with a different arithmetic — a case counted
in two denominators is a case counted twice — and nothing has asked for it. A
string is also what makes §2's expansion total and its identity stable; see
Alternatives.

**It does not reach a run file.** `CaseResult` records `case_id`, `suspended`
and the verdicts, and gains nothing here. What crosses a boundary about a group
is the group's *name*, inside the expanded aggregate's name, and the group's
confusion matrix, which is seven integers. Which cases were in it stays in the
repository. That is ADR 0002 §2 holding without being asked to: the counts are a
measurement of the system, the membership is the customer's data about their own
cases, and the split falls where it already falls.

### 2. `by_group` expands, and the expansion adds

Every aggregate gains `by_group: bool = False`. When `True`, the declared
aggregate expands into:

- one instance scoped to each group **present in the suite's cases**, and
- the ungrouped whole-run instance, unchanged.

The expansion **adds; it never replaces**. `Precision(over="…", by_group=True)`
yields the whole-run precision it always yielded, plus one per group. A suite
that turns the flag on loses no figure it had, and the number that gated its
releases keeps gating them.

**Groups come from the cases, not from a declaration.** There is no list of
expected groups anywhere. A group exists because a case carries its name, and it
stops existing when the last case carrying it is removed or renamed — at which
point its aggregates are absent from the run and `compare()` reports them
`missing`, which is §9 and is the correct sentence. Declaring the set of groups
somewhere would create a second place for the truth to live and a fourth failure
mode (declared but empty) that nobody needs.

**A case with no group is in no group.** It is counted in the whole-run
aggregate and in nothing else. There is no implicit "ungrouped" bucket, because
a bucket named after the absence of a label is a group nobody chose, with a
threshold nobody set, and it would appear and vanish as cases were labelled.

**All of them or none.** There is no way to ask for one group; §5 is where that
is refused and why.

### 3. The expanded name is the identity, and it is a public string

An expanded aggregate is named:

```
<name>[group=<group>]
```

So `precision[group=travel]`, `accuracy[group=meal]`, `f1[group=refunds]`. The
whole-run instance keeps its bare name.

Three properties, each load-bearing:

**It is the `Score.name`, not a field beside it.** `report/pages.py` builds the
run grid's columns from the distinct `score.name`s across runs and indexes each
row with `{v.score.name: v for v in run.aggregate}`. Two aggregates sharing a
name do not collide loudly — one silently overwrites the other and the grid
shows a column that is sometimes one group and sometimes another. So the name
has to carry the group, and carrying it anywhere else would leave that bug in
place.

**It changes the identity, for free and correctly.** `name` is a declared field
on `Precision`, `Recall`, `Accuracy` and `F1`, and it is not in
`IDENTITY_EXCLUDED`, so `dataclass_identity` already folds it in. Renaming the
instance is renaming the check, which is exactly right here: precision over
travel is not precision over the run, it is a different question with a
different answer and a different baseline. Nothing new is invented to make two
group aggregates distinguishable; the existing rule does it.

**It is a public string, and this ADR is where it is fixed.** It lands in
`Run.aggregate[].assertion` in every run file and every promoted baseline, in
`compare --json`'s `assertion`, in `diff --json`, and in both rendered
documents. Changing the grammar later is a diff of every artifact anyone has
kept. So it is written down here, gated by a test, and not left to a format
string in a helper.

The bracket form was chosen over `precision.travel` and `precision/travel`
because a group name is user data: it can contain a dot, and a slash reads as a
path in a product that already writes `anthropic/claude-haiku-4-5` for a model
label. `[group=…]` is unambiguous at a glance about *which* axis was split,
which matters the day a second axis exists — and if that day comes, the form
extends rather than needing to be replaced.

### 4. `by_group` is excluded from the identity, and `config_hash` moves anyway

`by_group` joins `threshold` and `tolerance` in
`RunAssertionBase.IDENTITY_EXCLUDED`.

This is not tidiness; without it §2's promise is false. `dataclass_identity`
hashes every declared field minus the exclusions, so if `by_group` counted, the
*whole-run* `precision` would change identity the moment the flag was set — its
id in the `classifier` baseline is `31e12a0068b3f1db` — and `compare()` would
report the figure that gates that example as `missing` plus a `new` one beside
it. The expansion would replace what it was supposed to add, in the one place it
was promised not to.

The justification is the same shape as the one for `threshold`. Identity answers
*what is measured*. `by_group` does not change what the whole-run aggregate
measures; it declares that further aggregates exist beside it. That is a
statement about the suite, not about the check.

**And `config_hash` still moves**, which is what makes this safe. The hash is
built from `(identity, threshold, tolerance)` over `run_assertions` — and after
§6's expansion, `run_assertions` *is* the expanded set. Turning `by_group` on
adds entries, so the hash changes, so a baseline promoted before the flag is
comparable but **not promotable** as the reference for the suite that now
declares more gates. That is the behaviour ADR 0002 §8 already specifies for a
raised threshold, reached here without a special case: look at the diff, then
re-baseline deliberately.

### 5. There is no single-group form

`Precision(over="…", group="travel")` cannot be written, in Python or in TOML.

The reason is the feature's whole point: **the class that degrades is the one
you were not watching.** A form that lets an author name a group lets them name
the three they already suspect, and the fourth — the one nobody thought to
list — goes on being averaged away. Watching a group you chose is watching your
own assumptions. `by_group` is total by construction, and totality is the
property being bought.

Mechanically, `group` is declared as a non-constructor field:

```python
group: str | None = field(init=False, default=None)
```

The expansion sets it with `object.__setattr__` after `replace()` — the pattern
`RunAssertionBase._normalize` already uses on a frozen slotted dataclass. Two
consequences fall out without a line of validation. A Python caller cannot pass
it. And the TOML loader's `_init_fields` filters on `f.init`, so `group = "x"`
in an `[[assertions]]` entry is already an unknown-parameter error carrying the
existing message and the list of parameters that do exist — the same refusal
that catches `threshold` on a `repeated` entry, for the same reason.

`dataclass_identity` iterates `fields()` and does not care about `init`, so the
field still separates the identities of §3. The one thing that must be
constructible is the one thing that cannot be constructed.

### 6. The expansion happens in `Suite.__post_init__`

`Suite` is where cases and `run_assertions` meet, and it is the only place they
do. It already rewrites one of its own fields there — `min_agreement`, through
`as_agreement` — so the mechanism is established rather than introduced. It sits
upstream of `config_hash()`, which is what makes §4 work. And both authoring
forms pass through it: the TOML loader builds a `Suite` like any Python caller,
so §1 and §2 reach data suites with no loader change, which is ADR 0007 §9's
"equal citizens" holding on its own.

The expansion is a module-level function in `digline.core.aggregate`, and it
reads the flag with `getattr(assertion, "by_group", False)`.

**The `RunAssertion` protocol is not touched.** It is structural, and
`docs/api.md` invites third parties to satisfy it by subclassing
`RunAssertionBase`. Adding a member would break anything satisfying it
structurally, to buy a static guarantee about a field the expansion is happy to
find absent. A custom aggregate that never heard of groups reports `False`,
never expands, and keeps working — which is the correct behaviour and also the
honest one: it cannot be expanded, because nothing has told it how to name
itself per group.

**Stated because it will surprise somebody:** after construction,
`suite.run_assertions` is not the sequence the author wrote. It is longer. The
expansion is deterministic and ordered — whole-run instance first, then groups
in sorted order, per declared aggregate — so two identical suites produce
identical `config_hash`es and identical documents, and a test says so.

### 7. The filter sits in the driver, so the noise floor is restricted at the source

`driver._outcomes` already builds the `CaseOutcome` list an aggregate is
evaluated over, reading a `{case_id: label}` map off the suite. It gains a
`{case_id: group}` map beside it and, when the aggregate carries a `group`,
returns only the outcomes whose case is in it.

Everything else is unchanged. `with_noise_interval` is called with the shorter
list and does what ADR 0006 §7 says: compute the folded verdict, slice the same
cases as each sample index saw them, re-evaluate the pure assertion per slice,
record the N values as `samples`, `sample_min` and `sample_max`. **The
per-sample re-evaluation is restricted to the group because the list it is given
is.** No branch, no parameter, no second code path — which is decision 3 of the
brief satisfied by construction rather than by care.

**Filtering here rather than inside the aggregate is a real choice**, and the
difference is visible. `per_sample_outcomes` returns nothing unless every judged
case in the list it is given carries the same number of samples: reading across
lists of different lengths would align sample 2 of one case with sample 3 of
another and call the result a measurement. Filter in the driver and that
condition is evaluated over the group, so a group's interval is undefined for
the group's own reasons. Filter inside the aggregate and it is evaluated over
the whole run, so one odd case anywhere — a case added at a different `samples`,
a case whose target failed on three of five — silences the interval on every
group at once. An aggregate about travel expenses should not go quiet because of
a hotel.

The `CaseOutcome` value is unchanged. It never learns what a group is, because
by the time it exists the filtering has happened.

### 8. Small groups: what goes quiet, what still works, what an error means

Group aggregates inherit the declared threshold and tolerance of the aggregate
they expanded from. There is no per-group threshold and no per-group tolerance;
see Alternatives. Three things follow, and a reader is owed all three before
they turn the flag on.

**The declared tolerance goes quiet.** A tolerance is measured over a
denominator, and the group's is smaller. The `classifier`'s `tolerance="3/20"`
was set from eight runs of the whole suite, where it means "three cases"; on a
three-case group one case changing its mind moves precision by 0.333, so the
tolerance is no longer the control that speaks. It is not wrong — 0.15 is still
0.15 — it has simply stopped being the wider of the two.

**The measured floor still works, and it is what does the work.** `compare()`
checks the declared tolerance first and the baseline's measured interval second,
saying in the reason which one spoke (ADR 0006 §5). A three-case group at
`samples=5` produces a genuinely wide interval, because one case flipping in one
sample index moves the group's figure a third of the way. The control that
sizes itself to the denominator is the one that was already sized by
measurement. **This is the answer to "aren't small groups too noisy": they are,
and the noise floor is the thing that knows it.**

**An errored group aggregate is a true statement.** `Recall` over a group whose
cases are all marked negative has an empty denominator, and ADR 0002 §10 fixed
what that is: `error`, never `1.0`. Under `by_group` this stops being an edge
case and becomes ordinary — a small group will often contain one label only.
The sentence to keep is that **it is not a malfunction**: the suite has asserted
something the group cannot answer, and `error` is the accurate report of that.

Its consequences are unchanged, and precisely: an errored aggregate does not
enter `Headline.unjudged`, which counts case verdicts only, so it moves no exit
code. It is an `errored` delta in the comparison, it appears in the document's
"What could not be judged" section and in `compare --json`, and `compare` still
exits 0. Nothing here alters that, and nothing here should — an aggregate that
could not be computed is not a regression, which is ADR 0001 §1's third state
doing its job.

The remedy, when a reader wants one, is a declaration and not a flag: the group
is too small, or the aggregate is the wrong question for it. Both are answered
by editing the suite, in a diff somebody reviews.

### 9. `compare`, `diff` and the grid: nothing is special-cased

An expanded aggregate is an ordinary run-scoped verdict. `index_verdicts` keys
it `("run", "", assertion_id, occurrence)` like any other, and both `compare()`
and `diff()` read that index — one pairing rule, which ADR 0008 §5 established
and which this ADR is not permitted to fork.

So **a group appearing or disappearing between two runs follows the existing
new/missing rules**, with no code and no new outcome. Add a case carrying a
group nobody had used and its aggregates are `new`: absent from the baseline.
Remove the last case of a group and its aggregates are `missing`: present in the
baseline but not in this run. A group renamed is one of each, which is the same
sentence `compare()` already prints for a renamed case or a renamed assertion,
and it is the correct one — nothing knows that `travel` became `transport`, and
guessing would be worse than reporting.

**`diff()` is the exception, and it belongs to ADR 0008 rather than being a gap
in this one.** A group set comes from the cases and §2 turns it into gates, so
changing it changes `config_hash` (§4) — and ADR 0008 §3 refuses a diff across
configurations before it reads a single verdict, because the two runs were
measured against different rulers. So two runs whose group sets differ cannot be
diffed at all; they can be *compared*, and `compare()` reports the `new` and the
`missing` above. That division is the right one: `compare()` is built to hold a
run against a reference under changed rules and to say the rules changed,
`diff()` is built to weigh two candidates and needs them weighed on one scale.
Both keep the behaviour they have, and neither learns what a group is. Two runs
whose group sets agree diff normally, group keys and all.

`Scope` gains no third member. A group aggregate is scoped to the run: it is
computed once per run, belongs to no case, and carries an empty `case_id`. What
distinguishes it from the whole-run figure is its identity, which is where
distinctions between checks belong.

**The grid: whole-run first, then groups alphabetically.** `report/pages.py`
builds one column per distinct aggregate name, so a suite with two aggregates
and five groups goes from two columns to twelve. The ordering is fixed here
because it is the thing that makes the widened table readable — the figure that
gates the release stays leftmost, where it was, and the classes below it are in
an order that does not change between runs. Whether long rows fold, scroll or
truncate is a rendering question, and it is deferred to the report block rather
than decided in an ADR that would be guessing at it.

### 10. The classifier ships its red rows

The `classifier` example gets `group` on its cases — the expense category its
`vars` already carry — `by_group=True` on both aggregates, a re-promoted
baseline, and a README section showing the per-class table.

**And two of those rows are red**, at the thresholds the example already
declares: `precision[group=tools]` at 0.500 and `precision[group=travel]` at
0.000, against a threshold of `3/5`. This is deliberate, and it is the reason
this section exists rather than being an implementation note.

The alternative was to tune the example until every row was green — lower the
thresholds, or pick an axis that splits more evenly, or set per-group
thresholds — and every version of that is **fixed decision 3 in demonstration
form**: an assertion arranged so it cannot fail, shipped as the thing users copy
first. An example whose bars were moved until nothing tripped would teach the
one habit this product exists to prevent. The classifier does not work on travel
expenses; the example says so.

Nor is this the red-by-construction threshold ADR 0002 §10 warns against. That
warning is about a bar set where somebody *wishes* the system were, which makes
a gate permanently red and therefore ignored. This bar is set where the system
measurably is — 0.727 over the run, threshold at 0.600 below the worst of eight
runs — and the group rows are the discovery that the same bar is not met by two
of five classes. The measurement did not move. What moved is how much of it is
visible.

**And the gate does not change colour**, which is what makes shipping it
honest rather than reckless. `compare` and `report` exit on *movement*:
`worse` counts regressions against the baseline, `unjudged` counts case verdicts
that errored. A group aggregate that fails in the run and failed in the baseline
is `unchanged` — the score did not move — so the example's `check.yml` workflow
goes on passing, and the red row is a fact in the document rather than a broken
pipeline. A reader gets the finding without the example
being unusable, and the day travel *degrades further*, that is a regression and
the gate says so.

This is the example's third act, and the three read in order: a **declared**
tolerance somebody measured and wrote down, a **measured** noise floor the
baseline records for itself (ADR 0006), and now **per-class visibility** —
the aggregate that was the gate, told to say which class it was averaging.

### 11. Compatibility

**No schema change.** `SCHEMA_VERSION` stays at 9 and no migration is owed. A
run file records an aggregate as its name, its `assertion_id`, its score,
threshold, tolerance, status, reason and matrix metadata; an expanded aggregate
is an ordinary verdict under an ordinary name. Nothing in `run_to_json` or
`run_from_json` learns a field. A run file written by this release and read by
the previous one parses, and shows aggregates whose names contain brackets.

**A suite that does not set `by_group` is byte-for-byte unchanged.** Same
`config_hash`, same identities, same run file, same document. `Case.group` on a
case in a suite with no `by_group` anywhere changes nothing at all.

**A suite that does set it is comparable and not promotable** against a baseline
promoted before it (§4). That is the intended friction, and the remedy is
`digline promote` after reading the report — the human act ADR 0002 §8 makes the
whole meaning of a baseline.

**`cases.json` gains an optional key.** A cases file written before this release
loads unchanged; one written after it does not load on an older release, which
refuses unknown keys by design (ADR 0007 §6). That direction is correct: a file
declaring a group to a version that would silently ignore it is exactly the
silently-dropped key that refusal exists to prevent.

**Plugins are untouched.** No protocol in `digline.run` changes, so no plugin
needs a release. A third-party `RunAssertion` that does not declare `by_group`
never expands (§6).

## Consequences

**A suite can now be red in a place the pipeline is green.** A document showing
`precision[group=travel] 0.000 / 0.600` beside an exit code of 0 is a new
combination, and the first reaction to it will be that something is broken. It
is not: `compare` has always gated on movement, and a failing check that failed
identically in the approved baseline is a fact somebody already signed. The
report and the README say this in words, because the combination is legitimate
and will otherwise be read as a bug.

**Aggregate counts grow multiplicatively, and the run grid with them.** Two
aggregates over five groups is twelve figures per run where there were two, and
twelve columns in `digline view`'s run list. The arithmetic is free — a
`RunAssertion` is a pure function over verdicts that already exist, and §7's
re-evaluation costs no call to anything — but the *reading* is not, and a suite
with twenty groups will produce a table nobody scans. That is a real limit on
how fine a group should be, and it is a limit of attention rather than of
compute.

**Small groups will error, routinely.** `Recall` over an all-negative group,
`Precision` over a group the system kept nothing from. §8 fixes what that means
and leaves the behaviour alone, but the volume is new: an aggregate erroring was
an event, and under `by_group` it becomes a row.

**The group name is now a public string in a committed file.** Renaming a group
is a `new` plus a `missing` in every comparison until the baseline is
re-promoted, exactly like renaming a case. Somebody will rename one and be
surprised, and the sentence `compare()` prints is already the right one.

**`Case` has acquired its second purely descriptive field**, after `metadata`.
The difference between them is worth keeping straight: `metadata` is payload and
is redacted at a boundary; `group` is read by the suite to build gates and its
*name* travels inside an aggregate's name. A future field that wants to be one
or the other has these two to be compared against.

## Alternatives considered

**A single-group form: `Precision(over=…, group="travel")`.** The obvious API,
and rejected in §5. It buys the ability to watch the groups you already suspect,
which is the ability this feature exists to make unnecessary. Its cost is
silent: the class that degrades is the one nobody listed, and a suite using the
single-group form looks thorough while remaining blind in exactly the place the
whole-run figure was already blind.

**Per-group thresholds.** Tempting, because §8 admits the inherited tolerance
stops speaking on a small group, and because it would let the `classifier` ship
green. Rejected on both counts. It is a second declaration surface — a mapping
from group name to threshold, in data, that has to be kept in step with a set of
groups that comes from the cases — and its failure mode is a group that appears
without a threshold, for which the only answers are "inherit" (which is this
ADR) or "error" (which makes adding a case a breaking change). And in the
`classifier` it would be used to move a bar until a demo passed, which §10 is
about.

**Weighting: a group contributing to the whole-run figure in proportion to
something.** Out of scope by the brief, and it would be a change to what the
whole-run aggregate *means* — the figure that has gated releases
would start answering a different question under an unchanged name and an
unchanged identity. If a weighted aggregate is ever wanted it is a new
`RunAssertion` with its own name, not a mode of the existing four.

**Group hierarchies: `travel/rail`, `travel/air`.** Rejected as a shape, not
just as scope. Nesting means a case is counted in two denominators, which means
two answers to "how many cases did this aggregate consider", which is the one
number ADR 0002 §10 insists never gets separated from the ratio. A hierarchy is
also a second axis wearing a delimiter, and §3's naming form already has room
for a second axis done properly.

**Cross-group comparison: an assertion that `precision[group=a]` is within some
distance of `precision[group=b]`.** A real question — it is the fairness
question — and genuinely a different one. It is a verdict about a *relationship
between two aggregates*, which no current type expresses: a `RunAssertion` maps
outcomes to a verdict, and this maps verdicts to a verdict. It would need its
own ADR, and it would need to answer what happens when one side errored. Refused
here, not refused in principle.

**Making `group` a `Sequence[str]`, so a case can be in several.** Rejected with
hierarchies and for the same arithmetic: a case counted twice makes `considered`
ambiguous. It also makes the expansion's totality harder to state — "every group
present in the cases" is unambiguous over a scalar field and needs a flattening
rule over a list.

**Deriving groups from `Case.metadata` instead of a new field.** The metadata is
already there and already carries `{"quarter": "2026-Q3"}` in the `classifier`.
Rejected because `metadata` is payload — redacted at a boundary under ADR 0002
§2 — and a group name is not: it travels inside an aggregate's name to world 2
by design. Building gates out of a bag whose contents are removed at a boundary
would mean the same suite producing different aggregates depending on where it
was read.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**Expansion stability is a property, tested as one.** The same suite constructed
twice produces the same `config_hash`, the same ordered `run_assertions`, and
the same set of `assertion_id`s — over several shapes: groups in different
declaration orders in `cases.json`, a group whose name sorts before and after
the others, mixed grouped and ungrouped cases, two aggregates over the same
`over`. The names are asserted literally, character for character, because §3
makes them a public format and a test that only checked uniqueness would let the
grammar drift.

**The whole-run identity does not move.** The `classifier`'s `precision` keeps
`31e12a0068b3f1db` with `by_group=True` set, asserted against the literal id, so
§4's exclusion cannot be undone without a test naming what it costs. Beside it:
`config_hash` *does* change, so the pair is checked together and neither can be
satisfied by weakening the other.

**A group vanishing between runs.** Build two runs from suites differing only in
that the last case of a group has been removed, and assert `compare()` reports
that group's aggregates `missing` and nothing else — no `regressed`, no
`errored`, and the whole-run figures untouched. The mirror case for a group
appearing, and the rename, which must produce exactly one `new` and one
`missing`. Beside them the refusal above: the same pair handed to `diff()`
raises, and the test says why rather than merely that it does. Symmetry is
tested on a pair whose group sets agree, in both argument orders, because ADR
0008 §2's promise covers these keys like any other.

**The noise floor is restricted to the group, and demonstrably.** A suite where
one group's cases are unanimous across samples and another's disagree: the
first's interval must be zero-width and the second's wide, from one run. Then
the case §7 chose its filter placement for — a case *outside* a group sampled a
different number of times, or errored on some samples — which must leave that
group's interval intact. That test fails if the filter is moved inside the
aggregate, which is the point of writing it.

**The three shapes of a small group.** An all-negative group makes `Recall`
error and `Precision` not; an empty-kept group makes `Precision` error; and in
both cases `compare` exits 0 and `Headline.unjudged` is unchanged, asserted
directly so §8's "behaviour unchanged" is a test and not a claim.

**The single-group form is refused from both directions.** `Precision(group="x")`
raises `TypeError` in Python, and `group = "x"` in a TOML `[[assertions]]` entry
raises `UsageError` naming the parameters that do exist — the second asserted on
the message, because it is the existing unknown-parameter refusal and the test
is that it reaches this case unchanged.

**`by_group` is inert without groups, and `group` is inert without `by_group`.**
Two runs, one from a suite with `group` on every case and `by_group` nowhere,
one from the same suite with the field removed: identical `config_hash`,
identical run JSON but for the timestamp.

**The example is gated as an example.** `test_examples.py` already runs each
example's whole cycle from nothing; the `classifier` additions ride on it. Added
beside them: the per-class table in the README matches the promoted baseline,
number for number, so the third act cannot rot the way a hand-written table
does.
