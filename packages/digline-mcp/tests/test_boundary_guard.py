"""Nothing reaches the SDK boundary without passing `json_visible`.

**This is a structural gate, not a string test, and the difference is the
point.** `test_errors.py` proves the two doors that exist today neutralise what
goes through them. It cannot fail on a *third* door, because it does not know
one was built — and a door built later is exactly how this family keeps biting.

The record, so the next reader does not re-derive it:

- **0.10.1** — a judge's quote of a model's answer reached a terminal raw;
  fixed at the sink with `visible()`.
- **0.13.1** — a C1 byte in `log --json`. Third time, so the rule became
  structural: no `print` in `digline.cli` outside its output module.
- **0.15.1** — a tool name carrying U+009B reached an MCP client raw. The rule
  moved from `digline.cli` onto the *value*, in `digline.core.json_visible`,
  because the CLI escaped the finished JSON text and `digline-mcp` hands
  dictionaries to an SDK that serialises them itself. **First bite at a door
  built after the rule was written.**
- **0.18.0 → digline-mcp 0.1.4** — a refusal's *message* carried the names of
  the rules that moved, which arrive inside a stored run document somebody else
  may have written. `digline.wire` neutralises the documents it renders; an
  exception message is not one, so it never entered `wire`. **Fifth bite,
  second at a post-rule door.**

Four of the five were found by a person reading, one at a time, after the door
existed. So this file asks the question the other tests cannot: **is there a
place in this package where a string becomes an SDK object, and is it
neutralised?** It answers by walking the source rather than by exercising it,
because a test that exercises can only reach the doors somebody remembered to
call.

**Two doors, and the second is here because the first does not cover 0.15.1.**
This file was proposed on the claim that it would have caught 0.15.1 as well as
0.18.0's. That is false of the `ToolError` gate and the correction is kept
rather than quietly fixed: 0.15.1 was a tool *name* inside a **returned
document**, and no gate on the exception door can see one. So there are two
tests for the two crossing shapes — the exception, and the returned document —
and each says in its own docstring what it does and does not reach.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "digline_mcp"

#: The SDK constructors that take a string digline composed and hand it to a
#: client. This is the list to extend when the SDK surface grows — and the
#: failure message says so, because the next door is the thing being guarded
#: against and a reader meeting a red here is the person building it.
#:
#: `ToolError` is the whole list today. It is a list rather than one name so
#: that adding the second costs an entry instead of a rewrite.
BOUNDARY_CONSTRUCTORS = frozenset({"ToolError"})

#: The one function that makes a composed string safe to hand over. Not
#: `visible()`, which is the terminal's rule: this text is serialised as JSON by
#: the SDK, an encoder already escapes C0, and `json_visible` covers exactly the
#: two ranges it does not — DEL and the C1 block. (`digline.core.text`)
NEUTRALISER = "json_visible"


def _sources() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def _call_name(node: ast.expr) -> str | None:
    """`ToolError` from `ToolError(...)` and from `errors.ToolError(...)`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_neutralised(argument: ast.expr) -> bool:
    """Whether this argument passed through the neutraliser on its way in.

    Accepts it anywhere in the expression rather than only at the top, because
    `json_visible(f"...{x}...")` and `f"{json_visible(x)}"` are both correct and
    a gate that demanded one shape would be a style rule wearing a safety rule's
    clothes. What it refuses is the argument that never meets it at all.
    """
    for node in ast.walk(argument):
        if isinstance(node, ast.Call) and _call_name(node.func) == NEUTRALISER:
            return True
    return False


def _boundary_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node.func) in BOUNDARY_CONSTRUCTORS
    ]


