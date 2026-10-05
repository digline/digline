"""The version of the machine surface, and the exit codes it reports.

Both are contracts with a program rather than with a person, which is why they
live here and not in a front end. `digline.cli` re-exports every name in this
module, so `from digline.cli import EXIT_OK, OUTPUT_VERSION` keeps working.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal, get_args

from digline.core import Outcome, Run, scale_lost
from digline.report import Headline, unjudged_cases
from digline.report.log import EXCLUSIONS, SPREAD_ABSENCES

__all__ = [
    "EXIT_OK",
    "EXIT_UNJUDGED",
    "EXIT_USAGE",
    "EXIT_WORSE",
    "OUTPUT_VERSION",
    "exit_code",
    "run_exit_code",
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
#:    `misnamed` on the headline, and `misnamed` as a tally kind on
#:    `explain --json`: added keys, under the same rule. It moves no exit code
#:    of its own, for `unreconciled`'s reason: each refused verdict is already
#:    errored and exits 2 through that. A run whose assertions name their
#:    verdicts after themselves, which is every run of a shipped assertion,
#:    reads `0` here and never meets the kind. (ADR 0027 §6, amended
#:    2026-09-28)
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
#:    `unread_on_record` on each span and each roll of `log --json`, and
#:    `on_record_not_read` beside `skipped` and `unreadable`: added keys, under
#:    the rule every added key above follows, so no bump. The runs the baseline
#:    or the register name that the scan did not read. A missing run folded
#:    away, joining spans and erasing rolls, and nothing said so. `0` and `[]`
#:    are what a store where every run named is read has always meant. They do
#:    **not** mean nothing is missing: a run neither artifact names leaves no
#:    trace. They move no exit code. `log` has none that depends on its
#:    reading. (#287)
#:
#:    `refused` on `log --json` and on MCP's `list_runs`, and
#:    `baseline_unreadable` on `list_runs`: added keys, under the same rule, so
#:    no bump. `refused` counts the runs the scan found and the store refused to
#:    read; `baseline_unreadable` says that `baseline_key: null` is a baseline
#:    that could not be read and not a suite with none. Wherever either would
#:    have been non-zero, the reading used to fail whole, so no consumer has
#:    ever parsed a response where these were anything but `0` and `false`.
#:    What does change is that a response now arrives where an error used to.
#:    (#314)
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
#:
#: *Since 2026-10-02 (#312), the paragraph above kept as written:* when you add
#: a key, the record is an entry in `_ADDED` at the end of this module, and a
#: test refuses the key until it is there. A paragraph here may still say why.
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
#: Not a verdict either, and `exit_code()` never returns it: a failure nobody
#: anticipated, which is not a fact about the suite. Before ADR 0041 it was 1,
#: Python's default, which read as "worse" from a gate that measured nothing
#: and from a reading that never gates. It is `EX_SOFTWARE` in `sysexits.h`,
#: beside 64's `EX_USAGE`, and that pairing is a choice: nothing here declared
#: 64 a `sysexits.h` value before. (ADR 0041)
EXIT_INTERNAL = 70


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
    outcome. **That sentence is the whole of the rule, and it was never
    deliberated.** It arrived with the first commit (`ae4a2af`), no ADR rules on
    it, and ADR 0013 builds on it without examining it. What it justifies is one
    suspension among judged cases. A run in which every case is suspended is a
    state no single suspension decided, and what that run should exit is open
    on #360.

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


def run_exit_code(run: Run) -> int:
    """The exit code of a run with nothing to compare it against: a first
    round, before any baseline.

    **`exit_code`'s rule, restricted to what a lone run can say.** `1` needs a
    relation: a check got worse, a canary moved, a pin drifted from the
    reference. None of these has a meaning without a reference, so this
    never returns `1`. What remains is `2`, for a case that could not be judged
    or a calibration case outside its band. Both are read from the run alone,
    by the same two functions `headline()` reads them with.

    **One function, so the rule has one place.** It was written inline twice,
    behind `digline report` and `digline explain`. The two copies agreed only
    because neither had moved yet (#318). `tests/test_run_exit_code.py` holds
    it to `exit_code`: for any run, this equals `exit_code` of the run compared
    with itself, which is the comparison with no relation in it.
    """
    if unjudged_cases(run) or scale_lost(run):
        return EXIT_UNJUDGED
    return EXIT_OK


# --------------------------------------------------------------------------- #
# The shape of every document this package builds, as a table a test reads
# --------------------------------------------------------------------------- #
#
# The record above is prose, and no test can read it. What follows is the same
# contract in a form one can: every object the builders in this package emit,
# named, with each key and the JSON types its value may take.
# `tests/test_wire_keys.py` builds every document from fixtures that reach
# every branch, walks it against this table, and fails on a key the table does
# not name, on a key it names and the document lacks, and on a value of a type
# it does not allow. It also fails on a shape or an optional key no fixture
# reached, so no pin here goes vacuous. (#312)
#
# **What this table does not hold: a key a front end splices beside a
# document.** It types what the builders in this package emit, and that is
# not every response `digline-mcp` returns. Its `explain`, `get_run` and
# `get_baseline` tools return a builder's document with the run's `key` added
# beside it. That key is pinned elsewhere: by name, in `digline-mcp`'s
# `SPLICE_ALLOWED`, and by its tool tests. Nothing here moves if it does.
# Measured in the release that shipped this table: renamed in the server, the
# key left this table's test green and failed four of `digline-mcp`'s.
#
# **Two parts, so that an addition and a change cannot look alike.** `_BASE` is
# the shape as it stood when this table was written, under `OUTPUT_VERSION = 2`,
# and it does not move: `_BASE_DIGEST` holds its digest beside the version, and
# the test fails when the two disagree. `_ADDED` is where every key added since
# goes, one entry each, and `_SHAPES` is derived from the two. So:
#
# - **adding a key** is one entry in `_ADDED`, naming why. That is what
#   `OUTPUT_VERSION = 2`'s rule allows without a bump, and a release diffs
#   `_ADDED` between two tags to list what it added (`RELEASING.md`);
# - **adding a word to a map's closed key vocabulary** is one entry in
#   `_ADDED_WORDS`, naming why, under the same rule. A consumer meets a key in a
#   map it did not know, which is what it meets when a key is added to an
#   object. Ruled 2026-10-03: until then the vocabulary was part of the type,
#   and a new word moved `_BASE` (#402; ADR 0024 §7.5, amended 2026-10-03);
# - **renaming or removing a key, or changing what type a value may take**, is
#   an edit to `_BASE` or to an existing `_ADDED` entry. A consumer parsing the
#   old shape breaks, so it is a bump of `OUTPUT_VERSION`: fold `_ADDED` into
#   `_BASE`, empty `_ADDED`, and pin the new digest beside the new version.
#
# **What this does not catch, stated where the claim is made.** A value from a
# vocabulary a consumer matches on, such as an outcome or a kind, moving to
# another word: the type is still a string. A number that changes meaning, like
# the `counts` entries above. Bytes inside a string, like the bump to 2. A type
# a value may take on a branch no fixture reaches: a type listed here and never
# produced is allowed and not demanded. And the digest is a tripwire, not a
# lock: anybody can overwrite it, and the diff between two tags is where that
# is seen.
#
# **This is an enumeration**, which the record above warns against: a list
# kept beside the set it describes goes stale and says nothing. What keeps this
# one from going stale is that the test compares by **equality**. A key the
# builders emit and the table omits is a failure, not a silence, so the table
# cannot fall behind the code without a red.
#
# The prose record above stays as written, as the history up to this table.
# From #312 on, an added key is recorded in `_ADDED`; a paragraph above may
# still say why, and the entry points at it.

#: A JSON value's type, as a parser sees it. `integer` is never a `bool`, which
#: Python counts as one, and `number` is an integer or a float but never a
#: `bool` either: `False == 0` is exactly the confusion this table is for.
#: `any` is a value this table does not type, and only a mapping whose values
#: the suite declares, such as disclosed metadata, uses it.
type _Json = Literal["string", "integer", "number", "boolean", "null", "any"]


@dataclass(frozen=True, slots=True)
class _Obj:
    """An object of a named shape in `_SHAPES`."""

    shape: str


@dataclass(frozen=True, slots=True)
class _Arr:
    """A list whose every item is one of `of`."""

    of: frozenset[_Type]


@dataclass(frozen=True, slots=True)
class _Map:
    """An object whose keys come from the data rather than from the code.

    `keys` is the closed vocabulary they are drawn from, where there is one,
    taken from the module that owns it and never copied here; `None` where the
    set is open, like a path or a name a suite declared. Sparse either way: a
    key that would carry nothing may be absent.
    """

    of: frozenset[_Type]
    keys: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class _OneOf:
    """An object of exactly one of `shapes`, told apart by its keys."""

    shapes: tuple[str, ...]


type _Type = _Json | _Obj | _Arr | _Map | _OneOf


@dataclass(frozen=True, slots=True)
class _Key:
    """One key of a shape: the types its value may take, and whether the key may
    be absent. An optional key is absent on some documents and present on
    others; it is never present and empty in place of absent."""

    types: frozenset[_Type]
    optional: bool = False


@dataclass(frozen=True, slots=True)
class _AddedKey:
    """One key added under the current `OUTPUT_VERSION`, without a bump.

    `ref` names the issue or the ADR that added it. There is no release field:
    the release a key shipped in is the first tag whose `_ADDED` holds it, and a
    field written by hand would add one more line to sweep at every cut.
    """

    shape: str
    key: str
    value: _Key
    ref: str


@dataclass(frozen=True, slots=True)
class _AddedWord:
    """One word added to a map's closed key vocabulary under the current
    `OUTPUT_VERSION`, without a bump. `ref` as on `_AddedKey`.

    The vocabulary is still taken from the module that owns it. `_BASE` reads
    it with these words taken out and `_derive` puts them back, so the owner
    stays the one place a word is written.
    """

    shape: str
    key: str
    word: str
    ref: str


#: Every word added to a map's key vocabulary under `OUTPUT_VERSION = 2`.
#: Appended to, never edited, like `_ADDED`.
_ADDED_WORDS: tuple[_AddedWord, ...] = (
    _AddedWord(
        "log",
        "spread_absence",
        "projected",
        "#402; ADR 0024 §7.5, amended 2026-10-03",
    ),
)


def _as_written(shape: str, key: str, vocabulary: Iterable[str]) -> frozenset[str]:
    """`vocabulary` as `_BASE` was written: without the words added since."""
    added = {w.word for w in _ADDED_WORDS if (w.shape, w.key) == (shape, key)}
    return frozenset(vocabulary) - added


def _k(*types: _Type, optional: bool = False) -> _Key:
    return _Key(frozenset(types), optional)


def _arr(*types: _Type) -> _Arr:
    return _Arr(frozenset(types))


def _map(*types: _Type, keys: frozenset[str] | None = None) -> _Map:
    return _Map(frozenset(types), keys)


_STR = _k("string")
_INT = _k("integer")
_NUM = _k("number")
_BOOL = _k("boolean")
_STR_OR_NULL = _k("string", "null")
_NUM_OR_NULL = _k("number", "null")
_STRINGS = _k(_arr("string"))
#: `ConfigValue` on the wire: what a configuration field, or a setting fact,
#: may hold.
_SCALAR = _k("string", "integer", "number", "boolean", "null")
_COUNTS = _map("integer")

_HEADLINE: Mapping[str, _Key] = {
    "output_version": _INT,
    "worse": _BOOL,
    "unjudged": _INT,
    "suspended": _INT,
    "config_changed": _BOOL,
    "counts": _k(_map("integer", keys=frozenset(get_args(Outcome.__value__)))),
    "reasons_available": _BOOL,
    "sentence": _STR,
    "artifacts_changed": _BOOL,
    "target_config_changed": _BOOL,
    "judge_config_changed": _BOOL,
    "rejudged": _BOOL,
    "canary_moved": _BOOL,
    "pinned_drifted": _BOOL,
    "pinned_unchecked": _INT,
    "target_echoed": _BOOL,
    "on_the_line": _INT,
    "within_noise": _INT,
    "scale_lost": _BOOL,
    "denominator_moved": _INT,
    "unreconciled": _INT,
    "reference_unreconciled": _INT,
    "misnamed": _INT,
    "exit_code": _INT,
    "baseline_key": _STR,
}

_DIFF: Mapping[str, _Key] = {
    "output_version": _INT,
    "tenant": _STR,
    "suite": _STR,
    "runs": _k(_Obj("diff.runs")),
    "counts": _k(_Obj("diff.counts")),
    "systems_differ": _BOOL,
    "artifacts_differ": _BOOL,
    "judges": _STRINGS,
    "sentence": _STR,
}

_VERDICT: Mapping[str, _Key] = {
    "name": _STR,
    "assertion_id": _STR,
    "status": _STR,
    "score": _NUM_OR_NULL,
    "threshold": _NUM,
    "tolerance": _NUM,
}

#: The shape of every document as it stood on 2026-10-02, when this table was
#: written. **It does not move** under `OUTPUT_VERSION = 2`: an added key goes
#: in `_ADDED`, and anything else here is a bump.
_BASE: Mapping[str, Mapping[str, _Key]] = {
    # `compare --json`, and the MCP `compare` tool. (compare.py)
    "compare": _HEADLINE,
    "compare.full": {
        **_HEADLINE,
        "deltas": _k(_arr(_Obj("delta"))),
        "shape": _k(_arr(_Obj("shape"))),
        "target_config_deltas": _k(_arr(_Obj("config_delta"))),
        "judge_config_deltas": _k(_arr(_Obj("config_delta"))),
        "suite_deltas": _k(_arr(_Obj("rule_delta"))),
    },
    "delta": {
        "case_id": _STR,
        "scope": _STR,
        "assertion": _STR,
        "outcome": _STR,
        "before": _NUM_OR_NULL,
        "after": _NUM_OR_NULL,
        "delta": _NUM_OR_NULL,
        "within_noise": _BOOL,
        "noise_min": _NUM_OR_NULL,
        "noise_max": _NUM_OR_NULL,
        "noise_samples": _INT,
        "canary": _BOOL,
        "calibration": _BOOL,
        "denominator_moved": _BOOL,
    },
    "shape": {
        "check": _STR,
        "assertion_id": _STR,
        "run": _k(_Obj("shape.side")),
        "reference": _k(_Obj("shape.side"), "null"),
    },
    "shape.side": {
        "extremes": _INT,
        "scores": _INT,
        "single_claim": _INT,
        "claims_unrecorded": _INT,
        "sample_means": _INT,
    },
    "config_delta": {
        "field": _STR,
        "outcome": _STR,
        "before": _SCALAR,
        "after": _SCALAR,
        "withheld": _BOOL,
    },
    "rule_delta": {
        "rule": _STR,
        "assertion_id": _STR,
        "scope": _STR,
        "outcome": _STR,
        "direction": _STR,
        "field": _STR,
        "before": _NUM_OR_NULL,
        "after": _NUM_OR_NULL,
        "expansion": _STR,
    },
    # `diff --json`. (diff.py)
    "diff": _DIFF,
    "diff.full": {
        **_DIFF,
        "checks": _k(_arr(_Obj("diff.check"))),
        "target_config_deltas": _k(_arr(_Obj("config_delta"))),
    },
    "diff.runs": {"left": _k(_Obj("diff.run")), "right": _k(_Obj("diff.run"))},
    "diff.run": {
        "key": _STR,
        "label": _STR,
        "created_at": _STR,
        "environment": _STR,
    },
    "diff.counts": {
        "total": _INT,
        "differing": _INT,
        "favours_left": _INT,
        "favours_right": _INT,
        "within_tolerance": _INT,
        "only_left": _INT,
        "only_right": _INT,
        "errored": _INT,
        "interval_pairs": _INT,
        "left_exceeds": _INT,
        "right_exceeds": _INT,
    },
    "diff.check": {
        "case_id": _STR,
        "scope": _STR,
        "assertion": _STR,
        "outcome": _STR,
        "favours": _STR,
        "left": _NUM_OR_NULL,
        "right": _NUM_OR_NULL,
        "delta": _NUM_OR_NULL,
        "tolerance": _NUM,
        "flipped": _BOOL,
        "left_interval": _k(_Obj("interval"), "null"),
        "right_interval": _k(_Obj("interval"), "null"),
        "intervals_overlap": _BOOL,
        "intervals_disjoint": _BOOL,
    },
    "interval": {"min": _NUM, "max": _NUM, "samples": _INT},
    # `explain --json`, and the MCP `explain` tool, which adds `key` beside it
    # (above). (explain.py)
    "explain": {
        "output_version": _INT,
        "scope": _STR,
        "exit_code": _INT,
        "facts": _k(_arr(_OneOf(("fact.check", "fact.setting", "fact.tally")))),
    },
    "fact.check": {
        "about": _STR,
        "kind": _STR,
        "scope": _STR,
        "case_id": _STR,
        "assertion": _STR,
        "assertion_id": _STR,
        "before": _NUM_OR_NULL,
        "after": _NUM_OR_NULL,
        "delta": _NUM_OR_NULL,
        "threshold": _NUM_OR_NULL,
        "noise_min": _NUM_OR_NULL,
        "noise_max": _NUM_OR_NULL,
        "noise_samples": _INT,
        "denominator_moved": _BOOL,
    },
    "fact.setting": {
        "about": _STR,
        "kind": _STR,
        "name": _STR,
        "outcome": _STR_OR_NULL,
        "before": _SCALAR,
        "after": _SCALAR,
        "withheld": _BOOL,
        "added": _INT,
        "removed": _INT,
        "direction": _k("string", optional=True),
        "expansion": _k("string", optional=True),
    },
    "fact.tally": {
        "about": _STR,
        "kind": _STR,
        "count": _INT,
        "state": _k("boolean", "null"),
        "shape": _k(_Obj("shape"), optional=True),
    },
    # `log --json`. (log.py)
    "log": {
        "output_version": _INT,
        "tenant": _STR,
        "suite": _STR,
        "window": _k(_Obj("log.window")),
        "runs": _INT,
        "first": _STR_OR_NULL,
        "last": _STR_OR_NULL,
        "spans": _k(_arr(_Obj("log.span"))),
        "rolls": _k(_arr(_Obj("log.roll"))),
        "spread": _k(_arr(_Obj("log.spread"))),
        "spread_absence": _k(
            _map(
                "integer",
                keys=_as_written("log", "spread_absence", SPREAD_ABSENCES),
            )
        ),
        "replays": _k(_arr(_Obj("log.replay"))),
        # Keyed by the schema version a skipped document declared.
        "skipped": _k(_COUNTS),
        "unreadable": _INT,
        "refused": _INT,
        "on_record_not_read": _STRINGS,
        "reference": _k(_Obj("log.reference"), "null"),
        "register": _k(_arr(_Obj("register_entry"))),
        "register_torn": _BOOL,
        "register_unreadable": _BOOL,
    },
    "log.window": {"since": _STR_OR_NULL, "until": _STR_OR_NULL},
    "log.sighting": {
        "provider": _STR,
        "sent": _STRINGS,
        "answered": _STR_OR_NULL,
        "absence": _STR_OR_NULL,
    },
    "log.span": {
        "side": _STR,
        "provider": _STR,
        "sent": _STRINGS,
        "answered": _STR_OR_NULL,
        "absence": _STR_OR_NULL,
        "first_seen": _STR,
        "last_seen": _STR,
        "runs": _INT,
        "environments": _STRINGS,
        "unread_on_record": _INT,
    },
    "log.roll": {
        "side": _STR,
        "provider": _STR,
        "sent": _STR,
        "before": _STR,
        "after": _STR,
        "last_before": _STR,
        "first_after": _STR,
        "silent_between": _INT,
        "unread_on_record": _INT,
    },
    "log.spread": {
        "name": _STR,
        "latest": _NUM,
        "reference": _NUM_OR_NULL,
        "low": _NUM_OR_NULL,
        "high": _NUM_OR_NULL,
        "runs": _INT,
        "excluded": _k(_map("integer", keys=frozenset(EXCLUSIONS))),
        "unidentified": _INT,
        "commits": _INT,
        "versions": _STRINGS,
        "within_run_low": _NUM_OR_NULL,
        "within_run_high": _NUM_OR_NULL,
    },
    "log.replay": {"key": _STR, "created_at": _STR, "source": _STR},
    "log.reference": {
        "key": _STR,
        "created_at": _STR,
        "promoted_at": _STR_OR_NULL,
        "target": _k(_Obj("log.sighting")),
        "judge": _k(_Obj("log.sighting")),
    },
    "register_entry": {
        "recorded_at": _STR,
        "digline_version": _STR,
        "disposition": _STR,
        "run": _k(_Obj("register_entry.run")),
        "baseline": _k(_Obj("register_entry.baseline")),
        "outcome": _k(_Obj("register_entry.outcome")),
        "exit_code": _INT,
    },
    "register_entry.run": {
        "key": _STR,
        "created_at": _STR,
        "config_hash": _STR,
        "environment": _STR,
        "digline_version": _STR,
        "rejudged": _BOOL,
    },
    "register_entry.baseline": {
        "key": _STR,
        "config_hash": _STR,
        "promoted_at": _STR_OR_NULL,
    },
    "register_entry.outcome": {
        "regressed": _INT,
        "improved": _INT,
        "unchanged": _INT,
        "new": _INT,
        "missing": _INT,
        "errored": _INT,
        "unjudged": _INT,
        "suspended": _INT,
        "within_noise": _INT,
        "on_the_line": _INT,
        "worse": _BOOL,
        "canary_moved": _BOOL,
        "config_changed": _BOOL,
        "artifacts_changed": _BOOL,
        "target_config_changed": _BOOL,
        "judge_config_changed": _BOOL,
        "rejudged": _BOOL,
    },
    # `run --json`, `rejudge --json` and the MCP `run` tool. (run.py)
    "run": {
        "output_version": _INT,
        "key": _STR,
        "tenant": _STR,
        "suite": _STR,
        "sentence": _STR,
        "resumed": _BOOL,
        "reused": _INT,
        "judge_reading": _k("string", optional=True),
        "usage": _k(_Obj("usage"), optional=True),
    },
    # The MCP `list_runs` tool. `list` prints no JSON. (run.py)
    "runs": {
        "output_version": _INT,
        "tenant": _STR,
        "suite": _STR,
        "baseline_key": _STR_OR_NULL,
        "runs": _k(_arr(_Obj("runs.row"))),
        "note": _STR,
        "advice": _STRINGS,
        # Keyed by the schema version a skipped document declared.
        "skipped": _k(_COUNTS),
        "unreadable": _INT,
        "refused": _INT,
        "baseline_unreadable": _BOOL,
    },
    "runs.row": {
        "key": _STR,
        "created_at": _STR,
        "environment": _STR,
        "git_commit": _STR_OR_NULL,
        "cases": _INT,
        "digline_version": _STR,
        "aggregate": _k(_arr(_Obj("runs.verdict"))),
    },
    "runs.verdict": _VERDICT,
    # The MCP `get_run` and `get_baseline` tools, which add `key` beside it
    # (above). (run.py)
    "run_document": {
        "output_version": _INT,
        "tenant": _STR,
        "environment": _STR,
        "suite": _STR,
        "config_hash": _STR,
        "created_at": _STR,
        "git_commit": _STR_OR_NULL,
        "digline_version": _STR,
        "promoted_at": _STR,
        "rejudged_from": _STR,
        "results": _k(_arr(_Obj("run_document.case"))),
        "aggregate": _k(_arr(_Obj("run_document.verdict"))),
        "target_config": _k(_Obj("system_config")),
        "judge_config": _k(_Obj("system_config")),
        # Keyed by an artifact's path.
        "artifacts": _k(_map(_OneOf(("artifact.disclosed", "artifact.withheld")))),
        "pinned": _STRINGS,
        "usage": _k(_Obj("usage"), "null"),
        # Keyed by a name the suite disclosed; the values are the suite's.
        "metadata": _k(_map("any")),
        "disclosure": _k(_Obj("disclosure")),
    },
    "run_document.case": {
        "case_id": _STR,
        "suspended": _BOOL,
        "canary": _BOOL,
        "calibration": _k(_Obj("calibration"), "null"),
        "verdicts": _k(_arr(_Obj("run_document.verdict"))),
    },
    "run_document.verdict": {
        **_VERDICT,
        "samples": _k(_arr("number")),
        "sample_min": _NUM_OR_NULL,
        "sample_max": _NUM_OR_NULL,
        "sample_means": _BOOL,
        "judged": _BOOL,
        # Keyed by a metric the suite disclosed; the values are the suite's.
        "metadata": _k(_map("any")),
    },
    "calibration": {"check": _STR, "low": _NUM, "high": _NUM},
    "artifact.disclosed": {"sha": _STR, "text": _STR},
    "artifact.withheld": {"withheld": _BOOL},
    "system_config": {
        # Keyed by a configuration field a target or a judge declared.
        "values": _k(_map("string", "integer", "number", "boolean", "null")),
        "withheld": _STRINGS,
        "identities": _STRINGS,
    },
    "disclosure": {
        "run_metadata": _STRINGS,
        "score_metadata": _STRINGS,
        "artifacts": _BOOL,
    },
    "usage": {"target": _k(_Obj("usage.line")), "judge": _k(_Obj("usage.line"))},
    "usage.line": {
        "calls": _INT,
        "counted": _INT,
        "partial": _BOOL,
        "input_tokens": _INT,
        "output_tokens": _INT,
        "cache_read_tokens": _INT,
        "cache_write_tokens": _INT,
        "thinking_tokens": _k("integer", "null"),
        "spent_usd": _NUM,
    },
}

#: Every key added under `OUTPUT_VERSION = 2` since `_BASE` was written, one
#: entry each. Appended to, never edited: changing an entry's types is a change
#: a consumer can see, and the rule for that is a bump.
_ADDED: tuple[_AddedKey, ...] = (
    # MCP's `list_runs`: the files the scan left out because their name is not
    # their run's key. A count, beside `unreadable` and `refused`. Not on
    # `log --json`, which has `refused` for a run the store refuses: that gap
    # is declared in ADR 0040 §6, not overlooked.
    _AddedKey("runs", "misfiled", _INT, "#332, #429; ADR 0040 §5"),
    # What resolving a run stepped over, `Resolved.note`, which until then only
    # the CLI said, on stderr. A sentence and not its facts, as `runs.note` is:
    # the run it names is by construction one that cannot be read here, and a
    # key in a field of its own invites the `get_run` that fails. Empty when
    # nothing was stepped over, and always for a key typed by hand. On
    # `run_document` it is optional because `get_baseline` resolves nothing.
    _AddedKey("compare", "note", _STR, "#433"),
    _AddedKey("compare.full", "note", _STR, "#433"),
    _AddedKey("diff.run", "note", _STR, "#433"),
    _AddedKey("explain", "note", _STR, "#433"),
    _AddedKey("run_document", "note", _k("string", optional=True), "#433"),
)


def _derive(
    base: Mapping[str, Mapping[str, _Key]],
    added: tuple[_AddedKey, ...],
    words: tuple[_AddedWord, ...] = (),
) -> Mapping[str, Mapping[str, _Key]]:
    shapes = {name: dict(keys) for name, keys in base.items()}
    for entry in added:
        shapes.setdefault(entry.shape, {})[entry.key] = entry.value
    for word in words:
        spec = shapes[word.shape][word.key]
        shapes[word.shape][word.key] = replace(
            spec, types=frozenset(_with_word(t, word.word) for t in spec.types)
        )
    return shapes


def _with_word(value: _Type, word: str) -> _Type:
    if isinstance(value, _Map) and value.keys is not None:
        return _Map(value.of, value.keys | {word})
    return value


#: The contract as it stands: `_BASE` with every `_ADDED` entry in it. Derived,
#: so the two parts above are the only places a key is written.
_SHAPES: Mapping[str, Mapping[str, _Key]] = _derive(_BASE, _ADDED, _ADDED_WORDS)


def _spell(value: _Type) -> str:
    match value:
        case str():
            return value
        case _Obj(shape):
            return f"<{shape}>"
        case _Arr(of):
            return f"[{_spell_all(of)}]"
        case _Map(of, keys):
            vocabulary = "" if keys is None else "|".join(sorted(keys))
            return f"map<{vocabulary}>[{_spell_all(of)}]"
        case _OneOf(shapes):
            return "one of(" + "|".join(f"<{s}>" for s in shapes) + ")"


def _spell_all(types: frozenset[_Type]) -> str:
    return "|".join(sorted(_spell(t) for t in types))


def _lines(shapes: Mapping[str, Mapping[str, _Key]]) -> list[str]:
    """The table as one line per key, in a fixed order: what the digest is taken
    over, and what a failure prints, so the two read the same."""
    return [
        f"{name}.{key}{'?' if spec.optional else ''}: {_spell_all(spec.types)}"
        for name in sorted(shapes)
        for key, spec in sorted(shapes[name].items())
    ]


# Read by `tests/test_wire_keys.py`, and by nothing in this package: the digest
# is a check on the table, not something a builder needs.
def _digest(shapes: Mapping[str, Mapping[str, _Key]]) -> str:  # pyright: ignore[reportUnusedFunction]
    text = "\n".join(_lines(shapes))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: The `OUTPUT_VERSION` `_BASE` belongs to, and `_BASE`'s digest. A test holds
#: both: a `_BASE` that moved under the same version is a rename, a removal or
#: a type change that did not bump.
_BASE_DIGEST: tuple[int, str] = (
    2,
    "6d8ccb58a32a164b0c99fcbc5bfd411c99f0184b5bfd4d27bf9a5f11bbf05835",
)
