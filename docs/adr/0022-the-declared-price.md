# ADR 0022 — The declared price

- Status: proposed — the text first, checkpointed before any code
- Date: 2026-09-15
- Assumes: [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4
  (a digest is a verifier);
  [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) (a plugin owns its
  provider's price list);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2 (a perimeter
  field is withheld at a boundary), §3 (the system's configuration is beside the
  hash, not inside it), §7 (keys added, nothing re-promoted), §9 (a named
  endpoint);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) (`samples` entered
  the hash because it changes how confidently every check is judged);
  [ADR 0007](0007-the-declarative-suite-format.md) §5 (only declarative
  parameters, no objects), §9 (the two forms are equal citizens, and hash
  equal);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (what the hash is the
  identity of)
- Amends: [ADR 0007](0007-the-declarative-suite-format.md) §5 — one dated
  sentence: pricing as an object stays out of a data suite, and pricing as
  declared numbers comes in (§1);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 — the hash has held only
  assertions, thresholds, tolerances, `samples`, `min_agreement` and the
  aggregates; a declared price joins them, for the reason in §3;
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §2 — the
  declared rates join the fields withheld at a named endpoint (§5)
- Touches: fixed decision 3 is upheld — an unpriced model still fails, and a
  declared zero is a declaration, never a default; decision 4 — cost is a
  budget, and this is what makes the budget measure the endpoint's cost rather
  than somebody else's list; decision 9 — a negotiated rate is withheld where
  `base_url` is, and the record says plainly that the withholding is a latch and
  not a constraint (§6)
- Requires: no `SCHEMA_VERSION` (the rates are `target_config` keys, ADR 0005
  §7) and no `OUTPUT_VERSION`. `config_hash` changes **only** for a suite that
  declares a price; every other suite hashes byte-identically
- Number: 0022

## Context

The first external run of the TOML quickstart pointed `type = "provider"` at
an OpenAI-compatible aggregator — one endpoint, five hundred models from several
vendors, its own prices. Everything the record promises held: stable ids, full
usage including cached tokens, every run priced, a comparison that said the
configuration had not moved.

The pricing was the one thing that was not true. The OpenAI plugin priced every
call from **OpenAI's** list, because that is the only list it has, and a
`CostBudget` over those runs measured what the calls would have cost at a
provider the requests never reached. The same is true of OpenRouter, of a
corporate gateway with a negotiated rate, and of a self-hosted vLLM where the
honest per-token price is zero.

