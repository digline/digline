# ADR 0030 — The configuration an application reports

- Status: accepted — the text first, the implementation written against it,
  the way [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) and
  [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md) were.
  §4 is the ruling; §5 is what the implementation still has to settle, and
  neither of its two items changes §4. **§6 says what is true while §4 is
  unwritten, and it is unwritten as of 2026-09-23**
- Shipped: unreleased
- Date: 2026-09-23
- Amended: 2026-09-25 — **§4's gate is written; §4's recorded fact is not.**
  `expect_config` exists, and a reported configuration that contradicts it is
  refused, so the perimeter is repaired for a suite that declares one. §5.1 is
  ruled and **deferred** to `SCHEMA_VERSION` 17, with its reason; §5.2 is ruled;
  §7 is new and records what the implementation settled that §5 did not
  anticipate. **§6 is narrowed and is still true for a suite that declares
  nothing** — read it before concluding this record is closed
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born, the verdict travels);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2 (the
  perimeter rule, by type), §8 (the configuration arrives in the answer) and §9
  (what the provider said answered, and its 2026-09-23 amendment, which is what
  opened this)
- Touches: fixed decision 9 (`CLAUDE.md`) — **the question is which side of it
  §8's fields fall on.** Nothing here proposes moving the decision; it proposes
  reading it on a boundary that was added after it was written
- Turns into surface: `docs/declarative.md`, `docs/api.md`, `docs/log.md`,
  `docs/adr/0005-…` §2's table

## Context

**This question predates the pilot and would outlive it.** `HttpTarget` has
reported a configuration since 2026-09-01, and the question below has been true
of every run it has ever produced. What arrived on 2026-09-23 is not the
problem but an application that makes it answerable: a real non-Python service
whose configuration digline reads out of its replies, rather than a shape argued
about in the abstract. `flower` is the instrument, not the reason.

[ADR 0005](0005-the-configuration-of-the-system-under-test.md) §9's amendment of
2026-09-23 refused `resolved_model` over HTTP and gave the reason:

> The rule above separates the two model names by provenance […] the sent
> `model` travels because *"it is written in the suite, and the suite goes
> through a review"* […] Over HTTP neither name is written in a suite.

That amendment closed one field and declared, without repairing, that the same
premise has fallen for a field which is **already open, already mandatory, and
already travelling**.

### The gap is live, and this is the measurement

Not an argument from the shape of the code. Run against 0.19.0 at `030f701`:

```
declared_config kept: {'provider': 'flower', 'model': 'kayak-skills-prod-eu-west-v3',
                       'base_url': 'flower.internal.acme'}
after redact -> values  : {'provider': 'flower', 'model': 'kayak-skills-prod-eu-west-v3'}
after redact -> withheld: ['base_url']
codename in the projected document: True
gateway host in the document      : False
```

`base_url` is withheld for describing the client's perimeter. The codename
beside it, which describes a project, an environment and a region, is not. That
is word for word the failure the 2026-09-10 correction found — *"both fields
arrive in the same reply from that same server"* — on the field that correction
did not look at.

A second measurement, because it is what §4 has to answer. `declared_config`
**deletes** `base_url` when its value has no parsable host, silently:

```
malformed base_url kept: {'provider': 'flower', 'model': 'gemini-2.5-flash'}
                         -> base_url present? False
```

So the one field that is withheld can be removed from the record by the party
being measured, without being told. §9's amendment refused to build a boundary
on that fact. This record has to say what to build one on instead.

## Decision

### 1. The question, stated so it can be answered once

**Of the fields [ADR 0005](0005-the-configuration-of-the-system-under-test.md)
§8 admits, which are measurements of the system and which are the end company's
perimeter — given that over HTTP the measured party writes all of them?**

§2 already fixed the test: *"§2's test is what the value describes."* What §2
could not have anticipated is a boundary where provenance gives the same answer
for every field, so the test has to be applied without the help provenance used
to give.

### 2. The fields, sorted by what the value can be

