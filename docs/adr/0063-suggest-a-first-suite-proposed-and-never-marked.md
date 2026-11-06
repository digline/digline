# ADR 0063 — `digline suggest`: a first suite, proposed and never marked

- Status: accepted 2026-11-06, by Alessandro Prandini (P-1549), with every
  item marked *decided here* taken and one amendment before it landed: a
  suite that does not exist yet moved from *Not decided here* into §1 and §5.
  Proposed 2026-11-06. **Its decisions were ruled before this record was
  written**, by Alessandro Prandini on 2026-11-06 (P-1548), on a table of
  seven questions measured against the code at `18b2c1be`. They are stated
  here as ruled, in this record's own words. **What this record adds is
  marked *decided here***. Nothing in it is implemented
- Shipped: unreleased
- Date: 2026-11-06
- Opens: **nothing at this record's landing.** No `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`, no `RECORDING_VERSION`, and no entry in the layout of
  `.digline/<tenant>/`: the file this record writes sits beside the suite
- Amends, each by a dated note beside the place it amends, which points here.
  Every text is kept as written:
  - [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md),
    *Not decided here*, *"The rich import against ADR 0023"*, and §13's third
    item, *"The rich import"*: the half that proposes checks is ruled here,
    and the half that samples recordings stays open
  - [ADR 0023](0023-capture.md) §8, *"The payload: a declared regime"*: the
    file of proposal follows the regime the suite's capture declares
