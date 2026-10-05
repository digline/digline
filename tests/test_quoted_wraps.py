"""No refusal interpolates another exception's text into digline's sentence.

ADR 0043 *Consequences*: the class of #445 is every site that wraps an
exception digline did not write in a refusal of its own, and a new wrap
reopens it. A site that wraps hands the exception to the refusal as a
`Quoted`, and the refusal keeps it apart from what digline wrote (§2). What
digline wants from the exception, a line, a column, an `errno`, a byte offset,
it reads off the attributes, and that text is digline's.

So this refuses, inside the arguments of a constructor of a type in
`REFUSALS`, any use of a name bound by `except … as` other than an attribute
of it: `{exc}`, `str(exc)`, `repr(exc)`, and `exc` handed to a helper that
could stringify it. Inside `Quoted.of(...)` or `Quoted(...)` it is allowed,
because that is the carrier.

**What it cannot see**, said here rather than found: a sentence built from the
exception into a variable first and then passed to the refusal, and a refusal
constructed outside the `except` block that bound the name. It reads the
syntax, not the data flow.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from digline.host import REFUSALS

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted(
    [*(ROOT / "src" / "digline").rglob("*.py"), *ROOT.glob("packages/*/src/**/*.py")]
)
REFUSAL_NAMES = frozenset(kind.__name__ for kind in REFUSALS)
CARRIER = "Quoted"


def _called(node: ast.Call) -> str | None:
    """The refusal type a call constructs, by name. `pytest.UsageError` shares
    a name with digline's and is not one: it stops a pytest session, for the
    person who started it (ADR 0043 §3)."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "pytest":
            return None
        return node.func.attr
    return None


def _is_carrier(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == CARRIER
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == CARRIER
    )


def _bare_uses(node: ast.AST, name: str) -> list[ast.Name]:
    """Every use of `name` under `node` that is not `name.attribute` and not
    inside the carrier."""
    found: list[ast.Name] = []

    def visit(current: ast.AST) -> None:
        if isinstance(current, ast.Call) and _is_carrier(current):
            return
        if (
            isinstance(current, ast.Attribute)
            and isinstance(current.value, ast.Name)
            and current.value.id == name
        ):
            return
        if isinstance(current, ast.Name) and current.id == name:
            found.append(current)
            return
        for child in ast.iter_child_nodes(current):
            visit(child)

    visit(node)
    return found


def offenders(source: str, filename: str) -> list[str]:
    """`file:line` of every refusal built from an exception's text."""
    found: list[str] = []
    for handler in ast.walk(ast.parse(source, filename)):
        if not isinstance(handler, ast.ExceptHandler) or handler.name is None:
            continue
        for statement in handler.body:
            for node in ast.walk(statement):
                if not isinstance(node, ast.Call) or _called(node) not in REFUSAL_NAMES:
                    continue
                arguments: list[ast.AST] = [
                    *node.args,
                    *(k.value for k in node.keywords),
                ]
                if any(_bare_uses(argument, handler.name) for argument in arguments):
                    found.append(f"{filename}:{node.lineno}")
    return found


def test_the_gate_reads_the_whole_surface() -> None:
    """A gate over no files passes vacuously."""
    names = {source.as_posix() for source in SOURCES}
    assert any(n.endswith("digline/host/loader.py") for n in names)
    assert any(n.endswith("digline_mcp/errors.py") for n in names)
    assert len(REFUSAL_NAMES) > 20


def test_no_refusal_quotes_an_exception_outside_the_carrier() -> None:
    found = [
        at
        for source in SOURCES
        for at in offenders(
            source.read_text(encoding="utf-8"), str(source.relative_to(ROOT))
        )
    ]
    assert not found, (
        "These refusals put another exception's text into digline's own "
        "sentence. Hand it over as `Quoted.of(exc, ...)`, and read what digline "
        "needs off the exception's attributes (ADR 0043 §2):\n" + "\n".join(found)
    )


@pytest.mark.parametrize(
    "planted",
    [
        'raise UsageError(f"cannot read {path}: {exc}") from exc',
        "raise RefusedError(str(exc)) from exc",
        'raise RefusedError("no: " + repr(exc)) from exc',
        "raise UsageError(_said(exc)) from exc",
    ],
)
def test_the_gate_catches_a_planted_wrap(planted: str) -> None:
    """The control: each shape the gate names, planted, fails it."""
    source = f"try:\n    pass\nexcept OSError as exc:\n    {planted}\n"
    assert offenders(source, "planted.py") == ["planted.py:4"]


def test_the_carrier_and_an_attribute_pass() -> None:
    source = (
        "try:\n    pass\nexcept OSError as exc:\n"
        '    raise UsageError(Quoted.of(exc, f"at byte {exc.start}: ")) from exc\n'
    )
    assert offenders(source, "fine.py") == []
