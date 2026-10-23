# ADR 0053 — A promotion refuses a pin nobody named

- Status: proposed 2026-10-23. The decision below was ruled on 2026-10-22 and
  narrowed on 2026-10-23 by Alessandro Prandini, on #483's promotion half,
  before this record was written. It is written with the code that implements
  it, in the same pull request
- Shipped: unreleased
- Date: 2026-10-23
- Opens: **nothing in the schema.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`.
  `compare --json` gains one key, `unjudged_causes`, recorded in
  `digline.wire.contract`'s `_ADDED` as every added key is
- Amends: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §8, which
  gains condition 11 and a dated note on *"checked **last**"*;
  [ADR 0051](0051-a-pinned-path-the-run-no-longer-records.md) *Context*, on
  *"a pin never blocks a promotion"*; and
  [ADR 0029](0029-the-artifact-that-must-not-drift.md) §10, *What does not
  move*. Each carries a dated note pointing here and is kept as written
- Assumes: [ADR 0029](0029-the-artifact-that-must-not-drift.md) §6 (a drifted
  pin returns 2, and a regression outranks it);
  [ADR 0051](0051-a-pinned-path-the-run-no-longer-records.md) §3 (a lost pin
  returns 2); [ADR 0049](0049-a-run-that-judged-nothing-does-not-pass.md) §5
  (a run that would exit 2 for a cause read from the run alone is already
  refused at promotion, and the precedent for doing it in general);
  [ADR 0031](0031-the-reference-promote-replaces.md) §2 (condition 8, beside
  the write)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 — *no
  vacuously green assertion* — is the reason: a pin whose drift was made the
  reference without anybody naming it is a declared control that went green
  because somebody promoted
- Number: 0053. Swept on 2026-10-23, before a line was written, across
  `origin/main` (`18f99c7`), every local and remote branch and tag (106 refs,
  after a fetch with `--prune`), the worktrees of this repository and the open
  pull requests (none). The highest number taken anywhere is 0052

## Context

*digline#483, its promotion half.*

**What a pin did at promotion.** A pinned file that drifted, or a pin that lost
its path, makes `compare` exit 2 (ADR 0029 §6, ADR 0051 §3). `promote` read no
comparison: its conditions answered from the run document and from whether the
baseline had moved (ADR 0002 §8), so it promoted such a run as it promoted any
other. The next comparison was then green, and nothing recorded that anybody
had looked at the file. Accepting a drift was done by promoting, in silence.

**Measured, not read.** On `18f99c7`, a reference that pins one file, and a
run in which that file's text changed: `digline promote --replacing <the
reference>` exited 0 and moved the baseline, and the `POST /promote` of
`digline view --allow-promote` answered *"Baseline set to …"*. Both are the red
half of the tests this record's code ships with,
`tests/test_promote_accepting_pin.py`, at `8eb4241`.

**The other three causes of 2 were already refused.** A case that could not be
judged is condition 3, a calibration case outside its band is 5, and a run that
judged nothing is 10. Each answers from the run alone. The two pin causes are
the ones that do not: they are relations, and need the reference.

## The decision

*Ruled 2026-10-22; narrowed 2026-10-23.*

1. **A promotion is refused while a pin is a cause of 2**, a drifted pin or a
   lost one, read against the baseline the promotion replaces. **Any cause, not
   the code**: in `exit_code` a regression or a moved canary returns 1 and
   outranks every cause of 2, so a run that drifted and got worse exits 1. Its
   drift is no less there, and it is refused too.

2. **The way past is to name the paths.** `digline promote --accepting-pin
   PATH`, once per path; `accepting_pins` on `promote_baseline`, `host.promote`
   and `promote_priced`. It must be **exactly** the set the pin causes
   implicate. A drifted pin implicates its own path. A lost pin implicates both
   halves, the path the reference pinned and the run no longer records and the
   pinned path with no reference, because nothing in either document says
   whether one became the other. One path more, one fewer or another is
   refused, and the refusal names the set. A path named where nothing is
   implicated is refused too: an authorisation names what moved.

3. **The authorisation is announced, not recorded.** `promote` prints which
   paths it accepted, on the line after the one that says the baseline was set.
   Nothing is written into the reference.

4. **One source for the causes, in `core`.** `causes_of_two(run, comparison,
   declared=...)`, in `digline/core/gate.py`, returns every cause that holds.
   `headline()` puts it on the headline as `unjudged_causes` and derives the
   four cause flags from it. `exit_code` reads that field behind a regression,
   and `run_exit_code` calls the function with no comparison. The write step
   calls it against the baseline it read. `unjudged` stays a count, because the
   sentence and the wire carry the number, and a test holds it to the tuple:
   `unjudged` is among the causes exactly when the count is above zero.

5. **Condition 11, in the write step, after 8.** `refusals_for` does not
   change. The backend calls `refusal_for_unaccepted_pins(run, current,
   accepting, declared=...)` with the baseline it read for 8, and raises what it
   returns. The type is `UnacceptedPinsError`.

## Why the responsibility is split

**Three causes in `refusals_for`, two in the write step.** `refusals_for`
answers from what a function holding the run, the configuration hash and the
declaration can answer. That is what lets every backend call it rather than
restate it, and what lets it be tested without a store. A case that could not
be judged, a lost scale and a run that judged nothing are facts about the run
alone. They were conditions 3, 5 and 10 before this record, and they stay
there.

The pin causes are relations. A drift is the run's file against the
reference's, and the reference is the baseline in the store **at the moment
of the write**. Passing a baseline into `refusals_for` would make it read a
reference somebody fetched earlier, and the promotion would be judged against
a reference that may already have moved. That is the reason condition 8 is not
in `refusals_for` either (`store/promotion.py`'s docstring). So 11 sits beside
8 and after it. 8 asks whether the reference moved since the person compared,
and if it did, a drift read against it would name paths nobody saw. Once 8
holds, the baseline it read is the one the person compared against, and 11 is
asked against that.

**And the set is still one set.** The split is about where each cause is
*refused*, not where it is *defined*. `causes_of_two` defines all five, and
the write step reads the pin causes from it, so a sixth cause added there
reaches `exit_code` and the write step at once. Whether a new cause belongs in
`refusals_for` or beside the write is decided the same way: from the run
alone, or against the reference.

## Consequences

**For anyone who pins a file.** Accepting a drift used to be done by promoting,
silently. It is now declared: `--accepting-pin` with each path, and `promote`
says what it accepted. A script that promoted after every change to a pinned
file now meets exit 64 and a refusal that prints the command to run.

**`digline view`'s button refuses, by choice.** The form carries no
authorisation, and it will not gain one: a click is not a statement about which
files moved. A run with a pin cause is refused there, and the refusal is the
same sentence the command line prints. It names the command, the flag and each
path. The button is still drawn on such a row. The runs page decides from the
run alone (its configuration and its errored cases, `_actions_cell` in
`digline/report/pages.py`), and a pin cause needs the reference, so the refusal
arrives after the click.

**For a backend.** `promote_baseline` gains `accepting_pins`, defaulted to an
empty set. The default is the prudent answer: accepting nothing refuses every
pin cause. A *caller* that does not pass it keeps working.
`packages/pytest-digline/tests/_cycle.py` is one, and is not touched. An
*implementer* without the parameter does not keep working. pyright no longer
accepts it as a `ResultStore`, and `host.promote` passes the argument every
time, so it raises `TypeError` there. A mandatory parameter would have broken
it the same way. `tests/_protocol_store.py`'s `MemoryStore` is the instance in
this repository, and it took the parameter. Condition 11 is an obligation of
the same kind as 8: `tests/test_promotion_conditions.py` walks the backends in
this repository for it, and the protocol's docstring states it for any other.

**For anyone who builds a `Headline` by hand.** `unjudged_causes` is
mandatory, because no default is safe. An empty tuple would let a headline with
`unjudged=3` exit 0. A construction that omits it raises `TypeError`.

**The version.** `RELEASING.md`, *Choosing the version*: *"Before 1.0, the
**minor** number moves when something a user relies on stops working as it
did: … an exit code changed …"*. `promote` exits 64 on a run it promoted with
0, so this is a minor. It shares the cut with #654's, which is a minor for the
same clause.

## Not decided here

- Whether `--accepting-pin` should also be recorded somewhere a later reader
  can find it without the promoting terminal's log, such as the register or a
  commit message. It is announced, and that was the ruling.
- A page that marks, before the click, a row the store will refuse for a pin.
  That would need a comparison per row.
