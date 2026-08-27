# Public API

Reference for what you need in order to write a suite. Everything below is
importable; anything not listed here is internal and may change.

## What is imported from where

Two packages, and the split is not arbitrary: `core` is the pure domain, with no
I/O and no dependency on the other layers; `run` is the driver that sets it in
motion.

| From `digline.core` | From `digline.run` |
|---|---|
| `Equals` `Contains` `Regex` `JsonSchema` `LlmRubric` `CostBudget` `LatencyBudget` | `Suite` |
| `AssertionBase` — for custom assertions | `Case` |
| `Repeated` `combine_samples` — sampling | `execute` |
| `Precision` `Recall` `Accuracy` `F1` — aggregates | |
| `TEXT_ONLY` `STRUCTURED_ONLY` `TEXT_OR_STRUCTURED` `TEXT_OR_CONVERSATION` `CONVERSATION_ONLY` `ALL_KINDS` | |
| `Judge` `JudgeReply` `ClaimJudge` `ClaimReply` — the judge protocols | `Target` `Response` |
| `ITALIAN_PII` `PiiPattern` `verify_iban` `verify_codice_fiscale` `verify_partita_iva` | |
| `Disclosure` — what may leave the perimeter | `Mapper` `default_mapper` |
| `Verdict` `Score` `Status` `Message` | |
| `Run` `CaseResult` `compare` `redact` `config_hash` | |

The report lives in `digline.report` (`headline`, `render_html`, `Locale`), the
store in `digline.store` (`FileResultStore`, `RunRef`).

A normal suite imports from both:

```python
from digline.core import Contains, CostBudget, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite
```

## The suite

### `Suite`

| Field | Type | Default |
|---|---|---|
| `tenant` | `str` | mandatory |
| `environment` | `str` | mandatory |
| `name` | `str` | mandatory |
| `assertions` | `Sequence[Assertion]` | mandatory |
| `cases` | `Sequence[Case]` | mandatory |
| `disclosure` | `Disclosure` | `Disclosure()` |
| `samples` | `int` | `1` |
| `min_agreement` | `Ratio \| None` | `None`, mandatory if `samples > 1` |
| `run_assertions` | `Sequence[RunAssertion]` | `()` |
| `artifacts` | `Sequence[Path]` | `()` |

`tenant` is the **perimeter**: one end customer, one project. It separates the
data on disk (`.digline/<tenant>/`) and `compare()` raises if two runs do not
share it. `environment` says *where inside that perimeter* — production,
staging, acceptance — and constrains nothing: comparing staging against the
production baseline is the pre-release check.

Neither has a default, and the CLI **verifies** them with `--tenant` / `--env`
without ever overwriting them.

Refused at construction: empty `assertions` (a run that checks nothing passes
vacuously), empty `cases`, two `Case`s with the same `id`.

`config_hash()` is the fingerprint of the configuration — assertions,
thresholds, tolerances — and not of the test data. It is what `promote`
compares.

### `Suite.artifacts`: the files that are the thing under test

The prompt is what is being evaluated, and until it is recorded a run cannot say
what produced it: while a prompt is being tuned the tree is dirty, every run
reads `-dirty`, and two runs of two different prompts are the same document.

```python
Suite(..., artifacts=[Path("prompts/system.md"), Path("prompts/rubric.md")])
```

Declared, never discovered — a file that counts as evidence is a file someone
named. Relative paths resolve against the suite's own directory. The **CLI**
reads them and hands the contents to `execute()`, exactly as it does for the
clock and for git, so the driver opens no files and stays testable without one.
A declared file that is missing is a usage error, not a run with no evidence.

They do **not** enter `config_hash`: changing a prompt has to leave the two runs
comparable, because that comparison — old prompt against new, score deltas
beside the text — is the experiment. A prompt change is a change to the
*system*, not to the rules that judge it.

Each one lands in `Run.artifacts` as an `Artifact`:

| Field | Type | Meaning |
|---|---|---|
| `sha` | `str` | SHA-256 of the bytes; `""` once withheld |
| `text` | `str \| None` | the content; `None` once withheld |
| `withheld` | `bool` | this suite chose not to send it |

`artifacts_sha(mapping)` digests the whole set into twelve characters — what
`digline view` labels a run with (`prompt a1b2c3`) so runs of one prompt group
at a glance.

