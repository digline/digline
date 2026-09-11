# ADR 0017 — The journal and the resumed run

- Status: accepted — the text first, the implementation written against it, the
  way [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0011](0011-the-mcp-server.md), [ADR 0012](0012-the-reading.md),
  [ADR 0013](0013-the-pytest-plugin.md),
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) and
  [ADR 0016](0016-the-canary-case.md) were
- Date: 2026-09-11
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) (the
  perimeter is a directory, and the payload stays where it is born);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §3
  (artifacts are recorded by digest and are not part of `config_hash`);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §3 (beside the
  hash and not inside it), §8 (one run measures one system, and the target is
  asked again after the last case), §9 (what the provider *said* answered);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §8 (the announcement
  before the first call);
  [ADR 0008](0008-the-two-run-report.md) §2 (the exit code is the contract);
  [ADR 0011](0011-the-mcp-server.md) §7 (two front ends over one host, and
  nothing imports the CLI);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule), §6
  (what a bump costs downstream);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §1 (a
  recorded answer is what the *target* said), §6 (a replay declares itself);
  [ADR 0016](0016-the-canary-case.md) §2 (the announced bill has to match the
  invoice)
- Turns into surface: [`AGENTS.md`](../../AGENTS.md) §7 (say what a hunt will
  cost before starting it) — §11 is what keeps that sentence true of a resumed
  run; and §6 (the exit codes are the contract) — a resume that is refused is a
  usage error and never a verdict about a suite
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 2 is upheld — the
  journal lives in `.digline/<tenant>/`, under the same ignored directory as the
  runs, and nothing of it is written outside the repository. Decision 9 is
  upheld by §2: the journal is not a document, never crosses a boundary, and
  `digline.wire` never learns its name.
- **`SCHEMA_VERSION` does not move.** That is a *condition* of this record and
  not a consequence of it, and §10 is where it is argued rather than assumed.

## Context

A 720-call run — 144 cases at five samples, about four dollars of Sonnet — was
killed part way through by a supervisor outside digline, on system memory
pressure. digline was not the cause: measured over the same suite through the
real SDK, the process is flat at 89–103 MB peak and accumulates roughly 900
bytes per call, all of it the combined verdict and its sample scores. Nothing of
the provider's reply survives the case: the thinking blocks never enter a
`Completion`, the SDK object dies inside `_complete`, and `Response` and
`EvaluatorInputs` die at the end of the case.

What the kill cost was not memory. It was **everything**. `cmd_run` calls
`execute()` and then `write_run()`, so until the last case of the last sample
there is no file anywhere. Seven hundred paid calls and a judged run existed
only as objects in a process, and a signal took them.

There is a second loss in the same shape, one level down. In `_run_case`, a
target that raises at sample 4 of 5 errors the **whole case** — correctly, by
ADR 0006: a partly-sampled case would be a weaker measurement claiming to be the
declared one. But the three answers already bought are dropped with it, and the
case leaves a hole in the run: an errored verdict makes the run unpromotable and
exits 2, so the remedy today is to run the other 143 cases again. A 529 that
outlives the SDK's own retries therefore costs the price of the whole suite.

Both losses come from the same missing thing: **a run has no state between its
first call and its last.** This record gives it one — a journal beside the run
file, written per case as the run goes, and a `--resume` that finishes what a
killed run started. It is deliberately not a retry policy, not concurrency and
not a checkpoint of the provider's answers; §"Not decided here" says which of
those it declines and why.

One sentence sets the frame for everything below, because every hard question
here reduces to it: **a run is a claim, and a resumed run may only be assembled
when every fact the claim asserts is true of both halves.** Half a run under one
prompt and half under another is not a run. §6 is that sentence turned into a
list, and §10 is the same sentence answering the schema question.

## Decision

### 1. Per case, and the granularity is the payload boundary

The journal records one entry per **case**, never per sample.

