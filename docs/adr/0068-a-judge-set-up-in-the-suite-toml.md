# ADR 0068 — A judge set up in the suite.toml, and the instruction recorded per kind of judge

- Status: accepted 2026-11-14, by Alessandro Prandini, proposed the same day
  from a first use outside the project, on an application with a judged
  suite, beside
  [ADR 0067](0067-calibrating-the-judge-against-a-person.md). The table, its
  four keys, and the digest per kind of judge were set out by the brief that
  asked for both records. **What this record proposed beyond them is marked
  *decided here***, with the alternative beside it. Accepted as proposed,
  at 17:34, with ADR 0067. Not built yet: the construction is the fifth
  pull request of ADR 0067 §10. *§3 built 2026-11-16*, in the release pull
  request of 1.3.0, by Alessandro Prandini's decision of that day to rename
  the key before any release carried it: the first case of *When it reaches
  a release*. §1 and §2, the table, wait on that fifth pull request.
  *§1 and §2 built 2026-11-19*, in a pull request of their own and not in
  the fifth of ADR 0067 §10, which still holds `at_least`: the plan of §5
  is narrowed to the table, and `at_least` stays with ADR 0067. §1 adds one
  refusal the record did not name, a `temperature` outside 0 to 2, at load
- Shipped: 1.3.0 — §3 alone, the digest per kind of judge; §1 and §2, a
  judge set up in the `suite.toml`, are on `main` and in no release
- Date: 2026-11-14
- Opens: **nothing.** No `SCHEMA_VERSION`: `judge_config` is a mapping of
  scalars, and its keys are added. No `OUTPUT_VERSION`, no
  `RECORDING_VERSION`, no entry in the layout of `.digline/<tenant>/`, and no
  assertion identity or `config_hash` moves
- Amends, each by a dated note beside the place it amends, which points
  here, the text kept as written:
  [ADR 0007](0007-the-declarative-suite-format.md) §3, *"a table as the
  coordinate is still refused as settings"* (§1);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §4, as
  amended on 2026-11-14, its `prompt_digest` and the limit it names (§3)
- Assumes: [ADR 0004](0004-every-plugin-is-a-target-and-a-judge.md) §1 (one
  plugin, a `Judge` and a `ClaimJudge`) and §5 (no credential in a suite);
  [ADR 0005](0005-the-configuration-of-the-system-under-test.md) §1 (a value
  not sent is absent)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 5 is upheld:
  no call the suite did not configure. Decision 6 is upheld: the provider is
  still resolved by its entry point
- Number: 0068, swept with 0067 (see its header)
- Owed: the three lines on digline.dev that every new record needs

## Context

**What happened.** On the same use as ADR 0067's, the suite was a
`suite.toml`, and a judge that needed a larger `max_tokens` than its
plugin's default could not be given one there: the file names a judge by
coordinates alone, and the cap is the plugin's. The loader's remedy is a
`suite.py`, for one setting; #1010 raised the default to 1024 in all three
plugins, which helps the case reported and not the next judge that needs
another number.

**What a `suite.toml` holds today**, read at `b3ea7e5b`:

- `judge = "provider/model"`, resolved through the plugin's entry point to
  both of its judges (ADR 0007 §3);
- `judge_pricing`, a table of rates beside it, since 2026-11-05;
- **a table as `judge` is refused**, with *"a judge named in data is its
  coordinate alone: it grades with the plugin's own defaults, and a judge set
  up differently is an object"* (`src/digline/host/toml_suite.py:631`).

**What a run records of the judge**: `provider`, `model`, `max_tokens`,
`temperature` where one was sent, what the provider said answered, and, since
#1010, `prompt_digest`, the digest of the instruction the judge is asked
under. Where a suite holds several judges of one identity, a value they
disagree on is dropped (ADR 0005 §4), and a `ScoreJudge` and a
`ClaimCountJudge` always disagree on their instruction, so a suite holding
both records no digest at all. ADR 0005 §4's note of 2026-11-14 names that
limit.

## Decision

### 1. `judge` may be a table of four keys

*Set out by the brief.*

```toml
[[assertions]]
type = "llm_rubric"
name = "tone"
rubric = "Is the answer courteous and plain?"
judge = { model = "anthropic/claude-haiku-4-5", max_tokens = 1024 }
threshold = 0.7
tolerance = 0.05
```

- **`model`**, mandatory: the coordinate, with ADR 0007 §3's rules
  unchanged, the first slash and an opaque model half.
- **`max_tokens`**, optional: an integer of at least 1, passed to the
  plugin's judge as its own argument.
- **`temperature`**, optional: a number, passed the same way. **A plugin that
  refuses one refuses it at load, with its own reason**: digline-anthropic's
  judges refuse every `temperature`, because the API version they send
  answers it with a 400 (`refuse_temperature`), and the sentence names the
  table's entry.
- **`pricing`**, optional: the rates, in `judge_pricing`'s shape and with its
  rules. *Decided here:* `judge_pricing` beside a table is refused, *"two
  prices for one judge"*; beside a string it stays as it is.

Any other key is refused by name, listing the four. The string form is
unchanged and remains the short way. The coordinate is still the
instrument's identity: the settings are how it is set up, and ADR 0005 §4
records them apart.

