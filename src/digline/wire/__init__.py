"""The machine surface: the same facts as the report, rendered for a program.

`digline.report` is the document for world 3, written for a person who did not
choose English. This is the other recipient. One subject, two renderings — and
**one** rendering per recipient, which is the whole reason this package exists:
every `--json` the CLI prints and every response the MCP server returns is built
by a function in here, so two front ends cannot drift into two answers.

It is the one place where fixed decision 9's boundary is a function you can
point at. Nothing in here emits a `Verdict.reason`, a suspension reason, or
metadata a `Disclosure` does not cover — a reason is payload, and the far side
of this boundary is a CI log or a model's context.

Pure, like the report: no I/O, no clock, held to it by
`tests/test_layering.py`. (ADR 0011 §6)
"""

from digline.wire.compare import compare_json, config_json, delta_json
from digline.wire.contract import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    OUTPUT_VERSION,
    exit_code,
)
from digline.wire.diff import check_json, diff_json, interval_json
from digline.wire.run import run_json

__all__ = [
    "EXIT_OK",
    "EXIT_UNJUDGED",
    "EXIT_USAGE",
    "EXIT_WORSE",
    "OUTPUT_VERSION",
    "check_json",
    "compare_json",
    "config_json",
    "delta_json",
    "diff_json",
    "exit_code",
    "interval_json",
    "run_json",
]