Per-sample would be the tempting granularity — it caps the loss at one call
instead of `samples - 1` — and it is refused for a reason that is not about
cost. A sample is an *answer*: to resume inside a case, the journal would have
to hold the model's outputs so the remaining samples could be judged beside
them, and it would hold them for **every run**, including the ordinary run that
declares `record_responses=False` precisely so that no answer is written down
(ADR 0015). The cheapest checkpoint would quietly become the product's most
complete store of payload.

Per case, the journal holds a `CaseResult` — which is exactly what the run file
holds, and nothing that the run file would not. A suite that records its answers
journals them because its run file carries them anyway; a suite that does not,
does not. That is the whole rule, and it is worth stating in its own sentence:
**the journal never holds anything the finished run file would not hold.**

The cost of the choice is stated rather than buried: a crash inside a case loses
up to `samples - 1` paid calls. At `samples=5` that is four calls out of 720.

### 2. The journal is a work file, not a document

    .digline/<tenant>/runs/<suite>/.pending/<key>.<leg>.jsonl
    key = <slugged created_at>-<config_hash>      # the run's own key, ADR 0002
    leg = 1, 2, 3 …                               # one file per attempt

Everything that follows from "not a document" is a rule, and each one closes a
question somebody would otherwise have to ask:

- It lives **under `runs/`**, so the generated `.gitignore` already covers it:
  `*/runs/` ignores the directory and everything beneath it. No new ignore rule,
  and no possibility of a journal reaching a commit.
- It is **never migrated**. `run_paths()` globs `*.json` in the suite directory;
  a `.jsonl` inside `.pending/` is neither matched nor wanted. The journal
  carries its own `JOURNAL_VERSION`, independent of `SCHEMA_VERSION`, because it
  is a *format*; it has no migration because it is a *work file*. A journal this
  digline cannot read is a journal this digline does not resume, and it says so.
- It is **never listed, compared, reported, viewed or explained**. `scan_runs`,
  `list_runs` and `run_paths` glob `*.json` in the suite directory and see
  nothing here. The only commands that know the journal exists are `run` and
  `--resume`.
- It is **never redacted**, because redaction is what happens on the way out and
  this never goes out. `redact()` is a function on a `Run`; the journal holds
  no `Run` until the run is written. The wire does not learn its name, which is
  condition 3 of the passenger rule (ADR 0014 §1) answered by the file not being
  a passenger at all.
- It is **deleted when the run file is written**, and §12 says what happens to
  one that outlives its run.

### 3. Three records, one serializer

Each line is a JSON object with a `kind`. The header is line 1 of every leg.

    {"kind": "header", "journal_version": 1, "leg": 1,
     "created_at": …, "started_at": …, "digline_version": …,
     "tenant": …, "environment": …, "suite": …, "config_hash": …,
     "cases_digest": …, "artifacts": {path: sha, …},
     "target_config": {…}, "judge_config": {…},
     "record_responses": false, "git_commit": …}

    {"kind": "observed", "target_config": {…}, "judge_config": {…}}

    {"kind": "case", "cause": "target", "case": {…}}

The `case` payload is produced by **the run file's own case serializer** —
`_case_to_dict` becomes `case_to_dict`/`case_from_dict` in `digline.core.run`
and gains no behaviour. Two serializers for one value is how the journal and the
run file start to disagree about a sampled verdict, and the disagreement would
surface as a resumed run whose reused half is subtly not what it would have
been.

Three properties of the format, each of them load-bearing:

**Append-only, so a retry adds a line rather than editing one.** A `case_id` may
appear more than once — §9 retries errored cases — and the **last** record for a
`case_id` is the one that counts. Nothing rewrites a journal in place.

**A torn last line is discarded on read.** The process was killed while writing
it; it is the one line whose absence is expected. Every earlier line parsed, so
every earlier case survives. A line that fails to parse anywhere *but* at the
end is a corrupt journal, refused by name rather than repaired.

