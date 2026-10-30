"""The suite `docker/smoke.sh` runs inside the image, taken off the front page.

    python3 docker/smoke_suite.py extract README.md <suite.py>
    python3 docker/smoke_suite.py worsen <suite.py>

The page holds more than one suite, so the quickstart is found by the name its
`Suite(...)` declares, never by where it stands. `tests/test_docker.py` runs
this against the page in every gate, because the image job that calls it runs
only when `docker/` or a workflow moves.

Standard library only: `smoke.sh` runs it with the runner's `python3`, outside
any environment that has digline. `.dockerignore` keeps it out of the build
context, so no byte of it reaches the image.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

#: The suite the smoke runs: the quickstart, by the `name=` it declares.
QUICKSTART = "support"
#: Its tenant, whose baseline `smoke.sh` looks for on the mounted volume.
TENANT = "northwind"
#: Written on both answers. Removing the second is the regression the front
#: page shows, and the run the smoke expects to exit 1.
SIGN_OFF = " — Northwind Support"

FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.M | re.S)


def _declared_name(source: str) -> str | None:
    """The `name=` of the one `Suite(...)` call in a block, read from the code."""
    names = [
        keyword.value.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Suite"
        for keyword in node.keywords
        if keyword.arg == "name"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    ]
    return names[0] if len(names) == 1 else None


def quickstart(page: str) -> str:
    """The one ```python block whose suite is named `QUICKSTART`."""
    found = [
        body
        for info, body in FENCE.findall(page)
        if info.strip() == "python" and _declared_name(body) == QUICKSTART
    ]
    if len(found) != 1:
        raise SystemExit(
            f"expected one suite named {QUICKSTART!r} on the front page, "
            f"found {len(found)}"
        )
    return found[0]


def worsen(source: str) -> str:
    """The quickstart with its second sign-off removed."""
    count = source.count(SIGN_OFF)
    if count != 2:
        raise SystemExit(
            f"expected the sign-off twice in the quickstart, found {count}"
        )
    head, _, tail = source.rpartition(SIGN_OFF)
    return head + tail


def main(argv: list[str]) -> None:
    match argv:
        case ["extract", page, suite]:
            text = Path(page).read_text(encoding="utf-8")
            Path(suite).write_text(quickstart(text), encoding="utf-8")
        case ["worsen", suite]:
            path = Path(suite)
            path.write_text(worsen(path.read_text(encoding="utf-8")), encoding="utf-8")
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
