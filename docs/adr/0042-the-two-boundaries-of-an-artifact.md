# ADR 0042 — The two boundaries of an artifact

- Status: accepted 2026-10-05. Ruled by discussion on #432, before any code.
  The text comes first and the implementation is written against it
- Shipped: 0.29.0
- Date: 2026-10-05
- Amends: [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4,
  by a pointer only. `Disclosure(artifacts=True)` stays necessary for an
  artifact to cross. It is no longer sufficient. Nothing else in 0003 changes,
  and §5's meaning of `withheld` is kept on purpose (§4 here)
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §3 (code
  that redacts discloses less, never more);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4 and §5;
  [ADR 0007](0007-the-declarative-suite-format.md) §6 (the read boundary, TOML
  only) and §7 (a data suite cannot widen a `Disclosure`);
  [ADR 0011](0011-the-mcp-server.md) §10 (a refusal reaches an agent as its
  sentence); [ADR 0041](0041-the-exit-code-of-a-failure-nobody-anticipated.md)
  §4.2 (a refusal written in words is a `RefusedError`, and exits 64)
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 9**, whose artifact
  paragraph says the declared artifacts *"cross a boundary only under
  `Disclosure(artifacts=True)`"*. That stays true, because the flag is still
  necessary. It stops being the whole rule, and the paragraph gains a pointer
  here. **It also adds a promotion condition**, the ninth by
  `store/promotion.py`'s count (§3). ADR 0002 §8, which collects them, names
  six (*Consequences*)
- Number: 0042. Swept on 2026-10-05, before a line was written, across
  `origin/main` (`091fb1d`), every local and remote branch, the `docs/adr/` of
  every sibling worktree, the open pull requests (#435, no record) and
  `private/`. The highest number taken anywhere is 0041

## Context

A suite names the files under test in `artifacts`. `read_artifacts` records
each one, path, digest and full text, in the run (ADR 0003 §2). Under
`Disclosure(artifacts=True)` the text crosses a boundary. Two routes carry
it:

- `report --redacted`, through `redact(run, suite.disclosure)` in
  `host/reading.py`;
- the MCP, through `wire.run_document(run, suite.disclosure)`, which builds its
  artifacts section itself and does not call `redact()`.

The projection of ADR 0034 is not a route, because it begins from
`redact(run, NOTHING_EXTRA)`.

**#432 found that nothing refuses the path.** `read_artifacts` refuses a
declared path for two reasons only: it is not a file, or it is not UTF-8. ADR
0007 §6 draws a read boundary at the perimeter, and it reaches the TOML form
only. A `.py` suite is checked nowhere. So the declared file can be any UTF-8
file the process can read:

- the suite's cases file, which is where #432 started;
- a `.env`;
- `~/.aws/credentials`;
- a run document under `.digline/`;
- the name table of ADR 0036, when its owner keeps it as text. It is the file
  that makes a projection's tokens resolvable;
- `.git/config`, where a remote URL with a token in it lives.

**The argument that left `.py` unchecked** is a comment in `host/loader.py`:
*"a `.py` suite is code and can already open anything, so a boundary there
would be decoration."* It is true of **reading**, which is a fact about Python.
It was never examined for **crossing**. Carrying a file across a perimeter, on
digline's channel, in digline's document, under digline's flag, is digline's
act, and digline can refuse to perform it. *The user's code can read the
user's data* and *digline ships it* are two different statements, and the
comment justifies only the first.

## Decision

### 1. Two boundaries, because there are two kinds of file

- A file **outside** the perimeter is **not read** (§2). It never enters a run,
  so no later step has to remember to keep it out.
- A file **inside** the perimeter that must not cross is **recorded, and
  refused at the exit** (§3). The developer who declared it keeps it in the
  complete run on their own disk, which is where ADR 0003 §4 says they own
  everything.

One boundary could not do both jobs. At the read alone, it would stop the
developer recording their own store. At the exit alone, it would let
`~/.aws/credentials` into every run file on disk.

### 2. The read boundary: ADR 0007 §6, for every suite format

`read_artifacts` refuses a declared artifact whose resolved path is outside
the perimeter. The rule and its unit are ADR 0007 §6's: the path is resolved
first, so a symlink pointing outward is outside, and the perimeter is the
`root` the front end passes. In all three front ends that is the directory
holding `.digline/`: `--root` in the CLI, `perimeter` in the MCP, and
`digline_root` or `rootpath` in pytest-digline.

**It covers every declared path**: the suite's `artifacts`, and what a target
answers through `HasArtifacts` (a `ProviderTarget`'s prompt file). The TOML
load-time check stays, because it refuses with the field's name before
anything is imported. This is the same rule reaching the form that had none.

**The cost is accepted.** An artifact from outside the perimeter can no longer
be recorded. No example, page or test in the tree declares one (an empty search
at `091fb1d`). A run started with `--root` set to a subdirectory has a
narrower perimeter, and a sibling file of the same repository is outside it.
The TOML form has worked that way since 0.7.1.

### 3. The exit boundary: `.digline` and `.git`

**An exit is any place where an artifact's text leaves the `Run` object.** There
are three:

- **`redact()`**, when `disclosure.artifacts` is true. It is behind
  `report --redacted`.
- **`run_document`**, on the same condition. It is behind the MCP.
- **`promote_baseline`**, always. It writes `without_responses(run)`, with
  every artifact's full text, to `baselines/`, which is versioned, and a
  repository gets pushed. Writing `.git/config` into a versioned file is
  exactly making it cross. No `Disclosure` is involved, because a baseline is
  the complete run and not a redacted one, so this check does not depend on
  the flag.

At each of the three, the artifact's **recorded key** is checked. The exit is
refused when any segment of the key, compared without regard to case, is:

- **`.digline`**: the store, meaning runs, baselines, the register, the
  journal and the name table;
- **`.git`**: the repository's own directory, or the file of that name in a
  worktree;

or when the key is **absolute, or begins with `..`**. A run recorded before §2
can carry a file from outside the perimeter. §2 stops new ones being recorded,
and this stops the old ones crossing.

*Widened 2026-10-05, by the change that implements this record (#458).* The
code refuses a key with a `..` segment **anywhere**, not only at the start. The
two readings agree on every key `read_artifacts` writes, because `relpath` puts
`..` only at the front. They differ only on a key edited by hand, where the
wider one refuses. This note is here so that the code and this record say the
same thing: without it, a later reader could take the wider rule for a defect
and narrow the code back to the letter.

**One predicate, in `core`, called from all three.** It reads the key string
and nothing else, so it is pure, and it may live where `redact()` lives.

- `redact()` is the primitive behind `report --redacted`.
- `run_document` chose not to inherit `redact()` (its docstring, *"Chosen, not
  inherited"*), so it calls the predicate itself.
- In promotion the predicate is **a ninth condition**, in `refusals_for`
  (`store/promotion.py`). That is where the conditions answered from the
  document alone already live, so every store implementation inherits it, and
  ADR 0034 §2's projection, derived from what `promote_baseline` returns, is
  never produced from a run that carries one. Its type joins the closed
  `PromotionRefusal` union and the protocol's list, as ADR 0031 §1's condition
  did.

A check written three times would be three rules that could come to disagree.

**Any segment, not only the first.** The key is relative to the directory
holding `.digline/`, so the store sits at `.digline/…`. But this repository
alone has ten stores below its root (`examples/*/.digline`), and a submodule or
a nested checkout has its own `.git`. A test on the first segment would stop
this perimeter's store and pass another one sitting inside the same perimeter.

**Without regard to case, and this was measured.** On macOS (APFS,
case-insensitive), `Path(".DIGLINE/t/runs/x.json").is_file()` is `True` for a
file at `.digline/t/runs/x.json`, and the recorded key is
`.DIGLINE/t/runs/x.json`. `resolve()` does not fold case. **Windows was not
tested.** Its default filesystem is case-insensitive as well, and the same
comparison covers it if it behaves the same way. That is an expectation, not a
measurement.

### 4. A refused crossing refuses the command

It does not narrow the document.

- **`promote`** refuses, and the baseline is not written. Per ADR 0041 §4.2 it
  exits 64 with the sentence.
- **`report --redacted`** raises a `RefusedError` subclass. Per ADR 0041 §4.2,
  that exits 64 with its sentence, and no document is written.
- **The MCP** raises the same class, which `digline.host.REFUSALS` classifies.
  It reaches the agent as its sentence through `translated` (ADR 0011 §10).

**The sentence names the path**, in every front end. After §2, whatever is
still refused at the exit is inside the perimeter, and its path names a place
in the user's own tree. That place is `.digline` or `.git`, never a customer.

**Why the document is not narrowed instead.** `withheld` already means *this
suite kept it back* (ADR 0003 §5). An artifact withheld by this rule would be
filed under a choice the suite did not make, and the MCP document would stamp
`"disclosure": {"artifacts": true}` beside it. The records had already ruled
against the silent narrowing: a refusal is a fact about the file, and a
narrowing is a guess that happens to be safe.

**Why not a marker of its own.** A `refused` flag beside `withheld` would be
true and would cross under redaction. But it adds a field to the run document
and to the wire, which means `SCHEMA_VERSION` and `OUTPUT_VERSION` both move,
for one bool.

### 5. What a path cannot see, stated as a limit

- **Files git ignores.** `.env`, local credentials and `.venv/` are inside the
  perimeter and outside both rules. Recognising them would need git at the
  exit, which only `host` may read (`CLAUDE.md`, *Structure*). The check would
  stop being a pure function in `core`. This is a limit chosen with its cost
  named, not an oversight.
- **Runs recorded before 0.7.1** keyed a file from outside their suite
  directory by its bare basename (ADR 0007's 2026-09-09 amendment). The escape
  is not in the key, so §3 cannot see it, and no migration can put it back.
- **Content.** A path rule says where a file sat, not what it holds. See *Not
  decided here*.

## Not decided here

**A committed `cases.json` keeps crossing.** It is the instance #432 was
opened for. A cases file committed beside its suite is inside the perimeter and
outside `.digline` and `.git`, so neither boundary touches it. The same holds
for a suite file whose cases are inline (`docs/guide.md`'s `support.py`), and
for an application file holding expected answers (the `app.py` it declares).
The question is one of content, not of path, and no rule about paths catches
it.

**Baselines already committed.** A baseline promoted before this record that
carries a file under `.digline` or `.git` has already crossed, and nothing here
reaches back into history. Reading one is unchanged. Promoting over it is
refused only if the new run carries such a file.

## Consequences

- A `.py` suite that declares a file outside its perimeter fails at `run`. The
  refusal names the field and the resolved path. This record does not promise
  that its wording is the TOML form's: the refusal is raised in
  `read_artifacts`, which is not `within_perimeter`, and how the two are
  written is left to the code.
- `report --redacted` and the MCP refuse, with exit 64 and the path, a run
  whose suite discloses artifacts and which records one under `.digline` or
  `.git`, in any case and at any depth. They refuse the same for a key that
  leaves the perimeter.
- `promote` refuses such a run **whatever the `Disclosure`**. The cost: a run
  that declares a file from the store or from `.git` can be compared, but it
  can never become a baseline.
- No `SCHEMA_VERSION`, no `OUTPUT_VERSION`: nothing is added to a document.
- ADR 0003 §4 gains a pointer here, in the change that carries this record.
- Owed in a later change, not this one: `CLAUDE.md` decision 9's artifact
  paragraph gains a pointer here.
- Owed in the same later change: five pages say `Disclosure(artifacts=True)` *is
  what lets* the files travel, and each gains *"inside the perimeter, and
  outside `.digline` and `.git`"*: `docs/api.md` (twice), `docs/tools.md`,
  `docs/mcp.md` and `packages/digline-mcp/README.md`.
- **The promotion conditions are growing faster than anyone reads them
  together.** This is an observation, not a ruling.
  - This record's condition is the ninth by `store/promotion.py`'s count.
  - Conditions 1 to 3 are ADR 0002's own (2026-08-25). Five more arrived in
    fourteen days: 4 on 2026-09-11 (ADR 0015 §7), 5 on 09-16 (ADR 0024 §4.5),
    6 on 09-19 (ADR 0027 §3), and 7 and 8 on 09-24 (b3735a5 and ADR 0031 §1).
  - ADR 0002 §8, the section that collects them, names six. Its amendment of
    2026-09-22 says why: each condition is added by the record that decides it,
    *"and none came back to say so here"*. Conditions 7 and 8 have not come
    back either.
  - `PromotionRefusal` is a closed union declared in the protocol, so every
    addition is public surface.

  A list that grows this way has to be read whole, at some point, to learn
  whether it has a principle or is a collection. Writing that down now costs
  a line. Noticing it at the twelfth costs a survey.
- The comment in `host/loader.py` stays true, because it is about reading. It
  gains a sentence saying that crossing is ruled here.

## Alternatives considered

- **One boundary, at the read.** Simpler. Refused: it stops a developer
  recording a file from their own store or `.git` in a run on their own disk,
  which they own in world 1. Making promotion an exit closes the committed
  baseline without it.
- **Exits at `redact()` and `run_document` only.** That was this record's
  first draft. The baseline is a versioned file, and *inside the perimeter* is
  not *committed*: `.git/config` reached a pushed repository through promotion,
  with neither check in the way.
- **One boundary, at the exit.** Refused: `~/.aws/credentials` would sit in
  every complete run and in every baseline promoted from one.
- **Narrow the document (`withheld`)** and **a marker of its own (`refused`)**:
  §4.
- **Refuse by ignore-status** rather than by name: §5.

## Test plan

A test for each refusal, and each must also fail on `main`, or it proves
nothing.

1. A `.py` suite declaring `../outside.txt`. `run` refuses, naming the path.
   The same suite with the file moved inside is accepted.
2. A `.py` suite whose target answers an outside path through `HasArtifacts`.
   It is refused the same way.
3. A run whose key is `.digline/t/runs/x.json`, under a suite with
   `Disclosure(artifacts=True)`. `report --redacted` exits 64 with the path. The
   MCP `get_run` returns the same sentence as a tool error.
4. The same for `.git/config`, for `.DIGLINE/…` and `.Git/config`, and for
   `examples/x/.digline/…`. The case-folded and nested forms are the ones a
   prefix test would miss.
5. The same run under `Disclosure()` (artifacts not disclosed) is accepted.
   Nothing crosses, so there is nothing to refuse.
6. A run whose key is `../secret.env` (one recorded before §2). It is refused at
   the exit.
7. The projection of a run that records `.digline/…` is unaffected, because it
   redacts under `NOTHING_EXTRA`.
8. `promote` of a run recording `.git/config` is refused with exit 64, under
   `Disclosure()` as well as under `Disclosure(artifacts=True)`, and no
   baseline file is written or replaced. `refusals_for` returns the refusal on
   its own, with no store.
9. **Mutation controls.** Remove the condition from `refusals_for`, and 8 goes
   red. Remove the case fold, and 4's case-folded cases go red.
   Test the first segment only, and 4's nested case goes red. Remove the
   predicate call from `run_document` alone, and 3's MCP leg goes red.