**They do not travel by default.** `Disclosure(artifacts=True)` is the opt-in,
and it is one line in the suite, which goes through a review. A prompt is your
file and it is also where an end company's rules end up, and no default can tell
those apart by looking — so the rule from ADR 0002 §3 holds without an
exception: redacting without knowing the policy discloses *less*, never more.
Where both texts are present, `render_html` shows the **unified diff** of each
changed file above the score deltas, and `digline compare` prints the tally
(`prompt.md · +3 −1 lines`) between the headline and the regressions.

Redaction removes the text **and the digest**: a digest verifies a guessed
prompt, and prompts are guessable. What remains is the path and `withheld=true`,
so a redacted run compared on its own reports the artifact as `unknown` — it
cannot say whether the prompt moved, and does not pretend to.

`digline report --redacted` is the exception, and not by relaxing anything:
`withhold_artifacts(comparison)` is applied by the side holding both runs, so the
outcome is a fact that side established. The document then says *"1 file under
test changed"* and stops — no diff, no digest, no path.
`Disclosure(artifacts=True)` is what puts the diff back. Reasoning in
[ADR 0003](adr/0003-artifacts-travel-only-when-the-suite-says-so.md).

### `Case`

| Field | Type | Default |
|---|---|---|
| `id` | `str` | mandatory |
| `vars` | `Mapping[str, object]` | `{}` |
| `expected` | `Output \| None` | `None` |
| `context` | `Sequence[str]` | `()` |
| `metadata` | `Mapping[str, object]` | `{}` |
| `suspended` | `str \| None` | `None` |
| `label` | `"positive" \| "negative" \| None` | `None`, mandatory with an aggregate |

`id` is the key `compare()` pairs on: renaming it produces a `new` plus a
`missing`. Choose it stable and **with no production data inside**.

`suspended` sets the case aside with a mandatory reason: the driver does not run
it, the run records it, the report shows it. It is for when a case is unstable —
without it, the only remedy would be deleting the case, which is making the
inconvenient failure disappear. The reason is payload and gets redacted.

`metadata` never reaches `Score.metadata`: an assertion writes its own metadata
from what it measured, and a mapper has no route to get there.

## The target

### `Target`

A protocol: `__call__(case: Case) -> Response`. A function is enough.

It is **singular**: the prompt × provider matrix is a loop over several targets
*above* `execute`, not inside it. That is what lets the same driver work on a
single case.

### `Response`

| Field | Type | Default |
|---|---|---|
| `output` | `Output` | mandatory |
| `input` | `str \| None` | `None` |
| `cost_usd` | `float \| None` | `None` |
| `latency_ms` | `float \| None` | `None` |
| `metadata` | `Mapping[str, object]` | `{}` |

`input` is the rendered prompt. It lives here and not on the `Case` because
rendering happens inside the target: without it, `llm_rubric` would judge an
answer without knowing the question.

`Output` is a closed union: `str`, `Mapping[str, object]` (structured output,
tool call) or `Sequence[Message]` (a conversation). An empty sequence is an
empty conversation, not an error.

### `Mapper`

`__call__(response: Response, case: Case) -> EvaluatorInputs`. It is **the
boundary**: everything entering the core enters as `EvaluatorInputs`.
`default_mapper` does the obvious thing; if you write your own, it stays the
only road in.

## Targets

### `Target`

Any callable `(Case) -> Response`. Most are functions, and nothing below is
required to write one.

### `ProviderTarget`

`digline.targets` carries the half of a provider target that has nothing to do
with the provider: composing the prompt, timing the call, pricing the tokens,
building the `Response`. A plugin writes one method.

```python
from digline_anthropic import AnthropicTarget

target = AnthropicTarget(
    prompt_file=Path(__file__).parent / "prompts/answer.md",
    system_file=Path(__file__).parent / "prompts/system.md",
    model="claude-sonnet-5",
    max_tokens=1024,
    temperature=0.0,
)
```

Real providers live in separate packages — `pip install digline` must not pull
somebody's HTTP client along with it — and the layering gate enforces it in both
directions: nothing under `src/` may import a plugin, and `digline.targets` may
not import an SDK.

### `PromptTemplate`

A prompt file, its digest, and the variables it asks for. Read at construction,
so a path that does not exist fails when the suite is imported.

Substitution is a regex over `{identifier}` — **not** `str.format`. A real
prompt contains JSON, and `format` raises on `{"role": "user"}`; here every
other brace is left exactly as written.

