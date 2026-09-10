# ADR 0005 — The configuration of the system under test

- Status: accepted
- Date: 2026-08-31
- Amended: 2026-09-01 — §8, HTTP targets. Added rather than a new ADR: it
  changes no decision above it, and reads as a correction to §6's aside about
  `HttpTarget` having no model
- Amended: 2026-09-10 — §9, the observed identity. Same test as §8: it widens
  §1 and §6 and overturns nothing. §3 above all is untouched, and that is what
  makes it an amendment rather than a new ADR — this is the record, never the
  hash
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

### 8. HTTP targets: the configuration arrives in the answer

*Addendum, 2026-09-01. §6 settled that a target which declares nothing records
nothing, and named `HttpTarget` as the case — "an application that has no model
at all". That was wrong about the ordinary case. The application behind the
endpoint usually does have a model; what it has is no way to say so.*

The Java path (`examples/langchain4j/`) is `HttpTarget` against a service
digline cannot import, and it loses precisely what §1 was written to record.
The prompt is covered — ADR 0003 carries it as an artifact, because the file
sits in the repository the suite sits in — but the model, the temperature and
the token cap are chosen on the other side of HTTP and are invisible. A team
that switches their LangChain4j app from one model to another gets a run that
compares clean on the configuration and says nothing, which is the sentence §5
exists to make impossible.

**So `HttpTarget` gains `config_path`, symmetric with `cost_path`.** It names a
JSON object in the response, and the target implements `HasConfig` from it:

```python
HttpTarget(
    url,
    request=...,
    output_path="data",
    cost_path="usage.cost_usd",
    config_path="config",
)
```

```json
{"data": "...",
 "usage": {"cost_usd": 0.0009, "elapsed_ms": 41.0},
 "config": {"provider": "openai", "model": "gpt-4o-mini",
            "temperature": 0.0, "max_tokens": 512}}
```

Cost is the precedent and the argument: when the model call happens elsewhere,
the only party who can price it is the one who made it, so digline reads a
number the application computed rather than pretending to know. The
configuration is the same fact one field over. Nothing about the mechanism is
new — a dotted path, a value read out of the answer.

**Absent `config_path`, absent configuration.** The parameter is optional, the
recorded object is empty, and §6 holds unchanged: absent is not a change. No
existing suite behaves differently.

#### The contract is enforced here, not followed

Every other `config` in this repository is written by a plugin, in Python, and
reviewed as code. This one is written by an application nobody here reviews, so
the rules of §1 and §2 stop being conventions the author follows and become
checks the reader performs. Five, and each refuses rather than repairs:

- **The closed key table of §1 and nothing else.** An unknown key is refused by
  name, with the allowed set in the message. Not dropped: silently discarding a
  field is how a team believes they recorded something they did not. This is
  §1's `additional_request_fields` argument arriving from the other direction —
  an open mapping of unknown keys is exactly where an account identifier or a
  customer's own tuning would sit, and here it would arrive over the wire.
- **Scalars only**, the same check `SystemConfig` already makes, made earlier so
  the message names the path in the answer rather than the field in the record.
- **`null` means not sent**, exactly as `sent()` reads an unset parameter: the
  key is absent, and the provider's own default applied.
- **`base_url` is reduced to host and port here**, not trusted. A plugin passes
  a URL it constructed; an application reporting its own endpoint is far more
  likely to send the whole thing, userinfo included, and ADR 0004 §5 makes a
  credential the one category no `Disclosure` can release. Under redaction it
  then gets the treatment of §2 unchanged — withheld, not dropped, `unknown`
  rather than `same` — because by then it is an ordinary `base_url` and
  `PERIMETER_FIELDS` does not care where it came from.
- **A configuration that cannot say who answered is refused**, per §1: no
  `provider`, no `model`, no record. Report the object completely or leave it
  out.

#### One run measures one system

A plugin is constructed once and answers the same way all run. An endpoint can
answer case 1 on one model and case 7 on another, and §6 has no reading under
which that is one configuration. Merging would describe a set-up nobody built;
recording the first silently would report a system that was not the one
measured throughout.

So **the first configuration reported is the run's, and a later answer that
disagrees errors its own case**, naming the field and both values. The run is
still written, the deltas are still there, and the case that broke the premise
is visible as an error rather than absorbed. A team that wants to compare two
set-ups runs two runs, which is what §6 already says a matrix is.

