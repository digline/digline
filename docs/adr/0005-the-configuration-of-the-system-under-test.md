# ADR 0005 — The configuration of the system under test

- Status: **proposed — open question, nothing implemented**
- Date: 2026-08-28
- Assumes: [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §3
  (artifacts are not part of `config_hash`),
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the payload
  stays where it is born)
- Blocks nothing: `digline-bedrock` ships without it, and the gap is documented
  where a reader meets it.

## Context

A run records the verdicts, the fingerprint of the configuration that produced
them, and — since ADR 0003 — the files under test. It does **not** record which
model answered, at what temperature, under what token cap, or with which extra
request fields.

`config_hash` is built from the assertions, their thresholds and tolerances, and
`samples`. Nothing the target does reaches it: not `model`, not `temperature`,
not `max_tokens`, not `additional_request_fields`. `Response.metadata` carries
the model and the token counts to the assertions, and `CaseResult` keeps only
`case_id`, `verdicts` and `suspended` — so none of it is persisted either.

Three consequences, and they are not equally serious.

**The report can say something true that reads as false.** Two runs that differ
only in temperature — or in a Bedrock `additionalModelRequestFields` — produce
the same `config_hash`, and `compare()` reports *"The configuration is the same
as the reference."* Under the current definition of "configuration" that
sentence is exact: the rules that judge did not move. To a reader in world 3 it
says something else, namely that nothing about the system moved. The word is
doing two jobs.

**A baseline cannot say what produced it.** ADR 0003 closed this for the prompt
and left it open for everything around the prompt. A run from a dirty tree with
`temperature=0.7` and one with `temperature=0.3` are the same document.

**The gap is invisible.** Nothing warns; the numbers simply mean less than they
look like they mean. `digline-bedrock` documents it on the argument itself,
which is a patch on one plugin's docstring, not a decision.

This is deliberately **not** a case for folding these values into
`config_hash`. ADR 0003 §3 decided that a change to the system under test must
leave two runs *comparable* — that comparison, old against new with the score
deltas beside it, is the experiment digline exists for. Fingerprinting the
decoding parameters would make every such experiment un-promotable. The
question is not "should this enter the hash" but **"should the run record the
system's own configuration, beside the hash and not inside it"**.

## The question

Should a `Run` record the configuration of the system under test — model,
temperature, token cap, provider-specific request fields — and should
`compare()` and the report show **which parameters changed**, by value?

The external feedback that prompted the second half: a difference reported as
"the configuration differs" is not actionable, while `temperature 0.3 → 0.7` is.
Whatever is recorded should be diffable by name, the way `ArtifactDelta` already
diffs a prompt, rather than collapsed into a hash somebody has to go and
reconstruct.

## What has to be decided, and by whom

**1. Who declares it.** A target knows its own parameters, but `ProviderTarget`
builds the `Response` and has no hook for extra metadata; a plugin wanting to
contribute one today would have to override `__call__` and reimplement the
timing and the pricing. Either the base grows a hook — an overridable
`configuration()` alongside `artifacts()` and `preflight()`, which is additive
and non-breaking — or the suite declares the values itself, which is honest but
duplicates what the target already holds.

**2. Where it lands.** `Run.system_config`, beside `Run.artifacts` and outside
`config_hash`, is the shape that follows from ADR 0003. It is a schema change
(`SCHEMA_VERSION`), migrated in place like schema 6 → 7 was.

**3. Whether the values are payload.** This is the part that needs ADR 0002 and
not just a field. A temperature is a measurement of the system and crosses a
boundary without difficulty. `additionalModelRequestFields` is not so simple: it
can carry a guardrail identifier, an account-specific configuration, or a
customer's own tuning — the same argument ADR 0003 §4 made for prompts, in a
smaller box. The likely answer is the same one: **a declared `Disclosure`, with
the prudent default**, and the model id treated separately from the free-form
fields, since a model id is a public product name and the fields are not.

**4. What the reader sees.** Named deltas — `temperature 0.3 → 0.7`,
`max_tokens 1024 → 512` — above the score deltas, like an artifact diff, in
both the report and the terminal. A withheld field shows as withheld rather than
as absent: "this suite chose not to send it" and "this run predates the feature"
are different facts, and ADR 0003 §5 already decided a reader is owed both.

**5. What "changed" means for a run whose target was a plain function.** A
`Target` is any callable; most have no configuration to declare. Absent must
stay absent, and it must not read as a change.

## Not decided here

Everything above. Nothing in this ADR is implemented, and no code depends on it.
Until it is decided, the contract in force is the one stated on
`BedrockTarget.additional_request_fields` and on `OpenAITarget.extra_body`:
these values change what the model does, they are not part of `config_hash`,
and a difference in them is **not** reported as a configuration change. A
suite that needs the difference to show today keeps the values in a file and
declares it in `Suite.artifacts`, where ADR 0003 already carries them into the
run and into the diff.
