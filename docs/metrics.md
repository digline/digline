# The metrics

One card per assertion and per aggregate: when to reach for it, what it takes,
what it produces, and what it will do to you if you are not looking.

Every example on this page is constructed by a test, and the metadata columns
come out of a program that runs all of them. In the examples, `judge` is your
`Judge` function, `claim_judge` your `ClaimJudge`, and `scorer` an `autoevals`
scorer — see [`api.md`](api.md) for the protocols.

## Choosing one

```text
Do the cases carry a human mark (ground truth)?
├── yes → the gate is a verdict about the run: Precision · Recall · Accuracy · F1
│         and the per-case check under it answers "did the system agree?"
└── no  → gate per case, and pick by what "correct" means here:
    ├── an exact string, or a fragment that must (not) be there ... Equals · Contains · NotContains · Affix
    ├── a shape rather than a value ............................... Regex · IsJson · JsonSchema · Length
    ├── close enough to an expected text .......................... Levenshtein
    ├── a judgement that only words can state ..................... LlmRubric   → wrap in Repeated
    ├── supported by the retrieved context ........................ Faithfulness
    ├── no personal data on the way out ........................... PiiAbsent
    └── a scorer you already own .................................. FromAutoevals
Always, next to whichever you picked: CostBudget · LatencyBudget
```

## What each one puts in the verdict

```python
# showcase.py
"""Every assertion, run once, printing what it puts in the verdict.

The `produces` line on each card comes from here, so a card cannot describe a
key that no longer exists.
"""

from digline.core import (
    F1,
    Accuracy,
    Affix,
    CaseOutcome,
    ClaimReply,
    Contains,
    CostBudget,
    Equals,
    EvaluatorInputs,
    Faithfulness,
    IsJson,
    JsonSchema,
    JudgeReply,
    LatencyBudget,
    Length,
    Levenshtein,
    LlmRubric,
    NotContains,
    PiiAbsent,
    Precision,
    Recall,
    Regex,
    Repeated,
    Verdict,
)

TEXT = "Hello Rome 42"


def show(assertion: object, **kwargs: object) -> None:
    inputs = EvaluatorInputs(output=kwargs.pop("output", TEXT), **kwargs)  # type: ignore[arg-type]
    verdict = assertion(inputs)  # type: ignore[operator]
    keys = ", ".join(verdict.score.metadata) or "—"
    score = "—" if verdict.score.score is None else f"{verdict.score.score:.3f}"
    print(f"{verdict.score.name:<16} {score:>7}  {verdict.status:<5}  {keys}")


print(f"{'check':<16} {'score':>7}  {'status':<5}  metadata keys")
show(Equals(), expected=TEXT)
show(Contains(needle="Rome"))
show(NotContains(needle="Milan"))
show(Affix(affix="Hello"))
show(Regex(pattern=r"\d+"))
show(IsJson(), output='{"city": "Rome"}')
show(JsonSchema(schema={"type": "object"}), output='{"city": "Rome"}')
show(Length(minimum=1, maximum=50))
show(Levenshtein(), expected="Hello Rome 43")
show(LlmRubric(rubric="Is it civil?", judge=lambda p: JudgeReply(0.8, "civil"),
               threshold=0.7, tolerance=0.05))
show(Faithfulness(judge=lambda p: ClaimReply(supported=3, total=4, reason="one unsupported"),
                  threshold=0.7, tolerance=0.05), context=("Rome is in Italy",))
show(PiiAbsent(), output="write to a@b.com")
show(CostBudget(max_usd=0.10, tolerance=0.02), cost_usd=0.05)
show(LatencyBudget(max_ms=800.0, tolerance=0.10), latency_ms=200.0)
show(Repeated(inner=Contains(needle="Rome"), samples=3, min_agreement="2/3"))

print()
kept = Contains(needle="MATCH")
outcomes = [
    CaseOutcome(case_id=f"c{i}", label=label, verdict=kept(EvaluatorInputs(output=out)))
    for i, (label, out) in enumerate(
        [("positive", "MATCH"), ("positive", "MATCH"), ("positive", "MISS"),
         ("negative", "MATCH"), ("negative", "MISS"), ("negative", "MISS")]
    )
]
print(f"{'aggregate':<16} {'score':>7}  {'status':<5}  metadata keys")
for aggregate in (
    Precision(over="contains", threshold="1/2", tolerance="1/6"),
    Recall(over="contains", threshold="1/2", tolerance="1/6"),
    Accuracy(over="contains", threshold="1/2", tolerance="1/6"),
    F1(over="contains", threshold="1/2", tolerance="1/6"),
):
    verdict: Verdict = aggregate(outcomes)
    keys = ", ".join(verdict.score.metadata) or "—"
    score = "—" if verdict.score.score is None else f"{verdict.score.score:.3f}"
    print(f"{verdict.score.name:<16} {score:>7}  {verdict.status:<5}  {keys}")
```

