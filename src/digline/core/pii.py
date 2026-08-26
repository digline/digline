"""Patterns for the identifiers that must not appear in an output.

Two rules shape everything here.

**A pattern with a checksum verifies it.** Without the check, any eleven digits
are a VAT number and any twenty-seven characters starting with two letters are
an IBAN — an assertion that cries wolf gets switched off, and an assertion that
is switched off protects nothing. `iban`, `codice_fiscale` and `partita_iva`
therefore carry a `verify`, and only a candidate that passes it is counted.

**Not all patterns are equally certain, and the count has to say so.** `email`
and `phone_it` have no checksum to verify: an email-shaped string is an email,
but a run of digits that looks like an Italian phone number is often an order
number, a date or a price. Read `pii_email` and `pii_phone_it` as "worth
looking at", and `pii_iban`, `pii_codice_fiscale` and `pii_partita_iva` as
"found one".

Whitespace is tolerated *inside* the patterns rather than stripped from the
text. Stripping would catch `IT60 X054 …` and also weld neighbouring words into
identifiers that were never written; tolerating it inside the pattern catches
the same real thing without inventing anything.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = [
    "ITALIAN_PII",
    "PiiPattern",
    "verify_codice_fiscale",
    "verify_iban",
    "verify_partita_iva",
]


@dataclass(frozen=True, slots=True)
class PiiPattern:
    """One kind of identifier: a name, a regular expression, and optionally the
    check that separates a real one from a coincidence.

    `verify` receives the matched text exactly as it appeared, spaces included,
    and decides whether it counts. `None` means the shape is the whole evidence,
    which is the honest thing to say for an email address.
    """

    name: str
    pattern: str
    verify: Callable[[str], bool] | None = None
    #: Compiled once at construction rather than on every case. It reaches
    #: `identity` as the constant `<Pattern>` — `canonical` renders an
    #: unrecognised object as its type name — so what actually distinguishes two
    #: patterns is `name` and `pattern`, which is right.
    compiled: re.Pattern[str] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PiiPattern.name must not be empty")
        try:
            compiled = re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(
                f"PiiPattern {self.name!r} does not compile: {exc}"
            ) from exc
        object.__setattr__(self, "compiled", compiled)

    def count(self, text: str) -> int:
        """How many real occurrences are in `text`.

        Returns a count and never the matches: what was found is payload, and a
        function that returned it would be the obvious place to accidentally put
        it in a reason.
        """
        found = self.compiled.findall(text)
        if self.verify is None:
            return len(found)
        return sum(1 for m in found if self.verify(m))


def _compact(value: str) -> str:
    return "".join(value.split()).upper()


def verify_iban(candidate: str) -> bool:
    """The ISO 13616 mod-97 check: rotate the first four characters to the end,
    replace each letter by its position plus nine, and the whole number must be
    congruent to 1 modulo 97.

    `int()` on a string of that length is fine in Python — integers are
    arbitrary precision — so the textbook digit-by-digit remainder loop is not
    needed here.
    """
    value = _compact(candidate)
    if not (15 <= len(value) <= 34) or not value[:2].isalpha():
        return False
    rotated = value[4:] + value[:4]
    digits = ""
    for char in rotated:
        if char.isdigit():
            digits += char
        elif "A" <= char <= "Z":
            digits += str(ord(char) - ord("A") + 10)
        else:
            return False
    return int(digits) % 97 == 1


#: The two alternating tables of the codice fiscale check character. Odd
#: positions (counting from one) are weighted differently from even ones, which
#: is what lets the algorithm catch a transposition of two adjacent characters —
#: the most common typing mistake, and the one a plain sum would miss.
_CF_EVEN = {c: i for i, c in enumerate("0123456789")} | {
    c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
}
_CF_ODD_VALUES = (1, 0, 5, 7, 9, 13, 15, 17, 19, 21)
_CF_ODD_LETTERS = (
    1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11,
    3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23,
)  # fmt: skip
_CF_ODD = {c: _CF_ODD_VALUES[i] for i, c in enumerate("0123456789")} | {
    c: _CF_ODD_LETTERS[i] for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
}


def verify_codice_fiscale(candidate: str) -> bool:
    """The check character: sixteenth position, derived from the first fifteen."""
    value = _compact(candidate)
    if len(value) != 16 or not value.isalnum():
        return False
    total = 0
    for i, char in enumerate(value[:15]):
        table = _CF_ODD if i % 2 == 0 else _CF_EVEN  # position 1 is index 0
        if char not in table:
            return False
        total += table[char]
    return value[15] == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[total % 26]


def verify_partita_iva(candidate: str) -> bool:
    """The Luhn check on eleven digits.

    Without it every eleven-digit run is a VAT number: an invoice total in
    cents, an order reference, a timestamp in milliseconds. The check rejects
    about nine out of ten of them.

    The `IT` prefix is stripped first: the pattern accepts it because that is
    how a VAT number appears on an invoice, and the checksum is over the digits.
    """
    value = _compact(candidate)
    if value.startswith("IT"):
        value = value[2:]
    if len(value) != 11 or not value.isdigit():
        return False
    total = 0
    for i, char in enumerate(value[:10]):
        digit = int(char)
        if i % 2 == 0:
            total += digit
        else:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
    return int(value[10]) == (10 - total % 10) % 10


#: An IBAN with single spaces tolerated between characters. The upper bound is
#: the ISO maximum of 34; `verify_iban` does the rest.
_IBAN = r"\b[A-Z]{2}[ ]?\d{2}(?:[ ]?[A-Z0-9]){11,30}\b"

#: A codice fiscale is never written spaced, so no tolerance is granted here:
#: allowing it would turn any sixteen alphanumerics into a candidate.
_CODICE_FISCALE = r"\b[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]\b"

#: Eleven digits, optionally spaced in the 4-3-4 grouping banks use, and
#: optionally prefixed by the country code as it appears on an invoice.
_PARTITA_IVA = r"\b(?:IT[ ]?)?\d{4}[ ]?\d{3}[ ]?\d{4}\b"

_EMAIL = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"

#: Italian mobile (3xx) and landline (0xx) numbers, with the separators people
#: actually type. No checksum exists, so this one over-reports by design.
_PHONE_IT = r"(?:\+39[ .-]?)?\b(?:3\d{2}|0\d{1,3})[ .-]?\d{6,8}\b"


ITALIAN_PII: tuple[PiiPattern, ...] = (
    PiiPattern("iban", _IBAN, verify_iban),
    PiiPattern("codice_fiscale", _CODICE_FISCALE, verify_codice_fiscale),
    PiiPattern("partita_iva", _PARTITA_IVA, verify_partita_iva),
    PiiPattern("email", _EMAIL),
    PiiPattern("phone_it", _PHONE_IT),
)
