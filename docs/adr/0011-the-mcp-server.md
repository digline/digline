# ADR 0011 — The MCP server (`digline-mcp`)

- Status: accepted 2026-09-08 — the text first, the implementation written
  against it on `digline-mcp`, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0007](0007-the-declarative-suite-format.md) and
  [ADR 0008](0008-the-two-run-report.md) were. The three calls this record left
  open were settled the same day and are written in below: §2's acknowledged
  count is `target_calls`, §4's `exit_code` lands on both surfaces through the
  one function, and §7's host extraction goes ahead as drafted
- Date: 2026-09-08
- Amended: 2026-09-09 — **§8 gains the check that makes it true.** A security
  review found that `suite` was unconstrained: the section's "the perimeter is
  the repository" was a description of intent, not of behaviour, and every
  tool — the read-only ones included — would execute a `.py` from any path on
  the machine. The decision is unchanged and now enforced. Ships in
  digline-mcp 0.1.1
- Amended: 2026-09-08 — §5's projection gains three things, each of them the
  section's own sentence deciding its own list. **The intervals**
  (`samples`, `sample_min`, `sample_max`, as recorded): they are readings of the
  instrument, and `AGENTS.md` §3 — tell a wobble from a drift — is unexecutable
  without them, since a score of `0.667` alone cannot say whether it was
  measured once or five times. **`target_config` and `judge_config`**: ADR 0005
  already ruled a model id and a temperature measurements of the system, so a
  document that named neither could not say which model produced the run it
  described; 0005's own withholding applies unchanged, through
  `SystemConfig.redacted()`, so `base_url` leaves as a withheld *name* and never
  as a value. **The artifact digest is withheld with the text**, correcting
  `{ sha }` in the list below: ADR 0003 §4 — an assumption this record
  declares — holds that a digest is a *verifier*, prompts live in a small
  guessable space, and a digest that travelled would defeat the withholding it
  travelled beside
- Amended: 2026-09-19 — **§5's projection gains the instrument's own flags**,
  which it had never followed: `rejudged_from`, `canary`, `calibration`,
  `judged`, `Run.judge_samples` and — the one the brief for this amendment did
  not list, because only the code says it — `Score.sample_means`. None was ever
  withheld data; all six were simply absent, and the sixth's absence makes a
  reader misread a number rather than miss one. Registered in three places as a
  gap to be closed "by a decision about the wire, not noticed by accident"
  (ADR 0024, *Not decided here*), and this is that decision. `OUTPUT_VERSION`
  does **not** move: added keys, which that contract has admitted nine times
- Amended: 2026-09-09 — shipped with 0.6.0 rather than after it: the release
  was widened by decision. The reasoning above stands unchanged, including
  §12's rejected alternative and the paragraph in §7 that weighed it; only the
  tag the work rode is different. `Requires: digline 0.6.0` still holds — the
  dependency is on what 0.6.0 contains, and it now contains it on the same day
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  tenant is the perimeter), §8 (a baseline is an approved reference) and the
  payload/verdict boundary that fixed decision 9 states;
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4–5
  (withheld rather than absent);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2 (a withheld
  config field carries no value to print in the first place);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §8 (the planned call
  count, announced before the first call);
  [ADR 0008](0008-the-two-run-report.md) §1 (a diff carries no `worse`, and the
  absence is the point)
- Turns into surface: [`AGENTS.md`](../../AGENTS.md), all eight rules. That file
  is the reason this one exists, and §1 of it is the reason the surface has the
  shape it has
- Requires: digline **0.6.0**. This package ships after that release, never with
  it — it depends on `diff()`, on per-group aggregates, and on the machine
  surface §6 promotes, none of which exist below 0.6.0
- Touches: `CLAUDE.md`'s **Structure** section. The `cli/` line and the
  allowed-dependency chain are amended in §6 and §7. Nothing in the *fixed*
  section is amended: decisions 2, 5, 6, 8 and 9 are reaffirmed, and §5 tightens
  decision 9 rather than loosening it
- Number: 0009 is reserved on `docs-boundaries` and 0010 is
  `per-group-aggregates`, both unmerged at the time of writing. The gap at 0009
  on this branch is expected and is not a missing record

## Context

**The agent is already here.** `AGENTS.md` exists because coding agents run
digline today: they shell out to the CLI, read the text a human was meant to
read, and act on it. That is a surface nobody designed. `--help` is a contract
with a person; a table with a `KEY` column and an asterisk marking the baseline
is a document for eyes. A program reading it is a program guessing.

Two things are true at once, and the CLI cannot hold both.

**An agent reading digline is a good outcome.** Assembling the evidence — what
moved, by how much, whether it exceeded the measured interval, what the prompt
was doing on either side — is real work, it is tedious, and it is exactly the
work `AGENTS.md` asks an agent to do before recommending anything. A machine
surface makes that work correct instead of approximate.

**An agent promoting a baseline is the thing `AGENTS.md` §1 forbids**, and the
CLI cannot forbid it. `digline promote` exists; an agent with a shell has
`digline promote`. §1 is a sentence in a file the agent may not have read,
asking it to decline something it is fully able to do. Every layer of that is
hope: hope the file was loaded, hope the sentence was weighted, hope the model
was not mid-way through a plan that reads "make the tests pass".

The reason that matters more than it looks: `promote` writes into
`.digline/<tenant>/baselines/`, which is **committed**. An agent that promotes
does not just get a comparison wrong — it puts a decision nobody made into
somebody's pull request, wearing the word *baseline*, which ADR 0002 §8 defines
as *approved*. The approval is the whole of the meaning, and an unattended
process cannot supply it.

A tool surface can settle this by construction rather than by instruction. That
is this record's thesis, and §1 states it in one line: **the tool that is
missing is the thesis.**

---

## §1 — Eight tools, and the ones that are absent

*Amended 2026-09-15 by [ADR 0020](0020-the-reading-across-runs.md) §9: the six
tools chosen here became eight, once, for `explain` and `log` together. Neither
writes, and the absent list below did not shrink.*

The server exposes exactly these tools, and no others:

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

Reads and measurement executions. Nothing else, and in particular nothing that
writes into the repository.

**`promote` does not exist on this surface.** Not disabled, not permission-
gated, not refused with a message: **absent by construction.** There is no
function, no name in the tool list, nothing for a model to attempt and be told
no about. A refusal is a conversation — it can be argued with, retried,
worked around by a model that has decided the refusal is a bug. An absence is
not a conversation. `AGENTS.md` §1 stops being a rule the agent is asked to
follow and becomes a fact about what the agent can reach.

