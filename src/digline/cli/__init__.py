"""The terminal front end: argparse, the printed output, the exit codes.

**One host front end among others**, since ADR 0011 §7. What touches the world —
the clock, git, importing the user's suite, reading the files it declares — is
`digline.host`, which this layer composes with `digline.wire`, the report and
the store. Nothing outside this package imports it: a front end is the top of
the chain, and front ends do not import each other.
"""

from digline.cli.main import build_parser, main

# Re-exported, not defined here: the exit codes and the output version are
# contracts with a program, so they live in `digline.wire` where the second front
# end can reach them without importing a front end (ADR 0011 §6). This keeps
# `from digline.cli import EXIT_OK` working for everything that already does.
from digline.wire import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    OUTPUT_VERSION,
    exit_code,
)

__all__ = [
    "EXIT_OK",
    "EXIT_UNJUDGED",
    "EXIT_USAGE",
    "EXIT_WORSE",
    "OUTPUT_VERSION",
    "build_parser",
    "exit_code",
    "main",
]
