# Digline Roadmap

This project moves by **tracks and gates, not dates**. Each track has an exit
gate; some tracks cannot start until evidence from real usage opens them. That
is deliberate: Digline's thesis is that quality regressions should be caught
by comparing against an approved, versioned baseline — and the roadmap itself
follows the same discipline. Features ship when validated, not when scheduled.

Two things will never be on this roadmap:

- **A hosted service that receives your payloads.** Prompts, outputs and the
  judge stay in your perimeter. Only verdicts and redacted runs are ever
  designed to travel.
- **Usage data collection, ever.** Digline makes no network calls except the
  ones your suite explicitly configures.

---

## Track A — Provider coverage

*Status: completed*

Complete and stabilize the provider plugins under the plugin contract
(ADR 0004: every plugin ships Target + Judge + ClaimJudge). The contract itself
widened in 0.8.0 — `_complete` returns a `Completion` rather than
`(text, Usage)` — without reopening the track: the old pair stays accepted
permanently, so a third-party plugin written against any earlier release is
unaffected (ADR 0004 §6).

- [x] `digline-anthropic`
- [x] `digline-openai` (incl. OpenAI-compatible endpoints via `base_url`)
- [x] `digline-bedrock` (Converse API; per-region pricing; conservative price
      seeding — unknown model/region fails preflight rather than guessing)
- [x] Price sentinel in CI: compare hardcoded plugin prices against a public
      dataset and open an issue/PR with the diff when they drift

**Exit gate:** three providers published, symmetric, and boring.

## Track B — Verdict credibility

*Status: completed*

A regression tool that mistakes noise for regression is worse than no tool.
This track makes the verdict itself trustworthy.

- [x] Record the configuration of the system under test (model, temperature,
      sampling parameters where the provider exposes them) in runs and
      baselines; `compare` highlights which parameters changed between the
      two (ADR 0005) — shipped in 0.2.0, extended in 0.3.0 to targets Digline
      cannot import, which report theirs in the answer (ADR 0005 §8), and again
      in 0.8.0 to what was **observed** rather than sent: `resolved_model` and,
      where a provider names one, `fingerprint`, so an alias that rolled under
      an unchanged suite is a named delta instead of an invisible one
      (ADR 0005 §9)
- [x] Repeated runs per case: score as a distribution, not a single sample —
      `Suite.samples` folds N calls per case, and since ADR 0006 the raw
      per-sample scores and the interval they span are recorded on the verdict
      and travel with it
- [x] Regression thresholds expressed relative to measured variance, not as
      absolute deltas — a drop is a regression only when it leaves the interval
      the *baseline* observed across its own samples (ADR 0006 §5), and an
      aggregate gets an interval of its own from one evaluation per sample
      index (§7). The observed min and max rather than a variance: five samples
      do not earn a distributional assumption, and a reader can check a min
      against the raw values printed beside it
- [x] **The canary case** (ADR 0016) — an alias is a pointer and pointers roll.
      `resolved_model` records what the provider *said* answered and is silent
      on the providers that say nothing, so `Case(canary=True)` is the
      behavioural half: a case that watches the model instead of measuring it.
      It is counted in **no** aggregate — the exclusion is a figure in the
      verdict's metadata, so a denominator stays reconcilable with the case
      file — and if it **moves at all**, in either direction, the headline says
      *the model under this alias likely changed* and the run exits `1`. A score
      that is a fingerprint rather than a quality cannot ride `worse`, so it is
      a fact of its own beside it. A suite that declares one must sample: at one
      sample there is no noise to measure and every wobble would stop a release
- [x] **Judging stored answers again** (ADR 0015) — `record_responses=True`
      keeps what the target said, per case and per sample, beside the prompt
      that produced it; `digline rejudge` replays those answers through the
      current suite, so a changed judge, rubric or threshold is measurable at no
      cost to the target. The field's usual answer to this is a response cache,
      which hands back an old answer as though it were a new one; this declares
      itself instead — in the document, in the headline, in `--json` — and the
      run it writes **cannot be promoted**, because a replay has no target
      variance and its interval would freeze a noise floor measured without the
      noise. The answers never cross a boundary and `promote` strips them from
      the reference