This is the one place where the *shape of the API is the argument*, and it is
worth saying plainly why the alternative was not taken. A `promote` tool that
raised "not permitted for agents" would be a better error message and a worse
design: it teaches that promotion is something this surface does, subject to a
policy, and a policy is exactly the kind of thing a future release relaxes
"just for CI". There is no policy here. There is no promote.

Three more commands are absent, on their own reasoning:

- **`migrate`** — upgrade maintenance. It rewrites every stored document of a
  suite, which is a maintenance operation performed by whoever performed the
  upgrade, at a moment they chose. `AGENTS.md` §8 tells an agent to *say* that
  a migration is needed, and §4 of this record makes sure it can: the skipped
  count reaches the agent as a field, so it can name the problem and the
  command. Naming it is the agent's job; running it is not.
- **`view`** — a human-facing document, and a long-lived HTTP server besides. An
  agent has no browser and no use for a bound port.
- **`report`** — the same, in one file. `render_html` produces the document for
  world 3 (ADR 0002), with a mandatory locale because it has a recipient who did
  not choose English. An agent is not that recipient. An agent that wanted the
  facts behind the document reads `compare`, which carries them.

The pattern across all four: **the surface offers what an agent can be right
about, and withholds what needs a person to have decided something.**

## §2 — `run`, and the count it has to say out loud

`run` is a measurement execution and it spends money. `AGENTS.md` §7 is written
about precisely this, and it is written as an obligation to *speak*: say what a
hunt will cost before starting it.

The CLI discharges that obligation by printing to stderr and trusting the reader
(ADR 0006 §8). Over MCP there is no stderr that reaches the agent, and no
reader — so the obligation is discharged by making the number **an argument the
caller must supply**:

```
run(suite: str, acknowledge_calls: int)
```

`acknowledge_calls` is **mandatory** and must equal `planned_calls(suite).target_calls`.
A mismatch is refused; the run does not happen.

**`acknowledge_calls` is `target_calls` — calls to the target — and nothing
else.** `CallPlan` deliberately does not fold judge repeats into one multiplier,
because nothing in the core claims to know which assertions call a model
(ADR 0006 §8), and a number that silently guessed would be worse than a number
with a stated scope. So the tool's description says exactly what the integer
counts, in those words, and the response carries `CallPlan.sentence()` — which
*does* name each `Repeated` and its factor — so the agent that has to report the
cost has the whole sentence and not just the part it acknowledged.

**The first call is the probe, and no tool returns the plan.** A `run` called
without a correct `acknowledge_calls` is refused **with the plan in the
refusal**: the count, the sentence, and the instruction to call again with the
number. So the sequence is

1. `run(suite="…")` → refused, and the refusal says `100` and
   `20 cases × 5 samples = 100 calls to the target; each answer is judged 3 times by rubric`.
2. `run(suite="…", acknowledge_calls=100)` → executes.

A separate `get_plan` tool was considered and rejected: it would be a tool an
agent could call, read, and never act on the number of — the acknowledgement
would go back to being a courtesy. Here the number cannot be skipped, because
the only way to learn it is to be refused for not knowing it, and the only way
to proceed is to type it back. **An agent cannot spend a hundred model calls
without having stated the number**, which is playbook rule 7 promoted from
advice to contract.

Two notes on the arithmetic. It is **declared-only**: `planned_calls` is a pure
function of the suite, no provider is asked and nothing is priced. And it
**excludes suspended cases**, because they are never called — announcing a
figure that included them would be a figure nobody could reconcile with the
invoice.

## §3 — A separate package, importing digline as a library

`digline-mcp` is a workspace package under `packages/`, beside the three
provider plugins, published separately, with its own version.

**Separate**, because `mcp` is a heavy dependency and `digline` has one. The
core's only runtime dependency is `jsonschema`; installing the MCP SDK brings in
twenty-five packages including `pydantic`, `starlette`, `uvicorn`, `httpx2`,
`cryptography` and `python-multipart`. None of that may land on somebody who ran
`pip install digline` to check whether their prompt got worse.
`tests/test_layering.py::test_nothing_shipped_with_digline_imports_a_plugin`
already enforces the direction and covers this package for free: it globs
`packages/*`.

One item in that list is worth answering before somebody asks.
`opentelemetry-api` arrives unconditionally as a transitive dependency of `mcp`.
It is an API-only package whose default implementation is a no-op — it exports
nothing and sends nothing without an SDK and an exporter, neither of which is
installed. Fixed decision 5 stands unamended: **no network call the user has not
explicitly configured**, and this package configures none. The gate for it is in
§13.

**Importing digline as a library, never shelling to the CLI.** A server that
ran `subprocess(["digline", "compare", …])` and parsed stdout would be a second
implementation of every refusal, exit code and message in this repository,
kept in step by nobody. Errors are typed exceptions crossing a function call —
`UsageError`, `TenantMismatchError`, `ConfigMismatchError`, `ErroredRunError` —
and §10 says how they become something the agent can read.

**Floor: `digline>=0.6.0`**, and `tests/test_plugin_floors.py` holds it there.
That file needs amending to accept this package, and §11 says how.

**Console script: `digline-mcp`**, so a client's MCP config names a command
rather than a Python invocation.

## §4 — Six shapes, field-for-field, under one `output_version`

The responses are the existing `--json` structures, **field-for-field**, under
the same `OUTPUT_VERSION`. There is no second, "LLM-optimized" rendering of the
same facts: **one machine representation of the truth**, or the two drift and
the day they disagree nobody can say which one is digline's answer.

Field-for-field and not byte-for-byte, deliberately. The MCP SDK renders a
returned mapping into a text block with `json.dumps(…, indent=2)` at its own
defaults, where the CLI prints `sort_keys=True, ensure_ascii=False`. The two
therefore agree on every key and every value and differ in key order, which is
not a fact about a JSON object. `structured_content` carries the mapping itself.
Claiming identical bytes would be claiming something false with no consequences,
which is the worst kind of thing to write into a decision record.

Three of the six shapes exist today and are reused unchanged:

- **`compare`** → the shape of `digline compare --json full`: the headline, then
  `deltas`, `target_config_deltas`, `judge_config_deltas`. Always `full`; there
  is no `headline`-only mode, because the agent's job under `AGENTS.md` §3 and
  §4 is to name the cases that moved, and it cannot name them from counts.
- **`diff`** → the shape of `digline diff --json full`. **No `worse` field**, and
  as ADR 0008 §1 says, the absence is the point: there is nothing here for a
  caller to gate on, because a verdict exists only against an approved reference
  and neither side of a diff was approved by anybody. The self-diff refusal is
  kept — two arguments that resolve to the same run are refused, because every
  line of the answer would be a tautology.
- **`run`** → the shape of `digline run --json`: `key`, `tenant`, `suite`, plus
  `sentence` per §2.

Three do not exist today and are decided here. `digline list` prints a text
table and has no `--json`; there is no CLI command at all that reads one run or
the baseline as data. So these shapes are being **invented**, which is a larger
commitment than reusing one, and they are specified rather than left to the
implementation:

**`list_runs`** — the run list an agent chooses from, which is `AGENTS.md` §2's
whole subject:

```
output_version, tenant, suite, baseline_key (or null),
runs: [ { key, created_at, environment, git_commit, cases } ],   newest first
note: "",                       # Listing.note(), empty when nothing was left out
skipped: { "<schema version>": <count> },
unreadable: <count>
```

Sorted on `created_at`, the recorded fact, not on the filename that encodes it —
the same rule `cmd_list` and `_resolve_key` already follow.

`note`, `skipped` and `unreadable` are **response fields and not a stderr aside**,
which is the whole reason they are listed. In the CLI that note goes to stderr so
it cannot break a pipeline; here there is no stderr, and a listing that quietly
dropped half a suite's history would read exactly like a suite with a shorter
history. `AGENTS.md` §8 tells the agent to propose a migration, and this is the
field it proposes from.

`unreadable` is a **count and not a list of paths.** A path under `.digline/` is
this machine's fact, and `FileResultStore.key_for` already says as much about
absolute paths in run documents. The count is what the agent needs to say
something true.

**`get_run`** and **`get_baseline`** — the projection §5 defines. `get_baseline`
takes no run argument and refuses, with the CLI's own sentence, when the suite
has no baseline yet: *run it, look at the result, then promote* — which is the
one place on this surface where the word `promote` appears, as instructions for
a person.

**One field is added to `compare`, in both the CLI and here: `exit_code`.**
`AGENTS.md` §6 tells an agent to respect the exit code as the contract — `0`
proceed, `1` stop and report, `2` stop because nothing downstream is meaningful.
An MCP tool has no exit code, and an agent left to re-derive one from `worse`
and `unjudged` has to know the precedence rule (a regression outranks an
unjudged case) that `exit_code()` exists to hold in one place. Rather than let
the two surfaces diverge on it, `exit_code` is added to `compare --json` as
well, computed by the same function. Adding a key is explicitly within
`OUTPUT_VERSION`'s stated rule that added keys do not break a consumer, so this
is not a bump: **`OUTPUT_VERSION` stays 1**, and gains one comment line
recording the addition, beside the lines already there for
`target_config_changed` and `judge_config_deltas`. That comment is the whole of
the version's history and it is why it can stay at 1 honestly — a consumer
reading the constant's docstring can see every key that arrived without one.
The `CHANGELOG.md` entry lands **when this branch merges**, not with 0.6.0:
`compare --json` on Friday's release does not carry the field.

`diff` gains nothing of the kind, and must not: it has no verdict to carry.

`run`'s response carries no exit code either — it reports that a run was
written, not whether it was any good.

## §5 — What `get_run` and `get_baseline` return: a chosen projection

**An MCP response is a boundary crossing**, and fixed decision 9 governs it.

This is the part of the design that the four opening decisions did not yet
absorb, and it is the most consequential thing in this record. A response here
does not go to a terminal, or to a CI log inside the perimeter. It goes into a
model's context — commonly a model hosted by a third party — and from there into
transcripts, caches and logs that nobody in this repository controls. It is a
*worse* destination than the CI stdout for which `_delta_json` already refuses
to emit a `reason`, on the grounds that "a reason is payload, and stdout of a CI
job is a place logs go and stay."

So the run tools return a **verdict-only projection**, and it is **chosen here,
not inherited from an existing serializer.**

What crosses, per decision 9 — the verdict:

```
output_version, tenant, suite, environment, key, created_at, git_commit,
config_hash,
results: [ { case_id,
             suspended: true|false,
             verdicts: [ { name, assertion_id, status, score,
                           threshold, tolerance, metadata,
                           samples, sample_min, sample_max } ] } ],
aggregate: [ …the same verdict shape… ],
target_config: { values: {…}, withheld: […], identities: […] },
judge_config:  { values: {…}, withheld: […], identities: […] },
artifacts: { "<path>": { sha, text } | { withheld: true } },
disclosure: { run_metadata: […], score_metadata: […], artifacts: true|false },
metadata: { …only what Disclosure covers… }
```

The three additions of 2026-09-08, each in one line. **The intervals** are
readings of the instrument and the section's own criterion admits them: a score
of `0.667` with no interval cannot tell a wobble from a drift, which is the
judgement `AGENTS.md` §3 asks for. **The two configurations** are measurements
by ADR 0005's ruling, and they arrive through `SystemConfig.redacted()` rather
than through a rule written again here — `base_url` is the one field that
withholding keeps back, it is already reduced to a host by `endpoint_host` so no
credential was ever in it, and `SystemConfig` refuses to hold a key as both
present and withheld, so absent-not-emptied is an invariant of the type rather
than a promise of this function. **The artifact digest** now leaves with the
text or not at all: `{ sha }` beside a withheld prompt was this record
contradicting ADR 0003 §4, which it names in its own assumptions.

What does not cross, and is **absent rather than emptied**:

- `Verdict.reason` — the judge quotes the output, so the reason *is* the output;
- `CaseResult.suspended`'s stated reason — a developer writes "fails on the
  Rossi account", which is a customer's name in a sentence about a test;
- any `Score.metadata` key not covered by the suite's `Disclosure`;
- `Artifact.text` **and `Artifact.sha` together** unless the suite declares
  `Disclosure(artifacts=True)`, per ADR 0003 §4 — a prompt carries the end
  company's rules, and a digest is a verifier that recovers them;