- Assumes: [ADR 0023](0023-capture.md) §4 (nothing ranked, scored, starred
  or pre-selected), [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §6 (the same at a served page), [ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md)
  §1 (a reviewed answer is a person's yes or no) and §3 (the listing groups and
  counts, and never proposes), [ADR 0010](0010-per-group-aggregates.md) §5 (no
  single-group form), [ADR 0012](0012-the-reading.md) §4 (no fact carries a
  reason), [ADR 0024](0024-the-judge-as-an-instrument.md) §4 (the calibration
  case), [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §1 (where the
  store lives), [ADR 0061](0061-a-local-page-whose-views-other-packages-may-extend.md)
  §2 and §5 (the page's two writes, and the views a plugin adds)

## Context

A first suite is the hard part: which checks, which numbers, which cases. The
skill `proposing-a-suite` gives a coding agent digline's method for it, in
five steps (`docs/proposing-a-suite.md`), and helps whoever works with Claude
Code. Everyone else meets an empty file. This record puts the same help inside
digline, as a command.

**What the method already rules, and this record keeps.** Three rules of the
skill hold whatever writes the proposal: it proposes and never marks; a suite
that cannot fail measures nothing, so a proposal carries a case it fails on;
the commit is the person's.

**What the rules already in force forbid.** ADR 0023 §4: *"Nothing in the
listing is ranked, scored, starred or pre-selected"*, kept word for word at a
served page by ADR 0037 §6, and for recordings by ADR 0059 §3: *"Nothing is
ranked, and no criterion is suggested: no this looks like a no"*. ADR 0058
left the piece this record is open, in its *Not decided here*: proposing an
assertion from the shape of the output, and sampling by output, *"go beyond
what 0023 §4 allows a listing to do"*, and §13 put it third, *"ruled before
it is"* built.

**Three measurements, at `18b2c1be`, that shaped what is ruled:**

- **The journal of a run is not a memory.** It is the legs under
  `runs/<suite>/.pending/`, and `complete()` deletes every leg once the run
  file exists (`src/digline/store/file_store.py:1958`). What lasts is the run
  documents and the register (ADR 0021), whose entry has, by type, no field a
  case id or a sentence could occupy (ADR 0021 §3). A memory of proposals is
  therefore a new thing, and not this record's (*Not decided here*).
- **A command cannot come from a plugin.** The entry point groups digline
  reads are `digline.providers`, `digline.recording_maps`,
  `digline.recording_wire` and `digline.views`. None adds a verb.
- **The bound ADR 0023 §4 names in code does not exist.** `max_per_pattern`
  is in no file under `src/`. A proposal that chose cases would have nothing
  to hold it to two per pattern.

## Decision

### 1. What it reads

*Ruled.* `digline suggest --suite S` reads:

- **the suite's recordings**: input, answer, the shape of the output
  (`OutputKind`, `finish`, the actors of the steps), the setup, the tools
  called, through the functions `digline record import` reads them with;
- **the reviewed answers** in the cases file the suite's capture names: a
  person's yes or no, with an episode's steps;
- **the run documents**, where there are any, to propose a threshold where
  the system measurably is; where there are none, the threshold is a
  placeholder, declared as one.

**The calls no suite named (`_unassigned`) are counted and never a source.**
A call without a suite belongs to none until a person assigns it, so a
proposal made from it would make that assignment. The command says how many
there are and the command that assigns them.

With no recording and no reviewed answer it proposes nothing, and says where
a suite begins: `digline record on`, which stays the person's act.

**A suite that does not exist yet.** *Ruled at acceptance (P-1549).* The
command reads the recordings even where no file of the suite exists, because
the recorder writes them by the suite's name (ADR 0058 §2). *Measured:* they
are filed by process, under `.digline/<tenant>/recordings/<process>/`, and the
name is each file's `suite` field (`docs/recording-format.md`), so the command
reads the files whose `suite` names S, across the tenant's process
directories. Then:

- **`--repository private|public` is mandatory and has no default**, as
  ADR 0059 §4 has it for a capture: the declaration is the person's. The
  proposed `[capture]` carries it;
- *decided here:* **`--tenant T` is mandatory too**, because with no suite
  there is no declared tenant to find the recordings under;
- where the suite exists, its capture is the one used, and **`--repository`
  is refused** by name: the regime is already declared.

### 2. What it proposes

*Ruled.* One file of proposal, holding:

- the suite's **`[capture]`**;
- **checks from the shape of the answers**: `IsJson` and a draft
  `JsonSchema` for a structured output, read from the keys and types every
  recording carries; `Length`; and for an episode the checks on the steps
  (`ToolsCalled`, `Subsequence`, `Before`, `Never`, `MaxSteps`) from a
  regularity that holds on **every** recording of the group, never one a
  single recording contradicts, because every case is asked every check
  (ADR 0010 §5);
- **limits**, from the runs where there are runs, placeholders otherwise;
- **a counterexample**: a reviewed no where there is one; otherwise a case
  constructed and marked as constructed, `counterexample-…`, **written in the
  file**, so the proposal can fail;
- **a calibration skeleton**: a `Calibration` with the answer to paste and the
  band to place, because an answer known to be partly right is the author's
  (ADR 0024 §4.1);
- **a rubric** for each judged check.

**Cases: none chosen. Reviewed answers: counts alone.** The command says how
many recordings and answers are not yet examined, by group, and the command
that examines them. Choosing which recordings become cases, or which answers
to review, is a pre-selection, and ADR 0023 §4, ADR 0037 §6 and ADR 0059 §3
**stay as they are**.

### 3. The rule that holds

*Ruled.* **`digline suggest` never writes a `reviewed_answer`, a `good`, a
`--by`, a label or a promotion**, and it writes nothing but the file of
proposal. **No command of digline reads that file** until the person adopts
its lines into the suite: a proposal enters no gate on its own, and nothing it
says is a verdict.

*Decided here:* **every check it proposes can fail**, by fixed decision 3:
a placeholder is a number that a measured answer can fall short of, never a
default that passes, and the counterexample of §2 is the proof that the
proposal as a whole can say no.

### 4. The assistant: a model of its own, not the judge

*Ruled.* **The judge and the assistant are two actors with two roles: the
judge measures inside the gate; the assistant proposes outside it.** The
assistant is declared apart, in TOML:

    [suggest]
    model = "anthropic/claude-…"

by coordinates, as a judge is (`docs/declarative.md`, *The judge, by
coordinates*), through the provider plugins there are. It is never the suite's
judge and never stands in for it: the judge stays the one the suite declares,
and the gate uses no word the assistant wrote until a person adopts it.

- **Who calls it:** whoever runs the command, from the perimeter where the
  store is (ADR 0034 §1), with the credentials there.
- **What it costs:** said before the first call, as `digline run` says its
  plan (`AGENTS.md` §7).
- **What it is given:** the suite's recordings (input, answer, shape, steps)
  and the reviewed answers. **Never the `_unassigned` calls.**
- **What it writes:** text in the file of proposal: a draft rubric, each check
  with a sentence on why, limits in place of placeholders, a constructed
  counterexample.
- **Without a declared model the command works**, with the rules of §2 alone
  and its placeholders. With none declared, no call is made: fixed decision 5.

### 5. Where it lives

*Ruled.* **The verb `digline suggest --suite S`, in the core.** `S` is a
suite's file, or, where no file exists yet, the suite's name, with `--tenant`
and `--repository` (§1). It writes `suite.proposed.toml` beside the suite, or,
*decided here*, in the working directory where there is no suite yet, **always TOML**, a `suite.py`
included, and says so on standard error, with what it assumed: the form, the
setup in force, the judge it read, each check and why, each number and where
it came from, the calibration band left to place, the counterexample. These
are the skill's fifth step, said by the command.

**No third write at the page.** ADR 0061 §2's two writes stay two. A
read-only view, through `digline.views` (ADR 0061 §5), is for after.

*Decided here:* a `suite.proposed.toml` already there is not overwritten: the
command refuses by name, and the person moves it or deletes it. What a person
wrote in a proposal file is not the command's to throw away.

### 6. The file of proposal follows the capture's regime

*Ruled.* **The file of proposal follows ADR 0023 §8**: it quotes recorded
inputs and answers, so it may stand where the suite's capture declares the
cases may, `"private"` (readable only inside the perimeter of whoever owns the
text) or `"public"`. Under `"public"` the command writes no recorded text into
it: the rules and counts stay, the quoted inputs and answers do not, and the
standard error says which were left out and why.

*Decided here:* what the command prints is digline's own words, counts and
the names of checks. **The recorded text reaches the file and nothing else**:
not standard output, not standard error. A `--json` and an MCP tool are not
in this record; where they come, they carry counts and the kinds of checks
alone (fixed decision 9; ADR 0012 §4).

### 7. What the core holds

*Ruled.* **The verb and the rules of §2 are in the core**: the verb because no
plugin can add one, and the rules because they read the `OutputKind` and the
steps the core defines. The assistant's call goes through the provider plugins
already there. The skill and `docs/proposing-a-suite.md` name `digline
suggest` as the first step, so the agent and the command start from the same
proposal.

## What does not change

- **ADR 0023 §4, ADR 0037 §6 and ADR 0059 §3**, word for word. Nothing is
  ranked, scored, starred or pre-selected, and no criterion is suggested.
- **ADR 0059 §1**: a reviewed answer is a person's yes or no, given with
  `--by`.
- **ADR 0061 §2**: the page writes two things.
- **The judge**: what the suite declares, measured as ADR 0024 measures it.
- **The layout of `.digline/<tenant>/`**: nothing is added to it.

## Consequences

**A person without an agent gets the first file**, with its checks, its
counterexample and the numbers it could not know marked as such. The agent
and the command start from the same proposal, and the skill keeps what only a
conversation can do: asking.

**The rich import of ADR 0058 is ruled in half.** Proposing checks from the
shape of the output is this record; sampling recordings into cases is not,
and waits on an amendment of ADR 0023 §4 that this record does not make.

**A model can be called by a command that is not a run.** Its cost is said
first and it is never the judge, so no verdict depends on it.

## Alternatives considered

- **The suite's judge as the assistant.** Rejected at the table: the judge
  measures in the gate, and an actor that wrote the text a gate reads is not
  one that should also score against it.
- **A third write at the page.** It would amend ADR 0061 §2 for what a
  read-only view gives without writing.
- **A plugin with a command of its own.** It would prove the rules without the
  core, but a tester would install one more thing to meet the help, and the
  rules read what the core defines.
- **Choosing cases by shape, one per group.** It is a pre-selection, and ADR
  0023 §4 forbids it as written.

## Not decided here

- **A memory of what the person accepted and rejected.** A file on the model
  of the register (ADR 0021), in a record of its own: it adds an entry to the
  layout, which is fixed decision 2.
- **Choosing cases, or answers to review**, which amends ADR 0023 §4 and ADR
  0059 §3.
- **The read-only view** at the page.
- **`--json` and an MCP tool**, beyond §6's rule for them.

## Test plan

- `digline suggest` writes `suite.proposed.toml` and nothing else; a second
  run refuses where the file is there.
- No `reviewed_answer`, `good`, `--by`, label or promotion is written, and no
  command reads the file: after `suggest`, the suite loads to the same
  declaration and the same `config_hash` as before it, and the cases file is
  byte for byte what it was.
- A check on the steps is proposed only where every recording of the group
  holds it; one contradicting recording takes it out.
- The counterexample is a reviewed no where there is one, and a constructed
  case marked as such otherwise; the proposed suite, adopted whole, fails on
  it.
- `_unassigned` calls are counted and never quoted, and never reach the
  assistant.
- A suite that does not exist: with `--tenant` and `--repository` the command
  writes the proposal, its `[capture]` carrying the regime given; without
  `--repository` it refuses and names the flag. Where the suite exists,
  `--repository` is refused.
- With no model declared, no call is made; with one, the cost is said before
  the first call.
- Under `"public"`, no recorded text is in the file; under either regime,
  none is on standard output or standard error.