#### `target_config` is asked twice

The driver read the target's configuration before the first case, so that a
malformed one failed before the suite was paid for. An `HttpTarget` has nothing
to declare at that point — it learns by answering. `execute()` therefore asks
before the first case **and** after the last, and records the second answer. A
target that declares statically gives the same answer both times, so nothing
about a plugin's behaviour moves; what the early call still buys is the early
failure it was added for.

#### What this does not do

It does not make the reported configuration *true*. An application can report a
model it did not call, and digline has no way to know — it has no way to know
what a plugin sends either, and the recorded value is a declaration in both
cases. What changes is that there is now something to declare, and that a
change in it becomes the named delta of §3 and the coinciding sentence of §5
for a team whose application is not Python.

It does not touch `config_hash`: §3 holds, and two runs of one suite against two
models stay comparable and promotable.

It does not extend to the judge. A suite whose target is an `HttpTarget` grades
with whatever `Judge` it holds, on this side, and `judge_config` collects it
unchanged. An application that judges its own output is not a judge digline can
record, and nothing here pretends otherwise.

### 9. What the provider said answered

*Amendment, 2026-09-10. Widens §1 and §6. §2, §3, §4, §5, §7 and §8 hold, and
§3 above all: what follows is recorded beside `config_hash` and never inside
it, so two runs across a model rotation stay comparable and promotable.*

§1 records what the target **sent**. `model="claude-sonnet-5"` is an alias, and
an alias is a promise about a family, not a name of a system: the provider
decides which snapshot behind it answers, and rolls that decision on its own
schedule without anyone touching the suite, the prompt or the parameters.

So the run records `claude-sonnet-5` on Monday and `claude-sonnet-5` on Friday,
`compare()` reports the configuration as unchanged, and a drop between the two
sends a reviewer to the prompt. This is §Context's first consequence — *the
report can say something true that reads as false* — one level down and harder
to see, because here the sentence is not merely narrow, it is the sentence a
reader would have written themselves from the same evidence.

**The record admits what the provider observed, beside what the target sent.**

| | |
|---|---|
| `resolved_model` | the model id the provider said answered |
| `fingerprint` | the backend build, where a provider names one |

Two rows added to §1's closed table, and nothing removed from it. They arrive
through the reply, on the record ADR 0004 §6 widened `_complete` to return;
they are that amendment's passengers, and this section is where they are
unloaded.

#### Observed is not sent, and absence means something else

§1's rule is `sent()`: an unset parameter is **absent**, because *"we did not
send it, the provider's own default applied"* is a different fact from *"we
sent nothing for it"*, and only absence states the first one honestly.

An observed field is absent for a different reason: **the provider did not
say.** Both are honest absences and both stay absent — no `None`, no
placeholder — but they are not the same fact, and one of the two is the whole
answer for one of the three plugins. `sent()` therefore gains a sibling and not
a flag, so that a plugin author reading either name knows which category they
are in.

The third column is the argument for keeping the distinction visible:

| | Anthropic | OpenAI | Bedrock Converse |
|---|---|---|---|
| resolved model in the reply | `message.model` | `completion.model` | **nothing** |
| backend build | — | `system_fingerprint` | **nothing** |

Converse returns `output`, `stopReason`, `usage`, `metrics`,
`additionalModelResponseFields`, `trace`, `performanceConfig` and
`serviceTier`. There is no model id anywhere in it: the caller passed a
`modelId` and the API does not echo one back, resolved or otherwise. So on
Bedrock — where an **inference profile** is precisely a name that stands for a
model chosen elsewhere, and where the gap is therefore widest — the record
degrades to nothing stated, and nothing stated is what it records. **We do not
fill the gap from the request.** Copying the requested `modelId` into
`resolved_model` would manufacture the one fact this section exists to obtain,
and it would manufacture it identically whether or not the profile had moved.

**How strong the signal actually is has to be measured, not assumed.** Whether
a given API echoes the alias back or resolves it to a snapshot is that API's
behaviour on the day, and this repository already has the precedent and the
machinery for finding out: `CACHE_READS_ARE_INSIDE_INPUT_TOKENS` is a constant
that exists because the cache-token convention was *measured* against the API
rather than inferred from the field names (friction 25), and it is re-measured
by a `@pytest.mark.live` test that fails loudly if the answer changes. The two
first-party plugins that can report an identity carry the same obligation: a
live test that asserts the reply's model id against the alias that was sent,
and says which it got. If an API turns out to echo the alias, `resolved_model`
equals `model`, the delta stays silent, and the record has cost a field and
told no lie.