- `SystemConfig`'s perimeter fields — `base_url`, the client's topology — which
  leave as a name in `withheld` and never as a value (ADR 0005 §2);
- `Case.metadata` and `Case.vars` entirely: they are the inputs, which is to say
  the data.

`suspended` becomes a **boolean**. The fact that a case was set aside is a fact
about coverage and belongs in the projection — `AGENTS.md` says a suspension
stays visible until it is lifted. The sentence explaining it is payload and does
not.

### The instrument's own flags — amendment, 2026-09-19

The projection above states what a *verdict* is and what a *case* is. It has
never stated what the **instrument** was doing, and six facts the run document
already carries do not reach a caller:
`Run.rejudged_from`, `CaseResult.canary`, `CaseResult.calibration`,
`Verdict.judged`, `Run.judge_samples` and `Score.sample_means`.

The gap was recorded in three places rather than fixed — ADR 0024's *Not decided
here*, the docstring of `run_document`, and `docs/mcp.md` — each saying the same
thing: none of them is withheld, they are simply absent, and closing it is a
decision about what crosses. This is that decision.

**Five were named in the brief; the sixth is `Score.sample_means`, and it is
the one that matters most.** The other five cost a reader a fact. This one costs
a reader a **wrong reading**: `samples: [0.5, 0.5]` is two judgements or two
means of judgements, and nothing in the projection says which. Schema 13 was
spent on that stamp precisely because no reading could tell them apart
(ADR 0024 §6.5) — and the surface built for a *model* to read has been shipping
the misreading the bump paid to stop. It joins here, or the bump bought the
document a guarantee the wire does not keep.

#### Each one, and what it lets a reader do

Not a block. They are five different kinds of fact and one of them is ruled out.

**`rejudged_from` — the sharpest, and it crosses whole.** A replay's answers
were not taken from the target: its scores did not move because the system
moved, and its interval is the judge's wobble with none of the target's in it.
A consumer that reads a replay as a fresh measurement concludes the system got
better on a day nothing was asked of it. It crosses as the **key**, not as a
boolean: `redact()` already rules it travels — "a run key — a timestamp and a
config hash — so it carries no payload" (ADR 0014 §3) — and the key is
actionable, since a caller can pass it straight back to `get_run` and read what
was replayed. `compare` already carries the boolean on its headline; this is the
half a caller reading **one run** has no way to get.

**`canary` — a case that is an instrument, not a measurement.** Its score is a
fingerprint of which model answered, and re-running asks the same alias the same
thing (ADR 0016). A consumer reading the case rows today averages it into
"quality" with everything else. It crosses as a boolean on the case row, the way
`suspended` does and for the same reason: which case watched the model is a fact
about the suite's design, never about the end company's data.

**`calibration` — the same family, with numbers.** The case carries an answer
the author wrote and a band its score must land in, so its score measures the
**judge** and not the system. The whole band crosses — the check's name and two
numbers — which is what `redact()` already keeps, for a reason it states: a
redacted document that lost them "would report an exit code its own contents
could not account for" (ADR 0024 §9). The same sentence is true here: a caller
that sees exit 2 and no calibration in the run cannot account for it.

**`judged` — a model placed this score.** It is the per-check half of the
judgement `AGENTS.md` §3 asks for: a movement on a judged check may be the
judge's noise, and the same movement on a deterministic one cannot be. It
crosses as a boolean, written only where true, exactly as the document writes
it. It is **not** derivable from what crosses today: the `shape` list is on the
comparison surface, needs a reference, and leaves out a `Repeated` fold by
construction — so a caller reading one run has nothing.

**`sample_means` — the sixth, and the one whose absence is a misreading.** It
qualifies `samples`, which this projection has carried since its first
amendment. It crosses with them, as a boolean, for the reason the intervals
cross at all: a reading of the instrument that cannot say what its numbers *are*
is not a reading.

**`judge_samples` — ruled OUT, and the omission is the point.** It says how many
times each judged check asked the judge per recorded answer, on a replay that
measured the judge's own range. The numbers it qualifies — `judge_min`,
`judge_max`, `judge_errored`, `judge_answer` — live in `Score.metadata`, and
this projection filters metadata to the suite's `Disclosure` allowlist with
**no `travels()` fallback**, so none of them crosses unless the suite names
them. A
bare `judge_samples: 5` would therefore reach a caller as a count with nothing
to count against: it cannot say how far the judge ranged, only that somebody
asked. `rejudged_from` and `sample_means` already tell the caller the two things
it can act on — this run is a replay, and these scores are folds — and the
count adds a number nobody can use. It waits for the decision that lets the
range itself cross, which is a different decision and belongs with the 0.15.0
finding that this projection is stricter than `travels()`.

#### The boundary, per field rather than by assertion

Each is checked against what a `Disclosure` governs and what `travels()` admits,
because the 0.15.0 delta-pass found this projection **stricter** than
`travels()` in exactly one place — `Score.metadata` is an opt-in allowlist
here, so the
numbers `aggregate.py` says cross do not — and a field placed in the wrong
container is a field silently dropped where world 2 needs it.

| field | what it is | why it crosses |
|---|---|---|
| `rejudged_from` | a run key: an ISO timestamp and a config hash | names a document of ours, never a case, an input or an answer. `redact()` already carries it in clear |
| `canary` | a boolean the case author wrote | a fact about the suite's design. `travels()` admits booleans; it is a field, so it does not pass through the metadata filter at all |
| `calibration` | a check name and two floats, declared in the suite | the author's own declaration. No customer data can reach it: the band is written in code and the answer it calibrates against stays in the case file, which does not cross |
| `judged` | a boolean copied from the check's `KIND` | a property of the *class*, not of the case |
| `sample_means` | a boolean about how the scores were stored | says what the numbers beside it are; carries no number of its own |

None of the five is a string taken from data. The one string among them —
`rejudged_from` — is a key digline composed, and the one place a customer's text
could enter a key is the suite name, which this projection already carries as
`suite`. Nothing here needs a `Disclosure`, and nothing here may be opened by
one: a `Disclosure` widens what the *suite* releases, and these are facts about
our own instrument.

#### What it costs: `OUTPUT_VERSION` does not move

The rule that applies is the contract's own first one — **an added key breaks no
consumer** — and it has been applied nine times without a bump, most recently
for `denominator_moved`. This change adds keys and does nothing else: no key is
removed, no value is rewritten, no number changes, and a caller that ignores all
six parses the bytes it parsed before.

