# ADR 0001 — The assertion produces a three-state `Verdict`, and the comparison against the baseline lives in the core

> **Note on the name (2026-08-26).** «prompteval» was the project's working
> name; it became **digline** because the name was already taken in the
> category. The text below has been updated to the new name: this note is the
> only place where the old name remains written.

- Status: accepted
- Date: 2026-08-25
- Touches: fixed decision 1 (`CLAUDE.md`), which stated assertions as pure functions
  `(output, context) -> Score`

## Context

The promptfoo audit (see `../../private/promptfoo-analysis.md`) and the audit of the three
adjacent competitors — autoevals, Langfuse, DeepEval (see `../../private/competitive-audit.md`) —
produced two results that change the design of the core.

**First: "one engine, two drivers" is not a differentiator.** It already exists, in two
forms. Langfuse does it on the SDK side — `langfuse/experiment.py:672` defines the
`EvaluatorFunction` protocol, and `langfuse/batch_evaluation.py:30` imports *the same*
protocol to apply it to production traces fetched via `client.run_batched_evaluation`
(`langfuse/_client/client.py:3237`). autoevals does it as a pure library:
`py/autoevals/score.py:43-61` defines `Scorer.__call__(output, expected, **kwargs) -> Score`
with only four runtime dependencies and no coupling to the platform.

The remaining differentiator, verified, is narrower: **the verdict and its history are a
versioned artifact of the project**. None of the four compares a run against a committed
baseline without a server:

- DeepEval has the concept of a baseline, but as a SaaS-side flag — `deepeval/utils.py:275-277`,
  literal comment «marked as the official baseline **on Confident AI** […] at upload time».
- Comparison between runs is behind a login — `deepeval/evaluate/compare.py:504-511` prints
  the invitation to `deepeval login` and returns.
- Its local storage is opt-in and ignored by git by convention —
  `deepeval/evaluate/local_store.py:46` («local-store is a no-op» if not configured),
  and `.gitignore:164` of their repo lists `.deepeval`.

**Second: threshold and baseline are two different things.** DeepEval's `assert_test`
catches "below 0.7". It does not catch "was 0.91, now 0.78, still above the threshold".
That regression, locally and without infrastructure, is today seen by nobody.

## Decision

### 1. A three-state `Verdict`, produced by the assertion

The assertion does not return a bare `Score` but a `Verdict`:

    Verdict(score: Score, threshold: float, tolerance: float, status: Status, reason: str)
    Status = Literal["pass", "fail", "error"]
    Verdict.passed  ->  derived property, status == "pass"

`Score` remains and keeps autoevals' shape (`name`, `score: float | None`, `metadata`),
so the two-way adapter is a function of a few lines. But the core never exposes it to the
driver: **the driver consumes `Verdict`, never `Score`**.

Three states and not two because `pass`/`fail` cannot represent "I could not judge".
With two states that case necessarily lands in one of them, and both choices are lies:
`pass` is a vacuously green assertion (violates fixed decision 3), `fail` is a false alarm
that erodes trust in the suite. `error` is the third outcome.

A binding consequence for interoperability: in autoevals `score is None` means "skip".
The adapter translates it into **`status="error"` with a mandatory `reason`**, never into
`pass`. The legitimate skip — "this assertion does not apply to this case" — is a decision
of the driver, which chooses not to invoke the assertion; it is not a state of the core.

### 2. `threshold` is always set