A Python suite has always had the remedy: `pricing=` on the target, one
argument, reviewed with the suite. A data suite cannot say it. The loader
refuses `pricing` by name (ADR 0007 §5: *"Not `client`, not `pricing`: those are
objects"*), so the one budget fixed decision 4 makes non-negotiable is
unmeasurable on exactly the endpoints the declarative form was written to reach.

That refusal was right about the object and wrong about the fact. A `Pricing` is
an object. **Four per-million rates are declared numbers** — no logic, no
callable, nothing an engine interprets — which is the test ADR 0007 applies to
everything else in a data suite. This record declares them.

## Decision

### 1. The shape: four numbers under the target

```toml
[target]
type = "provider"
provider = "openai/gpt-5.6-sol"
base_url = "https://api.aggregator.example/v1"

  [target.pricing]
  input_per_mtok = 1.10
  output_per_mtok = 4.40
  cache_read_per_mtok = 0.11     # optional
  cache_write_per_mtok = 1.375   # optional
```

- **`ModelPrice`'s own fields**, in its own unit: USD per million tokens. The
  loader builds a `ModelPrice` and nothing else, so the format dispatches and
  does not interpret (ADR 0007 §9).
- **One price, not a map.** A provider target names exactly one model through
  its coordinate, so the table prices that model. A second model is a second
  suite, as a second model always was.
- **An absent cache rate is not zero.** It means the endpoint has no cached
  tier, exactly as `ModelPrice` already reads `None`: a call that reports cached
  tokens against a price with no cached rate still refuses rather than pricing
  them at nothing.
- **Free is declared, never defaulted.** A self-hosted model is four zeros,
  written down — the TOML twin of `free()`, and the same decision 3 argument: a
  zero nobody wrote is a budget that cannot fail.
- **`type = "provider"` only.** An `http` target reads its cost out of the
  response through `cost_path`; there is nothing for a price to multiply, and a
  `[target.pricing]` beside `type = "http"` is refused by name.
- **`client` stays refused**, and so does `pricing = <anything but a table>`.

The loader's refusal of `pricing` as an injected object
(`host/toml_suite.py`) becomes this branch. ADR 0007 §5 gains its dated
sentence: *pricing as an object stays out of a data suite; pricing as declared
per-million rates comes in, because rates are data.*

### 2. Declared wins, and the document says so

A declared price **replaces** the plugin's entry for that model —
`Pricing.override(model, price)`, which already exists and already means *a
price the user corrects*. Where the plugin's list has no entry (most of an
aggregator's catalogue) the declared price is the only one there is, and there
is nothing to contradict.

**The two forms declare the same way.** The Python form's `pricing=` takes an
object, which is how it has always taken it, and that object now records
whether it is a declaration: `Pricing.declared` is `True` on the result of
`override()`, and `False` on the tables plugins ship. The TOML loader builds its
`Pricing` through `override()`, so a data suite and its Python twin carry equal
declared prices — the property §4's hash depends on.

**A finding about `free()`, and the interim it costs.** `free()` is not in
`digline.targets`: the OpenAI and Bedrock plugins each define their own, and
each builds a `Pricing` directly, so neither result is marked declared. The
declared zero therefore gets a constructor in `digline.targets.pricing` —
`free(*models)`, marked declared — and each plugin's `free()` delegates to it in
that plugin's next release, with its floor raised to the digline that carries
it (ADR 0017 §11's shape). Until those releases a Python suite that calls a
plugin's `free()` hashes exactly as it does today, while its data-suite twin with
four declared zeros hashes with the digest: ADR 0007 §9's hash equality is
broken for that one pair, for that window, and the release notes say so rather
than leaving a user to find two hashes for one suite.

**What the run records.** `target_config` gains, beside the model it prices:

    pricing              "declared"
    input_per_mtok       1.10
    output_per_mtok      4.40
    cache_read_per_mtok  0.11      # only where declared
    cache_write_per_mtok 1.375     # only where declared

Flat scalars, which is the shape `SystemConfig` requires, so a comparison names
the delta the way it names every other one: *input_per_mtok 2.50 → 1.10*. A run
priced by the plugin's own list records none of these keys — the list is the
plugin's, not the suite's, and ADR 0005 §1 records what the suite sent and
declared, not the defaults it inherited. These are ADR 0005 §7's added keys: no
schema bump, and no baseline re-promoted by their arrival.

### 3. A price is a ruler, not a temperature

ADR 0005 §3 keeps the configuration of the system under test **beside** the
hash: two runs at two temperatures, or against two models, stay comparable and
promotable, because the rules that judge them did not move. A declared price
looks like one more configuration value, and a model change moves a
`CostBudget`'s verdict just as a price change does. So the argument for putting
the price **inside** the hash has to be made, not assumed.

It is this. **Tokens are measured; dollars are computed.** A run records how
many tokens a call used — that is a measurement of the system, and a different
model or temperature changes it, which is what "configuration of the system"
means. A `CostBudget` does not judge tokens. It judges dollars, and dollars are
tokens multiplied by a rate that nobody measured: somebody **declared** it. The
rate is not a property of the system that answered. It is the scale the budget
reads the answer on.

Changing the temperature changes what is measured. Changing the declared price
changes the **ruler** — the same tokens now read as a different cost, against
the same threshold, so a run that passed yesterday can fail today with nothing
about the system having moved. That is exactly what a raised threshold does, and
exactly why thresholds are in the hash (ADR 0014 §1): a baseline recorded under
one ruler cannot be promoted as the reference for a suite that now reads cost on
another. `samples` entered the hash on the same argument (ADR 0006): it changes
how every check is judged, not what the system did.

The consequence, stated rather than discovered: a suite that declares a price,
or changes one, **changes its `config_hash`** — its baseline is comparable and
no longer promotable, and the comparison says *the rules changed*, which is the
true sentence. A suite that declares nothing hashes exactly as it did.

What does **not** enter the hash is a plugin's shipped list moving between
plugin releases. That price is not the suite's declaration, and a plugin release
that unpromoted every baseline in the world would be the accretion ADR 0014 was
written to prevent. The cost of that line is real and older than this record:
a plugin's list price changing still moves a `CostBudget` verdict without saying
the rules changed. Declaring the price is the remedy for a suite that cares.

### 4. The mechanism: a digest of the declared price, fed by both forms

    pricing_digest = sha256(canonical({model, input, output,
                                       cache_read, cache_write}))[:16]
    Suite.config_hash(*, pricing: str = "")

- **An empty digest leaves the hash byte-identical.** The digest joins the
  hash's sorted entries only when a price was declared, so no existing suite,
  run, key or baseline moves.
- **The host computes it from the target.** `Loaded` already carries what the
  forms owe — a data suite's target, built during the load, and a Python
  suite's module, whose `target` was built on import — so reading the declared
  price needs no new construction, and plugin clients are created lazily, so no
  credential is needed to read a price.
- **Every call site that computes the hash takes it**, and the list is closed:
  `execute()`, which stamps `Run.config_hash`; `measure()`, which writes the
  journal header; `promote`, from the CLI and from `view`; `rejudge`, whose
  replay carries the current suite's hash; and the MCP `run` tool. `compare`
  reads the hashes stored in the two documents and computes none.
- **Both forms feed it**, and ADR 0007 §9's property is extended to it: a data
  suite with `[target.pricing]` and its Python twin with
  `pricing=OPENAI_PRICING.override(model, ModelPrice(...))` produce the same
  digest and the same `config_hash`.

### 5. A correction in its own right: `promote` could sign the wrong target

A Python suite may hold several targets, and `run --target other` chooses one.
`promote` has never had `--target`. Until now that was harmless by accident —
the hash did not depend on the target, so a baseline promoted from a run made
against `other` recorded the same `config_hash` as one made against the default
— and it hid a real defect: **a multi-target suite could sign a run made against
one system as the reference for a suite whose default is another**, and nothing
in the promotion said which target the signature was for.

The declared price makes the defect visible, because the hash now depends on the
target's declaration: `promote` without `--target` reads the default target's
price and refuses a run made with a differently priced one as a configuration
mismatch. The fix is not a workaround for this record. `promote` and `view` gain
`--target`, with exactly `run`'s meaning, so the target a signature is for is
named at the moment of signing. A data suite has exactly one target and needs
none.

`rejudge` gains it too, found while writing the code: a replay's target is a
wrapper around stored answers and declares no price, so the hash a re-judged run
carries has to be computed off the target the suite would run today — named the
same way, for the same reason.

### 6. Withheld at a named endpoint, and the withholding is a latch

A negotiated rate is the customer's commercial fact. It is in the class of
`base_url`: where the suite names an endpoint, the declared rates join
`ENDPOINT_PERIMETER_FIELDS` and are withheld in every redacted document, every
`--json`, every MCP response and `log`, exactly as `resolved_model` is there.
At a first-party endpoint the price is a list price the suite chose to pin, and
it travels in clear like the model id.

**The hash is computed from the value; only its printing is withheld.** And that
has a consequence the record states rather than hides. `config_hash` travels in
clear everywhere — in every run key, in the register, in `log`, in `compare
--json`, in the MCP — and every other input to it crosses the same boundary on
its own merit: the assertion identities, the thresholds and tolerances,
`samples`, `min_agreement`. So a reader holding a redacted document holds a hash
in which the declared price is the one unknown, over a space small enough to
search: a rate to the cent, per million tokens. The value never prints; the hash
narrows it.

In the words `DESIGN.md` uses for walls:

> **Withholding a declared rate is a latch, not a constraint** — the value never
> prints, but the hash narrows it; a rate you cannot afford to narrow belongs in
> a Python suite, or at an unnamed endpoint.

A **Python suite** can price a target without declaring the price —
`Pricing(per_model={...})` built directly carries no declaration — and then no
digest enters the hash, at the stated cost that a change of that rate no longer
reads as *the rules changed*. At an **unnamed endpoint** the rate is a list price
and travels in clear, so there is nothing to narrow.

**Why not a keyed digest.** A salt committed per tenant would close the
enumeration, and it was weighed and refused. A negotiated rate is a commercial
fact, not a credential, and the salt's costs are the kind this project has
learned to count: a new committed file that stamps runs `-dirty` until it is
committed, and two clones that each generate one computing different hashes for
the same suite until one salt wins a merge. That is a new way for a baseline to
become unpromotable for a reason unrelated to the suite, bought to protect a
value that is not a secret — so the protection is declared for what it is
instead. A key taken from the repository's root commit, which needs no file, was
refused too: a shallow clone reports its shallow boundary as the root, so CI and
a laptop would disagree about it.

### 7. What a reader sees

At a first-party endpoint, a changed declared price is a named delta —
*input_per_mtok 2.50 → 1.10* — and a changed hash: *the suite changed since the
reference, so these numbers compare different rules*.

At a named endpoint the delta reads `unknown` and withheld, and the hash still
moved, so the reader is told **that** the rules changed without being told the
rate. The 0.13.0 sentence for a withheld identity does not fire on a price: a
withheld price is not an identity, and the rules-changed sentence already says
what is true.

## Consequences

**`CostBudget` measures the endpoint's cost on the endpoints the declarative
form exists for.** An aggregator, a gateway and a self-hosted server can each be
budgeted in the currency they actually charge.

**A declared price is part of the suite's identity.** Declaring one, or
correcting one, unpromotes the baseline — and that is the design: the budget's
ruler moved.

**A withheld rate is narrowed by the hash beside it.** Declared as a latch in
§6, with the two places a rate that cannot afford it belongs.

**A multi-target suite names the target it signs.** `promote --target` closes a
gap older than this record.

**A plugin's own list still moves verdicts silently between plugin releases.**
Unchanged by this record, stated here, and now avoidable by declaring.

## Alternatives considered

**The price beside the hash, as ADR 0005 §3 keeps configuration.** Rejected in
§3: a rate is the scale a budget reads on, not a property of the system, and a
baseline must not be promotable across a change of scale.

**Moving the price into `Suite`.** Rejected: it is the target's model's price,
and a suite holding it would describe a target it does not construct.

**A price map in the data suite.** Rejected in §1: a provider target prices one
model.

**A digest keyed with a committed per-tenant salt.** Rejected in §6: it closes
the enumeration, and costs a new way to stamp runs `-dirty` and to make two
clones disagree about a hash, to protect a commercial fact rather than a
credential. The weakness is declared as a latch instead.

**A key from the repository's root commit.** Rejected in §6: shallow clones
disagree about it.

**Leaving `promote` without `--target`.** Rejected in §5: a multi-target suite
could sign a run of one system as the reference for another.

**Putting the plugin's list price in the hash too.** Rejected in §3: a plugin
release would unpromote every baseline that uses it.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**The shape.** A `[target.pricing]` with two rates, with four, and with four
zeros loads; one with an unknown key, a negative rate, a string, or beside
`type = "http"` is refused by name. `pricing = "cheap"` is refused.

**Declared wins.** A declared price for a model the plugin's list knows prices a
call at the declared rate; for a model the list does not know, the declared
price is used and preflight passes where it failed before.

**The document says so.** `target_config` carries `pricing = "declared"` and
the rates for a declared price, and none of those keys for a plugin-priced run.

**The two forms hash equal.** A data suite with `[target.pricing]` and its
Python twin with `override()` produce the same digest and the same `config_hash`;
the same suite without a declared price hashes byte-identically to today, for
every example suite in the repository.

**The ruler moves the hash; the temperature does not.** Changing a declared rate
changes `config_hash`; changing `temperature` does not; changing the plugin's
shipped list does not.

**Every call site.** `run`, `rejudge`, `promote` from the CLI and from `view`,
the journal header and the MCP `run` tool each produce a hash that includes the
digest, asserted by promoting a run made with a declared price; and `promote
--target` promotes a run made with a non-default target.

**Withheld, and declared a latch.** At a named endpoint the rates appear in no
redacted document, `--json`, MCP response or `log` output, and no report. The
latch sentence of §6 is in the security page beside the other declared latches,
held there by a test, so the weakness cannot be edited out of the documentation
while it remains in the code.

**The undeclared Python price stays out of the hash.** A target built with
`Pricing(per_model=...)` directly produces no digest and hashes as today, and the
same price through `override()` produces one.

**`promote --target`.** A Python suite with two targets: a run made with
`--target other` and a declared price is refused by `promote` without the flag,
and promoted with it.

## Not decided here

**Pricing a judge declaratively.** A judge is named by a coordinate in a data
suite and its spend is reported, not budgeted by `CostBudget`. A declared judge
price is the same shape and a smaller question, and it waits for a suite that
needs its judge's cost to be exact.

**Cache-write tokens on OpenAI endpoints.** *Corrected 2026-09-15.* This
paragraph said the OpenAI plugin reports no cache writes "because OpenAI's API
has none", and that was already false: from GPT-5.6 the plugin's own price list
carries a cache-write rate, and openai 3.13.0 exposes
`prompt_tokens_details.cache_write_tokens`. The plugin still reports zero, for a
different reason, stated where the zero is (`digline_openai.client`): whether
those tokens sit **inside** `prompt_tokens`, as cached reads do, or beside it is
**unmeasured**, and each guess misprices. Until a real call settles it, a call
that writes a cache is undercounted, in the good-news direction — and a declared
`cache_write_per_mtok` prices nothing, on the official endpoint as on an
aggregator. What settles it is three calls with caching off as the baseline,
carried as a live test in `digline-openai`. An aggregator forwarding another
vendor's count in another field is the same question, and still needs its raw
usage before a rule.

**Dated prices.** A rate that changes on a known date is two suites or two
commits today, which is the honest form until somebody needs a third.