`OUTPUT_VERSION` moved to `2` for a different rule, and the distinction is worth
stating because it is the one a future change will be judged against: the bump
rewrote **bytes inside values a consumer already reads** — DEL and the C1 block
as their escape spelling, in every string this package renders. That is not an
added key, and it is why it cost a version. The two `counts` removals sit
between the two and were tolerated without a bump for a stated reason of their
own: they removed a number that was an affirmative false claim.

This change is in the first category, without qualification.

#### The reader on the other side

Our own reasoning operator (ADR 0019) is the nearest consumer and it reads
**`explain --json`**, not `get_run` — so it is not blocked today for the facts
`explain` already carries as tallies. What this amendment serves is the caller
reading **one run with no reference**, which is what `get_run` is for and what a
first run, a pre-baseline suite and any agent inspecting a stored document
actually have.

And `docs/mcp.md` currently tells that caller something that is not true. It
says of these fields: *"Call `explain` or `compare` for them, which carry
each as a fact."* Checked against the code:

- `rejudged` — true. `explain` emits the tally; `compare`'s headline carries it.
- `canary`, `calibration` — true only with a reference, and only on the
  comparison's deltas. A run read alone has neither.
- `judged` — **not carried anywhere** as a per-check fact. Inferable only from
  the `shape` list, which needs a reference and omits folds.
- `judge_samples` — **carried nowhere at all**: zero occurrences in
  `digline.wire` and in `digline.report.explain`.

So the documented workaround is false for one field and unavailable for another,
and the page is corrected by this amendment rather than left to be believed.

*Corrected 2026-09-19, and dated in the page itself rather than rewritten
silently: this is the third documentation defect in a week that promised
something the code does not do, and a page whose history shows it was **checked**
is worth more than one that reads as if it had always been right.*

#### What this does not do

It does not add a verdict, a gate or an exit code; it does not move
`SCHEMA_VERSION` — nothing about the stored document changes; it does not widen
any `Disclosure`; and it does not let `Score.metadata` cross by `travels()`,
which stays the open question `judge_samples` is waiting on.

#### Test plan

`tests/test_wire_boundary.py` is where this is asked, since that file was named
as the test that would ask for a decision:

- each of the five crosses, asserted by key and value on a run that carries it;
- `judge_samples` is asserted **absent**, so the ruled omission cannot be closed
  by accident and a later reader meets the ruling rather than a gap;
- a run carrying none of them projects exactly the keys it projects today, so
  the ordinary document is unchanged;
- `sample_means` travels **with** `samples`, asserted together: the pair is the
  claim, and either alone is the misreading;
- the negative half stands: no reason, no case inputs, no undisclosed metadata,
  no artifact digest without its text;
- `OUTPUT_VERSION` is asserted unchanged at `2`, beside the added keys, so the
  rule and its application are read in one place.

### Why chosen and not inherited

The obvious alternative is `run_to_json(run, redacted=True, disclosure=suite.disclosure)`.
It already exists, it already omits rather than empties, and it already stamps
`"redacted": true`. It was rejected for one reason, and the reason is a
sentence this repository has already written down about something else:

**Two contracts, two lifetimes.** `run_to_json` is under `SCHEMA_VERSION` — the
contract for documents already on disk, which is why it comes with migrations.
The MCP response is under `OUTPUT_VERSION` — the contract for what a consumer
parses today. `OUTPUT_VERSION`'s own docstring says why tying them together is
wrong: a new field inside a `Run` would move what an agent parses, and a
reworded storage concern would bump the surface. Inheriting the projection from
the storage document means **the boundary moves whenever `run_to_dict` moves.**
Choosing it means the boundary moves when this record moves, and only then.

The second reason is smaller and still decisive: a redacted storage document
*declares itself to be a run with pieces missing*. That is the right shape for a
run leaving a perimeter as a document. It is the wrong shape for an answer to
the question "what did this run measure", where nothing is missing — the payload
was never part of the answer.

### The gate

**The no-reason gate**, written as the sibling of the redaction tests: for every
tool on this surface, over a suite whose cases, verdicts, suspensions, artifacts
**and withheld configuration values** all carry distinctive payload strings,
**no response may contain any of them.** The withheld config value is in the
marker suite deliberately: the projection must not leak what the delta rendering
already withholds, and the two are built by different functions. Serialize the whole response, search it for each marker, fail on a
hit. It runs over every tool and not only the two that return runs, because
the point is the boundary and not the function.

That gate is what makes "chosen" mean something: a field added to the projection
without a decision fails a test rather than shipping.

## §6 — `digline.wire`: the machine surface, promoted out of the CLI

Every `--json` shape is built today in `src/digline/cli/main.py`, and every
builder of it is private: `_delta_json`, `_config_json`, `_interval_json`,
`_check_json`, `_diff_json`, with `compare`'s and `run`'s payloads assembled
inline inside their command functions. A second front end that reached for those
would be reaching for underscore names, which is how two renderings of the same
truth start to drift while both look maintained.

So the machine surface is promoted into a package of its own:

    src/digline/wire/    what crosses a boundary as a machine reads it:
                         OUTPUT_VERSION and the pure functions that build
                         every --json and every MCP response. No I/O.

**The name.** `report/` is the document for world 3, rendered for a person who
did not choose English. `wire/` is the same facts rendered for a program: one
subject, two recipients, two packages. "Wire format" already carries the
versioned-contract sense that `OUTPUT_VERSION` has, and the package is the one
place in the repository where decision 9's boundary is a function you can point
at.

**Contents**, moved verbatim except for losing their underscores:

```
OUTPUT_VERSION                       (moved; re-exported from digline.cli
                                      so `from digline.cli import OUTPUT_VERSION`
                                      keeps working)
delta_json, config_json, interval_json, check_json
compare_json(comparison, head, *, full)      extracted from cmd_compare
diff_json(...)                               made public
run_json(ref, plan)
runs_json(rows, *, baseline_key, listing)    new (§4)
run_document(run, disclosure)                new (§5) — the projection
```

`wire` imports `digline.core`, `digline.store` (for `Listing`) and
`digline.report` (for `Headline`), does no I/O, and reads no clock — the same
constraints `report/` is held to, and gated the same way.

The allowed-dependency chain in `CLAUDE.md` gains it:

    cli → host → targets → run/report/wire/bridge/online → store/production → core

