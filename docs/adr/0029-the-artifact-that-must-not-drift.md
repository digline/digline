# ADR 0029 — The artifact that must not drift

- Status: accepted — the text first, then the implementation written against
  it, the way
  [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0024](0024-the-judge-as-an-instrument.md),
  [ADR 0027](0027-the-run-reconciles.md) and
  [ADR 0028](0028-the-rules-that-moved.md) were
- Date: 2026-09-23
- Opens: **schema 16.** One field joins the run document, `Run.pinned`, and §3
  is the passenger rule applied to it in this record's own words, as
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 requires. Nothing else
  moves: `REGISTER_VERSION` stays at 1 (§10) and `OUTPUT_VERSION` stays at 2,
  because the wire grows by an added key
- Assumes: [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §3
  (artifacts are outside `config_hash`), §4 (withheld rather than absent) and
  §5 (a redacted run reports `unknown` and stays honest about it);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §7 (`unknown`
  rather than a fabricated change);
  [ADR 0008](0008-the-two-run-report.md) §1 (a verdict exists only against an
  approved reference, which is why `diff` never gates);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule) and
  §2 (a migration that invents nothing);
  [ADR 0016](0016-the-canary-case.md) §1 (the run being judged declares) and §5
  (a fact the headline names, never folded into `worse`);
  [ADR 0021](0021-the-register.md) §3 (the register keeps facts, not the
  sentence); [ADR 0024](0024-the-judge-as-an-instrument.md) §4.5 (the second
  cause of exit 2, and why ordering it after 1 costs nothing);
  [ADR 0028](0028-the-rules-that-moved.md) §4 (where the bar sits is a person's
  declaration, reported and never gated — and §7 here is where this record
  parts from it)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 — *no vacuously
  green assertion* — is the reason this exists at all: a declared control whose
  only outcome is a line in a report is vacuously green by construction.
  Decision 9 is honoured in §3's third condition and §8
- Turns into surface: `docs/tools.md` — specifically its closing paragraph,
  which currently promises this record and says there is no code, and which is
  amended **in the same change as this file, before any implementation**;
  [`AGENTS.md`](../../AGENTS.md) §6, where `2` acquires a third cause
- Credit: the gap was found while reading EvalSeal's work, which is also where
  the measurement in *Context* comes from

## Context

A tool description is not documentation. It is text placed in a model's context
window, and it is the text that decides whether the model calls that tool, with
what, and instead of which other one. It is an input to the system under test in
exactly the way a prompt is — and digline has said since ADR 0003 that the
prompt is the thing under test.

EvalSeal measured what that input does when nobody is watching it: **51 tool
descriptions rewritten under unchanged tool names, across 10 published MCP
servers.** The name is the identity a suite pairs on and the thing a reviewer
would notice moving. The description is the part that moved. A consumer pinning
a server version pins neither, because these were server-side edits.

digline can already carry the dump. `examples/mcp-tools` declares
`artifacts=[Path("tools.json")]`, the run records the digest and the text,
`compare` computes an `ArtifactDelta` per path, and the report prints the diff
above the score deltas because the cause belongs above the effect. All of that
is *recording*, and recording is most of the value.

What it is not is a control. `exit_code()` branches on four facts — `worse`,
`canary_moved`, `unjudged`, `scale_lost` — and a changed artifact is none of
them. So a suite can declare the tool definitions, record them faithfully, print
a red diff in a document, and exit `0`. **A note is the right record and the
wrong gate.** Somebody who declared the dump believing it protected them has a
control that has never once been able to fail, which is the shape fixed decision
3 exists to forbid.

The asymmetry with the prompt is not an oversight and must survive this record.
For a prompt, *changing the file is the experiment*: gating on it would fail the
run every time the work being measured was done. For a third party's tool
descriptions, changing the file is the thing you were watching for. One default
cannot serve both, so the difference has to be something the author declares.

This was ruled in every part on 2026-09-20 and written nowhere but in
`docs/tools.md`, as a paragraph telling a reader what digline will do and that
it does not do it yet. That paragraph is a promise on a public page. Amending it
is the first step of this record and not a cleanup after the code.

## Decision