Values render deterministically, because the same `vars` must give the same
prompt on the next machine: strings as they are, numbers and booleans through
`str()`, mappings and sequences as JSON with sorted keys and no spaces. Anything
else is refused by name — an object's `str()` may carry a memory address.

### `Pricing`

USD per million tokens, declared in code by the plugin and replaced by you in
one argument:

```python
AnthropicTarget(
    ...,
    pricing=ANTHROPIC_PRICING.override(
        "claude-sonnet-5", ModelPrice(input_per_mtok=2.5, output_per_mtok=12.0)
    ),
)
```

A price list is a fact about a day, and the plugin's carries the date it was
read. digline does not cut a release because a price moved.

**An unknown model raises**; so does a cached read the list cannot price. A
model priced at zero passes every `CostBudget` there is, quietly and in the
direction of good news, which is fixed decision 3.

### `HttpTarget`

For an application digline cannot import — a JVM service, a Go binary, anything
behind a gateway. It posts a body built from the case and reads the answer out
of the response by dotted path.

```python
from digline.targets import HttpTarget

target = HttpTarget(
    "http://localhost:8080/classify",
    request=lambda case: {"text": case.vars["text"]},
    output_path="data",
    cost_path="usage.cost_usd",
    latency_from_response="usage.elapsed_ms",
)
```

| Argument | |
|---|---|
| `url` | where to post |
| `request` | `(Case) -> Mapping`, the JSON body. A callable, not a template: a real payload has shapes a template cannot |
| `output_path` | dotted path to what the assertions judge |
| `cost_path` | dotted path to the cost, or `None` |
| `latency_from_response` | dotted path to the time the service reports. Left out, digline measures the round trip instead — which includes the network, and is a different number measuring a different thing |
| `headers`, `timeout` | as you would expect |

`preflight` asks whether **anything is listening** before the first case, so a
service that is down fails once with a sentence instead of once per case with a
stack trace. A `404` or a `405` counts as an answer: something is there and the
request was wrong, which is a different problem from nothing being there.

`urllib` only — digline has one runtime dependency and this is not where it
acquires a second. If you need retries, pooling or an auth flow, pass your own
callable: a target is any `(Case) -> Response`.

### What a target may also answer

Two optional protocols. A target that has the method is asked; a plain function
is left alone.

| Protocol | Asked by | For |
|---|---|---|
| `artifacts() -> Sequence[Path]` | the CLI, on `run` | merged into `Run.artifacts`, so `Suite(artifacts=…)` need not repeat a path the target already knows (ADR 0003) |
| `preflight(cases) -> None` | `execute()`, once, before the first call | raises naming **every** gap at once |

`ProviderTarget` implements both. `preflight` checks that each case provides
every variable its templates ask for, and that the model has a price — both are
cheaper to discover before the run than on case thirty-seven with thirty-six
paid calls behind it. It happens in the driver rather than in `Suite`, so a
script calling `execute()` directly is covered too, and so that a `Suite` stays
a declaration that knows nothing about how its outputs are produced.

## The assertions

Every assertion is an immutable dataclass and a pure function
`(EvaluatorInputs) -> Verdict`. They apply **to every case**: each one states
something that must hold for all of them.

| Assertion | Parameters | Threshold | Accepts |
|---|---|---|---|
| `Equals` | — (compares against `Case.expected`) | `1.0` | text, structured, conversation |
| `Contains` | `needle`, `case_sensitive=True` | `1.0` | text |
| `NotContains` | `needle`, `case_sensitive=True` | `1.0` | text |
| `Affix` | `affix`, `at="start"\|"end"`, `case_sensitive=True` | `1.0` | text |
| `Regex` | `pattern` | `1.0` | text |
| `Length` | `minimum`, `maximum`, `unit="characters"\|"words"` | `1.0` | text |
| `Levenshtein` | — (compares against `Case.expected`) | `0.9` | text |
| `IsJson` | `top_level="any"\|"object"\|"array"` | `1.0` | text |
| `JsonSchema` | `schema` | `1.0` | text, structured |
| `LlmRubric` | `rubric`, `judge`, **`threshold`**, **`tolerance`** | mandatory | text, conversation |
| `CostBudget` | `max_usd`, **`tolerance`** | `0.5` | all |
| `LatencyBudget` | `max_ms`, **`tolerance`** | `0.5` | all |
| `PiiAbsent` | `patterns=ITALIAN_PII` | `1.0` | text |
| `Faithfulness` | `judge` (`ClaimJudge`), **`threshold`**, **`tolerance`** | mandatory | text |
| `FromAutoevals` | `scorer`, **`threshold`**, **`tolerance`** | mandatory | text |

