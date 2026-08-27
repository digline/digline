# ADR 0003 — Artifacts travel only when the suite says so

- Status: accepted
- Date: 2026-08-26
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md), §2 and §3
- Touches: fixed decision 9 (`CLAUDE.md`), which lists what crosses a boundary

## Context

A run records `config_hash`, the commit, and every verdict. It does not record
the file that produced those verdicts.

For an LLM system that file is usually a prompt, and the prompt **is the thing
under test**. The gap shows up the moment anyone works the way this tool expects
them to work: while a prompt is being tuned the tree is dirty, `git_commit` ends
in `-dirty`, and two runs of two different prompts are indistinguishable from
their run files. `-dirty` says that something was uncommitted; it cannot say
what, and the reader who needs to know is reading the run file weeks later.

So the baseline — the artifact this project exists to make reviewable — is
missing the one input that explains it. Friction 24.

The second half of the problem is a boundary question, and it is why this needs
an ADR rather than a patch. A prompt is not a verdict and it is not a
measurement. It is a *file*, and files are exactly what decision 9 keeps on the
near side of a perimeter.

## Decision

### 1. A suite declares what is under examination

`Suite.artifacts: Sequence[Path]` names the files that *are* the thing being
tested. Nothing is discovered by convention: a file that is evidence is a file
someone named, for the same reason the CLI never goes looking for a suite.

### 2. The run records content and digest, and the CLI does the reading

`Run.artifacts: Mapping[str, Artifact]`, where `Artifact` carries `sha` — the
SHA-256 of the bytes — and `text`. `SCHEMA_VERSION` goes to 7, additively: a
schema-6 file gains `artifacts: {}` and is migrated in place.

The files are read by the **CLI**, not by the driver, and handed to `execute()`
the way `created_at` and `git_commit` already are. The driver stays free of the
filesystem, and a run can still be built in a test without one.

`git_commit` keeps its job. `-dirty` still means "not reproducible from the
repository"; it is simply no longer the only trace, and it is no longer the only
thing a reader has when the answer is "the prompt was different".

### 3. Artifacts are not part of `config_hash`

Changing a prompt must leave the two runs **comparable**. That comparison — old
prompt against new, with the score deltas beside the text diff — is the
experiment this whole tool is for, and folding artifacts into `config_hash`
would refuse it: every prompt edit would make the previous baseline
un-promotable and the comparison a wall of `new` plus `missing`.

A prompt change is a change to the **system**, not to the rules that judge it.
That is the same line `config_hash` already draws around the test data.

### 4. Artifacts do not travel unless the suite says so

`Disclosure.artifacts: bool = False`.

The tempting default was the other one. An artifact is the software house's own
property — it wrote the prompt, it owns it, and world 2 arguably has every right
to carry it between its own customers. That argument is true and it is not
enough.

A prompt is written *for* an end company, and it is where that company's rules
end up: eligibility conditions, thresholds, the phrasing legal insisted on, the
name of the internal system it must never mention. Often the business logic that
the customer would least like to see leave. The text is the software house's
artifact and the *content* is frequently the client's, and no default can tell
the two apart by looking.

So the rule from ADR 0002 §3 holds without an exception, which is worth more
than the convenience: **code that redacts without knowing the suite's policy
discloses less, never more.** A default of `True` would have made this the one
field where forgetting to pass a `Disclosure` leaks, and a principle with one
exception is a principle nobody can apply from memory.

Turning it on is one line in the suite, which is code, which goes through a
review — the same route by which every other widening of a perimeter is decided.

Locally nothing changes: the complete run always carries its artifacts, because
in world 1 the developer owns both the prompt and the data.

**The digest goes with the text.** This was very nearly left open, and leaving it
open would have meant deciding it by accident: the first implementation kept the
`sha` and dropped only the `text`, which reads like a careful middle course. It
is not one. A digest is a **verifier**, and a prompt is not drawn from a large
space — the software house wrote the template and the end company tuned the
numbers in it. Enumerating the plausible variants and hashing each against a
leaked digest recovers the text, and with it the rules:

```
recovered in 0.00s from the digest alone:
  Escalate the ticket when the refund exceeds 2500 EUR and the account is older than 90 days.
search space: 14874 candidates
```

Fourteen thousand candidates is not an attack, it is a loop. A digest travelling
beside a withheld text would hand over most of what withholding the text was
for, which makes it the *inverse* of the decision above rather than a softening
of it.

So redaction removes both, and `Artifact` carries `sha=""` with `withheld=True`
— absent rather than emptied in the document, like every other payload field
(decision 9). The cost is real and is stated in §5.

### 5. What the reader sees

`compare()` produces `ArtifactDelta` per path, and the report renders the
**unified diff** — removed and added lines with three of context, fixed width,
inside a `<details>` open below thirty changed lines and closed above it —
**above** the score deltas: what changed comes before what it did. The comparison
screen shows the same, because it is the same function. The terminal shows the
tally only, `prompt.md · +3 −1 lines`: a prompt unrolled there would bury the
regressions it is meant to explain.
An artifact withheld by disclosure is marked as withheld rather than absent —
"this suite chose not to send it" and "this run predates the feature" are
different facts and a reader is owed both.

**A redacted document shows the count and nothing else.** Not the diff, not the
digest, not even the path — `prompts/acme-underwriting-rules.md` is a
description of the customer often enough that a list of paths is payload. What
survives is the sentence, *"1 file under test changed"*, which is a measurement.

That count exists because `withhold_artifacts()` is applied by the party holding
**both** runs, which computes the outcome and then strips what it was. `redact()`
cannot do that job and must not try: it works on one run, and one run has
nothing to compare itself with.

**A redacted run file, on its own, cannot say whether a prompt moved.** That is
the price of §4 and it is paid openly: with no digest on either side the outcome
is `unknown`, not `same`, because `same` would be a guess wearing the clothes of
a finding. The headline says *"the files under test are not included, so whether
they changed is not known"*, and `Comparison.artifacts_changed` stays false —
a sentence in front of an end company must not assert something nobody
established. World 2 gets the verdicts and the fact that a file was withheld;
for whether it moved, it has to ask world 1, which still holds both.

`runs_page` labels each run with the short digest of its artifact set — `prompt
a1b2c3` beside the moment — so a column of runs sorts by prompt at a glance
without gaining a column.

## Consequences

- A baseline is now self-contained evidence: the verdicts, the configuration
  that judged them, and the prompt that produced them, in one committed file.
- Two runs from a dirty tree with different prompts are distinguishable, and the
  prompt is reproducible from the run file alone. That is the test that closes
  friction 24.
- Run files grow by the size of the declared artifacts, per run. A suite that
  declares a 40 kB prompt and keeps a hundred runs pays four megabytes for the
  history. Retention is already mandatory on the production side (ADR 0002 §6);
  on the repository side `runs/` is gitignored and the cost is local disk.
- A suite that declares no artifacts is unchanged in every respect, including
  the bytes of its run files beyond `"artifacts": {}`.

## Not decided here

Whether a **keyed** digest could give back what §4 takes away. An HMAC under a
per-tenant secret compares within one perimeter and verifies nothing without the
key, so world 2 could see that a customer's prompt moved without being able to
recover it. The capability is genuine and the objection in §4 does not apply to
it.

What stops it today is that the key has to live somewhere the redacting side can
reach, and that place does not exist yet: it is the production store and the
bridge, ADR 0002 §6. Deciding where a secret lives before there is anything to
put it in would be deciding it twice. Revisit when the bridge is built.