**Flushed and fsynced after every record.** A kill would survive a mere flush,
but the incident that produced this record was memory pressure on a whole
machine, and the syscall costs microseconds against a case that cost a network
call. The one thing this file may not do is be fast and empty.

`cause` is the field the run document has no room for: which layer produced the
error — `"target"`, `"mapper"`, `"assertion"`, or `""` for a case that did not
error. It is here and only here, and §9 is what reads it. This is the shape of
the whole record: **the journal may hold what the document does not, precisely
because it is deleted on success.**

### 4. `execute()` gains two arguments, and still knows nothing about the store

    def execute(suite, target, *, created_at, mapper=default_mapper,
                git_commit=None, run_metadata=None, artifacts=None,
                done: Mapping[str, CaseResult] = {},
                on_case: Callable[[CaseProgress], None] | None = None) -> Run

`done` maps `case_id` to a result already judged. Those cases are **not called**;
their results are placed in the run at the position the *suite* gives them, not
the position the journal does — so a resumed run's `results` sequence is in the
same order as an uninterrupted one's. A `done` entry naming a case the suite does
not declare is refused at the top of `execute()`: it is a pure-driver invariant,
and a library caller who passes one gets told rather than getting a run assembled
out of two suites.

`on_case` is called once per finished case, before the next one starts, with:

    @dataclass(frozen=True, slots=True)
    class CaseProgress:          # digline.core
        result: CaseResult
        observed_target: SystemConfig
        observed_judge: SystemConfig
        cause: Cause = ""        # "" | "target" | "mapper" | "assertion"

`CaseProgress` is defined in **core**, and that is a layering decision rather
than a filing one. The driver produces it and the store consumes it, and the
store may not import `digline.run` — so a value defined beside `execute()` would
either invert the dependency or force the store to accept an untyped object. It
is a pure value made of core types, which is what core is for.

The observed configurations travel with each case rather than being asked for at
the end, because §7 needs them to have been **written down before the crash**.
Asking the target is a property read on an object the driver already holds; it
calls nothing and costs nothing.

**`on_case` is not wrapped in a `try`.** Everything else in `_run_case` is
contained — a target that raises errors its case, a broken assertion errors its
own line — and this one is deliberately not. The failure it would hide is a
journal that stopped recording while the run went on for another six hundred
calls, which is the exact loss this ADR exists to end. A journal that cannot be
written stops the run at the case it failed on, with every earlier case on disk.

### 5. The store owns the journal, and journaling is its own protocol

    @runtime_checkable
    class SupportsJournal(Protocol):                     # digline.store
        def open_journal(self, header: JournalHeader) -> Journal: ...
        def pending(self, tenant: str, suite: str) -> tuple[Pending, ...]: ...

    class Journal(Protocol):
        key: str
        leg: int
        def append(self, progress: CaseProgress) -> None: ...
        def complete(self) -> None: ...   # the run is written; delete every leg

    @dataclass(frozen=True, slots=True)
    class Pending:
        key: str
        header: JournalHeader | None     # leg 1's: the birth certificate
        refusal: str                     # why it cannot be read, or empty
        legs: int
        done: Mapping[str, CaseResult]   # last record wins
        errored: frozenset[str]
        causes: Mapping[str, Cause]      # for the errored ones, the layer
        observed_target: SystemConfig
        observed_judge: SystemConfig
        finished: bool                   # the run file already exists

`refusal` rather than an exception, because `pending()` is a **survey**: a
journal this digline cannot read still has to be named — it holds paid work, so
it is never deleted on a guess — and naming it is what that field does.
`Listing` answers the same question the same way. The protocol carries one more
method, `drop_pending`, for §12's single case: a journal whose run already
exists.

**A separate protocol, asked for rather than required**, the way `Preflight` and
`HasArtifacts` are asked of a target. `ResultStore` is the persistence contract
for every backend, and the planned production store (Postgres, `src/digline/
production/`) has no business being obliged to implement an append-only JSONL
file in a repository. A store that cannot journal is used exactly as it is used
today, and the front end says so once rather than failing.

