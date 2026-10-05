"""The resolver: a projected document with its names read back from the table.

The mirror of `project`. The projection is handed a minter and turns names into
tokens; this is handed a lookup and turns tokens back into names. Both are
digline's code, called by the process that owns the name table, and neither
learns where the table is or what format it has. (ADR 0036 §2)
"""

from __future__ import annotations

from typing import cast

from digline.core.projection import rename
from digline.core.refused import Quoted
from digline.core.run import Run
from digline.core.tokens import Lookup, TokenKind

__all__ = [
    "DuplicateNameError",
    "IncoherentRowsError",
    "NotProjectedError",
    "NothingResolvedError",
    "UnresolvedConfigError",
    "WrongKindError",
    "WrongRowError",
    "resolve_tokens",
]


class NothingResolvedError(ValueError):
    """The document carries tokens and not one of them has a row: the wrong
    table, since a token has no row in any other. (ADR 0036 §8)"""


class WrongKindError(ValueError):
    """A token's row was minted under another kind than the kind of the place
    the token sits in. (ADR 0036 §3)"""


class WrongRowError(ValueError):
    """The lookup answered a token with a row that is not that token's, or
    that is not a row: a defect in the lookup, which is not read."""


class DuplicateNameError(ValueError):
    """Two tokens of one kind resolve to the same text: the table gives one
    name two rows. The mirror of the projection's refusal of a minter that
    gives one name two tokens. (Delta-pass over 0.25.0, F-3)"""


class IncoherentRowsError(ValueError):
    """Every row resolved, and together they describe no run: a judge's
    identity that is not its `provider/model`, a perimeter key read back in
    clear, an empty model. The rebuilt `Run` refuses them, and this names that
    refusal so a front end translates it. (Delta-pass over 0.25.0, F-2)"""


class NotProjectedError(ValueError):
    """The run is not projected, so it has no tokens to resolve."""


class UnresolvedConfigError(ValueError):
    """A configuration kept a token no row resolves. A configuration is read
    whole or not at all: its checks read `provider` and `model` by their text,
    and half of one would describe no system."""


#: The configuration kinds. A token of one of them that stays unresolved is
#: refused rather than left in place.
_CONFIG_KINDS: frozenset[TokenKind] = frozenset(
    {
        "target_config_key",
        "target_config_value",
        "judge_config_key",
        "judge_config_value",
        "judge_identity",
    }
)


def resolve_tokens(run: Run, lookup: Lookup) -> Run:
    """`run`, projected, with each token replaced by the text of its row.

    It returns a `Run` whose names are text again: `projected` is false, and
    `redacted` stays true, because the projection redacted first and a reason
    does not come back. Given every row, the result is the reference as
    `redact(reference, NOTHING_EXTRA)` would have written it.

    **A token with no row stays where it is**, as the token. Token by token
    nothing is told apart: erased, never minted here, and the wrong table read
    the same (ADR 0036 §8). The document as a whole tells them apart:

    - **tokens present and none resolved** is the wrong table, and is refused
      as `NothingResolvedError`. **No token at all** is an empty document, and
      is read. This fails loud on a legitimate document whose every row was
      erased, which is the direction ADR 0036 §8 chose.

    **Refused, besides:**

    - `NotProjectedError`: the run is not projected, so its names are text and
      not tokens;
    - `WrongKindError`: a row whose kind is not the kind of the place its
      token sits in. Which place carries which kind is `rename`'s map, the one
      the projection writes by (ADR 0036 §3);
    - `WrongRowError`: the lookup returned a row for another token, or
      something that is not a row;
    - `UnresolvedConfigError`: a token in a configuration, key, string value
      or judge identity, has no row. The other kinds stay in place when
      unresolved; a configuration cannot, because it would name no system.
    - `DuplicateNameError`: two tokens of one kind resolve to the same text;
    - `IncoherentRowsError`: the rows resolve, and the run they rebuild
      refuses them, as a judge identity that is not its `provider/model`.

    It writes nothing and knows neither the store nor the table.
    """
    if not run.projected:
        raise NotProjectedError(
            "this run is not projected: its names are text, and there are no "
            "tokens to resolve"
        )
    places: list[tuple[TokenKind, str]] = []

    def collect(kind: TokenKind, token: str) -> str:
        places.append((kind, token))
        return token

    rename(run, collect, projected=True)
    # One question per token, however many places it sits in. A loop rather
    # than a comprehension keyed by token: that one read each token's row once
    # per place and kept the last answer. (Delta-pass over 0.25.0, F-5)
    rows: dict[str, tuple[str, str] | None] = {}
    for _, token in places:
        if token not in rows:
            rows[token] = _read(lookup, token)
    texts: dict[str, str] = {}
    for kind, token in places:
        row = rows[token]
        if row is None:
            continue
        found_kind, text = row
        if found_kind != kind:
            raise WrongKindError(
                f"a token in a {kind} place has a row minted as {found_kind}: "
                "the document or the table was edited, or a writer is wrong, "
                "and reading it would put one kind's text where another's "
                "belongs"
            )
        texts[token] = text
    if rows and not texts:
        raise NothingResolvedError(
            f"none of the {len(rows)} tokens in this document has a row: it is "
            "being read against another tenant's or another suite's table"
        )
    stuck = sorted({k for k, token in places if token not in texts} & _CONFIG_KINDS)
    if stuck:
        raise UnresolvedConfigError(
            f"a configuration keeps a {stuck[0]} token with no row: a "
            "configuration is read whole or not at all, and half of one names "
            "no system"
        )
    names: dict[tuple[TokenKind, str], str] = {}
    for kind, token in places:
        if token not in texts:
            continue
        first = names.setdefault((kind, texts[token]), token)
        if first != token:
            raise DuplicateNameError(
                f"two {kind} tokens resolve to the same text: the table gives "
                "one name two rows, and the document would read two things as "
                "one"
            )
    try:
        return rename(
            run, lambda _kind, token: texts.get(token, token), projected=False
        )
    except ValueError as exc:
        # **A bare `ValueError` is a refusal nobody classified**, the shape
        # `run_from_dict` repairs at its own boundary.
        # The rows passed every check above one by one, and the `Run` built
        # from them refuses what they say together. A typed refusal already
        # carries its name and passes through unchanged.
        if type(exc) is not ValueError:
            raise
        raise IncoherentRowsError(
            Quoted.of(
                exc,
                "the rows resolve one by one and together describe no run: ",
                named=False,
            )
        ) from exc


def _read(lookup: Lookup, token: str) -> tuple[str, str] | None:
    """The kind and text of `token`'s row, or `None`. A row that is not this
    token's, or not a row, is refused."""
    # Held as `object`: the lookup is the owning process's code, and its
    # annotation is a promise this checks rather than trusts.
    row = cast(object, lookup(token))
    if row is None:
        return None
    found = [getattr(row, field, None) for field in ("token", "kind", "text")]
    match found:
        case [str(), str() as kind, str() as text] if found[0] == token:
            return kind, text
        case [str(), str(), str()]:
            raise WrongRowError(
                "the lookup answered a token with the row of another token: "
                "its text would be read in the wrong place"
            )
        case _:
            raise WrongRowError(
                f"the lookup answered a token with a {type(row).__name__}, "
                "which is not a row: a row has a token, a kind and a text, each "
                "a string"
            )