**Nothing about the CLI's output changes.** The commands print exactly what they
printed, from functions that now live one directory over. That is the point of
doing it as a move: the guarantee that the two surfaces agree is that there is
one function, not two that were once compared.

## §7 — `digline.host`, and the gate that makes §6 mean something

Promoting the shapes is only half the anti-drift move. The other half is a gate:
**nothing under `src/digline/` or `packages/` may import `digline.cli`.**

Enforced in `tests/test_layering.py` beside the gates that keep the core pure
and the driver ignorant of the store. Tests are exempt — they exercise every
layer by definition, and a dozen of them drive the CLI today.

Stated that plainly, the gate is not satisfiable by the current tree, and
finding that out is the useful part. `digline-mcp` needs five things that live
in `digline.cli` and are not shapes: `load_suite`, `load_target`,
`read_artifacts`, `git_commit`, `utc_now_iso`. It needs them because **they are
not the CLI's; they are the host's.**

`digline.cli` today wears two names at once:

1. **The host** — the process that has a filesystem, a clock and a git
   repository. Reading the clock, asking git for the commit, importing the
   user's `suite.py` without touching the bytecode cache, reading the declared
   artifact files. Any front end needs all of it.
2. **The terminal** — argparse, the help text, the printed tables, the exit
   codes. Only a terminal needs any of it.

`CLAUDE.md` already says the first thing and calls it the second:
*"the **only** one allowed to read the clock and git."* That sentence is right
about the layer and wrong about its name, and it has been getting away with it
because there has only ever been one front end.

So:

    src/digline/host/    the layer that touches the world: the clock, git,
                         importing a suite, reading the declared artifacts.
                         The only one allowed to read the clock and git.
    src/digline/cli/     the terminal front end: argparse, printing, exit codes.
                         One host front end among others.

The move, in full — this is a rename and a re-home, no logic changes:

| from | to |
|---|---|
| `cli/environment.py` | `host/environment.py` |
| `cli/errors.py` (`UsageError`) | `host/errors.py` |
| `cli/loader.py` | `host/loader.py` |
| `cli/toml_suite.py` | `host/toml_suite.py` |
| `cli/toml_errors.py` | `host/toml_errors.py` |
| `read_artifacts` from `cli/main.py` | `host/artifacts.py` |

What stays in `cli/`: `main.py` (argparse, printing, exit codes), `view.py`,
`__main__.py`, `__init__.py`. `main.py` drops from 911 lines to roughly 550 —
the `_*_json` family leaves for `wire`, `read_artifacts` leaves for `host`.

`digline.cli` re-exports what it exported before (`UsageError`, `OUTPUT_VERSION`,
the exit codes, `main`), so `from digline.cli import EXIT_OK` keeps working and
the twelve test files that do it are untouched. The three test files that import
`digline.cli.toml_suite` directly are updated; that is a mechanical rename.

Then `digline-mcp` imports `digline.host`, `digline.wire`, `digline.run`,
`digline.store`, `digline.report` and `digline.core` — and not `digline.cli`,
because there is nothing left in `digline.cli` that a server would want. The
gate is satisfiable, and it says something true: **the CLI is a front end, and
front ends do not import each other.**

`_resolve_key` and `_need_baseline` are the two remaining private helpers both
front ends need. They are resolution, not shape, and they raise `UsageError` and
bind `FileResultStore` concretely — so they go to `host/resolve.py` as
`resolve_key` and `need_baseline`, not to `wire`.

### What this costs, said plainly

This is the largest single item in the record and it is not what the MCP server
is *about*. It is roughly 1,200 lines moved between files, six import paths
changed, three test files updated, and one paragraph of `CLAUDE.md` rewritten —
all of it mechanical, none of it changing behaviour, and all of it verifiable by
the existing suite passing unchanged.

It lands as **its own commits, before any MCP code**, so the diff a reviewer
reads is a move and nothing else — a re-home, then an import sweep, then the
gate that makes the re-home mean something.

**None of it rides the 0.6.0 release.** This branch merges after Friday, so the
host layer arrives with the server or it does not arrive: there is no window in
which `digline` has shipped a `host/` package that nothing outside the CLI is
using. The cheap alternative in §12 was weighed against exactly this and
rejected.

## §8 — One server, one repository

`digline-mcp --root <path>` and, like every CLI command, `--tenant` and `--env`,
which **verify and never override** (ADR 0002 §1). One server process serves one
repository, and the perimeter is the repository.

**And `suite` is checked against it.** This section said the perimeter was the
repository and nothing enforced it: the argument arrived from a tool call and
went to `load_suite`, which *executes* a `.py`. Every tool was therefore a way
to run a file from anywhere on the disk — including the five annotated
`read_only_hint=True`, which is the annotation a client reads to decide it may
call one without asking a person. From 0.1.1 the spec must name a file inside
`--root`, checked in the one function every tool crosses. The check is
deliberately stricter than the loader's: it also refuses the dotted-module
form, which resolves through `sys.path` and so names something this server
cannot place inside the repository at all. The CLI still takes that form — a
person's tool has no perimeter to keep.

**And a suite inside the root is trusted, deliberately.** The check above is
about *which file* the server may be pointed at. It is not a sandbox, and it
does not try to be: a `suite.py` inside the repository is Python, and this
server executes it. It may `sys.path.insert` a directory outside the root and
import from it, open any file the process can open, and call anything it likes.
The adversarial pass over the 0.7.1 fixes confirmed all of that works, on this
surface and through the CLI, and it is written here so that the next person to
confirm it reads a decision rather than a miss.

The reasoning is the same one that put the perimeter on the *argument*. What
arrives from a tool call is attacker-controlled in the way that matters — a
model chose it, possibly because something in its context told it to — and the
five reading tools are annotated `read_only_hint=True`, which is a client's
licence to call them without asking a person. What is committed in the
repository is not that: it is code somebody wrote, reviewed and merged, and it
had to be trusted before digline ever ran it. A server that tried to confine it
would be claiming a guarantee it cannot keep, and the honest version of that
claim is this paragraph.

So the boundary is: **the agent may not choose the file; the repository may not
be confined.** If you need the second, the answer is an OS-level sandbox around
the whole process — a container, a jail — and not a check inside a program the
suite has already been imported into.

**Multi-project is N named servers in the client's config**, not a registry in
ours:

```json
{ "mcpServers": {
    "digline-northwind": { "command": "digline-mcp", "args": ["--root", "~/src/northwind"] },
    "digline-acme":      { "command": "digline-mcp", "args": ["--root", "~/src/acme"] } } }
```

The alternative — one server with a `project` argument, or a registry of known
roots — is refused, and fixed decision 2 is the reason. A registry is
machine-global state describing where other people's customers keep their
results. It would be the one file in this design that is not inside anybody's
repository, could not be committed with the code it points at, and would name
every tenant on the machine in one place. `.digline/<tenant>/` puts the
perimeter in the filesystem precisely so that it is not a field in a document
somebody could get wrong; a registry would put it back into a document.

**Transport is stdio.** The client launches the process; there is no bound port
and no listening socket. The SDK also offers SSE and streamable-HTTP, and
neither is wired here: fixed decision 5 is about network calls the user did not
configure, and a server that listened by default would be the same mistake
facing outward. If a remote transport is ever wanted it is a separate record,
with authentication in it.

## §9 — The playbook rides with the instrument

Tool descriptions are not `--help`. They are loaded into the context of the
model that is about to call them, at the moment it decides whether to. That
makes them the one place where `AGENTS.md` reaches an agent that never read
`AGENTS.md`.

So each description carries the rule that governs its own misuse:

- **`run`** carries §3's stopping rule — *decide the number of re-runs before
  running them; with a stochastic judge, enough re-runs always produce a green
  one, and a stopping rule chosen after the fact measures your patience rather
  than the system* — and §7's obligation to state the cost, which §2 has already
  made a parameter.
- **`list_runs`** carries §2 — *promote from the middle of several, never from
  the first one that goes green* — and, because this surface cannot promote, the
  form that applies here: **recommend** the median run to the human, with the
  key, and let them run the command.
- **`compare`** carries §5 — *"within noise" explains, it does not excuse* —
  and §6's reading of the exit code, which §4 puts in the response.
- **`diff`** carries ADR 0008 §1: neither side is a reference, there is no
  `worse`, and nothing here gates anything.
- **`get_run`** / **`get_baseline`** carry §4: several cases flipping together is
  investigated and not retried, because retrying destroys the evidence either
  way.

**The agent that loads the tools receives the discipline with the instrument.**
`tests/test_agents.py` already fails when `AGENTS.md` and the shipped skill drift
apart; the descriptions join that gate (§13), so a rule reworded in one place
cannot stay stale in the other two.

## §10 — The SDK, as it actually is

Verified against the published package rather than from memory, because it is
the one new external dependency and its reality shapes the implementation.

**The current SDK is `mcp` 2.2.0, and `FastMCP` no longer exists.** The 2.0
release renamed it; `mcp.server.fastmcp` is now a stub that raises
`ModuleNotFoundError` with a migration URL. Every example written before that
release — which is nearly all of them — is wrong. The API is:

```python
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="digline-mcp", version=...)


@server.tool(name=..., description=..., annotations=ToolAnnotations(...))
def list_runs(suite: str) -> dict[str, Any]: ...


server.run(transport="stdio")
```

**Floor: `mcp>=2.2,<3`.** Both halves matter. Unpinned, a resolver could hand a
user 1.x, where this code does not import. The `<3` cap is the lesson the caps
gate on `examples/` already encodes: a major version that renames the entry
point is not hypothetical here, it happened last month.

What was confirmed by running it:

- **Input schemas are derived from the signature.** `def get_run(suite: str, run: str = "latest")`
  produces `required: ["suite"]` with `run` defaulted. The six signatures in §1
  need no hand-written JSON Schema.
- **A returned mapping produces both** `structured_content` (the mapping itself)
  and a `content` text block. §4's field-for-field claim is about the former.
- **`ToolAnnotations`** carries `read_only_hint`, `destructive_hint`,
  `idempotent_hint`, `open_world_hint`. The five reading tools declare
  `read_only_hint=True`; `run` declares it `False` and `idempotent_hint=False`.
  These are hints and not enforcement — the enforcement is §1's absence — but a
  client that surfaces them shows the user the same shape this record describes.
- **`pyright --strict` reports zero errors** against the decorated form. The
  repository's strict gate survives contact.
- **Error handling is bimodal, and this dictates §3's implementation.** A
  `ToolError` reaches the caller with its message, as
  `CallToolResult(is_error=True, content=[TextContent(...)])`. **Anything else is
  wrapped and its message is discarded** — a custom exception arrived as the bare
  string `"Error executing tool <name>"`.

  So every digline exception is translated at the boundary: `UsageError`,
  `TenantMismatchError`, `ConfigMismatchError`, `ErroredRunError`,
  `DifferentSuitesError`, `DifferentJudgesError` and `ProviderNotFound` are
  caught and re-raised as `ToolError` carrying the message digline wrote.
  Nothing else is caught: an unexpected exception should be an unexpected
  exception, and dressing it as a tool result would hide a bug behind a sentence.

  **The translation is one function and it is gated** (§13). Without it, every
  carefully written refusal in this repository — the perimeter messages, the
  three promotion conditions, "no runs stored for suite … run it first" —
  reaches the agent as five identical words.

## §11 — `test_plugin_floors.py`, amended

The file auto-enrols every directory under `packages/` with a `pyproject.toml`,
so `digline-mcp` joins it the moment it exists. Two things then fail, and both
are the gate working:

**`test_a_dated_name_still_exists_in_the_core` fails outright.** It asserts
`hasattr(digline.core, name) or hasattr(digline.targets, name)` for every dated
name, because until now a plugin was a provider and a provider imports from
those two. `digline-mcp` imports from `digline.store`, `digline.run`,
`digline.report`, `digline.wire` and `digline.host`. The check is widened to
those modules. The rule is unchanged: a dated name that no longer exists in the
package it was dated against still fails.

**Every name it imports needs an `INTRODUCED` entry.** That is the gate doing
exactly what its docstring says — *the moment a plugin reaches for a new part of
the core, somebody has to say which version it appeared in, and that is exactly
the moment the floor needs deciding.* The names promoted in §6 and §7 are dated
**0.6.0**, which is the release that first publishes them, and the floor
`digline>=0.6.0` follows from the highest of them rather than being asserted.

**The vocabulary changes with it.** The file is written throughout about
*plugins*, and `digline-mcp` is a workspace package that registers no
`digline.providers` entry point and is not one. The docstring and the failure
messages say *workspace package*; the trap they describe — a floor below the
newest name the sources import — is identical either way.

