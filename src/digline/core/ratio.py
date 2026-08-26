"""Quantities that are really "k out of n", and the decimals that misspell them.

Agreement over `n` samples is `k/n` and nothing else. Written as a decimal it
stops being obviously so, and the two mistakes below both happened inside one
hour of writing a real suite:

- `min_agreement=0.67` for "two out of three". `2/3` is `0.666…`, so `0.67` is
  *above* it: every case with two votes out of three errored, silently and for
  the opposite of the intended reason.
- `tolerance=0.4` for "two out of five". This one worked — but only because
  `2/5` happens to be exact in decimal. It was right by luck.

So the fraction may be written as one: `"2/3"` or `Fraction(2, 3)`. And a float
that lands on no reachable `k/n` is refused at construction with the list of the
ones that exist, because a value that cannot be produced by counting is a value
nobody meant.
"""

from __future__ import annotations

from fractions import Fraction

from digline.core.types import FLOAT_PRECISION

__all__ = ["Ratio", "as_agreement", "as_ratio", "reachable_agreements"]

#: What a "k out of n" quantity may be written as. A plain float still works;
#: the other two forms exist so the intent survives being read six months later.
type Ratio = float | int | str | Fraction


def as_ratio(value: Ratio, *, field: str) -> float:
    """Parse `"2/3"`, `Fraction(2, 3)` or a float into a float."""
    if isinstance(value, str):
        try:
            return float(Fraction(value))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(
                f'{field} is {value!r}, which is not a number or a fraction like "2/3"'
            ) from exc
    return float(value)


def reachable_agreements(samples: int) -> list[Fraction]:
    """Every agreement `k/n` that `samples` samples can actually produce."""
    return [Fraction(k, samples) for k in range(1, samples + 1)]


def as_agreement(value: Ratio, *, samples: int, field: str) -> float:
    """Parse, then refuse anything `samples` samples cannot produce.

    The check applies to every form, not only to floats: `"2/4"` is as
    unreachable with three samples as `0.67` is. What is refused is the *value*,
    not the notation.
    """
    parsed = as_ratio(value, field=field)
    if not (0.0 < parsed <= 1.0):
        raise ValueError(
            f"{field} is {parsed}, which is outside (0, 1]: an agreement is a "
            "fraction of the samples"
        )
    reachable = reachable_agreements(samples)
    rounded = round(parsed, FLOAT_PRECISION)
    if any(round(float(f), FLOAT_PRECISION) == rounded for f in reachable):
        return parsed

    # Rendered as `k/samples`, not as the normalized fraction: with five samples
    # the reachable top is what a reader would write as "5/5", and printing
    # `Fraction(5, 5)` as "1/1" hides that k runs all the way to n.
    options = ", ".join(
        f"{k}/{samples} = {k / samples:.6f}" for k in range(1, samples + 1)
    )
    raise ValueError(
        f"{field} is {parsed:.6f}, which {samples} samples cannot produce: "
        f"agreement is a count of samples, so it is one of {options}. "
        'Write the fraction if that is what you mean, e.g. "2/3".'
    )
