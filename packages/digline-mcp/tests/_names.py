"""A name table for tests: it mints a token for every (kind, text), remembers
every text it was asked for, and answers a lookup for what it minted.

The texts it remembers are what an answer under `project` must not carry: a
name it minted a token for is a name the projection replaced. (ADR 0054 §7)
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field

from digline.core import TokenKind


@dataclass(frozen=True, slots=True)
class Row:
    token: str
    kind: str
    text: str


@dataclass
class RecordingTable:
    """`mint` and `lookup`, as ADR 0036 §2 hands them, over a dict."""

    rows: dict[str, Row] = field(default_factory=lambda: dict[str, Row]())

    def mint(self, kind: TokenKind, text: str) -> str:
        digest = hashlib.sha256(f"{kind}\0{text}".encode()).digest()
        token = base64.urlsafe_b64encode(digest).decode()[:22]
        self.rows[token] = Row(token, kind, text)
        return token

    def lookup(self, token: str) -> Row | None:
        return self.rows.get(token)

    def texts(self) -> set[str]:
        return {row.text for row in self.rows.values()}
