# ADR 0021 — The register

- Status: proposed — the text first, checkpointed before any code, beside
  [ADR 0020](0020-the-reading-across-runs.md)
- Date: 2026-09-15
- Amended: 2026-09-16 — one factual correction, no decision revisited: **§3's
  example gives `recorded_at` to the second, and the writer keeps
  microseconds.** `digline register` reads the clock through
  `host.utc_now_iso()`, which keeps them on purpose: truncating once let two
  runs in the same second share a key. The store's second-truncating
  `utc_now_iso` is not the one the CLI uses. The register gains from this too:
  the reader orders by `recorded_at` and a union merge makes file order
  meaningless, so two dispositions recorded in the same second still keep their
  order. `isoformat()` drops an all-zero fraction, and those values still sort
  correctly as strings, because `+` sorts before `.`
- Amended: 2026-09-16 — **§8's section of the reading is windowed, and no
  record said so.** `log --since`/`--until` apply to the dispositions as well as
  the runs, and each disposition is filtered on its own `recorded_at`, not on
  the `created_at` of the run it names. A window that ends before a person read
  a comparison shows the run and not the disposition about it. ADR 0020 §5
  describes the window over `created_at` and now points here. The register's
  section is a separate record with a separate date, and filtering it on the
  run's date would place a person's decision on a day they had not yet made it
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states);
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the payload
  stays where it is born), §8 (a baseline is an approved reference);
  [ADR 0008](0008-the-two-run-report.md) §2 (the exit code is the contract);
  [ADR 0011](0011-the-mcp-server.md) §1 (a writer is absent by construction);
  [ADR 0012](0012-the-reading.md) §4 (the boundary is a type);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §2 (a comparison that edits its
  reference is not one), §3 (a ledger has its own retention question, its own
  boundary question, and its own reason to exist);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §2 (a work file is not a
  document), §3 (append-only, the torn tail);
  [ADR 0019](0019-the-reasoning-operator.md) §5 (what a clause may name), §8
  (the decision journal), §9 (the policy wall), §10 (the label loop);
  [ADR 0020](0020-the-reading-across-runs.md) §6 (the boundary of the reading),
  §9 (eight tools)
- Amends: [ADR 0019](0019-the-reasoning-operator.md) §5 — one dated sentence
  (§7); [ADR 0017](0017-the-journal-and-the-resumed-run.md) §2 and
  [ADR 0019](0019-the-reasoning-operator.md) §8 — *"`digline.wire` never learns
  its name"* gains one named exception, the register, and no other (§8)
- Closes: ADR 0019's *Not decided here* on retention for the journal and on
  persisting a comparison's verdict
- Turns into surface: `digline register`; `.digline/<tenant>/register/`;
  `AGENTS.md` §1 and the `operating-digline` skill (an agent does not record a
  disposition, for the reason it does not promote)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 2 is upheld — the
  register is a file in the tenant's directory, committed like a baseline;
  decision 8 — the tenant is the directory, and the run's `environment` is
  recorded without constraining; decision 9 — an entry is counts and keys, by
  type (§3)