In bold what **has no default and must be declared**. `LlmRubric` because an LLM
judge is not reproducible; the budgets because cost and latency are noisy by
nature — tokens, retries, network — and an implicit tolerance of zero would turn
ordinary noise into a regression on every run.

All of them also accept `name` and `tolerance`. Changing `name` changes the
assertion's identity and produces `new` + `missing` in the comparison.

An `Output` branch that is not accepted produces **`error`**, never a silent
conversion: `Contains` on a dictionary does not stringify it to search inside.

None of these can be vacuously green, and construction refuses it:
`Contains("")` passes on everything, `NotContains("")` fails on everything,
`Affix("")` is true at both ends, `Length()` with no bounds passes on
everything. Those are four `ValueError`s when the suite loads, not four green
runs.

### `PiiAbsent`: the counts travel, the text found never does

Binary on purpose: "a bit of PII" is not a degree of quality, and a graded score
would invite a threshold meaning "some leakage is fine".

`Score.metadata` carries one entry for **every** declared pattern — including
the zeroes, because `pii_iban: 0` also says "we looked", and stable keys are
what lets a sampled run fold its metadata — plus `pii_total`. Neither the
`reason` nor the metadata ever carry what was found: it is payload, and it is
payload precisely *because* it is an identifier.

**The counts are not all equally certain**, and that has to be known when
reading them:

| Pattern | Check | How to read the count |
|---|---|---|
| `iban` | mod-97 (ISO 13616) | "I found one" |
| `codice_fiscale` | check character | "I found one" |
| `partita_iva` | Luhn | "I found one" |
| `email` | — | "worth a look" |
| `phone_it` | — | "worth a look" |

Without the checksum any eleven-digit sequence is a VAT number — an invoice
total in cents, an order reference, a timestamp — and an assertion that cries
wolf is an assertion that gets switched off. For email and phone no checksum
exists: they over-report by construction, and it is right that which two they
are should be known.

Spaces are tolerated **inside** the pattern, not stripped from the text:
stripping them would catch `IT60 X054 …` but would also weld neighbouring words
into identifiers nobody ever wrote.

Extensible by construction — `patterns` is a tuple:

```python
PiiAbsent(patterns=(*ITALIAN_PII, PiiPattern("badge", r"\bEMP-\d{5}\b")))
```

Text only: in a `structured` output, deciding which fields contain prose is a
decision, and taken silently it ends up scanning the keys instead of the values.

### `Faithfulness`: the judge decomposes, the core divides

`ClaimJudge` is a protocol separate from `Judge` because they answer different
questions: `Judge` returns a score it decided itself, `ClaimJudge` returns
**what it found** — `ClaimReply(supported, total, reason)` — and the core does
the division. A model asked for the fraction returns a number nobody can check;
two counts can be contradicted by arithmetic, and indeed `supported > total` is
refused at construction.

**Why the tolerance is mandatory.** `total` is decided by the judge, and two
judges on the same text count different claims: the same paragraph is three
claims for one and five for another, so **the denominator moves even when the
output does not**. This is a different noise from a judge scoring the same text
differently: it is structural, and no threshold absorbs it. The remedy is
`Suite.samples` with `Repeated` — several judgements on the same output, folded
by `min_agreement` before the verdict is settled. The tolerance covers the
oscillation that remains.

Empty `context` → **`error`**: faithfulness to nothing is the vacuously green
assertion. `total == 0` → **`error`** as well: an output that claims nothing has
no fraction to report, and calling it `1.0` would reward saying nothing.

Text only: in a conversation or in a `structured` output, deciding which part
holds the claims to check — the last turn? every assistant turn? which fields? —
is a real decision, and must not be taken silently.

### `FromAutoevals`: autoevals scorers as assertions

`Score` deliberately has the same shape as `autoevals.Score`, so adapting a
scorer costs a handful of lines and their taxonomy becomes compatibility instead
of work to redo. Nothing in `digline.core` imports `autoevals`: the protocol is
structural, and the core does not acquire a dependency for a shim.

