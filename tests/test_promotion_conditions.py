"""Condition 8 is an obligation no signature states, so a walk states it.

`promote_baseline`'s conditions live in three places (see
`digline/store/promotion.py`): the reading answers 1 and 7, `refusals_for`
answers the ones that follow from the document, and **8 is left to each
backend, beside its own write** — because it asks what the store holds now, and
a parameter carrying that answer in would hide the window ADR 0031 leaves open
rather than close it.

The cost of that shape is that a backend can simply omit 8 and nothing catches
it: the pure function is silent about it by construction, and the type checker
cannot see a missing refusal. The protocol states the obligation in prose. This
file is the half that fails out loud, and the precedent is
`tests/test_refusals.py`: *"the list is not the guard. `tests/test_refusals.py`
is"*.

**What it reaches, stated rather than discovered.** The walk covers classes
defined under `digline`. A backend published as a separate distribution is out
of its reach, and so is one written by somebody else entirely — no device in
this repository can hold those, which is the same footing ADR 0034 §12 ruled
for the digests. What it does hold is every store this repository grows,
starting with the production store ADR 0002 §6 plans.

**The delete has the same gap, and is walked here too.** `delete_run` reads the
baseline in its plan and refuses the run it rests on, with
`refusal_for_a_promoted_run`, which returns the refusal rather than raising it
for condition 8's reason. The walk below holds it the same way. (ADR 0044 §7)
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import textwrap

import digline
from digline.core import Run
from digline.store import FileResultStore, RunRef
from digline.store.deletion import refusal_for_a_promoted_run
from digline.store.promotion import refusal_for_a_moved_baseline, refusals_for

#: A run for the two fixtures below to pass. They are read as source and never
#: executed, but they are type-checked like everything else here, so the call
#: they carry has to be the real one.
_ANY_RUN = Run(
    tenant="t",
    environment="dev",
    suite="s",
    config_hash="h",
    created_at="2026-01-01T00:00:00+00:00",
)

#: The name a class must reach to have met condition 8, and the name of the
#: function that writes its sentence.
CONDITION_8 = refusal_for_a_moved_baseline.__name__

#: The function that answers the conditions that follow from the document, for
#: the same reason.
DOCUMENT_CONDITIONS = refusals_for.__name__

#: The delete's refusal about the baseline, which has condition 8's shape and
#: its gap: it asks what the store holds now, so each backend reads the
#: baseline itself, and a backend can omit it with nothing noticing.
#: (ADR 0044 §7)
DELETE_REFUSAL = refusal_for_a_promoted_run.__name__


def _promoting_classes(method: str = "promote_baseline") -> dict[str, type[object]]:
    """Every class defined under `digline` that implements `method`,
    `promote_baseline` unless another is named.

    A `Protocol` is skipped: it *declares* the method, which is how the
    obligation is written down, not a place the obligation is met.
    `__main__` modules are skipped because importing one runs a command line.
    """
    found: dict[str, type[object]] = {}
    for info in pkgutil.walk_packages(digline.__path__, "digline."):
        if info.name.rsplit(".", 1)[-1] == "__main__":
            continue
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if (
                inspect.isclass(value)
                and value.__module__ == info.name
                and method in vars(value)
                and not getattr(value, "_is_protocol", False)
            ):
                found[f"{info.name}.{value.__qualname__}"] = value
    return found


def _reaches(cls: type[object], target: str, method: str = "promote_baseline") -> bool:
    """Whether `method` can reach `target`, following `self.…` calls within the
    class.

    **Not a text search over the class**, and the difference is the whole
    guard: `FileResultStore` calls the helper from a private method, so a class
    that kept that method and stopped calling it would satisfy a text search
    while promoting without condition 8. That mutation passed against the first
    version of this file, and this is what replaced it. It is held by
    `test_a_helper_that_is_kept_and_never_called_is_not_reached`, not by this
    sentence: a defect a docstring records is one nothing stops anybody from
    putting back.

    Reached through `getattr` it does not see — as `tests/test_plugin_floors.py`
    says of the same dodge, code written to be invisible to a check built to
    catch it is the worst remedy on the table, and the answer there holds here.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    classdef = tree.body[0]
    assert isinstance(classdef, ast.ClassDef)
    methods = {
        node.name: node
        for node in classdef.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    seen: set[str] = set()
    stack = [method]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        node = methods.get(name)
        if node is None:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id == target:
                return True
            if isinstance(sub, ast.Attribute):
                if sub.attr == target:
                    return True
                if isinstance(sub.value, ast.Name) and sub.value.id == "self":
                    stack.append(sub.attr)
    return False


def _raises(cls: type[object], target: str) -> bool:
    """Whether the value `target` returns reaches a `raise`.

    **Reaching the call is not meeting the condition**, and the difference is
    what this function adds to `_reaches`. `refusal_for_a_moved_baseline`
    *returns* a refusal rather than raising one — deliberately, so a backend can
    read the baseline inside its own lock — so a class that calls it and drops
    the answer promotes over a moved baseline while satisfying every walk that
    only asks whether the name was reached. The mutation is two characters
    (`raise moved` → `pass`), it passed this file's first version 4/4, and
    `_CallsTheHelperAndDropsIt` below keeps it.

    Same method, on purpose. The refusal is returned, so the read, the question
    and the raise belong in one place — inside whatever makes the write atomic.
    A backend that returns it further up is free to, and will fail here: the
    remedy is to raise it where it is asked for, which is what the protocol
    already says.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    classdef = tree.body[0]
    assert isinstance(classdef, ast.ClassDef)
    for node in ast.walk(classdef):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        bound = {
            name.id
            for sub in ast.walk(node)
            if isinstance(sub, ast.Assign | ast.NamedExpr)
            and isinstance(value := getattr(sub, "value", None), ast.Call)
            and _calls(value, target)
            for name in _bound_names(sub)
        }
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Raise) or sub.exc is None:
                continue
            if isinstance(sub.exc, ast.Name) and sub.exc.id in bound:
                return True
            if isinstance(sub.exc, ast.Call) and _calls(sub.exc, target):
                return True
    return False


def _calls(call: ast.Call, target: str) -> bool:
    """Whether this call names `target`, plainly or through an attribute."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == target
    return isinstance(func, ast.Attribute) and func.attr == target


def _bound_names(node: ast.Assign | ast.NamedExpr) -> list[ast.Name]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t for t in targets if isinstance(t, ast.Name)]


