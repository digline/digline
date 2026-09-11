# ADR 0015 — The recorded output, and the declared re-judge

- Status: accepted — the text first, the implementation written against it on
  `release-schema`, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0011](0011-the-mcp-server.md),
  [ADR 0012](0012-the-reading.md) and
  [ADR 0013](0013-the-pytest-plugin.md) were
- Date: 2026-09-11
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born, the verdict travels), §3 (`Disclosure` is
  asymmetric), §8 (promotion has three conditions);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4 (what
  travels only when the suite says so, and why a digest goes with its text);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §3 (beside the
  hash, not inside it), §4 (a judge that moved is louder than a target that
  did);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §1 (what is repeated
  is the target's answer), §5 (the interval is the baseline's);
  [ADR 0011](0011-the-mcp-server.md) §5 (the boundary projection is chosen, not
  inherited);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule, which
  this field is checked against)
- Amends: [ADR 0012](0012-the-reading.md) §3 — the `TallyKind` list is closed by
  that section, and §8 below adds one member to it with the sentence that
  justifies it
- Touches: `CLAUDE.md`'s fixed decision 9 — **reaffirmed in its most literal
  case**. The model's answer is the payload, it is recorded only where it is
  born, and the two things that cross a boundary — `redact()` and
  `digline.wire` — drop it by construction. Nothing in the fixed section is
  amended

## Context

digline has never kept what the model said. It keeps the verdict about what the
model said: a score, a threshold, a status, an identity, and a `reason` in which
a judge quotes the output and which is therefore redacted at every boundary. The
run file is the record of a *judgement*, and the thing judged is gone the moment
the process exits.

That was the right default and it stays the default. What has accumulated
against it is three signals, and they arrive from three different directions.

**The scout asked for it.** In the mirror dogfood, the agent driving digline
against digline wanted to re-grade a stored run — to change a judge, or a
threshold, and see what the same answers scored — and there was nothing to grade
against, so the only available move was to pay the target again for answers
nobody doubted. The ask is recorded in the working material rather than
reproduced here: `private/` is a separate repository and this one is public.

**The Reddit thread asked the same thing from the outside**, unprompted, from
somebody who does not know this repository exists. Same reservation about the
wording, same place it is recorded. What matters for the decision is that the
ask did not originate inside the project.

**The competitive report answered it, and the answer is the interesting one.**
The audited field solves this with a **response cache**: `DEEPEVAL_CACHE_FOLDER`
in the audit's own notes is the concrete instance, and the pattern is general —
a hidden directory, keyed by something like the request, consulted before the
provider is called. It is a good engineering trade and a bad instrument. A cache
returns an old answer *as though it were a new one*: nothing in the resulting
document says the model was never asked, the run reads as a fresh measurement,
and a suite can go green against answers produced by a model that has since been
replaced. It is fixed decision 3's vacuously green assertion arriving through the
plumbing, and it is a store of somebody's payload in a location nobody declared
— which is the other half of what this project refuses. The report's conclusion,
written when the audit was: the honest answer to a cache is not a cache of our
own, it is **a re-judge that declares itself**. That is what §6 builds, and it is
why the recording and the replay are one ADR rather than two.

Three signals, and **no fourth is claimed**. The reconnaissance done for the
harvest work checked whether capture — building cases out of an application's
own traffic — would consume what this ADR records, and it does not: capture
reads the app's log, not a stored run's recorded output. The two features touch
the same neighbourhood and share no mechanism, and saying so plainly costs this
record nothing while a fourth signal quietly assumed would have cost it its
accuracy. Capture is deferred to a future traffic-to-case ADR and is not
designed here.

The hazard, stated before the design because it is the reason this record exists
first: **the output is the most sensitive field the document would ever carry.**
A `reason` is a judge's sentence about the output; the output is the thing
itself, in full, for every case. A feature that records it by default, or that
lets one line in a suite send it, would undo in a release what ADR 0002 and
ADR 0003 were written to establish.

## Decision

### 1. What is recorded, and where it lives

`CaseResult` gains a sequence:

    CaseResult.responses: tuple[RecordedResponse, ...] = ()

    RecordedResponse:
        output:     str | None      canonical JSON of the Output, or its text
        kind:       OutputKind | None
        input:      str | None      the rendered prompt, as sent
        cost_usd:   float | None
        latency_ms: float | None
        withheld:   bool            redaction took it
        oversize:   bool            the recorder refused it (§3)

**A sequence, not a scalar,** because `Suite.samples` already means one case has
N answers (ADR 0006 §1) and the fold from N verdicts to one is the suite's
measurement. Recording only the last answer would record the one thing no
verdict was built from. The order is the order they were produced, which is the
order `combine_samples` folded them in.

