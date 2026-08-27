# digline

Python-native evaluation engine for LLM output. Starting reference: promptfoo
(analysis in private/promptfoo-analysis.md). Not a clone: the decisions below
correct its structural mistakes and are not negotiable.

## Architectural decisions (fixed)

1. **One assertion engine, two drivers.** Assertions are pure functions
   `(EvaluatorInputs) -> Verdict` in `digline.core`, with no I/O, callable on
   their own (amended by ADR 0001: it used to be `(output, context) -> Score`).
   The offline driver (prompt × provider × test matrix) and the online one
   (stream of production responses) use the same code. If a change to the core
   makes an assertion callable only inside a runner, it is wrong.
2. **Per-project storage.** Everything lives in `.digline/<tenant>/` inside the
   user's repo: config and baselines versioned in git, run artifacts
   gitignored. Behind the `ResultStore` protocol, file-based implementation by
   default. Never a DB in the home directory, never global state on the machine.
3. **No vacuously green assertion.** Every assertion has a mandatory threshold
   or a default that can fail. A default of 0 that always passes is a bug.
4. **Cost and latency are budgets, not metrics.** A declared ceiling fails the
   run.
5. **Zero telemetry, zero phone-home.** No network call the user has not
   explicitly configured.
6. **Providers as plugins** (entry points), not vendored into the repo.
7. **The core must accept a single response**, not only a matrix: the reactive
   side (shadow path / in-path) is not decided yet, but must not be precluded.
8. **The tenant is the perimeter.** `Run.tenant` is mandatory and non-empty.
   `compare()` and `promote_baseline` raise if the tenants differ. The tenant is
   a directory in the layout — `.digline/<tenant>/` — so that the separation is
   enforced by the filesystem, not by a field inside a document.
   **No sub-perimeter**: `Run.environment` (mandatory, no default) says where
   inside the perimeter the run happened, does not enter the layout, and
   `compare()` reports it without constraining — comparing staging against the
   production baseline is the pre-release check. (ADR 0002)
9. **The payload stays where it is born, the verdict travels.** These cross a
   boundary: name, `assertion_id`, status, score, threshold, tolerance, and the
   metadata *measured by an assertion*. These do not: the `reason` and any
   metadata not covered by a `Disclosure` declared in code. Redaction is a
   function on the value (`redact`), not a serializer option; in the document
   the payload fields are absent, not emptied, and `"redacted": true` declares
   it. (ADR 0002)
   The **artifacts** a suite declares — the prompt is the thing under test — are
   recorded in every run and cross a boundary only under
   `Disclosure(artifacts=True)`: a prompt carries the end company's rules, so
   the prudent default holds here too. (ADR 0003)

## Structure

    src/digline/core/       pure domain: Score, Verdict, assertions, protocols. No imports from other packages.
    src/digline/store/      ResultStore and its implementations (file-based, inside the repo)
    src/digline/targets/    prompt template, pricing, the ProviderTarget base. No SDK, ever;
                            real providers are separate packages under packages/
    src/digline/run/        offline driver
    src/digline/report/     the document for world 3: pure functions, self-contained HTML, mandatory locale
    src/digline/production/ [planned] production store, Postgres first, mandatory retention
    src/digline/bridge/     [planned] production → repo: mandatory anonymization, generated case_id
    src/digline/online/     production driver
    src/digline/cli/        last layer: the **only** one allowed to read the clock and git
                            (the *clock*, meaning wall time: `created_at` is passed in so a
                            run is reproducible. A **duration** is not a clock — it cannot
                            say what time it is — so `perf_counter` for `latency_ms` in a
                            target is allowed and is what fills `Response.latency_ms`.)
    docs/                   public documentation: API reference, decisions (numbered ADRs)

Allowed dependencies: cli → targets → run/report/bridge/online →
store/production → core. Never the other way round, and nothing under `src/`
ever imports a plugin from `packages/`.

Build order: offline driver → report → store and CLI. **Nothing online before
the report**: it is what world 3 sees, and it is the only one of the three
artifacts that today exists in none of the audited competitors.

## Conventions

- Python 3.12+, uv, ruff, pyright strict, pytest. Types everywhere, `Protocol`
  for abstractions, frozen dataclasses for values.
- **The whole repository is in English**: comments, docstrings, test and
  variable names, error messages and runtime strings (`Verdict.reason` ends up
  in the committed baseline, which is a public format), plus `docs/`, the ADRs
  and this file. Italian only in conversation and in `private/`, which is not
  committed.
  **The one declared exception: `digline/report/text.py`.** The report is not a
  runtime string, it is a document with a recipient who did not choose English.
  `TEXT` is the per-locale table; `render_html` and `headline` take a mandatory
  `locale` with no default, like `environment`. ISO dates and the decimal point
  are not localized: two reports of the same run must stay comparable line by
  line.
  In the CLI the distinction is between *document* and *terminal*:
  `report --locale` is mandatory, `compare --locale` defaults to `en` like every
  other terminal output. Consistency between the two sentences is guaranteed by
  `headline()`, not by the user.
- Every assertion has tests with at least one failing case.
- `tests/test_layering.py` is a **mandatory gate**, not a style test: it guarantees
  that the core stays pure and importable from Plumbline without dragging storage
  along. It must not be weakened or made optional; if it fails, the change is
  wrong, not the test.
- Every decision touching the "fixed" section requires an ADR in docs/adr/
  before the code.
- Small commits, message in English, imperative.

## Relationship with Plumbline

Plumbline (CLI `plumb`) is the methodology for preventive verification of the
development process; digline verifies the model's output. digline.core must be
importable from Plumbline as a library. Plumbline's wall/friction dichotomy maps
onto in-path/shadow-path here: use the same terms.

## The three worlds (ADR 0002)

1. **Developer** — works in the repo, writes the assertions, sees everything.
2. **Software house** — maintains N customers, must see the signal **without
   holding the production data** of any of them.
3. **End company** — owns the data, does not read code, is entitled to an
   understandable verdict and to its data not leaving.

The tenant (decision 8) separates customers from each other; the
payload/verdict boundary (decision 9) separates what the end company may send
from what it must not.

## How to work with me

- Before writing code in a new area: an API proposal in 20 lines, then implement.
- If a request contradicts a fixed decision, stop and tell me, do not work
  around it.
- I am new to Python (not to programming): when you pick a non-obvious idiom,
  one line of rationale.