### 1. Not an assertion, and the door is named because somebody will open it again

The obvious shape is an assertion: `ArtifactUnchanged(path="tools.json",
sha="9f2c…")`, failing when the file moves. It is wrong, and the reason is
structural rather than aesthetic.

An assertion's parameters reach its `identity`, and every identity reaches
`config_hash`. An expected digest written into an assertion would therefore move
the hash the moment the file moved — which renames every stored run (the key is
`{slug}-{config_hash}`), unpromotes the baseline, and prints *the suite changed*
over a run where no rule changed. The author would be told the rules moved
because a third party edited a sentence. That is the trap ADR 0003 §3 avoided by
keeping artifacts out of the hash in the first place, reached through a
different door.

There is a second refusal underneath the first, and it is the one that makes
this non-negotiable rather than merely costly: **an assertion cannot see an
artifact.** `EvaluatorInputs` carries the output and the case; `RunAssertion`
carries the verdicts. Neither is handed the files the run recorded, and handing
them one would make an assertion depend on something no caller of it in
Plumbline could supply — which fixed decision 1 forbids in as many words.

So the control is not a check on an output. It is a statement about two
documents, and it belongs where two documents meet.

### 2. A declaration, read at compare time

The author names paths that must not drift. `artifact_deltas()` already computes
the outcome per path, on the digest, for both sides. The declaration does one
thing: it lifts a `changed` on a **named** path into the headline, where
`exit_code()` can see it.

It is a fifth fact of the same species as `canary_moved`, and it takes the same
treatment (ADR 0016 §5): **never folded into `worse`.** A drifted artifact is
not a regression. No score moved; the input did. Reporting it as a regression
would make the report say something untrue in order to produce the right number,
and a reader who then looked for the check that got worse would find none.

Two new facts on `Headline`:

- `pinned_drifted: bool` — a path the author declared must not drift is known
  to have moved.
- `pinned_unchecked: int` — how many declared paths this comparison could not
  answer for. §8 is what that means and why it is a count rather than silence.

### 3. Where the declaration lives: the run document

`Suite.pinned: Sequence[Path]` declares it, beside `artifacts` and coerced by
the same rule. `read_artifacts` resolves it (§4), and the run records the
resolved keys as `Run.pinned: tuple[str, ...]`.

This is the section the ruling of 2026-09-20 left open, and it is the expensive
one, so the alternatives are written down with their reasons.

**Rejected: a keyword argument to `compare()`, sourced from the suite.** It
costs no schema bump and it is wrong three times over.

- `compare(run, baseline)` is public core API, importable from Plumbline. A
  parameter with a default is a control that disarms when a caller forgets it,
  in silence — the precise failure this record exists to end. A parameter
  without a default makes every caller and every test of the most-used function
  in `digline.core` carry a set that most suites leave empty.
- `entry_for()` in `digline.host.register` is pure and is handed two runs and no
  suite. It computes the register's `exit_code`. A pin it cannot see is a `2`
  recorded in a committed log that the log cannot account for.
- The deciding one: **the pin would be read from today's suite to judge last
  month's run.** Two archived documents would then yield different exit codes on
  different days, with nothing in either saying why. Everything else that moves
  an exit code in this system is recorded in the document the exit code is about
  — `config_hash`, the canary flag, the calibration band. A control read from
  outside the documents is a control whose answer depends on the reader's
  working tree.

**Rejected: a file under `.digline/<tenant>/`.** Same defect as above, plus a
second place where a suite's rules live, which ADR 0007 spent a whole record
avoiding.

**Rejected: a flag on `Artifact`.** This is the one that looks right and is the
one the 2026-09-20 ruling explicitly closed. `redact()` replaces every artifact
with `Artifact(text=None, withheld=True)`: a flag living there is *dropped by
redaction*, which disarms the declaration for the software house — the world
exit 2 operates in. `Artifact` is the payload container, and the invariant on it
(`withheld` may not carry text) is a payload invariant. A rule does not live in
the thing it governs.

**The passenger rule (ADR 0014 §1), applied to `Run.pinned`:**