```console
$ python showcase.py
check              score  status  metadata keys
equals             1.000  pass   —
contains           1.000  pass   —
not_contains       1.000  pass   —
starts_with        1.000  pass   —
regex              1.000  pass   —
is_json            1.000  pass   json_kind
json_schema        1.000  pass   —
length             1.000  pass   length, unit, minimum, maximum
levenshtein        0.923  pass   distance, length
llm_rubric         0.800  pass   —
faithfulness       0.750  pass   claims_total, claims_supported
pii_absent         0.000  fail   pii_iban, pii_codice_fiscale, pii_partita_iva, pii_email, pii_phone_it, pii_total
cost_budget        0.667  pass   cost_usd, max_usd, ratio
latency_budget     0.800  pass   latency_ms, max_ms, ratio
contains           1.000  pass   samples, agreement, spread, errored_samples, scores

aggregate          score  status  metadata keys
precision          0.500  pass   true_positive, false_positive, true_negative, false_negative, considered, suspended_excluded, errored_excluded, unlabelled_excluded
recall             0.667  pass   true_positive, false_positive, true_negative, false_negative, considered, suspended_excluded, errored_excluded, unlabelled_excluded
accuracy           0.500  pass   true_positive, false_positive, true_negative, false_negative, considered, suspended_excluded, errored_excluded, unlabelled_excluded
f1                 0.571  pass   true_positive, false_positive, true_negative, false_negative, considered, suspended_excluded, errored_excluded, unlabelled_excluded
```

Two things to read off that table. `starts_with` and `contains` appear where
`Affix` and `Repeated` were asked for: the **name is the identity**, `Affix`
names itself after the end it checks, and `Repeated` keeps the name of the check
it wraps — so wrapping one does not produce a `new` plus a `missing`. And every
metadata value is a number or a short label: that is what lets the counts cross
a perimeter when the text they were measured on may not.

---

## Per case

### `Equals`

**Use it when** the answer is a fixed string or a fixed structure — a
classification label, an enum, a canned refusal.

```python
Equals()
```

**Takes** nothing but the defaults; compares against `Case.expected`.
`threshold=1.0`, `tolerance=0.0`. Accepts text, structured and conversation.
**Produces** `1.0` or `0.0`, no metadata.
**Watch out** a case with no `expected` is `error`, not `fail`: *"expected is
missing: equals cannot judge without an expected value"*.

### `Contains`

**Use it when** the answer must always carry a fragment — a sign-off, a
disclaimer, a required field name.

```python
Contains(needle="Kind regards", case_sensitive=False)
```

**Takes** `needle`, `case_sensitive=True`. Text only.
**Produces** `1.0` or `0.0`, no metadata.
**Watch out** `Contains("")` is refused at construction: it would pass on
everything. Handed structured output it is `error`, never a silent `str()`.

### `NotContains`

**Use it when** something must never appear: a competitor's name, an internal
code, the phrase legal struck out.

```python
NotContains(needle="as an AI language model")
```

**Takes** `needle`, `case_sensitive=True`. Text only.
**Produces** `1.0` or `0.0`, no metadata.
**Watch out** the negation lives in the assertion, not in a threshold you invert
— that keeps the reason readable in the report. `NotContains("")` is refused: it
would fail on everything.

### `Affix`

**Use it when** position matters and presence does not: a reply that must open
with a greeting, a JSON payload that must end with `}`.

```python
Affix(affix="Dear ", at="start")
```

**Takes** `affix`, `at="start"|"end"`, `case_sensitive=True`. Text only.
**Produces** `1.0` or `0.0`, no metadata. Names itself `starts_with` or
`ends_with`.
**Watch out** `Affix("")` is refused: every string starts and ends with it.

### `Regex`

**Use it when** the shape is describable and the value is not — an order number,
a date format, a citation marker.

```python
Regex(pattern=r"^ORD-\d{6}$")
```

**Takes** `pattern`. Text only.
**Produces** `1.0` or `0.0`, no metadata.
**Watch out** a pattern is not a parser. If you are matching braces or nesting,
the question is `IsJson` or `JsonSchema`.

### `IsJson`

**Use it when** the only question is whether it parses — the first check on any
tool-calling or structured-output path.

```python
IsJson(top_level="object")
```