**What a table does not hold**, and why each stays out:

- **no credential**, by ADR 0004 §5 and ADR 0007 §3, unchanged;
- **no instruction of the judge's own**: a judge with rules of its own is an
  object in `suite.py`, as ADR 0007 §3 says of a custom judge;
- *decided here*, **no other parameter of the plugin's**, a `region`, a
  `base_url`, a `prefill`: each is a plugin's word with a plugin's rules, and
  a table that took any of them would be the open mapping ADR 0005 §1 keeps
  out of the record. A judge set up beyond the four is an object.

*The alternative not taken:* a `[judges]` table at the top of the file, each
judge named once and referred to by name from the checks. It saves
repetition in a suite of many checks, and adds a second namespace, a name
declared in one place and read in another, to a format whose checks each
read whole today. It can come later without changing this form.

### 2. What the run records

*Set out by the brief: the temperature and the cap written in the run.*

Nothing new is needed for that: `max_tokens` and `temperature` are in
`judge_config` today, and a value that was not sent is absent, by ADR 0005
§1. The table's settings reach the run through the judge they build, so a
`max_tokens` raised in the file is a judge configuration that changed, and
`compare` says *the judge changed*, as it says it for a judge built in
Python.

*Decided here:* nothing records **where** a setting came from, the table or
the plugin's default. The run records what was sent, and a default sent is
sent.

### 3. The instruction, recorded per kind of judge

*Set out by the brief: a digest per kind of judge, so that two judges on one
model do not lose it.*

*Decided here:* `prompt_digest` gives way to two keys, **`score_prompt_digest`**,
written by a `ScoreJudge`, and **`claim_prompt_digest`**, written by a
`ClaimCountJudge`, each sixteen hex characters of the sha256 of its class's
`system`, as `prompt_digest` is. ADR 0005 §4's merge rule is narrowed for
these two keys alone: **each is merged over the judges that write it**, so a
judge of the other kind, which never writes it, does not disagree with it.
Two `ScoreJudge`s on one identity under two instructions still drop
`score_prompt_digest`, by the rule as it stands.

A judge outside these two classes that names a `provider` writes neither,
and declares what it likes in its own `config`, as today.

**When it reaches a release.** `prompt_digest` is in no release: it was
built in #1010, on `main`, for 1.3.0.

- **If this record is built before the cut of 1.3.0**, `prompt_digest` is
  renamed in place, and no reference anywhere was recorded with it.
- **If after**, a reference recorded under 1.3.0 holds `prompt_digest` and a
  later run holds the new key: `compare` reads one key `missing` and one
  `new`, and says *the judge changed* once more, as it did at 1.3.0's first
  run. The CHANGELOG of that release says so.

Both keys join `NAMED_CONFIG_KEYS`, and `prompt_digest` leaves it in the
first case; in the second it stays, so a 1.3.0 document still projects its
key in clear.

*The alternative not taken:* one key whose value names both digests,
`score:…;claim:…`. A configuration is diffed field by field and rendered by
value (ADR 0005 §1), and a value that packs two would say *changed* without
saying which instruction moved.

### 4. Compatibility

A minor, by `RELEASING.md`'s *Choosing the version*:

- a `suite.toml` that loads today loads the same; a table that was refused
  now loads, which is an addition;
- no signature changes: the table's keys are the judges' existing keyword
  arguments, passed by keyword as the string form passes `model`, and a
  plugin whose judge takes no such argument refuses the key at load, as
  `judge_pricing` is refused today for a judge that takes no price;
- ADR 0007 §9 holds both ways: nothing here is TOML-only, since a
  `suite.py` builds the same judge with the same arguments, and the gap
  closed is one the data form had;
- no assertion identity moves: a check fingerprints its judge by type name,
  never by its settings (`AssertionBase.identity`), so a table edited in
  place pairs with the verdicts before it;
- no `config_hash` moves: the judge's settings are its configuration, not
  the suite's rules, as they are for a judge built in Python;
- `judge_config` gains the two keys of §3, and, if built after 1.3.0, a
  first comparison that says the judge changed, said in the CHANGELOG.

### 5. The plan

Built in the fifth pull request of ADR 0067 §10, with `at_least`. *It
measures*: a table builds the judge that the same arguments build in
Python, compared by `config`; each of the four keys reaches the run, and its absence
leaves the key absent; an unknown key, a table beside `judge_pricing`, and a
`temperature` the plugin refuses are each refused at load by name, each with
a control that loads; a suite holding a `ScoreJudge` and a `ClaimCountJudge`
on one model records both digests, and a change to either instruction is
`changed` on its own key. *It closes* a cap that a `suite.toml` could not
raise, and an instruction change that a suite with both kinds of judge could
not see.

## Consequences

A `suite.toml` can set the two numbers a judge most often needs, and the
pricing it already could, without becoming a `suite.py`. What it sets is
recorded as a judge built in Python records it.

A suite with both kinds of judge sees a change to either instruction.

## Not decided here

- A `[judges]` table referred to by name (§1).
- Any judge setting beyond the four.
- Whether the string form should one day be written as a table by `digline
  suggest`, whose assistant sets its own `max_tokens` today.
