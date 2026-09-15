# ADR 0019 — The reasoning operator: the policy, the seat, and the journal

- Status: accepted — the text first, the implementation written against it on
  `reasoning-operator`, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0011](0011-the-mcp-server.md),
  [ADR 0012](0012-the-reading.md),
  [ADR 0013](0013-the-pytest-plugin.md),
  [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0016](0016-the-canary-case.md),
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) and
  [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md) were
- Date: 2026-09-14
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states, and an error
  is neither green nor a regression);
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the payload
  stays where it is born, the verdict travels), §8 (a baseline is an approved
  reference);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4 (a digest
  is a verifier);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5–§6 (the measured
  floor, and a flip is never within noise);
  [ADR 0010](0010-per-group-aggregates.md) §3 (the expanded aggregate's name is
  a public string);
  [ADR 0011](0011-the-mcp-server.md) §1 (absence by construction), §9 (the
  playbook rides with the instrument);
  [ADR 0012](0012-the-reading.md) §3 (the fact list and its closed
  vocabularies), §4 (no reason, and the boundary is a *type*), §5 (the reading
  states and never advises, and the multi-run vocabulary is out of its reach);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule), §3 (a
  ledger is a decision with its own reason to exist);
  [ADR 0016](0016-the-canary-case.md) §5 (the one place a single run is not a
  draw);
  [ADR 0017](0017-the-journal-and-the-resumed-run.md) §2 (a work file is not a
  document), §6 (the refusal list is exactly the set of facts the document
  asserts)
- Turns into surface: [`AGENTS.md`](../../AGENTS.md), the `operating-digline`
  skill, and `examples/operator/` — which is where all of this lands
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 9 is **reaffirmed**
  by §5 — a clause names identifiers and never contents; decision 2 by §8 — the
  journal lives in `.digline/<tenant>/` and never outside the repository; and
  decision 3 by §6 — a policy that could excuse anything is a policy nobody set
- Requires: **nothing new from the core.** Every organ this assembles has
  shipped for another reason. §12 names the two core gaps the work found and
  defers them
- Number: 0019. 0001–0018 are claimed on `main` and on every branch at the time
  of writing

## Context