#### The perimeter rule, by type — and one field joins `PERIMETER_FIELDS`

§2's test is what the value describes.

**`resolved_model` is a public product name and travels in clear**, exactly as
`model` does. `claude-sonnet-5-20260115` carries nobody's data; it is a
measurement of the system, which is what fixed decision 9 lets cross.

**`fingerprint` is withheld under redaction**, and this is the one genuinely
new ruling here. On the official endpoint it is an opaque backend id and
harmless. But `base_url` makes one plugin cover every OpenAI-compatible server,
and on a customer's own vLLM or Ollama the value of `system_fingerprint` is
whatever *that server* chose to put there — a build path, a container tag, a
hostname. That is the argument §2 made for `base_url` word for word: it
describes the client's perimeter rather than the model, and it arrives from
software nobody here reviews.

So it gets §2's existing treatment and no new mechanism: it joins
`PERIMETER_FIELDS`, the value is discarded at a boundary, the key is recorded
as **withheld rather than dropped**, and a comparison across it answers
`unknown` rather than `same`. No new `Disclosure` member — the prudent default
of ADR 0003 §4 is the answer here too, and an opt-in nobody has asked for is a
widening nobody reviewed.

The cost is stated rather than hidden: world 3 loses an opaque string that told
them little on its own, and world 1 — the developer, who sees everything — keeps
it. That is the right side to lose it on.

#### Where it lands, and why no version moves

`Run.target_config.values`, beside the sent parameters, in the record and not
in the hash (§3, unchanged).

**`SCHEMA_VERSION` does not move, and this is by construction rather than by
luck.** `target_config` is serialised as an open mapping of scalars, so a new
key inside `values` is the same event as a plugin declaring a `top_p` it did
not declare before: no field is added to any document, no reader has to learn a
shape, and `digline migrate` has nothing to do. A baseline promoted before this
release needs no re-promotion. `OUTPUT_VERSION` does not move either, by its own
existing rule: `--json` gains keys and a consumer that does not read them is
unaffected.

The rendering is free for the same reason: `config_deltas` iterates over the
keys that are there, and `config_changes` prints field, before and after. The
sentence §5 exists for arrives with no new code —

> The system under test answered under a different configuration:
> resolved_model claude-sonnet-5-20260115 → claude-sonnet-5-20260301.

— and where a regression coincides with it, §5's *coincides* sentence names it
next to the regression. That is the whole feature: an alias that rolled under a
suite nobody edited is now a named delta a reviewer reads instead of a silence
they cannot see past.

#### One sentence has to change, because it says `sent`

Two of the phrases §5 introduced are written for parameters that are sent:

    config.change.new      {field} {after}, not sent for the reference
    config.change.missing  {field} {before}, no longer sent

Applied to an observed field they state something false. `resolved_model` was
never *sent* — not by this run and not by the reference — and a reference
promoted last month recorded no observed identity at all, so this is not a
corner case: it is what every first comparison against an existing baseline
will print.

So the observed fields are a named set in the same file that already holds
`PERIMETER_FIELDS`, and they get two phrases of their own in both locales —
*"not reported for the reference"*, *"no longer reported"*. **The existing
sentences are not reworded.** ADR 0005's own consequences noted the cost of
changing report text a pipeline may match on; that cost is worth paying to give
a word back (§5) and is not worth paying to avoid a second table entry.

#### The judge is asked once, and once is too early

§4 records the instrument, and the instrument has the *strongest* version of
this problem: when a judge's alias rolls, the scale moves under a suite nobody
edited, and §4's ruling is that a changed instrument makes the scores less
comparable **regardless of what the target did**. An alias rotation is that
event with nobody to notice it.

But `execute()` asks `judge_config(suite)` **before the first case**, where a
target's configuration is asked twice (§8) and a judge's is not. Before the
first case a judge has observed nothing, so the record would be empty by
construction.

**So the judge is asked twice too, on §8's pattern and for §8's reason.** Read
before the first case, so a malformed configuration still fails before the
suite is paid for, and read again after the last, and the second answer is the
one recorded. A judge that declares statically gives the same answer both
times, so nothing about any existing plugin, fake or suite moves.

