"""A call whose counts were read and whose cost cannot be computed (#569).

ADR 0004 §8. A call that answered can leave digline holding three things
about its cost: priced, counts not recorded (`usage=None`, #629), and **cost
not computable**, which had no word. The plugin refused, and the check or the
case errored over a problem of accounting. `Completion.unpriced` is the word:
the counts stay on the line, the money does not, and `every_cost_known` says
so.
"""

from __future__ import annotations

import pytest

from digline.targets import Completion
from digline.targets.pricing import (
    ModelPrice,
    Pricing,
    UnknownModelError,
    Usage,
    free,
)

COUNTS = Usage(input_tokens=100, output_tokens=10)


# --------------------------------------------------------------------------- #
# The vocabulary: `Completion.unpriced` (§8.2)
# --------------------------------------------------------------------------- #


def test_unpriced_is_none_by_default_and_for_the_pair() -> None:
    """What every plugin written before the field returns."""
    assert Completion(text="yes", usage=COUNTS).unpriced is None


def test_unpriced_with_counts_is_a_sentence_kept_as_given() -> None:
    reply = Completion(text="yes", usage=COUNTS, unpriced="no rate for 'eu'")
    assert reply.unpriced == "no rate for 'eu'"
    assert reply.usage == COUNTS


def test_unpriced_with_no_counts_is_refused() -> None:
    """Counts not recorded already say the cost is not known."""
    with pytest.raises(ValueError, match="usage=None"):
        Completion(text="yes", usage=None, unpriced="no rate for 'eu'")


@pytest.mark.parametrize("sentence", ["", "   "])
def test_an_empty_sentence_is_refused(sentence: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        Completion(text="yes", usage=COUNTS, unpriced=sentence)


# --------------------------------------------------------------------------- #
# The predicate: `Pricing.why_unpriced`, and its default (§8.4)
# --------------------------------------------------------------------------- #

NO_CACHE_RATES = Pricing(per_model={"m-1": ModelPrice(1.0, 2.0)})
CACHED_READS = Usage(input_tokens=100, output_tokens=10, cache_read_tokens=50)
CACHE_WRITES = Usage(input_tokens=100, output_tokens=10, cache_write_tokens=40)


@pytest.mark.parametrize(
    ("usage", "kind", "count"),
    [(CACHED_READS, "cached-read", 50), (CACHE_WRITES, "cache-write", 40)],
)
def test_the_default_answers_for_a_rate_the_list_lacks(
    usage: Usage, kind: str, count: int
) -> None:
    sentence = NO_CACHE_RATES.why_unpriced("m-1", usage)
    assert sentence is not None
    assert f"used {count} {kind} tokens" in sentence
    assert f"declares no {kind} rate" in sentence


def test_cost_still_raises_where_the_predicate_has_a_sentence() -> None:
    """A caller that does not ask first gets no number nobody stated."""
    with pytest.raises(UnknownModelError, match="cached-read"):
        NO_CACHE_RATES.cost("m-1", CACHED_READS)


def test_a_rate_the_list_has_is_priced_and_the_predicate_is_silent() -> None:
    """The control: with the rate, a figure."""
    priced = NO_CACHE_RATES.override("m-1", ModelPrice(1.0, 2.0, 0.1))
    assert priced.why_unpriced("m-1", CACHED_READS) is None
    assert priced.cost("m-1", CACHED_READS) == pytest.approx(0.000125)


def test_an_unknown_model_is_not_unpriced_and_cost_refuses_it() -> None:
    """The reason for a predicate: `UnknownModelError` covers this too, and a
    typo in a model's name is not *cost not known*."""
    assert NO_CACHE_RATES.why_unpriced("m-typo", CACHED_READS) is None
    with pytest.raises(UnknownModelError, match="no price"):
        NO_CACHE_RATES.cost("m-typo", CACHED_READS)


def test_a_list_the_user_built_inherits_the_default() -> None:
    """A user enters by doing nothing: `override` and `free` give the base
    class, and so does `Pricing(...)`."""
    theirs = Pricing(per_model={}).override("theirs", ModelPrice(1.0, 2.0))
    assert theirs.why_unpriced("theirs", CACHED_READS) is not None
    assert free("hosted").why_unpriced("hosted", CACHED_READS) is None
