# ADR 0058 — The recorder: a call recorded where the application makes it

- Status: accepted 2026-11-02, by Alessandro Prandini, the text first.
  Proposed 2026-11-02. **Its decisions were ruled before it was
  written**, by Alessandro Prandini on 2026-11-02, in a design discussion that
  produced ten numbered decisions, and three of them were corrected by him the
  same evening. They are stated here as ruled, in this record's own words: the
  discussion's notes cite material that is not public, so they are not
  transcribed, as [ADR 0048](0048-the-versions-a-suite-holds-and-the-one-in-force.md)
  did not transcribe its own. **What this record adds is marked *decided here***,
  so that acceptance can rule on it item by item: the names, the recording's
  version, the order of the work, and what it learnt from measuring. Nothing in
  it is implemented
- Shipped: unreleased
- Date: 2026-11-02
- Opens: **nothing in the run schema.** This record writes no
  `SCHEMA_VERSION`, no step of `_STEPS`, no `OUTPUT_VERSION` and no
  `JOURNAL_VERSION`. Schema 23 is already travelling, with
  [ADR 0057](0057-the-replay-reads-the-trajectory-the-live-run-read.md)'s code
  on pull request #869, and this record neither rides it nor needs it to move
  again (§11). **A recording is a new document with a version of its own**,
  `RECORDING_VERSION`, born at implementation and not here (§11)