One limitation, stated because §4 was written against exactly this shape: with
two judges on one alias whose observations disagree, §4's merge rule drops the
disagreeing scalar, so the record falls silent on the loudest possible event.
That is §4's rule applied honestly — *any scalar the judges disagree on is
absent rather than reconciled* — and the identity list still carries who
graded. Making a disagreeing observation louder than a silent one is a change
to §4's merge, and it needs a frictions entry before it needs a rule.

#### Rotation: §8's rule, extended, and split by field

§8 decided this event once already, for the target digline cannot import:

> A plugin is constructed once and answers the same way all run. An endpoint
> can answer case 1 on one model and case 7 on another, and §6 has no reading
> under which that is one configuration.

The premise's first half is now wrong. A plugin *is* constructed once, but what
it observes is not its own — a provider can roll a model between case 1 and
case N, and the plugin has no more control over that than an `HttpTarget` has
over the application behind it. **The event §8 governs has arrived on the side
§8 assumed was safe**, and two rules for one event is one too many.

So §8's rule is extended, and split, because the two new fields are not the
same kind of fact:

- **`resolved_model` — first wins, and a later disagreement errors its own
  case.** Word for word §8: the run is still written, the deltas are still
  there, and the case that broke the premise is visible as an error rather than
  absorbed. A model that changed under an alias mid-run is the system under
  test changing mid-measurement, which is the thing §8 refuses to average away,
  and a suite that wants to compare two systems runs two runs.
- **`fingerprint` — a later disagreement records nothing.** The field is absent
  from the run, under the observed-absence rule above: *the provider did not
  give one answer for this run*. It does **not** error the case. OpenAI
  documents `system_fingerprint` as changing whenever they change the backend
  configuration, so erroring on it would paint runs red for an event with no
  bearing on which model answered — the false red that teaches a team to stop
  reading the colour.

The asymmetry is not a softening of §8. It is §8's own question asked of each
field: *does a change here mean a different system was measured?* For a model
id it does. For a backend build it does not, and claiming it did would be the
manufactured fact this ADR spends its length refusing.

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
- An application digline cannot import can now be recorded as completely as a
  plugin, by reporting one object in its answer. The Java path stops being the
  one where a model change is invisible (§8).
- The configuration contract acquires an enforced form as well as a followed
  one. A field added to a plugin is a code review; the same field arriving over
  HTTP is refused until it is added to the table here (§8).
- Existing report text changed in both locales. A pipeline matching on the
  English sentence rather than on `--json` has to be updated; the JSON keys did
  not move.

- A baseline records not only which model was asked for but, where the provider
  says so, which one answered. An alias that rolled under a suite nobody edited
  becomes a named delta beside the score it coincides with, instead of a
  silence a reviewer has to already suspect.
- Nothing is re-promoted, nothing is migrated, and no version number moves. The
  record was already a record of scalars, so admitting two more is the same
  event as a plugin declaring a parameter it did not declare before.
- Bedrock is honest about having nothing to say, and stays that way. The one
  provider where an inference profile makes the gap widest is the one that
  cannot close it, and the record says so rather than echoing the request back.
- `fingerprint` is the second field redaction keeps back, joining `base_url` for
  the same reason: on a custom endpoint its value is written by software nobody
  here reviews.
- The judge's configuration is read after the run as well as before it. No
  existing plugin, fake or suite behaves differently, and a judge whose alias
  rolls stops being the one instrument change §4 could not see.
- `digline-anthropic` and `digline-openai` gain a live test each whose job is to
  keep this section honest about how strong the signal is. If an API starts
  echoing the alias, the test says so before a reader has to infer it from a
  delta that never fires.

## Not decided here

**Whether a rotated `resolved_model` should also fail the run**, as opposed to
erroring the cases that observed the second one. It errors today, which is
§8's answer, and §8's answer is enough until somebody's run says otherwise.

**Recording the observed identity per case rather than per run.** It is the
shape that would describe a rotation completely — every case says who answered
it — and it is a `CaseResult` field, which is a `SCHEMA_VERSION` bump and a
migration for a fact nothing reads yet. The run-level record plus an errored
case says the same thing in the cases that matter, at no cost to any document.

**A `resolved_model` for `HttpTarget`.** §8's closed key table refuses what it
does not know, so an application cannot report one until the table says it may.
Adding it there is a line in `CONTRACT_FIELDS` and a line here, and it should
wait for an application that has one to report.

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