**Exit gate:** a baseline comparison can state, honestly, whether an observed
difference is signal or sampling noise. **Met** — the two runs in
`tests/fixtures/brief/` are the case it was written against, and the test that
reads them fails if it stops being met. 0.7.0 closed the last gap underneath
it: every limit — threshold, tolerance, measured floor, budget,
`min_agreement` — is now compared at the precision the document stores and is
inclusive (ADR 0009), so an edge case is decidable from the six decimals a
reader can see rather than from a residue nobody can.

## Track C — Adoption and developer experience

*Status: ongoing, low ceremony*

- [ ] Try-without-installing: a Codespace on the examples repo — you test it
      in the browser, but in *your* environment, because Digline has no server
      by design
- [ ] The run/baseline JSON format documented as a **versioned public
      contract**. The engine is Python; the contract is language-neutral. Not
      to be confused with what 0.6.0 shipped: `digline.wire` and
      `OUTPUT_VERSION` are the contract for what digline *prints* — every
      `--json` and every MCP response — and this item is about the documents it
      *stores*, which are versioned by `SCHEMA_VERSION` and still described
      nowhere a reader outside Python could use
- [x] A LangChain example evaluated in process: the target is a function
      that invokes the chain, so there is no server and no HTTP, and the
      default path runs on a fake chat model — no key, no network, and CI runs
      it (`examples/langchain/`)
- [x] A LangChain4j example over `HttpTarget`: one endpoint reporting the
      answer, what the call cost, and which model answered under what settings
      — so a run from a service Digline cannot import is as complete a document
      as one from a plugin (`examples/langchain4j/`, ADR 0005 §8)
- [x] A declarative suite format, `digline run suite.toml` (ADR 0007) —
      shipped in 0.5.0. TOML rather than YAML:
      `tomllib` is in the standard library from 3.11, and a suite format that
      costs a runtime dependency to read would double the one this project has.
      It arrived together with **providers as entry points** — fixed decision
      6, stated since the first commit and real from 0.5.0, because a judge
      named in data has to be resolvable without anything under `src/`
      importing a plugin. Scope was the assertions whose parameters are already
      data; a custom assertion, a custom target and a `Disclosure` stay Python,
      and the loader says so by name
- [x] An MCP server, `digline-mcp` (ADR 0011) — shipped in 0.6.0, which is
      also its own 0.1.0 and the first package this workspace ever published
      from scratch. Six tools, read and measurement only, and **`promote`
      absent by construction**: a refusal is a conversation a model can argue
      with, an absence is not, so `AGENTS.md` §1 stops being a rule an agent is
      asked to follow. `run` takes a mandatory
      `acknowledge_calls` that must match the preflight, so an agent cannot
      spend a hundred model calls without having stated the number. It brought
      two internal layers with it: `digline.host`, the part of the CLI that
      touches the world, and `digline.wire`, the machine surface both front ends
      render through
- [x] `digline explain` (ADR 0012) — the run read back at length, in prose:
      what ran, what moved and against which measured interval, what was set
      aside, which configuration differed. It compares where the suite has a
      baseline and reads the run alone where it does not. The report is written
      for someone who does not read code and therefore compresses; this is the
      same facts expanded, for the developer holding the report. It **states
      and never advises** — the judgment `AGENTS.md` describes stays a
      person's — and `--json` returns the typed fact list the prose is rendered
      from, so a terminal and a pipeline cannot describe one run two ways.
      Shipped in 0.7.0
- [x] `Suite(artifacts=[...])` accepted a `str` where it means a `Path`, and
      failed later and elsewhere: `AttributeError: 'str' object has no attribute
      'is_absolute'`, raised inside `read_artifacts` at run time, naming neither
      the suite nor the field. Coerced in `Suite.__post_init__`, the way the
      TOML loader already coerces by declared type — one rule, extended from the
      data form to the Python constructor rather than invented twice, and the
      loader's own `Path(str(entry))` is gone with it. Where a value cannot be
      coerced it is refused **by field name**, which is the fallback the TOML
      errors already model — so `artifacts = [3]` in a data suite stops loading
      quietly as the path `3`. Found while writing a fixture for ADR 0011's
      boundary gate