**`input` sits beside `output`, and it is not an extra.** The prompt is rendered
*inside* the target — `Response.input` exists because "without it `llm_rubric`
would judge an answer without knowing the question" — so a stored answer with no
stored question cannot be re-judged by any assertion that takes the input, which
is most of the ones that call a model. The harvest reconnaissance reached the
same conclusion independently from the other end: input-beside-output is the
shape a future online driver needs, because a production response arrives with
the request that caused it or it arrives unjudgeable. One shape serves both, and
it is this one.

**`cost_usd` and `latency_ms` ride along** for a narrower reason that is easy to
discover too late: a suite holding a `CostBudget` or a `LatencyBudget`, re-judged
without them, does not fail those checks — it **errors** them, silently turning
a declared gate into a row nobody gated on. They are numbers measured by the
system, so they cross a boundary on their own merit by `travels()` and in fact
already do, inside `CostBudget`'s score metadata.

`Output` is a closed union, so the stored form is the canonical JSON of whichever
branch it was, with `kind` recording which. `canonical()` already exists for
exactly this and is already what makes a document deterministic.

### 2. Opt-in, declared on the suite — and deliberately not a `Disclosure`

    Suite.record_responses: bool = False

Off by default and never inferred. In the declarative form it is one line in
`[suite]`; the loader builds cases and suites from declared fields, so the
Python and the data forms gain it together.

**It is not a member of `Disclosure`, and the distinction is the whole safety
of this feature.** `Disclosure` governs what *crosses a boundary*;
`record_responses` governs what is *written inside the perimeter*. Two verbs,
two decisions. Putting the flag inside `Disclosure` would put it in the type
whose every other member is a licence to send, and the first reader to set it
would reasonably believe they had turned on exactly what §4 forbids.

**`config_hash` consequence: none, and that is a ruling rather than an
omission.** Recording changes no score, pairs no verdict differently, and moves
no bar, so by ADR 0014 §1 it stays out — and the precedent is exact:
`Suite.disclosure` has never been in the hash either. A suite that turns
recording on keeps its baseline, keeps its promotion, and its next report says
the rules are unchanged, because they are.

### 3. Whole, or nothing at all

A recorded answer is evidence for a re-run, not prose for a human, so it is
recorded in full. What it is not is unbounded: the ceiling is **65 536
characters** for `output` and the same for `input`, and exceeding it on either
records **neither**, with `oversize=True` saying which absence this is.

Truncation is the option that looks kindest and is worst. A clipped answer
re-judged produces a score that looks like every other score — a silent, plausible
number measured on evidence the document does not admit is partial. `reason`
clips at `MAX_FAILURE_CHARS` because a reason is a sentence for a person and half
a sentence still informs them; this is not that, and the difference is why the
rule differs.

The arithmetic, said out loud: forty cases at five samples, both fields at the
ceiling, is about 25 MB — in `<tenant>/runs/`, which is gitignored. The realistic
figure is two orders of magnitude below it, and a suite that reaches the ceiling
is telling you something about its target.

### 4. It never travels, and no `Disclosure` releases it

`redact()` drops every recorded response, unconditionally. `digline.wire` never
learns the field's name. There is no flag, no suite declaration and no MCP
parameter that changes either sentence.

This is the `base_url` treatment (ADR 0005 §2) rather than the artifact
treatment (ADR 0003 §4), and the argument is that the two absences are not the
same kind of thing:

- A **prompt** is the software house's own file, which is why opting it in is
  defensible — it merely *contains* the end company's rules, and the opt-in is
  one line that goes through a review.
- An **output** is the end company's data by construction. It is a reply about
  their input, produced for them, and nothing in a suite's review can make it
  the software house's to send.

And there is a shorter argument standing right beside it. `Verdict.reason` is
redacted **because the judge quotes the output**. A design that withheld the
quote while releasing the thing quoted from would not be a boundary.

What a redacted document keeps is the **count**, with `withheld=True` on each
entry: *this run recorded its answers and kept them back* and *this run recorded
none* are different facts and a reader is owed both — the same distinction
`Artifact.withheld` exists to carry. `Run.__post_init__`'s verified-rather-than-
believed check gains a clause: a run claiming `redacted` while carrying a
response text is refused, the way one carrying a live `reason` already is.

### 5. Promotion strips them

`promote_baseline` writes the run document verbatim today, and
`<tenant>/baselines/` is **committed**. With recording on, promoting would put
the model's answers into git, in the repository of a software house that may
hold no right to keep that end company's data — and it would do it as a side
effect of the most routine action in the product.

