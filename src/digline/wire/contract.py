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
#:    `exit_code` joins the headline under the same rule (ADR 0011 §4). It is
#:    the number `AGENTS.md` §6 calls the contract, and it is a *field* because
#:    an MCP tool has no process to exit; it is on `compare --json` as well so
#:    that the two surfaces cannot answer differently. `diff` gains nothing of
#:    the kind and must not: it has no verdict to carry.
OUTPUT_VERSION = 1

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

    Precedence is deliberate: **a regression outranks an unjudged case.** Both
    need attention, but a regression is a statement about behaviour that got
    worse, while an unjudged case is a statement about the harness. When both
    are true the louder fact must be the one the pipeline reports, or a real
    regression would hide behind a flaky provider.

    A suspension never fails: it is a decision someone already made, not an
    outcome.
    """
    if head.worse:
        return EXIT_WORSE
    if head.unjudged:
        return EXIT_UNJUDGED
    return EXIT_OK
