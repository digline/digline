"""Every word `unjudged_causes` can carry is a word the contract names.

`unjudged_causes` is a list of strings on the wire, and its rule is that each
cause is named as the boolean or count beside it on the same document (ADR
0053). Nothing held that: `causes_of_two` could append a word no key on the
document carries, and the table in `digline.wire.contract`, which types the
list as strings, would let it through. True since the pin causes arrived, and
found when #642 added the first word since.

The words are read from the code that produces them, the `causes.append(...)`
calls in `causes_of_two`, rather than from a list kept here: a list written
beside the set it describes goes stale, which is the thing this test exists to
catch.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import get_args

from digline.core import CauseOfTwo, causes_of_two
from digline.report import Headline
from digline.wire.contract import _SHAPES  # pyright: ignore[reportPrivateUsage]


def appended() -> set[str]:
    """The words `causes_of_two`'s body appends, read from its source.

    Every append has to be of a string literal: a word computed at run time is
    one nothing here could read, and is refused rather than skipped.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(causes_of_two)))
    words: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "causes"
        ):
            (argument,) = node.args
            assert isinstance(argument, ast.Constant), ast.unparse(node)
            assert isinstance(argument.value, str), ast.unparse(node)
            words.add(argument.value)
    return words


def test_the_reading_finds_the_causes() -> None:
    """Not an empty set: a reading that found nothing would pass every test
    below."""
    assert "unjudged" in appended()
    assert "unpaired" in appended()


def test_every_cause_is_a_key_of_the_document_it_is_listed_on() -> None:
    """ADR 0053's rule: a cause is named as the key beside it, so a consumer
    who reads `unpaired` in the list finds `unpaired` on the document."""
    for shape in ("compare", "compare.full"):
        keys = set(_SHAPES[shape])
        assert "unjudged_causes" in keys
        missing = appended() - keys
        assert not missing, f"{shape} names no key for {sorted(missing)}"


def test_every_cause_is_a_field_of_the_headline() -> None:
    """The headline is where the document's keys come from."""
    fields = set(Headline.__dataclass_fields__)
    assert appended() <= fields, sorted(appended() - fields)


def test_the_declared_vocabulary_is_the_produced_one() -> None:
    """Both directions between `CauseOfTwo`, the type a consumer of
    `digline.core` reads, and what the function appends: a word declared and
    never produced is a cause nobody can meet, and a word produced and not
    declared is one pyright would refuse and nothing at run time would."""
    assert set(get_args(CauseOfTwo.__value__)) == appended()
