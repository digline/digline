"""ADR 0002 §8 lists the promotion conditions, and this holds the list to the code.

§8 is where the conditions are collected, and each one is added by the record
that decides it. Twice, nobody came back to add a new one to §8. On 2026-09-22
the section said *three* while the code refused on more, and its amendment named
the cause: *"each by the record that decided it, and none came back to say so
here"*. That amendment removed the count from the heading and left the cause in
place. On 2026-09-24 conditions 7 and 8 arrived and did not come back either
(#437).

**What this compares, and why not the types alone.** The copy that did stay in
step is the numbered list in `ResultStore.promote_baseline`'s docstring, because
it sits beside the code a new condition changes. So §8 is held equal to that
list, **number for number and type for type**. The numbers matter because a
condition can reuse a type: 6 raises `ErroredRunError` like 3, and the second
amendment of 2026-09-22 records that anyone counting types *"finds five and
stops"*. A comparison of type sets would have been blind to the same condition.
It would also have been blind to the two conditions that were missing, because
`PromotionRefusal` covers only the five that `refusals_for` answers. 7 belongs
to `read_run` and 8 to each backend's write, and neither is in the union.

**The anchor in the code.** Every type in `PromotionRefusal`, and the type
`refusal_for_a_moved_baseline` returns, must appear in the list. A condition
that brings a new type into either one turns this file red until both lists
name it.

**What it cannot see.** This is the limit of the test, stated where the test is:

- A condition added to the code with a type the list already names, if nobody
  adds it to the protocol's list either. That is a second `ErroredRunError` in
  `refusals_for`, say, or a third refusal in `read_run` raising
  `TenantMismatchError`. The test then compares two lists that agree with each
  other and are both short.
- The refusals of `read_run`, 1 and 7. No declared type collects them, so
  nothing here anchors them to the code: a new one with a new type is caught
  only if somebody writes it into the protocol's list.
- A condition removed from the code while both lists still name it.

What it does hold: the drift #437 found, where the protocol's list grew and §8
did not.
"""

from __future__ import annotations

import inspect
import re
import typing
from pathlib import Path

from digline.store import PromotionRefusal, ResultStore
from digline.store.promotion import refusal_for_a_moved_baseline

ROOT = Path(__file__).resolve().parents[1]
ADR_0002 = ROOT / "docs" / "adr" / "0002-three-worlds-and-where-the-data-lives.md"

#: An item of §8: `7. **`SuiteMismatchError`** — ...`. Item 6 reads
#: `6. **`ErroredRunError`, for a run ...`, so the type is matched up to its
#: closing backtick and no further.
_ADR_ITEM = re.compile(r"^(\d+)\. \*\*`(\w+)`", re.MULTILINE)

#: An item of the protocol's list: `7. `SuiteMismatchError`, raised with 1 ...`.
#: `inspect.getdoc` strips the common indentation, so an item starts its line.
_PROTOCOL_ITEM = re.compile(r"^(\d+)\. `(\w+)`", re.MULTILINE)


def section_8() -> str:
    """§8 of ADR 0002, from its heading to the next one."""
    text = ADR_0002.read_text(encoding="utf-8")
    start = text.index("### 8. Promotion's conditions")
    end = text.index("\n### ", start + 1)
    return text[start:end]


def adr_list() -> list[tuple[int, str]]:
    """§8's conditions as (number, type), in the order the section gives them."""
    return [(int(n), name) for n, name in _ADR_ITEM.findall(section_8())]


def protocol_list() -> list[tuple[int, str]]:
    """The same, from `ResultStore.promote_baseline`'s docstring."""
    doc = inspect.getdoc(ResultStore.promote_baseline) or ""
    return [(int(n), name) for n, name in _PROTOCOL_ITEM.findall(doc)]


def types_the_code_declares() -> set[str]:
    """The refusal types the code collects: `PromotionRefusal`'s members, and
    what `refusal_for_a_moved_baseline` returns other than `None`.

    `__value__` is what a `type X = ...` statement binds: the union itself,
    which `typing.get_args` takes apart. The return annotation is read through
    `get_type_hints` because this repository writes `from __future__ import
    annotations`, which leaves every annotation a string until it is resolved.
    """
    members: tuple[type, ...] = typing.get_args(PromotionRefusal.__value__)
    returned = typing.get_type_hints(refusal_for_a_moved_baseline)["return"]
    moved: tuple[type, ...] = typing.get_args(returned)
    return {t.__name__ for t in (*members, *moved) if t is not type(None)}


def test_the_two_lists_are_found() -> None:
    """A guard on the guard: two empty lists are equal, and would prove
    nothing. Both have to start at 1 and count up without a gap."""
    for found in (adr_list(), protocol_list()):
        numbers = [n for n, _ in found]
        assert numbers == list(range(1, len(numbers) + 1)), found
        assert len(numbers) >= 8, found


def test_section_8_names_every_condition_the_protocol_does() -> None:
    """§8 against the protocol's list, number for number and type for type."""
    assert adr_list() == protocol_list(), (
        "ADR 0002 §8 and ResultStore.promote_baseline's docstring list the "
        "promotion conditions differently. A condition added to the code "
        "belongs in both, with the same number and the same type: §8 is "
        "where the conditions are collected, and the record that adds one "
        "does not come back to it on its own (#437)."
    )


def test_every_refusal_type_the_code_declares_is_listed() -> None:
    """The anchor: a type in `PromotionRefusal`, or the type condition 8
    returns, that neither list names is a condition nobody wrote down."""
    listed = {name for _, name in protocol_list()}
    missing = sorted(types_the_code_declares() - listed)
    assert not missing, (
        f"{', '.join(missing)} can refuse a promotion and is not in "
        "ResultStore.promote_baseline's list of conditions. Add the condition "
        "there and to ADR 0002 §8, under the same number."
    )
