"""Every example's committed `.digline/.gitignore` keeps what the generated one
keeps, so a run of an example says nothing about a directory git would commit.

#523 is the general case: a `.gitignore` that exists is left as it is, and
since #690 a run says on stderr what git would commit. The eleven examples
were eleven instances of it. Each committed `*/runs/` and not `*/name-table/`,
so every run of every example printed that `git add` would commit the name
table, and the example taught the gesture that does it: run, `git add`, and
the re-identification key enters the repository.

Git decides, as it does for the warning: this asks `unignored`, the function
the warning is made from, about each example's tenants in this checkout.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from digline.host import unignored

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is needed")


def tenants() -> list[tuple[str, str]]:
    found = [
        (store.parent.name, tenant.name)
        for store in sorted(ROOT.glob("examples/*/.digline"))
        for tenant in sorted(store.iterdir())
        if tenant.is_dir()
    ]
    assert found, "no example carries a store: this would pass by asking nothing"
    return found


@pytest.mark.parametrize(("example", "tenant"), tenants())
def test_a_run_of_the_example_has_nothing_to_say(example: str, tenant: str) -> None:
    assert unignored(ROOT / "examples" / example, tenant) == ()