def test_every_store_that_promotes_raises_condition_8() -> None:
    """A class that promotes and never *raises* what
    `refusal_for_a_moved_baseline` returns has skipped the one condition the
    pure function cannot carry for it. Reaching the call is not enough: it
    returns the refusal rather than raising it."""
    missing = sorted(
        name
        for name, cls in _promoting_classes().items()
        if not (_reaches(cls, CONDITION_8) and _raises(cls, CONDITION_8))
    )
    assert not missing, (
        f"{', '.join(missing)} implements promote_baseline without raising what "
        f"{CONDITION_8} returns. Condition 8 — the baseline present is not the "
        "one the run was compared against — is the one condition left to each "
        "backend, beside its own write.\n\n"
        "**How much else checks it depends on which backend you are**, and both "
        "halves matter when you are deciding how much care this needs. For "
        "`FileResultStore`, the store this repository has, "
        "`tests/test_promote_replacing.py` checks the behaviour too: the "
        "mutation that drops the raise reddens five of its tests. For any "
        "*other* backend — the production store ADR 0002 §6 plans, or one "
        "somebody else writes — nothing else checks it at all, and this test is "
        "the only thing that will ever reach you. It is written for the second "
        "case, which is why it does not lean on the first.\n\n"
        "Read the baseline inside whatever makes your write atomic, pass it to "
        f"{CONDITION_8}, and raise what it gives you; see "
        "ResultStore.promote_baseline."
    )