`CONTRACT_FIELDS` holds eleven keys. Sorting them by what a value can *carry*,
rather than by what it is called, partitions them cleanly:

| | fields | what a value can carry |
|---|---|---|
| **numbers and closed enums** | `max_tokens`, `temperature`, `top_p`, `top_k`, `seed`, `response_format`, `json_mode` | a quantity or one of a known set. A number cannot be a codename |
| **free-form strings the app writes** | `provider`, `model`, `region` | anything at all, including a project, an environment and a customer |
| **already withheld** | `base_url` | ADR 0005 §2 |

The first row is safe and needs no ruling: `temperature = 0.2` describes the
system and can describe nothing else. **The second row is the whole question.**
`declared_config` requires `provider` and `model` as non-empty strings and
constrains them no further, and `region` is checked for nothing at all.

### 3. Why "withhold them like `base_url`" is the obvious answer and the wrong one

It is the consistent reading — a free-form string an unreviewed party wrote is
in `base_url`'s trust category — and it is one line in a frozenset. It also
takes out most of what a run over HTTP is *for*:

- `SystemConfig.redacted()` keeps `identities` on the stated ground that *"a
  provider and a model are measurements and travel in clear, so the instruments
  a run used are named in a redacted document too."* That sentence was written
  about a plugin and would now be false of one target in two.
- `digline log`'s rows are built on `provider` and `model`. An HTTP run would
  become a span of a system with no name, which is a reading of nothing.
- The headline's *"the configuration is the same as the reference"* would answer
  `unknown` for every HTTP run, permanently — the un-actionable `unknown` that
  ADR 0003 §5 spends its length avoiding.

It also does not make the value any more trustworthy. It makes it invisible,
which is a different thing, and it is the second time that trade has come up
this month: §9's amendment refused the same move for `resolved_model` on the
ground that a withheld field over HTTP is *recorded nowhere and rendered
nowhere*.

### 4. The ruling: restore the review, do not withhold the value

**The suite declares the system it expects; the application reports; digline
refuses a mismatch.** One new key in `[target]`, and the partition §9 lost is
back:

```toml
[target]
type = "http"
url = "http://localhost:8080/answer"
output_path = "data.answer"
config_path = "config"
expect_config = { provider = "gemini", model = "gemini-2.5-flash" }
```

- **`model` travels because it is reviewed again.** The value in the document is
  one a human wrote in a file that goes through a pull request, and the
  application's job is reduced to *agreeing with it*. §2's provenance test is
  satisfied rather than abandoned, which is why this is a repair and not a
  workaround.
- **A mismatch is a refusal, not a withholding.** An application that reports a
  model the suite did not declare is refused at the boundary, in
  `declared_config`'s existing voice and beside its existing refusals. That is
  §8's own idiom — *"the contract is enforced here, not followed"* — and it
  answers the malformed-`base_url` disarm at the same time: the check is on a
  value the suite wrote, so there is nothing for the measured party to remove.
- **It is what §8 already says the reader is owed.** *"One run measures one
  system"* is §8's rule; today it is enforced across the run's own answers and
  against nothing a human declared.
- **And it unblocks §9 rather than closing it.** Once the sent names are
  reviewed, the provenance partition exists on HTTP, and `resolved_model`
  becomes a field this repository could admit on the argument §9 actually makes
  — instead of one refused because the argument is unavailable.

**Undeclared is not silently permissive, and it is recorded rather than
refused.** A suite that declares no `expect_config` is the case every existing
suite is in, so an unconditional refusal would break all of them. The shape is
the one ADR 0005 §1 already uses for an unset parameter: absence is a fact, and
it is recorded as one. A run whose suite declared nothing records that its
configuration is **unreviewed**, and that is what crosses — the reader is told
the names came from the measured party, rather than being left to assume a
review that did not happen.

Refusing instead was considered and is not the ruling: it is a cleaner perimeter
bought by breaking every HTTP suite in existence, for a weakness that is legible
once it is named. A fact a reader can see is worth more than a refusal that
stops the reader being there at all.