One delicate point, and it is the constraint from ADR 0001: in autoevals
`score is None` means "skip". Here it becomes **`error` with a mandatory
reason**, never `pass`. A skip turning green would be a vacuously green
assertion dressed up as interoperability. A legitimate skip — "this assertion
does not apply to this case" — stays a decision of the driver, which simply does
not invoke it.

### Negations live in the assertion, not in the threshold

`NotContains` exists as a type rather than as a `Contains` with an inverted
threshold because a threshold reads as "how well": a suite writing "it must not
apologise" as `Contains("sorry", threshold=0.0)` would be green on every output,
apologies included.

### `IsJson` and `JsonSchema` are not the same question

`IsJson` accepts **text only**: a `structured` output is already decoded by
whoever produced it, so the check would always pass — vacuously green. And text
that cannot be decoded is **`fail`** here, not `error`: being decodable *is* the
question. In `JsonSchema` the same input is `error`, because there the question
was about the shape and could not be answered. An `error` is neither green nor a
regression: the distinction decides what CI does.

### `Levenshtein` is graded, and that is the reason to have it

`Equals` answers "identical or not", so a model sliding from an exact match to a
near-exact one is indistinguishable from one sliding to nonsense: `0.0` for
both. Here the first scores `0.97` and the second `0.2`, and `compare()` sees
the difference. Normalized similarity `1 - distance / max(len)`, an in-house
algorithm with no dependencies — `digline.core` is the library Plumbline imports
and it stays bare. It reads `Case.expected` instead of carrying the expected
string itself: the expected value is the case's data, not a parameter of the
assertion.

`Score.metadata` carries `distance` and `length`; the `reason` **quotes neither
string**, for the same reason the judge's `reason` does not cross the perimeter.

### The budgets are not binary

`CostBudget` and `LatencyBudget` give a graded score
(`cap / (cap + measure)`, `0.5` exactly at budget) rather than pass/fail. That is
needed so `compare()` can see the **drift**: a cost rising from 0.01 to 0.09
under a cap of 0.10 is invisible to a threshold and visible here. The raw values
— `cost_usd`, `max_usd`, `ratio` — live in `Score.metadata` and cross the
boundary, because they are measurements.

## When the answer changes on its own

Two different noises, and they go in two different places.

**The system oscillates** — same input, different answers. That is
`Suite.samples`: the driver calls the target N times per case and folds the
verdicts. It needs the driver because it needs to call the target more than
once.

**The judge oscillates** — same output, different votes. That is `Repeated`,
which wraps an assertion and asks it N times:

```python
Repeated(
    inner=LlmRubric(rubric="…", judge=judge, threshold=0.7, tolerance=0.05),
    samples=3,
    min_agreement=0.67,
)
```

It takes `threshold`, `tolerance` and `accepts` from `inner` and they cannot be
passed: two copies of a threshold drift apart. Wrapping an assertion **changes
its identity**, so the first comparison afterwards shows a `new` and a
`missing` — deliberate, because it is the right way for "this check is now judged
three times" to reach whoever reviews the PR.

### What the numbers mean

With a single sample the fold is the **identity function**: a suite that does not
sample produces the same bytes as before.

With several samples the score is the **mean** of the per-sample scores — so
raising `samples` never trips `CostBudget` by itself: what the user pays per
answer has not changed. The total spent goes into
`Score.metadata["total_cost_usd"]`.

`agreement` is **the fraction of samples that gave the same verdict as the
majority**. Not the variance, not the spread: it answers the question one
actually asks — *if I run it again, does it still say the same thing?* A rubric
oscillating between 0.80 and 0.88 is noisy and harmless; one oscillating between
0.69 and 0.71 around a threshold of 0.70 is not, and only agreement tells them
apart. The `spread` (max − min) is reported alongside for anyone who wants the
other view.

Below `min_agreement` the outcome is **`error`, not `fail`**: a judgement that
does not repeat is not a failure, it is a judgement that could not be given —
and it means a suite that is too noisy cannot be promoted to reference.

In `Score.metadata`: `samples`, `agreement`, `spread`, `errored_samples`,
`scores` (the raw scores). All numbers, so they cross the boundary: the software
house sees how unstable a check is without seeing what it was judging.

## Aggregates: the verdict on the run

With ground truth, the question that decides a release is not "did case 14 pass" but
"is precision still above 0.60". It is a `Verdict` like any other — mandatory
threshold, so a **gate by construction** — and `compare()` says whether it regressed.