`open_journal` creates the leg file with `O_CREAT|O_EXCL`, which is the entire
concurrency story: a second process resuming the same run loses the race and is
refused by name. **No lock file** — a lock is the wrong instrument here, because
the process this ADR exists for is one that was *killed*, and a stale lock left
by a killed process would block the very resume it was meant to protect.

### 6. When a resume is refused, and why the list has that shape

A resume is refused unless every one of these matches the header of leg 1:

| field | what a mismatch means |
|---|---|
| `journal_version` | this digline does not know the format; it does not guess |
| `digline_version` | half the verdicts came from another engine, and the document names one |
| `tenant`, `environment`, `suite` | a different run in a different place |
| `config_hash` | the rules changed: thresholds, tolerances, `samples`, `min_agreement`, the aggregates |
| `cases_digest` | the questions changed — the half this ADR's opening sentence is about |
| `artifacts` (path → sha) | the prompt moved, and the prompt is the thing under test |
| `target_config` (declared) | a different model, temperature or endpoint answered the second half |
| `judge_config` (declared) | the scale moved, which is louder than the target moving (ADR 0005 §4) |
| `record_responses` | the document would record answers for half its cases |
| `git_commit` | the code around the suite is not the code that produced the first half |

The list is not a collection of good ideas. It is **exactly the set of facts the
run document asserts**, plus the two that make the journal readable. That is the
rule, and it is what makes §10 possible: a document that asserts nothing untrue
of either half needs no field saying it had two.

Two of the rows deserve their own sentence.

`cases_digest` is a new pure method on `Suite`, beside `config_hash()`, over the
declared cases. It is a **journal** field: it is never written to a run
document, never travels, and above all **never joins `config_hash`** — cases are
deliberately outside the hash (ADR 0014 §1), and a digest that crept into it
would unpromote every baseline the first time somebody fixed a typo in a case.

`git_commit` is the weakest row and says so. A dirty tree yields `<sha>-dirty`,
which is equal to itself however much the tree changed between legs — so for an
uncommitted working tree the real protection is `cases_digest` and the artifact
shas, and a custom assertion edited between legs is not covered by anything. A
run from a dirty tree already declares itself unreproducible; the resume checks
what it can and does not pretend to check more.

Every one of these is checked **before the first call of the new leg**, so a
refused resume costs nothing and the journal is left exactly where it was.

### 7. The observation survives the crash; the rule does not change

`ObservedIdentity` already refuses to average a system away. When a provider
answers as one model and then as another under the same alias, `see()` raises,
the driver errors that one case, and the run is still written — ADR 0005 §8
implemented as a sentence a reader can act on: *pin the model id instead of the
alias, or evaluate each one as its own run.*

Across a crash the rule does not change. What has to change is that the
observation is held by an object in a process, and the process is gone. So:

1. The journal records the observed configurations as they become known — the
   `observed` record of §3, written whenever the value differs from the last one
   written, which in an uninterrupted run means once.
2. On resume the host **seeds** the target and every judge from that record —
   `ObservedIdentity.resume(...)` — before the first call of the new leg.
3. An alias that rolled between the legs therefore raises on the first call of
   the second leg, exactly as it would have raised on the next call of the first,
   and the outcome is identical: that case errors, the run is written, the run
   exits 2 and cannot be promoted, and the reason names both model ids.

Flagged, not averaged — and flagged by the mechanism that already existed rather
than by a second one built beside it. Seeding reaches every plugin without a
plugin release, because `observed` is an attribute of `ProviderTarget` and
`JudgeBase` and the plugins subclass them (ADR 0004).

The limit, stated: a third-party target that observes an identity of its own
without using `ObservedIdentity` cannot be seeded, and a resumed run records what
its second leg saw. The way in is the protocol — a target that exposes
`observed` gets this for free — and a target that observes nothing (a plain
function, an `HttpTarget`, Bedrock Converse, whose reply carries no model id at
all) has nothing to average and loses nothing.

