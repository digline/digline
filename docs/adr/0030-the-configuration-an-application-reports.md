# ADR 0030 — The configuration an application reports

- Status: accepted — the text first, the implementation written against it,
  the way [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) and
  [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md) were.
  §4 is the ruling; §5 is what the implementation still has to settle, and
  neither of its two items changes §4
- Date: 2026-09-23
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the
  payload stays where it is born, the verdict travels);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2 (the
  perimeter rule, by type), §8 (the configuration arrives in the answer) and §9
  (what the provider said answered, and its 2026-09-23 amendment, which is what
  opened this)
- Touches: fixed decision 9 (`CLAUDE.md`) — **the question is which side of it
  §8's fields fall on.** Nothing here proposes moving the decision; it proposes
  reading it on a boundary that was added after it was written
- Turns into surface: `docs/declarative.md`, `docs/log.md`,
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
2. **`region`.** `eu-west-1` is a public cloud name; a region in a customer's
   own deployment is whatever they called it. §2 puts it in the free-form row
   by type and §4's declaration covers it at no extra cost if it is included —
   the open part is only whether it is mandatory to declare, and nobody has
   asked for it either way.

## Consequences

- One reading of fixed decision 9 covers both target kinds, instead of a rule
  whose justification silently changes meaning between them.
- An HTTP suite gains a preflight it did not have: the system it believes it is
  measuring, checked against the system that answered.
- Every existing HTTP run's document is unchanged, and every existing HTTP suite
  keeps running — under §4's recorded `unreviewed`, not under a refusal.
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

## Not decided here

**The judge.** ADR 0005 §8 already rules that an application which judges its
own output is not a judge digline can record, and nothing here changes it.

**Whether a mismatch fails the run or errors its cases.** It is the shape of
§9's rotation question and should get the same answer for the same reason, once
there is a run that has met it.

**Anything about `resolved_model`.** It is closed by ADR 0005 §9 and this record
does not reopen it. What it does is remove the reason it was closed: once §4 is
written, the sent names are reviewed and the provenance partition exists on
HTTP. Reopening it is then a separate amendment to §9, on §9's own argument,
and not a consequence anybody should read out of this record.
