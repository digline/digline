# ADR 0026 — The thinking a model charged for

- Status: accepted — the text first, the implementation written against it on
  `thinking-tokens`, the way
  [ADR 0025](0025-the-tokens-and-the-bill.md) and
  [ADR 0024](0024-the-judge-as-an-instrument.md) were
- Date: 2026-09-19
- Opens: **schema 15**, with one passenger. It does not wait for a second: the
  consumers are ready — two plugins to read the field and a third to declare it
  absent — so this is not ADR 0014 §3's field that drifts because nothing reads
  it. If a second passenger appears while this is being built it boards; if not,
  15 ships with one, as 14 did
- Assumes: [ADR 0025](0025-the-tokens-and-the-bill.md) (the document records
  what a run consumed, and `Usage` is the record of one call);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule);
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §6 (a plugin
  translates its provider's vocabulary and the core holds the record they fill)
- Touches: nothing in `CLAUDE.md`'s *fixed* section

## Context

A model that reasons before it answers spends most of its output budget on
tokens nobody reads. The bill counts them, because they are output tokens; the
answer does not contain them. A run that records `output_tokens: 8000` for a
reply of two sentences is telling the truth and telling it uselessly: the
question a reader has — *what did I pay for* — is answered by the split, and
the split is exactly what digline has been dropping.

**This was mistaken for shipped, and that is worth one sentence in the record.**
ADR 0025's reconnaissance proposed the field; 0.16.0 shipped `Usage` with
**four** counts and not five; and the gap was found by somebody sitting down to
write the plugin patch that would fill it. Nobody noticed in between because
every reading of `Usage` was written against the four that exist. It is recorded
here so the next reader learns what this record is for: **describing what
exists**, not what a previous record intended.

**Read from the SDKs rather than from memory**, on the versions this workspace
pins:

- `anthropic` **1.5.0** — `Usage.output_tokens_details: OutputTokensDetails |
  None`, and that type has exactly one field, `thinking_tokens: int`. The
  container is optional, so an older SDK, or a reply without it, gives `None`.
- `openai` **3.13.0** — `CompletionUsage.completion_tokens_details`, whose type
  carries **five** fields: `reasoning_tokens`, `audio_tokens`,
  `accepted_prediction_tokens`, `rejected_prediction_tokens`, `text_tokens`.
- `digline-bedrock` — Converse's `TokenUsage` has `inputTokens`,
  `outputTokens`, `cacheReadInputTokens` and `cacheWriteInputTokens`, and **no
  reasoning split at all**.

## Decision

### 1. One field, three states

`Usage.thinking_tokens: int | None = None`, beside the four that exist.

**`None` means *not reported*, and is never guessed as `0`.** The distinction is
not decoration: a provider that does not report the split, an SDK too old to
carry the field, and a model that did no thinking are three different facts, and
only the third is a zero. A `0` written where nothing was reported is a
measurement nobody made — the invention ADR 0014 §1's second condition refuses
and ADR 0025 §3 refused for `Run.usage` itself.

The three states, each a different sentence:

| value | what it says |
|---|---|
| `None` | the provider, or this SDK, did not report a split |
| `0` | it reported one, and this reply did no thinking |
| `n > 0` | it reported one, and `n` of the output tokens were thinking |

**The SDK floor is the case that makes this real, and it was measured rather
than assumed.** `digline-anthropic` runs against whatever `anthropic` the user
installed, and its declared floor is `anthropic>=0.40`. Installed and read on
2026-09-20: **`anthropic` 0.40.0's `Usage` has exactly two fields**,
`input_tokens` and `output_tokens`, and no `output_tokens_details` at all — so
`getattr` gives `None` and the document says *not reported*, which is true. The
workspace pins **1.5.0**, where the container exists and is `None` on a reply
that reports no split.

Both halves of *not reported* are therefore reachable by a supported install,
not hypothetical: the field missing from the SDK, and the field present and
empty. A plugin that wrote `0` for either would be reporting the absence of a
field as the absence of thinking.

### 2. It is a **breakdown**, not a new billable quantity — and this is the
### inverse of friction 25

The single most important line in this record, because the analogy nearest to
hand is the wrong one.

`cache_write_tokens` exists because a provider reported writes **outside**
`input_tokens`: a call showed `input_tokens=10` beside `cache_write=9202`, and
folding them in reported that call at a thousandth of its cost (friction 25).
The lesson was *a count outside the total must be added*.

`thinking_tokens` is the opposite shape. Both providers report it **inside** the
output count — Anthropic's thinking tokens are output tokens, OpenAI's reasoning
tokens are part of `completion_tokens` — so the money is already counted.
Adding them would bill every reasoning call **twice**, and the error would be in
the direction that looks like diligence.

So: **`Pricing.cost` does not change.** The field is recorded and never priced.
The way to tell the two cases apart is not analogy, it is the invariant below
and the provider's own documentation — and the reason this section exists is
that the next person to add a token field will reach for friction 25 first.

### 3. The invariant, asserted rather than trusted

**`thinking_tokens <= output_tokens`**, checked in `Usage.__post_init__` beside
the negative checks. A reply claiming more thinking than output is a **malformed
reply, refused by name** — not recorded, not clamped, not repaired.

Refused rather than clamped because the two failures a clamp hides are both
worse than an error: a provider whose accounting has drifted, and a plugin
reading the wrong field into the right one. Both are things somebody must be
told, and a silently corrected number tells nobody. It is the rule
`ClaimReply` already applies to `supported > total`, one layer down, and for the
same reason: two counts can be contradicted by arithmetic, so the arithmetic is
done.

#### The fold: `None` propagates

Two reported sides add. **Any unreported side makes the total unreported**, and
the justification belongs here rather than in the test that checks it: a total
that folded an unreported split into a reported one would report a number
**smaller than the truth**, in the good-news direction — the direction this
project has twice paid to stop reporting in (friction 25, and the undercount
B-1 closed). A run whose second call reported no split did not do less
thinking; it did an unknown amount, and the honest total of a known number and
an unknown one is unknown.

So `Usage(thinking_tokens=100) + Usage(thinking_tokens=None)` is `None`, and it
is the one place in this record where a reader might expect arithmetic and get a
refusal to do it.

#### The seed of a fold is not an unreported measurement

**Found while writing the tests for the rule above, and recorded because the
rule is what caused it.** Every total in digline is a fold that starts at
`NO_USAGE`, whose `thinking_tokens` is `None` — so under the rule as stated, the
seed unreported every split in the run, and a target that reported one on every
call produced a document saying *not reported*. The other four counts are zeros
and would never have noticed; this is the first field for which the identity
element of `Usage.__add__` is not an identity.

The distinction the fix rests on is the record's own: **a line that counted
nothing is not an unreported measurement, it is no measurement.** `None` on a
call that was made means *the provider said nothing*; `None` on an empty
accumulator means *there is nothing here yet*, and only the first is a fact to
propagate. So the neutrality is decided by `counted`, which is the honest
predicate — nothing counted, nothing to fold, take the other side whole — and
the three folds that build a bill each apply it: `CallTotals.plus` and
`CallTotals.__add__` in the core, and `JudgeBase._ask`'s accumulator, where the
first reply replaces the seed instead of adding to it.

**The subtraction that makes a judge's line this run's share** (ADR 0025 §4)
follows from the same sentence: an unreported `after` stays unreported, and a
`before` that reported nothing subtracts nothing rather than being read as a
zero.

### 4. The count is re-tokenised, and the record says so where it is read

Anthropic documents `thinking_tokens` as **re-tokenised and therefore
approximate**: it is not a byte-exact count of what the model emitted, it is a
count derived after the fact. That sentence belongs in the plugin, beside the
line that reads the field, and in `docs/api.md` beside the type — not only here,
because the person who needs it is reading a number in a document and wondering
why it does not add up exactly.

**What follows from approximate** is a thing this record must state so it is not
discovered as a bug: `thinking_tokens` may not reconcile to the digit with any
other count, and it is not a term in any arithmetic digline performs. It is
recorded, it is reported, and nothing is derived from it.

### 5. What each plugin does, and why one does nothing

- **`digline-anthropic`** reads `usage.output_tokens_details.thinking_tokens`,
  through the optional container, giving `None` where the container is absent.
- **`digline-openai`** reads `usage.completion_tokens_details.reasoning_tokens`,
  the same way.
- **`digline-bedrock` does nothing, and says so.** Converse reports no reasoning
  split, so this plugin can only ever record *not reported*. That is a
  **declared absence**: stated in its changelog without a version bump, because
  a no-op is not a release (there is nothing for a user to install), and an
  absence nobody wrote down is one the next reader has to rediscover by reading
  the provider's API.

**Only `reasoning_tokens`, of OpenAI's five.** The siblings answer different
questions: `audio_tokens` is a modality, `accepted_prediction_tokens` and
`rejected_prediction_tokens` are speculative-decoding accounting, `text_tokens`
is the complement of the modality split. None of them is *thinking the model was
charged for and the reader cannot see*, which is what this field is. They are
named here so that the next reader knows they were seen and left, rather than
missed.

### 6. The passenger rule (ADR 0014 §1)

| | 1 — the hash | 2 — the migration | 3 — the boundary |
|---|---|---|---|
| `Usage.thinking_tokens` | untouched. `config_hash` is the identity of the suite configuration; what a call consumed is the thing measured, never the ruler. `Usage` is not in `identity` either — it is on a recorded response and inside a total | the 14 → 15 step writes **nothing**. `None` is the only honest value: a call measured before this release may well have done thinking, and nothing in its document says how much. Absent means *not reported* in an old document and in a new one alike, which is `Run.usage`'s own argument one field down | it follows the grain ADR 0025 §8 ruled: inside `CallTotals.tokens` it is part of the run's total and **crosses**; inside `RecordedResponse.usage` it is a fact about one of the end company's requests and **does not**. No new rule, and no new mechanism — it rides the two containers that already answer this question |

**The step writing `0` would invent a measurement**, which is the whole of
condition 2, and the reason this passenger is cheap.

### 7. The old reader, and what does not move

A 0.16.x reader meeting a schema-15 document refuses it on the version, as it
refuses any newer schema in either direction. Ignoring the key, if it could,
would misread nothing: no verdict depends on it, no gate reads it, no
denominator moves. So the bump rests on the train alone — ADR 0018 §3.4's first
argument, as ADR 0025 §10 did, and for the same reason: a new field on a stored
document is never a patch.

`OUTPUT_VERSION` **stays at 2**. `_usage_document` gains a key, and an added key
breaks no consumer — the rule that contract has applied nine times.

### 8. What this does not do

- **No cost changes.** §2. The field is recorded and never priced.
- **No budget.** A ceiling on thinking would be a gate and needs a threshold,
  a tolerance and an exit code of its own; `CostBudget` already gates the number
  the money is written in.
- **No inference.** Where a provider reports no split, digline does not derive
  one from the answer's length or from anything else.
- **No plugin release for bedrock**, per §5.

## Test plan

Beyond a failing case for every rule, which the conventions require:

**The step invents nothing.** A schema-14 fixture migrates to 15 and is asserted
to carry `thinking_tokens is None` on every recorded response and in both totals
— and a document written fresh by a target whose provider reports no split is
asserted to be indistinguishable from it, because both are *not reported*.

**The three states are three.** `None`, `0` and `n` round-trip and compare
unequal, and `0` is asserted **present** in the document where it was reported —
a zero that was measured is a measurement and is not dropped as a default.

**The invariant refuses rather than clamps.** `Usage(output_tokens=2,
thinking_tokens=3)` raises, by name, and the message says which count exceeded
which. A clamped or repaired value is asserted **not** to occur.

**The same arithmetic inside the fold is an `assert`, and must stay one.** A
folded total cannot exceed its own output — both sides are bounded by theirs —
so there is no honest way for it to fire: `thinking > output` on one reply is a
malformed *reply* and naming the refusal names the provider's fault, while a
total that broke the bound could only be this fold's arithmetic, our fault, the
family B-1's finite guard belongs to. Promoting it to a named refusal would
dress our own bug as a hostile input, so the test states it as a property and
the code asserts it.

**The sum keeps the state**, per §3: two reported sides add, and any unreported
side makes the total unreported. Asserted in both directions, because a fold
that silently treated `None` as `0` is the good-news undercount and would look
identical from the total alone.

**A reported split survives every fold that builds a bill** — the failing case
§3's last part was written from. A target reporting the split on every call, a
judge doing the same, and a judge reused across two runs: each asserted to carry
a number rather than the `None` the seed would have produced. It is the one test
here that fails loudly on a defect nobody would have seen in a document, because
*not reported* is a plausible thing for a document to say.

**The boundary, both halves.** The per-response count does not survive
`redact()` or `without_responses`, and the total does — the same assertion ADR
0025's tests make, extended to the fifth field so the asymmetry is not proved
only for four.

**Each plugin reads its own field, and the floor.** A fake reply carrying the
split records it; a fake reply whose container is absent records `None`; and for
`digline-anthropic`, a fake SDK object without `output_tokens_details` at all —
the old-SDK case — records `None` rather than raising.

**Bedrock records `None` and is not bumped.** Asserted on its own reply shape,
so the declared absence has a test behind it.

## Not decided here

**A ceiling on thinking.** §8.

**Whether the other four `completion_tokens_details` fields are ever recorded.**
§5 names them and leaves them. The first suite that needs to tell an audio call
from a text one can bring its own record.

**Whether `thinking_tokens` should reach the report.** It is in the document and
on the wire; whether the HTML document for world 3 shows it is the same question
ADR 0025 §9 answered *no* to for the bill, and it waits for the same reason: a
recipient who is owed a verdict is not owed an accounting breakdown.
