"""The summary's prefix where no relative path exists, as pytest gives it.

The prefix is the suite's nodeid as a path from where pytest started, computed
by `_from_where_pytest_started` rather than asked of `cwd_relative_nodeid`,
whose contract moved under this plugin (see the function). That computation is
`os.path.relpath`, which raises `ValueError` on Windows when the start and the
rootdir are on two drives. pytest's own `bestrelpath` gives the destination as
it is there, and so does this.

No runner here has two drives, so a real pytest session cannot reach the
branch. It is reached with Windows' own `relpath`, `ntpath.relpath`, which
raises for two drives on any system, on Windows paths. A private name is
imported for it, as `test_spec_rule_mirrors_the_loader.py` does; the branch
that does have a relative path is held by a real session, in
`test_summary_names.py`.
"""

from __future__ import annotations

import ntpath
import os
from pathlib import PureWindowsPath

import pytest

from pytest_digline.plugin import (  # pyright: ignore[reportPrivateUsage]
    _from_where_pytest_started,  # pyright: ignore[reportPrivateUsage]
)


def test_two_drives_give_the_destination_as_pytest_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = PureWindowsPath("D:/work/project")
    started = PureWindowsPath("C:/Users/someone")
    with pytest.raises(ValueError):
        ntpath.relpath(root / "suites/both.py:support", started)
    monkeypatch.setattr(os.path, "relpath", ntpath.relpath)

    prefix = _from_where_pytest_started(root, started, "suites/both.py:support")

    assert prefix == "D:\\work\\project\\suites\\both.py:support"


def test_one_drive_gives_the_relative_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: the same paths on one drive take the other branch."""
    root = PureWindowsPath("C:/work/project")
    started = PureWindowsPath("C:/work")
    monkeypatch.setattr(os.path, "relpath", ntpath.relpath)

    prefix = _from_where_pytest_started(root, started, "suites/both.py:support")

    assert prefix == "project\\suites\\both.py:support"
