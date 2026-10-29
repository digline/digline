# ADR 0055 — A migration step that renames

- Status: proposed 2026-10-28. Two of its clauses, §3 and §4, were ruled on
  2026-10-28 by Alessandro Prandini before this record was written, and are
  stated here as ruled. The rest is proposed with the record
- Shipped: unreleased
- Date: 2026-10-28
- Opens: **nothing in the schema.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`,
  and no line of `_STEPS`. This record writes the rule the first renaming step
  will be held to, before that step exists
- Amends: [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1, by a dated note
  beside it that points here. Its text is kept as written
- Assumes: [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (what may ride a
  bump, and the second condition: migrate additively, without inventing), §2
  (absent is how *not recorded* is written; migration stays a rewrite, not a
  read), §5 (the refusal is symmetric);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §11 (a migration
  that derives rather than invents);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §17.3 (the form
  that stands in for a foreign verdict's metadata value)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 2 is where the
  document lives, and nothing here moves it
- Number: 0055. Swept on 2026-10-28, before a line was written, across
  `origin/main` (`3e399566`), the two branches on the remote (`main` and
  `capture`, whose highest record is 0023), every worktree of this repository
  and the open pull requests (none). The highest number taken anywhere is 0054

**How to read the clauses.** Each one says where it comes from:
*derived* names the record it follows and is checked against that record;
*ruled* is a decision taken before this record and transcribed; *new* is
decided here and is checked against the code it cites.

## Context

Every step `digline migrate` has ever run adds. `_STEPS` in
`src/digline/store/migrate.py` holds 18 steps, from `4 -> 5` to `21 -> 22`,
read at `3e399566`:

- **7 write a value**: `4 -> 5` (`suspended`), `5 -> 6` (`aggregate`),
  `6 -> 7` (`artifacts`), `7 -> 8` (`target_config`, `judge_config`), `8 -> 9`
  (`samples`, `sample_min`, `sample_max`, derived from `metadata["scores"]`),
  `16 -> 17` (a calibration band's `assertion_id`, derived from the case's
  verdicts) and `17 -> 18` (`projected`);
- **11 write nothing**: `9 -> 10` to `15 -> 16`, and `18 -> 19` to `21 -> 22`.
  Each exists so that the absence of an entry keeps meaning *not additive*.

**None removes a key, and none renames one.** ADR 0014 §1 is the rule for what
may ride a bump, and it is written for passengers: a field that arrives, with a
value the old document already justifies. It does not say what a step may do
to a key that is already there.

The name pass made that the next question. On 2026-10-28 Alessandro Prandini
ruled that the boolean `withheld` becomes `redacted` where it means *this was
kept back*, and three of the places it is written are in the stored document,
not only on the wire. Measured at `052a769a` on the eleven committed baselines,
their redacted and projected forms, and one fresh run:

| where, in the stored document | written by | form |
|---|---|---|
| an artifact's entry, `artifacts.<path>.withheld` | `_artifact_to_dict` | `true`, present only when withheld |
| a recorded response, `results[].responses[].withheld` | `_response_to_dict` | `true`, and the entry carries nothing else |
| the value that stands in for a foreign verdict's metadata under a projection, `results[].verdicts[].metadata.<token>` | `project`, through `WITHHELD_METADATA` | the object `{"withheld": true}` |

The second row is read from the code only: no measured document held a
withheld response. The same ruling leaves the **list**
`target_config.withheld` / `judge_config.withheld` as it is, and that list is
spelt with the same word.

So schema 23 would carry the first step that renames, and the rule for it is
written here, before the code.

## Decision

### 1. What a renaming step does

The value already exists; only its name changes. The step reads the old key,
writes the new one, and carries the value **unchanged**. It computes nothing
and supplies no default.

*Derived:* ADR 0014 §1's second condition, and ADR 0006 §11 — *a value the old
document already justifies*, *derived, not invented*. Carrying a value
unchanged is the limit case of deriving one.

**The step finds the key by its position in the schema, never by its
spelling.** *New.* The table above is why. `withheld` is spelt the same in the
list of a configuration, which this step must not touch, and a foreign
verdict's metadata value is the verdict's author's payload in a document that
is not a projection: a third-party assertion may write `{"withheld": true}` as
its own value, and renaming it would rewrite what that assertion measured. The
stand-in exists only where `projected` is `true`, on a verdict whose `origin` is
not `builtin`, under a key that is not one of the driver's own. That is where
`project` writes it (`_withhold_foreign`), and a projected `Run` checks it on
its foreign verdicts when it is built (`_check_projected`), which is what
`run_from_dict` builds.
A renaming step addresses that position and no other.

### 2. What a renaming step may not do

It may not change the value's **shape** or its **meaning** as well. If both the
name and the shape change, they are two steps, and each is held to its own rule.

*New.* The reason is that a rename can be checked on its declared paths alone
(§7): the value there is the same before and after. A step that also reshapes
cannot be checked that way.

**What this record does not cover.** There is a third kind of step, besides one
that adds and one that renames: one that **transforms**, computing a new shape
from the old one. §1 forbids a renaming step to compute, and ADR 0014 §1 is
written for a field that arrives, so no rule covers such a step today. This
record does not write that rule. The first case is the calibration band,
`{check, low, high}` in `results[].calibration`, if it becomes a relation
between two answers instead of an absolute band, and **its rule is owed before
its code**.

### 3. A document where the key is absent

**It stays absent.** The step does not invent it.

*Ruled* by Alessandro Prandini on 2026-10-28: *"A migration that turns a
silence into a value is the defect we are removing from the product, and we do
not put it into the mechanism that migrates it."* It agrees with ADR 0014 §2,
where absent is how *not recorded* is written, and every step that writes
nothing already keeps that meaning.

For the three places above, absent is also the common case: an artifact's and
a response's `withheld` are written only when `true`, and the stand-in exists
only in a projection.

### 4. A document that carries both names

**It is refused, and no name is chosen.** The file is left as it was.

*Ruled* by Alessandro Prandini on 2026-10-28: two names for one meaning is
exactly the contradiction the name pass removes, and preferring one in silence
would hide it.

No writer produces such a document: before the step only the old name exists,
and after it only the new one. So a document that holds both was not written as
it stands, which is the condition the refusal in `16 -> 17` already names
(*"the document was not written as it stands"*). The refusal goes where that one
goes: a `NonAdditiveError` naming the document and the position, which
`migrate_paths` counts as refused and moves past. Measured on schema 23
documents read by this tree and by digline 0.35.0, a refused document is left
**byte-identical** on disk.

The refusal applies **at the position of §1**. Inside a metadata value that is
not the stand-in, both names are payload and are not read.

### 5. The old name after the step

**Removed, not kept as an alias.**

*New.* This is the clause ADR 0014 §1 does not cover, because there passengers
migrate by being added. An alias would make the reader accept two names for one
meaning, which is what §4 refuses on the way in. The reader at the new version
reads the new name only, as it reads every key at exactly one version.

### 6. The direction

**Migration runs forward only.** *Derived:* ADR 0014 §5, which made the
refusal symmetric. *Measured*, not asserted: on 2026-10-28 a copy of a
schema 22 store had its four documents marked `schema_version: 23` and nothing
else, and was read by this tree at `3e399566` and by digline 0.35.0 installed
from PyPI. Both read schema 22, and both answered the same way:

- `digline list` exits 0, lists no run, and says *"ignored: 3 run(s) at schema
  23"*, that the baseline *"could not be read: schema_version 23 is not
  supported (expected 22). Upgrade digline to one that reads it"*, and
  *"upgrade digline to read them: a newer document cannot be rewritten
  backwards without discarding what the newer schema added"*;
- `digline compare --run latest` exits 64 with the same advice;
- `digline migrate` refuses all four documents, *"the document declares schema
  23, which is newer than this version understands (22). Upgrade digline
  instead"*, exits 64, and leaves each file byte-identical.

So a user who returns to the version before a renaming step is told to upgrade,
and loses nothing on disk. What they cannot do is read the migrated documents
with that version: nothing migrates a document backwards. A committed baseline
can be restored from git; the runs under `*/runs/` are gitignored and have no
earlier copy.

A user further back is told something else, and nothing this record does can
change it, because the sentence is printed by their binary (ADR 0014 §5). On the
same day digline 0.20.0, which reads 16, met a store migrated to 22:
`digline compare` advised *"Run `digline migrate`"*, the advice for the other
direction, and `digline migrate` refused each document with *"Upgrade digline
instead"*.

### 7. The gate this rule needs, and that it does not yet have

A rule that only a reviewer reads is a convention. This one owes a check, and
the check is **owed before the first renaming step lands, in the same pull
request at the latest**. *New.* Proposed form:

- **Every entry of `_STEPS` declares its nature**: it *writes nothing*, it
  *adds*, or it *renames*. A renaming step declares each pair it renames as
  **two paths in the schema**, the old and the new, never as two names.
- **One test reads `_STEPS` as a family.** Each step is applied to a document
  of its from-version that carries every path the step can touch, and to one
  that carries none of them, and is held to its declared nature:
  - *writes nothing*: the document is identical but for `schema_version`;
  - *adds*: every path before is still there, with its value unchanged;
  - *renames*: the test compares the document before and after **on the
    declared paths**. The value at each new path equals the value at its old
    path (§1, §2). The old path is gone (§5). No other path changed. And every
    position that carries the old name and was not declared still carries it
    where it did.
  - The document without the key comes out identical but for `schema_version`
    (§3). A document with both names at a declared position is refused and
    left as it was (§4).
- **A step that declares no nature, or declares one it does not keep, is red.**

**Why paths and not names.** A comparison of the sets of key names cannot hold
§1. `withheld` is written at four positions in the stored document and three of
them are to be renamed. A step that renamed the wrong one would still leave the
name `withheld` in the document, because the configuration's list keeps it, and
a comparison of names would pass. Declared paths, and the undeclared positions
checked to be untouched, are what catch it.

Today nothing reads `_STEPS` as a family. Each step is tested where its field is
(`tests/test_calibration.py` for `16 -> 17`, `tests/test_noise_floor.py` for
`8 -> 9`, and so on), and no test names `_STEPS`.

*Noted 2026-10-29 (#803), and the paragraph above kept as written: it was true
on 2026-10-28.* The gate is paid. Every entry of `_STEPS` declares its nature,
with its paths as `SchemaPath`s, and `tests/test_migration_steps.py` reads
`_STEPS` as a family. No step in `_STEPS` renames, so the renaming half is run
on a renaming step built in that test, and on a broken copy the same checks
must refuse.

## Consequences

- Schema 23's renaming step, when it is written, follows §1 to §6 and arrives
  with §7's gate. The three places in *Context* are the first instance.
- A rename of a key in the stored document is no longer free to be read as
  *additive*. It has its own family, and the family is checked on its declared
  paths.
- A step that transforms is covered by no rule, this one included, and its rule
  is owed before its code (§2). The calibration band is the first case.
- What a rename costs a user is §6: one more step forward, and no road back
  with the version before.

## Alternatives considered

- **Keep the old name as an alias**, read by the new reader beside the new one.
  Refused by §5: it makes two names for one meaning the reader's normal case,
  which is what the name pass removes.
- **Find the key by its spelling**, everywhere in the document. Refused by §1:
  it would rename the list of a configuration and a third-party assertion's
  payload.
- **Prefer one name when both are present.** Refused by §4, as ruled.
- **Migrate on read.** Refused again for ADR 0014 §2's reason: a committed
  baseline would change bytes depending on who last read it.

## Not decided here

- **Which keys are renamed.** The three places in *Context* are the instance
  measured on 2026-10-28; the list of schema 23 is decided with its code.
- **The register and the journal.** Neither is a document `_STEPS` migrates.
  The register's reader refuses another format with *"a register is a format,
  not a document, so nothing migrates it"*, and the journal's reader refuses
  another `JOURNAL_VERSION`. A rename in either is a version of its own, and
  this record does not rule on it.
- **The rule for a step that transforms**, and so the calibration band's change
  of shape (§2).