### 8. A resumed run carries the **original** `created_at`

The header's, always. The resumed leg's own start time is recorded in that leg's
header and dies with the journal.

A run measures a system **as of when it started**, and the journal header is the
birth certificate. Three things follow from taking the original, and all three
are why:

- The run lands at the key it would have had. `key_for` is
  `{slug(created_at)}-{config_hash}`, which is also the journal's name, so a
  resumed run writes the file the killed run was always going to write, and
  resuming twice cannot produce two runs of one measurement.
- Chronology stays honest. `list_runs` is key-ordered and therefore
  `created_at`-ordered; a run stamped at the hour of its rescue would sort after
  work that was done later than the thing it measured.
- `compare` against a baseline reads two runs as two points in time, and the
  point in time of this one is when the suite was launched.

The resume timestamp is the one fact this record gives up to leave the document
alone. It is written in the leg's header while the journal lives, printed on
stderr at the moment it exists, and gone when the run is written. §10 says what
it would take to keep it, and why that is the next bump's question and not this
release's.

### 9. `--resume` retries errored cases by default

A case whose journaled result holds an errored verdict is **called again**,
unless `--keep-errors` says otherwise.

The reason is not that an error is unimportant; it is that an error makes the
run unusable. An errored verdict exits 2 and `promote_baseline` refuses it, so a
resume that faithfully preserved the errors would spend its remaining calls
finishing a run that is dead on arrival — the completed form of the hole the
kill left. And the ordinary cause is the target's weather: a 529 that outlived
the SDK's retries is not a statement about the suite's meaning.

This is also the whole of what this record does about the second loss in
§Context. `_run_case` is **unchanged**: a target that raises still errors its
case, and a partly-sampled case is still not allowed to pass itself off as the
declared measurement. What changes is the remedy. An errored case used to mean
running the other 143 again; now it means `--resume`, which re-pays that case and
nothing else.

The deterministic failures — a mapper that raises, a custom assertion that
raises — will be retried too and will fail again, at the cost of one case. That
is why `cause` is in the journal: the announcement before the second leg names
what is being retried and why, so a user who sees *mapper raised* three resumes
running learns that this one is not the weather. Selecting automatically on
`cause` was considered and refused in §Alternatives: it would make digline decide
which of a user's failures are worth money, from a taxonomy of its own.

### 10. The document does not move, and neither does `SCHEMA_VERSION`

**A resumed run carries no marker, because there is nothing to mark.**

The test is the one ADR 0015 §6 passed and this fails, which is the useful way to
put it. A replay declares itself as `rejudged_from` because it is a **different
kind of measurement**: its answers were not taken from the target, so its
interval is the judge's wobble alone and promoting it would freeze a noise floor
measured without the noise. A resumed run is not a different kind of measurement.
Every call it reports was made against the target, at the declared sampling,
under the configuration named in the document — §6 is precisely the guarantee
that every fact the document asserts is true of both halves, and §7 is what
happens when one stops being true.

What actually differs from an uninterrupted run is the wall-clock spacing between
calls, and the document has never recorded that for any run. There is no per-case
timestamp and no duration; `created_at` is the launch, and §8 keeps it the
launch.

So: no field on `Run`, no key in `run_to_dict`, no migration step, no entry in
`_NON_ADDITIVE`, **`SCHEMA_VERSION` stays at 10**, no baseline is re-promoted,
and 0.11.0 is a minor release that adds a CLI verb and a store area rather than a
schema ritual (ADR 0014 §6). A resumed run is byte-for-byte the run that would
have been written had nothing killed it, which is the strongest form the promise
takes.

`Run.metadata` was the cheap alternative and is refused for the reason ADR 0014
§3 refuses it for `digline_version`: it is payload-governed, so the fact would
vanish at exactly the boundary where it might matter, and it would collide with a
key the user chose.