**Takes** `top_level="any"|"object"|"array"`. Text only.
**Produces** `1.0` or `0.0`, and `json_kind` — `object`, `array`, `invalid`, and
so on, which is what tells you *how* it was wrong.
**Watch out** it says nothing about the contents. Pair it with `JsonSchema`.

### `JsonSchema`

**Use it when** the structure has rules: required keys, types, enumerations.

```python
JsonSchema(schema={
    "type": "object",
    "required": ["intent", "confidence"],
    "properties": {"confidence": {"type": "number"}},
})
```

**Takes** `schema` (a JSON Schema document). Text and structured.
**Produces** `1.0` or `0.0`, no metadata.
**Watch out** it validates, it does not parse-and-explain: for "did the model
even return JSON" the answer is `IsJson`, and the two are different questions on
purpose. This is the one assertion with a runtime dependency (`jsonschema`), for
the reason in ADR 0001: a half-written validator is a vacuously green check.

### `Length`

**Use it when** answers are drifting longer, or must fit a channel — an SMS, a
card, a summary field.

```python
Length(minimum=20, maximum=280, unit="characters")
```

**Takes** `minimum`, `maximum` (at least one), `unit="characters"|"words"`.
Text only.
**Produces** `1.0` or `0.0`, and `length`, `unit`, `minimum`, `maximum` — so the
report says how far out it was, not merely that it was.
**Watch out** `Length()` with neither bound is refused: it passes on everything.

### `Levenshtein`

**Use it when** you have an expected text and "nearly right" is a real answer —
a translation, a normalisation, a rewrite.

```python
Levenshtein(threshold=0.85)
```

**Takes** nothing required; compares against `Case.expected`. `threshold=0.9` by
default. Text only.
**Produces** a graded score, plus `distance` and `length`.
**Watch out** graded is the whole reason to have it — a binary near-match is
just `Equals` with extra steps. No `expected` is `error`.

### `LlmRubric`

**Use it when** the criterion is a judgement that only words can state: is it
polite, does it stay on policy, does it answer *this* question.

```python
LlmRubric(
    rubric="Answers the question without inventing policy",
    judge=judge,
    threshold=0.8,
    tolerance=0.05,
)
```

**Takes** `rubric`, `judge`, and **`threshold` and `tolerance` with no
defaults** — an LLM judge is not reproducible, and an implicit tolerance over a
noisy value is a green light nobody gave. Text and conversation.
**Produces** the judge's score; no metadata of its own (the judge's reason
becomes `Verdict.reason`, which is payload and does not travel).
**Watch out** three things are `error`, never `fail`: a judge that raises, a
score outside `[0, 1]`, and a reply with no reason. And a bare `LlmRubric` is
almost always the wrong shape — see `Repeated`, and chapter 2 of the
[guide](guide.md).

### `Faithfulness`

**Use it when** the system retrieves and then answers, and the question is
whether the answer stayed inside what was retrieved.

```python
Faithfulness(judge=claim_judge, threshold=0.9, tolerance=0.05)
```

**Takes** `judge` (a `ClaimJudge`), **`threshold`**, **`tolerance`**. Reads
`EvaluatorInputs.context`. Text only.
**Produces** a graded score, plus `claims_total` and `claims_supported`.
**Watch out** the judge returns two **counts** and the core divides. A model
asked for a ratio returns a number nobody can check; asked for counts it returns
something arithmetic can contradict. No claims found at all is `error`, not
`1.0`.

### `FromAutoevals`

**Use it when** you already have an `autoevals` scorer and want it under a
baseline rather than under a threshold.

```python
FromAutoevals(scorer=scorer, threshold=0.7, tolerance=0.05)
```

**Takes** `scorer`, **`threshold`**, **`tolerance`**. Text only.
**Produces** whatever the scorer's `Score` carried: its name, its value, its
metadata, passed through.
**Watch out** it needs the `autoevals` package, which digline does not depend
on. The adapter exists so migrating in costs one line, not a rewrite.

### `PiiAbsent`

**Use it when** the output reaches a person, or leaves the perimeter, or is
about to be pasted into a ticket.

```python
PiiAbsent()
```

**Takes** `patterns`, defaulting to the Italian set: IBAN, codice fiscale,
partita IVA, email, phone — the first three checksum-verified, so a number that
merely looks like an IBAN is not one. Text only.
**Produces** `1.0` or `0.0`, plus a count per pattern and `pii_total`.
**Watch out** binary on purpose: "a bit of PII" is not a degree of quality, and
a graded score would invite a threshold meaning "some leakage is fine". **The
counts travel and the text found never does** — the number of matches crosses a
boundary, the matched string is not even put in the metadata.

