"""The plugin's copy of the loader's spec rule, held to the loader.

`_suite_identity`, `_path_of` and `_attribute_of` resolve a spec without loading
it, by the rule `digline.host.loader` applies when it does load one. Two copies
of a rule drift, and the day the loader changes nobody would know. So each copy
is compared here with what the loader itself does, on the forms a spec takes.

What the loader does is read from the loader, not restated. A spec naming a file
that does not exist is refused, and the refusal names the path the loader
resolved, or the module it tried to import, so nothing is loaded. The attribute
is the loader's own `_split`, a private name a test may import. The one part
that is restated is which specs are TOML, by `SUITE_SUFFIX`: the loader's
refusal reads the same for a missing `.toml` and a missing `.py`.

Reading the rule through those refusals is reading it through a derivative. If
the loader stops naming the path or the module in its refusal, this test can no
longer read it and fails loudly, and that is meant: a guard that can no longer
see has to say so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.host import SUITE_ATTR, SUITE_SUFFIX, UsageError, load_suite
from digline.host.loader import _split  # pyright: ignore[reportPrivateUsage]
from pytest_digline.plugin import (  # pyright: ignore[reportPrivateUsage]
    _attribute_of,  # pyright: ignore[reportPrivateUsage]
    _path_of,  # pyright: ignore[reportPrivateUsage]
    _suite_identity,  # pyright: ignore[reportPrivateUsage]
)

SPECS = [
    "both.py",
    "eval/both.py",
    "./eval/both.py:support",
    "eval/../eval/both.py:billing",
    "/nowhere/both.py:support",
    "eval/both.toml",
    # The edges of the rule: a path with no `.py`, a tail that is not an
    # identifier, a Windows drive letter, which is not an attribute, and a
    # backslash path with no `.py`, which is a file by its separator alone.
    "eval/both",
    "eval/both.py:not-an-id",
    "C:\\suites\\qa.py",
    "C:\\suites\\qa",
    "nowhere_pkg.mod",
    "nowhere_pkg.mod:support",
]


def loader_resolves(spec: str) -> tuple[str, str]:
    """What the loader made of `spec`: `("file", path)` or `("module", name)`."""
    with pytest.raises(UsageError) as refused:
        load_suite(spec)
    said = str(refused.value)
    if said.startswith("no such file: "):
        return "file", said.removeprefix("no such file: ").split(" (from ")[0]
    prefix = "cannot import module '"
    assert said.startswith(prefix), said
    return "module", said.removeprefix(prefix).split("'")[0]


@pytest.mark.parametrize("spec", SPECS)
def test_the_plugin_resolves_a_spec_as_the_loader_does(
    spec: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    kind, where = loader_resolves(spec)
    attribute = None if spec.endswith(SUITE_SUFFIX) else _split(spec)[1] or SUITE_ATTR

    assert _suite_identity(spec) == (where, attribute), spec
    if kind == "file":
        assert str(_path_of(spec)) == where, spec
    if not spec.endswith(SUITE_SUFFIX):
        assert _attribute_of(spec) == _split(spec)[1], spec