### 5. What the implementation still has to settle

Neither item changes §4. Both are about how its ruling is carried, and both are
the reason this record is text before code.

1. **Where `unreviewed` lands in the document.** It is a fact about the record,
   so the candidates are a `SystemConfig` field or a `withheld`-style marker —
   and a `SystemConfig` field is a `SCHEMA_VERSION` bump with a migration and
   the ritual around it, for a fact nothing reads yet. A marker on the existing
   shape is the cheaper reading and has to be shown to be an honest one. This
   is the cost the §9 amendment declined to pay inside an enablement release,
   and it is still the cost here.

   *Ruled 2026-09-25: a new `SystemConfig` field, owed at `SCHEMA_VERSION` 17,
   and not written here.* **The cheaper reading was tried against the honesty
   test this item set for it, and it fails — the reason matters more than the
   ruling, because a deferral whose reason is missing gets reopened by somebody
   who assumes nobody tried.** `SystemConfig` has exactly three fields, and each
   one already means something that a review flag is not:

   - `values` is *"the parameters that decided how the system answered"*. A
     review is not a parameter and it decided nothing about the answer. A key
     there would also have to get past `declared_config`'s closed key table —
     so the marker would be smuggled through the very contract §4 exists to
     strengthen, and it would then be rendered as a configuration delta,
     `unreviewed: true → false`, in a table of temperatures and token caps.
   - `withheld` means *this run kept a value back at a boundary*. That is a
     claim about a value that existed and was removed. Nothing was withheld
     from an unreviewed configuration — it was never checked — and ADR 0005 §2
     attaches a specific reading to that set: a withheld field compares as
     `unknown` rather than `same`, so the marker would silently turn every
     unreviewed run's comparison into an absence of a finding.
   - `identities` is `provider/model` labels, sorted and distinct, compared for
     equality against real instruments. A flag is not a label.

   So all three are dishonest, each in a different way, and none of them by a
   little. **The honest shape is a fourth field**, which means `SCHEMA_VERSION`
   16 → 17, a migration step keyed on 16 in `store/migrate.py`, and both halves
   of the ritual around it.

   **Deferred, and not for its cost.** The ritual is affordable; the window is
   not. A diagnostic capture for the index divergence is owed before the next
   tag (`RELEASING.md`, under v0.20.1), and a schema bump is the other ritual of
   that same window. **Two rituals competing for one release window is how one
   of them gets done badly**, and the one that would be done badly is the one
   nobody is watching. So the field waits for a window of its own, and §6 stays
   true until it gets one.
2. **`region`.** `eu-west-1` is a public cloud name; a region in a customer's
   own deployment is whatever they called it. §2 puts it in the free-form row
   by type and §4's declaration covers it at no extra cost if it is included —
   the open part is only whether it is mandatory to declare, and nobody has
   asked for it either way.

   *Ruled 2026-09-25: not mandatory, and it needs no rule of its own.* §7 makes
   `expect_config` a declaration of **keys** rather than of a whole
   configuration: every key a suite writes is checked, and every key it does not
   write is not. `region` is therefore reviewed by a suite that names it and
   unreviewed by one that does not — the same answer §4 gives `provider` and
   `model`, reached without a clause of its own. Mandatory was refused for the
   reason the item already gave, and for one more: a mandatory key is a suite
   that cannot adopt §4 without declaring a field it may not know, which prices
   the repair out of exactly the deployments that need it.

### 6. Accepted is not implemented, and the gap is open while it is not

**Stated here because a ruling nobody has written reads, three months on, as a
thing that was done.** §4 is accepted. Nothing in it is implemented. So for as
long as that is true:

- an application's `provider` and `model` are whatever it reports, checked
  against nothing a human declared;
- `model` **crosses a boundary in clear**, today, on every HTTP run — the
  measurement in §Context is not a prediction;
