# ADR 0020 — The reading across runs

- Status: proposed — the text first, checkpointed before any code, the way
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) and
  [ADR 0019](0019-the-reasoning-operator.md) were
- Date: 2026-09-15
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states);
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the payload
  stays where it is born, the verdict travels);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2 (a
  perimeter field is withheld, a measurement travels), §8 (one run measures one
  system), §9 (what the provider *said* answered);
  [ADR 0008](0008-the-two-run-report.md) §2 (the exit code is the contract);
  [ADR 0010](0010-per-group-aggregates.md) §3 (an aggregate's name is a public
  string);
  [ADR 0011](0011-the-mcp-server.md) §1 (absence by construction), §4 (added
  keys are no bump), §7 (two front ends over one host);
  [ADR 0012](0012-the-reading.md) §3 (the fact list is the surface), §4 (the
  boundary is a type), §5 (no advice, and the multi-run vocabulary is out of
  explain's reach);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §6 (a
  replay declares itself);
  [ADR 0016](0016-the-canary-case.md) §5 (the behavioural half of identity);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §7 (a roll inside a run
  errors a case), §8 (a resumed run carries the original `created_at`);
  [ADR 0019](0019-the-reasoning-operator.md) §12 (the two core gaps)
- Amends: [ADR 0011](0011-the-mcp-server.md) §1 and §13 — six tools become
  **eight**, once, for `explain` and `log` together (§9);
  [ADR 0012](0012-the-reading.md) §8 and
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §8 — their
  "no seventh tool" sentences are superseded here and stay true of the releases
  they describe
- Turns into surface: `digline log`; the MCP tools `explain` and `log`;
  `docs/mcp.md` ("The six tools"); `examples/operator/README.md` (the
  interactive path); `ROADMAP.md`; the `operating-digline` skill wherever it
  names the surface
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 1 is upheld — the
  fold is pure and lives in `digline.report` beside `history.py`; decision 2 —
  it reads the store and writes nothing; decision 8 — one tenant, one suite,
  and `environment` reported without constraining; decision 9 — `redacted()` is
  applied **inside** the function that builds the reading (§6)