| condition | `Run.pinned` |
|---|---|
| 1 — leaves `config_hash` untouched | It is a *reporting* declaration about files already outside the hash by ADR 0003 §3. Putting it in would recreate §1's trap exactly: the author adds a pin, and every baseline in the repository needs re-promoting to say that they intend to watch a file |
| 2 — migrates additively, without inventing | `()`. A run written before this idea pinned nothing, which is what an absent key already says — the same shape as `canary`, written only when non-empty (ADR 0014 §2) |
| 3 — does not widen what travels | A subset of a set that already travels. `redact()` keeps the **keys** of `run.artifacts` today and drops only the texts and digests, so every declared path is already in a redacted document; naming a subset of them adds no path that was not there. It is a declaration the suite author wrote, not a measurement of the end company's data — `canary`'s reason, in `redact()`'s own comment: a redacted document that lost it would report an exit code its own contents could not account for |

Condition 3 is worth one more sentence, because looking at it turns up something
adjacent. Artifact **paths** travel in a redacted run, and
`prompts/acme-underwriting-rules.md` is a description of a customer. That is
known and already handled at the surface that matters: `artifact_lines()`
renders the count and suppresses the table whenever anything is withheld, for
exactly this reason. This record changes nothing there and §9 keeps the new
clause inside the same discipline.

### 4. Refused when the suite loads — in `read_artifacts`, not in `Suite`

A declared path that names nothing recorded produces no delta at all. Not
`unknown`, not a row: `artifact_deltas()` iterates the union of the two runs'
recorded keys, so a path in neither is a control that never runs and never says
so. A typo would be the quietest possible failure of a feature whose whole
purpose is to stop a quiet failure.

So it is refused at load, the way a declared artifact that is not a file already
is, with the same sentence shape and in the same function.

**Why `read_artifacts` and not `Suite.__post_init__`.** `Suite` cannot check it.
The artifact set is the union of what the suite declared and what the *target*
answered through `HasArtifacts` — a `ProviderTarget` names the prompt file it
builds from, so `artifacts=[…]` need not repeat it — and a suite has no target
at construction. Pinning a target-contributed prompt is legitimate and must
work. `read_artifacts` is the one place that holds both halves.

It is also the only place that can resolve the key. The author writes
`tools.json`, relative to the suite's own directory; the run records it keyed
against the **perimeter**, which is `examples/mcp-tools/tools.json` or, for a
file outside the repository, the `../` it is. A declaration matched against the
written path rather than the recorded key would miss by a prefix. `Suite.pinned`
therefore keeps the relative thing a reader typed — as `Suite.artifacts` does —
and `Run.pinned` holds the resolved keys, deduplicated after resolution, because
`tools.json` and `./tools.json` are one pin declared twice.

### 5. The rule is read on the comparison's rows

`ArtifactDelta` gains `pinned: bool`. `compare()` sets it from `run.pinned`;
`Comparison.pinned_drifted` is `any(d.pinned and d.outcome == "changed")`.

This is what *"the rule sits on the comparison, not on the artifact"* means
mechanically, and it is the difference between a control that survives a
boundary and one that evaporates at it:

- `redact()` works on **one** run, and one run has nothing to compare itself
  with. A redacted run reports `unknown` and stays honest about it (ADR 0003
  §5). This is the only disarming this design accepts, and §8 makes it loud.
- `withhold_artifacts()` is for the party holding **both** runs and producing a
  document for someone who will not. It keeps `outcome` and drops the payload —
  so `changed` survives, and the pin with it. **`pinned` must be carried in that
  `replace()`**, beside `outcome`. Carrying one and dropping the other would
  produce a document that knows a file moved and has forgotten that somebody
  declared it must not.

That second bullet is the software-house case, and it is why the rule cannot be
stated on the artifact: there, the payload is gone by design and the outcome is
a fact the caller established.

**That one line gets a test by name, because dropping it fails quietly.**
`test_a_withheld_comparison_still_knows_the_path_was_pinned`, in
`tests/test_artifacts.py`. A `replace()` that forgets `pinned` raises nothing,
type-checks, and produces a document that reports a moved file and has silently
forgotten it was declared — green everywhere, wrong for the one reader who
cannot check for themselves. So the test is paired with a **mutation control**:
remove `pinned=` from that call and the test must go red for that reason. A gate
on a field nobody can see going missing has to be shown to fail, or it is
verifying the field's existence and not its carriage. (Clear `__pycache__`
after restoring the mutation: a same-length swap put back within a second keeps
the mutant loaded.)

