"""`docs/api.md` says which causes of `2` `run_exit_code` cannot see.

`run_exit_code(run)` is `exit_code`'s rule with nothing to compare against, so
it never sees a cause that is a relation between a run and its reference. In
`core/gate.py` those are the causes `causes_of_two` adds only when it has a
`comparison`. The bullet on `run_exit_code` in `docs/api.md` names them, and
it named the drifted pin and not the lost one, which is a relation too
(ADR 0051 §3).

A count would catch a cause removed and not a phrase swapped for another
cause's, so this is a golden set: each relation, and the words `api.md` uses
for it. A new relation in `gate.py` with no words here fails, and so does a
phrase that stops being in the bullet.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "src" / "digline" / "core" / "gate.py"
API = ROOT / "docs" / "api.md"

#: Each cause `causes_of_two` adds only with a comparison, and the words the
#: bullet on `run_exit_code` uses for it.
RELATIONS = {
    "pinned_drifted": "a drifted pin",
    "pinned_lost": "a lost pin",
}


def _gated_on_a_comparison() -> set[str]:
    """The causes appended under `if comparison is not None and …`."""
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    (function,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "causes_of_two"
    ]
    found: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.If) or "comparison is not None" not in (
            ast.unparse(node.test)
        ):
            continue
        for call in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "append"
                and isinstance(call.args[0], ast.Constant)
            ):
                found.add(str(call.args[0].value))
    return found


def _bullet() -> str:
    """The bullet on `run_exit_code`, its lines folded into one."""
    text = API.read_text(encoding="utf-8")
    start = text.index("- **`run_exit_code(run)` is the same rule")
    end = text.index("\n  - ", start)
    return re.sub(r"\s+", " ", text[start:end])


def test_every_relation_in_the_gate_has_its_words() -> None:
    assert _gated_on_a_comparison() == set(RELATIONS), (
        f"causes_of_two adds {sorted(_gated_on_a_comparison())} only with a "
        f"comparison, and this test has words for {sorted(RELATIONS)}: give the "
        "new relation its phrase here and in api.md's bullet on run_exit_code"
    )


def test_the_bullet_names_every_relation() -> None:
    bullet = _bullet()
    missing = {
        cause: words for cause, words in RELATIONS.items() if words not in bullet
    }
    assert not missing, (
        f"api.md's bullet on run_exit_code does not say {missing}: {bullet!r}"
    )


def test_the_reader_of_the_gate_finds_what_it_should() -> None:
    """The control: the reader finds the two relations today, and none of the
    three causes that answer from the run alone."""
    found = _gated_on_a_comparison()
    assert "pinned_drifted" in found
    assert not found & {"unjudged", "scale_lost", "nothing_judged"}