- Requires, at implementation: **two new entries in the tenant's layout**,
  `recordings/` and `recorder.toml` (§4, §10). **The sentence at
  `src/digline/store/file_store.py:145-146` extended**, or it becomes false:
  *"Nothing digline writes can land here, because every other path in the
  layout goes through `baselines/`, `runs/` or `register/`."* **The generated
  `.gitignore`** (`file_store.py:117-123`) ignores `*/recordings/` and
  `*/recorder.toml`
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter), §2 (the payload stays where it is born) and §5 (a
  case born outside world 1 gets a generated id);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §1 and §3
  (input beside output, whole or nothing);
  [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md) §1 (the
  recorded tool call);
  [ADR 0023](0023-capture.md) §2, §4, §6, §8 and §11 (a person's explicit
  label, elected by a person, the generated id, the payload regime, what
  capture never does);
  [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md) §1
  (the store lives in the end company's perimeter);
  [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §2 and
  [ADR 0048](0048-the-versions-a-suite-holds-and-the-one-in-force.md) §6 (an
  entry added to fixed decision 2's list);
  [ADR 0057](0057-the-replay-reads-the-trajectory-the-live-run-read.md) (one
  trajectory, recorded as the live run read it)
- Amends, **at acceptance**: `CLAUDE.md`'s fixed **decision 2**, by an
  **addition to the list** of what `.digline/<tenant>/` holds, in the shape of
  *"Added to the list 2026-09-29 (ADR 0036 §2)"*: the recordings of a tenant,
  one subdirectory per process, and the file that switches the recorder on for
  that tenant (§4, §10). Both are ignored by git, as `runs/` is, and neither is
  versioned the way `baselines/` is. **It is an addition and not an
  exception**: both sit inside the layout, and the decision's reason stays
  whole
- Names, and does not amend: ADR 0023. The import of §4 elects cases under its
  rules, and where the import this record foresees would go further than they
  allow, that is declared *Not decided here* rather than ruled. ADR 0034 §1 and
  the planned bridge (`CLAUDE.md`, *Structure*, `bridge/`), which §4's refusal
  applies and does not change
- Touches, in `CLAUDE.md`'s *fixed* section: **decision 2** gets an addition to
  its list (*Amends*). **Decision 8** is upheld: a recording is filed under the
  tenant it was made for, and the import refuses a recording whose tenant is not
  the suite's (§4). **Decision 9** is upheld and not edited: a recording is
  payload, whole, and nothing in `digline.wire` learns its name. **Decision 5**
  is upheld: the recorder writes files and makes no call of its own. **Decision
  7** is what makes the narrow piece possible: a single call is a recording
- Number: 0058. Swept on 2026-11-02 before a line was written, across every ref
  of this repository, local and remote, and every worktree. The highest number
  taken anywhere is 0057

**Lines cited here are at `9536a52a`**, unless a line names another commit.

## Context

**A test set made by hand lags the application it tests.** While an
application is being developed, the calls it makes to a model are the material
a suite is made of: on one day of development, tens of calls, a handful of
distinct inputs, several prompts in turn. Today none of it reaches digline. A
case is written by hand, from a memory of what the application did.

**The recorder is the piece that keeps that material**, at the place where the
application makes the call, in the shape a suite reads. It is designed now and
built in 1.1. Three facts about the code decide its shape.

**What an assertion reads is not persisted.** A provider target builds the
`Response` an assertion sees, and its `metadata` carries `finish`, `tools` and
`tool_calls` from the plugin's `Completion.as_metadata`
(`src/digline/targets/completion.py:191`). It is not written anywhere: the
comment at `src/digline/targets/provider.py:262-264` says so. ADR 0057 is the
defect this produced in a replay, and its repair is the shape a recording's
response takes. **A recorder with a serializer of its own would make the same
defect a second time** (§11).

**Case, set-up and response are already apart in the run document, and in
three different places.** The case is `Case.vars` (`src/digline/run/suite.py:165`).
The set-up is `Run.target_config` (`src/digline/core/run.py:1551`), the named
scalar parameters, and the declared files the prompt lives in. The response is
`RecordedResponse` (`core/run.py:1032`). A call recorded inside an
application has all three in one place, the call, and must separate them as it
records, or nothing later can.

**The label a person gives already has a home.** `Case.label`
(`run/suite.py:172`, of type `Label`, `src/digline/core/aggregate.py:48`) is
the human calibration label the driver reads (`src/digline/run/driver.py:1100`).
A person who says yes or no to a recorded response gives that label, before the
case it will belong to exists.

## Decision

### 1. Three levels: tenant, app, suite

**The tenant exists and keeps its meaning** (decision 8). **The suite exists**:
one prompt is one suite, with its own cases, baseline and noise floor. **The app
is the level between them**, the application that makes the calls, and the
place where the verdicts of many suites will one day be composed.

**In 1.1 the app is a field of the recording, not a directory.** It is written
on every recording and read by the import and by the status command (§10), and
it does not enter the layout. A directory would change the address of every
baseline and every run, which is fixed decision 2's subject; a field changes
nothing that exists. Whether the app becomes a level of the layout is left to
the release that composes verdicts across suites.

### 2. The suite is named at the call site

**Each call site names its suite**: `suite=` on the wrapped call. Explicit,
stable from development to production, and never derived from the code, because
a name derived from a module or a function changes when the code is moved, and
the suite's history would break with it.

**The wrapper carries the tenant and the app**; the call carries the suite.

**A call that names no suite is recorded in the app's collecting suite,
`_unassigned`**, with the module and the function of the call site. It enters
no gate until a person assigns it. *Decided here, the name:* the working name
said *unlabelled*, which already means a case without a `Label`
(`core/aggregate.py:97` and `:160`). What is missing here is a suite, not a
label.

### 3. Three compartments, from the first day

A recording separates what it records into three compartments:

| Compartment | What it holds | What it becomes |
|---|---|---|
| `case` | the messages sent, or the variables the call declares | `Case.vars` |
| `setup` | system prompt, model, parameters, the tools offered | the set-up of a run: `target_config` and the declared prompt |
| `response` | text, finish, tools, tool calls, usage | a `RecordedResponse` |

**The setup is digested**: `setup_digest`, so that the import can tell *the same
set-up answered differently*, which is noise, from *a different set-up*, which
is a change.

**The default for a single call is decided by the provider's plugin**: the
messages are the case, everything else is the setup. Where the user message
mixes a template and the data, the call may pass the template's variables as the
case with **`digline_vars={...}`**, which the wrapper takes out before the call
reaches the provider's SDK.

**One format for two sources.** A reader of trace files, planned after 1.1,
fills the same three compartments from a file. If the format serves both, there
is nothing for a later major release to break here.

*Decided here, the names:*
- `setup`, not `system`. *System* collides with the `system` argument of
  Anthropic's API, which is a field **inside** this compartment, and with
  `SystemConfig`, which is only part of it. `setup` is the word
  `SystemConfig`'s own docstring uses for what it records (*"a single set-up to
  record"*, `core/run.py:533-534`).
- `setup_digest`, not a fingerprint: *fingerprint* is already
  `Completion.fingerprint`, the provider's `system_fingerprint`, and *digest* is
  the word this repository uses for its own (`cases_digest`, the declared-price
  digest).
- `digline_vars`, because it becomes `Case.vars`. The prefix stays because the
  keyword travels among the SDK's own.

### 4. Where a recording lives, and the import that refuses another tenant

**A recording is filed under the tenant it was made for**:
`.digline/<tenant>/recordings/<process>/`. In development the tenant is the
suite's, fixed on the wrapper. In production it is resolved **per call**, from a
string or a function the wrapper is given, so that each customer's material is
filed in its own tenant's directory and nowhere else.

**The suite lives in the development tenant.** The baseline is one per suite,
not one per customer. A production tenant names where a recording came from,
on the recording, as **`source_tenant`**, and never reaches the gate: being many
tenants is a property of the material, not of the measurement.

**The import refuses a recording whose `source_tenant` is not the suite's
tenant, by name**, until the bridge exists. Bringing a production recording
into a suite that is developed elsewhere is the production-to-repository bridge,
which `CLAUDE.md`'s *Structure* lists as `bridge/`, planned and not built. Where
the cases are the end company's, ADR 0034 §1 puts the store, and the cases in
it, inside the end company's perimeter, and fixed decision 2 records that
widening. An import that crossed tenants before the bridge would be the bridge,
without its rules.

**The import elects cases under ADR 0023.** A person's yes or no on a recorded
response is an explicit label (0023 §2); the person names what is written
(0023 §4); the id is generated from the case's input (0023 §6, which ADR 0002
§5 was amended for); the regime of 0023 §8 decides whether the input may be
written to a committed file. In 1.1 the yes or no becomes `Case.label` at
promotion (§7).

**Redaction is foreseen in the format and implemented at deployment**, not in
1.1: the format has room for a response withheld as `RecordedResponse` already
writes one (`withheld`), and §10 refuses to start without a declared redaction.
**So in 1.1, in production, the recorder starts only where `redact = "none"` is
written**: no other declaration has an implementation behind it to honour.

### 5. The episode, and nesting

**`digline.episode` is in 1.1, with nesting.** It is a context around one turn
of an agent or one pass through a chain. The single calls made inside it are
attached to it. **An episode is a recording with the same three compartments**:
the case is the message that started it; the setup is the digest of its
children's setups (§8); the response is the final output, with the trajectory
derived from the children in ADR 0057's form.

*Noted 2026-11-03: the public names are `digline.recorder.wrap`, around the
provider's client, and `digline.recorder.episode`, with `digline.recorder.attach`
beside it. `digline.episode`, as this record writes it, does not exist: the
top-level package does not import the recorder, so that importing `digline`
costs nothing while the recorder is off.*

It is compared by `ToolsCalled`, which exists. **No new assertion on the
trajectory comes with it.**

**An episode delimits a case.** In code, an episode does it; in a file, the
reader of trace files will do it after the fact, applying the same notion and
not inventing it. A chain seen node by node is a set of single calls; the
episode is the case that matters.

*Decided here, what the code taught:*

- **The episode's id is propagated explicitly.** It lives in a `ContextVar`,
  and a context variable reaches an asyncio task and `asyncio.to_thread`, but
  not a thread started with `threading.Thread` nor a `ThreadPoolExecutor`
  worker. That was observed on 2026-11-02 on CPython 3.14.5, with a command
  that was not saved; the implementation owes it as a test. A framework that
  runs synchronous nodes in a pool would leave the children outside the episode
  without a sign. So the episode exposes its id, and a call made in another
  thread or another process attaches to it by passing that id.
- **A child the recorder cannot attach is an orphan, and is declared as one.**
  It is recorded with the episode id it was given, or with none, and the import
  says how many it found. It never disappears into the collecting suite, and it
  is never attached by guessing from timing.
- **Processes.** Each process writes its own subdirectory (§10), so an episode
  whose children run in another process has recordings in two subdirectories,
  and the import joins them by the episode id. The subdirectory is chosen at the
  first write, not at import, so that a process forked after importing the
  wrapper does not write into its parent's.

*Noted 2026-11-03 ([ADR 0060](0060-the-steps-of-a-trajectory-live-recorded-and-collected.md) §3), and the section above kept as written.* A run of
digline collects the calls a wrapped client makes inside the target's call,
recorder on or off, through a context variable that `host` sets around that
call alone. An episode the application opens there hands its calls to the
collection as well: off, it stays the empty context this section describes;
on, it records as it does here. The collection meets the same limit as the
episode's id: it does not cross a `threading.Thread` or a `ThreadPoolExecutor`
worker, and `attach(id)` is the way across.

### 6. Where the code lives

**The format, the three compartments, the episode, nesting and the import are
digline's.** Each provider plugin — `digline-anthropic`, `digline-openai`,
`digline-bedrock` — adds two things: the map of which field of its provider's
request is case and which is setup, and the reading of finish, tools and usage
from the reply. The second is code the plugins already have: they read finish at
`packages/digline-anthropic/src/digline_anthropic/client.py:444`,
`packages/digline-bedrock/src/digline_bedrock/client.py:365`, and
`packages/digline-openai/src/digline_openai/client.py:333` and `:379`. The
first is new: today the request is built by `ProviderTarget.__call__`
(`targets/provider.py:207-218`), not by the plugin. Each plugin ships a minor
with 1.1. Without digline a plugin has nothing to write to, and without a
plugin digline cannot separate a provider's call.

*Noted 2026-11-04, and the paragraph above kept as written: one map shipped
before 1.1.* `digline-anthropic` 0.8.0, published on 2026-11-03, carries its
recording map, declared under `digline.recording_maps`. It is inert until
digline itself has `digline.recorder`: 1.0.3, the latest release on PyPI when
this note was written, has none, so no released digline loads the map before
1.1. `digline-openai` 0.6.0 and `digline-bedrock` 0.7.0 carry no map, and
their minors still come with 1.1.

**In the layers**, the wrapper reads files and the clock (§10), so it sits with
`digline.host`, the one layer allowed to. `digline.core` gains nothing that
does I/O, and `tests/test_layering.py` stays as it is.

*Decided here:* the openai plugin assembles its `Completion` inside
`complete()` (`client.py:283-345`), and has no function from a reply to a
`Completion` the way the other two do (`completion_of`, anthropic `:435`,
bedrock `:350`). It gains one, so that the wrapper reads a reply with the code
the target already uses.

### 7. Foreseen in the format now, built later

- **Every step of a trajectory carries its index**, for the order assertions
  planned after 1.1 will read.
- **Finish belongs to the steps where a model answered.** A model step carries
  the finish its reply reported; a tool step has none, because a tool does not
  end a reply. A single call is one model step, and `RecordedResponse.finish`
  is its finish.

  *Noted 2026-11-03 ([ADR 0060](0060-the-steps-of-a-trajectory-live-recorded-and-collected.md) §1): confirmed, and built on.* One function makes
  the steps of a trajectory, a single call's and an episode's alike: one
  `model` step per call, with its finish, then one `tool` step per call it
  asked for.
- **A canonicalised argument carries the type it came from beside it.**
  `canonical` reduces a value it does not know to `"<TypeName>"`
  (`core/types.py:382`), so a `datetime` and the string `"<datetime>"` become
  the same value. The type beside it (`"datetime"`) is what a later repair will
  read. Written as an absent-is-not-recorded key, it is additive when it comes.
- **Every recording carries a `label` compartment, empty.** It is
  `Case.label` before the case exists: the person's yes or no at the import in
  1.1, a label given downstream later, or a labelled archive someone already
  has. At promotion it becomes `Case.label`. Labels are consumed, never
  collected by digline. The yes or no at the import is not a collection: it is
  the person's own label, given once, by the person, and digline never infers
  a label from anything else.

*Decided here, the name:* `label`, singular, of type `Label | None`: the same
name and the same type as the field it becomes. The collision between the
working name and `Case.label` was what showed that they were one datum.

*Noted 2026-11-03 ([ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md)),
and the section above kept as written.* The yes or no at the import is not
`Case.label`. `Label` is the class of the input where a suite has ground
truth, and the person at the import judges the recorded answer. So the yes
or no makes a case of a kind of its own, a reviewed answer, judged by the
named check and failing where the judge contradicts the person. The import
no longer writes `Case.label`, and the `label` compartment of a recording
stays what it is: a label given downstream, or a labelled archive.

*Noted 2026-11-04 ([ADR 0062](0062-the-recorder-out-of-process-and-in-other-processes.md)
§2), and the section and the note above kept as written.* The `label`
compartment is out of the recording's contract, and is gone from the
recording with it: no reader read it, and a writer in another language is not
asked to fill a field nobody reads. A file written with one is still read,
and the key ignored. A label given downstream, or a labelled archive, has no
place in a recording in 1.1.

### 8. The setup of an episode

**An episode's `setup_digest` is the digest of its children's setups and the
repository's `git_commit`** (`src/digline/host/environment.py:64`). It may be
declared by hand with `setup=` on `digline.episode`.

The commit is there because a chain may run steps that call no model. When one
of those changes, no prompt moves; with the children's setups alone, the import
would see *the same setup, different responses*, and report as noise what is a
change.

### 9. A step, and who acted

**A step of a trajectory is a `RecordedStep`, and it carries an `actor`**:
`model` or `tool`, and `engine` when someone declares one by hand in a later
release. 1.1 produces `model` and `tool` only. A step that runs no model and is
no tool call is invisible to the wrapper: it is part of the setup until someone
declares it.

*Decided here, the names:* `RecordedStep`, because `Step` is already
`digline.store.migrate.Step` (`src/digline/store/migrate.py:140`), and the
prefix puts it beside `RecordedResponse` and `RecordedToolCall`. `actor`,
because `kind` is already `RecordedResponse.kind`, the branch of `Output` a
response's text came from, one level up from where a step sits.

### 10. How it is switched on

**Wired once, in code.** The wrapper goes around the provider's client, with
`app=`, and `suite=` goes on each call. **There is no automatic hooking of the
provider's library**: every call would land in `_unassigned`, and the suite is
the one thing §2 says must be explicit.

**Switched outside the code, and off by default.** Off, the wrapper passes the
call through. On, it records. It is switched on by a file,
`.digline/<tenant>/recorder.toml`, or by an environment variable. **The file
is ignored by git, in the generated `.gitignore`, like `*/recordings/`**: a
switch that was committed would switch recording on for everyone who clones the
repository.

**A status command** says whether the recorder is recording, where, and how many
recordings each suite has gained since the last import.

*Amended 2026-11-03, by Alessandro Prandini's decision, at implementation:
how "since the last import" is known.* Not from a ledger: ADR 0023 §9 allows
the import no memory but the draft. Each case the import writes carries
`examined_through`, the newest `recorded_at` among the suite's recordings the
person was shown, and each recording now carries `recorded_at`, the system
time it was written at. The count is the suite's recordings written after the
newest `examined_through` in its draft. The status reads it only when it is
given the suite, because only the suite says where its draft is. A suite whose
draft holds no case from the recordings is *never imported*, said with its
total. A recording with no `recorded_at` is never counted as after the
watermark.

**In production:**
- it is switched on by a command, per tenant, which writes the file;
- the wrapper re-reads the file at an interval, so no restart is needed;
- it refuses to start, loudly, in three cases: **no declared redaction**
  (`redact = "none"` is allowed, and must be written), **no declared sampling**,
  and **no writable directory with a ceiling on its size**;
- at the ceiling it stops recording and says so in the status. It does not
  rotate and it does not delete;
- one subdirectory per process, and the import joins them;
- recordings already imported are deleted only by an explicit command.

**The wrapper is Python.** An application in another language is not served by
it in 1.1.

*Noted 2026-11-04 ([ADR 0062](0062-the-recorder-out-of-process-and-in-other-processes.md)),
and the sentence above kept as written: it stays true of the wrapper, and is
no longer the whole of the recorder.* An application in another language is
served in 1.1 by two other doors that write the same recording: a proxy,
`digline record proxy`, between its SDK and the provider, and an interceptor
copied into a Java project. The recording's format becomes a public contract.

*Decided here, what off costs, and how it is held:*

- **Off must not import `digline.core`.** Importing it is not cheap: measured
  once on 2026-11-02 at `cd71a383` on CPython 3.14.5, about 50 ms warm with
  274 modules loaded, with a command that was not saved, so the figure is
  indicative and the implementation owes the saved measurement. Off, the
  wrapper's module imports nothing of digline's beyond itself, and everything
  else is imported at the first recording.

  *Amended 2026-11-03, decided in the conversation of the session that
  implemented it, after a pass as a user measured the first recording holding
  an asynchronous client's event loop for about 90 ms:* where the recorder is
  on when the client is wrapped, `wrap()` imports what the first recording
  would, at the application's start. Off, nothing changes, and the test that
  `digline.core` is not in `sys.modules` holds as written. Switched on later
  from the file, the first recording still imports it, once.
- **The cost per call off is measured, not declared.** It is a test that
  imports the wrapper off and asserts that `digline.core` is not in
  `sys.modules`; a benchmark of a client injected without network, called bare
  and wrapped off, against a threshold the implementation states; and the
  interval check, which is one comparison of a monotonic clock per call, with
  the file read only when the interval has passed.

*Noted 2026-11-03 ([ADR 0060](0060-the-steps-of-a-trajectory-live-recorded-and-collected.md) §3), and the cost off kept as written for every process
that is not a run of digline.* The wrapper reads one context variable per call
before it asks whether recording is on, and hands the reply to a collection
where one is open. Only `host` opens one, around the target's call in a run,
and never the wrapper on its own, so production never does. The two tests
above hold as written: the variable lives in `digline.recorder`, and the read
is inside the stated threshold.

### 11. One serializer, and the recording's own version

*Decided here:*

- **The response compartment is written by the function that writes a recorded
  response into a run document**, not by a second one. Two serializers of one
  fact are how a trajectory came to have three forms (ADR 0057).
- **A recording carries `RECORDING_VERSION`.** It is a document of its own,
  beside the run document's `SCHEMA_VERSION` and the journal's
  `JOURNAL_VERSION`, and it moves on its own schedule. **A reader older than a
  recording refuses it by name**, saying which version it read and which it
  knows, and never reads a newer recording as an older one.
- **The run schema does not move for this record.** A recording's response
  compartment holds what `RecordedResponse` holds at the schema the writing
  digline writes. Schema 23 brings `finish` and `tools`, and is enough.

### 12. A finish no plugin normalised

*Decided here:* the vocabulary of `Finish` is applied by the provider plugins,
and only there. A recording made without a plugin, or by a function, carries
the text it was given, the way a recorded response already does on the branch
of #869. A finish nobody normalised is not read as one of `Finish`'s words.

### 13. The order of the work

*Ruled by Alessandro Prandini on 2026-11-02:* 1.1 carries all three pieces
below, and they are built **in this order**. The order is the declared limit,
not the boundary of 1.1: whatever is built, is built after what comes before it
in the list.

1. **The narrow piece**: the wrapper around the synchronous, non-streaming
   client of each of the three plugins; the episode with nesting inside one
   thread and across asyncio, with explicit propagation and declared orphans;
   the switch, its three refusals and its ceiling; the status command; and the
   narrow import, the person's yes or no under ADR 0023.
2. **Streaming and asynchronous clients.** None of the three plugins uses
   either today; a wrapper around an application's client meets both.
3. **The rich import**: proposing an assertion from the shape of the output
   and sampling by output (*Not decided here*).

At the end of November 2026 what exists is looked at, and whether anything of
it moves to a later release is decided then, not here.

## Consequences

**No run document changes.** No step, no key, no reader of runs is touched.

*Noted 2026-11-03 ([ADR 0060](0060-the-steps-of-a-trajectory-live-recorded-and-collected.md) §5), and the sentence above kept as written: it no
longer holds for 1.1.* The steps of a trajectory enter the run document in
1.1, as `steps` on a recorded response, on schema 23's step, which still
writes nothing. This record foresaw it in *Alternatives considered*: *"Steps
enter the run document when assertions read them live, so that the live form
and the document move together"*. In 1.1 four assertions read them live, so
the document moves with them. In a recording, the steps move into the
response, and `Recording.steps` goes (ADR 0060 §6).

**The layout gains two entries per tenant**, `recordings/` and
`recorder.toml`, and the generated `.gitignore` gains both: `*/recordings/`,
because a recording is payload and is never committed, and `*/recorder.toml`,
because a switch that was committed would switch recording on for whoever
clones.

**Three plugin minors ride 1.1**, one per provider.

**A person who imports records labels**: the import is where a recorded
response becomes a case, by a person's yes or no, under ADR 0023's rules.

## Why one record, and not three

*Decided here.* The refusal of another tenant (§4) and the app as a field (§1)
could each have been an amendment of its own, to ADR 0034 and to fixed decision
2. Neither changes either. The refusal **applies** ADR 0034 §1: it refuses what
that section already keeps inside the end company's perimeter, until the bridge
gives a way across. The app as a field adds nothing to the layout. The one
change to the fixed section is the two new entries of §4 and §10, and the
precedent for that change is that the record which adds an entry amends the
list itself (ADR 0036 §2, ADR 0048 §6). Three records would have given two of
them nothing to decide.

## Alternatives considered

**Reform schema 23 before it ships, into steps.** It would replace
`tool_calls`, `tools` and `finish` with a list of steps. Rejected:
- ADR 0057 records `tools` beside `tool_calls` so that a target whose two lists
  disagree is replayed as it was judged, and one list of steps cannot hold the
  disagreement;
- the live form an assertion reads would stay the three keys, and the document
  would hold a fourth form, which is the defect ADR 0057 closes;
- the migration would stop writing nothing: it would rewrite every stored
  document that holds `tool_calls`;
- a journal written by 1.0 and read back in a resume would meet a shape it did
  not write, and `JOURNAL_VERSION` does not move with the schema.

A single recorded response is one model step and its tool steps, so the
schema 23 fields read as steps without loss. Steps enter the run document when
assertions read them live, so that the live form and the document move
together.

**The app as a directory.** Rejected for 1.1: it moves every address in the
layout to compose verdicts nobody composes yet.

**Hooking the provider's library automatically.** Rejected: every call would
land in `_unassigned` (§10).

**`system` for the setup compartment.** Rejected: §3.

**The recorder's own serializer, shaped to the recording.** Rejected: §11.

## Not decided here

- **A label from more than one source.** `Case.label` holds one value. The
  person's yes or no at the import, a label given downstream and a labelled
  archive may disagree about one case, and which one wins is not ruled.
- **The rich import against ADR 0023.** Proposing an assertion from the shape
  of the output and sampling by output go beyond what 0023 §4 allows a listing
  to do (*nothing ranked, scored, starred or pre-selected*), and an expected
  read from the recorded response may be what 0023 §11 item 1 forbids. Built
  third (§13), and ruled before it is.
- **How a suite declares recordings as its source.** ADR 0023 §3 declares a
  source in Python with a reader; recordings are read by digline. Whether the
  declaration still has to be code is 0023 §3's question, asked again.
- **The bridge.** §4's refusal lasts until it exists, and this record does not
  design it.
- **How redaction is implemented**, at deployment.
- **An application in another language.**

  *Noted 2026-11-04 ([ADR 0062](0062-the-recorder-out-of-process-and-in-other-processes.md)),
  and the item above kept as written.* Decided there for 1.1: the proxy for
  any SDK that takes a base URL, and an interceptor for Java. .NET, Node and
  Go interceptors are left after it.
- **A review interface over recordings, and recording a response flagged from
  inside the application.** Neither is part of this record.

  *Noted 2026-11-03 ([ADR 0061](0061-a-local-page-whose-views-other-packages-may-extend.md)),
  and the item above kept as written.* The first half is decided there: a
  local page over `.digline/`, served by `digline view`, reads the
  recordings and writes two things, the switch and an imported case, through
  the host functions `digline record` calls. The second half, recording a
  response flagged from inside the application, is not decided there.