### 6. Exit 2, not 1

`pinned_drifted` joins `unjudged` and `scale_lost` in the second branch of
`exit_code()`.

The reason is the one that decided it on 2026-09-20 and it is narrower than
"both codes stop a pipeline". A redacted comparison yields `unknown` on the
pinned path, and `Comparison.artifacts_changed` already refuses to read
`unknown` as a change. Returning `1` off a fact the layer below declines to
assert would have `exit_code()` claim, one layer up, exactly what the fact layer
will not claim. `2` already means *the numbers beside this are not what they
look like*, which is true here: the system that produced them is not the system
the reference approved.

Precedence is unchanged and deliberate. A regression or a moved canary still
outranks a drifted pin, for ADR 0024 §4.5's reason: both codes stop the
pipeline, the headline names both facts, and putting the quieter one first would
hide a real regression behind it.

`EXIT_UNJUDGED` keeps its name. `2` now has three causes and the constant is
named after the first; renaming an exported constant to fix a naming debt would
break consumers to improve a docstring. `exit_code()`'s own body is the
enumeration, and its docstring names all three there — which is the one place an
enumeration is safe, because it is the source (`digline.wire.contract`'s rule
about counts and enumerations).

### 7. `changed` fires. `new` and `missing` do not

Four outcomes are reachable for a pinned path. Only one of them is drift.

- **`changed`** — both sides recorded it, the digests differ. This is the fact,
  and the only one that returns 2.
- **`new`** — the baseline has no such artifact. The commonest cause is adding
  the pin: the first comparison after it would go red on arrival, teaching the
  author that the feature is noise before it has ever caught anything.
- **`missing`** — the run has no such artifact. Unreachable through
  `Run.pinned`, because §4 refuses a pin that names nothing the run recorded,
  and reachable only for the baseline's own pins, which §8 declines to gate on.
- **`unknown`** — §8.

`new` and `missing` are governed by the rule `digline.core` already applies
everywhere it reads an outcome — every `outcome not in ("same", "unknown")` sits
beside a docstring saying it: **absent is not a change.** A comparison must not
report as movement a file that one side simply never had. This is the same
discipline that lets a baseline promoted last month keep comparing.

This is the section most at risk of being read as a loophole, so: a third party
who wanted to evade the control by *removing* the tool dump from their server
would produce a `missing`, which cannot happen, because the run's own recording
is what the pin is validated against — the dump not being there is a failed run,
not a green one.

### 8. A withheld pin never passes, and never fails, and is never silent

The third thing 2026-09-20 left open, and the one with a real conflict in it.

The author declared *this must not drift*. Redaction means we cannot tell. The
conflict is that both available answers are lies: calling it drift asserts a
fact nobody established, and calling it clean says *it did not drift* about a
question that was not asked.

**The ruling: `unknown` does not fail, and does not pass either.** It is a third
state with its own count, `pinned_unchecked`, named in the headline sentence and
carried on the wire.

The failing half follows §7's rule: absent is not a change, and a withheld
digest is the most absent a fact can be. It also follows §6 one step earlier —
if `exit_code` may not assert what the fact layer declines to assert, neither
may the fact layer assert it about a digest it does not hold.

The silent half is refused outright, and this is where the design earns its
keep. A control that quietly reports success when it could not run is worse than
no control, because it produces the same green as a control that ran. So the
comparison says how many pins it could not check, every surface prints it, and
the sentence is addressed to the person who can do something about it: the
reader holding *both* runs can answer this question, and
`withhold_artifacts()` (§5) is how they answer it for the reader who cannot.

Whether an unchecked pin should be made to fail is a **policy about a pipeline**,
not a fact about a run, and it belongs to whoever runs the pipeline. `--json`
carries the count so that a caller who wants that rule can have it in one line.
digline does not grow a flag for it: a flag that turns *I do not know* into
*failed* would be the first place in this system where a number asserts more
than the document behind it.