- `resolved_model` is closed (ADR 0005 §9), so the field this record would
  eventually reopen stays shut meanwhile, which is the conservative half working.

#### Narrowed 2026-09-25, and still open where it was

*§4's gate is written. This section is not deleted, because deleting it would
answer a question it was written to keep open. What follows is what remains
true, which is less than it was and further from nothing than a reader of the
amendment line will expect.*

**For a suite that declares `expect_config`, the gap above is closed.** The
`model` in its document is a value a human wrote in a file that went through a
pull request; the application's part is reduced to agreeing with it, and
disagreement is refused. §4's repair is not partial there, and the three
sentences above are false of such a run.

**For a suite that declares nothing, all three are still true, and that is
every existing HTTP suite on the day this shipped.** The gate is opt-in by
construction — §4 ruled that undeclared must not be refused, or every existing
suite would break — so a suite that adopts nothing changes in no way, including
in the way it is exposed. And one sentence is now true that was not:

- **a reader of the document cannot tell the two populations apart.** This is
  precisely the half §4 ruled and §5.1 deferred: a run whose suite declared
  nothing is supposed to record that its configuration is `unreviewed`, and it
  does not. So a document carrying a reviewed `model` and a document carrying an
  unreviewed one are byte-identical in the part that matters, and **"reviewed"
  is a property of the suite that no reader of the run can see.** World 2 is
  told nothing and is therefore left doing exactly what §4 says it must not do:
  assuming a review that may not have happened.

That last sentence is awkward to write, and the awkwardness is the shape of the
deferral rather than a defect in the prose: this release repaired the perimeter
for those who opt in and left the *transparency* owed, which is the half a
reader of a document depends on. Whoever reaches this section next must not read
§4's implementation as closing it. **If §5.1 is still open and this section is
still here, what is missing is the fact in the document, not the gate** — and
the run to distrust is the one whose suite you have not read.

**And it applies to the pilot that made the question answerable.** `flower`
reaches digline through an HTTP target, so the first real non-Python application
digline measures is also the first to report a configuration nobody reviewed. The
release that gives it `tools_path`, `tool_calls_path` and `usage_path` does
**not** close this, and the declarative documentation says so where those paths
are described rather than leaving a reader to find this record.

The honest summary, for whoever reads this next: the premise fell on
2026-09-23, the consequence was named the same day, and the code is still owed.
If this section is still here and §5 is still open, nothing has been done.

### 7. What the implementation settled, 2026-09-25

*Added with the code. §5 named two open items and these are not among them: they
are questions §4's ruling could not have known it was asking, answered where
the answer is now load-bearing.*

#### It declares keys, not a configuration

**`expect_config` is a partial declaration: every key it names is checked, every
key it does not name is not.** The alternative — a declaration that must match
the reported configuration exhaustively — was refused, and not on convenience.
§2 already sorted the fields, and the row that needs review is the free-form
strings an application writes. A suite forced to declare `temperature` and
`max_tokens` to review `model` would be declaring, in the suite, numbers chosen
on the other side of HTTP, and the first divergence would teach it to stop
declaring anything. Partial keeps the cost of the repair proportional to the
field that needs it.

**A declared key the application never reports is a mismatch, not a pass.**
Absent is not agreement. §8 reads a missing key as *not sent, the provider's own
default applied* — which is an honest reading of an application's silence and
would be a dishonest one here, because the suite asked a question and got none
of an answer.

#### It is recorded beside `config_hash`, never inside it

The first instinct is the other one: it is the suite's own declaration, and what
`config_hash` fingerprints is the suite. It is still wrong, for the reason ADR
0005 §3 exists.

- **`config_hash` covers rulers, not measurements.** Its members are an
  assertion's identity, its threshold and tolerance, `samples`, `min_agreement`
  and the declared price — the last one because *"the price is the ruler, not
  the thing measured"*: a `CostBudget` judges dollars, and the same tokens pass
  or fail as the rate moves. `expect_config` is no ruler. When it agrees it
  contributes nothing to any score; when it disagrees there is no comparable run
  to speak of. **The pair of runs whose verdicts differ because this declaration
  moved does not exist**, and that pair is the only thing `config_hash` protects
  against.