```python
Suite(
    ...,
    assertions=[Contains(needle="MATCH", name="agrees_with_mark")],
    run_assertions=[
        Precision(over="agrees_with_mark", threshold=0.60, tolerance="1/21"),
        Accuracy(over="agrees_with_mark", threshold=0.65, tolerance="1/21"),
    ],
    cases=[Case(id="art-01", label="positive"), ...],
)
```

`over` names **one** per-case assertion, the one answering "does it agree with the
mark?". From there the matrix: positive+pass = TP, positive+fail = FN,
negative+pass = TN, negative+fail = FP.

| Aggregate | Formula |
|---|---|
| `Precision` | `TP / (TP + FP)` |
| `Recall` | `TP / (TP + FN)` |
| `Accuracy` | `(TP + TN) / counted` |
| `F1` | `2TP / (2TP + FP + FN)` |

Four dataclasses and not a `Metric(kind=…)`: `Precision(over=…)` reads as English, and
moving from precision to recall is **a different question**, hence a different identity
and a different baseline.

`F1` sits beside the others because precision and recall trade against each other: a
stricter prompt that keeps fewer items and gets more of them right **raises precision and
lowers recall**, and each of the two numbers alone tells half the story. `F1` is the one
that falls when the trade was a bad one. Written as `2TP / (…)` and not as `2PR / (P + R)`:
same number, but one denominator to check instead of three, and no decision to make about
what `F1` means when precision has already gone to `error`.

`Suite` refuses an `over` that no assertion carries **and** one that two assertions share:
they are the same mistake seen from two sides. And if an aggregate counts a matrix, every
case must have a `label`.

Empty denominator → **`error`**, not `1.0`: if the system kept nothing, precision is
undefined, and `1.0` would be the most dangerous possible answer.

**The two exclusions never get separated from the number.** `suspended_excluded` is the
only value in the product that improves by *removing* work — suspending a failing case
raises the ratio without anyone lying — so it travels next to the figure in the `reason`,
in the metadata and in the report's table.

### Where to put the threshold

**An aggregate is a contract about present behaviour, not a target.** The threshold is set
where the system *is*, by measuring it, and the comparison protects against getting worse.
A threshold set where you wish you were makes the gate red by construction, hence useless
for CI and soon ignored.

With the numbers from the brief: measured precision ≈ 0.62, hence a **threshold of 0.60**,
not 0.70. You reach 0.70 by improving the prompt and *then* raising the threshold — which
is a change to the configuration, visible in `config_hash` and in a PR.

## "k out of n": when a number is a count

`min_agreement` is a fraction of the samples and nothing else: with three samples there
exist `1/3`, `2/3` and `3/3`, and that is all. Written in decimal it stops being obvious,
and that cost two mistakes in one hour of real suite work:

- `min_agreement=0.67` for "two out of three". `2/3` is `0.666…`, so `0.67` sits
  **above** it: every case with two votes out of three went to error, silently and for the
  opposite reason.
- `tolerance=0.4` for "two out of five". This one worked — but only because `2/5` is exact
  in decimal. It was right by luck.

So the fraction can be written as one — `"2/3"` or `Fraction(2, 3)` — and a float that
lands on no reachable `k/n` **is refused at construction**, with the list of the ones that
exist. The refusal looks at the value, not the notation: `"2/4"` is as impossible with
three samples as `0.67` is.

For an aggregate's tolerance the form counts as an expression, not as a check — the
denominator is the number of counted cases, which the suite knows and the assertion does
not: `tolerance="1/21"` says "one case" where `0.047619` says nothing.

## The tolerance is measured, not chosen

For a deterministic assertion the tolerance is `0.0` and there is nothing to
decide. For one that is not — `LlmRubric`, the budgets — **an invented number
produces either false alarms on every run or a threshold that never trips**. The
procedure:

1. Freeze the system: no changes to the prompt, the model, the cases.
2. Run the suite 5–10 times and promote the first run to reference.
3. Compare the others with `--json full` and take the largest `delta` in
   absolute value for each assertion.
4. The tolerance is that maximum plus a margin — doubling it is reasonable.
5. Put it back in the suite; from then on, whatever exceeds that threshold is a
   fact, not noise.