### `CostBudget`

**Use it when** always. A budget is a ceiling that fails the run, not a metric
on a dashboard.

```python
CostBudget(max_usd=0.01, tolerance=0.05)
```

**Takes** `max_usd`, **`tolerance`**; `threshold=0.5`. All output kinds.
**Produces** a graded score — `1.0` at zero spend, falling as the ceiling
approaches — plus `cost_usd`, `max_usd`, `ratio`.
**Watch out** graded rather than binary is the point: a cost that creeps from
40% to 80% of budget is visible long before it breaches. `tolerance` has no
default because cost is noisy by nature — tokens, retries, a slow provider — and
an implicit zero would call ordinary noise a regression every run.

### `LatencyBudget`

**Use it when** always, alongside the cost. The same reasoning, in milliseconds.

```python
LatencyBudget(max_ms=2000.0, tolerance=0.10)
```

**Takes** `max_ms`, **`tolerance`**; `threshold=0.5`. All output kinds.
**Produces** a graded score plus `latency_ms`, `max_ms`, `ratio`.
**Watch out** measure what you can control. If your target includes a network
you do not own, tolerance is doing more work than the threshold.

### `Repeated`

**Use it when** the check underneath it is a judge. This is judge noise made
into a measurement instead of a surprise.

```python
Repeated(
    inner=LlmRubric(rubric="Stays on policy", judge=judge,
                    threshold=0.8, tolerance=0.10),
    samples=5,
    min_agreement="3/5",
)
```

**Takes** `inner`, `samples`, `min_agreement` (a fraction). Threshold and
tolerance come from `inner`, and so does the name.
**Produces** the folded score, plus `samples`, `agreement`, `spread`,
`errored_samples`, and `scores` — the raw votes, which is the column `digline
view` shows under the combined number.
**Watch out** below the agreement floor the verdict is **`error`**, never a
pass: *"the samples did not agree: 0.67 of them share the majority verdict,
below the required 1.00"*. `min_agreement` must be a fraction `samples` can
actually produce — `0.67` with three samples is refused at construction with the
list of the ones that exist. And this is the **judge** wobbling; for the target
answering differently, the answer is `Suite(samples=…)`.

---

## Per run

All four take `over` — the name of the one per-case assertion whose verdicts get
counted — plus a mandatory `threshold` and `tolerance`, both readable as
fractions. All four produce the same metadata: the four cells of the confusion
matrix, `considered`, and the three exclusions. All four are `error`, never
`1.0`, on an empty denominator.

Every case must carry a `label` the moment one of these is declared, and `Suite`
refuses `over` that names no assertion **or** two. Where to put the threshold:
where the system measurably is — chapter 5 of the [guide](guide.md).

### `Precision`

**Use it when** false positives are what your users see: the item that should
not have been kept, the ticket that should not have been escalated.

```python
Precision(over="agrees_with_mark", threshold="3/5", tolerance="1/21")
```

`TP / (TP + FP)`. Rises when the system gets choosier — including when it gets
choosier by keeping almost nothing, which is what `Recall` is for.

### `Recall`

**Use it when** what is missed is what hurts: the fraud not flagged, the outage
not escalated.

```python
Recall(over="agrees_with_mark", threshold="3/5", tolerance="1/21")
```

`TP / (TP + FN)`. Rises when the system gets more generous, and a system that
keeps everything scores `1.0` — which is what `Precision` is for.

### `Accuracy`

**Use it when** the two classes matter equally and are roughly balanced.

```python
Accuracy(over="agrees_with_mark", threshold="2/3", tolerance="1/21")
```

`(TP + TN) / considered`. **Watch out** on a skewed suite it flatters: with one
positive in twenty, answering "no" to everything scores `0.95`.

### `F1`

**Use it when** you need one number and precision and recall are trading against
each other — a stricter prompt keeps fewer items and gets more of them right,
raising one and lowering the other.

```python
F1(over="agrees_with_mark", threshold="3/5", tolerance="1/21")
```

`2TP / (2TP + FP + FN)`. Written that way and not as `2PR / (P + R)`: the same
number with one denominator to check instead of three, and no decision to make
about what `F1` means once precision has already gone to `error`.

---

## See also

- [`guide.md`](guide.md) — how these get calibrated, in the order the problems arrive
- [`api.md`](api.md) — the full parameter reference, the judge protocols, custom assertions
- [`adr/0001-verdict-not-score.md`](adr/0001-verdict-not-score.md) — why a verdict has three states