- **Inside the hash, it would re-break the model rotation from the suite's
  side.** ADR 0005 §9's amendment states its own placement in as many words —
  *"recorded beside `config_hash` and never inside it, so two runs across a
  model rotation stay comparable and promotable"*. A declaration in the hash
  makes rotating the declared model move it, which replaces the named delta
  `model gemini-2.5-flash → gemini-2.5-pro` with the opaque hash difference §3
  says this ADR exists to replace. Keeping the reported value out and letting
  the declared one in would be the same mistake wearing the suite's clothes.
- **And it would charge a re-promotion for adopting the fix.** Adding the key to
  an existing suite would move its hash, and `promote_baseline` refuses a run
  produced under another one. ADR 0005 §7 is titled *"keys added, nothing
  re-promoted"*, and this record's own Consequences promise that every existing
  HTTP suite keeps running. **A gate whose adoption costs a re-baseline is a gate
  teams decline**, and a declined gate protects nobody.

#### The refusal names both values and the move that resolves it

It lands in `declared_config`'s voice, where §4 put it, and takes
`BaselineMovedError`'s shape: what was not done, what the suite declared, what
the application reported, and what to do next. **Both values, because either
side may be the one that moved** — the application may have rotated, or the
declaration may be stale — and a message that says only that something is wrong
sends a reader to guess which. It stays a `ValueError`, like `declared_config`'s
other four refusals: a new exception type would have to be registered as a
refusal, and this is the same refusal the contract already makes, one field
further on.

#### A mismatch errors its cases, and cannot be caught any earlier

*Not decided here* said this should get §9's rotation answer for §9's reason,
once a run had met it. It does, and the mechanism leaves no second option:
`preflight()` sends a `HEAD` and *"does not check behaviour"*, and the driver's
pre-run configuration read — the one ADR 0005 §8 added so that *"a malformed one
failed before the suite was paid for"* — is empty for an `HttpTarget`, because
an endpoint learns its configuration by answering. **There is nothing to check
until a case has been paid for.** So the refusal lands beside the rotation
refusal, in `_record`, and behaves as it does: the case errors, the run is still
written, and the reason is legible on it.

The consequence, stated rather than left to be discovered: a suite whose
application is on the wrong model **errors every case**, with the same sentence
on each, and pays for the calls. That is worse than a refusal before the first
case and far better than a green run measuring a system nobody declared — and
the earlier refusal is unavailable for the reason above, not unwanted.

#### What this does to ADR 0005 §9, and what it does not

**§9 refuses `resolved_model` over HTTP on three grounds, and §4 reaches one.**
The provenance partition is restored for the fields a suite declares: the sent
`model` is reviewed again, so the rule that separates a sent name from an
observed one has something to separate. §4's own bullet — *"it unblocks §9
rather than closing it"* — is therefore true, and it is one third of the
argument. **The other two refusals are untouched:**

- a withheld `resolved_model` over HTTP would still be *"recorded in the run
  file and rendered nowhere at all"*, because `sighting()` and
  `config_deltas()` redact before they read. §9 refuses that on its own merits
  and §4 does not touch it;
- the withholding would still turn on `base_url`, a key the measured party
  controls, and `declared_config` still deletes a `base_url` whose value has no
  parsable host, silently. §4 does not cover `base_url`, and this record's
  Alternatives say so.

So **§4 does not reopen §9**, and anybody reading it as having done so is acting
on a third of an argument. What it does is make the route visible: a suite that
declared `base_url` *inside* `expect_config` would close the disarm, because an
endpoint that cannot be reduced would then contradict a reviewed value instead
of vanishing from the record. That is an amendment to §9 on §9's own argument.
**It is not ruled here, it was not tried here, and it is not a consequence of
what was.**