If at step 3 the maximum is as large as the differences you want to catch, the
tolerance is not the remedy: that check is too noisy to be a gate, and it has to
be made stable — `Repeated` with `min_agreement`, a tighter rubric, a judge at a
lower temperature.

A command doing the five steps (`digline calibrate`) is planned and not written
yet: first we need to see how the procedure behaves by hand.

## Custom assertions

Inherit from `AssertionBase` and be a dataclass — `identity` is derived from the
declared fields, so without a dataclass there is nothing to fingerprint (and the
message tells you so).

```python
from dataclasses import dataclass
from digline.core import (
    TEXT_ONLY,
    AssertionBase,
    EvaluatorInputs,
    OutputKind,
    Verdict,
)


@dataclass(frozen=True, slots=True)
class MaxWords(AssertionBase):
    limit: int
    name: str = "max_words"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = TEXT_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        assert isinstance(inputs.output, str)
        words = len(inputs.output.split())
        return self._binary(words <= self.limit, f"{words} words (limit {self.limit})")
```

`AssertionBase` gives three exits: `_error(reason)`, `_binary(ok, reason)`,
`_graded(value, reason, metadata=...)`, plus `_accept(output)` which applies
`accepts`. **Threshold and tolerance are excluded from the identity**: they are
*how* you judge, not *what* you check, so raising a threshold leaves the
verdicts paired and the comparison says so.

### A custom aggregate

`RunAssertionBase` is the same thing one level up: the dataclass declares `over`,
`threshold`, `tolerance`, calls `self._normalize()` in `__post_init__` — that is
what accepts `"2/3"` where the field says `Ratio` — and implements
`__call__(outcomes: Sequence[CaseOutcome]) -> Verdict`. The exits are
`_error(reason, matrix)`, `_graded(value, reason, matrix)` and `_ratio(num, den,
label, matrix)`, which is the one needed almost always: it handles the empty
denominator as `error` and puts the exclusions next to the number without you
having to remember.

`build_matrix(outcomes)` builds the confusion matrix if you need it; a metric
that does not count a matrix — one over raw scores instead of outcomes —
overrides `requires_label` with `False`, and `Suite` stops demanding a `label`
on every case.

## The judge

`Judge` is a protocol: `__call__(prompt: str) -> JudgeReply`, with
`JudgeReply(score: float, reason: str)`. The core composes the prompt from the
rubric, the input and the output; you supply the call to the model.

`JudgeReply` validates at construction: score in `[0, 1]`, non-empty `reason`.
It is the boundary an LLM enters through, that is, the least reliable input in
the system.

A judge that raises, that returns a score out of range or that gives no reason
produces a verdict in **`error`**, not a failure: not having been able to judge
is a different thing from having judged badly.

### The prompt a judge receives

**One shape, for every assertion that asks a judge anything.** This is interface,
not an implementation detail: anybody writing a judge — and everybody writing a
*fake* judge, which is every test — has to parse it, and reading digline's source
to find out was friction 32.

```text
<instruction, when the assertion has one>

Rubric:
<the rubric>

Context:
<the context lines, one per line>

Input:
<the input>

Output to judge:
<the output>
```

Three rules, and they hold for `LlmRubric`, for `Faithfulness` and for whatever
comes next:

1. The **instruction comes first, never after the output.** A trailing line is
   what made `Faithfulness` unusable with a fake: the fake split on the output
   label and counted the trailing instruction as a claim nothing supported, so
   every score halved with the suite green.
2. The output is **last**, behind `Output to judge:`, which appears **once**.
   `digline.core.JUDGE_OUTPUT_LABEL` is that string — import it rather than
   typing it, and `prompt.split(JUDGE_OUTPUT_LABEL, 1)[1].strip()` is the whole
   of what a fake needs.
3. Sections appear in the order above and are **omitted when empty** — no blank
   `Context:` heading when there is no context.

`ClaimJudge` receives the same shape. Its instruction asks for two counts:

```text
Decide which claims in the output are supported by the context, and report how
many claims the output makes and how many of them the context supports.

A claim is supported only if the context states it or entails it. Knowing it to
be true from elsewhere does not make it supported.
```

## What `--json` promises

`digline compare --json` and `digline run --json` print an object whose first
key is `output_version`, currently `1`. It is bumped when the shape changes and
is **not** `SCHEMA_VERSION`: that one versions documents already on disk and
comes with migrations, because a run file written last month must still be
readable. This one versions what a pipeline parses on stdout today, where
nothing is migrated and the only question is whether the consumer knows the
shape moved. A reworded sentence must not bump the storage schema, and a new
field inside a `Run` must not bump the output contract for consumers who saw no
change.

