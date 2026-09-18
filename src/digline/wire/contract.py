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
    """
    if head.worse or head.canary_moved:
        # Two facts, one number. A canary that moved says the model behind the
        # alias probably changed, which is a reason to stop whichever direction
        # it moved in — and it is deliberately not folded into `worse`, so the
        # headline can say what happened without saying something untrue about
        # it. (ADR 0016 §5)
        return EXIT_WORSE
    if head.unjudged or head.scale_lost:
        # A lost scale is not an errored verdict — the score is real, and it is
        # the evidence — but the numbers beside it are not measurements, which
        # is what 2 already means. It comes after 1 by choice rather than by
        # necessity: a regression on a binary check beside a collapsed judge is
        # still true, both codes stop a pipeline, and the headline has already
        # put the calibration clause first. (ADR 0024 §4.5)
        return EXIT_UNJUDGED
    return EXIT_OK
