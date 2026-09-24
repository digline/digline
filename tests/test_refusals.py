"""Every exception class digline defines is classified.

`digline.host.refusals` sorts them into refusals — shown to a reader, exited on
— and everything else. The list only helps if nobody can add a class without
touching it, and that is what this file is for: a refusal type added to the
store and left out of a front end's tuple reached the user as a closed
connection in 0.19.2 (friction 59), and the fix for the next one is to make it
impossible to add silently.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import digline
from digline.host.refusals import NOT_REFUSALS, REFUSALS


def _qualified(kind: type[BaseException]) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def _defined_exceptions() -> dict[str, type[BaseException]]:
    """Every exception class defined in a module under `digline`, by the name of
    the module that defines it — a re-export is the same class, counted once.

    `__main__` modules are skipped: importing one runs the command line.
    """
    found: dict[str, type[BaseException]] = {}
    for info in pkgutil.walk_packages(digline.__path__, "digline."):
        if info.name.rsplit(".", 1)[-1] == "__main__":
            continue
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseException)
                and value.__module__ == info.name
            ):
                found[_qualified(value)] = value
    return found


def test_every_exception_digline_defines_is_classified() -> None:
    unclassified = sorted(
        set(_defined_exceptions())
        - {_qualified(kind) for kind in REFUSALS}
        - set(NOT_REFUSALS)
    )
    assert not unclassified, (
        f"{', '.join(unclassified)} is defined in digline and classified nowhere. "
        "If a reader should see its message, add it to REFUSALS in "
        "digline/host/refusals.py; if it never reaches a front end, add it to "
        "NOT_REFUSALS with the reason. Every front end that catches refusals "
        "catches what that list says, so a class left out of both is one that "
        "reaches somebody as a traceback."
    )


def test_the_walk_sees_every_listed_class() -> None:
    """The control on the test above, which would pass on a walk that found
    nothing. Every class either table names must be one the walk reached —
    and so a name left behind by a class that was renamed or removed fails here
    rather than sitting in the table as a reason about nothing."""
    walked = set(_defined_exceptions())
    listed = {_qualified(kind) for kind in REFUSALS} | set(NOT_REFUSALS)
    assert listed <= walked, sorted(listed - walked)


def test_no_class_is_classified_twice() -> None:
    names = [_qualified(kind) for kind in REFUSALS]
    assert len(names) == len(set(names)), "a refusal is listed twice"
    assert not set(names) & set(NOT_REFUSALS), (
        "a class cannot be both a refusal and not one"
    )