def test_every_store_that_promotes_reaches_the_document_conditions() -> None:
    """The same for 2 to 6 and 9, where the failure is quieter: a backend that
    restates them has a second copy to keep in step with this one, and the
    protocol's own docstring records what that costs — it said "five
    conditions" while there were six."""
    missing = sorted(
        name
        for name, cls in _promoting_classes().items()
        if not _reaches(cls, DOCUMENT_CONDITIONS)
    )
    assert not missing, (
        f"{', '.join(missing)} implements promote_baseline without calling "
        f"{DOCUMENT_CONDITIONS}. The conditions that answer from the document are a "
        "function so that no backend restates them."
    )


def test_the_walk_sees_the_one_store_there_is() -> None:
    """The control on both tests above, which pass on a walk that found
    nothing — and a walk over an installed package is exactly the kind of thing
    that quietly finds nothing. `FileResultStore` is the store this repository
    has; when there is a second, it is here too or this fails."""
    walked = _promoting_classes()
    assert walked, "the walk found no class implementing promote_baseline"
    assert "digline.store.file_store.FileResultStore" in walked, sorted(walked)
    assert walked["digline.store.file_store.FileResultStore"] is FileResultStore


class _KeepsTheHelperNeverCallsIt:
    """The mutation, kept: `FileResultStore`'s shape with the one call removed.
    The private method still names condition 8, so a text search over the class
    finds it; `promote_baseline` never reaches the method, so nothing is
    refused."""

    def promote_baseline(self) -> None:
        self._write()

    def _refuse_a_moved_baseline(self) -> object:
        return refusal_for_a_moved_baseline

    def _write(self) -> None:
        pass


class _KeepsTheHelperAndCallsIt:
    """The same class with the call in place — the control that says the
    mutant's `False` is the walk's answer, not a walk that answers `False` to
    everything."""

    def promote_baseline(self) -> None:
        self._refuse_a_moved_baseline()
        self._write()

    def _refuse_a_moved_baseline(self) -> object:
        return refusal_for_a_moved_baseline

    def _write(self) -> None:
        pass


def test_a_helper_that_is_kept_and_never_called_is_not_reached() -> None:
    """The defect `_reaches` was written to replace: a text search passes the
    mutant, and the walk must not."""
    assert CONDITION_8 in inspect.getsource(_KeepsTheHelperNeverCallsIt), (
        "the mutant no longer names condition 8, so it no longer fools a text "
        "search and this test proves nothing"
    )
    assert _reaches(_KeepsTheHelperAndCallsIt, CONDITION_8)
    assert not _reaches(_KeepsTheHelperNeverCallsIt, CONDITION_8)


class _CallsTheHelperAndDropsIt:
    """The mutation `_raises` was written to catch, kept: `FileResultStore`'s
    shape with `raise moved` replaced by `pass`. It calls condition 8 and
    discards the refusal, so it promotes over a moved baseline — and every walk
    that asks only whether the call was *reached* says yes."""

    def promote_baseline(self) -> None:
        self._refuse_a_moved_baseline(_ANY_RUN, None, None)
        self._write()

    def _refuse_a_moved_baseline(
        self, run: Run, current: Run | None, expected: str | None
    ) -> None:
        moved = refusal_for_a_moved_baseline(
            run, current, expected, removed_by="nowhere"
        )
        if moved is not None:
            pass  # the mutation, and the whole point of this fixture

    def _write(self) -> None:
        pass


class _CallsTheHelperAndRaisesIt:
    """The same class with the raise in place — so the mutant's `False` is the
    predicate's answer and not an answer it gives everything."""

    def promote_baseline(self) -> None:
        self._refuse_a_moved_baseline(_ANY_RUN, None, None)
        self._write()

    def _refuse_a_moved_baseline(
        self, run: Run, current: Run | None, expected: str | None
    ) -> None:
        moved = refusal_for_a_moved_baseline(
            run, current, expected, removed_by="nowhere"
        )
        if moved is not None:
            raise moved

    def _write(self) -> None:
        pass