So promotion strips `responses` and keeps everything else. Nothing is lost: a
baseline is an approved reference of *verdicts*, and §6's replay reads a stored
**run**, never the baseline. The one committed artifact in this product stays
payload-free, which is the property that made committing it defensible in the
first place.

### 6. `digline rejudge`: the honest answer to the cache

    digline rejudge --suite eval/suite.py --run 2026-09-11T09-14-…

It reads a stored run, replays its recorded answers through the **current**
suite's assertions, and writes a new run that says where the answers came from:

    Run.rejudged_from: str | None = None      the stored run's key

A replay target hands back, per case, the recorded responses in the order they
were produced; the driver is otherwise the driver. What is fresh and what is
carried through is decided by what actually happened:

| field | value | why |
|---|---|---|
| `judge_config` | measured now | the judge really ran; it is the thing under examination |
| `target_config` | copied from the source run | it describes the system that produced these answers, and nothing else does |
| `artifacts` | copied from the source run | the prompt that produced these answers, not the one on disk today |
| `created_at`, `git_commit`, `digline_version` | fresh | this evaluation happened now |
| `config_hash` | the current suite's | the point of the exercise is that the rules moved |
| `rejudged_from` | the source key | the declaration, and §7 is what it is for |

Four refusals, each naming what is missing:

1. The source run recorded no responses — the opt-in was off. Refused, naming
   the flag.
2. `Suite.samples` does not equal the recorded count for a case. A replay at
   three over five recorded answers is a different measurement wearing the
   suite's name.
3. Any response is `withheld` or `oversize`. A partial replay is a weaker
   measurement claiming to be the declared one — the same rule the driver
   already applies when one call of a sampled case fails.
4. The source run belongs to another tenant. The perimeter refuses before
   anything else does, as everywhere.

`rejudge` writes a run and does not gate; `compare` gates. That is ADR 0008 §2's
division and it is unchanged by a second way of producing a run. `CallPlan`'s
sentence tells the truth about what it will cost: **no calls to the target**, and
the judge repeats it already knows how to count.

### 7. A replay is not promotable

`promote_baseline` refuses a run that declares `rejudged_from`.

Not for tidiness. A replay has **zero target variance** by construction: the
answers are fixed, so the noise interval it records is the judge's wobble alone.
Promoted, it would become the baseline against which future *real* runs are
measured, and ADR 0006 §5 says the interval a movement is judged against is the
baseline's — so every ordinary wobble of the target would then read as a
movement beyond the noise. A replay promoted as a reference is a noise floor
measured without the noise.

It is the fourth condition on promotion and it sits with the other three
(ADR 0002 §8): the configuration must match, the run must have judged every
case, the tenant must be the perimeter — and the answers must have been
measured.

### 8. What the reader sees

A replay compared against a baseline is legitimate and is in fact the reason the
command exists: change the judge, hold the answers still, see what moved. A
reader who is not told that the answers were held still would draw a conclusion
about a model that was never asked anything. So:

- **`Headline` gains `rejudged: bool`** and a clause in the sentence, in both
  locales, placed immediately before the target-configuration clause: the
  numbers are qualified before the system that produced them is described. The
  target clause still prints — it is still true of the answers being judged.
- **`explain` gains one `TallyKind`, `rejudged`.** That list is closed by
  ADR 0012 §3, so this is an amendment and is declared as one in the header. It
  earns the ninth member by the same test §3 sets: it says something the report
  says, and a reading that omitted it would describe a measurement where there
  was a replay.
- **The run page and the comparison's meta line name the source key**, so the
  document leads back to the run the answers came from.
- **Where the recorded answers themselves are shown**: `digline view`, which is
  local and inside the perimeter, and the run detail of a **non-redacted**
  report. A redacted document has nothing to show by §4, so the rule needs no
  flag — it falls out of the redaction.

No seventh MCP tool. ADR 0011 §1 adds a tool when something needs one, and the
wire gains fields here, not a surface.

### 9. Compatibility

`SCHEMA_VERSION` 9 → 10, as one passenger of the bump ADR 0014 governs.
Migration sets `responses` absent and `rejudged_from` null; nothing is invented
and nothing is refused. No baseline needs re-promoting, because none of this
touches `config_hash` (§2).

`OUTPUT_VERSION` stays at `1`. `rejudged` and the source key are added keys on
an existing document and `rejudge --json` is a new command's shape — both under
the rule ADR 0008 §7 and ADR 0012 §8 already wrote.

A suite that never sets `record_responses` produces a run file byte for byte the
one it produces today, plus the version header. That is the same promise
ADR 0006 made for `samples=1`, and it is the promise that makes a default-off
feature honest.

