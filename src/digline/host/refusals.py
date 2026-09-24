"""Every exception digline defines, sorted into refusals and everything else.

**A refusal** is raised on purpose and carries a sentence written for a reader:
a crossed perimeter, a moved configuration, a document that is not a run. A
front end shows it and exits on it. **Anything else** that reaches a front end
is a bug, and travels as one.

The list exists because a front end catches refusals by naming them, and a
name nobody added is a refusal that reaches the user as a traceback. 0.19.2
added two, `SuiteMismatchError` to the store and `DocumentRefusedError` to the
core, and the tuple `digline view` catches on its one route that writes never
learned either: a promotion there was written and then answered with a closed
connection. So the list is not the guard. `tests/test_refusals.py` is:
it walks every module under `digline` and fails on any exception class that is
in neither table below, which is what turns *a type somebody added* into *a type
somebody classified*.

Here in `host` because it is the lowest layer that can import every type it
lists — `targets` raises two of them, and nothing below `host` may import
`targets`. Both front ends already import `host`.
"""

from __future__ import annotations

from collections.abc import Mapping

from digline.core.diff import DifferentJudgesError, DifferentSuitesError
from digline.core.run import DocumentRefusedError
from digline.host.errors import UsageError
from digline.run.replay import ReplayError
from digline.store.migrate import NonAdditiveError
from digline.store.protocol import (
    ConfigMismatchError,
    ErroredRunError,
    JournalBusyError,
    JournalRefusedError,
    PathRefusedError,
    RegisterRefusedError,
    ReplayedRunError,
    RunNotFoundError,
    SuiteMismatchError,
    TenantMismatchError,
    UncalibratedRunError,
)
from digline.targets.pricing import UnknownModelError
from digline.targets.registry import ProviderNotFound

__all__ = ["NOT_REFUSALS", "REFUSALS"]

#: Every refusal digline raises deliberately, by layer. A subclass is listed
#: beside its parent rather than left to be caught through it: the rule is that
#: every class is *classified*, and a class covered by accident is not.
REFUSALS: tuple[type[Exception], ...] = (
    # core
    DifferentSuitesError,
    DifferentJudgesError,
    DocumentRefusedError,
    # store
    ConfigMismatchError,
    ErroredRunError,
    ReplayedRunError,
    UncalibratedRunError,
    TenantMismatchError,
    SuiteMismatchError,
    PathRefusedError,
    RunNotFoundError,
    RegisterRefusedError,
    JournalRefusedError,
    JournalBusyError,
    NonAdditiveError,
    # run
    ReplayError,
    # targets
    UnknownModelError,
    ProviderNotFound,
    # host
    UsageError,
)

#: The exception classes that are not refusals, by qualified name, each with the
#: reason it never reaches a front end. By name rather than by type because one
#: of them is private to its module, and importing it here to classify it would
#: be the one reason anybody outside that module ever named it.
NOT_REFUSALS: Mapping[str, str] = {
    "digline.core.protocols.JudgeAbstained": (
        "a judge's declared abstention: the assertion catches it and records the "
        "judge's sentence as the verdict's reason (ADR 0004 §7.4)"
    ),
    "digline.store.file_store._MalformedLine": (
        "private to the register reader, which re-raises it as "
        "RegisterRefusedError naming the line"
    ),
}