digline answers one question: *did the system get worse than what somebody
approved?* The operator loop — [`DESIGN.md`](https://github.com/digline/digline/blob/main/examples/operator/DESIGN.md)
and `examples/operator/` — is what asks that question on a schedule when nobody
is looking, absorbs the measurement's own noise, and wakes a human only for
drift that deserves a decision.

It automates the judgment `AGENTS.md` writes down, and nothing beyond it. What
it cannot do is **exercise a judgment nobody wrote down as data**, because there
is no such artifact. The escalation rules exist; they are simply scattered
across three kinds of thing with three lifetimes:

| Where | What it encodes | Form |
|---|---|---|
| `AGENTS.md` §1–8 | the whole judgment layer | prose |
| the `operating-digline` skill | the same eight rules, held identical by `tests/test_agents.py` | prose |
| `operator.toml` | cadence, `max_reruns`, `structural_flip_cases`, the budget | **data** |
| `loop.py::cycle()` | the classification order — four events decided in sequence | **code** |
| `dossier.py`'s `HEADLINES` / `BECAUSE` | the per-verdict sentence *and the rule it cites* | prose-in-code |
| `DESIGN.md` §2–4 | what it may do alone, what it escalates | prose |
| `docs/guide.md` §8 | the five triggers | prose |
| [ADR 0016](0016-the-canary-case.md) §5 | the canary's always-wake | **ruled** |

Read that table as one fact: **the stopping rule is data, the classification is
an `if`-order, and the reasons are prose in three places.** Nothing anywhere can
say *which policy ruled a given cycle*, because there is no policy to name.

The job description was written before the job existed.
`docs/guide.md` §8 divides its five triggers in a way this record
is the answer to:

> The first three come from **inside**: you changed something, and digline says
> so the next time you run it. Nothing is required of you but to answer.
>
> The last two come from **outside**, and nothing announces them. The model
> moves under you; a customer finds something you never thought to test. These
> are what "maintenance" means to the person doing it, and each needs a *habit*
> rather than a message — a schedule for one, a reflex for the other.

A habit is a thing an operator can have. But `loop.py` has no seat for one:
`escalate` is *derived* from the verdict — `drift` and `structural` and
`system-error` wake somebody, everything else does not — so there is no place a
decision could be made, and nothing for a policy to be exercised *by*.

**The hazard, stated before the design, because it is why the form matters more
than the content.** A policy that is prose is a policy an agent reinterprets; a
policy that is code is a policy an agent can rewrite, and is executable by the
same process that reads it. Both fail the same way and the failure is silent:
the escalation rules drift toward whatever the model found convenient this
week, and nobody can point at the moment they moved. The whole value of the
artifact is that **the human approves the policy and the agent exercises it and
never edits it** — so the artifact has to be shaped to make editing it a thing
that happens in a diff, and re-deriving it a thing that cannot happen at all.

*The reconnaissance this record was written from, the measured costs, and the
pilot's own numbers are recorded in the working material rather than reproduced
here: `private/` is a separate repository and this one is public. It is the same
boundary [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) drew
for the signals that opened it.*

## Decision

### 1. The policy is one file, it is TOML, and it is `operator.toml`

There is **one form**, and it is the file that already holds the four numbers an
agent could otherwise talk itself into. `operator.toml` gains a `[policy]` table
and an ordered array of clauses; it does not gain a sibling.

```toml
[policy]
# The identity a cycle reports. §4.
name = "northwind-weekly"

# A window in which a hold is preferred. The cycle records the window it
# evaluated under, or the decision is not reproducible. §2.
quiet_hours = { from = "22:00", to = "06:00", tz = "Europe/Rome" }

[[policy.hold]]
name = "known-red-travel"
aggregate = "precision[group=travel]"
because = "red in the approved baseline; ADR 0010 §10 ships it deliberately"

[[policy.hold]]
name = "flaky-waterproof"
case = "is-it-waterproof"
assertion_id = "e7c3e24524385570"
max_cycles = 3
because = "wobbles on its own; three cycles of drift is the real signal"
```

**Not `.py`, and not "equal citizens" with a Python form.** That rule exists in
[ADR 0007](0007-the-declarative-suite-format.md) §9 to stop the *engine*
forking, and there is no engine here to fork. The asymmetry that decides it is
0007 §7: a data suite is pinned to `NOTHING_EXTRA` because a suite that is data
must not be able to widen a boundary. **A policy widens no boundary** — it
decides who sleeps — so §7's whole reason for keeping a Python form does not
transfer. What does transfer is the hazard above: a form that cannot compute is
a form the agent cannot be argued into re-deriving.

**Not `.md`.** A policy a program must obey cannot be prose. The split that
survives is the honest one: **the numbers are in TOML, the reasons stay in
`AGENTS.md`**, and a clause's `because` is a sentence for the human reading the
diff, never a rule the program parses.

**The cost, stated rather than buried**, in the shape ADR 0007 §5 stated its
own: the day a clause needs a predicate, it needs **declared vocabulary** — a
new key, in this record's successor, with its own name and its own meaning. The
day it needs an *expression language*, this is the wrong artifact and the
answer is a different one. There is no escape hatch, of any kind, and that is
the feature rather than the omission.

**And `operator.toml` is the file the operator may not write**, which §9 turns
into a probe. That is not a new claim: the file's own first line has said it
since it was written — *"The operator's configuration. It reads this; it never
decides it."* Putting the policy anywhere else would have created a second
artifact with the same rule and one more place to get it wrong.

### 2. The judgment seat: `escalate` stops being a function of `verdict`

`Cycle` carries the verdict it carries today, computed the way it is computed
today. **The deterministic classification does not move**, and that is
load-bearing: layer 2 of the alert is rendered from it, `tests/test_examples.py`
asserts all four scenarios against it, and it is reproducible in a way a model
is not.

What changes is one line. `escalate` stops being `bool(reproduced)` and becomes
a **decision**, taken after the classification, carrying three things:

    Decision:
        escalate: bool
        reason:   str          # prose, for the human
        clause:   str | None   # the policy clause applied, by name

A cycle with no policy behaves exactly as it behaves today: no clause applies,
the verdict's own escalation stands, and `clause` is `None`. That is what makes
this safe to land before any policy exists.

**Quiet hours are the one clause that needs a clock**, and the clock is why the
rule is written here. `digline.host` is the only layer allowed to read wall
time, so that a run is reproducible; a decision that depends on the hour is
reproducible only if **the cycle records the window it evaluated under**. So a
policy declaring `quiet_hours` produces a cycle that states the local time it
was evaluated at and the window in force. A decision nobody can re-derive is a
decision nobody can review.

### 3. The cited clause

A decision carries the name of the clause it applied, and the rule is the whole
reason the seat exists:

> **A reason that cites no clause is the model's opinion; a reason that cites
> one is the policy being exercised.**

So a hold with no `clause` is not available. Either a clause covered this cycle
— and the decision names it — or no clause did, and the verdict's escalation
stands. There is no third branch in which the reasoner holds something because
it judged the week quiet. That is the sentence that keeps this from being an
agent with opinions about your pager.

It follows that the clause name is a **public string**, in the cycle file and in
the journal, with the same consequence [ADR 0010](0010-per-group-aggregates.md)
§3 accepted for an expanded aggregate's name: renaming a clause is a rename
everywhere it has been recorded, and it is written down here rather than left to
a format string.

### 4. `policy_digest`, and it is `cases_digest`-shaped

A cycle reports the identity of the policy that ruled it:

    policy_digest = sha256(canonical(parsed policy))[:16]

**Over the parsed document, not the file's bytes**, the way
`Suite.cases_digest()` is taken over `canonical(cases)` — so reflowing a comment
does not churn an identity, and two policies that say the same thing have the
same digest.

The precedent is deliberately `cases_digest` and **not** `config_hash`:

- it is **never in `config_hash`.** A policy change must not unpromote a
  baseline. The policy judges the measurement; it does not change what was
  measured, and a hash that moved would print *the rules changed* over a run
  where no rule did;
- it is **never written to a run document.** A run is a measurement, and which
  policy read it afterwards is not a fact about the measurement;
- it lives in the **cycle file and the journal**, which are the two places that
  are about the cycle rather than about the run.

[ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4's
digest-is-a-verifier objection is asked and does not apply: a policy is the
software house's own operational rule, not the end company's data, and §5 is
what keeps it that way — a digest that could recover a clause recovers a clause
naming identifiers, never contents.

### 5. What a clause may name: identifiers yes, contents no

A clause may name a `case_id`, an assertion — by name or by `assertion_id` —
an aggregate's name (`precision[group=travel]`, by ADR 0010 §3), and a verdict.
Five keys, and that is the whole vocabulary: §1's promise was that it grows by
declaration rather than through an escape hatch, so a sixth is a decision
somebody writes down and not a key somebody adds. It may **never** name
`Case.vars`, an output, a judge's `reason`, or an artifact's text.

This is decision 9 reaffirmed rather than amended, and the line is the one
`explain` already draws by type: the fact list has no field a reason could
occupy ([ADR 0012](0012-the-reading.md) §4), so a reasoner reading it cannot
construct a clause out of payload even if asked to. What §5 adds is the rule for
the *file*, which a human writes and which no type constrains.

The reason it is worth its own section: the decision journal (§8) records the
clause that fired, so **whatever a clause may name is a thing that ends up
written down, cycle after cycle**. An identifier is the customer's word for
their own test; the contents are the customer's data. The reconnaissance for
capture reached this from the other direction and flagged it as the question to
settle before a pilot repeats it, and this is the settlement.

*Amended 2026-09-15 ([ADR 0021](0021-the-register.md) §7): naming a case inside
the tenant's own repository — a clause in `operator.toml`, a line in the ignored
journal — is in-perimeter naming and is allowed; a content-derived identifier
never crosses a ledger's travelling surface, and no register entry carries a
case id at all.*

### 6. The policy is a narrowing instrument only

**A clause may hold. A clause may not wake.**

The default is the deterministic verdict's own escalation, and a policy can only
take cycles out of it. There is no clause that escalates something the classifier
held — and the absence is a design rather than a gap. A new reason to wake
somebody is a new *classification*: it belongs in `loop.py`, deterministic,
reproducible, and tested against the four scenarios, where a reader can see it
and a test can hold it. A policy clause that wanted to widen is a signal that the
classifier needs a verdict it does not have, and the answer is to give it one.

**Three floors no clause may lower, and the list is closed:**

| floor | why |
|---|---|
| the canary's always-wake ([ADR 0016](0016-the-canary-case.md) §5) | evidence about *which system answered*; re-running cannot settle it, and neither can a preference |
| `max_reruns`, mid-cycle | decided before the first run so it is not decided by the mood of one. Raising it is a stopping rule chosen after the fact |
| an exit code of `2` | nothing downstream of an unjudged run is meaningful, the green checks included. A held `2` is a suite that stopped working and a pager that stopped ringing |

**A fourth answer shares the field and is not a fourth floor.** Where the digest
a cycle reports is not the digest of the policy on disk (§9), no clause is
consulted at all — not because a floor forbade the hold, but because there is no
policy in force to do the holding. A decision reports it in the same place, as
`policy-moved`, because a reader asking *why was this not held* wants one answer
rather than two; this record keeps the two apart because they are different
facts, and the sentence a reader is shown says which one happened.

This is fixed decision 3 in a new costume, and the section exists to pay it: a
policy that could excuse anything is a policy nobody set, and the three floors
are what stop `because = "…"` from becoming a universal solvent.

### 7. The decision arrives as a file

`dossier.py` is **pure** — a cycle in, a document out, no clock and no
filesystem of its own — and its output is gated byte-for-byte against the two
alerts committed under `examples/operator/alerts/`. That gate is an asset, and
this record is written so as not to spend it.

So the decision reaches the dossier the way layer 3 already does: **as a file**,
named on the command line, absent when it did not run.

    python loop.py     --config operator.toml --out cycle.json
    python decide.py   --cycle cycle.json --out decision.json     # the seat
    python judgment.py --cycle cycle.json --decision decision.json \
                       --out judgment.md                          # layer 3, opt-in
    python dossier.py  --cycle cycle.json --decision decision.json \
                       --judgment judgment.md --out alert.md

Two consequences, both stated rather than discovered:

**`CYCLE_FORMAT` goes 3 → 4**, because the cycle now carries `policy_digest`,
the evaluated window and the decision. It is the example's own format and not
the tool's, so nothing under `src/` moves and no `OUTPUT_VERSION` is touched.

**The captured alerts are regenerated, and a third joins them.** `draw` and
`drift` are rebuilt with no decision recorded; `held` is the **same cycle** as
`drift`, decided under the policy — so the two documents differ in nothing
except what a declared policy did about an identical measurement, which is what
makes them a comparison rather than two anecdotes. A cycle written before this
record says so rather than pretending: `_wall()` already models that sentence
for a cycle predating the probe, and the decision line takes the same shape —
*an absence is stated, never faked.*

### 8. The journal: append-only, gitignored, and a hold is always written

    .digline/<tenant>/decisions/<suite>.jsonl      append-only, gitignored

**Every decision is written, and a hold most of all.** A hold nobody records is
indistinguishable from a cycle that never ran — which is the failure mode that
would make a quiet quarter unreadable, and the quiet quarter is the thing this
whole design is trying to earn.

One line per decision: the cycle key, the `policy_digest`, the clause, the
decision and its reason, and the facts it turned on — the ones cited, never the
whole list.

**Gitignored, on the `seen.json` precedent** rather than on
[ADR 0017](0017-the-journal-and-the-resumed-run.md)'s. 0017's journal is a
*work file* deleted on success; this one must survive, so what it borrows is the
other pattern in this project's own dogfood: a private, append-forever history
from which a committed, reviewable artifact is later distilled by an explicit
command.

Being ignored also closes a trap that would otherwise be found the hard way.
`git_commit` reads `git status --porcelain`, so a tracked journal written during
a cycle would leave the tree dirty and **stamp the very run it records as
`-dirty`**. The same hazard is already documented, in this project's own
dogfood, for a `tee`'d run log. Porcelain ignores the ignored, so the rule that
keeps the history also keeps the run reproducible.

The journal is not a document: it is never listed, compared, reported,
explained, migrated or redacted, and `digline.wire` never learns its name. What
it holds by §5 is identifiers, so there is nothing in it that redaction would
have had to reach.

*Amended 2026-09-15 ([ADR 0021](0021-the-register.md) §8), narrowly: the
register enters the wire as one named exception. This journal is not that
exception, and stays unknown to the wire, forever.*

### 9. The probe grows a second negative, and a fourth check

`loop.py` proves the wall each cycle: one write that must be refused beside one
that must succeed, because refusal alone proves nothing. A reasoning operator
has **two** absences to prove, not one, and they are different in kind.

| half | what it proves |
|---|---|
| negative — `promote`, by name, at the MCP wire → *unknown tool* | the operator cannot approve its own reference |
| negative — can this identity write `operator.toml`? | whether the operator can edit the policy it exercises |
| positive — the cycle file → written | the identity is not simply refused everything |
| **the fourth check** — the reported `policy_digest` matches the policy on disk | the cycle was ruled by the policy it names |

**Two walls, two scales, and the second one is not the first wearing a new
name.** The MCP wall keeps digline's own trichotomy — **intact**,
**collapsed**, **inconclusive** — because there the wall *is* the absence and
any answer at all is a collapse. The policy wall cannot borrow that vocabulary,
and writing the code is what settled it: measured against a developer's
checkout, or against a repository whose owner holds every key, `operator.toml`
simply **is** writable, so a probe that reported *collapsed* would cry wolf on
every machine it ever ran on and be ignored by the third week — which is the
failure ADR 0016 §6 already named about a canary with no floor.

So it is reported for what it is: **enforced** where the identity cannot write
the policy, **unenforced** where it can, **inconclusive** where the question
could not be put. `unenforced` is not a failure and is not dressed up as one —
it is the latch of the rung taxonomy, stated out loud, and it is the honest
answer for a single maintainer. The wall a deployment actually relies on is the
**push**, protected by branch rules rather than by file modes, which an example
with no protected remote documents and cannot exercise — exactly as it already
documents the push probe.

The existing snapshot-and-restore extends to `operator.toml` for free, so a
wall that let a policy edit through is put back before the comparison reads
anything.

The fourth check is the one that is new in kind. The first three ask whether a
wall stands; this asks whether the **record is honest** — whether the digest in
the cycle describes the file that actually ruled it. Without it, a policy
swapped between the read and the write would produce a cycle that names a policy
nobody applied, which is worse than no digest at all.

**Declared a latch, not a constraint**, and the honesty is inherited rather than
invented. `DESIGN.md`'s three rungs measure a protection against the identity it
constrains: a preference the identity can bypass, a latch it must reconfigure to
cross, a constraint the platform enforces against everyone. Measured against a
single maintainer who owns the repository, path protection on `operator.toml` is
a **latch** — an auditable event rather than a quiet edit — and saying so is the
same move the security page already makes about its declared zeros. It is a
latch for the operator's narrow identity, which is who it exists for.

### 10. The label loop

A decision journal that nobody answers is a log. What makes it history is one
field, added later, by a person:

    wanted: "yes" | "no" | "unsure"      answered_at: <iso>

*Would you have wanted to be woken?* — asked about a hold as much as about an
escalation, because a hold that should have woken somebody is the expensive
error and the one nothing else can see.

This is scout's pattern applied to the operator: the round asks what you
actually did, writes your answer beside the model's, and a later command distils
the pair into cases. The ambiguity is the same one the capture reconnaissance
found and named — *"ignored" can mean wrong, or it can mean timeless* — which is
why the third answer is `unsure` and not an empty string.

What it earns is stated plainly, because it is the point of the whole record:
once the journal holds `(decision, wanted)` pairs, **the operator's own judgment
is a digline suite** — cases that are cycles, an `expected` that is the human's
answer, and an aggregate that says whether the policy still agrees with the
person it was written for. The instrument measures the operator, on exactly the
terms the operator measures everything else.

The distillation command and the committed artifact it writes are **not in this
record**; they arrive with the ledger (§"Not decided here"). What lands here is
the field and the question.

### 11. Where it lives: the example's evolution

All of this is `examples/operator/`. It is not a package, not a front end, and
not `src/`.

The reason is the one this project applies to every surface: a tool is added
when something needs it. The reference assembly is where the loop was designed,
where its four scenarios are tested, and where somebody forks it — and a policy
that could only be exercised by a published component would be a policy nobody
could try on a Tuesday.

The layering note that will apply the day it *is* a component is already
written and already binds: it sits **above `host`**, it may not import
`digline.cli`, and `tests/test_layering.py` holds both. Nothing in this record
moves that line; it only declines to cross it yet.

### 12. Compatibility, and the two gaps this found

**Nothing under `src/` changes.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
migration, no plugin floor, no baseline re-promoted. The example's own
`CYCLE_FORMAT` goes 3 → 4 (§7). A suite that never adopts a policy sees no
behavioural change of any kind, and `examples/operator/` without a `[policy]`
table produces the cycle it produces today plus a decision that says the verdict
decided it.

The reconnaissance found exactly **two** gaps that the core has to close, and
neither is needed for the policy to work. They are recorded here because this is
where they were found, and deferred because they belong to a release rather than
to an example:

1. **`wire.runs_json` carries no aggregates**, while `digline view`'s run list
   does. A reasoner asking "has this check moved three weeks running" must open
   N full run documents to learn what the human-facing table already shows in a
   column. The machine surface being thinner than the document surface is
   backwards, and it is the one place in the product where that is true.
2. **`explain` is absent from the MCP surface.** The scheduled loop reads the
   fact list through the CLI; the interactive operator — same rules, same
   boundary, same absent `promote` — cannot reach it at all, and has to
   re-derive from `compare` what `explain` already types.

Both are additive, both are `OUTPUT_VERSION`-neutral by the rule ADR 0011 §4
already states, and both wait for the release that wants them.

## Consequences

**The escalation policy becomes a thing you can diff.** It was always a
decision; it was never an artifact. From here, changing when somebody is woken
is a pull request with a `because` in it, and a cycle can say which version of
that decision ruled it.

**A quiet week becomes evidence rather than silence.** Every hold is written
with the clause that produced it, so "nothing happened" and "nine things
happened and the policy absorbed them" stop looking identical from outside.

**Somebody will want a clause that wakes them.** §6 says no, and the answer is
not a flag: it is a new deterministic verdict in `loop.py`, where a test can
hold it. The first time this is met will feel like friction and is the design
working — a policy that can only narrow is a policy whose failure mode is a
missed page, which the label loop measures, rather than an invented one, which
nothing would.

**The probe now proves two absences, and one of them is a latch.** A single
maintainer reading §9 will notice that the wall protecting the policy is one
they can cross. That is stated rather than dressed up, and it is why the fourth
check exists: the digest makes a crossing *visible* even where the wall cannot
make it *impossible*.

**The operator becomes measurable by the instrument it operates.** That is the
prize and it is also the risk: a policy calibrated against its own journal can
drift toward whatever the person answering was feeling that month, which is why
`wanted` has three values and why the distillation is a person's command rather
than a cycle's side effect.

## Alternatives considered

**A policy in Python.** The form that can express anything, and rejected in §1:
it is executable by the process that reads it, and the one property this
artifact must have is that the agent cannot re-derive it.

**A policy in Markdown, beside `AGENTS.md`.** Rejected in §1. A policy a program
must obey cannot be prose, and the half that *is* prose already has a home.

**A separate `policy.toml`.** Rejected in §1 for the reason that made it
tempting: it would be a second file with the same rule — *read, never written* —
and therefore a second thing to protect, probe and get wrong. `operator.toml`
already carries that rule in its first line.

**Clauses that may escalate as well as hold.** Rejected in §6. A new reason to
wake somebody is a classification, and a classification belongs where a test can
hold it.

**Putting `policy_digest` in the run document, or in `config_hash`.** Rejected
in §4. The first records a fact about the reader in the thing read; the second
would unpromote every baseline the day a comment changed.

**A committed journal.** Rejected in §8: it dirties the tree on every cycle and
stamps the run it records as `-dirty`. The reviewable artifact is a distillation,
which is the ledger's business.

**Letting the reasoner hold without naming a clause**, with its reasoning in the
open instead. Rejected in §3, and it is the most tempting of these because the
reasoning would often be good. An unclaused hold is an opinion with a paragraph
attached, and it is indistinguishable from the policy having been exercised —
which is precisely the distinction the whole record exists to keep.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The four scenarios still classify as they do today.** `steady`, `wobble`,
`drift` and `structural` produce the same verdict, the same run count and the
same probe outcome with no policy present — the test that proves §2 added a seat
rather than moved the classifier.

**A cycle with no policy escalates exactly as it does today**, with `clause`
null, asserted against the existing expectations.

**Each of the three floors refuses**, one test each, asserted on the sentence: a
clause covering a moved canary, a clause raising `max_reruns`, a clause holding
an exit-2 cycle. The message names the floor and the record.

**A hold is written.** A cycle whose clause holds it produces a journal line and
an alert, and the journal line carries the clause name — the test that would
catch a hold becoming silent.

**The digest is over the parsed document.** Reflowing a comment and reordering
two keys leave `policy_digest` unchanged; changing a threshold in a clause moves
it. Both directions, because only the pair proves §4.

**A clause naming payload is refused at load.** `vars`, an output, a reason and
an artifact path, one case each, asserted on the message — §5 as a load-time
refusal rather than a convention.

**The probe's second negative, both ways.** A writable `operator.toml` reads as
**collapsed** and is restored before the comparison; an unwritable one beside a
successful cycle-file write reads as **intact**. And the fourth check: a policy
swapped between the read and the write reads as collapsed, naming the two
digests.

**The captured alerts are what the dossier writes**, byte for byte, from the
regenerated cycles — the existing gate, extended to carry a decision, and the
one that keeps a committed document from becoming a screenshot.

**`AGENTS.md` and the skill stay in step**, by the gate that already holds them,
over whatever rule this record adds to both.

## Not decided here

**Retention for the journal, and the distilled artifact.**
[ADR 0014](0014-what-may-ride-a-schema-bump.md) §3 deferred a ledger with its
own words — *"a ledger is a decision with its own retention question, its own
boundary question — a name is payload in a way a timestamp is not — and its own
reason to exist"* — and that question arrives there rather than here. Until it
does, append-forever and ignored is enough, and it is enough because the file
never leaves the repository.

**Persisting a comparison's verdict.** The journal records what the *operator*
decided; `compare` still records nothing at all, so a rejection lives only in
whatever commit message mentions it. A `compare` that wrote would be a side
effect, so it is an opt-in or a command of its own — the ledger's question, not
this one's.

**The two core gaps of §12**, which belong to the release that wants them.

**A predicate in a clause.** §1 states the cost and declines to pay it in
advance. The day one is genuinely needed, it is declared vocabulary in this
record's successor — and if what is wanted is an expression language, the honest
answer is that this is the wrong artifact.

**The reasoning operator as a component.** §11 keeps it an example. Whether it
becomes a front end over `host` and `wire`, on its own cadence, is a question
that arrives with the thing that would need it, and it brings its own record.