`threshold: float` does not admit `None`. Since the state "not set" does not exist, there
cannot be a default that always passes: fixed decision 3 becomes impossible to violate by
construction, rather than by discipline. It is the mistake promptfoo made
(`context-recall` and `context-relevance` with a default threshold of 0, issue #9910).

For deterministic assertions the threshold is degenerate (`1.0`, with score 0.0/1.0). It
is redundant but uniform: the driver treats every verdict the same way.

### 3. `compare()` is in the core, not in the driver

    compare(run: Run, baseline: Run) -> Comparison
    Outcome = Literal["regressed", "improved", "unchanged", "new", "missing", "errored"]

A pure function, zero I/O, callable without a runner — like everything else in the core.
It is point 2 of the differentiator, so it cannot sit in a layer that requires a driver to
be reached: that would be Langfuse's mistake, which has the right logic but buried in
`worker/src/features/evaluation/evalService.ts` (1,723 lines with Prisma, BullMQ,
ClickHouse and Redis inside), hence not callable in CI without deploying the
infrastructure.

Every assertion declares `tolerance: float` — default `0.0` for deterministic ones,
**mandatory and explicit for `llm_rubric`**, because an LLM judge is not reproducible and
an implicit tolerance over a noisy value is another way of being vacuously green.

The tolerance is recorded **in the `Verdict`**, not only in the assertion. Two reasons: it
makes `compare(run, baseline)` self-sufficient with only two arguments, and it makes the
baseline self-describing — a baseline file contains everything needed to interpret it,
without having to reconstruct the configuration that produced it.

Order of evaluation of the outcomes, deliberately not commutative:

1. present only in the run → `new`; present only in the baseline → `missing`
2. either side has `status == "error"` → `errored`
3. `status` went from `pass` to `fail` (or the reverse) → `regressed` / `improved`,
   **regardless of the tolerance**: a change of outcome is never noise
4. otherwise numeric comparison: `|delta| <= tolerance` → `unchanged`,
   `delta < 0` → `regressed`, `delta > 0` → `improved`

Rule 2 formalizes the constraint: **`error` is not green and is not a regression.** An
error presenting itself as a regression would fail a PR for the wrong reason; one
presenting itself as `unchanged` would hide a suite that has stopped working.

The tolerance used is the current run's, not the baseline's. Comparing two runs with
different tolerances is legitimate and is in fact the interesting case — seeing the effect
of a configuration change — but promotion to baseline is refused in that case (§5).

### 4. `Output` is a closed union

    Message(role: str, content: str)
    Output = str | Mapping[str, object] | Sequence[Message]

Agents produce tool calls and conversation turns, not strings. This type touches the
signature of every assertion: changing it later means rewriting them all, so it has to be
decided now even if the first assertions will only use the `str` branch.

Every assertion declares `accepts: frozenset[OutputKind]`. An output of a type that is not
accepted produces **`status="error"`**, never a silent conversion: `contains` on a
`Mapping` must not stringify the dictionary and search inside it, because the result would
be true or false for reasons that have nothing to do with the intent of whoever wrote the
test.

### 5. The baseline carries its own anchors

`Run` includes `git_commit: str | None` and `config_hash: str`, where the second is the
hash of the suite — assertion names, thresholds, tolerances — and deliberately *not* of
the test data, which changes on its own.

`promote_baseline` **refuses** to promote a run whose `config_hash` does not match the
current configuration. Without this constraint the baseline would record scores produced
by thresholds different from the ones in force, and every later comparison would be
meaningless while staying syntactically valid — the worst way to be wrong.

The JSON serialization is deterministic: sorted keys, floats at fixed precision. This is
not a cosmetic detail: the baseline is a committed file, its purpose is to be readable in
a code review, and a diff dirtied by key reordering or by the seventeenth digit of a float
is read by nobody.

## Consequences

- Fixed decision 1 of `CLAUDE.md` is to be read as `(inputs) -> Verdict`. Unchanged:
  purity, absence of I/O, callability without a runner.
- The core gains `compare()` and the `Run`/`Comparison` types. They stay pure functions:
  `Run` is a value, not an object that knows how to persist itself. The `ResultStore`
  lives in `digline.store` and depends on the core, never the other way round.
- The core has one runtime dependency: `jsonschema`, for the `json_schema` assertion.
  The alternative — a minimal in-house validator — was discarded: an incomplete validator
  that accepts schemas it cannot check is, once again, a vacuously green assertion.
- `Score` stays public and stable in autoevals' shape. It is an interoperability
  commitment: autoevals scorers can be adapted in a few lines, and their taxonomy becomes
  compatibility instead of work to redo.

## Not decided here

**`Judge` is synchronous.** The protocol is `__call__(prompt: str) -> JudgeReply`. That is
fine for the offline driver, but the online driver will need an `async` variant:
evaluating a stream of production responses with a blocking judge is not practical.

The core must not prevent it. Concretely: no assertion may assume the judge returns
immediately, and the future `AsyncJudge` will have to coexist with the synchronous one
without duplicating the assertions. The choice between a parallel protocol and a single
`async` protocol with a synchronous adapter is deferred to the ADR that will introduce
`digline.online`.

**The reactive side (in-path / shadow-path)** stays undecided, per fixed decision 7.
`EvaluatorInputs` accepts a single response and knows nothing of a matrix — the matrix is
an iteration the offline driver performs — so the choice stays open at no cost. In
Plumbline's terminology: shadow-path is *friction*, in-path is *wall*.

---

## Amendment of 2026-08-25 — the assertion's identity

A re-reading of the core: `compare()` paired verdicts on `(case, name, occurrence)`, that
is, **by position**. With two `contains` on the same case, swapping their order produced
an invented `regressed` and `improved`; removing the first of three made the third come
out as `missing` and had the second compared against the baseline of the first. Silently,
both.

Position is not identity. §3 above stays valid in its four rules; what changes is what the
rules are applied to.

**Three consequent changes.**

1. **`Assertion.identity`** — the fingerprint of *what the assertion checks*: its type and
   its parameters (needle, pattern, schema, rubric, cap, judge type), derived generically
   from the dataclass fields in `AssertionBase`.

   **Threshold and tolerance are deliberately excluded from it** (`IDENTITY_EXCLUDED`).
   They describe *how* you judge, not *what* you check, and they already travel inside
   every `Verdict`. Including them would have made a raised threshold produce a `new` plus
   a `missing` instead of pairing the verdicts — that is, it would have made unreachable
   exactly the most interesting comparison, the one showing the effect of the
   configuration change, and it would have made dead code of the branch of `compare()`
   that names the moved threshold. It would also have contradicted §3 above, which
   declares it legitimate to compare two runs with different tolerances.

   `canonical()` is what makes the fingerprint stable across processes: a `frozenset`
   field would have a different iteration order on every run, and an injected `Judge` is a
   function object whose `repr` contains a memory address.

   A `Judge` therefore contributes its own type name, not its own value: two different
   judges are indistinguishable. It is a deliberate limit — which judge is wired in is a
   property of the execution environment, not of the declared suite.

   `AssertionBase` documents the contract — a subclass must be a dataclass — and makes it
   fail with a message that names it, rather than with the `TypeError` from
   `dataclasses.fields()` on an arbitrary object.

2. **`Verdict.assertion_id`** — the identity travels in the verdict all the way to the
   baseline, because that is where `compare()` has to find it again. The default is the
   score's name, which is correct whenever a case carries a single assertion per name.

   The occurrence survives as a tie-breaker between verdicts that share an identity — the
   same assertion, identically configured, applied twice to the same case. There, position
   is the only thing left, and it is correct precisely because the two are
   interchangeable.

3. **`config_hash` is built on `(identity, threshold, tolerance)`.** The old triples
   `(name, threshold, tolerance)` did not distinguish `Contains(needle="Rome")` from
   `Contains(needle="Milan")`: two different suites with the same fingerprint, and a
   baseline promoted under one considered valid for the other.

   The two halves are separated on purpose. `identity` covers what is checked and is what
   `compare()` pairs on, so it must survive a change of threshold or the verdicts would
   stop meeting each other. Threshold and tolerance belong here because they change the
   *meaning* of the suite anyway: a baseline recorded with a threshold of 0.7 cannot serve
   as a reference for a suite that now demands 0.9.

   The result is the property that is needed: **a raised threshold is comparable but not
   promotable.** You look at the diff, then you decide whether to re-baseline.

   §5 is to be read this way. It still does not cover the test data — `config_hash` never
   sees a case, it takes assertions and nothing else.

`SCHEMA_VERSION` goes from 1 to 2. A file written without `assertion_id` cannot be
compared correctly, so it must be refused and not read with a silent fallback: that would
be the same defect as before, moved up one level.

For the same reason deserialization no longer has fallbacks: every field of the verdict is
mandatory and its absence raises an error that names it. A `tolerance` silently read as
`0.0` would have turned every recorded drift into a regression — that is, exactly the
defect `SCHEMA_VERSION` exists to prevent.

**Other invariants added in the same re-reading**, all of the same family — a wrong value
must be prevented, not detected:

- `Verdict` refuses a `status` that contradicts `score >= threshold`. It was possible to
  build a `pass` with a score below the threshold: the run's table and the pass/fail gate
  would have told the reviewer two different stories about the same result. It is the same
  reason why `passed` is derived.
- `Verdict.threshold` is validated in `[0, 1]`.
- `JudgeReply` validates score and reason at construction. It is the boundary the LLM
  enters through, the least reliable input in the system, and a docstring promising a
  range is worth nothing if nobody enforces it.
- `Score` and `JudgeReply` refuse `NaN` explicitly, instead of leaning on the fact that
  `0.0 <= nan <= 1.0` is false — a refusal by accident, with a message that sends the
  reader looking for a range problem.
- `normalize_output` is recursive. The shallow version left `{"a": ["x"]}` and
  `{"a": ("x",)}` different: the same defect one level down, where it shows less. An
  agent's structured output is nested, so that was the common case.
- `output_kind([])` is `conversation`, and it is now deliberate rather than a consequence
  of `all()` over an empty iterable: a model that produced no turns is a real outcome to
  be judged, not a configuration error.
- The `reason` of a change of outcome declares whether the **threshold** moved. Without
  it, a configuration change reads in a PR as the model getting worse.
- `CostBudget` and `LatencyBudget` demand an explicit `tolerance`, with no default, like
  `LlmRubric`. Cost varies with sampling and retries, latency with the network and the
  provider's load: an implicit tolerance of zero would have turned ordinary noise into a
  regression on every run. §3 is to be read as a general rule — **the tolerance has a
  default only where the measurement is deterministic.**

### The `Verdict` carries what gets persisted

Found while checking identity-based pairing against a real baseline, and not in memory.

The baseline goes through rounding to `FLOAT_PRECISION` on its way to disk; the in-memory
run does not. A score of `0.9090909090909092` was written as `0.909091` and read back as
`0.909091`, while the next run kept its unrounded form: `compare()` saw a delta of `-9e-8`,
above the default tolerance of `0`, and reported **a phantom regression on every execution
against a saved baseline**.

No in-memory test could catch it, because there both sides are unrounded. That is why the
two regression tests added go through the real filesystem.

`Verdict.__post_init__` now rounds score, threshold and tolerance to `FLOAT_PRECISION`:
**a `Verdict` and its copy read back from disk are indistinguishable.** Rounding in the
value rather than inside `compare()` makes it an invariant of the type instead of a
courtesy of a caller — the same reason why `passed` is derived and why the `status` cannot
contradict the threshold.

A consequence for `AssertionBase._graded`: the value must be rounded **before** deriving
the `status`, otherwise a score exactly on the boundary could produce a `status` that
disagrees with the score then stored — and `__post_init__` would refuse it, rightly.
