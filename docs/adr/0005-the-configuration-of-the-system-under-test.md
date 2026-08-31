# ADR 0005 — The configuration of the system under test

- Status: accepted
- Date: 2026-08-31
- Supersedes: the *proposed — open question* draft of 2026-08-28, whose five
  open points are the five sections below
- Assumes: [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §3
  (what is under test does not enter `config_hash`) and §4–5 (withheld rather
  than absent, `unknown` rather than a guess),
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §1 (a plugin ships a
  target *and* a judge) and §5 (a credential never appears anywhere),
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the payload
  stays where it is born)
- Touches: fixed decision 9 (`CLAUDE.md`), which lists what crosses a boundary

## Context

A run records the verdicts, the fingerprint of the configuration that judges
them, and — since ADR 0003 — the files under test. It does **not** record which
model answered, at what temperature, under what token cap, in which region or
against which endpoint.

`config_hash` is built from the assertions, their thresholds and tolerances,
`samples` and the aggregates. Nothing the target does reaches it.
`Response.metadata` carries the model and the token counts to the assertions,
and `CaseResult` keeps only `case_id`, `verdicts` and `suspended` — so none of
it is persisted either.

Three consequences, and they are not equally serious.

**The report can say something true that reads as false.** Two runs that differ
only in temperature produce the same `config_hash`, and `compare()` reports
*"The configuration is the same as the reference."* Under the current definition
of "configuration" that sentence is exact: the rules that judge did not move. To
a reader in world 3 it says something else, namely that nothing about the system
moved. The word is doing two jobs.

**A baseline cannot say what produced it.** ADR 0003 closed this for the prompt
and left it open for everything around the prompt. A run from a dirty tree at
`temperature=0.7` and one at `temperature=0.3` are the same document.

**The gap is invisible.** Nothing warns; the numbers simply mean less than they
look like they mean. `digline-bedrock` documented it on the argument itself,
which is a patch on one plugin's docstring, not a decision.

This is deliberately **not** a case for folding these values into
`config_hash`. ADR 0003 §3 decided that a change to the system under test must
leave two runs *comparable* — that comparison, old against new with the score
deltas beside it, is the experiment digline exists for. Fingerprinting the
decoding parameters would make every such experiment un-promotable.

## Decision

### 1. What "the configuration" is, and what it is not

**The configuration of the system under test is the set of parameters that
decide how the model answers, declared by the target itself.** Named, closed,
and small:

| | |
|---|---|
| `provider` | which plugin answered — always present |
| `model` | the model id, or the inference profile id — always present |
| `max_tokens` | the output cap |
| `temperature` | where set |
| `top_p`, `top_k` | where set, on a provider that names them |
| `seed` | where the provider exposes one |
| `region` | Bedrock: what was called is what was priced |
| `base_url` | the **host** of a custom OpenAI-compatible endpoint |
| `response_format`, `json_mode` | the **shape** the answer was asked for, where the provider takes one |

The last row is not a decoding parameter, and it is here for the same reason
the others are: asking for a JSON object changes what comes back, so a
regression can coincide with it. It is recorded reduced to a scalar — the
`type` of the request, `json_mode` as the boolean it already is — because a
`json_schema` carries a whole schema, and a schema is structure rather than a
value to diff.

Each plugin declares exactly what it actually sends. Nothing is invented: a
provider without a `seed` records no `seed`, and a parameter left unset is
**absent**, not `None` — "we did not send it, the provider's own default
applied" is a different fact from "we sent nothing for it", and only absence
says the first one honestly.

`base_url` records the host and port, never the scheme, never the path and
never the userinfo: a URL is one of the places a credential is written by
accident, and ADR 0004 §5 makes a credential the one category with no
`Disclosure` that can release it.

**`additional_request_fields` and `extra_body` stay out.** They are the escape
hatch — whatever Converse or a compatible endpoint takes and the plugin's own
signature does not name. ADR 0004 already keeps them out of `config_hash`, and
the end-to-end test in each plugin pins that; this ADR adds its sibling and
leaves them out of the recorded configuration for the same reason. **What is
outside the contract is outside the record.** A mapping of unknown keys with
unknown values cannot be diffed into a sentence a reader can act on, and it is
exactly where an account-specific identifier or a customer's own tuning would
sit — the argument of §2, in the box where it cannot be checked. A suite that
needs those values to show keeps them in a file and declares it in
`Suite.artifacts`, where ADR 0003 already carries them into the run and into
the diff.

### 2. The perimeter rule, by type: one special field, one existing rule

**A model id and a number carry nobody's data, and travel in clear.**
`claude-sonnet-5`, `0.7`, `1024`, `eu-west-1` are public product names and
decoding parameters. They are measurements of the system, which is precisely
what decision 9 lets cross a boundary. Withholding them would cost the whole
feature and protect nothing.