## Consequences

- One reading of fixed decision 9 covers both target kinds, instead of a rule
  whose justification silently changes meaning between them.
- An HTTP suite gains a preflight it did not have: the system it believes it is
  measuring, checked against the system that answered.
- Every existing HTTP run's document is unchanged, and every existing HTTP suite
  keeps running — under §4's recorded `unreviewed`, not under a refusal.
  *Corrected 2026-09-25: the first half held and the second did not. An existing
  suite does keep running and its document is unchanged — unchanged to the point
  that it records no `unreviewed` either, because §5.1 deferred the field. It
  runs under **nothing**, which is the status quo and not the ruling. §6.*
- `resolved_model` over HTTP stops being closed *on principle* and becomes
  closed *pending this*, which is a different and smaller thing.

## Alternatives considered

**Declare and do not fix**, as [ADR 0029](0029-the-artifact-that-must-not-drift.md)
§9b does for a stored document. The precedent is real and the reasoning
transfers only halfway: §9b is about a party who can *forge* a document, against
which no refusal helps, and it says so. Here the value is not forged, it is
merely unreviewed — and a review is exactly the thing that can be added. A
declaration is the right answer when nothing can be done; something can be done.

**Withhold `provider` and `model` over HTTP.** §3.

**Derive `base_url` from `HttpTarget.url` so every HTTP run is a named
endpoint.** Refused in ADR 0005 §9's amendment, on the ground that it settles
the question by mechanism and renders the field nowhere. It remains the right
*mechanism* if a withholding is ever chosen, and it would close the
malformed-`base_url` disarm as a side effect — which is worth keeping in view
even under §4, since §4 does not touch `base_url`.

**A closed vocabulary for `provider`.** Attractive for one field and useless for
the other: the set of providers is nearly enumerable and the set of model names
is not, so it would solve the easier half and leave the harder one exactly as it
is.

## Test plan

- The measurement in §Context, as a test rather than a probe: an application's
  reported `model` reaching a redacted document is the thing that must stop
  being true, so it is asserted in the direction that fails today.
- The malformed-`base_url` drop, asserted as the disarm it is — a config whose
  `base_url` cannot be reduced is read as first-party, and a test that says so
  is what keeps §4's independence from it honest.
- Both halves of the mismatch, beside each other: a declared configuration the
  application agrees with passes, and one it contradicts is refused naming both
  values. A gate that refuses everything passes the second test alone.
- A suite that declares nothing records `unreviewed` and still runs — the
  compatibility half, which is the one a later reading of this record will want
  to have been pinned.

*Amended 2026-09-25, with what was actually pinned.* The first item is asserted
of a **declaring** suite: the reported `model` that reaches a redacted document
is now one the suite wrote, so the test asserts agreement rather than the
absence of a crossing — an undeclared suite still crosses in clear, and a test
asserting otherwise would be asserting §5.1's deferred half. The last item is
pinned in its compatibility half only: a suite that declares nothing **still
runs**, unchanged, and records **no** `unreviewed`, because there is no field to
record it in. That half of the item is owed with the schema bump, and a test
claiming it today would be the vacuous kind — passing because it asks nothing.

## Not decided here

**The judge.** ADR 0005 §8 already rules that an application which judges its
own output is not a judge digline can record, and nothing here changes it.

**Whether a mismatch fails the run or errors its cases.** It is the shape of
§9's rotation question and should get the same answer for the same reason, once
there is a run that has met it. *Ruled 2026-09-25 — §7. It got the same answer,
and the mechanism left no other: there is nothing to check until an answer has
arrived, so there is no earlier place to refuse from.*

**Anything about `resolved_model`.** It is closed by ADR 0005 §9 and this record
does not reopen it. What it does is remove the reason it was closed: once §4 is
written, the sent names are reviewed and the provenance partition exists on
HTTP. Reopening it is then a separate amendment to §9, on §9's own argument,
and not a consequence anybody should read out of this record.