## Consequences

**The product gains an answer to a question it used to answer with money.**
"What would this run score under a different judge" cost a full re-run of the
target; it now costs the judge calls and declares itself.

**The most sensitive field in the system now exists, and every boundary in the
codebase had to be asked about it.** That is the real cost of this ADR and it is
paid in tests, not in prose: the boundary suite plants an output in a fixture and
asserts it cannot be constructed into anything that leaves.

**Somebody will ask for a `Disclosure(outputs=True)`.** The answer is in §4 and
it is no. The request will be reasonable — an end company asking for its own data
back is entitled to it — and the route for that is the perimeter it already owns,
not a flag that makes every other suite's outputs one line from travelling.

**A replay that cannot be promoted will surprise someone.** It should: the
surprise is the instrument refusing to let a measurement of the judge become the
reference for the target.

**Run directories get bigger for suites that opt in.** They are gitignored and
`digline list` already reports what it holds; a retention rule for the run
directory is not invented here, and §"Not decided here" says so.

## Alternatives considered

**A response cache, like the field's.** Rejected in the Context, and it is the
alternative this record is written against: a cache returns an old answer as if
it were new, which is a green run nobody measured and a store of payload nobody
declared.

**Record by default, redact at the boundary.** Rejected. The boundary would
hold — §4 is a property of `redact()` and of `wire/`, not of a flag — but the
*store* would fill with payload on every run of every suite, in every repository
that upgraded, without anybody choosing it. Fixed decision 5's spirit is that
nothing about a user's data happens because they did not opt out.

**Record only the failing cases.** Rejected: which cases failed is a verdict, and
a recording that depends on the verdict cannot be used to re-judge the verdict.
It also produces the one corpus nobody wants to hold — every bad answer, none of
the good ones.

**Truncate at a ceiling instead of refusing.** Rejected in §3. A clipped answer
re-judged is a plausible number measured on evidence the document does not admit
is partial.

**Keep the answers in the promoted baseline.** Rejected in §5: it puts payload
into git as a side effect of the most routine action in the product.

**`rejudge` as a flag on `run`.** Rejected for the reason `diff` is not a flag on
`compare` (ADR 0008 §2): the two produce different kinds of run — one measured,
one replayed — and a user must never have to remember which mode they selected.

**Letting a replay be promoted with a warning.** Rejected in §7. A warning is
what a reader skips; the floor it would freeze is what every future comparison
reads.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The boundary, planted.** `tests/test_wire_boundary.py`'s marker suite gains an
output marker: a recorded response whose text is a unique token. The assertion is
that the token appears in the run file written inside the perimeter and in
**nothing** produced by `redact()`, `run_to_json(..., redacted=True)`,
`run_document`, `compare_json`, `delta_json`, `explain_json`, or the rendered
report of a redacted run.

**Promotion strips, and promotion refuses.** A run with responses promotes and
the baseline on disk is asserted to carry none; a run with `rejudged_from`
refuses promotion with the sentence naming why.

**The replay is the same measurement.** A suite run against a stubbed target with
`record_responses=True`, then re-judged with the same assertions, produces the
same scores case for case — the test that proves the replay is faithful rather
than approximately faithful. Then the same replay with a changed threshold
produces the expected flip, which is the feature.

**The four refusals**, one test each, asserted on the sentence: no responses, a
sample-count mismatch, a withheld or oversize response, a foreign tenant.

**Oversize records nothing.** A response one character over the ceiling records
neither field and sets the flag; the re-judge that meets it refuses.

**The default is byte-identical.** A suite without the flag produces a run file
identical to the one the previous release produced, modulo `schema_version` and
`digline_version` — asserted on the bytes, as ADR 0006 §11's test does.

**Both locales.** The `rejudged` clause exists in `en` and `it`, and the
no-advice gate of ADR 0012 §5 runs over the new strings like every other.

## Not decided here

**Capture — turning an application's own traffic into cases.** Adjacent, and it
consumes the app's log rather than a recorded response. It gets its own record:
a future traffic-to-case ADR, unnumbered here because nothing should reserve a
number it has not earned.

**Retention for the run directory.** Recording makes run files larger and the
question of how many a store should keep is now worth asking. It is a store
decision, not a schema one, and it does not ride this bump.

**Re-judging across suites** — replaying run A's answers through suite B's
assertions where B is not the suite that produced it. `rejudge` uses the current
suite by design, and the cross form raises a pairing question (`case_id`s that
may not exist on both sides) that deserves its own answer rather than a flag.

**An MCP `rejudge` tool.** Waiting for something to need it, per ADR 0011 §1.