**`base_url` is the one field that describes the client's perimeter.**
`https://llm-gw.internal.acme-bank.it/v1` is topology: it names an internal
gateway, and often the customer. So under redaction it gets **exactly the ADR
0003 artifact treatment** — the value is discarded, the key is recorded as
withheld rather than dropped, and a comparison across it reports `unknown`
rather than `same`. One special field, one existing rule, no new mechanism: in
particular no new `Disclosure` member, because the prudent default of ADR 0003
§4 is the answer here too and an opt-in nobody has asked for is a widening
nobody reviewed.

`unknown` and not `same` is the same choice ADR 0003 §5 made and for the same
cause: with no value on one side, `same` would be a guess wearing the clothes
of a finding.

### 3. Where it lands: `target_config`, beside the hash and not inside it

`Run.target_config`, a `SystemConfig` — a flat mapping of scalars plus the set
of keys withheld — recorded in every run, and in the baseline at promote time
because a baseline *is* a promoted run file.

It is **not** folded into `config_hash`, and that is the point of the ADR
rather than a detail of it. `config_hash` is the identity of the *suite*: the
rules that judge. This is the identity of the *system*: the thing judged. Two
runs at two temperatures must stay comparable and promotable, exactly as two
runs of two prompts do (ADR 0003 §3).

And the feature is the **named delta**. An opaque hash difference is what this
ADR exists to replace: "the configuration differs" sends a reader to reconstruct
what differed, while `temperature 0.3 → 0.7` is a sentence they can act on.

`SCHEMA_VERSION` goes to 8, additively, and is migrated in place like 6 → 7:
a run written before this ADR recorded no configuration, which is exactly what
an empty one says.

### 4. The judge is recorded too, and its change is louder

`Run.judge_config`, same shape, collected from the judges the suite's
assertions hold.

A judge is not part of the system under test — it is the **measuring
instrument**. When the target moves, the thing being measured moved and the
scores are a finding. When the *judge* moves, the scale itself moved, and the
scores are not comparable with the baseline **regardless of what the target
did**: a rubric graded by one model and then by another is two measurements of
one output by two instruments nobody calibrated against each other. That is a
stronger statement than a target change and the report makes it as one —
"reduced comparability", not "here is what changed".

Collected rather than declared, because a judge is bound where it is used: the
target is one object passed to `execute()`, while a judge is a field of the
assertion that asks it (§6). A suite may therefore hold several, and the record
is in two halves that answer two questions.

**Which instruments graded is always recorded**, as the set of distinct
`provider/model` identities bound in the run, however many there are. This is
the half that cannot be allowed to fall silent. The first shape of this decision
recorded nothing at all once two judges disagreed on their identity — and a
suite grading with two instruments that replaces one of them is *precisely* the
event this section exists to catch, so the record went blind exactly where it
was most needed. A rule that holds for one judge and abandons the case for two
is not a rule.

**How it was set up is recorded only when there is one of them.** With a single
identity the scalars are merged, and any scalar the judges disagree on is
absent rather than reconciled: a `ScoreJudge` capped at 400 tokens beside a
`ClaimCountJudge` capped at 800 is two set-ups, and writing one down would be a
fact nobody established. With two identities there is no single set-up at all —
inventing a merged `max_tokens` would describe a judge nobody built — and the
identity list carries the whole answer.

A judge added or removed is reported as **added or removed**, never as a value
that moved. `model a → b` is what replacing a lone judge looks like and it stops
being true the moment a suite grades with three; one identity gone and one
arrived stays true at every count.

### 5. What the reader sees

`compare()` **reports and never fails.** Two headline facts, on the pattern
`artifacts_changed` already set:

- `target_config_changed`, with the named deltas — field, before, after;
- `judge_config_changed`, reported more strongly, flagging the comparison as
  of **reduced comparability**.

A field withheld shows as withheld rather than absent, and a baseline that
recorded no configuration at all yields `unknown` for every field rather than a
column of fabricated `new`s (§7).

And the sentence this ADR exists for: **where a regression coincides with a
configuration delta, the report says so next to the regression** — *"this drop
coincides with temperature 0.3 → 0.7"*. Not a claim of cause: `coincides` is
the strongest word the data supports, and it is the word that makes a reviewer
check the config before blaming the prompt. Both facts render in the HTML
report in both locales, in the terminal summary, and in `--json`.

The configuration section sits **above** the score deltas, beside the artifact
diff, for the reason ADR 0003 §5 put it there: what changed comes before what
it did.

**And the word is given back.** With this ADR the report prints two sentences in
a row, and until they were read next to each other they both said
*configuration* while meaning different things:

> The configuration is the same as the reference. The system under test answered
> under a different configuration: temperature 0.3 → 0.7.

The first one is about the rules that judge, and the rules have a name of their
own — the **suite**. So it becomes *"The suite is unchanged from the
reference."*, in both locales and in the terminal, and *configuration* is left
to mean one thing: how the system under test was set up. The field names
(`config_hash`, `Comparison.config_changed`) do not move, because they are a
parsed contract and this was a reading problem; the view's `OLDER SUITE` marker
follows the copy, since it was the same word about the same fact.

### 6. Granularity: recorded where the thing is bound

A target is bound **once per run** — `execute(suite, target, …)` takes one, and
the `prompt × provider` matrix is a loop *above* the driver, one run per cell.
So one `target_config` per run, which is the same level `Run.artifacts` sits at
and the same level the question is asked at.

A judge is bound **per assertion**: `LlmRubric(judge=…)`, `Faithfulness(judge=…)`,
and a `Repeated` wrapping either. The driver walks the declared assertions,
follows a wrapper through to what it wraps, and records the identity of every
judge it finds — plus the merged set-up when they are all one instrument, which
is the ordinary case even with two of them, since ADR 0004 §1 makes `ScoreJudge`
and `ClaimCountJudge` two objects normally built against one model.

So `SystemConfig` carries `identities` beside `values`: the set of instruments,
and the settings of the one when there is one. On the target side it is empty —
a target is bound once per run, so the set could only ever hold a single element
and would repeat what `values` already says. A judge that declares no instrument
at all is passed over the way a plain-function target is.

**A target that declares nothing records nothing.** A `Target` is any callable
and most are plain functions; `HttpTarget` calls an application that has no
model at all. `config` is therefore an **optional protocol asked for**, the same
family as `Preflight` and `HasArtifacts` and asked for the same way — not a
mandatory member of `Target` or of `Judge`, which would break every function
target and every fake judge in every test suite, ours included. Absent stays
absent, and absent is not a change.

### 7. Compatibility: keys added, nothing re-promoted

`SCHEMA_VERSION` 7 → 8, additive, with its migration step. Old files stay
readable through `digline migrate`, and a **baseline promoted before this ADR
needs no re-promotion**: compared against a run that does record its
configuration, every field reports `unknown` — "this reference predates the
record" — rather than an error or a wall of `new`. Deltas appear from the first
pair of runs that both have one.

`OUTPUT_VERSION` follows its existing rule and does **not** move: `--json`
gains keys, and a consumer that does not read them is unaffected.

## Consequences

- A baseline is now self-contained evidence of the whole experiment: the
  verdicts, the rules that judged them, the prompt that produced them, and the
  system that answered.
- The sentence *"The configuration is the same as the reference"* stops being
  able to mislead — it is now *"The suite is unchanged from the reference"*,
  and the rules and the system are two facts with two names.
- A suite that grades with several judges is comparable on the thing that
  matters most about it: replacing one of two instruments is reported, and
  reported as the stronger fact.
- A software house can hand world 3 a report saying that a drop coincided with
  a model change without handing over the endpoint its customer's gateway sits
  on.
- Every plugin gains one property. The protocol did not gain a mandatory
  member, so nothing anyone has written stops satisfying `Target` or `Judge`.
- A run file grows by two small objects. A suite whose target declares nothing
  grows by `"target_config": {}`.
- Existing report text changed in both locales. A pipeline matching on the
  English sentence rather than on `--json` has to be updated; the JSON keys did
  not move.

## Not decided here

**`prefill`.** Anthropic's assistant-prefill is text put in the model's mouth,
so it is *prompt* — the thing under test rather than a parameter of the system
that answers it — and prompt is ADR 0003's subject: a suite that needs it
recorded declares the file it lives in as an artifact, and gets a diff rather
than a scalar. It is also, of the arguments in this family, the one most likely
to carry a customer's own phrasing.

**`token_param`.** It decides which argument carries the output cap —
`max_tokens` or `max_completion_tokens` — for endpoints that disagree about the
name. It is API plumbing: the cap it delivers is already recorded, and the model
answers the same way whichever spelling reached it.

Both are deliberate exclusions rather than open questions. Reversing either is
an edit to a plugin's `config` and a line here, not another ADR.

**A keyed digest for `base_url`**, which is the same question ADR 0003 left
open for artifacts and gets the same answer: revisit when the bridge exists and
there is somewhere for the key to live.

**Whether a judge change should be able to fail a run.** It reports today.
Making "reduced comparability" a gate would need a policy about who decides it
and where that policy is declared — a `Suite` field, presumably — and no
frictions log entry has asked for it yet.
