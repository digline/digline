"""The type gate, checked against defects it must catch.

`pyright --strict` is a gate, and a gate is worth what it refuses. This file runs
it against files written to fail and asserts that it does, and against a file
written to pass and asserts that it does — the second being the one that matters.

**Why it exists.** During the 0.15.0 delta-pass pyright reported every newly
added public name in `digline` as an unknown import symbol, while names that
already existed resolved normally. `json_visible` had just been added to
`digline.core`; pyright could type-check the file that defined it and could not
see it from the file that imported it. The gate was green because nobody had
added a symbol — not because it was working — and it was blind in exactly the
case it is there for.

**What the cause was, stated honestly.** Two things changed before it cleared,
and the incident cannot be split between them after the fact: `src` was added to
`[tool.pyright] extraPaths`, which had listed every plugin's source root and not
the core's own, and the editable install was rebuilt. An editable install leaves
nothing in `site-packages/digline/` but `py.typed`, and pyright does not read the
`.pth` that points at the source, so a stale one can leave it resolving from
somewhere that no longer matches the tree. Afterwards the blind state could not
be reproduced by removing `extraPaths` alone. So `extraPaths` is kept because it
makes resolution independent of install state, not because it was proven to be
the cause.

That is why the test below is written against the **symptom** rather than either
suspected cause: whatever breaks resolution next time — a stale install, a moved
path, a new packaging layout — a name this project exports must be visible to the
checker that gates it, and if it is not, this says so out loud.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Files pyright must refuse, and the rule each must be refused by. They prove
#: the checker is running at all and is strict when it does: a gate that reports
#: nothing because it never ran looks exactly like a clean tree.
MUST_REFUSE: tuple[tuple[str, str, str], ...] = (
    (
        "a wrong return type",
        "def wrong() -> str:\n    return 12345\n",
        "reportReturnType",
    ),
    (
        "a name that is not in digline.core",
        "from digline.core import this_name_does_not_exist\n\n"
        "_ = this_name_does_not_exist\n",
        "reportAttributeAccessIssue",
    ),
)

#: A file pyright must **accept**, and the one that would have caught the 0.15.0
#: incident. Names chosen from three packages and three vintages, so that a
#: resolver seeing only part of the tree fails here rather than somewhere subtle.
MUST_RESOLVE = (
    "from digline.core import json_visible, travels\n"
    "from digline.report import visible\n"
    "from digline.wire import OUTPUT_VERSION\n\n"
    "_ = (json_visible, travels, visible, OUTPUT_VERSION)\n"
)


def _errors(path: Path) -> list[tuple[str, str]]:
    """`(rule, message)` for every error pyright reports on one file."""
    done = subprocess.run(  # noqa: S603
        [str(ROOT / ".venv" / "bin" / "pyright"), "--outputjson", str(path)],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if not done.stdout.strip():
        pytest.skip(f"pyright did not run here: {done.stderr.strip()[:200]}")
    report = cast("dict[str, object]", json.loads(done.stdout))
    found = report.get("generalDiagnostics", [])
    assert isinstance(found, list)
    rows = cast("list[object]", found)
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = cast("dict[str, object]", row)
        if entry.get("severity") != "error":
            continue
        out.append((str(entry.get("rule", "")), str(entry.get("message", ""))))
    return out


def _planted(source: str, name: str) -> Path:
    """Written inside the checked tree, because *where* a file sits is half of
    what is under test: resolution of `digline.*` is what broke, and a file
    outside the project resolves by different rules."""
    path = ROOT / "src" / "digline" / f"_type_gate_{name}.py"
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("what", "source", "rule"), MUST_REFUSE, ids=[row[0] for row in MUST_REFUSE]
)
def test_the_type_gate_refuses_what_it_must(what: str, source: str, rule: str) -> None:
    """The gate is live and strict. If pyright passes either of these it is not
    checking this project, and every other green it reports is worth nothing."""
    planted = _planted(source, f"refuse_{abs(hash(what))}")
    try:
        rules = [rule for rule, _ in _errors(planted)]
    finally:
        planted.unlink(missing_ok=True)
    assert rule in rules, (
        f"pyright did not refuse {what}: it reported {rules or 'nothing at all'}."
    )


def test_the_type_gate_can_see_the_names_this_project_exports() -> None:
    """The one that would have caught the 0.15.0 incident.

    Not a control that must fail but a control that must **pass**, and the
    asymmetry is the point: the failure being guarded is a checker that refuses
    something correct, which every *must-fail* probe in this file is blind to —
    a broken resolver reports an error either way, so those two stay green while
    the gate is useless. Only asking it to accept something true can tell.
    """
    planted = _planted(MUST_RESOLVE, "resolve")
    try:
        found = _errors(planted)
    finally:
        planted.unlink(missing_ok=True)
    unresolved = [
        f"{rule}: {message}"
        for rule, message in found
        if rule in {"reportAttributeAccessIssue", "reportMissingImports"}
        or "unknown import symbol" in message
    ]
    assert not unresolved, (
        "pyright cannot see names this project exports, so it cannot gate a "
        "change that adds one:\n  " + "\n  ".join(unresolved) + "\n"
        "Check `[tool.pyright] extraPaths` includes `src`, and rebuild the "
        "editable install (`uv sync --all-packages`) — an editable install "
        "leaves only `py.typed` in site-packages and pyright does not read the "
        "`.pth` beside it."
    )
