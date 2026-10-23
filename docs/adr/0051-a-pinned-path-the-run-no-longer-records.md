# ADR 0051 — A pinned path the judged run no longer records

- Status: accepted 2026-10-18, by Alessandro Prandini, after its code landed
  in #582. **#483 stays open for its promotion half.** The code of the
  comparison has landed; the promotion's has not, and *Context* leaves it
  outside this record (*"`promote` computes no comparison … That is outside
  this record"*). The sentence below on closing #483 holds for the half that
  landed.
  Proposed 2026-10-16. The decision below was ruled on 2026-10-16,
  on #483, before this record was written. The text is not yet accepted, and
  nothing in it is implemented. #483 stays open: this record answers its
  question, and the issue closes when the code lands. *The block above is the
  proposed phase's own text, kept as written, and speaks from that phase.* The
  start of this status carries what is true now, and `Shipped:` below says in
  which release the code landed
- Shipped: 0.32.0
- Date: 2026-10-16
- Opens: **nothing on landing.** No code, no `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`. The code that implements it moves no schema either: the
  pins it reads on the reference's side are `Run.pinned`, recorded since schema
  16 ([ADR 0029](0029-the-artifact-that-must-not-drift.md) §3)
- Amends: [ADR 0029](0029-the-artifact-that-must-not-drift.md) §7, §8 and §9,
  which carry dated notes pointing here and are kept as written
- Assumes: [ADR 0029](0029-the-artifact-that-must-not-drift.md) §4 (a pin
  that names nothing the run recorded is refused), §5 (the rule is read on the
  comparison's rows), §6 (a drifted pin returns 2, and why not 1), §9 (the
  judged run declares) and §10 (what does not move);
  [ADR 0016](0016-the-canary-case.md) §1 (the run being judged declares)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. Decision 3 — *no
  vacuously green assertion* — is the reason, as it was ADR 0029's: a pin that
  loses its path and still reads green is a declared control whose outcome
  nobody sees
- Turns into surface, when the code lands: `AGENTS.md` §6, where `2` gains a
  cause, and `exit_code()`'s docstring, which is the enumeration of them
- Number: 0051. Swept on 2026-10-16, before a line was written, across
  `origin/main` (`7289fd7`), every local and remote branch and tag (81 refs,
  after a fetch with `--prune`), the worktrees of this repository and the open
  pull requests (none). The highest number taken anywhere is 0050

## Context

*digline#483.*

**The case.** A pinned artifact whose path changes in the same run that changes
its content leaves two rows in `artifact_deltas`: the old key `missing`, not
pinned because pins are read from the judged run, and the new key `new`,
pinned, with nothing to compare against. No row is `changed`, so
`pinned_drifted` is false; no row is `unknown`, so `pinned_unchecked` is 0.
`compare()` exits 0 and the headline says nothing about pins.

**Measured, in #483.** One suite, one pinned `tools.json`, moved from `eval/d1`
to `eval/d2` with `git mv` and changed in the same run. Each published release
from 0.19.0 to 0.29.0, installed from PyPI, gives `compare` exit 0 and
`pinned_drifted: false` for the rename, against exit 2 and `true` for the same
change under an unchanged name, and accepts the promotion. `digline-mcp`'s
`compare` tool gives the same. The table and the list of releases are in the
issue.

**Read in the code, at `7289fd7`, and not executed.**

- The identity of an artifact is its path relative to the perimeter:
  `read_artifacts` and `read_pinned` key both with the same `_key`, in
  `src/digline/host/artifacts.py`. The digest is the value under that key,
  never the key.
- `artifact_deltas()`, in `src/digline/core/compare.py`, reads pins from the
  judged run alone and iterates the union of the two runs' keys. Each key is
  looked up by exact string on each side, and digests are compared only between
  two entries under the same key.
- `pinned_unchecked` counts pinned rows whose outcome is `unknown`, which
  `artifact_deltas()` assigns only where a side is withheld. The `new` row of
  the rename is not counted. That `pinned_unchecked` is 0 in the case above is
  deduced from this, and #483's headline, which carries no unchecked clause, is
  consistent with it.
- `exit_code()`, in `src/digline/wire/contract.py`, reads `pinned_drifted` and
  not `pinned_unchecked`.
- `promote` computes no comparison. Its refusals are read from the run document
  and from the baseline in force (`src/digline/store/promotion.py`), so a pin
  never blocks a promotion, renamed or not. That is outside this record.
  *No longer true since 2026-10-23 ([ADR 0053](0053-promote-refuses-a-pin-nobody-named.md)),
  and kept as written.* `promote` now compares the run with the baseline it
  replaces, beside the write and after condition 8, and a drifted or lost pin
  refuses the promotion unless `--accepting-pin` names exactly the paths it
  implicates. The sentence was true of the code it describes, at `7289fd7`.

**What ADR 0029 considered.** §7's reason for not firing on `new` is the first
comparison after a pin is added: it *"would go red on arrival, teaching the
author that the feature is noise before it has ever caught anything."* §8 is
about redaction: *"The author declared this must not drift. Redaction means we
cannot tell."* Neither considers a pinned path that the judged run no longer
records.

**What ADR 0029 decided and the code never did.** §9: a pin present in the
baseline and absent from the run *"is not silent either: the comparison reports
it"*. Nothing in `src/` or in `packages/*/src/` reads `baseline.pinned`, and the
comment beside the line that reads pins from the judged run says *"which ADR
0029 §9 reports elsewhere"*. The search was for `baseline.pinned` and
`left.pinned`, and it found nothing.

## The decision

*Ruled 2026-10-16.* Three facts join the comparison. One of them moves the exit
code.

1. **A pinned row with no reference value is unchecked in its own right.** A
   pinned row whose outcome is `new` has nothing to be compared with, so whether
   it changed was not checked. It is reported with its own name, its own count
   and its own clause in the headline sentence, and it does not move the exit
   code. For a pin just added beside its file, *this pin has no reference to
   compare against yet* is true and informative: §7's reason against `new` was
   a reason against red, not against the sentence.

2. **A pin the reference held and the judged run does not hold is reported.**
   This is the fact §9 already ruled — *"the comparison reports it"* — and the
   code never built. It covers a pinned path the judged run does not record,
   and a path the judged run still records but no longer pins. It has its own
   name, count and clause, and it does not move the exit code: §9's withdrawal
   stays possible without a red, which is its reason. It is not drift. The
   contents were never compared, so nobody can say the file drifted.

3. **The conjunction returns 2.** A path the reference pinned and the judged
   run does not record, **and** a pinned row in the judged run with no reference
   value to compare against: that run is the rename of #483, and it exits 2.

   **Why 2.** The contract says what `2` means, in `exit_code()` in
   `src/digline/wire/contract.py`, and ADR 0029 §6 said it first: "`2` already
   means *the numbers beside this are not what they look like*, which is true
   here — the system that produced them is not the system the reference
   approved." That is why a drifted pin returns 2 and not 1, and it is the
   same reason here.

   **Why this departs from §8.** §8 ruled that an unchecked pin neither passes
   nor fails, and left the policy to whoever runs the pipeline: *"`--json`
   carries the count so that a caller who wants that rule can have it in one
   line."* That works for a withheld pin, because somebody chose to withhold
   it, and whoever runs the pipeline knows redaction is on and can build a rule
   on the count in advance. A lost pin has no such owner. Nobody chose to lose
   the pin, and no flag set beforehand covers it. On that, 2 asserts no more
   than the document behind it.

   **The declared cost.** A run that removes pinned file X and adds a pin on a
   new file Y in one change gets a 2. That run is indistinguishable from the
   rename: from the two documents, a path the reference pinned is gone and a
   pinned path has no reference value, and nothing in either says whether one
   became the other. In one of the two readings a guarantee was lost. Where two
   readings cannot be told apart and one of them is a lost guarantee, the gate
   says it could not judge. That is what 2 means.

   §9's withdrawal is untouched by this. Either half alone is reported and
   moves nothing: a pin withdrawn with its file, or a pin withdrawn while the
   file stays, or a pin added beside a new file. Only the two together exit 2.

**The names.** They follow ADR 0029's `pinned_drifted` and `pinned_unchecked`:

| fact | on `Comparison` | on `Headline` |
|---|---|---|
| 1. a pinned row whose outcome is `new` | `pinned_unreferenced` (paths) and `pinned_unreferenced_count` | `pinned_unreferenced: int` |
| 2. a pin the reference held and the judged run does not | `pinned_withdrawn` (paths) and `pinned_withdrawn_count` | `pinned_withdrawn: int` |
| 3. the conjunction | `pinned_lost: bool` | `pinned_lost: bool`, read by `exit_code()` beside `pinned_drifted` |

Paths and counts are kept apart for the reason `pinned_unchecked_count` gives:
a path can describe a customer, and a renderer reaches for the count.

**Precedence is unchanged.** A regression or a moved canary still returns 1
before any cause of 2, by ADR 0029 §6 and ADR 0024 §4.5.

**A withheld side is read first.** Read in the code, at `7289fd7`, and not
executed: `artifact_deltas()` answers `unknown` for a withheld side before it
asks about `new` or `missing`, so in a redacted comparison a pinned path
answers §8's fact and not these. This record changes that order in no way.

## What does not change

- **The identity of an artifact stays its path.** A declaration names a path,
  so a pin is a path, and a comparison of pins is a comparison of paths.
- **§7 still says that an absence is not a change.** The facts above are not
  changes. They are other outcomes, with names of their own, and none of them
  is folded into `pinned_drifted`.
- **Identity by content is not the answer.** A rename with no change still
  gives `new` and `missing`, and in #483 the digests differ, so pairing rows by
  content would not save even this case.
- **`pinned_unchecked` keeps its meaning and its count.** §8 invited consumers
  to build a rule on it, and its sentence, *"is not included here"*, is false
  for a `new` row, which is included and has no reference. The new facts have
  names, counts and sentences of their own.
- **`digline diff` never gates on any of them**, as ADR 0029 §10 rules for
  `pinned_drifted`: neither side of a diff was approved by anybody.
- **The register gains nothing**, by ADR 0029 §10's reasoning: `RecordedOutcome`
  carries `exit_code`, and a bumped `REGISTER_VERSION` makes every committed
  register unreadable.

## Its price, under ADR 0029 §10

**`OUTPUT_VERSION`.** The headline block on the wire gains three keys. The
contract's stated rule is that an added key does not break a consumer, and
ADR 0029 §10 kept `OUTPUT_VERSION` at 2 on that rule. What an added key does
not cover is the exit code: a consumer that reads only the number sees a 2 in
a case that read 0 before, and nothing in the version says so. Whether that
asks for an `OUTPUT_VERSION` bump is a question this record names and leaves to
the change that implements it, by the contract's own procedure.

**A run that exited 0 can read as 2.** A comparison of two stored runs is
recomputed every time it is made, so a stored pair that exited 0 under the code
before this will exit 2 under the code after it, when it is the case above.
That is the point of the change and it needs a release note.

**Not covered here.** `pytest-digline` does not gate on a pin at all; that is
#484, and this record does not decide it.
