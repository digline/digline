"""The version of the machine surface, and the exit codes it reports.

Both are contracts with a program rather than with a person, which is why they
live here and not in a front end. `digline.cli` re-exports every name in this
module, so `from digline.cli import EXIT_OK, OUTPUT_VERSION` keeps working.
"""

from __future__ import annotations

from digline.report import Headline

__all__ = [
    "EXIT_OK",
    "EXIT_UNJUDGED",
    "EXIT_USAGE",
    "EXIT_WORSE",
    "OUTPUT_VERSION",
    "exit_code",
]

#: The shape of what `--json` prints, and nothing to do with `SCHEMA_VERSION`.
#:
#: Two contracts, two lifetimes. `SCHEMA_VERSION` is about documents already on
#: disk, which is why it comes with migrations: a file written last month must
#: still be readable. This one is about what a pipeline parses on stdout today,
#: where nothing needs migrating and the only question is whether the consumer
#: knows the shape moved. Tying them together would mean a reworded sentence
#: bumping the storage schema, and a new field inside a `Run` bumping the output
#: contract for consumers who saw no change.
#:
#: 1: `worse`, `unjudged`, `suspended`, `config_changed`, `artifacts_changed`,
#:    `counts`, `reasons_available`, `sentence`; `deltas` under `--json full`.
#:    Since then, and without a bump because the rule above is that added keys
#:    do not break a consumer: `target_config_changed` and
#:    `judge_config_changed` on the headline, and `target_config_deltas` /
#:    `judge_config_deltas` under `full` (ADR 0005 §7).
#:
#:    Also without a bump, by the same rule: `pinned_drifted` and
#:    `pinned_unchecked` on the headline (ADR 0029). The first is a new cause of
#:    exit 2, which a consumer reading `exit_code` already honours; the second is
#:    on the wire *because* it moves no number — a pin nobody could check is
#:    neither a pass nor a failure, and a pipeline that wants its own policy about
#:    that needs the count rather than a sentence to parse.
#:
#:    `digline diff --json` is under this same contract from the start, and its
#:    arrival is not a bump either: a *new command's* output breaks no existing
#:    consumer, because nothing that parses `compare --json` today sees a byte
#:    change. Its structure is symmetric and carries **no `worse` field** — the
#:    absence is the point, not an omission (ADR 0008 §1).
#:
#:    `digline explain --json` is under this same contract from its first
#:    release, and its arrival is not a bump either — by the same rule as
#:    `diff`'s, and the rule is **"a new command"** rather than "additive".
#:    The word matters: what it emits is a new top-level shape, a list of typed
#:    facts, not a key added to an existing document. Calling that additive
#:    would license adding shapes to `compare --json` later under a word that
#:    was never about them. It carries no sentence at all, which is the other
#:    half of ADR 0012 §3: the prose is a render of those facts, so shipping it
#:    would ship a derived value. (ADR 0012 §8)
#:
#:    `exit_code` joins the headline under the same rule (ADR 0011 §4). It is
#:    the number `AGENTS.md` §6 calls the contract, and it is a *field* because
#:    an MCP tool has no process to exit; it is on `compare --json` as well so
#:    that the two surfaces cannot answer differently. `diff` gains nothing of
#:    the kind and must not: it has no verdict to carry.
#:
#:    `rejudged` on the headline (ADR 0015 §8), `canary_moved` on the headline
#:    and `canary` on each delta (ADR 0016 §8): the same rule a fourth time.
#:    `canary_moved` is the first addition that can change the **exit code** of
#:    a run — and only of a suite that declares a canary, which no suite did
#:    before this release, so no existing consumer sees a number it did not see
#:    before.
#:
#:    `on_the_line` on the headline (ADR 0018 §8): the same rule a fifth time,
#:    and the quietest instance of it. It counts the checks whose measured band
#:    covers their own threshold — a fact about how firmly this run answered,
#:    not about how it compares — and unlike `canary_moved` it **cannot** move
#:    an exit code, by that section's own ruling. A consumer that ignores it
#:    parses the same numbers it parsed before.
#:
#:    `scale_lost` on the headline and `calibration` on each delta (ADR 0024
#:    §4.7): the same rule a seventh time. Like `canary_moved` it can change the
#:    exit code, and only of a suite that declares a calibration case, which no
#:    suite could before this release.
#:
#:    `target_echoed` on the headline (ADR 0020 §3, row 7): the same rule a sixth
#:    time. The endpoint returned the requested id as the model that answered,
#:    so what answered is not identified. A fact and not a verdict — it moves no
#:    exit code — and never true behind a named endpoint, where the answering
#:    model is withheld.
#:
#:    `denominator_moved` on the headline and on each `explain` check fact: the
#:    same rule an eighth time, and **it arrives with one change that is not an
#:    added key**, stated here rather than left to be discovered. The `counts`
#:    map no longer counts a delta whose two sides were measured over different
#:    numbers of cases — the key set is untouched, but `improved` or `regressed`
#:    is one lower in a run where that happened, and `worse` is false where the
#:    arithmetic pointed down. That is not a shape change and it is not additive
#:    either: it is the removal of a number that was an affirmative false claim,
#:    which is the only reason this rule tolerates one. The precedent is exact —
#:    ADR 0024 §4.4 took the calibration deltas out of the same map without a
#:    bump, and for the same reason. A consumer that summed the six counts to
#:    recover "how many deltas were there" was already wrong then.
#:    (the delta-pass over 0.15.1)
#:
#:    `denominator_moved` **on a delta whose outcome flipped from `fail` to
#:    `pass`**: the same rule a ninth time, and the same one number removed for
#:    the same reason. The entry above took the incomparable *movements* out of
#:    `counts`; this takes out the incomparable *flip upward*, which is the case
#:    the advisory behind that entry is about and the one it left in. So
#:    `improved` is one lower again in a run where a gate crossed its threshold
#:    on a denominator that had moved, and the flag is now true on rows where it
#:    read false. No key moves, and a flip the other way is untouched: it still
#:    counts, still makes `worse` true and still exits 1. The precedent is the
#:    one directly above, which is ADR 0024 §4.4's. (the delta-pass over 0.15.2)
#:
#:    `unreconciled` on the headline, and `unreconciled` as a tally kind on
#:    `explain --json`: added keys, under the same rule. It moves no exit code
#:    of its own. A run that does not reconcile already exits 2 through the
#:    errored verdict that each gap is recorded as. A run that reconciles, which
#:    is every run the shipped driver produced before it, reads `0` here and
#:    never meets the kind. (ADR 0027 §7)
#:
#:    `reference_unreconciled` on the headline, and `reference_unreconciled` as
#:    a tally kind on `explain --json`: added keys, under the same rule, and
#:    without a bump for the reason every entry above gives. The same count for
#:    the **reference** — the document that is versioned in git, and the one
#:    whose gaps nothing read until now. It moves **no exit code at all**, which
#:    is where it differs from the entry above it: the run being compared may
#:    itself reconcile perfectly, and failing it for the state of a baseline
#:    promoted weeks ago would fail the wrong run. What the number is for is a
#:    pipeline that wants to refuse a comparison standing on a measurement
#:    nobody can state. A comparison against a reference that reconciles, which
#:    is every one the shipped promotion path allows, reads `0` here and never
#:    meets the kind. (F-10, the second 0.17.0 delta-pass)
#:
#:    `spread_absence` beside `spread` on `log --json`: an added key, under the
#:    same rule. The spread comes out empty for four different reasons and only
#:    one of them is a fact about the suite, so a consumer reading an empty
#:    `spread` could not tell a fresh store from a suite that declares no
#:    run-level check from a run whose aggregates all flipped. The key names
#:    which, counted by cause and never as a total. It reaches no exit code —
#:    `log` exits 0 whenever it read the store, and its `--json` has no
#:    `exit_code` at all. (ADR 0024 §7.5, amended 2026-09-22)
#:
#:    `suite_deltas` under `compare --json full` and over MCP, and a `"rule"`
#:    kind on `explain --json`: added keys, under the same rule. What moved on
#:    the **suite** side when `config_hash` changed — each threshold, tolerance,
#:    sample count and gate by value and by direction. Nothing is recorded to
#:    make them: they are derived from two stored documents out of fields every
#:    verdict has always carried, so no schema moves and a baseline promoted a
#:    year ago is read as well as one promoted today. It moves no exit code and
#:    gates nothing — where the bar sits is a person's declaration, and
#:    `promote_baseline` refusing across a changed `config_hash` is where they
#:    sign it. (ADR 0028)
#:
#: 2: **the first bump, and the first change that is not an added key.** Every
#:    entry above is something a consumer could ignore and go on parsing the
#:    bytes it parsed before. This one rewrites bytes inside values it already
#:    reads: DEL (U+007F) and the C1 block (U+0080–U+009F) are now written as
#:    their JSON escape spelling — six ASCII characters where there used to be
#:    one character — in every string this package renders, keys included.
#:
#:    **Why the value and not the serialised document.** `digline.cli` escaped
#:    those two ranges on the finished JSON text, where the change is invisible
#:    to a parser: `\\u009b` and the raw byte are one character to `json.loads`.
#:    That cannot be done for every front end. `digline-mcp` hands dictionaries
#:    to an SDK that serialises them itself, so digline never touches those
#:    bytes, and a tool name carrying U+009B — which *is* CSI, and opens on a
#:    terminal what ESC `[` opens — reached an MCP client raw. The only surface
#:    both front ends share is the value, so the value is where the rule had to
#:    go, and the cost moves from the terminal to the consumer.
#:
#:    **What it costs, stated plainly.** A pipeline that read a control character
#:    out of a provider-supplied string — a tool name, a model id, a finish
#:    reason — now reads its escape spelling instead. Nothing else moves: no key
#:    added or removed, no number changed, and any text without those two ranges
#:    is byte-identical. The trade is that a control byte inside text the
#:    measured system chose is not data anybody needs verbatim, and that one fact
#:    must not read differently at two front ends — which is the reason this
#:    package exists. (from the release delta-pass over 0.15.0)
#:
#: **This record grows by an added key. No count of the keys is written, and no
#: enumeration of a set that can be found by looking — but the criterion is
#: narrower than either, and most counts in this repository are fine.**
#:
#: A record saying what it *decided* is dated history and does not age: each
#: entry above names what a release added and why it needed no bump, and an
#: occasion does not change. The defect lives in one place only — where a record
#: describes the **present state** of a set that *other* records grow. That is a
#: claim about today, in a document nobody revisits, about a set whose growth is
#: somebody else's amendment, so it is guaranteed to be falsified by a procedure
#: that does not pass through it.
#:
#: The repository holds exactly two of that species, both named in ADR 0012 §3
#: so a reader can check for a third rather than re-derive the criterion: ADR
#: 0002 §8's promotion conditions and ADR 0011's MCP tools. Both fixed
#: 2026-09-22, which makes that sweep complete rather than ongoing.
#:
#: A stale count is visible — five where six exist. A stale enumeration is not:
#: it contradicts nothing and simply never looks at the sixth, and a gate built
#: on one cannot fail on what it omits. So the count is the symptom and the list
#: is the disease. Enumerate where the enumeration **is** the source — the five
#: exclusion names in `digline.core.compare` exist in one place and every
#: renderer walks it — and look where the source is elsewhere.
#:
#: The cure sits at the point of growth rather than in a gate at the point of
#: reading: a check can look for numbers, it cannot ask whether a set has an
#: amendment procedure. So, when you add a key here: there is no total to
#: correct, because none is written.
OUTPUT_VERSION = 2