And the brief for the day somebody wants it anyway, written now so it is not
re-argued from memory: a `resumed_at: tuple[str, ...]` — one entry per leg — is a
**passenger for the next bump**, and it passes all three of ADR 0014 §1's
conditions. It leaves `config_hash` untouched (a fact about the process, not the
suite); it migrates to absent, which is *not recorded* and is honest; and it
travels in clear like `digline_version` and `promoted_at`, being a fact about the
software house's own instrument. It does not ride today because nothing forces
the schema to move today, and ADR 0014's closing rule is that waiting is the
intended behaviour.

### 11. One composition, two front ends; one new verb, on one of them

The four steps — open the journal, execute with `on_case`, write the run, delete
the journal — become **one function in `digline.host`**:

    prepare(suite, target, *, now, git_commit, artifacts,
            resume: Pending | None = None, retry_errors: bool = True) -> Prepared
    measure(suite, target, *, store, prepared, run_metadata=None,
            artifacts=None, mapper=default_mapper) -> Measured

Two calls and not one, because a front end has to be able to **refuse and
announce before the first call**: `prepare` decides what this launch is — which
`created_at` it carries, which cases it will not call, which errored ones it is
re-paying for — and raises `JournalRefusedError` if the resume would not be one,
at no cost. `measure` then opens the journal, executes, writes the run and
deletes the journal, and returns the stored `RunRef` beside the `Run` and the
`CallPlan`: the journal may only be deleted once the run file exists, so the
write is inside the composition rather than after it.

`cmd_run` and the MCP `run` tool each call `execute()` and `write_run()`
themselves today, which means journaling wired in two places would be journaling
that drifts in one of them. The host is the layer allowed to touch the world and
the layer both front ends already sit on (ADR 0011 §7), so the composition
belongs there and **the MCP tool gets the journal for free**: a killed
MCP-launched run leaves a journal the CLI can finish.

**The wiring ships in each front end's own release.** `digline.cli` moves onto
`measure()` with this one. `digline-mcp` is a workspace package with a floor —
`digline>=…` — and a floor cannot name a release that does not exist yet, so its
call site moves in the `digline-mcp` release that follows this one, with its
floor rising to the digline that carries `measure`. That is the shape ADR 0016
§8 used for `pytest-digline` and it is the same constraint. Until then a
killed MCP-launched run leaves no journal; a killed CLI one does.

The **verb** is CLI-only in this release. `digline run --resume [KEY]` — no key
means the most recent pending journal, and stderr names the others it passed
over, the way `Listing.note()` names what a scan left out. The MCP gains no
resume: its `run` tool is gated by an acknowledged call count (ADR 0011 §2), and
an agent resuming would have to acknowledge a number it cannot obtain without a
probe tool that section exists to refuse. That is a real design question and it
is not this record's.

Four behaviours of the command, each of which is a refusal to cost somebody money
by surprise:

- **`--resume` with no pending journal refuses.** It does not silently start a
  fresh run. Somebody who typed `--resume` believed there was something to
  finish, and starting 720 calls instead is a four-dollar misunderstanding.
- **Plain `run` with a pending journal still runs**, and says on stderr that a
  journal is pending and what would finish it. Silently abandoning paid calls is
  the same surprise pointed the other way.
- **The announcement subtracts what it will not call.** `planned_calls` gains a
  `done` argument and `CallPlan` a `reused` count, so the sentence reads *112 of
  144 cases × 5 samples = 560 calls to the target; 32 case(s) already judged, 3
  retried after an error*. ADR 0016 §2's rule stands: the announced bill has to
  match the invoice, and on a resumed run the old sentence would announce a bill
  that never arrives.
- **A resume with nothing left to call still writes the run.** A process killed
  between the last case and `write_run` is the cheapest possible resume, and it
  costs zero calls.

