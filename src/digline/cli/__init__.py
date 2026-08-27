"""The command line. The last layer, and the only one that touches the world.

It reads the clock and asks git; everything below receives those as values.
"""

from digline.cli.main import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    OUTPUT_VERSION,
    build_parser,
    exit_code,
    main,
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
