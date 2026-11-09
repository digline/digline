# ADR 0059 — The import of recordings: a reviewed answer, a grouped listing, a source declared as data

- Status: accepted 2026-11-03, by Alessandro Prandini, the text first, as it
  stands at `c1cfa94a`: every item marked *decided here* taken, with the
  recommended names (`ReviewedAnswer`, `--good` and `--bad`).
  Proposed 2026-11-03. **Its decisions were ruled before this record
  was written**, on 2026-11-03, in the conversation of the session that wrote
  it, after a pass as a user over `digline record import`. They are stated
  here as ruled. **What this record adds is marked *decided here***: the name
  of a new kind of case, the names of two flags, a suite field and two details
  of the import. Each was proposed, for acceptance to take or remove item by
  item
- Shipped: 1.1.0
- Date: 2026-11-03
- Opens: **nothing at this record's landing.** No `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`, no `RECORDING_VERSION` and no line of `_STEPS`. What the
  new kind of case owes in the run document is the implementation's question,
  named in *Not decided here*
- Amends, each by a dated note beside the place it amends, which points here.
  Every text is kept as written:
  - [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
    §7, the `label` compartment as the person's yes or no at the import (§1);
  - [ADR 0023](0023-capture.md) §11, item 1, by one sentence (§2); §4, by one
    sentence (§3); §3, and the question its *Not decided here* left open on
    `repository` (§4);
  - [ADR 0024](0024-the-judge-as-an-instrument.md) §4, which **does not
    change**: §1 sets a section beside it, and the note says so;
  - [ADR 0007](0007-the-declarative-suite-format.md) §7, whose rule for
    `Disclosure` stands, and which no longer covers a capture source (§4)
- Assumes: [ADR 0023](0023-capture.md) §4 and its ruling 6 (two invocations,
  no dialogue), §5 (the expected is the person's, never derived), §8 (a regime
  declared, never looked up), §9 (the watermark `examined_through`);
  [ADR 0024](0024-the-judge-as-an-instrument.md) §4.1 (a fixed answer, the
  target never called), §4.3 (only the named check runs), §4.4 (excluded from
  metrics, included in everything that reports);
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §2 (a case of a kind of its own) and §3 (in the gate, out of the aggregate);
  [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
  §4 (the import refuses another tenant), §5 (the episode), §7 (what the format
  foresees)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 9 is not
  touched, for the reason ADR 0023's *Touches* gives (*What does not change*).
  Decision 3 is upheld: a case of the new kind fails when the judge
  contradicts the person
- Number: 0059. Swept on 2026-11-03, before a line was written, across
  `origin/main` (`80cf7557`), whose highest record is 0058; the two other
  branches on the remote, `capture` (`f51e437f`, highest 0023) and
  `schema-23-trajectory` (`cd71a383`, highest 0057); every worktree of this
  repository; and the open pull requests, of which #869 is the only one and
  adds no record. The highest number taken anywhere is 0058
- Owed: the three lines on digline.dev that every new record needs (the nav,
  and the two tables the site builds its pages from). Until they land, the
  `docs` job reads red on this record's pull request, which is the state the
  site's runbook expects, and no required check reads it

**How to read the clauses.** *Ruled* is a decision taken before this record
and transcribed. *Decided here* is a name or a detail this record proposes,
and acceptance rules on it.

## Context

ADR 0058's import shipped narrow in 1.1's second piece:
`digline record import --tenant T --suite S` lists, and a second invocation
with `--positive ID` and `--negative ID` writes the cases named, each with the
label given, into the file the suite's `CaptureSource` names. A pass as a user
over it, on 2026-11-03, found three places where the import says something
other than what the person means.

**The yes or no is written where it means something else.** The import writes
the person's answer as `Case.label`, and `Label` is
`Literal["positive", "negative"]` (`src/digline/core/aggregate.py:48`): the
**class of the input**, where the suite has ground truth, read by an aggregate
that counts a confusion matrix. The person at the import does not say which
class an input belongs to. They say whether the recorded **answer** is good.
ADR 0058 §7 made the two one datum, from a collision of names, and the pass
showed that they are two.

**The listing is a list.** It prints every case in the files' order, which is
honest, and it gives a person in front of two hundred recordings nothing to
see them by.

**The source can only be Python.** A suite written as `suite.toml` cannot
declare `capture`. `src/digline/host/toml_suite.py:200` refuses it, citing
ADR 0023 §3, and ADR 0023's *Not decided here* left open the question of
whether `repository` must stay in Python.

## Decision

### 1. The yes or no at the import is a reviewed answer, not `Case.label` — ADR 0058 §7 amended

*Ruled.* **The yes or no a person gives a recorded answer at the import makes
a case of a kind of its own**, with the mechanics of ADR 0024's calibration
case and a verdict of its own:

- **the answer is fixed**: the recorded response, which the person read. The
  target is never called for the case (ADR 0024 §4.1);
- **only the judged check it names runs on it** (ADR 0024 §4.3);
- **the expected verdict is the person's**: for a yes the check passes, for a
  no it does not;
- **a judge that contradicts the person fails the case.** It is a failure of
  the case, in the gate, and not `scale_lost`;
- **it is kept in the gate and out of the aggregate accuracy**, the split ADR
  0037 §3 rules for the recalled kind and ADR 0016 §2 for the canary. ADR 0037
  §2 is the precedent for a case of a kind of its own: *"It is a different
  kind of case, and digline knows it, not only records it."*

**ADR 0024 §4 does not change.** A calibration case is an answer known to be
*partially* correct, placed in a band that lies strictly between 0 and 1
(`src/digline/core/calibration.py:87`). A band that touches an extreme cannot
see a judge collapsed onto it, which is what that case exists to see. A yes or
a no asks for exactly that extreme, so it is not a calibration case and is not
written as one. This kind is set **beside** §4, and §4's note says so.

**What the run counts, in one line.** The run counts these cases by direction,
apart from `Accuracy`: the judge passed an answer the person said no to, and
the judge failed an answer the person said yes to.

*Noted 2026-11-04, by the maintainer's ruling; the section above is kept as
written.* **A run with a contradiction is not promoted.** `promote` refuses it
as it refuses a lost scale, naming each case and which way the judge went:
*a baseline where the judge contradicts the person is not a baseline*. The
person's yes or no is the expected verdict, and a reference scored by a judge
that gave the other would be held against every later run for as long as it
stands. It is promotion's condition 12 in [ADR 0002](0002-three-worlds-and-where-the-data-lives.md)
§8, after 5, the lost scale, which is the judge's other fault. This record
said nothing of promotion, and the implementation of 2026-11-04 (#903) left
it unchanged; the ruling closes that.

*Noted 2026-11-05, by the maintainer's ruling; the section above is kept as
written.* **A suite that calls no target may declare none.** The answer is
fixed and the target is never called for a reviewed answer, nor for a
calibration case, so a suite made of the two kinds alone, which is what the
import writes into a suite declared for it, may leave its target out, in
`suite.py` or as `[target]`. The run, the re-judge and the promotion treat it
as any suite. A case the target answers needs one, and the suite is refused
when it loads, naming that case: the sentence says why a target is needed now.
And **a suite that declares a capture may hold no case yet**, since the first
import is what writes them; its run judges nothing and exits 2. Measured on
the driver: a calibration case is not called for either, so the rule names
both kinds where the ruling named reviewed answers.

*Amended 2026-11-05, by Alessandro Prandini's ruling (P-1530), the section
above kept as written.* **An episode's reviewed answer carries its steps, and
the suite's trajectory checks run on it.** *Only the judged check it names
runs on it* is narrowed for an answer the import took from an episode: the
person read a turn, and a turn is its answer and the steps it took to it. So
`ReviewedAnswer.steps` holds that episode's trajectory, in the run document's
form, and the suite's checks on a trajectory (`ToolsCalled`, `ToolCalledWith`,
`Subsequence`, `Before`, `Never`, `MaxSteps`) run on the case beside the
named check. **On a yes, a red one is a contradiction**, counted and refused
by `promote` as the named check's is: a person who said yes to the turn said
yes to its steps. On a no they decide nothing, because a no does not say
which part of the turn was wrong. An answer without steps, a single call's or
one written before this amendment, is asked its check alone, as before. The
import writes the steps of the newest recording of the answer under the setup
in force, the setup ADR 0058 §8's `episode_setup` gives an episode, or of its
first recording where none is under it.

**`Case.label` is the class of the input, and the import no longer writes
it.** The suite's author writes a label where the suite has ground truth.
ADR 0023 §5's rule stands as it is: a capture writes one only from a total
mapping the source declares.

*Decided here, the name of the kind.* Two candidates:

- **`Case.reviewed_answer: ReviewedAnswer`, recommended**, with `output`, the
  recorded answer; `check`, the judged assertion it is for; and `good: bool`,
  the person's yes or no. It says what the case is: an answer, reviewed by a
  person. `review` is also the word for ADR 0037's served page. The kind there
  is *recalled*, so the two do not collide, and a person reviewing an answer is
  what both describe;
- `Case.person_verdict: PersonVerdict`, with the same three fields. It names
  the person outright, and it reads as the core's `Verdict`, which is an
  assertion's result and never a person's.

Neither reuses *calibration*, *positive*, *negative* or *expected*.

*Decided here, the flags.* `--positive` and `--negative` are renamed, because
those words are now the class of the input:

- **`--good ID` and `--bad ID`, recommended.** They say that the answer is
  judged, not the input;
- `--accept ID` and `--reject ID`, not recommended. *Accept* reads as the
  approve side of `promote`, which a case written at the import is not
  (ADR 0023 §1).

*Decided here, two details the kind needs.* **The check** is declared by the
source, as `check`, the name of a judged assertion of the suite, and a source
that writes reviewed answers without one is refused by name. **The person's
mark** is `--by NAME` on the writing invocation, and it is mandatory. It is
never read from git's configuration or from the environment: a name taken from
a machine is inferred, and the mark is the person's own.

### 2. A yes becomes an expected only where the suite declares it — ADR 0023 §11, item 1, amended

*Ruled.* Where a suite declares that its output is deterministic, a yes
**also** writes `expected`, the recorded answer, with the person's mark beside
it. A no never writes an expected: *not this answer* names no answer. Nowhere
is it inferred.

**How a suite declares it today: it cannot.** What exists is a check's `KIND`,
`"judged"` or `"deterministic"` (`src/digline/core/assertions.py:240`), which
says how a check scores and nothing about the target. *Decided here, proposed:*
`Suite.deterministic_output: bool = False`, settable in TOML and in Python,
outside `config_hash` like `capture`. It is **never deduced from the checks'
`KIND`**: a suite of deterministic checks over a sampled model has a
deterministic check and a non-deterministic output. Acceptance takes it or
removes it. Removed, a yes writes no expected anywhere.

**ADR 0023 §11, item 1, gains one sentence:** *"An expected a person named at
the import, in a suite that declares `deterministic_output`, carries that
person's mark and is not inferred: the person said that this answer is the
answer."*

### 3. The listing groups and counts, and never ranks or proposes — ADR 0023 §4 amended

*Ruled.* `digline record import --tenant T --suite S` groups the recordings not
yet examined **by the shape of their output**, and prints each group with its
count. Inside a group the order is the files' order. Nothing is ranked, and no
criterion is suggested: no *this looks like a no*.

*Decided here, the shape:* the triple (`OutputKind`, `finish`, the actors of
the steps in order, for an episode).

- `OutputKind` is the core's own classification of an output, `"text"`,
  `"structured"` or `"conversation"` (`src/digline/core/types.py:134`). It is
  read, not invented for the import.
- `finish` is the step's, where a step carries one. A single call's
  `RecordedResponse` carries no `finish` until ADR 0057's schema 23, so until
  then a single call's shape is its `OutputKind` alone.

**ADR 0023 §4 gains one sentence:** *"Where the material is recordings, which
carry no verdict and no label to pair, the listing groups by the shape of the
output — the core's `OutputKind`, the finish, and an episode's actors in order
— and prints each group's count, in the files' order and never ranked."*

*Noted 2026-11-05, by the maintainer's ruling; the section above is kept as
written.* **The setup in force is per form**, the partition the groups are
first made in: the newest eligible recording among the episodes for an
episode's answer, among the single calls for a single call's, and each group
says under its heading which setup is in force there. The listing's head no
longer names one setup. Measured on a Node application (P-1518): a turn
recorded last as an episode put every single call under an earlier setup, so
the same answer was not electable in the suite's listing and was written from
`--from _unassigned`, where no episode was. Two SDKs asked the same question
still give two setups, by their default fields: that is the setup's identity,
and it is not changed here.

### 4. The source is declared as data too — ADR 0023 §3 amended, and its open question decided

*Ruled.* A `[capture]` table in the suite's TOML file declares `cases_file` and
`repository` (`"private"` or `"public"`). `Suite.capture = CaptureSource(...)`
stays, for a suite written in Python.

**ADR 0023 §3 said the declaration is code.** It is amended: the declaration is
code only where it carries a reader, and `[capture]` carries none. §3 gave two
reasons. The first, *a reader is a function*, has no subject here: the
recordings are read by digline. The second is ADR 0007 §7's ceremony, which
asks for *"a change somebody wrote"* and a reviewer saw. **A table in a
versioned, reviewed file is that change as much as a line in `suite.py` is.**
And the template copied to a client it is false for is copied in Python exactly
as in TOML. The risk is symmetric, so it is not an argument for code.

**ADR 0023's *Not decided here*, *"Whether `repository` stays in Python even
once the reader is data"*, is decided by this section: it does not.** The
remedy for the copied template is a rule, in both forms:

- **`repository` is mandatory, with no default**, in TOML as in Python;
- **`"public"` refuses** to write, as it does today;
- **every writing invocation prints the whole declaration**, tenant, suite,
  `cases_file` and `repository`, before the line of each case it writes, and
  **the listing prints it at its head**. A copied declaration is then in front
  of the person at every use, and not only on the day the suite was written.

**ADR 0007 §7 stands for `Disclosure`**: a data suite still discloses nothing
beyond the verdict. Its note says that a capture source is no longer under
it, and why. `src/digline/host/toml_suite.py:200` changes with the code, not
with this record.

## What does not change

- **Two invocations, no dialogue** (ADR 0023 §4 and its ruling 6): one lists
  and writes nothing, the other writes the cases named and no other.
- **The watermark `examined_through` is written in the case** (ADR 0023 §9),
  the newest `recorded_at` the person was shown, and it is still the import's
  only memory.
- **`"public"` refuses** to write, naming the regime (ADR 0023 §8).
- **A suite that declares a source and does not load its file is refused when
  it is loaded**, naming the cases it left out. TOML or Python, the refusal is
  the same.
- **The case written carries `vars` and the person's mark, and never an
  `expected` unless the suite declares `deterministic_output`** (§2, ADR 0023
  §11 as amended).
- **An episode is one case.** Its id is `capture_id` of the `case=` it was
  opened with, and its recording keeps the episode id of its own, by which its
  calls are joined (ADR 0058 §5).
- **The import refuses another tenant's recordings** before anything is shown
  (ADR 0058 §4).
- **Fixed decision 9 is not touched.** ADR 0023's *Touches* gives the reason,
  and it holds here unchanged: the import writes inside the perimeter, and
  nothing it writes reaches the wire. A `[capture]` table moves where the
  declaration is written, not what crosses.

## Consequences

**A suite gains a kind of case that measures the judge against a person**, on
answers the application actually gave. A regression of the judge fails the
gate, and the accuracy of the suite's own cases is not diluted by them.

**The import's vocabulary changes before 1.1 ships.** `--positive` and
`--negative` were never released: `digline record` arrives with 1.1, and the
newest tag on the remote, read on 2026-11-03, is `v1.0.3`. So the rename
breaks no user.

**A suite written as data can import recordings**, at the cost of reading its
own declaration every time it writes.

## Not decided here

- **What the run document records of a reviewed answer**: whether the kind
  needs a key in the run, and so a schema bump, or rides an existing one.
  That is the implementation's measurement, and it waits for the code.
- **How the run shows its count** of the two directions: §1 rules that it is
  a count of its own, not where it is printed.
- **A reviewed answer in a suite with no judged check.** §1 refuses a source
  without `check`. Whether a no can be anything in such a suite is left
  open.