Refusals are `UsageError` and therefore exit **64**, which is the usage code and
not a verdict: a resume that could not proceed has said nothing about a suite,
and 1 and 2 are reserved for runs that did (ADR 0008 §2). `run --json` gains `resumed` and `reused` keys; `OUTPUT_VERSION` stays
at `1`, added keys being no change to what an existing consumer parses.

### 12. Compatibility, and the journal that outlives its run

Nothing about an ordinary run changes: same document, same key, same bytes, same
schema, same baselines, same plugin floors — `digline.targets` gains
`ObservedIdentity.resume(...)` and the plugins inherit it without a release.

The one case worth a rule is a journal whose run file **already exists** — the
process was killed after `write_run` and before the delete. It is not resumable
and not evidence of anything: the run it belongs to is on disk. `pending()`
reports it as finished, and `run` removes it with one line saying so. A journal
whose `journal_version` is unknown is left alone and named, never deleted: a file
this digline does not understand is not a file it may throw away.

## Consequences

**A long run stops being all-or-nothing.** The worst case goes from *everything
since the first call* to *the case that was in flight*, which at five samples is
four calls out of seven hundred.

**The remedy for an errored case stops being the whole suite.** That is the
second loss closed, and it is closed without touching the rule that produced it.

**There is a new file in the store, and users will find it.** `.pending/` sits
under the ignored `runs/`, so it cannot reach a commit, but a journal that is
never resumed is never deleted either. That is deliberate — it holds paid work —
and it is why `run` names pending journals every time it starts.

**A resumed run is indistinguishable from an uninterrupted one, on purpose.**
The fact that it was resumed lives in the terminal and in a file that is deleted
on success. Somebody will eventually want that fact in the document; §10 leaves
them a passenger and three conditions instead of an argument.

**Two more things now have to stay in step with the run file.** The journal's
case records share the run file's serializer, which is one of them; the header's
refusal list is the other, and it is a list that has to grow the day a field is
added to `Run`. §6's framing is what makes that maintainable — the question is
never *should this be checked* but *does the document assert it*.

**The store protocol grows a sibling.** `SupportsJournal` is optional, so no
future backend is forced to implement a file format, and a store that does not
journal degrades to exactly today's behaviour with one line of warning.

## Alternatives considered

**Write the run file incrementally instead of a journal.** Rejected. A run
document is validated as a whole and read as a whole, `write_run` is atomic
through `os.replace` precisely so that an interruption never leaves half a
document, and the aggregates do not exist until the last case has been judged. A
partially written run file would be a document that lies about being one.

**Journal per sample.** Rejected in §1: it would store the model's answers on
every run, including the runs whose whole configuration says not to.

**Rewrite the journal in place on a retry.** Rejected: append-only with
last-record-wins survives a kill at any instant, and a rewrite is a second window
in which a signal destroys work.

**A lock file for concurrency.** Rejected in §5. The process this feature exists
for is one that was killed, and a lock it could not release would block the
rescue.

**A new `created_at` for the resumed run.** Rejected in §8. It would produce a
second file for one measurement, sort the run after work done later than it, and
date the measurement at the hour of its rescue.

**Refuse to resume anything that errored, or retry it only on an explicit flag.**
Rejected in §9: the default would then be a resume that carefully finishes a run
nobody can promote and that exits 2 regardless.

**Choose what to retry from `cause`.** Rejected in §9. It reads well until
digline is the thing deciding which of a user's failures are worth money, from a
taxonomy of its own making. The cause is reported so the user decides; the
default is the one that makes the run usable.

**Compare the observed `resolved_model` at the end of the resumed leg and refuse
to write the run.** Rejected in §7. It strands both legs' paid calls in a journal
that can never become a run — pinning the model to fix it would then fail the
`target_config` check. Seeding the identity reproduces the in-process rule
exactly: one case errors, everything else is preserved and readable.

**Put the resumed marker in `Run.metadata`.** Rejected in §10, for ADR 0014 §3's
reason: payload-governed, absent at the boundary that matters, and colliding with
the user's own keys.