- [x] **`pytest-digline`** (ADR 0013) — shipped in 0.9.0, and its own 0.1.0. The
      comparison as rows in pytest's own report, **one per check** rather than
      one per case, because the check is digline's unit of verdict and a case
      can hold a regression and an error at once. It brought a state the exit
      code cannot express: a suspended case is a `SKIPPED` carrying its reason,
      where on the CLI route a suspension never fails and so disappears into
      `0`. It **compares without running** by default — a gate people invoke on
      a keystroke must not spend — and `--digline-run` refuses under
      `--collect-only`. `promote` is **absent by construction**, as it is from
      the MCP server, with an AST sweep over the package's own sources holding
      it: a green test run is the likeliest place for a baseline to be promoted
      by accident. It is inert until a suite is named, which is what lets it be
      installed in this repository's own environment without becoming a
      variable in the gates that judge it
- [x] **A GitHub Action**, `digline/digline-action` — the gate on the pull
      request, in its own repository because the Marketplace requires one.
      Composite over `ghcr.io/digline/digline` so the action's version and the
      image are released together, and so `image:` can be an **input**: the
      official image installs nothing at runtime, but `compare` loads the suite
      and a suite imports the application, so a suite with dependencies of its
      own derives the image and points the action at it. A docker action's image
      is a static string and could not have offered that. The comment carries
      `digline compare`'s output verbatim, and the job exits with digline's own
      code rather than a pass/fail of its own
- [ ] README pass with fresh eyes: assume the reader arrived five minutes ago
- [x] An official container image, `ghcr.io/digline/digline`: the CLI and the
      three provider plugins, published by the release workflow on a `v*` tag.
      For the reader who wants the cycle in CI without a Python toolchain of
      their own. Shipped in 0.5.0, tagged `:0.5.0`, `:0.5` and `:latest`, built
      for `amd64` and `arm64`. The open question resolved the way it was posed:
      the image mounts the repository, because `.digline/` lives there and never
      in the container — and it writes as the calling user rather than as root,
      which the workflow checks on the filesystem before it pushes
      (`docker/README.md`)

This replaces *"a thin JVM emitter"*, which was on this list and was wrong. An
emitter means the JVM side runs its own assertions and posts the verdicts, which
is a **second engine**: two implementations of what `contains` means, drifting
apart, with the run format as the only thing holding them together. The one
place that is allowed to happen is nowhere. `HttpTarget` keeps one engine and
one set of assertion semantics, and asks the application only for what it alone
can know — its answer, its cost, its configuration.

**Exit gate:** someone who is not the author sets up a suite without asking
the author anything.

---

The two tracks below are **gated on evidence from real production pilots**,
not on a feature schedule. If you run LLM calls in production and want to be
one of those pilots, open an issue — that is the fastest way to move them.

## Track D — Production (world 2)

*Status: design open, implementation gated on pilot evidence*

Everything below is a **hypothesis under validation**, not a commitment.

- Push ingestion over HTTP (runs emitted from any language)
- A transparent proxy as a third capture path — point your agent's base URL
  at it, zero code changes. Honest caveats: correlation metadata (tenant, run
  boundaries) is still required, and an in-path component carries production
  obligations (latency, availability) that a shadow-path library does not
- Traffic → cases: turning captured production traffic into evaluable cases
  and golden candidates, cleanly separated from the noise around them
- Redaction as a first-class transformation: per-tenant HMAC digests,
  scrubbing of provider error payloads — the payload stays where it is born;
  the verdict travels
- A production store (Postgres) alongside the file store
- Agent trajectories with **readable reasoning**: not just which tools were
  called in which order, but a non-technical account of why — extending the
  existing principle that reports must be legible to people who don't code.
  The first half arrived offline in 0.8.0: a provider reports the tools it
  called, and `ToolsCalled` asserts on them. The *why* is what stays here
- Open question, deliberately undecided: a reactive mode ("is this specific
  output valid, right now?") as opposed to the retrospective one

## Track E — Fleet (world 3)

*Status: titles only, entirely dependent on the same pilot evidence*

For software houses maintaining AI features across many end clients: a fleet
console, redacted runs traveling per tenant, per-client reports. Nothing here
is designed yet — on purpose.

---

*Suggestions and war stories are welcome as issues.*
