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
from digline.targets.pricing import Usage

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