EXIT_OK = 0
EXIT_WORSE = 1
EXIT_UNJUDGED = 2
#: Not a verdict, and `exit_code()` never returns it: it is the front end
#: refusing the request that was made, which `AGENTS.md` §6 states as "anything
#: else is the CLI refusing the request you made, not a verdict on the suite".
#: It sits with the others because the four are one documented table, and a
#: reader asking what `2` means should not find three answers here and one
#: somewhere else.
EXIT_USAGE = 64


def exit_code(head: Headline) -> int:
    """The one place a headline becomes a number.

    Precedence is deliberate: **a regression, or a canary that moved, outranks
    an unjudged case and a lost scale.** Both need attention, but a regression
    is a statement about behaviour that got worse — and a moved canary a
    statement about *which model* answered — while an unjudged case is a
    statement about the harness. When both are true the louder fact must be
    the one the pipeline reports, or a real regression would hide behind a
    flaky provider.

    A suspension never fails: it is a decision someone already made, not an
    outcome.

    `2` has three causes and this body is the enumeration of them — the one place
    an enumeration is safe, because it is the source rather than a description of
    somebody else's set. `EXIT_UNJUDGED` keeps the name of the first; renaming an
    exported constant to settle a naming debt would break consumers to improve a
    docstring.

    What is **not** read here: `head.pinned_unchecked`. A pin nobody could check
    is a fact about this comparison's competence rather than about the world, and
    turning it into a number would assert one layer up precisely what the fact
    layer declines to assert one layer down — the same reason a drifted pin
    returns 2 and not 1. It is on the headline, in the sentence and on the wire,
    and it moves nothing. (ADR 0029 §6, §8)
    """
    if head.worse or head.canary_moved:
        # Two facts, one number. A canary that moved says the model behind the
        # alias probably changed, which is a reason to stop whichever direction
        # it moved in — and it is deliberately not folded into `worse`, so the
        # headline can say what happened without saying something untrue about
        # it. (ADR 0016 §5)
        return EXIT_WORSE
    if head.unjudged or head.scale_lost or head.pinned_drifted:
        # A lost scale is not an errored verdict — the score is real, and it is
        # the evidence — but the numbers beside it are not measurements, which
        # is what 2 already means. It comes after 1 by choice rather than by
        # necessity: a regression on a binary check beside a collapsed judge is
        # still true, both codes stop a pipeline, and the headline has already
        # put the calibration clause first. (ADR 0024 §4.5)
        #
        # A drifted pin joins them, and for the reason that chose 2 over 1: a
        # redacted comparison answers `unknown`, `Comparison.artifacts_changed`
        # already refuses to read that as a change, and returning 1 would have
        # this function assert what the layer below will not. `2` already means
        # *the numbers beside this are not what they look like*, which is true
        # here — the system that produced them is not the system the reference
        # approved. A regression still outranks it: both stop the pipeline and
        # the sentence names both, so ordering the quieter one first would only
        # hide the louder. (ADR 0029 §6)
        return EXIT_UNJUDGED
    return EXIT_OK
