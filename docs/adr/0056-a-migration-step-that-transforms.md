# ADR 0056 — A migration step that transforms

- Status: proposed 2026-10-28. One of its clauses, §2, was ruled on 2026-10-28
  by Alessandro Prandini: its rule before this record was written, and its
  boundary after the record was first proposed. Both are stated here as ruled.
  The rest is proposed with the record
- Shipped: unreleased
- Date: 2026-10-28
- Opens: **nothing in the schema.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`,
  and no line of `_STEPS`. This record writes the rule a transforming step will
  be held to, before the first one exists
- Answers: [ADR 0055](0055-a-migration-step-that-renames.md) §2, which says a
  third kind of step exists, that no rule covers it, and that its rule is owed
  before its code
- Assumes: [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (what may ride
  a bump), §2 (absent is how *not recorded* is written; migration stays a
  rewrite), §5 (the refusal is symmetric);
  [ADR 0055](0055-a-migration-step-that-renames.md) §2, §6 and §7;
  [ADR 0024](0024-the-judge-as-an-instrument.md) §4 (the calibration case, the
  first case this rule will meet)
- Touches: nothing in `CLAUDE.md`'s *fixed* section
- Number: 0056. Swept on 2026-10-28, before a line was written, across
  `origin/main` (`fd3f7afe`), the three branches on the remote (`main`,
  `capture` and `quoted-is-written`, whose highest records are 0055, 0023 and
  0054), every worktree of this repository and the open pull requests (none).
  The highest number taken anywhere is 0055

**How to read the clauses.** As in ADR 0055: *derived* names the record it
follows and is checked against it; *ruled* is a decision taken before this
record and transcribed; *new* is decided here and is checked against the code
it cites.

## Context

ADR 0055 §2 named three kinds of migration step: one that adds, one that
renames, and one that **transforms**, computing a new shape from the old one.
It ruled on the second, said that no rule covers the third, and said the
third's rule is owed before its code.

**The relatives that exist.** Of the 18 steps in `_STEPS` at `fd3f7afe`,
seven write a value, and they are the only steps with anything in common with
a transformation:

| step | what it writes | from what |
|---|---|---|
| `4 -> 5` | `suspended: false` on each case | the version: no case was suspended before the field existed |
| `5 -> 6` | `aggregate: []` | the version |
| `6 -> 7` | `artifacts: {}` | the version |
| `7 -> 8` | `target_config: {}`, `judge_config: {}` | the version |
| `8 -> 9` | `samples`, `sample_min`, `sample_max` on a sampled verdict | **derived** from `metadata["scores"]`, which the document already holds |
| `16 -> 17` | a calibration band's `assertion_id` | **derived** from the case's verdicts, and **refused** when they do not say which check it is |
| `17 -> 18` | `projected: false` | the version |

All seven add a key and leave every other one where it was. None writes a new
shape over an old one, so none is a transformation. Two of them derive their
value from what the document holds, and one of those two refuses when it
cannot: `16 -> 17` is the nearest precedent this record has.

That refusal was measured on 2026-10-28 on this tree. A schema 16 run whose
calibration case held two verdicts with different identities, neither named as
the band's check, was migrated with `digline migrate`:

- the run was refused with *"case 'calibration-half-right' carries the
  calibration band of 'llm_rubric', and its verdicts do not say which check
  that is. … the document was not written as it stands, and binding it to a
  guess would state a verdict nobody measured"*;
- the other two documents of the store were migrated, the tally read *"2
  migrated, 0 already current, 1 refused"*, and the command exited 64;
- the refused file was left byte-identical on disk.

**The first case.** The calibration case of ADR 0024 §4 is declared as a band,
`low` and `high` around one fixed answer, and stored as such:
`results[].calibration` carries `assertion_id`, `check`, `low` and `high`,
measured on the one committed baseline that has a calibration case
(`examples/prompt-first`). The answer itself is payload and is not in the
document. Changing that band into a relation between answers is planned for
1.0, and that step would be a transformation. Its shape is not decided by this
record.

## Decision

### 1. What a transforming step is

It **reads one or more paths and writes one path of a different shape**. It
declares the paths it reads and the path it writes, as paths in the schema.

*New*, as a kind. *Derived* in its declaration from ADR 0055 §1 and §7: a step
finds what it touches by its position in the schema, never by a key's spelling,
and declares it as a path. The paths it reads and does not write are removed by
the step, and the declaration names them, so nothing leaves the document
undeclared.

**Its domain is declared too.** A transforming step applies at the positions
where the thing it transforms exists. A case with no calibration band is not a
case whose band is missing: it is outside the step's domain, and the step
passes it unchanged. *New.* The distinction matters for §3 and §6: inside the
domain an input that is absent is refused; outside it there is nothing to
transform.

### 2. When the old value does not determine the new one

**The step does not invent it.** It refuses the document with a sentence that
names what is missing, and writes no default.

*Ruled* by Alessandro Prandini on 2026-10-28, in translation: *"A default put in by a migration
is a silence turned into a value, and it is the defect we are removing from the
product: we do not put it into the mechanism that migrates it."*

It has a precedent in the code: `16 -> 17` refuses exactly this way, by name,
and the file is left as it was (*Context*). And it agrees with ADR 0014 §1's
second condition, *a field whose honest migrated value is a guess does not
ride*.

**When a default is a declaration.** *Ruled* by Alessandro Prandini on
2026-10-28, after this record was first proposed. The reason above was wider
than `_STEPS`, and this is the question that bounds it:

> **What the value states: was it true of that run?** If it was, the default
> is a declaration. If it was not, the default is forbidden, and the step
> refuses, naming what is missing.

**Why the question is put on the fact.** An earlier form of this clause asked
*could the old version have produced another value?* That question reads the
schema, and at a change of schema its answer is always no: the field did not
exist, so the old version could have produced nothing else. A question whose
answer is fixed in advance is not a check. Put on the fact, the question can
answer no.

**Why a false default is forbidden and not merely tolerated.** A default is
not read alone. It is compared with a value recorded by a later run, and a
false one produces a difference that nobody measured: a change reported where
none was established.

**The five steps that write a fixed value, read against the question.** Three
pass, and two are violations, declared.

| step | writes | was it true of that run? |
|---|---|---|
| `4 -> 5`, `_add_suspended` | `suspended: false` | **yes.** No case could be set aside before suspension existed, so none was |
| `5 -> 6`, `_add_aggregate` | `aggregate: []` | **yes.** A run written before aggregates existed declared none |
| `17 -> 18`, `_add_schema_eighteen` | `projected: false` | **yes.** Nothing before schema 18 could write a projection, so the document is not one |

**The declared violations: exactly two, and the count is fixed.** Both are
released, and the question forbids both. They are named here rather than left
among the steps that pass:

| step | writes | what it states, and why that was not true | where the difference is produced |
|---|---|---|---|
| `6 -> 7`, `_add_artifacts` | `artifacts: {}` | *no file under test.* The run had a prompt; nothing recorded it | the artifact deltas of `compare` (`artifact_deltas` in `src/digline/core/compare.py`) give `new` for every file a later run declares, so `artifacts_changed` is true and the report says a file under test changed since the reference; the same `{}` excludes a run from the spread of `digline log` as *testing another prompt* (`_why_not` in `src/digline/report/log.py`) |
| `7 -> 8`, `_add_configs` | `target_config: {}`, `judge_config: {}` | *the target declared nothing.* It had a configuration; nothing recorded it | `compare`, `diff` and the register read it as not recorded, by `config_deltas`' second rule. `digline log` does not: `_why_not` excludes the run from the spread as *asking another system*, and `sighting` reports *declared no configuration* and sends it on the wire as an absence (both in `src/digline/report/log.py`) |

Measured on 2026-10-28: a store written by digline 0.20.0 and migrated to
schema 22, with its baseline's `artifacts` set to the `{}` that
`_add_artifacts` leaves and the suite declaring one file, compared with a new
run: *"1 file under test changed since the reference."*, and `compare --json`
gives `artifacts_changed: true`. The readers, line by line, are recorded in
full in the maintainer's notes, in the record of an empty container read two
ways.

A step added later that the question forbids is refused. It does not join this
list. This clause does not change the two steps: it names them.

### 3. Totality

**Every document the step accepts is transformed, or the step declares which
documents it refuses and why. There is no third outcome, and in particular no
silent one.**

*New.* `8 -> 9` has the outcome this clause forbids a transformation: a verdict
with no `scores` gains nothing, in silence. For a step that adds, that is
right, because the absence already means what the step would add (ADR 0014
§2). For a step that transforms, it would leave the old shape under the new
version number, which the reader at that version does not read: the silence
would surface later, as a reader's refusal far from its cause.

So the three outcomes a transforming step may have are: transformed; refused
with a sentence the step declares; and, at a position outside its declared
domain, untouched (§1). The third is declared, not silent.

### 4. A transformation does not also rename

**The path it writes is a path it read.** If the shape and the name both
change, they are two steps: this one, and a renaming step under ADR 0055.

*Derived* from ADR 0055 §2, checked against its text rather than copied. That
clause says a renaming step *"may not change the value's shape or its meaning
as well. If both the name and the shape change, they are two steps, and each is
held to its own rule."* The mirror holds for a step that reads one path and
writes it back reshaped. For a step that reads several paths and writes one,
it holds when the written path is one of those read: the others are removed,
by declaration (§1). If the written path is none of them, the step has named
something new, and that is a rename; it splits.

One difference from the mirror: ADR 0055 §2 also forbids a rename to change
the value's **meaning**. This record does not forbid a transformation to. What
it forbids is reaching a new value by a default (§2). *New.*

### 5. The direction

**Forward only.** *Derived:* ADR 0014 §5 and ADR 0055 §6. *Measured*, not
asserted, on 2026-10-28 at `fd3f7afe`: a copy of a schema 22 store whose four
documents were marked `schema_version: 23` and nothing else was read by this
tree. `digline list` exited 0 and said the runs were ignored and the baseline
could not be read, advising an upgrade; `digline compare --run latest` exited
64; `digline migrate` refused all four and exited 64; and every file was left
byte-identical. That is the measurement of ADR 0055 §6 again, on the tree this
record is written on, and `src/` and `packages/` did not change between the two.

What a transformation adds to it is not measured, because no transformation
exists: whether the old shape can be computed back from the new one. Nothing in
`_STEPS` goes backwards in any case: `upgrade_document` refuses a document newer
than its reader, and has no step from a higher version to a lower one. A user
who returns to the version before a transforming step is told to upgrade, and
loses nothing on disk; the runs under `*/runs/` are gitignored, so there is no
earlier copy of a migrated run to return to.

### 6. The gate this rule needs

Owed **before the first transforming step lands, in the same pull request at
the latest**. *New.* Proposed form, within the family test ADR 0055 §7
proposes:

- A transforming step declares its nature as *transforms*, with the paths it
  reads, the path it writes, the paths it removes, its domain, and the
  sentences it refuses with.
- The test applies it to documents of its from-version, and each must end in
  exactly one of the three outcomes of §3:
  - **inputs present and determining**: the declared path holds the new shape,
    the paths declared removed are gone, and no other path changed;
  - **an input absent inside the domain**: the step refuses, with one of its
    declared sentences, and the document is left byte-identical;
  - **inputs present that do not determine the new value**: the same refusal
    (§2);
  - **outside the domain**: the document is identical but for
    `schema_version`.
- An outcome that is none of these, or a refusal with a sentence the step did
  not declare, is red.

## Consequences

- The first case will meet §2 at once, if it takes the shape the plan for 1.0
  describes, two fixed answers ordered with a gap. A stored document holds one
  score and a band for a calibration case, and not the answer; nothing in it
  measures a second answer. On that shape the old value does not determine the
  new one, and the step refuses every document with a calibration case. On the
  committed baselines that is one, `examples/prompt-first`'s. This is a
  consequence of §2, not a decision about the calibration case.
- **What the refusal road costs, for whoever decides that shape.** If the
  calibration case takes a shape the band does not determine, the only
  committed baseline refused is `examples/prompt-first`'s, and it is promoted
  again from a new run.
- A transforming step costs a refused document a decision by a person, as a
  `_NON_ADDITIVE` row does: re-run and re-promote, or keep the version that
  reads it.

## Alternatives considered

- **Write a default when the old value does not determine the new one.**
  Refused by §2, as ruled.
- **Skip what cannot be transformed, and leave it in its old shape.** Refused
  by §3: the reader at the new version would refuse it later, far from the
  step.
- **Treat a transformation as a passenger under ADR 0014 §1.** That rule is
  for a field that arrives. A transformation replaces one, so the question it
  must answer, what happens to the old shape, is not one §1 asks.

## Not decided here

- **The shape of the calibration case after 1.0.** ADR 0024 §4 describes it as
  a band, and today's code is that band (`CalibrationBand` in
  `src/digline/core/calibration.py`, refusing anything but
  `0 < low <= high < 1`). Its replacement is decided with its own record.
- **Whether a transformation may be undone.** Nothing goes backwards (§5).
