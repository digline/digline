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
| `project` `project_served` `Minter` `TokenKind` `is_token` `ProjectionRefusedError` — [the projection](#the-projection) | |
| `resolve_tokens` `Lookup` `NameRow` and its refusals — [the resolver](#the-resolver) | |
| `run_to_json` `run_from_json` — [the committed file](#the-committed-file-run_to_json-and-run_from_json) | |

The report lives in `digline.report` (`headline`, `render_html`, `Locale`,
[`render_run_html`](#the-first-round-render_run_html),
[`case_history`](#one-case-across-runs-case_history) and
[`suspension_snippet`](#setting-a-case-aside-suspension_snippet)), the
store in `digline.store` (`FileResultStore`, `RunRef`, and three methods by
name: `FileResultStore.name_table_dir` — [below](#the-name-tables-directory) —
and `read_run` and `read_baseline` —
[further below](#reading-and-promoting-from-a-program)).

Two more, for anything that drives digline rather than declares a suite.
`digline.host` is the layer that touches the world — `load_suite`, `Loaded`,
`load_target`, `read_artifacts`, `git_commit`, `utc_now_iso`, `resolve_key`,
`suite_runs`, `SuiteRuns` and `left_out`, `promote` and `REFUSALS`.
`digline.wire` is the machine surface: `OUTPUT_VERSION`, the exit codes, and the
functions that build every `--json` and every MCP response. A script that loads
a suite imports the first. A front end imports the second, and so does **a
program that needs the number a run exits with**: two functions in it,
[`exit_code` and `run_exit_code`](#the-exit-code-exit_code-and-run_exit_code),
give that number without a front end.

**These moved in 0.6.0.** `load_suite` and its neighbours used to live in
`digline.cli.loader`, which was two layers wearing one name — the host, and the
terminal. If you followed an earlier version of
[the guide](guide.md), change `from digline.cli.loader import load_suite` to
`from digline.host import load_suite`. (ADR 0011 §7)

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
data on disk (`.digline/<tenant>/`) and `compare()` raises
`DifferentTenantsError`, in `REFUSALS`, if two runs do not share it. It raises too if one is [projected](#the-projection) and the other is
not. `environment` says *where inside that perimeter* — production,
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
named. A `str` where a `Path` is meant is coerced on construction, the way the
TOML loader coerces by declared type, and what cannot be a path is refused there
by field name rather than at read time. Relative paths resolve against the
suite's own directory. The **CLI**
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

### `Suite.record_responses`: the answers, for judging them again

Off by default. With `record_responses=True` the run records, per case and per
sample, what the target answered, the rendered prompt that produced it, and what
that call cost in money and in milliseconds:

```python
suite = Suite(..., record_responses=True)
```

That is what [`digline rejudge`](rejudge.md) replays: a changed judge, rubric or
threshold, over the same answers, at no cost to the target.

It is **not** a member of `Disclosure`, and the distinction is the safety of the
feature. `Disclosure` governs what crosses a boundary; this governs what is
written inside the perimeter. Nothing recorded here ever crosses: `redact()`
drops it, `digline.wire` does not know the field's name, no `Disclosure`
releases it and none can be added — a judge's `reason` is already withheld
*because it quotes the output*, and releasing the thing quoted from while
withholding the quote would not be a boundary. `digline promote` strips the
answers too: `baselines/` is committed.

It does not enter `config_hash`, so turning it on costs no baseline: recording
changes no score, pairs no verdict differently and moves no bar.

Whole or nothing, at 65 536 characters per field: over the ceiling the entry
records neither the answer nor the prompt and says `oversize`, because a clipped
answer re-judged produces a score that looks like every other score. Reasoning
in [ADR 0015](adr/0015-the-recorded-output-and-the-declared-re-judge.md).

### `Case.canary`: watching the model instead of measuring it

An alias is a pointer, and pointers roll. `resolved_model` records what the
provider *said* answered — and is silent on Bedrock, and on a customer's own
gateway, where nobody says anything. A canary is the behavioural half of that
answer:

```python
Case(id="alias-probe", canary=True, vars={"ask": "..."})
```

The case is called and judged like any other, and then:

- it is in **no** aggregate — not precision, not recall, not a per-group
  instance — and the reason names it: `accuracy 0.700000 = 14/20 (20 counted, 0
  suspended, 0 could not be judged, 1 canary)`;
- it needs no `label`, and may declare no `group`;
- if it **moves at all** — worse or better, since its score is a fingerprint
  rather than a quality — the headline says *the model under this alias likely
  changed* and the run exits `1`, on `Headline.canary_moved` rather than on
  `worse`;
- a movement inside the baseline's own interval is not a move, which is why a
  suite that declares a canary must declare `samples >= 2`: at one sample there
  is no noise to measure and every wobble would stop a release.

Reasoning in [ADR 0016](adr/0016-the-canary-case.md).

### `Case.calibration`: watching the judge's scale

The canary watches whether the model is still that model; a calibration case
watches whether the scale is still a scale. A judge that has gone binary is
*more* repeatable, not less — every answer at 1.00, every time — so no number of
re-runs sees it. An answer you know to be half right, scored at 1.00, does:

```python
from digline.run import Calibration, Case

Case(
    id="half-supported",
    context=("Refunds take 30 days.", "A receipt is required."),
    calibration=Calibration(
        output="Refunds take 30 days and need no receipt.",
        check="faithfulness",
        low=0.3,
        high=0.7,
        input="How do refunds work?",
    ),
)
```

It is a **fixed answer**, not a flag on a generated one: an answer the target
generates today is not known to be partial. So:

- **the target is not called** for it. The driver hands `output` and `input` to
  your mapper as a `Response`, so the judge is reached along the path your real
  cases take;
- **only the named check runs** on it. A `CostBudget`, a `LatencyBudget` or a
  `ToolsCalled` would read a call nobody made and error;
- it is in **no** aggregate, and the reason names it (`… 1 calibration`); it
  needs no `label` and may declare no `group`, and it cannot also be a canary;
- a movement of its score **inside the band** is shown, in its own section of
  the report and on each `--json full` delta as `"calibration": true`, and it is
  never a regression: it is left out of `counts` and out of `worse`, because the
  target was never asked;
- if the check's score lands **outside `[low, high]`** — at storage precision,
  both ends inclusive — the headline leads with *the calibration case … scored
  1.000000 across 3 samples (1.000000, 1.000000, 1.000000), outside its declared
  band 0.300000–0.700000*, and the run exits **`2`**, on `Headline.scale_lost`.
  The numbers exist and are not measurements. A regression beside it still
  exits `1`, and the calibration clause still comes first. It needs no
  baseline, so a first run can be stopped by it;
- a run whose scale was lost **cannot be promoted** (`UncalibratedRunError`);
- `digline rejudge` re-judges it from the declaration, not from the stored run.

What it refuses at construction, each cheaper met as a sentence than as a
number: a band that touches `0` or `1` (an extreme in band cannot detect the
extreme); a `check` that names no assertion, or two; a check whose class does
not declare `KIND = "judged"` (read through `Repeated`); a suite with
`samples < 2` — on this case that repeats the judge alone; and, for
`LlmRubric` and `Faithfulness`, an `input` left unset. Those two show the judge
the question, and the target that would render it is not called: write the
question, or `""` if your real cases have none. `None` and `""` are different
declarations.

`output` and `input` are payload. **The fields are never written into a run**,
recorded responses or not: the run holds the check's name and the band. A
judge's own `reason` may quote them inside the perimeter, as any reason may
quote any answer, and it reaches the run file and the journal when every
judgement of the case errors. Every boundary drops it: `--redacted`, `--json`,
`explain` and the MCP server carry no reason. Whether an answer
makes a good calibration — four claims, two supported — is your craft, and
nothing checks it. Reasoning in
[ADR 0024](adr/0024-the-judge-as-an-instrument.md) §4.

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
| `group` | `str \| None` | `None` |
| `canary` | `bool` | `False` |
| `calibration` | `Calibration \| None` | `None` |

`id` is the key `compare()` pairs on: renaming it produces a `new` plus a
`missing`. Choose it stable and **with no production data inside**.

`group` names the class this case belongs to — an expense category, a language,
a customer segment. It is **descriptive**: no target and no assertion is given
it, and a suite that sets `by_group` nowhere behaves as though the field did not
exist. `None` means the case is in no group and is counted only in the whole-run
aggregate; there is no implicit "ungrouped" bucket. An empty string is refused,
because `None` already spells "no group". See
[ADR 0010](adr/0010-per-group-aggregates.md).

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
| `usage` | `Usage \| None` | `None` |
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

### `JudgeBase`, and why a plugin ships two of them

A plugin is a target **and** a judge (ADR 0004). `digline.core` declares `Judge`
and `ClaimJudge` and implements neither — the judge is injected, which is what
keeps an assertion a pure function — and `digline.targets` is where the box it
arrives in lives:

| | |
|---|---|
| `JudgeBase` | model, price list, and the counters below. A plugin writes `_complete` |
| `ScoreJudge` | `(prompt) -> JudgeReply`, satisfies `Judge` |
| `ClaimCountJudge` | `(prompt) -> ClaimReply`, satisfies `ClaimJudge` |
| `loads_lenient` | the JSON object in a reply, however the model wrapped it |
| `SCORE_SYSTEM` `CLAIM_SYSTEM` | what each judge is told, written against the shape `judge_prompt()` produces |

```python
from digline.core import Faithfulness, LlmRubric
from digline_openai import OpenAIClaimJudge, OpenAIJudge

judge = OpenAIJudge(model="gpt-5-mini")
LlmRubric(
    rubric="One sentence, and it cites the passage.",
    judge=judge,
    threshold=0.8,
    tolerance=0.05,
)
Faithfulness(judge=OpenAIClaimJudge(model="gpt-5-mini"), threshold=0.9, tolerance=0.05)
```

Both protocols, always, because they answer different questions and a plugin
shipping only the first would leave `Faithfulness` with nothing to run on.

**Why it is not optional.** What a judge is sent is the model's *output* — the
thing decision 9 keeps inside the perimeter. A judge that cannot live where the
output lives forces the payload out of it, and no `Disclosure` in the suite
would say so: disclosure governs what leaves the run *document*, not what an
assertion did while producing it. `digline-openai` takes a `base_url`, so a
customer's own Azure deployment or vLLM judges its own runs.

**What judging cost.** `judge.calls`, `judge.spent_usd`, `judge.latency_ms` and
`judge.tokens` accumulate for the life of the object and are **never reset**: a
per-run figure is a delta the caller takes. A call that raises is not counted —
its cost is unknown, and counting it at zero is the undercount that reads as
good news. `Response.cost_usd` is the *target's* call and does not include any
of this (ADR 0004 §3).

Since 0.16.0 the run **does** carry it: `execute()` reads these counters before
the first case and after the last, and writes the difference as the judge line
of `Run.usage` — which is why the delta is the shape, and why a suite that
reuses one judge object across runs still gets a per-run figure. Two assertions
holding the *same* judge instance are one bill; two instances configured
identically are two, and they add (ADR 0025 §4).

### `Run.usage`, and what a line means

`Run.usage` is two `CallTotals` — `target` and `judge` — or `None` on a document
that recorded none, which is every document written before schema 14 and never
a run that consumed nothing.

| Field | Meaning |
|---|---|
| `calls` | calls this line covers |
| `counted` | of those, how many reported their usage |
| `tokens` | the `Usage` counts, summed over the counted calls |
| `spent_usd` | what the line cost |

`counted` below `calls` means the total covers **part** of the run — a target
that reports no counts, or a leg somebody resumed by hand without figures — and
`line.partial` says so. The CLI prints that parenthesis only when it is true,
and `--json` carries `partial` as a field so nothing has to derive it.

The totals cross a boundary; the per-call counts on a recorded response do not
(ADR 0025 §8).

**`thinking_tokens` is a breakdown, not a fifth quantity.** A model that reasons
before it answers is billed for tokens nobody reads, and since schema 15 `Usage`
says how many of its `output_tokens` those were. They are **inside**
`output_tokens` — both providers that report the split count them there — so the
money is already counted and `Pricing.cost` does not read the field. That is the
opposite of `cache_write_tokens`, which sits outside `input_tokens` and must be
added (ADR 0026 §2).

Three states, and the middle one is the reason there are three: `None` is *the
provider, or this SDK, did not report a split*, `0` is *it reported one and this
reply did no thinking*, and a count above `output_tokens` is refused as a
malformed reply rather than clamped. A total folds two reported sides and stays
`None` if either side is unreported — an unknown amount of thinking is not zero
thinking, and a fold that treated it as zero would report less than the truth.

Anthropic documents its count as **re-tokenised, and therefore approximate**: it
is derived after the fact, so it may not reconcile to the digit with
`output_tokens` or with anything else. Nothing downstream derives anything from
it (ADR 0026 §4).

**Reading a reply.** Lenient about the wrapping — a bare object, a ```` ```json ````
fence, or an object with prose around it all read correctly, because
`response_format` is an optimisation and half the compatible providers refuse
it. Strict about the content: a missing `score`, a score outside `[0, 1]`, a
missing `reason` or a fractional claim count all raise, and `LlmRubric` turns
the exception into **`error`** — neither green nor a regression.

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
    config_path="config",
)
```

| Argument | |
|---|---|
| `url` | where to post |
| `request` | `(Case) -> Mapping`, the JSON body. A callable, not a template: a real payload has shapes a template cannot |
| `output_path` | dotted path to what the assertions judge |
| `cost_path` | dotted path to the cost, or `None` |
| `latency_from_response` | dotted path to the time the service reports. Left out, digline measures the round trip instead — which includes the network, and is a different number measuring a different thing |
| `config_path` | dotted path to an object saying which model answered and how it was set up, or `None`. See below |
| `expect_config` | the configuration the suite expects the application to report, or `None`. A contradiction errors the case. See below |
| `tools_path` | dotted path to the tool names the model called, in order, or `None` |
| `tool_calls_path` | dotted path to those calls with their arguments, or `None`. Declared alone, the names are derived from it |
| `usage_path` | dotted path to an object of token counts, by `Usage`'s own field names, or `None` |
| `headers`, `timeout` | as you would expect |

Every `*_path` is a dotted path **into the JSON answer**, never a file. Declared
as `str`, deliberately: the declarative loader resolves a `Path`-annotated
parameter against the suite's directory, which would turn `data.answer` into a
filename nobody wrote.

#### `config_path`: the configuration, when the model call is on the other side

The call happened in your application, so your application is the only one that
can say what made it. `config_path` names a JSON object in the answer:

```json
{"provider": "openai", "model": "gpt-4o-mini",
 "temperature": 0.0, "max_tokens": 512}
```

It becomes `Run.target_config`, so `compare` names what moved —
`model gpt-4o-mini → gpt-4o` — instead of reporting the configuration as
unchanged (ADR 0005 §8). Left out, the target declares nothing, which is what it
has always done: absent is not a change.

The keys are a **closed set**, and one that is not in it is refused by name
rather than recorded: `provider`, `model`, `max_tokens`, `temperature`,
`top_p`, `top_k`, `seed`, `region`, `base_url`, `response_format`, `json_mode`.
`provider` and `model` are required. A `null` reads as *not sent*, so the key is
absent. A `base_url` is reduced to host and port before it is recorded — never
the scheme, the path or the userinfo — and withheld under redaction like any
other.

The first answer is the run's configuration, and a later one that disagrees
**errors its own case**: one run measures one system, so two set-ups are two
runs.

#### `expect_config`: the review that makes the value worth recording

Everything above checks the *shape* of what your application reports. Nothing
checks that it is true — over HTTP the measured party writes every field, so the
`provider` and `model` in a run are values nobody reviewed, and they cross a
boundary in clear. `expect_config` is the repair (ADR 0030 §4): the suite
declares, the application agrees, and a contradiction is refused.

```python
target = HttpTarget(
    "http://localhost:8080/classify",
    request=lambda case: {"text": case.vars["text"]},
    output_path="data",
    config_path="config",
    expect_config={"provider": "gemini", "model": "gemini-2.5-flash"},
)
```

The value in the record is then one a reviewer wrote in a file that went through
a pull request, and the application's part is reduced to agreeing with it.

**The keys you name are the keys checked** — partial on purpose, so declaring
`model` does not oblige you to declare a temperature chosen on the other side of
HTTP. Nothing is mandatory. A declared key the application never reports is a
mismatch too: absence is not agreement.

A mismatch **errors its cases**, like the rotation above and for the same reason,
and it cannot be caught earlier: `preflight` sends a `HEAD`, and an `HttpTarget`
has nothing to declare until it has answered. Four things are refused at
construction instead, because each would otherwise produce a green run that
reviewed nothing: `expect_config` without `config_path`, an empty
`expect_config`, a key outside the closed set, and a value that is not a scalar.

It is recorded **beside** `config_hash` and never inside it, so adding the key
costs no re-promotion and a declared model rotation stays comparable (ADR 0030
§7). What is still owed: the document does not yet record *whether* a
configuration was reviewed, so a suite that declares nothing is where it always
was — see ADR 0030 §6.

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
| `config -> Mapping[str, ConfigValue]` | `execute()`, before the first call **and after the last** | recorded as `Run.target_config` (ADR 0005). Asked twice so a malformed one fails before the suite is paid for, and a target that can only learn it by answering — `HttpTarget`, or any plugin recording what the provider said answered — still records one |

`ProviderTarget` implements all three. `preflight` checks that each case provides
every variable its templates ask for, and that the model has a price — both are
cheaper to discover before the run than on case thirty-seven with thirty-six
paid calls behind it. It happens in the driver rather than in `Suite`, so a
script calling `execute()` directly is covered too, and so that a `Suite` stays
a declaration that knows nothing about how its outputs are produced.

### `_complete`: what a plugin returns

One method, and it returns a **record**:

```python
def _complete(self, prompt: str, system: str | None) -> Completion:
    reply = self._client().messages.create(**request)
    return Completion(
        text=text_of(reply),
        usage=usage_of(reply),
        finish=finish,  # "stop" | "length" | "tool_use" | "filtered" | "other"
        finish_raw=raw,  # the provider's own word, verbatim
        tools=("search",),  # names, in order — `None` if none were reported
        model=reply.model,  # what the provider said answered
        fingerprint=None,  # OpenAI's `system_fingerprint`, where there is one
    )
```

Everything after `usage` defaults, so a provider that reports none of it writes
`Completion(text, usage)`. **The old `(text, Usage)` pair is still accepted and
always will be** — a plugin written before ADR 0004 §6 keeps working unchanged,
and the pair is the honest return for a provider with nothing else to say.

Three rules a plugin follows, because getting any of them wrong is a boundary
mistake rather than a formatting one:

- **`finish` is normalised, `finish_raw` is not.** The vocabulary is
  `digline.core.Finish` and it is what an assertion is written against, so one
  check works on every provider. Use `finish_of(word, TABLE)` for the
  translation: a word the table does not know becomes `other`, **never `stop`**,
  because calling an unrecognised ending "it finished normally" would turn a
  truncated run green the day a provider adds a stop reason.
- **`tools=None` and `tools=()` are different facts.** `()` is the model calling
  nothing; `None` is nobody reporting. `ToolsCalled` errors on the second rather
  than announcing that no tool was called.
- **A call without a name is `None` at its position, never `""` or `"None"`.**
  None of the three SDKs validates a reply, so a server that leaves the name
  out hands over `None` or no key. Write `ToolCall(tool=None, …)` and `None` in
  `tools`, in the same place. `ToolCall` refuses `""`. The run document omits
  `tool` for such a call and writes `"tool_absence": "not_reported"`, never
  `"tool": null`, which every reader before schema 13 turns into a tool named
  `"None"`. A plain-function target says the same with `"tool": None` in
  `metadata["tool_calls"]`. (ADR 0018 §1, amended 2026-09-17)
- **`model` is read out of the reply, never copied from the request.** Echoing
  the requested id back would manufacture the one fact it exists to obtain, and
  would do so identically whether or not the model had rolled underneath. A
  provider that does not say records nothing — `Bedrock` Converse is the case.

What is not asserted on is not recorded. `finish` and `tools` reach
`Response.metadata`, which is **not persisted**: what reaches a run file is what
an assertion measured out of it, through `Score.metadata`.

### `config`: what decided how the model answered

A run records the verdicts, the rules that judged them, the prompt that produced
them — and, since ADR 0005, the system that answered:

```python
@property
def config(self) -> Mapping[str, ConfigValue]:
    return {
        **super().config,
        **sent(max_tokens=self.max_tokens, temperature=self.temperature),
    }
```

Flat, scalar, and only what was actually sent — `sent()` drops an unset
parameter rather than writing `None`, because "the provider's default applied"
and "we sent nothing for it" are different facts. `provider` and `model` are
always present; a target that declares neither declares nothing, which is what
a plain function does and is not a change.

It does **not** enter `config_hash`, for the reason `Suite.artifacts` does not:
two runs at two temperatures have to stay comparable, and that comparison is the
experiment. What it gives instead is the **named delta** — `temperature 0.3 →
0.7` in the report, in the terminal and in `--json` — and, where a regression
lands in the same comparison, the sentence *"this drop coincides with
temperature 0.3 → 0.7"* beside it.

Two of the recorded fields are **observed rather than sent**, and they come out
of the record above: `resolved_model` — what the provider said answered, where
the target sent an alias — and `fingerprint`. Absence means something different
for them: not *we did not send it*, but *the provider did not say*. They are
what catches a model that rolled under an alias nobody edited; a rotation part
way through a run errors that case, while a rotated `fingerprint` simply goes
absent. `fingerprint` is withheld under redaction, because on a custom
`base_url` its value is written by a server nobody here reviews. (ADR 0005 §9)

`JudgeBase` answers the same property, and a judge's is recorded separately as
`Run.judge_config`: a judge that moved is a change of measuring *instrument*, so
the scores stop being comparable with the baseline whatever the target did, and
the report says so rather than leaving it to be noticed.

A suite may hold several judges, so `judge_config` records **which** instruments
graded as well as how: `identities` is the set of distinct `provider/model`
labels bound in the run, always recorded, and `values` carries the merged set-up
only when that set has one element. Replacing one of two judges arrives as one
identity removed and one added — never as `model a → b`, which stops being true
the moment a suite grades with three.

What is out, and why. `additional_request_fields` and `extra_body` are the
escape hatch, outside the plugin's own signature, and what is outside the
contract is outside the record. `prefill` is *prompt* — put in the model's mouth
— so it belongs to `Suite.artifacts`, where it gets a diff rather than a scalar.
`token_param` only decides which argument carries the cap that is already
recorded. `response_format` **is** in, reduced to its `type`, and so is the
judge's `json_mode`: they change the shape of the answer, so a regression can
coincide with them.

`base_url` records the **host** — never the path, never the userinfo — because
it is the one recorded field that describes the client's own topology, and it is
the one redaction keeps back.

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
| `ToolsCalled` | **`expected`** (the tool names, in order) | `1.0` | all |
| `ToolCalledWith` | **`tool`**, **`arguments`**, `match` (`exact` or `subset`) | `1.0` | all |

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
    min_agreement="2/3",
)
```

`min_agreement` is a count of samples, so **write it as one**. `0.67` in that
slot is refused at construction — three samples produce `1/3`, `2/3` and `3/3`
and nothing else — and it is refused for a good reason: see
["k out of n"](#k-out-of-n-when-a-number-is-a-count) below.

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

Only a *judged* verdict — `pass` or `fail` — can be the majority. An errored
sample counts against agreement and never for it: four samples that could not
judge do not "agree", and the fifth does not get to decide the check alone
([ADR 0006 §12](adr/0006-repeated-samples-and-the-noise-floor.md)). With no
errored sample this is the same number it always was.

Below `min_agreement` the outcome is **`error`, not `fail`**: a judgement that
does not repeat is not a failure, it is a judgement that could not be given —
and it means a suite that is too noisy cannot be promoted to reference.

In `Score.metadata`: `samples`, `agreement`, `spread`, `errored_samples`,
`scores` (the raw scores). All numbers, so they cross the boundary: the software
house sees how unstable a check is without seeing what it was judging.

### The interval, and the noise floor

On the `Score` itself, not in `metadata`: `samples` (the raw per-sample scores,
in order), `sample_min` and `sample_max`. **Absent when there is one sample** —
a suite left at `samples=1` writes the file it always wrote. They are fields
rather than three more keys in the bag because `compare()` reads them to decide
an outcome, and a rule that reads a stringly-keyed bag is a rule one typo
disables silently.

They travel, for the same reason `spread` does: they measure the system's own
variability, not what it judged.

`compare()` then reads them as a **noise floor**. After the declared tolerance,
a movement that lands inside the interval the *baseline* observed across its own
samples is `unchanged`, and the delta says so:

```python
delta.within_noise  # True when the interval is what called it unchanged
delta.noise_min, delta.noise_max, delta.noise_samples
```

`Outcome` gains no member — a movement within noise **is** `unchanged`, and the
fact rides beside it, in `--json` as in the report.

Four things it does not do:

- **it never rescues a flip.** `pass` → `fail` is rule 3 of `compare()` and
  sits above the numeric branch, so a drop through the threshold is reported
  whatever the samples did. It follows that the floor can never wave a failure
  through;
- **it reads the baseline's interval, never this run's.** The baseline is the
  promoted, reviewed measurement; letting a noisy new run widen its own excuse
  is how a regression hides inside a model that got less stable;
- **an interval of zero width is not a floor.** Five samples out of five — the
  ordinary case away from the boundary — leaves nothing to be inside, so every
  later change of mind is reported;
- **it invents nothing where there is no interval.** A baseline promoted before
  this release, or a suite at `samples=1`, keeps the absolute rule, and the
  report says the noise of that check is not known rather than implying there is
  none.

An **aggregate** has no samples of its own, so it gets an interval a different
way: the driver evaluates it once more per sample index — the sample-0 verdict
of every case, then the sample-1 verdict, and so on — and records those N values.
It costs no call to anything. The recorded score does not change: it is still
computed from the folded per-case verdicts, and the per-sample values answer a
different question whose only job is to size the noise.

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

### Per class: `by_group`

An aggregate over the whole run is an average, and an average carries a class that is
broken. `by_group=True` keeps the whole-run figure and adds one aggregate per group
present in the cases:

```python
run_assertions = (
    [
        Precision(
            over="agrees_with_mark", threshold=0.60, tolerance="3/20", by_group=True
        ),
    ],
)
cases = ([Case(id="art-01", label="positive", group="refunds"), ...],)
```

With three groups that is four verdicts, named `precision`, `precision[group=…]` — and
those names are a **public format**: they land in `Run.aggregate[].assertion` in every run
file and baseline, in `compare --json`, and in both documents.

| | |
|---|---|
| **All of them or none** | There is no `Precision(group="x")`, in Python or in TOML. The class that degrades is the one you were not watching, so watching a class you named is watching your own assumptions. |
| **The expansion adds** | The whole-run figure keeps its identity, its threshold and its baseline. `config_hash` still moves, because the new gates join it — so a baseline promoted before the flag is comparable but not promotable. |
| **Groups come from the cases** | Never from a declaration. A group exists because a case carries its name, and its aggregates are `new` or `missing` when that changes, like any other check. `diff()` refuses such a pair outright: a changed group set is a changed configuration. |
| **Same machinery, smaller set** | Thresholds, tolerance and the ADR 0006 §7 noise floor are inherited and computed over the group's cases. No new semantics anywhere. |

Two things to expect on a small class. The **declared tolerance goes quiet**: a tolerance
measured over twenty cases means nothing over three, where one case is a third of the
group — the measured floor is what still sizes itself to the denominator. And an aggregate
can **error**, where a class carries one label only and the denominator is empty. That is
not a malfunction: the suite asserted something the class cannot answer, and `error` is the
accurate report of it. It changes no exit code, exactly as it did before.

**A failing class beside a green pipeline is a legitimate reading.** `compare` gates on
*movement*: a class under its threshold in this run that was under it in the baseline is
`unchanged`, so nothing got worse and the exit code is 0. The threshold says the system
does not meet the bar; the comparison says it has not moved. The report prints that
sentence under the figures rather than leaving a reader to conclude it is a defect. The
`classifier` example ships exactly this, on purpose — see its README.

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
exist. A float that *does* land on one is accepted and reaches the same verdict as the
fraction: the gate compares at `FLOAT_PRECISION` like every other limit, so `0.666667` and
`"2/3"` agree (they did not before ADR 0009 §7 — the guard rounded and the gate did not,
so `0.666667` was accepted and then rejected two-of-three as `error`). **Write the
fraction anyway.** It says what it means, and it is the form that cannot be spelled
wrong. The refusal looks at the value, not the notation: `"2/4"` is as impossible with
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

The tolerance is the **declared** control and stays a judgement someone makes.
Beside it, a sampled check now carries a **measured** one — the interval its own
samples spanned in the baseline, see [the noise floor](#the-interval-and-the-noise-floor).
They are checked in that order, both produce `unchanged`, and the reason says
which one spoke. A tolerance that was set generously as a hand-rolled noise
floor can be tightened back to what a reviewer actually means to allow; nothing
forces it, and nothing breaks if nobody does.

### A tolerance that switches the check off

`compare` reads a flip between pass and fail before it reads the tolerance, so a
tolerance only ever judges a score that stayed on one side of its threshold. On
the passing side a score moves by at most `1 - threshold`. On the failing side it
moves by at most just under `threshold`. **A tolerance at least as wide as the
wider of the two holds every movement there is**, and the check speaks only when
it flips. That happens far lower than 1.0: at `threshold=0.5` a tolerance of
`0.5` is already there, and at `threshold=0.8` one of `0.799999`.

digline does not refuse it, because a tolerance is the suite's choice. It says
so, on stderr, where the suite is loaded: `digline run` prints one line per
such check, before the first call, and the exit code does not move.

```text
digline: tolerance 0.5 on 'loose' (threshold 0.5) covers every movement its score can make without crossing the threshold: compare will report this check only when it flips between pass and fail
```

`digline.core.tolerance_is_blind(threshold, tolerance)` is the rule, and
`digline.run.blind_tolerances(suite)` returns the checks it names, per case and
over the run. Two surfaces do not carry the line yet: the MCP `run` tool, which
has no stderr, and `pytest --digline-run`, for the reason
[the pytest page](pytest.md) gives about the `KIND` note (#396).

**Silence is not a clean bill.** Four ways to a blind check cannot be seen from a
threshold and a tolerance, and the line says nothing about them:

- **A tolerance wide for how the scores actually move.** `0.9` on a check whose
  scores move by `0.2` is as blind. Only the measurements show it: the procedure
  above.
- **Scores on a grid.** The rule assumes any score in `[0, 1]` can occur. A
  binary check folded over five samples scores `0, 0.2, … 1`, and at
  `threshold=0.5` a tolerance of `0.4` already holds every move on either side.
  `examples/classifier` declares exactly that, on purpose.
- **The noise floor.** A second way to `unchanged`, measured from the baseline's
  samples and never declared. A baseline whose samples spanned 0 to 1 blinds the
  check the same way, and no declaration can show it.
- **A threshold that moved between the baseline and this run.** The sides are
  drawn at the suite's threshold. A baseline measured under another one has
  sides of its own, and `compare` reports that change as a loosened rule.

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

**`KIND` is optional on a check of your own.** Every check `digline.core` ships
declares what kind of check it is, as a class variable:

```text
KIND: ClassVar[CheckKind] = "deterministic"
```

| `KIND` | Means |
|---|---|
| `deterministic` | The same output always gets the same verdict. |
| `judged` | A model decides, so the verdict is noisy by construction: `LlmRubric`, `Faithfulness`. |
| `budget` | A declared ceiling on cost or latency, scored graded rather than pass/fail — `cap / (cap + measured)`, `0.5` exactly at the cap — so drift under the cap stays visible to `compare()`. Over the cap the verdict fails, whatever the score rounds to: `CostBudget`, `LatencyBudget`. |
| `aggregate` | One verdict about the whole run, from every case's outcome: `Precision`, `Recall`, `Accuracy`, `F1`. |
| `wrapper` | Its nature is the thing it wraps: `Repeated`, and `FromAutoevals`, whose scorer may or may not call a model. |

The list of checks the home of digline.dev shows is built from it, and since
0.14.0 digline reads it in three more places — **optional, but no longer
unread**:

- a [calibration case](#casecalibration-watching-the-judges-scale) may only name
  a check whose `KIND` is `judged`, and `rejudge --judge-samples` asks only
  those checks again;
- a verdict of a `judged` check is written with `"judged": true`, which is what
  `explain`'s shape reading reads;
- **a check whose class declares no `KIND`** — read through `Repeated` — is left
  out of that reading, and `digline run` names it on stderr on every run:

  ```text
  digline: max_words declares no KIND, so the shape reading leaves it out; declare KIND = "judged" or "deterministic" on its class to have it read
  ```

  Nothing fails without it; the line is there so the exclusion is never silent.

**The known hole: `FromAutoevals`.** It declares `wrapper` and wraps a scorer,
not an assertion, so there is nothing to read through. An autoevals scorer that
calls a model is therefore **neither judged nor announced**: the shape reading
cannot see it at all, and nothing on your terminal says so. Closing it needs the
adapter to declare what its scorer is, which is a decision of its own and has not
been taken.

It is a `ClassVar`, not a field, so it never enters `identity` or
`config_hash`: declaring it, or changing it, leaves every stored baseline paired
and promotable. `MaxWords` above works without it, and is announced.

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

### A judge that cannot answer

Since 0.16.0 a judge can **decline** rather than invent a score. It raises
`JudgeAbstained(reason)`, imported from `digline.core`, and the check is
`error` carrying the judge's own sentence — *the judge declined to score: …* —
instead of our sentence about a judge that blew up.

The shipped `ScoreJudge` and `ClaimCountJudge` raise it when the model's reply
declares it, and only then:

```json
{"abstain": true, "reason": "the answer is a refusal, so there is nothing to score"}
```

Three rules, and they are the contract rather than an implementation detail:

- **`abstain` absent is not an abstention.** A judge that never declines
  behaves exactly as it did: a missing `score` and a `"score": null` are still
  broken replies.
- **A value that is not `true`/`false` is a broken reply**, not a declining.
- **`reason` is mandatory.** A declining with no reason is refused, because the
  sentence is the whole of what an abstention is worth.

A reply that declines *and* scores has declined: a judge that supplied both has
not scored.

Declining is not a low score. `0` says the output was read and failed the
rubric; declining says it could not be read against the rubric at all. For
`ClaimCountJudge` the distinction is sharper: an output that asserts nothing is
`"total": 0`, which is an answer, while declining says the judge could not tell
what it asserts. (ADR 0004 §7)

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

## The run that was killed

A run is written once, at the end. That used to mean a suite killed part way
through — a supervisor, a memory-pressure reaper, `Ctrl-C` — lost every call it
had already paid for.

digline now keeps a **journal** beside the run while it goes:

    .digline/<tenant>/runs/<suite>/.pending/<run key>.<leg>.jsonl

One record per **case**, written and `fsync`ed before the next case starts, in
the same directory the runs live in and therefore covered by the same
`.gitignore`. It holds exactly what the finished run file would hold and nothing
more — a suite that does not record its answers does not journal them either —
and it is **deleted the moment the run file exists**. A completed run looks
exactly as it did before.

To finish one:

```console
$ digline run --suite suite.py --resume
digline: tenant 'northwind' · 112 of 144 cases × 5 samples = 560 calls to the target; 32 cases already judged
2026-09-11T09-14-02-000000-00-00-81c684c28b62
```

With no key it takes the most recent unfinished run; `--resume KEY` names one.
A plain `digline run` never resumes, and says on stderr that a journal is
pending so the calls in it are not abandoned by accident.

**A resumed run is not marked as one, because there is nothing to mark.** It
carries the `created_at` of the run it finishes, writes the file that run was
going to write, and states nothing that is untrue of either half. That is
guaranteed by the refusals rather than assumed: a resume is refused, before the
first call of the new leg, when any of these has moved since the run started —

| | |
|---|---|
| `config_hash` | thresholds, tolerances, `samples`, `min_agreement`, the aggregates |
| the cases | their ids, data, labels, groups and order |
| the artifacts | the prompt is the thing under test, and it is digested |
| `target_config`, `judge_config` | a different model, temperature or endpoint answered |
| `record_responses` | the document would carry answers for half its cases |
| `git_commit`, the digline version | the code around the suite, and the engine |

Half a run under one prompt and half under another is not a run.

**An alias that rolled between the halves errors, it is not averaged.** What the
provider said answered is journalled as it is learnt and given back to the target
and the judges on resume, so a model that changed across the seam raises on the
first call of the new leg exactly as it would have on the next call of the old
one: that case errors, the run is still written, and it exits 2 and cannot be
promoted (ADR 0005 §8).

**Errored cases are retried.** An errored verdict exits 2 and cannot be
promoted, so a resume that kept them would finish a run nobody can use — the
usual cause is a provider that stopped answering, not a suite that stopped
meaning anything. `--keep-errors` keeps them as journalled.

For a script that drives digline itself, the four steps are one call:

```python
from digline.host import measure, prepare

prepared = prepare(
    suite,
    target,
    now=utc_now_iso(),
    git_commit=commit,
    artifacts=artifacts,
    resume=None,
)
print(prepared.plan.sentence())  # say what it will cost, first
measured = measure(suite, target, store=store, prepared=prepared)
print(measured.ref.key)
```

`prepare()` decides what the launch is and refuses a resume that would not be
one; `measure()` opens the journal, runs, writes and deletes it. Underneath,
`execute()` gained `done=` — results it must not call for — and `on_case=`, a
callback per finished case. The driver still knows nothing about the store.

The reasoning in full is
[ADR 0017](adr/0017-the-journal-and-the-resumed-run.md).

## The name table's directory

The name table maps the tokens in a projected reference back to the text they
stand for ([ADR 0036](adr/0036-the-name-table-and-the-process-that-owns-it.md)).
**digline does not write it.** The process that owns the table does, in a
format of its own, and hands digline two callables. The table still lives in
the tenant's directory, like everything else in the perimeter, under one
reserved name:

    .digline/<tenant>/name-table/

A program outside digline reaches it from a store:

```python
from digline.store import FileResultStore

store = FileResultStore(project_root)  # the directory that holds .digline/
where = store.name_table_dir("northwind")  # .digline/northwind/name-table/
where.mkdir(parents=True, exist_ok=True)  # the owning process creates it
```

`name_table_dir` checks the tenant the way every tenant is checked — one safe
path segment, so `..` or `a/b` is refused with `PathRefusedError` — and returns
the path. It creates nothing, does not resolve links, and reads nothing.

**What the reservation holds, and how.**

- **The name is a directory, not a file.** A table kept in SQLite is at times
  several files: `-journal` while a transaction is open, `-wal` and `-shm` in
  WAL mode. Every one of them, and anything another engine keeps, sits inside
  the directory, so one name covers them all.
- **digline writes nothing under it and reads nothing from it.** Nothing is
  refused at run time, because nothing needs to be: every path digline builds
  goes through `baselines/`, `runs/` or `register/`, and none walks the
  tenant's directory. A test keeps that true, with a planted SQLite file and
  its companions left byte for byte unchanged through a run and a promotion.
- **It is kept out of git.** The table is the re-identification key and is
  never committed. The `.gitignore` digline generates in `.digline/` ignores
  `*/name-table/`. **A `.gitignore` generated before this rule existed does not
  have that line, and digline never rewrites one that is already there**:
  add `*/name-table/` to it by hand before the table is written.

What is inside the directory, its format, its lock and its retention are the
owning process's. `tenant_dir` is not documented and stays internal: the
reserved directory is the only part of a tenant's layout a program outside
digline is given.

## Reading and promoting from a program

A program that drives digline reads a run, reads a baseline and promotes, and
catches what digline refuses. These are the names it does that with. Each one
is published by name: listing a class above does not make its methods public.

```python
from digline.host import REFUSALS, load_suite, promote, resolve_key, utc_now_iso
from digline.store import FileResultStore, RunRef

suite, loaded = load_suite("suite.py")
store = FileResultStore(project_root)
try:
    key = resolve_key(store, suite, "latest").key
    run = store.read_run(RunRef(tenant=suite.tenant, suite=suite.name, key=key))
    baseline = store.read_baseline(suite.tenant, suite.name)  # None: first round
    reference = promote(
        store,
        loaded,
        key,
        target=None,  # the suite's own target; a spec names another
        replacing="none",  # or the baseline key compare printed
        promoted_at=utc_now_iso(),
    )
except REFUSALS as refused:
    print(refused)  # a sentence written for a reader
```

### Reading: `read_run` and `read_baseline`

- **`FileResultStore.read_run(ref)`** returns the `Run` stored under a
  `RunRef`. It refuses `RunNotFoundError` when there is no such run,
  `PathRefusedError` for a name that is not one safe path segment or a file
  that leads out of the store, `TenantMismatchError` or `SuiteMismatchError`
  when the document names another tenant or suite than the address it was
  read through, and `DocumentRefusedError` for a document this version cannot
  read.
- **`FileResultStore.read_baseline(tenant, suite)`** returns the baseline, or
  `None` when the suite has none yet in that perimeter. The first round is not
  an error. It refuses the way `read_run` does, and one way more:
  **`NotAReferenceError`** for a projected document that is not a reference,
  one with no `promoted_at` or with answers. That is a served projection
  standing where a reference belongs
  ([ADR 0038](adr/0038-the-projection-of-a-run-nobody-promoted.md) §1).

### Listing: `suite_runs`

**`suite_runs(store, tenant, suite, *, mint)`** returns a suite's runs and
the key of its baseline: the list the first screen of `digline view` shows, for
a program that shows it somewhere else (#276). It returns a **`SuiteRuns`**:

- `runs`: `(key, run)` pairs in key order, which is chronological. A key is
  what `RunRef(tenant=..., suite=..., key=key)` takes, so `read_run` needs
  nothing more.
- `baseline_key`: the key the baseline is known by, the one a row is marked
  with. `None` when there is no baseline, **or** when one is there and could
  not be read. `baseline_refused` tells the two apart. It is empty for the
  first and holds what refused the read for the second.
- `skipped`: how many files the scan left out for their schema, by version.
- `unreadable_count`: how many files this version cannot place at all. A
  **count**: `Listing.unreadable` is the file names, and the two are named
  apart so that one is not read for the other.
- `advice()`: what to do about `skipped`, in the direction the versions say.
- `listing`: the store's scan as it returned it, **in clear only, and
  deprecated**. It is `None` on a projected list, because its `runs` and its
  `unreadable` are file names, which a projected list keeps off the page.
  Read `skipped`, `unreadable_count` and `advice()` instead, in either
  regime. It stays in clear for now because a published `digline-mcp`
  passes it to `runs_json`, and it is removed in a release of its own (#362).
- `refused`: `(key, what refused it)` for each run the scan found and the read
  did not show. **One run the store refuses does not take the others down.**
- `unnamed`: on a projected list, how many files were left out **without a
  name**, because their only name is a file name that is not a run key. Always
  0 in clear.
- `note()`: one line naming everything above that was left out, and a
  baseline whose run is not in the list. Empty when there is nothing to say.
  **An empty note does not mean nothing is missing**: a run removed from the
  store is named only where the baseline remembers it, as with `resolve_key`.
  - It is in English, for a terminal and for `--json`.
  - It names three refused runs and counts the rest. Every one is in
    `refused`.
  - It is true beside the list and beside one case's history alike.

**`left_out(listed, *, locale)`** is that line as a document shows it, in the
document's language. `locale` is mandatory, with no default, as on
`render_html`. Only the frame is translated: in clear, a refusal's sentence is
the store's and stays in English. It adds what to do about runs skipped for
their schema, which `note()` leaves to `advice()`, because a page has
no second line to put it on. `digline view` shows it under the list and under a
case's history (#339).

Each `run` in `runs` is a `Run`, a frozen dataclass. These are the fields a
list of runs reads:

- `created_at`: when the run was made, an ISO 8601 UTC timestamp with
  microseconds. Where digline wrote the run's file, its key begins with it.
- `environment`: where inside the perimeter the run was made, as the suite
  declared it ([`Suite`](#suite)).
- `results`: one `CaseResult` per case the run holds.
- `aggregate`: the verdicts about the run as a whole
  ([aggregates](#aggregates-the-verdict-on-the-run)), each a
  [`Verdict`](#verdicts-and-comparison). Empty when the suite declares none.

**It opens every document.** Aggregates are in the run, and the store keeps no
index, so every stored run is parsed in full. That is what `digline view` pays
for the same screen.

**`mint` is mandatory, with no default.** `None` lists in clear. A
[`Minter`](#the-projection) lists projected: every run goes through
`project_served`, and through **one check on the minter for the whole list**.
One name gets one token on every row, which is what lets a row's aggregates be
held against the baseline's by name.

- **A run that cannot be projected is left out and named by its key, never
  shown in clear.**
- **A key is the name of the file the run is stored in.** Where digline wrote
  the file, the name is a time and a digest, which the projection leaves
  alone, so it names nothing. A file somebody named otherwise is treated two
  ways:
  - **in clear**, it is listed and refused under its file name, which is what
    `read_run` needs to read it;
  - **projected**, a file name is shown only where it names nothing. A readable
    run is listed only if its file name is its `key_of`. A refused file is
    named only if its name has a run key's form. Everything else is counted in
    `unnamed` and named nowhere, control characters included.
- **That repairs the page, not the store.** The store answers *what is a run's
  key* two ways, the file's name and `key_of`, and `--run latest` fails on a
  renamed newest run for that reason. That is #332, and an ADR is owed.
- **On a projected list, `refused` and `baseline_refused` carry the refusal's
  type, not its sentence**, because a sentence can quote a name.
- **A minter that answers wrong refuses the whole call**, as
  `ProjectionRefusedError`: an answer without a token's form, one name given
  two tokens, or two names given one, anywhere in the list. So does anything
  the minter raises. digline never opens the table; it calls what it is handed
  ([ADR 0036](adr/0036-the-name-table-and-the-process-that-owns-it.md) §2).
- **One minter is not proved to be one table.** Nothing on a projected
  document says which table minted it, and that is ADR 0036's open question.

`PathRefusedError` is raised when `tenant` or `suite` is not one safe name.
A suite with no runs is an empty list, not a refusal. A run directory that
exists and cannot be opened is not an empty list: it raises
`DirectoryUnreadableError`, because nothing in it was read (#365).

`scan_runs` and `list_runs` stay internal. `suite_runs` is the read for a
program that shows runs. `resolve_key(store, suite, "latest")` is the one for a
program that needs only the newest.

### One case across runs: `case_history`

**`digline.report.case_history(runs, case_id)`** folds `(key, run)` pairs
into one case's history, oldest first, as a **`CaseHistory`** of
**`CaseEntry`** rows. It is the table `digline view` shows at `/case/<id>`, and
its input is the list `suite_runs` returns (#278):

```python
from digline.host import suite_runs
from digline.report import case_history

listed = suite_runs(store, tenant, suite, mint=None)
history = case_history(listed.runs, case_id)
print(listed.note())  # what the history does not cover
```

On a page, show `left_out(listed, locale=...)` there instead.

Both are frozen dataclasses. A **`CaseHistory`** carries:

- `case_id`: the case it follows, as it was asked for: a name in clear, or a
  token on projected runs.
- `entries`: one `CaseEntry` per run given, oldest first.

A **`CaseEntry`** is how one run judged the case:

- `run_key`: the key the run was given under, the one `suite_runs` lists it
  by. `RunRef(tenant=..., suite=..., key=entry.run_key)` reads that run, so a
  row is tied to its run by this field and not by its position. It is the key
  as given: `case_history` does not check it against the run.
- `created_at`, `environment`, `config_hash` and `git_commit`: the run's own,
  copied from it. `git_commit` is `None` where the run was made with no git.
- `verdicts`: the case's verdicts in that run, each a
  [`Verdict`](#verdicts-and-comparison). Empty when the run had the case and
  judged nothing, and when the run does not have the case.
- `suspended`: why the case was set aside in that run, or `None` when it was
  not. On a redacted or projected run the reason is withheld, and a
  placeholder stands in its place. This is what tells an empty row apart: a
  case that was suspended, and not merely unjudged.
- `present`: `False` when the run does not contain the case at all.

- **The order is the rule:** `created_at`, then the key, so two renderings of
  one history put the rows in the same order.
- **A run the case is not in is a row with `present=False`**, not a missing
  row. A case added or removed shows as a gap.
- **The history covers the runs it was given, and only those.** A run the
  read left out is no row at all, and the rows around it close up, so the gap
  reads as continuity. What was left out is in `SuiteRuns.note()`, and in
  `left_out` for a page. **Whoever shows a history shows that line beside
  it.**

It refuses, as `DifferentRegimesError`, two ways:

- runs of which some are projected and some are not;
- projected runs and a `case_id` that is not a token. A name in clear matches
  no token, so every row would read `present=False`, which says *this case is
  in no run*. On a projected page, ask for the case by the token its links
  carry. A caller holding the name gets the token from its own minter.

**Runs in clear and an id with a token's form are not refused.** A case id is
free text, and that form is a legal one.

### Setting a case aside: `suspension_snippet`

**`digline.report.suspension_snippet(case_id, reason)`** returns the line that
suspends a case, `Case(id='...', suspended='...')`, for a person to add to the
suite and commit (#279). It is the line `digline view` shows at
`/suspend/<id>`. digline produces it and never applies it: `Case` is Python in
the user's repository, and a suspension is a decision about the suite, so it
goes through the review every other one goes through.

```python
from digline.report import suspension_snippet

line = suspension_snippet(entry_case_id, "flaky since the 2026-09 model update")
```

- **Both strings go into the line through `repr`**, so the line parses back
  to the same case id and the same reason, whatever either holds: quotes,
  backslashes, line breaks. That is the reason to call this rather than build
  the line by hand: a copy of the quoting is a copy of a rule about what
  reaches a file under review.
- **On a projected document the line carries a token.** The `case_id` there
  is the token the page's links carry, and the line puts it in the suite as
  if it were the case's name. So the line is usable as it stands only where
  the store is in clear. Where the runs are projected, the line names a case
  no suite has.

The page `digline view` serves the line on, `digline.report.pages.suspend_page`,
stays internal: its navigation links to `digline view`'s own screens.

### The first round: `render_run_html`

**`digline.report.render_run_html(run, *, locale)`** renders one run on its
own: the document `digline report` writes when the suite has no baseline yet
(#277). `read_baseline` answers `None` on a first round, and `render_html`
cannot take that `None`.

```python
from digline.core import compare
from digline.report import render_html, render_run_html

baseline = store.read_baseline(tenant, suite)
if baseline is None:
    document = render_run_html(run, locale="en")  # look first, then promote
else:
    document = render_html(compare(run, baseline), run, baseline, locale="en")
```

- **It is the same document as `render_html` wherever a section is about the
  run**: the header, the aggregates, the files under test, what answered and
  what judged. Where a section was about two runs, it says there is no
  reference, and groups the cases by what each verdict is.
- **It is not a verdict.** There is no headline, because "worse" is a relation
  and there is nothing to be worse than.
  - `digline report` still exits `2` on a first round with an unjudged case or
    a lost scale. A program gets the same number from
    [`run_exit_code(run)`](#the-exit-code-exit_code-and-run_exit_code).
- **`locale` is mandatory**, for `render_html`'s reason: the document has a
  recipient.
- **On a projected page, project first**: `project_served(run, mint)`, or
  `suite_runs(..., mint=...)`. The document names nothing. Its header says
  it is redacted, and **beside that, that its names were replaced by strings
  and are kept by the data owner** (#313). A configuration parameter whose
  value was kept back still shows as a string and *not included*, even where
  the parameter is one of digline's own: that is #323.

It is not a way to skip the reference. A run with a baseline can be rendered
on its own, and that is a look at the run, not a comparison.

### The exit code: `exit_code` and `run_exit_code`

The number `digline compare`, `report` and `explain` exit with, for a program
that shows a run and has to say whether it passes (#318). Both are in
`digline.wire`, both are pure, and neither needs a store or a suite:

```python
from digline.core import compare
from digline.report import headline
from digline.wire import exit_code, run_exit_code

baseline = store.read_baseline(tenant, suite)
if baseline is None:
    code = run_exit_code(run)  # a first round
else:
    code = exit_code(headline(compare(run, baseline), run, baseline, locale="en"))
```

| Code | Constant | Means |
|---|---|---|
| `0` | `EXIT_OK` | proceed |
| `1` | `EXIT_WORSE` | a check got worse, or a canary moved |
| `2` | `EXIT_UNJUDGED` | a case could not be judged, a calibration case left its band, or a pinned file drifted from the reference |

- **`exit_code(head)` is the rule**, read from a `Headline`. A regression or a
  moved canary outranks the causes of `2`. A suspension never fails. That
  rule was never deliberated: it arrived with the first commit and no ADR
  rules on it. So a run whose cases are **all** suspended exits `0` too, and
  whether it should is open on
  [#360](https://github.com/digline/digline/issues/360). The headline's
  `locale` does not change the number.
- **`run_exit_code(run)` is the same rule with nothing to compare against.**
  It never returns `1`, because *worse*, a moved canary and a drifted pin are
  relations. What is left is `2` for an unjudged case or a lost scale, read
  from the run alone.
  - **It is held to `exit_code` by a test**: for any run, it equals `exit_code`
    of the run compared with itself, in clear, redacted and projected.
  - `digline report` and `digline explain` compute their first-round code
    through it, so a program and the CLI cannot disagree.
- **On the wire**, `compare --json` and `explain --json` already carry the
  same number as `exit_code`, and MCP's `compare` and `explain` tools too.

### Promoting: `promote`, and why not `promote_baseline`

`promote(store, loaded, key, *, target, replacing, promoted_at)` makes the run
`key` the baseline of the suite `loaded` holds, and returns the reference it
wrote. That is the value a projection starts from
([ADR 0034](adr/0034-the-store-outside-and-the-reference-that-names-nothing.md)
§2).

- `key` is a run key. `latest` is refused: resolve it with `resolve_key`, which
  also returns the note on what its scan skipped.
- `target` is the spec of the target the run was measured with, as `--target`
  takes it, or `None` for the suite's own. **It is a parameter because only
  the caller knows which target was measured.** A suite with several targets
  would otherwise sign a run of one system as the reference for another
  ([ADR 0022](adr/0022-the-declared-price.md) §5).
- `replacing` is the reference this promotion replaces, as `compare` printed
  it: a key, or `none` where the suite has no baseline yet
  ([ADR 0031](adr/0031-the-reference-promote-replaces.md)).
- `promoted_at` is the signature's time, read by the caller: `utc_now_iso()`.

It refuses every condition `digline promote` refuses, because it is what
`digline promote` calls. The conditions are the ones
[ADR 0002](adr/0002-three-worlds-and-where-the-data-lives.md) §8 collects,
plus the moved reference from ADR 0031. The last one checked is
`BaselineMovedError`, raised when the baseline changed after `compare` read it.

**`FileResultStore.promote_baseline` is not documented, and that is on
purpose.** It takes the configuration hash the run must match as an argument.
That hash is the suite's, over the price of the target measured, and the value
a caller finds in reach is the run's own `config_hash`. Passed that value, the
check compares the run with itself and passes every time. `promote` takes what
the suite was loaded as and computes the hash itself, so there is nothing to
pass wrongly. A program that implements a store of its own meets
`promote_baseline` on the `ResultStore` protocol, and what that protocol owes
is documented there.

### `Loaded`: what `load_suite` returns

`Loaded` is the second value `load_suite` returns, and it is published as an
**opaque value**. Keep it and pass it back to `load_target` and to `promote`.
What is committed is its name and that path. Its fields are internal.

Until it was named here, `load_suite` returned it and `load_target` took it,
both documented, while the type itself had no name on this page. Publishing
it closes that gap too: `load_target` no longer takes a type the page does not
name.

### `REFUSALS`: what to catch

`REFUSALS` is a tuple of every exception class digline raises on purpose, with
a sentence written for a reader. Anything else that escapes digline is a bug
and should travel as one. What it commits to:

- **Complete.** Every refusal digline defines is in it, and a test fails on
  one that is not. digline's own command line, `digline view` and
  `digline-mcp` all catch this tuple, and nothing narrower.
- **Named, never copied.** Write `except REFUSALS`. The tuple is read from the
  installed digline, so a refusal added in a later version is caught without
  your code changing. A copied list is how a refusal once reached a person as
  a closed connection.
- **A class leaves it only with a changelog entry.** Adding one is an ordinary
  change. Removing one would stop your code from catching it without anything
  turning red, so it is announced as a break.
- **The message is for a reader inside the perimeter.** It can name the
  tenant, the suite, a path or a run key. Whether to show it across a boundary
  is up to the program showing it.

It is a tuple because `except` takes a class or a tuple of classes, and nothing
else. It is meant for catching, not for extending. To catch your own errors
beside digline's, compose them: `except (*REFUSALS, MyError)`. digline's
command line does the same with `ValueError`. No program outside digline has
needed digline's front ends to show one of its errors as a refusal. **If a
plugin ever does**, the form is a common base class the refusals inherit,
which can be added without breaking a caller of the tuple.

`NOT_REFUSALS` is exported beside it and is not documented. It is the other
half of the classification's bookkeeping and stays internal.

## What `--json` promises

`digline compare --json` and `digline run --json` print an object whose first
key is `output_version`, currently `2`. It is bumped when the shape changes and
is **not** `SCHEMA_VERSION`: that one versions documents already on disk and
comes with migrations, because a run file written last month must still be
readable. This one versions what a pipeline parses on stdout today, where
nothing is migrated and the only question is whether the consumer knows the
shape moved. A reworded sentence must not bump the storage schema, and a new
field inside a `Run` must not bump the output contract for consumers who saw no
change.

**Version 2 is the first bump, and the first change that is not an added key.**
Every earlier addition was something a consumer could ignore while parsing the
same bytes it parsed before. This one rewrites bytes inside values you already
read: DEL (U+007F) and the C1 block (U+0080–U+009F) are written as their JSON
escape spelling — six ASCII characters where there used to be one — in every
string digline renders for a program, keys included. So a pipeline that pulled a
control character out of a provider-supplied string, such as a tool name or a
model id, now reads `\u009b` where it used to read the character itself. Nothing
else moves: no key added or removed, no number changed, and any text without
those two ranges is byte-identical.

The reason is that the same fact must not read differently at two front ends.
`digline-mcp` hands its documents to an SDK that serialises them itself, so
escaping the finished text — which is what the CLI used to do, invisibly to a
parser — could never cover it, and a tool name carrying U+009B reached an MCP
client raw. The only surface both front ends share is the value.

At version 1, `compare --json` carries `worse`, `unjudged`, `suspended`,
`config_changed`, `artifacts_changed`, `target_config_changed`,
`judge_config_changed`, `within_noise`, `counts`, `reasons_available`,
`sentence` and `exit_code`; `--json full` adds `deltas`, `target_config_deltas`,
`judge_config_deltas` and `shape`.

`exit_code` is the number the process exits with, in the object — the same
`0` / `1` / `2` a shell sees, computed by the one function that knows a
regression outranks an unjudged case. It is there because the same object is
returned by the MCP server's `compare` tool, which has no process to exit, and
a caller made to re-derive it from `worse` and `unjudged` would have to know a
precedence rule it should never have to think about. `digline diff --json` has
no such field and must not: neither side of a diff was approved by anybody, so
there is nothing to gate on. A golden key set in the tests fails the build if a key is
added without the bump — *added* keys leave a consumer working, which is why
these arrived without one. Each delta carries `within_noise`, `noise_min`,
`noise_max` and `noise_samples` beside its outcome.

## Verdicts and comparison

`Verdict(score, threshold, status, reason, tolerance, *, assertion_id)` with
`status` in `"pass" | "fail" | "error"`. `passed` is derived. It is not possible
to build one that contradicts itself: a `status` disagreeing with
`score >= threshold` is refused. `assertion_id` is keyword-only and has no
default. An empty one is refused with `UnidentifiedVerdictError`, which is in
`REFUSALS`: it is what `compare()` pairs on, and one derived from the name would
pair verdicts that were never the same check. An assertion built on
`AssertionBase` passes its `identity` and never meets it.

`Verdict` and `Score` are frozen dataclasses. Beside the constructor's
arguments, a **`Verdict`** has one field more:

- `judged`: `True` when a model placed the score on its scale, meaning the
  check's `KIND` is `judged`. The driver stamps it and an assertion never sets
  it. It is a copy of a declaration, not a measurement: no comparison, gate or
  exit code reads it, and it is outside `assertion_id` and `config_hash`.

A verdict's **`Score`**, `verdict.score`, carries:

- `name`: the check's name, never empty. It is what a table of results heads
  a column with. On a projected run it is a token.
- `score`: the number, between 0 and 1, or `None` when there is no score. A
  `None` is never a pass: the verdict that carries it is `error`.
- `metadata`: what the assertion measured
  ([the keys sampling adds](#what-the-numbers-mean)).
- `samples`, `sample_min` and `sample_max`: the per-sample scores and the
  interval they span, empty and `None` with one sample
  ([the interval](#the-interval-and-the-noise-floor)).
- `sample_means`: `True` when each of `samples` is itself a mean of
  judgements, as when a sampled suite runs a `Repeated` check. Never declared:
  the fold stamps it, and only together with `samples`.

`compare(run, baseline) -> Comparison` returns one `AssertionDelta` per verdict,
with outcome `regressed`, `improved`, `unchanged`, `new`, `missing`, `errored`,
plus one `ConfigDelta` per configuration parameter on either side — `field`,
`outcome`, `before`, `after` — under `target_config_deltas` and
`judge_config_deltas`. A parameter withheld at a boundary, and every parameter
on a baseline that predates ADR 0005, reports `unknown`: neither is a change, so
a baseline promoted last month keeps comparing without being promoted again.
The rules apply in this order: presence on one side only, then error, then a
change of outcome (**regardless of the tolerance**), then the declared
tolerance, then the measured noise floor — see
[the interval](#the-interval-and-the-noise-floor). The last two both produce
`unchanged`, and `within_noise` on the delta says which one spoke.

### Boundaries

**Every limit in digline is compared at `FLOAT_PRECISION`, and every limit is
inclusive.** One rule, no exceptions — a value sitting exactly on a limit is on
the passing side of it, and the comparison reads the numbers as the document
stores them, never the residue underneath.

What that means at each limit:

- **the threshold**, per case, per aggregate, per group and per sample, is
  `score >= threshold`: a score exactly equal to the threshold **passes**;
- **the declared tolerance**, on a delta, is `abs(delta) <= tolerance`: a
  movement exactly equal to the tolerance is **`unchanged`** (and `same` under
  `diff`);
- **the measured noise floor**, on the baseline's interval, is
  `sample_min <= score <= sample_max`: a score exactly on either end of the
  interval is **within noise**, so `unchanged` with `within_noise` set;
- **a budget** is `measured <= cap`: a cost or a latency exactly at its ceiling
  is **within budget**, and scores exactly `0.5`;
- **`min_agreement`** is `agreement >= min_agreement`: samples that agree
  exactly as much as you asked for **agree**.

Because the rule reads the stored numbers, it is decidable from the document in
front of you. A delta of `0.047619` against a tolerance of `0.047619` is
`unchanged`, and stays `unchanged` whether or not either run has been through
the disk — the arithmetic underneath cannot answer differently from the six
decimals you can see.

The live example is one run of the public `brief` fixtures, pinned at
[`c9d86ff`](https://github.com/digline/brief/blob/c9d86ff22d68d3df458fa0da81348ec962d16aa7/fixtures/README.md):
the baseline's `precision`, re-evaluated at sample index 1, scores exactly
`0.600000` against a threshold of `0.600000` and passes.

`digline.core` exports the rule, so an assertion of your own compares the way
the built-in ones do:

```python
from digline.core import meets, within, at_precision, STORAGE_STEP

meets(0.7, 0.7)  # True  — a score meeting its threshold
within(0.047619, 0.047619)  # True  — a delta within its tolerance
at_precision(1 / 3)  # 0.333333
STORAGE_STEP  # 1e-06, one unit at storage precision
```

Why it is stated once rather than at each call site, and what it cost to adopt,
is [ADR 0009](adr/0009-boundary-semantics.md).

#### Writing an agreement

`min_agreement` accepts `"2/3"` and `0.666667` alike, and both now reach the
same verdict. **Write the string.** An agreement is a count of samples over a
count of samples; `"2/3"` says that, and `0.666667` is a rendering of it that a
reader has to decode. The string form is also the one that cannot be spelled
wrong: a float that no `k/n` can produce is refused, and with three samples
`0.666666` is one such value.

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

`Disclosure(artifacts=True)` lets the declared files travel; the default keeps
them, digest and all. There is deliberately **no** member for `base_url`: a
model id and a temperature are measurements and always travel, while an endpoint
host is topology and is always withheld, appearing in the document as
`"withheld": ["base_url"]` and in a comparison as `unknown` — one special field,
one existing rule, no switch to forget (ADR 0005 §2).

## The projection

When the end company keeps the store, the reference a software house commits
is a **projection** of it: the promoted run, redacted, with every name
replaced by a token ([ADR 0034](adr/0034-the-store-outside-and-the-reference-that-names-nothing.md)).
It is produced **inside the process that owns the name table**, which is not
digline's ([ADR 0036](adr/0036-the-name-table-and-the-process-that-owns-it.md)
§7), so this is the part of digline that process calls:

```python
from digline.core import Minter, TokenKind, project, run_to_json


def mint(
    kind: TokenKind, text: str
) -> str: ...  # look (kind, text) up in the table; mint a token if it is absent


reference = store.promote_baseline(...)  # or digline.host.promote
document = run_to_json(project(reference, mint))
```

**`project(run, mint)`** returns a `Run` with `projected` and `redacted` both
set. It writes nothing, commits nothing, and does not know where the document
goes. It starts from the reference a promotion returns, never from a
comparison (ADR 0034 §2).

**`Minter`** is `Callable[[TokenKind, str], str]`: the token for a name,
minted if the table has none. digline never mints, stores or resolves a
token. A token is 22 characters of url-safe base64, 128 random bits from
`secrets` (ADR 0036 §5), and the minter is keyed by kind *and* text, so equal
text in two kinds gets two tokens.

**`TokenKind`** names what each token stands for: `case_id`, `group`,
`verdict_name`, `calibration_check`, `artifact_path`, `target_config_key`,
`target_config_value`, `judge_config_key`, `judge_config_value` and
`judge_identity`. The group inside `family[group=…]` is tokenised apart from
the family, so the name still parses. Configuration keys are tokenised
wherever they appear, in `values` and in `withheld`. Numbers stay as they
are: ADR 0034 §4 has not decided them.

**The order is part of what it is.** `project` redacts first, with no
`Disclosure`, and only then replaces names. The perimeter fields — `base_url`,
`fingerprint`, and `resolved_model` wherever `base_url` names an endpoint —
are withheld while their keys are still text. The other order would carry them
across under tokens, and nothing on the projected document could see it.

**`ProjectionRefusedError`**, in `REFUSALS`, is raised for:

- a run that is already projected;
- a run that is not a promoted reference: no `promoted_at`, or recorded
  answers still on it. **This reads what the document says**; a `Run` built
  by hand with a stamp and no answers passes;
- an answer from `mint` without a token's form, one name given two tokens, or
  two names given one token, within one call. **The first is a check of form**:
  a minter that echoed a 22-character name back would pass it;
- an identity on the target side, which no kind covers;
- a verdict whose `assertion_id` is not a digest. The `Assertion` protocol
  lets `identity` be any string, and one written by hand as readable text
  would cross the projection in clear. The refusal says to derive it with
  `dataclass_identity`, which is what `AssertionBase` does.

### A page, not a commit: `project_served`

**`project_served(run, mint)`** projects a run for a page served at the data
owner's side, **promoted or not**
([ADR 0038](adr/0038-the-projection-of-a-run-nobody-promoted.md)). It is the
same projection, made the same way, without the two refusals that belong to
the committed file: a run nobody promoted is projected, and recorded answers
become withheld placeholders, so their count crosses. Promotion's refusals are
not applied either, because an errored, replayed or unreconciled run is what a
reviewer most needs to see.

```python
from digline.core import project, project_served

shown = project_served(store.read_run(ref), mint)  # a page
reference = project(store.read_baseline(tenant, suite), mint)  # a commit
```

- **`project` is `project_served` with those two refusals in front.** For a
  reference, both return the same document.
- **It refuses everything else `project` refuses**: a run already projected, a
  target-side identity, a readable `assertion_id`, and a minter that answers
  wrong.
- **What tells its document from a projected reference** is what the document
  says: a reference carries `promoted_at` and no answer. `read_baseline`
  refuses the other where a reference belongs, as `NotAReferenceError`.
- **Through one table, a served run and a projected reference pair case by
  case**, so `compare()` holds the two projections against each other and
  finds a regression. Two tables do not, and nothing detects it (below).

**`Run.projected` is verified, not believed**, like `redacted`. A run that
declares it is refused unless it is redacted, every name listed above is a
token, every artifact is withheld, the run carries no metadata, and no verdict
carries string metadata. The strings it leaves in clear, because digline
writes them, are checked for their form: a verdict's and a band's
`assertion_id` and `config_hash` are digests, `digline_version` a version,
`rejudged_from` a run key, and `created_at`, `promoted_at` and `resumed_at`
times. The keys of a verdict's metadata are not checked:
they are in none of ADR 0034 §4's classes yet. **The refusal of run metadata
decides nothing about numbers.** Redaction with no `Disclosure` already removed
every entry, numbers included, so a projection never has any. ADR 0034 §4
still leaves numbers undecided everywhere else.

**`compare()` refuses a pair whose `projected` differs**, as
**`DifferentRegimesError`**, in `REFUSALS`, the way it refuses two tenants. A
projected document names its cases by token and the other side names them by
text, so no case would meet its counterpart. Every one would read as `new`
plus `missing`, which exits 0, and a regression against the projected
reference would read as *Nothing got worse*. **This does not close the same
failure between two projections minted from different tables.** Both declare
`projected`, and nothing in a document says which table minted it. That is an
open question of ADR 0036.

### The committed file: `run_to_json` and `run_from_json`

`project` returns a `Run`, and `resolve_tokens` takes one. Between them is the
file the software house commits. These two functions are the way across: the
one writes a projection to that file, the other reads the file back (#322).

- **`run_to_json(run)`** returns the document as text: sorted keys, floats at
  `FLOAT_PRECISION`, a trailing newline. Two equal runs give the same bytes, so
  a projection made twice through one table diffs clean in a pull request. A
  projection is already redacted, and it is written with the defaults. The two
  keyword arguments, `redacted` and `disclosure`, redact a run in clear on the
  way out, as `redact` does.
- **`run_from_json(text)`** returns the `Run` the document describes. The
  document is checked while the `Run` is built, so **`projected` is verified,
  not believed**: a document that declares it and leaves a name in clear is
  refused, with every other check listed above.
- **A document this version cannot read is refused** as
  `DocumentRefusedError`, in `REFUSALS`. That covers text that is not JSON, a
  `schema_version` other than this release's, and a document that is not a run.

Parsing the file with code of your own skips those checks, which is why these
two functions are on this page. They are the same functions the store reads
and writes every run with.

## The resolver

The mirror of the projection. `project` is handed a minter and turns names
into tokens; **`resolve_tokens(run, lookup)`** is handed a lookup and turns
them back ([ADR 0036](adr/0036-the-name-table-and-the-process-that-owns-it.md)
§2, §3, §8). It is called by the process that owns the table. digline itself
never calls it, because it never holds the table.

```python
from digline.core import resolve_tokens, run_from_json

reference = run_from_json(committed_file.read_text(encoding="utf-8"))
readable = resolve_tokens(reference, table.lookup)  # table: the owner's
```

**`Lookup`** is `Callable[[str], NameRow | None]`: the row a token names, or
`None`. **`NameRow`** is structural: anything with a `token`, a `kind` and a
`text`, each a string, is one. digline builds no row, and the owner's row type
needs no import to satisfy it. The kind is a plain `str`, compared for
equality with the kind of the place the token sits in.

**What it returns** is a `Run` whose names are text again: `projected` is
false and `redacted` stays true, because the reasons were removed before the
names were and do not come back. With every row present, the result is the
reference as `redact(reference, NOTHING_EXTRA)` writes it. A test holds that.

**A token with no row stays where it is**, as the token: an erased case id is
read as its token, and an erased group leaves `family[group=<token>]`,
still parseable. Token by token, *erased*, *never minted here* and *the wrong
table* all read the same.

**Refused**, each in `REFUSALS`:

- **`NothingResolvedError`**: the document carries tokens and none has a
  row. That is the wrong table, because a token has no row in any other. A
  document with **no** token is read. A legitimate document whose every row
  was erased is refused too: that fails loud, which is the direction chosen.
- **`WrongKindError`**: a row minted under another kind than its place's.
  Which place carries which kind is the same map the projection writes by.
- **`WrongRowError`**: the lookup answered with the row of another token, or
  with something that is not a row.
- **`UnresolvedConfigError`**: a configuration key, string value or judge
  identity has no row. The other kinds stay in place when unresolved. A
  configuration cannot, because its checks read `provider` and `model` by
  their text, so half of one names no system.
- **`NotProjectedError`**: the run is not projected, so there is nothing to
  resolve.
- **`DuplicateNameError`**: two tokens of one kind resolve to the same text.
  The table gives one name two rows, and the run would read two things as
  one, such as two cases with one id. It is the mirror of the projection's
  refusal of one name given two tokens. Equal text in two kinds is two names,
  and is read.
- **`IncoherentRowsError`**: every row resolved, and the run they rebuild
  refuses what they say together. Examples are a judge identity that is not
  its `provider/model`, a perimeter key read back in clear, or an empty model.
  Without it, that was the rebuilt `Run`'s own bare `ValueError`, which no
  front end translates.

## A complete example

It really runs: `examples/quickstart/` holds `app.py` — the application under
test, with `reply(question_id)` and `render_prompt(question_id)` — and this file.
A test in `tests/test_examples.py` executes it on every build and checks that it
is identical to the one below, so the documentation cannot drift from the code.

```python
"""A complete, working suite.

Run it from this directory:

    digline run     --suite suite.py
    digline promote --suite suite.py --run latest --replacing none
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
