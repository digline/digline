"""The one exception the CLI raises at its own users.

Its own module because both loaders raise it and one of them imports the
other: `loader.py` dispatches on the extension and hands a `.toml` to
`toml_suite.py`, which has to be able to say "this file is wrong" without
importing the module that called it.
"""

from __future__ import annotations

__all__ = ["UsageError"]


class UsageError(Exception):
    """Something the caller can fix by typing a different command, or by
    editing the file they named."""
