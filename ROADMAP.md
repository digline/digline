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
(ADR 0004: every plugin ships Target + Judge + ClaimJudge).

- [x] `digline-anthropic`
- [x] `digline-openai` (incl. OpenAI-compatible endpoints via `base_url`)
- [x] `digline-bedrock` (Converse API; per-region pricing; conservative price
      seeding — unknown model/region fails preflight rather than guessing)
- [x] Price sentinel in CI: compare hardcoded plugin prices against a public
      dataset and open an issue/PR with the diff when they drift

**Exit gate:** three providers published, symmetric, and boring.

## Track B — Verdict credibility

*Status: next — highest priority*

A regression tool that mistakes noise for regression is worse than no tool.
This track makes the verdict itself trustworthy.

- [x] Record the configuration of the system under test (model, temperature,
      sampling parameters where the provider exposes them) in runs and
      baselines; `compare` highlights which parameters changed between the
      two (ADR 0005) — shipped in 0.2.0, extended in 0.3.0 to targets Digline
      cannot import, which report theirs in the answer (ADR 0005 §8)
- [ ] Repeated runs per case: score as a distribution (mean and spread), not
      a single sample
- [ ] Regression thresholds expressed relative to measured variance, not as
      absolute deltas — a drop is a regression only when it exceeds the noise
      floor of the case

**Exit gate:** a baseline comparison can state, honestly, whether an observed
difference is signal or sampling noise.

## Track C — Adoption and developer experience

*Status: ongoing, low ceremony*

- [ ] Try-without-installing: a Codespace on the examples repo — you test it
      in the browser, but in *your* environment, because Digline has no server
      by design
- [ ] The run/baseline JSON format documented as a **versioned public
      contract**. The engine is Python; the contract is language-neutral
- [x] A LangChain4j example over `HttpTarget`: one endpoint reporting the
      answer, what the call cost, and which model answered under what settings
      — so a run from a service Digline cannot import is as complete a document
      as one from a plugin (`examples/langchain4j/`, ADR 0005 §8)
- [ ] A declarative suite format, `digline run suite.yaml`, as a future ADR
      (0007). It depends on shipping **providers as entry points** — fixed
      decision 6, which is stated in `CLAUDE.md` and not yet real: a judge named
      in data has to be resolvable without anything under `src/` importing a
      plugin. Scope is the assertions whose parameters are already data; a
      custom assertion, a custom target and a `Disclosure` stay Python
- [ ] README pass with fresh eyes: assume the reader arrived five minutes ago
- [ ] A gate pairing `docs/adr/*.md` with the site's nav, the same shape as
      `test_every_example_has_a_page_in_the_site_nav` in `tests/test_examples.py`.
      digline.dev enumerates each ADR in `mkdocs.yml` and builds with
      `omitted_files: warn`, so a new ADR with no nav line fails `mkdocs build
      --strict` — and only in the cross-repo build, never in anything a
      contributor runs locally. It is the trap the examples already have a test
      for, one directory over

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
  existing principle that reports must be legible to people who don't code
- Open question, deliberately undecided: a reactive mode ("is this specific
  output valid, right now?") as opposed to the retrospective one

## Track E — Fleet (world 3)

*Status: titles only, entirely dependent on the same pilot evidence*

For software houses maintaining AI features across many end clients: a fleet
console, redacted runs traveling per tenant, per-client reports. Nothing here
is designed yet — on purpose.

---

*Suggestions and war stories are welcome as issues.*
