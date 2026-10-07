# ADR 0045 — One declared path, resolved once

- Status: accepted 2026-10-07, by Alessandro, after #481's code was written
  against it and measured. It was proposed the same day, the text first and
  before any code. Three of its claims were deductions then, and #481's code
  measured them (§4, §6, §7). The pin's measured differently from its
  deduction, and §7 carries the wording ruled on the measurement. Three points
  entered at acceptance: the name a symlink is recorded under (§5), the target
  named by its class (§5), and the absolute path that now reaches an MCP
  agent, by a ruling of the same day (*Consequences*). What it
  rests on was ruled in discussion on 2026-10-07, after the measurements in
  #476 and #481, and is recorded here as ruled: the defect, the repair, the
  anchoring rule and the reason a target's path is not anchored, the accepted
  consequence, the name a run records, and that ADR 0042 §2 is amended rather
  than annotated. Two further rulings the same day decide what
  `HasArtifacts` requires and where the recorded name comes from (§5). Both
  were given in conversation and written into the record of #476 before this
  text cited them. What this record decides on its own is marked *decided
  here* where it is made
- Shipped: unreleased
- Date: 2026-10-07
- Opens: **nothing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no migration.
  The name a run records keeps its form and its unit (§3)
- Requires, at implementation (#481), and done there:
  - `ProviderTarget.artifacts()` answers the path its template read, resolved
    when it was read (§2);
  - `read_artifacts` stops resolving what a target answers, and refuses a
    relative one with a sentence that names the target (§5);
  - one normalization of each declared path, which feeds both ADR 0042 §2's
    check and the recorded name (§5);
  - the docstrings of `read_artifacts`, `read_pinned`, `HasArtifacts` and
    `ProviderTarget.artifacts` rewritten to say so
- Amends: [ADR 0042](0042-the-two-boundaries-of-an-artifact.md) §2. Its read
  boundary reaches a target's prompt file through *"The rule and its unit are
  ADR 0007 §6's"*, and 0007 §6's rule anchors a relative path to the suite's
  directory. The boundary stays. The anchor goes, for a target's path (§4,
  §7). Its test plan's second entry is annotated inside the same note
- Assumes: [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md)
  §2 (the run records content and digest, and the host does the reading);
  [ADR 0007](0007-the-declarative-suite-format.md) §6 (a data suite's paths
  resolve against the suite file, inside the perimeter);
  [ADR 0042](0042-the-two-boundaries-of-an-artifact.md) §3 (the exit check
  reads the recorded key); [ADR 0041](0041-the-exit-code-of-a-failure-nobody-anticipated.md)
  §4.2 (a refusal written in words)
- Touches:
  - [ADR 0007](0007-the-declarative-suite-format.md) §6, by a dated note and
    not by an amendment. Its text stays true for the TOML form, and what was
    carried past that form was ADR 0042 §2's reference to it (§7);
  - [ADR 0029](0029-the-artifact-that-must-not-drift.md) §4, by a dated note,
    which says that pinning a prompt a target contributes *"is legitimate and
    must work"*. It still works where the path is anchored. Under §2 and §4
    here, a pin and a bare relative target prompt can come to be keyed
    differently, and the run is then refused. *Measured with #481*, and the
    note was written from the measurement (§7);
  - in `CLAUDE.md`'s *fixed* section: nothing. Decision 9 says what crosses a
    boundary, not where a path resolves from
- Closes: on landing, the half of #476 that asks for the rule to be declared.
  Its other half, the two READMEs, is #485. At implementation, #481
