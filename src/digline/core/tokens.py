"""The vocabulary of a projection: the kinds of text a token stands for, the
callable that mints one, and the form a token has.

Here rather than beside `project` because `Run` checks a projected document's
tokens when it is built, and `project` builds a `Run`: the grammar has to sit
below both. Nothing here mints, stores or resolves a token. digline is handed
the callable that does, by the process that owns the name table, and learns
nothing about where the table is. (ADR 0036 §2)
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal, Protocol

__all__ = ["TOKEN_LENGTH", "Lookup", "Minter", "NameRow", "TokenKind", "is_token"]

#: What a token stands for. A value names **what the text is**, and reads on its
#: own in the owning process's table, where there is no document around it.
#:
#: Kinds are separate wherever an equality between two places would tell the
#: software house something it must not have: so configuration is a key kind
#: and a value kind, and target and judge are apart. A judge's identity is a
#: kind of its own because it is built from the judge's `provider` and `model`,
#: and an equal label would decode the value's token. (ADR 0034 §5, ADR 0036 §6)
type TokenKind = Literal[
    "case_id",
    "group",
    "verdict_name",
    "calibration_check",
    "artifact_path",
    "target_config_key",
    "target_config_value",
    "judge_config_key",
    "judge_config_value",
    "judge_identity",
    # An application module a check could not reach (`Run.modules_unchecked`):
    # a name of the application's, which can carry a customer's. (#712)
    "module_name",
]

#: Look-up-or-mint: the token for a (kind, text), minting one if the owning
#: process's table has none. Keyed by both, so equal text in two kinds gets two
#: tokens. It runs inside the process that owns the table, and nothing outside
#: that process may write it. (ADR 0036 §2, §6, §7)
type Minter = Callable[[TokenKind, str], str]


class NameRow(Protocol):
    """A row of the name table, as digline reads it: the token, the kind it
    was minted under, and the text.

    **Structural**: digline builds no row. The owning process's own row type
    satisfies this by having the three, read-only or not, and imports nothing
    to do so. The kind is a `str` rather than a `TokenKind` because the core
    only compares kinds for equality (ADR 0036 §3). The token is here so that
    a lookup which returns another token's row is refused rather than read.
    """

    @property
    def token(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def text(self) -> str: ...


#: The row a token names, or `None` where the table has none: erased, never
#: minted here, or the wrong table, which read the same (ADR 0036 §2, §8). The
#: mirror of `Minter`, handed to `resolve_tokens` by the owning process.
type Lookup = Callable[[str], NameRow | None]

#: 128 random bits in url-safe base64 without padding. (ADR 0036 §5)
TOKEN_LENGTH = 22

_TOKEN = re.compile(rf"[A-Za-z0-9_-]{{{TOKEN_LENGTH}}}")


def is_token(text: str) -> bool:
    """Whether `text` has the form of a token.

    **A check of form, and nothing more.** It cannot tell a token from any
    other 22 characters of the same alphabet: a case id that happens to be one
    passes. Whether a token was minted, and for which text, only the table
    knows. The alphabet has no `[`, `]` or `=`, which is what keeps
    `family[group=…]` parseable with both parts tokenised.
    """
    return _TOKEN.fullmatch(text) is not None
