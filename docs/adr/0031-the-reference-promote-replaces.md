# ADR 0031 — The reference a promotion replaces

- Status: accepted — the text first, checkpointed and ruled on 2026-09-24,
  the code after it. It is a breaking change, so it rides **0.20.0**, not
  0.19.2: that release was being cut when this record was opened, and this is
  deliberately not part of it
- Date: 2026-09-24
- Amended: 2026-09-24, with the code, on `promote-replacing`. These are three
  facts the text did not foresee, and none of them revisits a decision.
  **The key rule moved into the core** as `digline.core.key_of`, and
  `FileResultStore.key_for` delegates to it. §2 has the report and the wire
  print the key, and both import nothing but the core, so the rule could not
  stay in the store. **The `none` literal lives beside it** as
  `digline.core.NO_BASELINE`, for the same reason: the `view` form is rendered
  in `report`. **The examples and the image are not yet changed.** Each
  example pins `digline<0.20`, and the image installs the pinned release, so
  they show 0.19's `promote` until their pins move with 0.20.0. Changing them
  earlier would document a flag their own install refuses
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §8 (a
  baseline is an approved reference, and promotion has named conditions);
  [ADR 0011](0011-the-mcp-server.md) §1 (the MCP has no `promote`) and §6 (one
  rendering of the truth, two front ends);
  [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (the passenger rule), §2
  (a comparison that edits its own reference is not one) and §3
  (`promoted_at`); [ADR 0021](0021-the-register.md) §2 (`accepted` does not
  promote, and `promote` does not register) and §3 (the entry records the
  baseline's key)
- Opens: nothing. No `SCHEMA_VERSION`, no passenger, no migration. The run
  document gains no field (§1 says why). `OUTPUT_VERSION` stays 2: `compare
  --json` gains one key under that version's added-key rule (§2)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 2 (the baseline
  is a committed file inside the repository) is why the defect exists, and
  why the git wall described in §Context sits outside the tool
- Turns into surface: `digline promote` (a mandatory flag, a new refusal);
  `digline compare` (names the baseline's key); `digline view` (the promote
  form carries the key it rendered against); the report header;
  `docs/guide.md`, `docs/api.md`, the README and every example that promotes
- Credit: the defect was found by **kantorcodes1**, a reader on the
  r/ClaudeCode thread about the Claude Code plugin. The post was about
  something else. They read `promote_baseline` anyway and found what is below
- Number: 0031. Swept on 2026-09-24 across every ref and every sibling
  worktree; 0030 was the highest claimed

## Context

**The finding, as the reader put it.** `promote` resolves the run, checks it,
and rewrites the baseline atomically. It never checks that the baseline it
replaces is still the one the run was compared against. Two people review
different runs and promote a few minutes apart, and the second one silently
overwrites a newer reference. It is a classic lost update, and it is real.
`FileResultStore.promote_baseline` reads the run, applies its seven conditions,
and calls `_write_atomic` on `baselines/<suite>.json`. It never reads the file
it is about to replace.

**A wall exists, and it is outside the tool.** The baseline is a file in git,
so the second promotion lands as a diff. Two shapes are worth telling apart,
because the wall is not the same height in both:

1. *Two branches, one parent.* Both people promote from the same `main`. The
   second one to merge conflicts on `baselines/<suite>.json`, because `main`
   requires a branch to be up to date. The conflict *is* the wall, although a
   conflict resolved with "take mine" gets past it.
2. *One branch, a moved parent.* Person B compared run Y against reference K0
   yesterday. Overnight person A promoted X, and `main` now holds K1. B pulls,
   runs `digline promote --run Y`, and pushes. There is no conflict. The pull
   request shows a diff from K1 to Y, which is exactly what every promotion
   pull request looks like. Nothing on the page says that Y was never compared
   against K1. A reviewer finds that out only by going to look for it.

**Why it is still a defect.** In the second shape, the review is the only
wall. The facts that would reveal the problem exist only on the digline side:
the reference the comparison was made against, and the reference present when
the write happens. A tool that has both, knows they differ, and stays silent is
wrong, whether or not a wall exists elsewhere.

**The proposal already stated in public**: promote refuses when the current
baseline is not the one the run was compared against, and names the key it
expected. This record keeps that proposal. Reading the code corrects one word
in it.

**What the guard buys, and what it does not, in one place so neither is read
without the other.** It buys this: *replacing a reference that moved is never
silent.* It does not buy this: *replacing a reference that moved cannot
happen.* The refusal prints the key it found, and somebody can copy that key
without re-running the comparison. §3 states this limit as plainly as the
guarantee, and any surface that describes the guard carries both halves.

### What reading the code found

1. **Today digline does not hold the first key.** A run is written before any
   comparison. `compare` reads the run and the baseline in force *at that
   moment*, prints, and writes nothing. It is right to write nothing: §2 of
   ADR 0014 is why a comparison does not edit documents. A run can also be
   compared any number of times, against any number of references. So at
   promote time, in a later process and perhaps on a different day, no file
   says which comparison a person read. The one exception is the register
   (ADR 0021 §3). It records `baseline_key` beside a disposition, but only
   when someone chose to record one. The public sentence said digline "knows
   both keys". It knows both keys *at different moments*, and only the person
   carries one moment into the other. §1 is built on that correction.
2. **No comparison surface names the baseline's key.** `compare` prints the
   sentence and the counts. `compare --json` carries the headline and the exit
   code. The report header shows the baseline's `created_at` and `promoted_at`.
   The key appears only in `digline list`, as the `*` row, and in the
   register. So a person asked to carry the key would first have to find it
   somewhere else.
3. **`digline view` has the same race, in small.** The runs page is rendered
   against the baseline read at request time. The promote `POST` never sees
   that key. A second tab, or a second person on a shared server, can promote
   between the render and the click. The page already holds the key it would
   need to send.
4. **The same race exists on the run side, and this record does not rule on
   it.** `promote --run latest` resolves `latest` when it writes, not when the
   person compared. If a run is written between `compare --run latest` and
   `promote --run latest`, the person promotes a run they never saw. This
   needs no second person: a CI job, an agent or a second terminal is enough.
   *Not decided here* keeps it open.

## Decision

### 1. The key comes from the person, and is derived rather than recorded

The expected key is **supplied by whoever promotes**. It is the key of the
reference they compared against, as `FileResultStore.key_for` computes it:
`{slug(created_at)}-{config_hash}`. Nothing new is stored. The key is derived
from two fields every run document already carries, and it is the identity
that `list`, the register and `log` already use for a reference.

**It is not recorded in the run document, because recording it would record
the wrong fact.** That is the reason. What follows it only confirms it.

The only baseline a run document could hold is the one in force when the run
was **measured**, since the document is written then and never again. That is
not the comparison a person read. The baseline can move between the
measurement and the comparison, and then a legitimate re-compare against the
new reference would be refused. It can also move between the comparison and the
promotion, which is the case this record exists for, and there the recorded
key would agree with a comparison nobody made. A field that is wrong in both
directions is not a guard. It is a second, confident answer to the question
the guard exists to ask.

A `compare` that stamped the key into the run document instead would be a
comparison that edits documents, which ADR 0014 §2 rejects. A run compared
twice would also carry only the last comparison.

**The passenger rule is not the reason, and this record says so, because the
field would pass it.** A field such as `baseline_at_measure` meets all three
conditions of ADR 0014 §1:

1. It leaves `config_hash` alone. It is a fact about the process, not about the
   suite.
2. It migrates to absent, meaning *not recorded*. A run measured before the
   field existed recorded no reference.
3. It is a key built from a timestamp and a hash that already travel in clear.

It could ride, and cost would be a weak reason to turn it away. Wrongness is a
decisive one.

**It is not derived from the register.** The register holds the right fact,
but only when a person chose to write a line. ADR 0021 §2 keeps the two
gestures apart, and its *Alternatives* leaves "a register entry before every
promotion" to each team's own policy. A check that ran only after a
disposition would be silent in the default path, which is where the lost
update happens.

**It is the key, not a digest of the file's bytes.** `digline migrate`
rewrites every committed baseline in place when the schema moves. The bytes
change and the reference does not. A digest would refuse every promotion that
was compared before an upgrade and promoted after it. It would also be a string
no person can match against `list`. One case looks like a hole and is not:
a reference promoted again after it was replaced (K0, then K1, then K0). That
is benign, because the verdicts compared against are the same verdicts.

### 2. Where the key is carried

- **Library.** `ResultStore.promote_baseline` gains a mandatory keyword with
  no default: `expected_baseline: str | None`. `None` means *the suite has no
  baseline*. It is mandatory for the reason `promoted_at` is mandatory: a
  default would make *not checked* the ordinary outcome.
- **CLI.** `digline promote` gains `--replacing KEY | none`, and it is
  required. `--replacing none` is how a first promotion is written: it says
  there is nothing to replace. No run key can be `none`, and `none` is **not**
  a wildcard: it states that no baseline is present, and it is refused if one
  is. The flag is named for what it asserts. The shorter `--over` was proposed
  and rejected: it reads as an abbreviation of `--override`, which is the
  opposite of what it does. Because the flag is mandatory, it will appear in
  scripts read by people who never read this record, and a safety check whose
  name reads as a bypass teaches exactly the wrong thing.
- **`compare`.** It names the key it compared against. The terminal prints one
  line under the headline, `against baseline <key>`. `compare --json` gains
  `baseline_key`, which reaches the MCP through the same `digline.wire`
  function. The report header gains the key beside `promoted_at`. The key is
  a timestamp and a `config_hash`, and both already cross every boundary.
- **`view`.** The promote form carries a hidden `replacing` field holding the
  key of the baseline the page was rendered against. The `POST` passes that
  value, never the key of whatever baseline exists when the click arrives.

The check runs **last**, after the run's own refusals and right before the
write. There are two reasons. A run that is errored, replayed, uncalibrated or
under an old configuration is refused whatever the reference, and sending that
person to re-compare first would send them round twice. And placing the check
beside the write makes the remaining window as narrow as this design allows
(see *Not decided here*).

### 3. No force flag, and what the guard is without one

**The guarantee:** replacing a reference that moved is never **silent**.
**The limit:** replacing it is still **possible** without a new comparison.
The refusal names the key it found (§4), so a person can copy that key into
`--replacing` without comparing anything. digline cannot tell someone who read
the comparison from someone who copied a string. The two sentences go together,
here and on every surface that describes the guard. A record that sells a
guard as more than it is leaves its readers with a false belief, and nothing
checks for that until someone relies on it.

What makes the guarantee worth having, even with that limit, is that the
person has to name the reference being replaced, having just been told it is
not the one they compared against. After that, what happens is their decision,
and the git wall still stands behind it.

There is no `--force`, no `--replacing any`, and no environment variable. This
was the prior, and the public reason for it is the argument: **anyone who
wants to promote anyway runs the comparison again.** `compare` is offline and
deterministic, and it calls no model. Doing the right thing costs one command
and a few seconds. A flag costs more than that, because the flag becomes the
habit. It is the thing somebody types at seven in the evening, and after the
first time it is simply part of how the team promotes. Copying the found key is
possible too, but it is a decision about one named reference. A flag is a
standing permission.

### 4. What the refusal says

The new type is `BaselineMovedError`. It sits beside the other refusals in
`digline.store`, joins the tuple the CLI maps to exit 64, and joins the tuple
`view` turns into `view.promote.refused`. Missing from either tuple, it would
reach the user as a traceback.

The text names both keys, the reference's `promoted_at` when it was recorded,
and the command that settles the question. There are three shapes:

- *A different reference.*
  `run <run> was not promoted: it was compared against baseline <expected>, and
  the baseline of suite <suite> is now <found> (promoted <promoted_at>).
  Promoting it would replace a reference nobody compared it against. Compare
  it with the current one — digline compare --run <run> — and promote with
  --replacing <found> if it still holds.`
- *One appeared.* This is `--replacing none` when a baseline exists. The
  sentence is the same, with `it was promoted as the first baseline of suite
  <suite>` in place of the first clause.
- *One vanished.* The key was expected and no baseline exists. The text reads
  `the baseline <expected> it was compared against is no longer there`, and
  sends the person to `git log` over `baselines/`, because a reference that
  disappeared was deleted by a commit.

Where `promoted_at` is empty, the parenthesis is left out rather than filled
with *unknown*. That is ADR 0014 §3's rule for a signature nobody dated.

### 5. What does not move

- The MCP has no `promote` (ADR 0011 §1) and still has none. It gains a key in
  `compare`'s answer.
- The seven existing conditions, their order, and `view`'s pre-computed chips
  are unchanged. `view` cannot predict this refusal: it is about time, not
  about the run, so it has no chip and appears only as a refused `POST`.
- The register is unchanged. An entry already records `baseline_key`, and a
  team that requires one before each promotion can now check the two against
  each other.
- The git wall is unchanged, and it is not replaced. It is still the only
  thing that sees two promotions made on two machines.

## Consequences

- **A breaking CLI change.** Every `digline promote` without `--replacing`
  fails with a usage error that says which flag is missing and where to find
  the key. In this repository that covers the promote steps in `publish.yml`
  (two first promotions, which become `--replacing none`), the site's
  `home.json` replay, and `docs/guide.md`, `docs/rejudge.md`,
  `docs/register.md`, the README, three example READMEs and
  `examples/quickstart/suite.py`. The plugin's `ask-a-person` hook matches the
  verb, not the flags, so it needs no change. The `operating-digline` skill has
  to learn where the key comes from.
- **A breaking library change.** `promote_baseline` has a new mandatory
  keyword. Library callers include the test helper in `pytest-digline`
  (`tests/_cycle.py`) and about a dozen test modules here.
- It ships in **0.20.0**, a minor release, and not in 0.19.2. Its changelog
  credits **kantorcodes1** and says what they did: they read `promote`'s code
  after coming in from a post about something else.
- `view.py`'s module docstring says *"the same three refusals"*. There are
  seven conditions and six types today, counting the `SuiteMismatchError` that
  0.19.2 added to `read_run`. It is corrected in the same change, because this
  record adds another. The tuple of refusals that `view` catches does not
  include `SuiteMismatchError` either. That is a separate question for whoever
  owns the 0.19.2 follow-up, noted here because this change edits the same
  tuple.

## Alternatives considered

- **Record the reference in the run document.** Rejected in §1 because it
  records the wrong fact, even though it would qualify as a passenger.
- **Have `compare` write the key somewhere**, such as a sidecar file per run.
  A comparison that writes is rejected by ADR 0014 §2. Runs are also
  gitignored, so the sidecar would not reach a second machine, and the second
  machine is where shape 2 happens.
- **Take the key from the register.** Rejected in §1: it would be silent in
  the default path.
- **An opaque token printed by `compare`**, hashing the run key and the
  baseline key, so that only a comparison can produce it. It would stop a key
  copied from `list`. Rejected because it cannot be read: the refusal could no
  longer say which key was expected, which is §4's whole requirement. It would
  also defend against a deliberate person, who can edit the JSON by hand
  anyway. The tool's job here is to not be silent, not to be a lock.
- **`--over` as the flag's name.** Rejected in §2: it reads as `--override`.
- **An optional `--replacing`.** Absent in the ordinary case means unchecked in
  the ordinary case, which is where the lost update happens.
- **A force flag.** §3.
- **Compare against the current baseline inside `promote` and print the
  result.** That turns a refusal into a promotion based on a comparison nobody
  read, which is the defect in a new form.

## Test plan

- Every shape in §4, each with its exact keys in the message: K0 expected with
  K1 present; `none` expected with K1 present; K0 expected with no baseline
  present.
- `none` expected with no baseline present promotes. K1 expected with K1
  present promotes.
- A baseline migrated between the comparison and the promotion (new bytes,
  same key) promotes. This is the control that fails if the check is ever
  moved onto a digest.
- The check runs last: a run that is both errored and against a moved baseline
  is refused as errored.
- `view`: render the page, promote a different run through the store, then
  `POST` the form. The response is refused and names both keys.
- `compare`: the terminal line, the JSON key, and the MCP answer carry the same
  string (the parity suite).
- `promote --help` states both halves of §3 for `--replacing`: the guarantee
  and the limit, in the same sentence.
- The CLI exits 64 on the new refusal, and a missing `--replacing` is a usage
  error that names the flag.
- One test must fail on today's `main`: two promotions of different runs, both
  with the first reference as `--replacing`. The second write must not happen.

## Not decided here

- **The window inside the call.** The check and the rename are two system
  calls. Two processes promoting on one checkout within microseconds can still
  both pass. Closing that needs a lock. An `O_EXCL` lock file inside a
  committed directory has its own failure: a stale lock blocks every
  promotion, and it can be committed. The window this record closes is
  minutes wide and involves people. The one left open is microseconds wide and
  involves two processes on the same disk.
- **`promote --run latest`** (finding 4). A run written between the comparison
  and the promotion is the same defect on the run side. The candidates are to
  refuse `latest` in `promote`, or to have `compare` also print the resolved
  run key. Neither is ruled here.
- **Whether `compare --json` should also name the resolved run key.** It
  belongs to the question above rather than to this one.