- Number: 0045. Swept on 2026-10-07, before a line was written, across
  `origin/main` (`d87fb51`, and again at `e97c780`), every local and remote
  branch, the `docs/adr/` of every sibling worktree, the open pull requests
  (#482, which carries 0044's code; #485 and #455, no record) and `private/`
  (no claim on 0045). The highest number taken anywhere is 0044

## Context

A `.py` suite at `R/eval/suite.py` builds a `ProviderTarget` with
`prompt_file="prompt.txt"`. The perimeter is `R` (`--root R`). #481 put a file
named `prompt.txt`, each with different text, in three directories and ran the
suite from each of them. Python 3.14.5, at `d87fb51`:

| working directory | sent to the model | recorded as `eval/prompt.txt` | exit |
|---|---|---|---|
| `R/eval` (the suite's) | `R/eval/prompt.txt` | `R/eval/prompt.txt` | 0 |
| `R` (the root) | `R/prompt.txt` | `R/eval/prompt.txt` | 0 |
| `OUT` (outside the perimeter) | `OUT/prompt.txt` | `R/eval/prompt.txt` | 0 |

The command line and the MCP server gave the same results, and so did
`system_file`. In the third row a file outside the perimeter reached the
provider, and ADR 0042 §2's read boundary passed, because it checked a file
inside it. In the second row the run records a prompt that was not sent.

**The TOML form has the same double resolution, and there it fails loudly.**
*Measured 2026-10-07, on the code of `e97c780`, offline:* a suite at
`R/eval/suite.toml` whose `[target]` declares `prompt_file = "prompt.md"`, and
a provider pointed at a closed port on `127.0.0.1`.

| front end | working directory | suite named as | result |
|---|---|---|---|
| command line | `R` | `eval/suite.toml` | exit 64: *"not a file at `R/eval/eval/prompt.md`"* |
| command line | `R/eval` | `suite.toml` | runs, records `eval/prompt.md` |
| command line | `R` | absolute | runs, records `eval/prompt.md` |
| command line | `OUT` | absolute | runs, records `eval/prompt.md` |
| MCP server | `R`, `OUT`, `R/eval` | `eval/suite.toml` | runs, records `eval/prompt.md` |

The loader joins the suite file's directory to the declared path and hands the
target the joined path, still relative when `--suite` was relative. The target
reads `eval/prompt.md` against the working directory and finds the right
file. `read_artifacts` then joins the suite's directory a second time. The MCP
server is not affected, because it makes the suite's path absolute before
loading it (`within_root`).

### Two words, kept apart

This record turns on one distinction, and Python names both sides of it
`resolve`.

- **To resolve** a relative path, here, is to anchor it: to decide which
  directory it is joined to, and so which file it names. The defect is two
  resolutions of one path, against two directories.
- **To normalize** a path is what `Path.resolve()` does to an absolute one: it
  follows symlinks and removes `.` and `..`. It anchors nothing.

`Path.resolve()` on a relative path does both: it anchors the path to the
working directory, then normalizes it. So a call named `resolve()` can be a
resolution, a normalization or both, and this record says which. Text quoted
from other records keeps its own wording.

### What was ruled before this text, on 2026-10-07

1. **The defect is the double resolution of one declared path, not its
   anchoring.** `PromptTemplate` reads the file and the target sends it.
   `ProviderTarget.artifacts()` returns the path as it was given, and
   `read_artifacts` resolves it again, against the suite. When the two
   resolutions disagree, ADR 0042's boundary checks a different file from the
   one that was sent.
2. **It is closed by having whoever reads the file report the path it read,
   already resolved.** `read_artifacts` no longer resolves what a target has
   already opened. The path meant is the one used for reading, not the name the
   run records (ruling 6).
3. **A target's prompt file is not anchored to the suite.** A
   `PromptTemplate` can be built without a suite, and there is then no
   directory to anchor to. A Python object that changes meaning according to
   who builds it is worse than the defect.
4. **A path is anchored to the suite only where a suite is necessarily
   present.** `Suite.artifacts` and `Suite.pinned`: yes. A target's fields:
   no. The TOML form: yes, by ADR 0007 §6, because there the path is a
   declaration and not code.
5. **The consequence is accepted.** In a `.py` suite a bare relative path in
   a target depends on the working directory, and is anchored by hand with
   `Path(__file__).parent`. So the READMEs of `digline-openai` and
   `digline-bedrock`, which passed `"prompts/answer.md"`, were the ones that
   were wrong.
6. **The name a run records stays relative to the perimeter, computed from
   the file actually read.** No absolute names, ADR 0042 §3's check intact,
   no baseline invalidated. In the divergent case the name and the content
   change together, and that is the correction. Recording the path as read,
   absolute, as the name was ruled out, unmeasured.
7. **ADR 0042 §2 is amended, not annotated.** A dated note is for a text that
   stays true and needs a qualification. §2 stops being true (§7).

### What reading the code found

At `e97c780`. The files read are byte-identical to `d87fb51`, where #481
measured. Code was read; nothing was run for this section.

- **`PromptTemplate.__init__`** (`targets/template.py`) does `Path(path)` and
  `read_bytes()`. A relative path opens against the process's working
  directory, and the text it reads is what the target sends.
- **`ProviderTarget.artifacts()`** (`targets/provider.py:92`) returns
  `template.path`, a `Path` as it was given, still relative.
- **`read_artifacts`** (`host/artifacts.py:23`) does `base / entry` for a
  relative entry, checks the perimeter on that and reads that. `base` is the
  suite's directory in all three front ends: `cli/main.py:264`,
  `digline-mcp`'s `server.py:365` and `pytest-digline`'s `plugin.py:385`.
- **`read_pinned`** (`host/artifacts.py:98`) resolves a pin *"exactly as
  `read_artifacts` resolves an artifact"*.
- **The TOML form resolves a `[target]` path before the target exists, and
  leaves it relative.** `_resolve_paths` (`host/toml_suite.py:776`) joins a
  `Path`-typed parameter to the suite file's directory. `within_perimeter`
  calls `Path.resolve()` on the joined path to check it, which anchors it to
  the working directory and normalizes it, and then returns the joined path,
  not that result. With a relative `--suite` the target holds a relative
  path. The measurement above is what that does.
- **`ProviderTarget` is the only implementation of `HasArtifacts` in the
  tree.** The protocol (`run/driver.py:171`) is public, returns
  `Sequence[Path]`, and says nothing about what a path is relative to.

### How the suite's anchor reached a `.py` target

Nobody decided it. It arrived by reference.

- **The second resolution is older than both records.** It came with the
  first provider target: `af7c480` (2026-08-27, *"Anthropic target"*) added
  `declared.extend(target.artifacts())` and `base / entry` to the CLI. The
  same commit's docs and tests anchor the prompt with `Path(__file__).parent`,
  which is why the two resolutions agreed there. *Measured with `git log -S`
  and `git show`.*
- **ADR 0007 §6 drew the rule for the paths "a data suite can write"**, the
  TOML form: *"A relative path resolves against the suite file's directory"*.
- **ADR 0042 §2 took "the rule and its unit" from it**, and applied them to
  *"what a target answers through `HasArtifacts`"*. That gave the code's
  behaviour a rule, by reference. No sentence in either record says that a
  `.py` target's prompt file is anchored to the suite.

Whether anybody read that behaviour as a decision before ADR 0042 was not
looked for.

### The name a run records, measured

*Measured at `d87fb51`, offline, on a real store, on the command line only:*
a scratch repository holding a copy of `examples/prompt-first` under `eval/`,
its fake client, and `digline run`, `compare` and `promote`.

- **What the field holds.** `artifacts` maps a name to `{sha, text}`. The name
  is the path relative to the perimeter (`eval/prompts/user.txt`).
  `target_config` holds neither the prompt's name nor its digest.
- **The name is not in `config_hash`.** The prompt directory was renamed with
  identical content. `config_hash` stayed the same across all six runs, and
  `compare` reported `config_changed: false`. A run's key is `created_at` plus
  `config_hash`, so its identity does not move.
- **A baseline promoted before a rename, same content.** `compare` exits 0
  and reports four files under test changed: two added since the reference,
  two no longer declared, on identical files. `promote --replacing` accepts
  the run.
- **ADR 0042 §3's predicate on the strings.** `barred_from_crossing` returns
  nothing for `eval/prompts/user.txt` and for `prompts/user.txt`, and refuses
  an absolute one.

**A name has moved once before, and nothing failed.** Since `af7c480` the file
recorded is the one resolved against the suite. Its name was relative to the
suite's directory until 0.7.1, and relative to the perimeter since (`67f566d`,
2026-09-09), with no migration of the names already written. 0.7.1's
changelog says so: a suite kept in a subdirectory *"will see its artifacts
renamed once … it shows in the report's artifact section and **does not fail
a run**"*. No step in `store/migrate.py` rewrites an artifact key. That
sentence predates pins: since 0.19.0 a pinned file's change can fail a
comparison (ADR 0029), and what a rename does to a pin is #483.

## Decision

### 1. The defect is the second resolution, not the anchor

One declared path is resolved once, by whoever opens the file. For a
target's prompt that is the target, because the text it read is the text it
sends. `read_artifacts` records and checks what was declared. It does not
decide, a second time and against another directory, which file that was.
Ruled (ruling 1).

**It covers both formats, and they show it differently** (*Context*, both
tables):
- **In a `.py` suite it is silent.** The run exits 0, sends one file and
  records another, and in #481's third row the boundary passes a file outside
  the perimeter.
- **In a TOML suite it fails.** From the command line with a relative
  `--suite` that has a directory in it, the second resolution names a path
  that does not exist, and the run stops with exit 64 on
  `eval/eval/prompt.md`. The target has read and found the right file, and
  nothing wrong is recorded, but a suite that is right cannot run from the
  root. A relative spec with no directory in it, `suite.toml` from `R/eval`,
  does not fail: the second join lands on the right file.

### 2. Whoever reads the file reports the path it read

`ProviderTarget.artifacts()` answers the path its template read, already
resolved, and `read_artifacts` takes it as it comes. Ruled (ruling 2).

**Resolved when it is read, not when it is asked.** *Decided here,* as what
"the path it read" means. `PromptTemplate` reads at construction, which is at
the suite's import, and `artifacts()` is asked later. A path resolved at the
question would be a second resolution against whatever the working directory
had become by then. Nothing in digline changes the working directory between
the two (no `chdir` under `src/` or a package's `src/`), but a suite's own code
can.

**The path used for reading is not the name the run records.** The name is §3.

### 3. The name a run records keeps its form

The name stays relative to the perimeter, as `read_artifacts` has keyed it
since 0.7.1, and it is computed from the file actually read. Ruled
(ruling 6).

- **Where the two resolutions agreed, nothing moves.** The name is
  byte-identical to the one `ff90d56` records, and so is everything that reads
  it: `compare`'s
  artifact deltas, ADR 0042 §3's check at the exits, ADR 0034's projection
  token, the runs page's label and the register's `artifacts_changed`.
- **Where they disagreed, the name and the content change together.** The
  run records the file the target read, under that file's name. A baseline
  promoted from such a run recorded a file that was not sent, and `compare`
  reports the difference as an artifact change. For a file that is not
  pinned, that does not change the exit code. For a pinned one, see §7.
- **The name is never absolute.** A file outside the perimeter is refused
  before it is recorded (ADR 0042 §2), so there is no name to give it. The
  target has already read it, at the suite's import. The refusal comes after
  that read and before any provider call (§6).

### 4. Anchored to the suite only where a suite is necessarily present

Ruled (ruling 4).

| where the path is written | anchored to | why |
|---|---|---|
| `Suite.artifacts`, `Suite.pinned` | the suite file's directory | a `Suite` field is read by a front end that loaded a suite file |
| a target's field, in a `.py` suite | nothing, by digline: the reader opens it as given, so the working directory decides | a target can be built without a suite |
| a `[target]` path in a `.toml` suite | the suite file's directory, by ADR 0007 §6 | a declaration, not code. Measured: the loader joins the suite's directory without making the path absolute, so when the spec is relative `read_artifacts` joins it a second time (§1). The MCP server and `pytest-digline`'s ini pass the spec absolute |

**Why a target's path is not anchored to the suite.** A `PromptTemplate` can be
built without a suite: in a test, in a notebook, in an application that uses
the target directly. There is then no directory to anchor to. A Python object
whose path changes meaning according to who builds it is worse than the
defect this record closes (ruling 3).

**The TOML row holds as a rule, and since #481 in code.** The anchor is right,
the suite file's directory. What was wrong is that the loader hands the target
the joined path still relative when the spec is relative, so the target and
`read_artifacts` each resolved it. Only the command line and `pytest-digline`'s
`--digline-suite` pass a spec as typed; the MCP server and the ini pass it
absolute. §2 repairs that without touching the loader: the target's template
reads the joined path against the working directory, `ProviderTarget` answers
the path it read, absolute, and `read_artifacts` takes it as it comes, so
§5's refusal of a relative path is never reached. *Measured with #481,* on
every form in the record of #476's table: `--suite eval/suite.toml` from `R`,
`../R/eval/suite.toml` from `OUT`, `suite.toml` from `R/eval` and an absolute
spec, through the command line, `--digline-suite`, the ini and the MCP server.
The target answers `R/eval/prompt.md`, absolute, the provider is sent
`R/eval`'s text, and the run records `eval/prompt.md`. The loader did not
change.

**Why the target already reads the right file.** *Ruled 2026-10-07, by
Alessandro.* A relative `--suite` is relative to the working directory, so the
path the loader joins is relative to that same directory, and read from there
it lands on the right file. Not by luck: by construction. That is why the
loader does not change.

*Ruled 2026-10-07, by Alessandro, correcting the sentence that stood here.*
Before the repair of this record, a TOML target given a relative spec answers
a relative path, so §5's requirement is **not** met in that form there:
printed at `ddb57fe` (the record of #476, *The TOML forms tried*), and at
`ff90d56` the second join of that answer is what refuses the run with exit 64.
It is met through §2,
without touching the loader. That the file read is already the right one is
what makes a change to the loader unnecessary, and it is not to be confused
with §5's requirement. *Anchored to the commit instead of the day on
2026-10-07, by Alessandro: a record says the date or the commit, never
"today".*

**Measured, beside it.** *Measured 2026-10-07, at `ddb57fe` and at the code of
`e97c780`, which are identical in `host/`, `targets/` and the packages'
sources.* In every TOML form measured, the target reads and finds the right
file, `R/eval/prompt.md`, and the defect is only `read_artifacts`'s second
join. The forms, the route each was tried by, and who measured what are in
the record of #476, in its section *The TOML forms tried: these, and no
others*.

### 5. `HasArtifacts` requires a path already resolved

*Ruled 2026-10-07, by Alessandro.*

**The protocol requires every path a target answers to be already resolved.
A relative path is refused, with a sentence that names the target.** The
refusal is raised in `read_artifacts`, where the target's answer arrives,
before the run starts.

**Why.**
- **A target has no suite necessarily present, so it has no anchor.** §4's
  rule gives a relative path no directory to resolve against.
- **Resolving it against the working directory would put the second
  resolution back.** The target read its file once, against whatever it read
  against. A relative path handed to `read_artifacts` and resolved there,
  against anything, is a second resolution of one declaration, which is the
  defect of §1.

**"Already resolved" means absolute.** *Decided here,* as how the ruling is
read in code: an absolute path names one file whatever the working directory.
`read_artifacts` still normalizes it for ADR 0042 §2's check, so a symlink
pointing outward is still outside. That is a normalization, and it anchors
nothing.

**The refusal, as the code words it.** *Decided at implementation, and
accepted with this record.* A `UsageError`, so exit 64 on the command line:
*"the target Naming of suite 'qa' answers the artifact prompt.txt, a relative
path. A target reports the file it read, already resolved: a relative answer
would be resolved a second time, against a directory the target did not read
from. Answer it absolute (ADR 0045 §5)"*. **The target is named by its class's
qualified name, never by its `repr`.** A `repr` is the suite's code, and
calling it inside a refusal would run that code, which can raise or print
anything, at the moment digline is explaining why it stopped. A comment in
`_target_name` says so, so that nobody "improves" it into a `repr`. The same
naming reaches ADR 0042 §2's sentence for a target's file, which now reads
*"the target Stub of suite 'qa' answers the artifact …"*, and names the
resolved path only where it differs from the one answered.

**It reaches a target's answer and nothing else.** `Suite.artifacts` and
`Suite.pinned` stay relative to the suite file, as §4 says, and
`read_artifacts` keeps resolving them against `base`.

**The recorded name is computed from the same path the boundary checked.**
*Ruled 2026-10-07, by Alessandro.* Each declared path is normalized once, in
one place, and that one result feeds both ADR 0042 §2's check and the name
§3 records. **Why:** if the boundary normalizes and the name comes from the
path before normalization, the two diverge again. That is the defect of §1 in
other clothes: one declaration, two paths made from it, and a check that
answers for a file the record does not name.

**So a symlink is recorded under the file it points at.** *Accepted with this
record.* A target answering a link inside the perimeter that points at another
file inside it has that other file's name recorded, and ADR 0042 §2's boundary
is measured on the same resolved file. The bytes recorded are the same either
way; the name is the file's, not the link's. Test plan entry 8 holds it.

### 6. The accepted cost: a bare relative path follows the working directory

Ruled (ruling 5). In a `.py` suite, `OpenAITarget("prompts/answer.md", …)`
reads `prompts/answer.md` from wherever the process was started. It is
anchored by hand:

```python
target = OpenAITarget(
    Path(__file__).parent / "prompts/answer.md", model="gpt-5", max_tokens=1024
)
```

**It is not refused.** `ProviderTarget` resolves the path when its template
reads it and answers it absolute, so §5 is met. ADR 0042 §2's check then
applies to the file that was read. In #481's third row that file is outside
the perimeter, so the run is refused instead of sending it. *Measured with
#481:* run from `OUT`, the command line exits 64, the MCP server raises a
`ToolError` and `pytest-digline` reports an error, by its flag and by its ini,
each with ADR 0042 §2's sentence. A provider that writes down every prompt it
is sent was called zero times, and no run file was written.

**Where the docs already anchor, and where they did not.** `docs/api.md`,
`docs/metrics.md`, `digline-anthropic`'s README, the three plugins' docstrings
and `examples/prompt-first` anchor with `Path(__file__).parent`. The READMEs of
`digline-openai` and `digline-bedrock` passed a bare path. #485 corrects them.

### 7. What happens to the records this one rests on

- **ADR 0042 §2 is amended** (ruling 7). Its boundary stays, and still
  reaches what a target answers: a file outside the perimeter is not read into
  a run, whichever way it was declared. What goes is the anchor its reference
  to ADR 0007 §6 carried to a target's path. The note goes in §2, and it
  annotates the test plan's second entry inside it, rather than as a note of
  its own. That entry, *"a `.py` suite whose target answers an outside path
  through `HasArtifacts`"*, still holds. "Outside" is now said of the file the
  target read, not of the suite's directory joined to the path it gave.
- **ADR 0007 §6 gains a dated note, not an amendment.** Its rule stays true
  for the TOML form: a `[target]` path is anchored to the suite file's
  directory. The loader applied it without making the path absolute, which is
  the TOML half of §1, and §2 repairs it. What was carried past the TOML
  form was ADR 0042 §2's reference to the rule, and that reference is what
  this record amends.
- **ADR 0029 §4 is touched, and its note travels with #481's code.** §4 says
  pinning a prompt a target contributes *"is legitimate and must work"*, and
  a pin is resolved against the suite (§4 here). After §2, a target's prompt
  is keyed from the file it read. With an anchored path the two keys agree as
  they did before. A pinned target prompt declared with a bare relative path never
  reaches the provider from a working directory other than the suite's: the
  run is refused and nothing is sent. Which refusal fires depends on where
  that directory is. Inside the perimeter, with a file of that name,
  `read_pinned` refuses it: *"pins prompt.md (as eval/prompt.md), which this
  run records no artifact for"*. Outside the perimeter, ADR 0042 §2's boundary
  refuses first, in `read_artifacts`, and `read_pinned` is never reached.
  Where no such file exists, the suite's own import fails, exit 64, as on
  `main`. Measured with #481.

## Consequences

- **A target that answers a relative path through `HasArtifacts` is refused at
  `run`**, with a sentence that names it. The protocol is public, so this is a
  break for any such target outside the tree. Inside it there is none:
  `ProviderTarget` is the only implementation, and §2 has it answer absolute.
- **A `.py` suite whose target names a bare relative prompt, run from a
  directory other than the suite's, records the file it read.**
  - If that file is outside the perimeter, the run is refused before any
    provider call, by ADR 0042 §2's sentence. *Measured with #481,* as §6
    says.
  - If it is inside, its name is the one §3 computes from it. Against a
    reference promoted before the repair, `compare` reports the old name as no
    longer declared and the new one as added. That is the shape measured on a
    rename with identical content. For a file that is not pinned the exit code
    does not move.
- **Where the two resolutions agreed, nothing moves.** The name, the digest
  and every reader of them are as they were (§3). That covers every suite that
  anchors its target's path, and every TOML suite that ran before #481.
  *Measured with #481:* a reference promoted from the agreed case on
  `ff90d56`, compared with a run on the repair, exits 0 with
  `artifacts_changed: false` and `config_changed: false`.
- **§2's repair mends two opposite failures.** *Measured with #481,* on the
  command line, the MCP server and `pytest-digline`'s flag and ini.
  - **In a `.py` suite** it records the right file instead of the wrong one.
    Before it, the run passed and recorded a file that was not sent. After it,
    run from `R`, the provider is sent `R`'s text and the run records
    `prompt.txt` with that text.
  - **In a TOML suite** it stops a refusal that threw away a valid run.
    Before it, `--suite eval/suite.toml` from the root exited 64 on
    `…/eval/eval/prompt.md`, for a suite whose prompt is where it says, and so
    did `../R/eval/suite.toml` from `OUT`. After it the target answers
    `R/eval/prompt.md`, absolute, and the run records `eval/prompt.md`, as
    every other way of running it does (*Context*, the TOML table). The loader
    did not change.
- **A pinned target prompt declared with a bare relative path never reaches
  the provider from a working directory other than the suite's: the run is
  refused and nothing is sent.** Which refusal fires depends on where that
  directory is. Inside the perimeter, with a file of that name, `read_pinned`
  refuses it: *"pins prompt.md (as eval/prompt.md), which this run records no
  artifact for"*. Outside the perimeter, ADR 0042 §2's boundary refuses
  first, in `read_artifacts`, and `read_pinned` is never reached. Where no
  such file exists, the suite's own import fails, exit 64, as on `main`.
  Measured with #481 (§7). ADR 0029 §4's note says the same.
- **A prompt missing at a suite's import now names its absolute path, and
  that path reaches an MCP agent.** `PromptTemplate` makes its path absolute
  when it reads it (§2), so the `FileNotFoundError` of a bare relative prompt
  that is not there carries the machine's absolute path where `main` carried
  `prompt.md`. Through the MCP server the agent receives it whole: it crosses
  by [ADR 0043](0043-a-message-digline-did-not-write.md) §1 as amended, because digline
  asked for the read and the system wrote the words. *Measured with #481,*
  in-process through the MCP server, against `ff90d56` as the control.
  *Ruled 2026-10-07, by Alessandro:* it is a deliberate widening of what
  crosses to an MCP agent, allowed by ADR 0043 §1 as amended. Whether that is
  a boundary stays open, in the queue of rulings, where it is the third case
  and the first produced by us rather than found. The ruling is written in the
  record of #476 before this text cited it.
- **No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no migration.** No document
  gains a field, and the recorded name keeps its form.
- **In the change that carries this record:** ADR 0042 gains an `Amended:`
  line and a note in §2, which also annotates its test plan's second entry.
  ADR 0007 §6 gains a dated note. digline.dev gains this record's three
  entries.
- **Done with #481's code:** the four docstrings named under *Requires*, and
  `PromptTemplate`'s, `docs/api.md`'s `ProviderTarget` section, a changelog
  entry, and ADR 0029 §4's note.
- **#476's other half is #485.** It corrects the `digline-openai` and
  `digline-bedrock` READMEs. Their tests, and `digline-anthropic`'s, ran each
  example from the directory its `__file__` names, so a bare relative path
  passed them. Since #481 they run each example from another directory, and a
  bare `"prompts/answer.md"` put back in one block of each README turns its
  test red: test plan entry 11, measured.

## Alternatives considered

- **Anchor a target's path to the suite.** It is what the code did, and what
  ADR 0042 §2 stated by reference. Refused by ruling 3: a target can be built
  without a suite, and an object whose path changes meaning according to who
  builds it is worse than the defect.
- **Record the path as read, absolute, as the name.** Refused by ruling 6,
  unmeasured. ADR 0042 §3's predicate refuses an absolute key: measured on the
  strings, not on a promotion. *Deduced, not measured:* every existing
  reference would then read as a full set of renames, since every name it
  holds is relative.
- **For `HasArtifacts`, resolve a relative answer against the working
  directory.** Refused by §5's ruling. The target has already read its file.
  Resolving its answer again, against anything, is the second resolution, and
  the working directory at that moment need not be the one the target read
  against.
- **For `HasArtifacts`, resolve a relative answer against the suite.** Refused
  by §5's ruling. A target has no suite necessarily present (§4), and this is
  the behaviour #481 measured: the boundary checking a file the target did
  not send.
- **Annotate ADR 0042 §2 instead of amending it.** Refused by ruling 7. A
  dated note is for a text that stays true. §2 stops being true for a target's
  path.

## Not decided here

**What `HasArtifacts` means where the target is not the reader.** §5 rules the
case this record was written for: a target that reads the file it names, and
answers the path it read. Two cases are left, and neither is ruled:

- **A target that names a file it does not read.** A target that calls an
  application, or a remote service, can still name the prompt that service
  uses. There is no read in the target to report, so "the path it read" has no
  referent. §5 still requires the path to be absolute, and where that path is
  anchored is the target's author's choice. Whether such a target should
  answer through `HasArtifacts` at all is not ruled.
- **That the path answered is the path opened.** The protocol requires it.
  Nothing checks it. A target that reads one file and answers another passes
  §5, and the boundary checks the file it answered. Whether something should
  check it is not ruled. The digest named below would be one way, for a
  target that keeps one.

**The double read: one file, read twice, at two moments, and it can change in
between.** The target reads the file when it is built, which for a
`ProviderTarget` is at the suite's import, and that text is what it sends.
`read_artifacts` reads the same path again when the run starts, and that text
is what the run records. After §2 and §5 the path is resolved once, but the
file is still read twice, so a file changed between the two moments is sent
in one version and recorded in the other. This record closes the divergence
of path, not the divergence of time. **A candidate, named and not proposed:**
`ProviderTarget` carries its template's digest (`PromptTemplate.sha`), and
`read_artifacts` computes one from its own read, so the two could be
compared. Whether to compare them, refuse on a difference, or record the text
the target read instead of reading again, is not ruled here.

**The wording and the class of §5's refusal.** *Settled with #481, and
accepted with this record:* §5, *The refusal, as the code words it*.

**Any signal for a bare relative path in a target.** Ruling 5 accepts the
consequence. No warning, refusal or note was ruled, and none is added here.

**Whether `docs/api.md` states the rule in prose.** *Settled with #481:* its
`ProviderTarget` section now says why `Path(__file__).parent`, in prose, and
its table of the protocols a target may answer says that `artifacts()`
answers absolute paths and that a relative one is refused.

**`compare`'s report of a rename.** Four files reported as changed when two
were renamed with identical content stays as it is. A pin blinded by a rename
is #483, and `pytest-digline`'s gate on a pin is #484. Neither is decided here.

**When anything is measured on Windows.** Nothing here schedules it. The
repair was measured on `pytest-digline` with #481, by its flag and its ini
(test plan entry 9).

## What this record does not claim

- **That the class of this defect is closed.** It is closed only where digline
  does the resolving. Where a suite's own code reads a file, and the same suite
  declares that file as an artifact, the two resolutions are the user's and
  digline's, and nothing here joins them. `tools/home_capture.py` generates
  such a suite: its target calls
  `app.reply(case.id, Path("prompt.md").read_text(…))`, which reads against
  the working directory (line 201), and the same file declares
  `artifacts=[Path("prompt.md")]`, which digline resolves against the suite's
  directory (line 208). Run from the suite's directory, they agree. Run from
  anywhere else, the run records one file and the application reads another,
  and no rule about paths can see it. The cure there is the one of §6,
  `Path(__file__).parent`, written by the user.
- **What any front end does on a route not measured.** Before the repair, the
  code was measured on all three front ends, `pytest-digline` included, in
  both formats. The TOML forms are in the record of #476, in its section *The
  TOML forms tried: these, and no others*. After it, #481 measured the command
  line, the MCP server and `pytest-digline`'s flag and ini, in both formats,
  on every form of that table. Nothing after the repair was measured with
  `system_file`, or on a route outside those.
- **Anything about Windows.** Nothing in this record ran there. `_key` has a
  fallback for a path on another drive that returns an absolute string
  (`pragma: no cover`). A file on another drive is outside the perimeter and
  refused before it is keyed. That was read, not executed.
- **That existing baselines stay valid in every case.** It was measured for
  the rename of a relative name with identical content, at `d87fb51`, on the
  command line only. The MCP server was not used for that measurement.
- **That the text recorded is the text sent.** The file is read twice, at
  two moments (*Not decided here*, the double read). This record closes the
  divergence of path, not the divergence of time.
- **That the double resolution reached anything other than the provider
  call.** #481 left that unchecked: the run file recorded the inside file's
  text.
- **That the noise floor ignores artifacts.** No reference to them was found
  in its code. That is a hint, not a proof.
- **That nobody read the old behaviour as a decision before ADR 0042.** It was
  not looked for.
- **What a pin does on a route not measured.** *Measured with #481* (§7): on
  the command line from `R/eval`, `R`, `OUT` and from two directories with no
  such file, and through the MCP server and `pytest-digline`'s flag from `R`;
  in the TOML form with `--suite eval/suite.toml` from `R` and
  `../R/eval/suite.toml` from `OUT`. Test plan entry 7 holds the case from
  `R`.

## Test plan

Each test must also fail on `main`, or it proves nothing. Where an entry
cannot fail on `main`, it says so and says what it guards instead. A working
directory is set per test, never inherited.

1. **The divergent case, in the root.** #481's layout, run from `R`. The run
   records `prompt.txt`, the file sent, with its digest, and not
   `eval/prompt.txt`. Red on `main`.
2. **The divergent case, outside.** Run from `OUT`. `run` is refused with
   ADR 0042 §2's sentence, and a counting fake provider was called zero times.
   Red on `main`, which exits 0 and sends `OUT/prompt.txt`.
3. **The agreed case.** Run from `R/eval`, and with `Path(__file__).parent`
   from `R`. The name and digest are byte-identical to what `main` records.
   Green on `main` too, by construction: it guards that the repair moves
   nothing where the two resolutions agreed.
4. **A relative `HasArtifacts` answer.** A target answering
   `Path("prompt.txt")` is refused, and the sentence names the target. The
   same target answering the absolute path is accepted. Red on `main`, which
   resolves the relative one against the suite.
5. **Resolved when read.** A suite that builds its target with a bare
   relative path and then changes the working directory before the run. The run
   records the file the template read. Red if the resolution is moved to
   `artifacts()`.
6. **The TOML form.** A `[target]` with `prompt_file = "prompt.md"`, run from
   the command line from `R` with `--suite eval/suite.toml`, from `R/eval`
   with `--suite suite.toml`, and from `OUT` with an absolute `--suite`, and
   through the MCP server. The same file is sent and recorded in every case,
   as `eval/prompt.md`. **Red on `main`:** the first case exits 64 on
   `eval/eval/prompt.md` (*Context*, measured).
7. **A pin on a target's prompt.** Anchored, run from `R`: accepted and
   pinned. Bare relative, run from `R`: `read_pinned` refuses it. This
   measures §7's deduction. If it does not hold, ADR 0029 §4's note is not
   written from this record, and the point goes back for a ruling.
8. **One normalization.** A target answers a symlink inside the perimeter that
   points at another file inside it. The recorded name is the one the
   boundary checked, the file the link points at. A symlink pointing outward
   is refused. Green on `main`, which normalizes the same path twice and gets
   the same answer. The mutation is what bites: compute the name from the path
   before normalization, and the first half goes red.
9. **Three front ends.** Entries 1, 2 and 4 through the command line, the MCP
   server and `pytest-digline`, through both its flag and its ini.
10. **A reference promoted before the repair.** Promoted on `main` from the
    agreed case, compared after it: exit 0 and no artifact change. A guard,
    green on `main` by construction.
11. **The READMEs hold the rule, not only the examples.** The README tests of
    `digline-openai`, `digline-bedrock` and `digline-anthropic` move to the
    temporary directory before executing each example, so a bare relative
    path passes them: they prove that the examples run, not that they anchor.
    Each example is executed from a working directory that is not the suite's,
    the one `__file__` names, so that a bare relative path fails. Without
    this, the rule of this record is declared and not held.
    Mutation: put a bare `"prompts/answer.md"` back in one block of each
    README, and its test goes red.
12. **Windows is not in this plan.** No runner here has it. That is stated so
    that its absence is not read as a pass.
13. **Mutation controls.**
    - Restore `base / entry` for a target's entries: 1, 2 and 4 go red.
    - Remove §5's refusal: 4 goes red.
    - Resolve in `artifacts()` instead of at the read: 5 goes red.
    - Compute the name from the path before normalization: 8 goes red.