- Requires: no `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no migration, no baseline
  re-promoted. `digline-mcp` releases with its floor raised to the digline that
  carries `log` (§9)
- Number: 0020. 0021 is claimed by the register on the same branch, and cites
  §6 of this record

## Context

**The product's best-known roll left nothing a ledger could read.**

0.8.0 taught every run to record what the provider said answered, and its
release notes measured it: on Anthropic, `claude-haiku-4-5` answered as
`claude-haiku-4-5-20251001`. That sentence is the whole of the evidence. The
runs that measured it were run artifacts, and run artifacts are ignored by
design (fixed decision 2), so they are gone. No stored document on the machine
this record was written from, in any example or in the dogfood, carries a
`resolved_model` that differs from its alias.

The dogfood's own store is the material this record was checked against, and
it says the same thing more quietly. Sixteen runs over seven days. Twelve were
written by a digline that did not name itself and record no answering model at
all. Four record one, and in all four the provider named the alias back:
`claude-sonnet-5` answered as `claude-sonnet-5`. One of the sixteen is a replay,
which asked the target nothing. The alias story that store can tell is a flat
line with a long absence in front of it — true, and worth being able to say.

So the thesis of this release — *digline learns to remember* — begins with a
reading rather than a file. Every fact it needs is already in the documents:
`target_config` and `judge_config` with their `withheld` sets and `identities`,
`digline_version`, `rejudged_from`, `created_at`. What is missing is the fold
that reads them **down** the runs instead of across a pair, and a surface where
the reasoning operator can ask *which alias rolled in this window* without
opening sixteen documents.

Two more gaps were named by ADR 0019 §12 and are verified against today's
`main`, because the same reader hits them:

1. **`wire.runs_json` carries no aggregates**, while `digline view`'s run list
   is a grid with one column per aggregate. It has exactly one caller — the MCP
   `list_runs` tool. `digline list` has no `--json` at all, so this is a gap on
   the machine surface an agent reads and nowhere else.
2. **`explain` is absent from the MCP.** The scheduled loop reads the fact list
   through the CLI; the interactive operator, with the same rules and the same
   absent `promote`, cannot reach it.

**The hazard, stated before the design.** The tempting version of this feature
infers a roll from movement: the scores changed on a Tuesday, the prompt did
not, so the model must have. That is a deduction, and the product already has
the one deduction it permits — the canary, which says *likely* and says it in
`compare` (ADR 0016 §7). Identity is **declared by the record**. A reading that
put a score beside an identity would invite every consumer to do the arithmetic
this record refuses to do.

## Decision

### 1. A roll, and only that

> **A roll is two sightings of the same sent model, on the same side and the
> same provider, whose recorded answering models differ.**

Everything else is something else, and it is named as what it is:

- a change in the **sent** `model` is a **suite edit**. Somebody wrote a
  different name in the suite; ADR 0005 already reports it as a configuration
  delta, and the history of the suite is git's;
- a sighting beside an **absence** (§3) is neither a roll nor evidence against
  one. `A`, then three runs that recorded nothing, then `B` is a roll whose
  moment is **not known** — it happened after the last run that recorded `A`
  and no later than the first that recorded `B`, and it is reported as that
  window with the count of silent runs inside it, never pinned to a date;
- a change in behaviour is not an identity at all (§4).

**One run is at most one sighting per side**, and that is guaranteed rather
than assumed. `ObservedIdentity` errors the case in which an alias answers as a
second model mid-run (ADR 0005 §8), and a resumed run seeds the identity from
its journal so a roll at the seam errors the same way (ADR 0017 §7). A run
document therefore never holds two answering models on one side, and a
resumed run is one sighting, dated at its original `created_at` (ADR 0017 §8).

### 2. A replay is never a sighting of the target

A run with `rejudged_from` asked the target nothing. Its `target_config` is the
source run's, copied (`digline/run/replay.py`), so counting it would stretch the
source's *last seen* on the strength of a copy — in the dogfood's store, by
three days.

The target side of a replay is **not a sighting**, and the reading says so in
its own line: the replay is named, with the run it re-judged. The **judge**
side of a replay *is* a sighting — the judge was asked, and that is the whole
point of a re-judge (ADR 0015 §6). One document, two sides, two answers, and
the rule is written per side so that neither is lost.

### 3. The absences, and there are six

A reading of identity over real history is mostly absence, and each absence is
a different fact. They are checked in the order below; the first that applies
names the run.

| # | What the document shows | The sentence | Dated |
|---|---|---|---|
| 1 | a skipped or unreadable file (`Listing.skipped`, `unreadable`) | **not read** — *N runs at schema K were not read* | no |
| 2 | the side recorded no configuration (`SystemConfig.recorded` is false) | **declared nothing** | yes |
| 3 | several instruments on the judge side (`identities` holds two or more, so `values` is empty by rule) | **several judges; no single answering model** | yes |
| 4 | `resolved_model` in `withheld` | **withheld** at a named endpoint | yes |
| 5 | a configuration, a writer that names itself, no `resolved_model` | **no answering model was reported** | yes |
| 6 | a configuration, no `resolved_model`, and no `digline_version` | **not recorded** — *this document does not name its writer* | yes, by `created_at` |

A document with a `resolved_model` is a sighting whatever else it lacks: a file
written by 0.8 or 0.9 carries the model and not the writer, and the record
declares the identity, which is all a sighting needs.

Three of the rows deserve their own sentence.

**Row 5 cannot say who was silent.** The provider may return no model id
(Bedrock does not, by its own service model), or a plugin may not pass one on.
The document does not distinguish them, so the sentence does not either.

**Row 6 is undated by principle.** The repository's dependency pin at
`git_commit` would put a release on most of those runs — and it is a derivation
from a second record, taken on trees that in the dogfood are `-dirty` in every
case, so the pin at the commit is not a statement about what ran. The document
is the authority. *Not recorded* is the honest sentence, and the row stays
exactly as undated as the document left it.

**Row 3 is the one the reconnaissance did not expect.** It went looking for
five absences and the code has six: `SystemConfig` refuses a single set-up
beside two identities, because a merged one would describe a judge nobody
built. So where a suite holds two judges, the reading can say *which two* and
cannot say either one's answering model. That is the cost of a rule this record
does not reopen.

Absence is **never collapsed into its neighbours**. A span of silent runs is its
own row, between the sightings on either side of it, so that a reader cannot
mistake *nothing was recorded for four days* for *the same model answered for
four days*.

### 4. The row has no score, by type

The reading is two value types, both frozen, both in `digline.report` beside
`history.CaseHistory`, and neither has a field a score could occupy:

    IdentitySpan:
        side:          "target" | "judge"
        provider:      str
        sent:          str | tuple[str, ...]     # a model, or the judges' identities
        answered:      str | None                # None exactly when `absence` is set
        absence:       AbsenceKind | None        # §3's rows 2–6
        first_seen:    str                       # created_at of the first run in the span
        last_seen:     str
        runs:          int
        environments:  tuple[str, ...]           # reported, never a partition

    Roll:
        side, provider, sent
        before:        str
        after:         str
        last_before:   str                       # the last run that recorded `before`
        first_after:   str                       # the first run that recorded `after`
        silent_between: int                      # runs in between that recorded nothing

No `score`, no `status`, no `outcome`, no canary flag, no aggregate. This is
ADR 0012 §4's move applied to a different hazard: there the type could not hold
a reason, so it could not leak one; here it cannot hold a measurement, so no
consumer is handed the two columns whose juxtaposition is the deduction. A
reader who wants to know what the scores did beside a roll has `compare` and
`explain`, one command away, and the canary, which is the product's one
licensed inference about behaviour.

`environments` is reported and never splits a span: decision 8 keeps the
environment inside the perimeter and out of any constraint, and an alias that
answered the same in staging and production is one fact rather than two.

### 5. Where it lives: `digline log`

    digline log --suite suite.py [--since ISO] [--until ISO] [--json] [--locale en]

**Not `explain`.** ADR 0012 §5 puts the whole multi-run vocabulary out of
explain's reach — *again*, *recurs*, *since* — because a single run has no
second run to speak about. A timeline is nothing but that vocabulary. Adding it
to explain would either break §5 or produce a timeline unable to say *first
seen*.

**Not `view`.** A column there is a convenience for a person and may come
later; the consumer this is for has no browser (ADR 0011 §1).

**Not a gate.** `log` exits 0 when it read the store, whatever it found, and
64 when it could not be asked. A roll is a fact about the system and not a
verdict about a suite: the verdict belongs to `compare`, where a changed
`resolved_model` is already a named delta and a moved canary already exits 1
(ADR 0008 §2, ADR 0016 §5). Two commands gating on one fact is how a pipeline
learns to ignore one of them.

**The window is over `created_at`**, the recorded fact, inclusive at both ends,
and the words are scoped to it. *First seen* means **first seen in this store,
in this window** — runs are ignored by fixed decision 2, so a hosted runner has
no history and a fresh clone has none either. The reading says *0 runs in this
store* there, and never *no roll*.

**The reference is named once**, at the end: the baseline's key, `promoted_at`
where it was recorded, and its sighting. It is the one sighting that is
committed, and the one that travels between machines with the repository.

**The terminal output** follows `compare`'s rule for a terminal: `--locale`
defaults to `en`. Its strings live under `log.*` in `digline/report/text.py`,
in both locales, and they sit under ADR 0012 §5's no-advice gate with one
change of list: the multi-run tokens are *permitted* here, which is the point
of the command, and **`likely` is forbidden**, because that word belongs to the
canary and a reading of the record never speculates.

### 6. The boundary: `redacted()` inside, and what it costs

`log_json` builds every span from `SystemConfig.redacted()` of each run, inside
the function, so the CLI's `--json`, the MCP tool and the terminal all read the
same reduced configuration. It is the placement 0.12.1 used to close the door
in `config_deltas`: one function, and the door closes once rather than once per
front end.

What travels: the provider, the sent model (written in the suite and reviewed
with it, ADR 0005 §9 amended), the answering model where the endpoint is not a
named one, keys, `created_at`, `digline_version`, `environment`,
`rejudged_from`, counts. What does not: anything topology-shaped, and **no case
id anywhere** — the reading is about the system, and it has no reason to name a
case at all.

**The cost, stated rather than discovered.** At a named endpoint,
`resolved_model` is withheld in every rendering, including a developer's own
terminal. So the reading **cannot declare a roll there**: consecutive withheld
sightings are one *withheld* span, whatever answered. The alternative — a
`changed: true` bit computed over the withheld values — is refused: equality
over a guessable space is a verifier, and ADR 0003 §4 already refused a digest
beside a withheld prompt for exactly that reason. A roll behind a customer's
gateway is visible in the run file and in a non-redacted report, where it
always was, and behaviourally through the canary, which is the half of ADR 0016
written for providers that say nothing.

### 7. The first gap: aggregates in `runs_json`

Each row of `runs_json` gains the run's aggregate verdicts, each carrying
exactly the fields fixed decision 9 lets cross: `assertion`, `assertion_id`,
`status`, `score`, `threshold`, `tolerance`.

**No metadata**, so no `Disclosure` parameter joins the function's signature:
the confusion counts are measured metadata and would cross, but they are one
`get_run` away and the list is what a caller scans to *choose* a run, which is
the same reason `view`'s grid shows scores and not matrices. **No reason**,
because none crosses. The name is ADR 0010 §3's public string.

The only caller already loads every run document to build its rows, so this
adds no reading. `OUTPUT_VERSION` stays 1 by ADR 0011 §4's rule, and no
document moves.

### 8. The second gap: `explain` on the MCP

    explain(suite, run="latest")  ->  explain_json(...) + {"key": ...}

The tool is `cmd_explain` without the terminal: the scope follows the store
(ADR 0012 §1), the exit code rides in the payload as it does on `compare`
(ADR 0011 §4), and the response is `explain_json` verbatim with the resolved
key beside it.

**No locale argument.** `compare` over MCP hardcodes `en` because it ships a
sentence; the fact list ships none (ADR 0012 §3), and the only locale-sensitive
call on the path computes a headline whose *number* does not depend on it.
There is nothing to localise, so there is nothing to choose.

**The boundary is already a type** (ADR 0012 §4), and `tests/test_wire_boundary.py`
already drives `explain_json`. What is added is the lesson 0.12.1 paid for: the
marker suite is driven **through the server's tool**, not only through the
wire function, because the door that leaked there was a composition the wire
tests never reached.

### 9. Eight tools, amended once

| tool | arguments | kind |
|---|---|---|
| `list_runs` | `suite` | read |
| `get_run` | `suite`, `run` | read |
| `get_baseline` | `suite` | read |
| `log` | `suite`, `since`, `until` | read |
| `compare` | `suite`, `run` | measurement |
| `diff` | `suite`, `run1`, `run2` | measurement |
| `explain` | `suite`, `run` | measurement |
| `run` | `suite`, `acknowledge_calls` | measurement |

`explain` is a measurement for the reason `compare` is: with a baseline it holds
a run against the approved reference and carries the exit code that gates.
`log` is a read.

**The two arrive together so the count moves once.** ADR 0011 §1 was written as
a table chosen a row at a time, and §13's first test asserts the set: a
seventh name fails until somebody edits that test, which is the point. That test
is edited once, to eight names asserted as a set, and the registration comment
in `server.py` — *"six entries, and the sixth is not `promote`"* — becomes
*eight entries, and none of them writes*. The absent list does not shrink:
`promote`, `migrate`, `view`, `report`, and after ADR 0021 the register's
writer.

ADR 0012 §8 said *no seventh MCP tool in 0.7.0*, and ADR 0015 §8 said *no
seventh MCP tool* for its own release. Both were true of what they described
and are superseded here rather than edited: a tool is added when something
needs it, and ADR 0019 §12 is the something. ADR 0011 §2's *"there is no
seventh tool"* is about a call-plan tool and stays true — neither of these is
one.

**The front end ships in its own release**, the shape ADR 0017 §11 used: `log`
imports a name that exists only from the digline that carries it, so
`digline-mcp`'s floor rises to that release, and the plugin-floor gate — which
is name-based — is what enforces it.

### 10. What it says about the material it was checked against

Rendered in the terminal over the dogfood's store, in the shape §4 types:

    scout-judge · 16 runs in this store, 2026-09-08 → 2026-09-14

    target anthropic
      sent               answered as        first seen            last seen             runs
      claude-haiku-4-5   not recorded       2026-09-08T16:12:27Z  2026-09-09T06:51:45Z     8
      claude-sonnet-5    not recorded       2026-09-09T08:08:18Z  2026-09-10T11:58:06Z     4
      claude-sonnet-5    claude-sonnet-5    2026-09-11T14:51:30Z  2026-09-14T15:03:21Z     3

      No roll recorded.
      12 runs do not name their writer, and record no answering model.
      1 replay re-judged 2026-09-11T15:09:23Z and asked the target nothing.

    judge  declared nothing, in every run

    reference  2026-09-14T15:03:21Z · approved 2026-09-14T15:53:17Z
               claude-sonnet-5 answered as claude-sonnet-5

`claude-haiku-4-5` to `claude-sonnet-5` is not in the roll line, because it is
not a roll: somebody changed the suite, on a date the suite's history records.
And *no roll recorded* is scoped by the rows above it — three sightings, twelve
silences — rather than read as a property of the provider.

This is the whole of the positive evidence, and it is stated as such: **the
roll this feature exists to show does not appear in any history available to
test it against.** The roll cases of the test plan are synthetic, and the
dogfood is the acceptance case for the sentence that matters most when nothing
happened.

### 11. Compatibility

Nothing enters the run document. `SCHEMA_VERSION` stays 11, nothing migrates,
no baseline is re-promoted, `OUTPUT_VERSION` stays 1. `runs_json` gains a key;
the MCP server gains two tools; the CLI gains one verb.

**`log` needs no exception to "the wire never learns its name".** That sentence
(ADR 0017 §2, ADR 0019 §8) is about work files and the decision journal. `log`
reads **documents**, which the wire has always known. The narrow exception is
the register's, and ADR 0021 §8 writes it.

## Consequences

**"Which alias rolled" becomes a question with a typed answer**, and on the
material available today the answer is mostly absence. That is the feature
working: a reading that could only report rolls would report nothing, and a
reader could not tell that from a store that recorded nothing.

**A roll behind a named endpoint stays invisible to the reading.** §6 pays for
the boundary with the one case a software house maintaining a customer's
gateway would most want to see. The canary is the answer there, and it was
already the answer.

**The history is the machine's.** A laptop that has run the suite for a month
can tell the story; the runner that runs it on a schedule cannot. The operator
that most wants this reading is the one least likely to have the runs — which is
an argument about where the operator runs, not about what the reading may
infer.

**The MCP surface grows for the first time since it was chosen.** Eight entries
is still a list a person reads in one breath, and none of the two writes.

## Alternatives considered

**A section of `explain`.** Rejected in §5: ADR 0012 §5 forbids the vocabulary
a timeline is made of.

**Dating an undated run from the dependency pin at `git_commit`.** Rejected in
§3: a derivation from a second record, on dirty trees, presented as a fact of
the first.

**Inferring a roll from score movement, or printing scores beside identities.**
Rejected in §4, by type. The canary is the licensed inference and it lives in
`compare`.

**Counting a replay as a sighting.** Rejected in §2: its target configuration is
a copy.

**A `changed` bit over withheld values.** Rejected in §6: an equality oracle
over a guessable space is the verifier ADR 0003 §4 refuses.

**Making `log` a gate.** Rejected in §5: `compare` already gates on the same
fact, and two gates on one fact teach a pipeline to mute one.

**A stored timeline file**, updated as runs are written. Rejected: it would be a
second record of facts the documents already hold, which is how two records
start to disagree. The fold is cheap; the documents are the authority.

**Adding `explain` now and `log` later.** Rejected in §9: the count would move
twice, and §13's test would be edited twice for one decision.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**A roll is only a roll.** Two sightings, same sent model, different answering
model: one `Roll`. Different sent models: no roll, and the spans say so. The
same answering model with collapsing scores in a fixture: no roll. A changed
answering model with identical scores: a roll. Both directions of the last pair,
because only the pair proves the reading ignores the scores.

**The roll across a silence.** `A`, three runs that recorded nothing, `B`: one
`Roll` with `silent_between == 3`, `last_before` and `first_after` the two
sightings, and no date in between asserted anywhere in the output.

**A replay is not a target sighting and is a judge sighting**, asserted on a
fixture where the replay is the newest run: the target's `last_seen` is the
source's, the judge's is the replay's.

**Every row of §3**, one fixture each, asserting the sentence in both locales
and the precedence order where two rows could apply. Row 6's fixture carries a
`git_commit` and a dirty marker, and the output is asserted to contain no
release number.

**The type has no score.** `IdentitySpan` and `Roll` are asserted by field set,
so a field added by accident fails here.

**The boundary.** A run at a named endpoint with a marker in `resolved_model`
and `base_url`, driven through the CLI's `--json`, the terminal output and the
MCP tool: the marker appears in none. Two such runs whose withheld values differ
produce one withheld span and no roll. The same marker suite drives the MCP
`explain` tool, not only `explain_json`.

**The aggregates in `runs_json`** carry exactly the six fields, asserted as a
set, and no `reason` and no `metadata` key.

**Eight tools**, asserted as a set; `promote`, `migrate`, `view` and `report`
asserted absent by name.

**No advice, and no `likely`**, over the `log.*` strings in both locales.

**The dogfood's shape**, reproduced as a fixture of sixteen synthetic documents
with the same identities and absences as §10 — no case content — rendered and
asserted line by line.

## Not decided here

**A column in `view`.** A convenience for a person, and it waits for one to ask.

**One answering model per judge where there are several.** It would need a
`resolved_model` per identity in `judge_config`, which is a document change and
a passenger question for the next bump under ADR 0014 §1, not a reading.

**The committed history of the reference** — `git log` over `baselines/`, which
holds promotions and migrations in one list. Reading git from a reading is the
host's business and a second record; ADR 0021 is where the reference's history
is decided, and it is decided as a register rather than as a git parser.

**A store-wide or cross-suite timeline.** One alias may serve several suites.
The unit here is the suite, because that is what the store is keyed by; a
tenant-wide view is a convenience over the same fold.