The `examples/` caps gate is untouched: no example depends on `digline-mcp`.

## §12 — Alternatives rejected

**`promote` present but refused.** §1. A refusal is a conversation.

**A second, LLM-shaped response format** — flattened, prose-annotated, "easier
for a model". Rejected as decision 3 in the opening set and restated here
because it will be proposed again: two representations of one truth diverge, and
the day they disagree there is no answer to which one is digline's.

**Shelling out to the CLI.** §3. A second implementation of every refusal.

**`get_run` returning `run_to_json(redacted=True)`.** §5. Two contracts, two
lifetimes.

**A tool for the call plan.** §2. It would make the acknowledgement a
courtesy again.

**A registry of projects.** §8. Machine-global state naming every tenant.

**Leaving the shapes in `cli/main.py` and letting `digline-mcp` import
`digline.cli`.** This is the cheap alternative to §6 and §7 and it deserves its
paragraph, because it is the one that will look attractive at the wrong moment.
It works: nothing today forbids it, the gates all pass, and the server ships a
week sooner. What it costs is the guarantee. `digline-mcp` would import
`_delta_json` and `_check_json` — private names, by definition not a contract —
and the first time somebody refactors `cmd_compare` they would have no way to
know that a published package parses the function they are editing. The shapes
would be identical on the day they shipped and there would be nothing keeping
them identical. That is precisely the drift this record exists to prevent, and
buying a week with it is buying the week from a later maintainer.

**Remote transport (SSE / streamable-HTTP).** §8. A listening socket by default
is fixed decision 5's mistake facing outward. Deferred to a record with
authentication in it.

## §13 — Test plan

In `packages/digline-mcp/tests/`, run by the workspace pytest, plus the
amendments named above.

**The absence, which is the thesis:**

1. `list_tools()` returns exactly six names, asserted as a set. Adding a
   seventh fails until somebody edits this test, which is the point. *(Edited
   once, by ADR 0020 §9, to eight names: a ninth now fails the same way.)*
2. `promote`, `migrate`, `view` and `report` are not among them, asserted by
   name, so the failure says which one came back.
3. No module in `packages/digline-mcp/src/` imports `promote_baseline`,
   `migrate_paths` or `serve` — the absence holds at the import graph and not
   only at the tool list.

**The boundary (§5), the redaction tests' sibling:**

4. **The no-reason gate.** A suite whose verdict reasons, suspension reasons,
   case metadata, case vars and artifact text all carry distinct markers. Every
   one of the tools is called; each response is serialized whole and
   searched for every marker. Any hit fails, naming the marker and the tool.
5. `Disclosure(artifacts=True)` lets artifact text through, and only then —
   the positive half, so the gate is proving a boundary and not proving that
   the field is always empty.
6. `Score.metadata` covered by `Disclosure` travels; the rest is absent, not
   emptied — asserted on key presence.

**The shapes (§4):**

7. For `compare`, `diff` and `run`: the tool's `structured_content` equals
   `json.loads` of the corresponding CLI `--json` output over the same store,
   key for key. This is the anti-drift test, and it is why §6 exists.
8. `diff`'s response has no `worse` key, at any nesting depth.
9. `list_runs` over a store containing a foreign-schema document reports it in
   `skipped` and `note`, and `unreadable` is an integer.
10. `get_baseline` on a suite with no baseline refuses with the sentence naming
    `promote` as something a person runs.

**The acknowledgement (§2):**

11. `run` without `acknowledge_calls` is refused, the target is never called,
    and the refusal contains both the integer and `CallPlan.sentence()`.
12. `run` with a wrong `acknowledge_calls` is refused the same way. A suspended
    case is excluded from the figure, so a suite with one suspended case of
    twenty acknowledges 19 × samples.
13. `run` with the right number executes and writes exactly one run.

**The errors (§10):**

14. Each of `UsageError`, `TenantMismatchError`, `ConfigMismatchError`,
    `ErroredRunError`, `DifferentSuitesError`, `DifferentJudgesError` reaches the
    caller as a `ToolError` whose text contains digline's own message.
    Parametrized, so a new exception type added to digline without a translation
    fails here rather than reaching an agent as five words.

**The layering (§6, §7):**

15. Nothing under `src/digline/` or `packages/` imports `digline.cli`. In
    `tests/test_layering.py`, beside the existing gates.
16. `digline.wire` does no I/O and reads no clock — the constraint `report/` is
    already held to, same forbidden-module list.
17. `digline.core` still imports on its own without dragging `wire`, `host` or
    `store` in. The existing subprocess check, unchanged, still passing.

**The dependency (§3):**

18. `pip install digline` does not install `mcp`: no module under `src/` imports
    it. Covered by the existing plugin-direction gate, asserted explicitly here
    because the dependency is heavy enough to be worth naming.
19. Importing the server module configures no OpenTelemetry exporter and opens
    no socket.

**The playbook (§9):**

20. Each tool description quotes the `AGENTS.md` rule §9 assigns it, checked
    against the file the way `tests/test_agents.py` checks the shipped skill —
    so a rule reworded in one place cannot stay stale in the other two.

## Consequences

- A coding agent can read a digline result correctly and **cannot promote a
  baseline**, because there is nothing to call. `AGENTS.md` §1 stops being a
  request.

  *Amended 2026-09-24 by [ADR 0032](0032-the-second-path-to-an-absent-tool.md).*
  The claim stands; its reason did not, and the difference mattered. The
  subject of that sentence is the **agent**, not this server, so "there is
  nothing to call" was a claim about the whole reachable surface — and it had
  been checked against one package. `digline view` served `POST /promote`,
  reachable with no browser and no credential, from the first release of it
  until ADR 0032 §1 made refusal the default. The sentence is true again, and
  now for the stated reason.
- An agent cannot start a hundred model calls without having stated the number.
- digline gains two internal packages, `wire` and `host`, and the CLI becomes
  what it always was: one front end.
- The machine surface has one implementation, and the test that says so compares
  the two callers rather than trusting them.
- `packages/digline-mcp` ships on its own cadence, floored at `digline>=0.6.0`
  and `mcp>=2.2,<3`.
- `CLAUDE.md`'s Structure section is amended: two new lines, and the
  clock-and-git sentence moves from `cli/` to `host/`.