At version 1, `compare --json` carries `worse`, `unjudged`, `suspended`,
`config_changed`, `artifacts_changed`, `counts`, `reasons_available` and
`sentence`; `--json full` adds `deltas`. A golden key set in the tests fails the
build if a key is added without the bump.

## Verdicts and comparison

`Verdict(score, threshold, status, reason, tolerance, assertion_id)` with
`status` in `"pass" | "fail" | "error"`. `passed` is derived. It is not possible
to build one that contradicts itself: a `status` disagreeing with
`score >= threshold` is refused.

`compare(run, baseline) -> Comparison` returns one `AssertionDelta` per verdict,
with outcome `regressed`, `improved`, `unchanged`, `new`, `missing`, `errored`.
The rules apply in this order: presence on one side only, then error, then a
change of outcome (**regardless of the tolerance**), then numeric comparison
against the tolerance.

## Redaction

`Disclosure(score_metadata, run_metadata)` declares **in the suite's code** the
metadata keys that may cross a boundary beyond the default.

The two halves follow different rules on purpose: from `Score.metadata`, written
only by assertions, numbers and booleans pass on their own merit; from
`Run.metadata`, which an integration annotated from production, **nothing
passes**, numbers included. `0.01` written by `CostBudget` is a measurement;
`1499.00` copied from a request is a customer's data dressed up as one.

`redact(run, disclosure)` returns the run without its payload — `reason` and
suspension reasons disappear, the verdicts remain. It is a function on the value
and not a serializer option, so no future transport can forget about it.

## A complete example

It really runs: `examples/quickstart/` holds `app.py` — the application under
test, with `reply(question_id)` and `render_prompt(question_id)` — and this file.
A test in `tests/test_examples.py` executes it on every build and checks that it
is identical to the one below, so the documentation cannot drift from the code.

```python
"""A complete, working suite.

Run it from this directory:

    digline run     --suite suite.py
    digline promote --suite suite.py --run latest
    digline compare --suite suite.py --run latest
    digline report  --suite suite.py --run latest --locale it --out report.html
"""

from __future__ import annotations

import app  # the application under test, sitting next to this file
from digline.core import (
    Contains,
    CostBudget,
    JudgeReply,
    LatencyBudget,
    LlmRubric,
    Regex,
)
from digline.run import Case, Response, Suite


def judge(prompt: str) -> JudgeReply:
    """Stand-in for a real model call.

    digline composes `prompt` from the rubric, the question and the answer,
    and asks for two things back: a score in [0, 1] and a reason. Replace the
    body with your own call; the protocol is all that is required.

    Note it is a plain function. That is why a suite is Python and not YAML.
    """
    concise = len(prompt.split()) <= 90
    signed = "Northwind Support" in prompt
    score = 0.4 + 0.3 * signed + 0.3 * concise
    return JudgeReply(
        score=score,
        reason=f"signed={signed}, concise={concise}",
    )


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="support",
    assertions=[
        # Every assertion runs on every case, so each one states something that
        # must hold for all of them.
        Contains(needle="Northwind Support"),
        Regex(pattern=r"^[A-Z]"),
        LlmRubric(
            rubric="Does the reply answer the question in at most three sentences?",
            judge=judge,
            threshold=0.7,
            # Mandatory and without a default: a judge is not reproducible, and
            # an implicit tolerance over a noisy value is a green light nobody
            # decided to give.
            tolerance=0.05,
        ),
        CostBudget(max_usd=0.02, tolerance=0.05),
        LatencyBudget(max_ms=800.0, tolerance=0.10),
    ],
    cases=[
        Case(id="where-is-my-order"),
        Case(id="how-do-i-return"),
        Case(id="is-it-waterproof"),
        # Set aside with a stated reason, which the report shows. The driver
        # does not run it; the run still records that coverage is smaller.
        Case(id="refund-status", suspended="the refund API is down, ticket 412"),
    ],
)


def target(case: Case) -> Response:
    """Called once per case. It calls the application and reports what it cost."""
    result = app.reply(case.id)
    return Response(
        output=result.text,
        input=app.render_prompt(case.id),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
```

The cycle that follows is in the [README](../README.md).