def test_a_refusal_that_is_computed_and_dropped_is_not_raised() -> None:
    """The defect this file shipped with: `_reaches` passes a class that calls
    condition 8 and throws the answer away, because calling is all it asks.

    **Both halves, or the control is half a control.** The mutant must still
    satisfy the old predicate — otherwise `_raises` is catching something
    `_reaches` already caught, and the new predicate is doing no work."""
    assert _reaches(_CallsTheHelperAndDropsIt, CONDITION_8), (
        "the mutant no longer even reaches condition 8, so it no longer "
        "demonstrates the gap between reaching and raising"
    )
    assert not _raises(_CallsTheHelperAndDropsIt, CONDITION_8)
    assert _raises(_CallsTheHelperAndRaisesIt, CONDITION_8)


# --------------------------------------------------------------------------- #
# The delete: the same obligation, on `delete_run` (ADR 0044 §7)
# --------------------------------------------------------------------------- #


def test_every_store_that_deletes_raises_the_refusal_about_the_baseline() -> None:
    """A class that defines `delete_run` and never raises what
    `refusal_for_a_promoted_run` returns removes the run under the current
    baseline, and a reference vanishes from under a gate (ADR 0034 §1). Like
    condition 8's walk, this reaches the classes in this repository and no
    others."""
    missing = sorted(
        name
        for name, cls in _promoting_classes("delete_run").items()
        if not (
            _reaches(cls, DELETE_REFUSAL, "delete_run") and _raises(cls, DELETE_REFUSAL)
        )
    )
    assert not missing, (
        f"{', '.join(missing)} implements delete_run without raising what "
        f"{DELETE_REFUSAL} returns. The run the suite's current baseline was "
        "promoted from must be refused, before the first removal: read the "
        f"baseline in your plan, pass it to {DELETE_REFUSAL}, and raise what it "
        "gives you; see ResultStore.delete_run."
    )


def test_the_delete_walk_sees_the_one_store_there_is() -> None:
    walked = _promoting_classes("delete_run")
    assert walked, "the walk found no class implementing delete_run"
    assert walked.get("digline.store.file_store.FileResultStore") is FileResultStore


_ANY_REF = RunRef(tenant="t", suite="s", key="k")


class _DeletesWithoutTheBaseline:
    """Test plan item 14's control: a class whose `delete_run` skips the
    baseline check, and removes."""

    def delete_run(self) -> None:
        self._remove()

    def _refuse_a_promoted_run(self) -> None:
        promoted = refusal_for_a_promoted_run(_ANY_REF, None)
        if promoted is not None:
            raise promoted

    def _remove(self) -> None:
        pass


class _DeletesAfterTheBaseline:
    """The same class with the check in place, so the mutant's failure is the
    walk's answer and not one it gives everything."""

    def delete_run(self) -> None:
        self._refuse_a_promoted_run()
        self._remove()

    def _refuse_a_promoted_run(self) -> None:
        promoted = refusal_for_a_promoted_run(_ANY_REF, None)
        if promoted is not None:
            raise promoted

    def _remove(self) -> None:
        pass


def test_14_a_delete_that_skips_the_baseline_check_fails_the_walk() -> None:
    """The class keeps the helper and its raise, so a text search and
    `_raises` both pass it; only the walk from `delete_run` says it is never
    reached."""
    assert _raises(_DeletesWithoutTheBaseline, DELETE_REFUSAL)
    assert not _reaches(_DeletesWithoutTheBaseline, DELETE_REFUSAL, "delete_run")
    assert _reaches(_DeletesAfterTheBaseline, DELETE_REFUSAL, "delete_run")