### 9. The run's declaration governs; a withdrawn pin is reported, not enforced

Two runs, two pin sets. The run being judged declares, by ADR 0016 §1's reading
— a flag that moved between the two is read from the side under judgement.

A pin present in the baseline and absent from the run is therefore **not**
enforced. It is an author withdrawing a declaration, and a withdrawal that could
not be made without a red would be a pin nobody could ever remove. It is not
silent either: the comparison reports it, in the manner of ADR 0028 §4 —
reported and never gated, because where a bar sits is a person's declaration.

The cost of that is stated rather than discovered: **deleting a line from the
suite disarms the pin, and the only thing standing in front of that is code
review.** A pin is not in `config_hash` (§3), so unpinning does not unpromote the
baseline and no gate fires. This is the same protection the *cases* have and one
less than the thresholds have, and it is the price of condition 1. The suite is
versioned in git; a diff that removes a pin is a diff a reviewer can see, and
that is the whole of the guarantee.

### 10. What does not move

**The register gains nothing, and `REGISTER_VERSION` stays 1.** The temptation
is to add `pinned_drifted` to `RecordedOutcome` so a promotion's recorded `2` is
accounted for. The precedent refuses it: `scale_lost` moves the exit code and is
*not* in the register either, and the entry already carries `exit_code` and
`artifacts_changed` — which is necessarily `true` whenever a pin drifted, since
the pinned path's outcome is `changed`. The cost of the alternative decides it:
the register is a format and **nothing migrates it** — a bumped version makes
every committed register in every repository permanently unreadable, by a design
decision ADR 0021 made on purpose. A field that is nearly derivable does not buy
that.

**`OUTPUT_VERSION` stays 2.** Two added keys on the headline block, and the
contract's stated rule is that added keys do not break a consumer. The record in
`digline.wire.contract` gains an entry saying so, which is how that record grows.

**`digline diff` never gates on it.** A pin is a statement about a reference, and
neither side of a diff was approved by anybody (ADR 0008 §1). `Difference` marks
the row and stops, and `cmd_diff` continues to exit 0 on any report it can
produce.

**The report prints a count when anything is withheld, and a marked row
otherwise.** `artifact_lines()` already suppresses the table behind
`any(delta.withheld …)` because a list of paths describes a customer; the pin
clause lives inside that same branch and names no path when the table is gone.

**TOML declares it.** `pinned` is a list of paths and nothing else — no code, no
callable — so it passes the `suite.toml` form by the same handling `artifacts`
gets, including the perimeter check on each entry (ADR 0007 §6). A control
available only to suites written in Python would be a control the declarative
users cannot have, and there is no reason here of the kind that keeps `pricing`
out.

## Consequences

The feature costs a schema bump, which is a ritual with a release in the middle
of it: `SCHEMA_VERSION` 15 → 16, a `_STEPS` entry that writes nothing (a run
that predates this pinned nothing, and `()` is what an absent key already says),
the committed example baselines migrated, and the dependency caps moved in step.
Nothing else in this record can be built before that, and §3 is the argument for
paying it rather than taking the cheaper shape.

`examples/mcp-tools` is where it is demonstrated, because it is the example the
problem was found in: `pinned=[Path("tools.json")]` beside the `artifacts=` line
that is already there, and the behaviour assertions stay — a pin says the
definitions moved, the assertions say what the move did, and the example ships
both because neither answers the other's question.

The paragraph in `docs/tools.md` that promises this record stops promising and
starts describing. That edit is part of the change that adds this file, and it
precedes the implementation: a public page saying *no ADR written* is repaired
by writing the ADR, not by shipping the code and tidying afterwards.

What this does not do: it does not watch a server. It watches a **file**, and
`docs/tools.md` already says at length that keeping that file fresh is the suite
author's job and belongs in the CI step immediately before `digline run`. A pin
on a dump that stopped being refreshed is a control that passes forever, and no
amount of gating fixes a stale input — it only makes the stale input louder when
it finally moves. That paragraph stays exactly where it is, and it now stands in
front of a control that can fail, which is the only condition under which it was
ever worth reading.