- Requires: no `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no migration, no baseline
  re-promoted. A new store area and an optional store protocol
- Number: 0021, beside 0020 on the same branch

## Context

`compare` answers the one question digline exists for and then forgets the
answer. So do `explain` and `report`, which gate on the same comparison. The
exit code reaches a pipeline, the sentence reaches a terminal, and nothing
reaches the repository.

The dogfood shows what that costs, in a commit written on 2026-09-09. Two
edits to the judge's prompt were tried against the approved baseline, both made
things worse, both were reverted — and the only record of either is a paragraph
in that commit's message. The paragraph is good. It names no run. The runs it
describes are still in the store, and nothing joins the prose to them: a reader
a month later can read *why* and cannot find *which*.

What the repository does remember is thinner than it looks:

- **`promoted_at`** is the time of the **latest** signature, and only that
  (ADR 0014 §3 kept it to one field on purpose);
- **`git log` over `baselines/`** holds every signature — and every migration,
  in the same list. The dogfood's five commits there are three promotions and
  two migrations, told apart only by a `created_at` that did not change;
- **the operator's decision journal** (ADR 0019 §8) holds what the *operator*
  decided about a *cycle*, and it is ignored by git on purpose.

None of them holds the thing a person did when they read a comparison and said
*no*. This record gives that act a place.

The rule every choice below follows is ADR 0014 §3's, taken literally: a ledger
is a decision with **its own reason to exist** (§1), **its own boundary
question** — a name is payload in a way a timestamp is not (§3, §7) — and **its
own retention question** (§6).

## Decision

### 1. The machine's memory and the human's memory

> **The decision journal is what the operator decided. The register is what a
> person decided. The first is the machine's memory and is ignored by git; the
> second is the human's memory and is committed by the human who wrote it.**

A verdict is not a rejection. `compare` exiting 1 is the machine saying a check
got worse; *rejected* is a person reading that and deciding the change does not
ship. A register that stored verdicts would be a log of exit codes — every one
of which can be recomputed from two documents that are still on disk — and it
would still not contain the two rejections of 2026-09-09.

So the register records **a disposition**, and the verdict it was taken
against beside it. Three values, in the shape of the journal's `wanted`
(ADR 0019 §10), for the same reason that record gave:

    accepted | rejected | unsure

`unsure` is not an empty string. *I read it and could not decide* is a
different fact from *nobody read it*, and a register that could not say the
first would turn it into the second.

### 2. A command of its own

    digline register --suite suite.py --run KEY --disposition rejected

**A separate command, not a flag.** `compare --record` was the first answer and
is the wrong seat: `explain` and `report` produce the same verdict and exit with
the same code, so a flag on one would leave two thirds of the verdicts
unrecordable. And `compare` over the MCP is a measurement annotated as touching
nothing; a flag that wrote would exist on one front end and not the other.

**The disposition is mandatory**, with no default, like `environment` and like
`report --locale`. A defaulted disposition is a disposition nobody gave.

**It computes the comparison itself**, with the same `compare()` and the same
`headline()` the gate uses, against the baseline in force when it runs. The
entry records the digline that computed it (§3), because what a comparison
returns for a given pair has moved between releases — 0.12.1 changed the
configuration deltas of the same two documents.

**It exits 0 when it wrote**, like `promote`, and 64 when it could not: no
baseline to have judged against, a key that does not resolve, a tenant that is
not the suite's. It never exits with the comparison's code — the gate is
`compare`'s, and a recording command that failed a pipeline would be a second
gate on one fact.

**An unjudged run may be recorded.** A person rejecting a run that could not be
judged is a real act with a real reason, and refusing to write it down would
make exit 2 the one verdict the register cannot hold.

**`accepted` does not promote, and `promote` does not register.** They are two
gestures of one family — a person, the CLI, a file under the tenant, a commit —
and they stay two, because accepting a change and approving a new reference are
different decisions that often happen on different days.

**Absent from the MCP**, by construction and for `promote`'s reason (ADR 0011
§1): it writes into the repository, and the disposition is by definition not
the agent's to give. The server keeps eight tools (ADR 0020 §9), and this is not
one of them.

### 3. The entry is counts and keys, by type

One line of JSON per disposition:

    {"register_version": 1,
     "recorded_at": "2026-09-15T08:12:03+00:00",
     "digline_version": "0.13.0",
     "disposition": "rejected",
     "run":      {"key": …, "created_at": …, "config_hash": …,
                  "environment": …, "digline_version": …, "rejudged": false},
     "baseline": {"key": …, "config_hash": …, "promoted_at": … | null},
     "outcome":  {"regressed": 2, "improved": 1, "unchanged": 61, "new": 0,
                  "missing": 0, "errored": 0,
                  "unjudged": 0, "suspended": 0, "within_noise": 3,
                  "on_the_line": 1, "worse": true, "canary_moved": false,
                  "config_changed": false, "artifacts_changed": true,
                  "target_config_changed": false, "judge_config_changed": false,
                  "rejudged": false},
     "exit_code": 1}

Every field is on the verdict side of fixed decision 9 or is a fact about the
software house's own process, like `digline_version` and `promoted_at`
(ADR 0014 §3). The `outcome` block is `Headline`'s facts minus the one that is
prose.

**What it does not carry, and why each one is out:**

- **No case id**, and no assertion or aggregate name. In the dogfood, case ids
  are slugged titles of the threads being judged — content with a hyphen in it.
  The register records *how much* moved, and the run it names says *what*.
- **No sentence.** `Headline.sentence` names the canary case that moved
  (ADR 0016 §7) and the files that changed, so it carries identifiers the
  entry has just refused.
- **No free text.** A note field is where a person writes *"fails on the Rossi
  account"* — the example ADR 0012 §4 gave for the same reason.
- **No author.** A name is payload in a way a timestamp is not (ADR 0014 §3),
  and the register is committed, so the author is already in the commit.

That last point is also where the *why* goes. **The reason for a rejection is
the commit message of the commit that adds the line** — written by the person
who recorded it, in the words they choose, in the history that already holds
every other human reason in the repository. The register does not replace the
paragraph of 2026-09-09. It gives it a run key to point at.

`promoted_at` is `null` where the reference was promoted before the field
existed, and the reading says *not recorded* there. It is never filled from
git.

### 4. Committed, by the person who wrote it

    .digline/<tenant>/register/<suite>.jsonl        append-only, committed

Not under `runs/` and not under `decisions/`, so the generated `.gitignore`
tracks it without a new rule. The tenant is the directory, as everywhere.

**The commit is the person's.** `digline register` writes a tracked file and
leaves the tree dirty until somebody commits it, exactly as `promote` does with
`baselines/`. A run launched in between is stamped `-dirty`, as it would be after
an uncommitted promotion; the hazard is the promote gesture's own, and it is
met the same way.

**The operator never writes it — and the reason is not only absence.** On the
MCP the writer is absent. But the scheduled loop drives the **CLI**
(`examples/operator/loop.py` shells out to `digline run` and `digline explain`),
and on the CLI the verb exists. What actually keeps the operator out is the
shape of the act and the wall it would have to cross: a disposition is a
person's by §1, a register line is worthless until committed, and the operator
does not push (ADR 0019 §9). The rule is written into the example as a test —
no script and no workflow under `examples/operator/` invokes `digline register`,
asserted the way `digline promote` already is — and into `AGENTS.md` §1 beside
the rule it mirrors.

**Two branches that both append** meet at the end of the file, which is the one
place a line-based merge always conflicts. `ensure_layout` writes a
`.digline/.gitattributes` beside the `.gitignore` — created only when absent,
never overwritten — declaring `*/register/*.jsonl merge=union`. Git's union
driver keeps both sides' lines; the reader orders entries by `recorded_at` and
does not rely on file order, and drops a line that is byte-identical to one
already read.

### 5. Its own format, and no migration

`REGISTER_VERSION = 1`, beside and independent of `SCHEMA_VERSION` and of the
journal's format. The register is a **format** and not a document: it is never
migrated, never re-promoted, and a line this digline cannot read is refused by
name and left on disk. Nothing ever rewrites a committed register line —
ADR 0014 §2's argument about baselines applies without change: the bytes of a
committed record must not depend on who last ran a command.

**A changed mind is a second line, never an edit.** Recording `accepted` over a
run already recorded `rejected` appends; both stand, and the newest disposition
for a (run, baseline) pair is the current one. The history of having changed
one's mind is part of what the register is for.

**The torn tail and the hole**, on ADR 0017 §3's rule: a last line that does not
parse is a write that was killed, and it is discarded on read with a note; a
line that does not parse anywhere else is a corrupt register, refused by name,
and `digline register` refuses to append to it — appending past a hole would
bury it.

Writing is one line, flushed and synced, through `O_APPEND`.

A store that cannot hold a register implements no `SupportsRegister`, the way a
store that cannot journal implements no `SupportsJournal` (ADR 0017 §5): the
planned production store is not obliged to write an append-only file in a
repository, and the command says so once rather than failing.

### 6. Retention, for both ledgers

One rule, and it lands differently on each file because the files live in
different places:

> **Absence is stated, never read as zero. Rotation is allowed for ignored files
> only. A committed file's retention is git.**

**The register is committed, so it is never truncated.** Deleting old lines from
the working tree does not delete them from anything — git holds them — and it
does rewrite a committed record, which §5 refuses. Its size is the cadence of a
human act, one line per disposition, and that is the whole of the size question.

**The decision journal is ignored, so it may be rotated** — by a person, by a
tool somebody writes, or by the platform. The one condition is the ruling's
first clause: a reader must not read a rotated history as a short one. The
reader's half already exists. `decide.py --streak-unknown` (`462046c`) is this
rule applied: a journal that should hold earlier cycles and cannot be produced
is an unknown streak, and a clause with `max_cycles` does not hold on it. The
example ships no rotation of its own; whoever adds one marks it, so that the
seat can tell a rotated journal from a young one.

**The platform rotates too, and says so less clearly.** On a hosted runner the
journal is carried as an artifact, and artifacts expire. An expired journal that
is still listed reads as unknown; one that has been deleted cannot be told from
a first cycle. That limit is written into both workflows as a comment rather
than solved, because solving it would take a record of the journal's existence
held somewhere that does not expire — which is a committed file, which is the
thing §1 says the journal is not.

**Neither ledger has a compliance retention, and this is why.** `CLAUDE.md` makes
retention mandatory for the planned production store, which holds payload. The
ledgers hold none by type — the register by §3, the journal by ADR 0019 §5 as
amended in §7 — so their retention is a question of size and readability, not
of a data subject's rights. A ledger that ever came to hold content would lose
that answer, and would owe the question again.

### 7. Naming inside the perimeter, amended into ADR 0019 §5

ADR 0019 §5 says a clause may name identifiers and never contents. The dogfood
showed the distinction that sentence is missing: its identifiers *are* content,
slugged from the titles of the posts it judges. It gains one dated sentence:

> *Amended 2026-09-15 (ADR 0021 §7): naming a case inside the tenant's own
> repository — a clause in `operator.toml`, a line in the ignored journal — is
> in-perimeter naming and is allowed; a content-derived identifier never crosses
> a ledger's travelling surface, and no register entry carries a case id at
> all.*

**Scoped to the ledgers, and the scope is a finding rather than a preference.**
The ruling as first worded said content-derived ids never cross *a travelling
surface*. Read literally, that condemns surfaces that have shipped since 0.6.0:
`compare_json`, `diff_json`, `run_document` and the fact list all carry
`case_id` over `--json` and over the MCP, and the report a customer opens names
cases in every table. Fixed decision 9's list of what crosses a boundary does
not name `case_id` at all — it has travelled by practice, not by ruling. Closing
that is a decision touching the fixed section, which needs its own record before
its code (`CLAUDE.md`); this one narrows the sentence to what it governs and
names the wider question in *Not decided here*.

One consequence of `462046c` belongs here. The journal is now carried between
hosted cycles as an artifact of the repository's own workflow runs, so its
case ids live on the CI platform's storage beside the code. That is the
repository's perimeter and not a new one — the same host already holds
`cycle.json` and the alert — but it is travel, and it is written down.

### 8. The wire learns one name, narrowly

ADR 0017 §2 and ADR 0019 §8 both say *`digline.wire` never learns its name*. It
is amended once, narrowly:

> **The register enters the wire as a named exception. The decision journal and
> `.pending/` stay unknown to the wire, forever.**

The register reaches a reader **through ADR 0020's `log`**, and not through a
ninth tool. The reading gains one section per reference: the dispositions
recorded against it, in `recorded_at` order, each with its run key, its
`exit_code` and its counts. The story of the alias and the story of the
reference are one read-only reading, and the MCP surface stays at eight entries,
none of which writes.

`register_json` is built from entries that hold nothing §3 did not admit, so the
boundary is a type here too, and the marker suite drives it through the CLI's
`--json` and through the MCP `log` tool.

`log` itself was never excluded: it reads documents, which the wire has always
known (ADR 0020 §11). The exception is the register's alone.

### 9. What the register knows that the reference does not

| record | what it knows | what it cannot say |
|---|---|---|
| `promoted_at` | when the reference in force was signed | any earlier signature |
| `git log` over `baselines/` | every signature, with its author and message | which commits were migrations, except by reading `created_at`; any verdict that was not a promotion |
| the register | every recorded disposition, the verdict it was taken against, and the reference identity it was judged under | a verdict nobody recorded |

The register never replaces `promoted_at` and never infers a signature. Where
consecutive entries name different baseline keys, the reading may say *the
reference changed between these two dispositions*, because both entries declare
it; where no entry was recorded, it says nothing, because nothing declared
anything.

## Consequences

**A rejection becomes findable.** The paragraph in the commit message stays
where people write paragraphs, and now has a run key beside it in the same
commit.

**The register is only as complete as the habit.** Nothing records a
disposition on anyone's behalf, by design, so a team that never runs the command
has a register that says so — an empty file, not a clean record. That is the
same bargain `promote` makes.

**A committed file grows by one line per human decision**, forever, and that is
its retention. At the cadence a person reviews comparisons, it will not be the
largest file in the repository in anyone's lifetime.

**The journal may now be rotated**, and the reader already refuses to count
through a gap.

**Case ids stay on the wire where they already are.** §7 declines to settle
that, and the declining is itself on the record.

## Alternatives considered

**`compare --record`.** Rejected in §2: one of three commands that produce the
verdict, and on one of two front ends.

**The operator's journal, promoted to a committed file.** Rejected in §1: it
records a machine's decision about a cycle, at a different grain, and a
committed journal stamps the run it records as `-dirty` (ADR 0019 §8).

**An ignored register with a committed distillation.** Rejected: that is the
journal's pattern, and it exists because the journal is written by something
that cannot commit. The register is written by a person who can, at the moment
they decide.

**Verdicts only, no disposition.** Rejected in §1: every verdict can be
recomputed from two documents, and the thing that cannot is the person's
decision.

**A free-text reason field.** Rejected in §3: it is where payload is written,
and the commit message is where the reason already goes.

**Case ids in the entry**, so a reader can see what moved without opening the
run. Rejected in §3 and §7: in the material this was checked against, they are
content.

**A ninth MCP tool to read the register.** Rejected in §8: the reading of the
reference belongs beside the reading of the alias, and one read-only tool holds
both.

**Letting `register` exit with the comparison's code.** Rejected in §2: a second
gate on one fact.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The disposition is mandatory.** `digline register` without `--disposition` is
refused by the parser and writes nothing; each of the three values writes one
line. *The refusal exits 2, not 64, and that is a finding rather than a choice:
every missing required flag in the CLI exits with argparse's own 2 today, which
collides with `EXIT_UNJUDGED`. One command exiting 64 alone would be a second
convention; settling the collision for the whole CLI is in* Not decided here.

**The entry's shape is a set.** A written line's keys, and the keys of its `run`,
`baseline` and `outcome` blocks, are asserted as sets, so a field added by
accident — above all a case id — fails here.

**The verdict is the gate's.** For a fixture pair, the entry's `outcome` and
`exit_code` equal what `headline()` and `exit_code()` return for the same pair.

**Append, never rewrite.** Recording twice for one run leaves two lines and the
first byte-identical; the register's bytes before the second write are a prefix
of its bytes after.

**The torn tail and the hole**, on ADR 0017 §3's pair: a truncated last line is
discarded on read with a note; a corrupt middle line is refused by name, and a
subsequent `register` refuses to append and leaves the file unchanged.

**The union merge.** Two branches that each append one line merge without a
conflict under the generated `.gitattributes`, and the reader returns both
entries in `recorded_at` order. An existing `.gitattributes` is not overwritten.

**The operator cannot reach it.** The MCP tool set is asserted to be ADR 0020's
eight with no register writer; no file under `examples/operator/` contains
`digline register`.

**The boundary.** A register whose run and baseline documents carry markers in a
case id, a reason, `vars` and a withheld `base_url`, read through `log --json`
and through the MCP `log` tool: no marker appears.

## Not decided here

**Whether `case_id` crosses a boundary at all.** It travels today over `--json`,
over the MCP and into the report, and fixed decision 9 does not name it. §7
found the question and scoped itself away from it; answering it touches the
fixed section and needs its own record first.

**The label loop's distillation** (ADR 0019 §10). The register's disposition and
the journal's `wanted` share a vocabulary on purpose, and turning either into a
suite that measures the operator is still the command ADR 0019 deferred.

**A rotation marker's format** for the journal. §6 states the obligation; the
example ships no rotation, and the marker arrives with the first one.

**argparse's exit code.** A missing or invalid flag exits 2 in every command,
which is `EXIT_UNJUDGED`'s number: a pipeline that typed `--disposition` wrong
reads *the run could not be judged*. The fix is one parser for the whole CLI and
it touches ADR 0008 §2's contract, so it is not made in passing here.

**Requiring a register entry before a promotion.** The two gestures are kept
apart in §2. Whether a team may make one a precondition of the other is a policy
question for that team's workflow, not a rule of the tool.