@pytest.mark.parametrize("source", _sources(), ids=lambda p: p.name)
def test_every_string_crossing_to_the_sdk_is_neutralised(source: Path) -> None:
    """Walk the source; every boundary construction neutralises its message.

    Parametrized per file so a red names the file that opened the door rather
    than reporting that the package, somewhere, has a problem.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for call in _boundary_calls(tree):
        name = _call_name(call.func)
        assert call.args, (
            f"{source.name}:{call.lineno}: {name}() is constructed with no "
            "positional message, which this gate cannot read. If the SDK "
            "surface changed, teach this file the new shape."
        )
        assert _is_neutralised(call.args[0]), (
            f"{source.name}:{call.lineno}: this {name}() hands a string to the "
            f"SDK without passing it through {NEUTRALISER}().\n\n"
            "A refusal's text is not all digline's own words: it interpolates "
            "tenants, suite names, provider ids and the names of the rules that "
            "moved, each of which can arrive inside a stored document somebody "
            "else wrote. DEL and the C1 block go out raw otherwise, and U+009B "
            "*is* CSI.\n\n"
            f"Wrap it: {name}({NEUTRALISER}(message)). If this call genuinely "
            "carries no third-party text, that is still the wrong reason to "
            "skip it — the next edit to the string will not come back here."
        )


def test_the_guard_can_see_a_boundary_at_all() -> None:
    """The control that must fail.

    Every assertion above passes vacuously on a package with no boundary call
    in it, and a gate that has verified nothing looks exactly like a gate that
    has verified everything. So: the doors exist, and this file found them.
    """
    found = [
        (source.name, call.lineno)
        for source in _sources()
        for call in _boundary_calls(ast.parse(source.read_text(encoding="utf-8")))
    ]
    assert found, (
        "no SDK boundary construction found anywhere in digline_mcp. Either the "
        f"package stopped raising {sorted(BOUNDARY_CONSTRUCTORS)}, or this gate "
        "is now looking for the wrong name and is passing on nothing."
    )
    assert len(found) >= 2, (
        f"expected both doors out of errors.py, found {found}. `translated()` "
        "and `refuse()` are the two, and losing sight of one is how the other "
        "gets audited alone."
    )


#: A tool's *return* is the other way a string crosses to a client, and it is
#: the shape 0.15.1 was about. `digline.wire` neutralises every document it
#: builds, so a return that is one of its calls is covered by construction. What
#: is not covered is a value spliced in beside it: `{**wire_builder(...), "k": v}`
#: is a document the front end composed, and the splice never met `neutralised`.
#:
#: Today the only splice is `key` — a run id digline composes from a timestamp
#: and a `config_hash`, with no third-party text in it. It is allowlisted by
#: name rather than by shape, so that the *second* splice is a decision somebody
#: takes here instead of a line that slips in looking like the first.
SPLICE_ALLOWED = frozenset({"key"})


def test_a_returned_document_is_wires_or_an_allowlisted_splice() -> None:
    """The other crossing shape, and the honest limit of the gate above.

    **Stated plainly, because the claim was overreached when this file was
    proposed:** the `ToolError` gate would *not* have caught 0.15.1. That defect
    was a tool *name* inside a returned document, and the fix was to make
    `digline.wire` neutralise what it builds. A gate on the exception door
    cannot see it.

    This is the half that watches the other door. It cannot re-prove that `wire`
    neutralises — `digline`'s own suite does that — but it does refuse the
    `{**document, "extra": value}` splice that would put a front-end-composed
    string back into a neutralised document, which is how 0.15.1's shape would
    return.
    """
    server = SOURCE / "server.py"
    tree = ast.parse(server.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        for key in node.value.keys:
            if key is None:  # `**something` — the wire builder's own document
                continue
            spliced = key.value if isinstance(key, ast.Constant) else "<computed>"
            if spliced not in SPLICE_ALLOWED:
                offenders.append(f"server.py:{node.lineno}: {spliced!r}")
    assert not offenders, (
        "a returned document splices a value beside a `digline.wire` document "
        f"without that key being allowlisted: {offenders}.\n\n"
        "`wire` neutralises what it builds; a value spliced in afterwards never "
        "met it. If the new value is digline's own — an id, a count, a key — add "
        f"it to SPLICE_ALLOWED with the reason. If it can carry text digline did "
        "not write, it has to pass json_visible first."
    )


def test_the_neutraliser_is_imported_where_it_is_used() -> None:
    """A name that is used but not imported would be a `NameError` at the worst
    possible moment — inside the handler for somebody else's failure, where it
    would replace a written refusal with a crash."""
    for source in _sources():
        tree = ast.parse(source.read_text(encoding="utf-8"))
        if not _boundary_calls(tree):
            continue
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert NEUTRALISER in imported, (
            f"{source.name} constructs an SDK boundary object but does not "
            f"import {NEUTRALISER}"
        )