**Bump the schema and record the resumption properly.** Rejected for this
release, and the refusal is the point of §10 rather than an economy. A bump is a
ritual with a release in the middle of it (ADR 0014 §6) — the nine committed
baselines, the caps, the migration, the regenerated reports — and this feature
needs none of it. Paying that price to record a fact that changes nothing about
how a run is read would be the accretion ADR 0014 was written to prevent.

**`--resume` as a separate command (`digline resume`).** Rejected: it would need
every one of `run`'s arguments — the suite, the target, the root, the tenant, the
metadata — and would be `run` under another name, with two places for the
composition to drift.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**A killed run loses one case.** A driver test with a target that raises
`SystemExit` at case 40 of 100 asserts the journal holds 39 cases, the header,
and one observation record; and that resuming calls exactly 61 cases.

**The resumed run is byte-identical.** The same suite against a deterministic
target, run once uninterrupted and once in three legs, produces documents equal
in every byte but the key — which is asserted **equal too**, because §8 says the
key is the original's. This is the test that makes §10 true rather than intended.

**Order comes from the suite.** A resume whose journal holds the cases in a
different order from the suite produces `results` in the suite's order.

**Every row of §6 refuses, one test each**, each asserting that the message names
the field and that **no call was made** — a refused resume that had already paid
for something would be the failure this feature exists to prevent.

**The roll at the seam.** A target whose observed `resolved_model` changes
between legs produces an errored case on the first call of the second leg, a run
that is still written, `exit_code() == 2`, and a `promote_baseline` that refuses.
The message names both ids. The same test for a judge.

**Errors are retried, and `--keep-errors` keeps them.** Both directions, with
the call count asserted in both, and with `cause` asserted for a target failure,
a mapper failure and an assertion failure.

**The torn line.** A journal whose last line is truncated mid-object resumes
with every earlier case; a journal with a corrupt line in the middle is refused
by name. A journal at an unknown `journal_version` is refused and **still on
disk** afterwards.

**The race.** Two `open_journal` calls for the same run: the second is refused,
and the first leg file is untouched.

**Nothing else sees it.** `scan_runs`, `list_runs`, `run_paths` and
`digline migrate` over a suite directory holding a `.pending/` with two legs
report and touch nothing; `git check-ignore` confirms the path is ignored by the
generated rule.

**The announcement matches the invoice.** A resumed plan's `target_calls` equals
the number of calls the target actually receives, asserted by counting them.

**The completed journal.** A journal whose run file exists is reported as
finished and removed, with the line asserted.

**The schema did not move.** `SCHEMA_VERSION == 10` and `run_to_dict` over a
resumed run has exactly the keys it has today — asserted as a set, so a field
added by accident fails here rather than in somebody's baseline.

## Not decided here

**Retrying a failed sample inside a case.** The honest fix for `_run_case`'s
`k - 1` lost samples is a retry policy — backoff, a ceiling, a rate-limit key,
and one layer owning it — which is the same ADR `execute()`'s docstring already
defers concurrency to. This record bounds that loss and leaves it.

**Concurrency.** Untouched, and the journal does not prejudge it: `on_case` is
called once per finished case, which stays true whatever order the cases are
finished in. What a concurrent driver would need in addition is a rule for a leg
that finished cases out of order, which is a paragraph in that ADR and not a
constraint on this one.

**Resume over MCP**, §11: it collides with the acknowledged call count rather
than merely extending it.

**A `digline pending` command.** `run` names what is pending on every launch,
which is where a user is when it matters. A command for it is a convenience, and
it waits for somebody to ask.

**A journal for the online driver.** `src/digline/online/` consumes a stream of
production responses, where "resume" means an offset into somebody else's queue
and not a set of cases left to call. Fixed decision 7 is not disturbed: nothing
here reaches the core, and a single response still runs through the same
assertions with no journal in sight.
