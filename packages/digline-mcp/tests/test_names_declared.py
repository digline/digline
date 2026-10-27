"""The declaration at start: `--names clear` or `--names project`, no default,
and the name table under `project`. (ADR 0054 §1, §4, §6)

Each refusal here happens before the store is opened, so none of them can
name anything in it, and each test also checks that no server was built.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from digline.host import NameTable, UsageError, load_name_table
from digline.wire import EXIT_USAGE
from digline_mcp import server

TABLE_SOURCE = """\
def mint(kind, text):
    return "A" * 22


def lookup(token):
    return None


class Table:
    mint = staticmethod(mint)
    lookup = staticmethod(lookup)


TABLE = Table()
HALF = object()
"""


def refused(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> str:
    """The stderr of a command line that must not start a server."""

    def started(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(f"a server was built from {argv}")

    monkeypatch.setattr(server, "build_server", started)
    with pytest.raises(SystemExit) as stopped:
        server.main(argv)
    assert stopped.value.code == EXIT_USAGE, f"{argv} exited {stopped.value.code}"
    return capsys.readouterr().err


def test_without_the_declaration_the_server_does_not_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No default: a configuration that passes `--root` alone, as every one
    before 0.7.0 did, no longer starts, and says what it needs."""
    err = refused(monkeypatch, capsys, ["--root", "."])
    assert "the following arguments are required: --names" in err


def test_a_value_that_is_not_one_of_the_two_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """*Refuse* is not a value (ADR 0054 §2), and neither is anything else."""
    err = refused(monkeypatch, capsys, ["--root", ".", "--names", "refuse"])
    assert "argument --names: invalid choice: 'refuse'" in err


def test_project_without_a_table_is_a_configuration_error_naming_nothing_stored(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The message says what is missing, and is the same sentence whatever the
    store holds, because the store was never opened. (ADR 0054 §4)"""
    store = tmp_path / ".digline" / "acme-bank" / "runs" / "qa"
    store.mkdir(parents=True)
    err = refused(monkeypatch, capsys, ["--root", str(tmp_path), "--names", "project"])
    said = err.strip().splitlines()[-1]
    assert said == (
        "digline-mcp: error: --names project needs --name-table: the tokens come "
        "from the name table, and none was given"
    )
    assert "acme-bank" not in err and "qa" not in said


def test_a_table_under_clear_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    err = refused(
        monkeypatch,
        capsys,
        ["--root", ".", "--names", "clear", "--name-table", "pkg.mod:TABLE"],
    )
    assert "--name-table is read only under --names project" in err


def test_a_table_that_cannot_be_loaded_is_refused_at_start(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    spec = tmp_path / "table.py"
    spec.write_text(TABLE_SOURCE, encoding="utf-8")
    err = refused(
        monkeypatch,
        capsys,
        ["--root", ".", "--names", "project", "--name-table", f"{spec}:HALF"],
    )
    assert "has no callable mint or lookup" in err


def test_project_with_a_table_starts_with_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The table named `module:attribute` is loaded at start and handed to the
    server with the declaration."""
    spec = tmp_path / "table.py"
    spec.write_text(TABLE_SOURCE, encoding="utf-8")
    received: dict[str, object] = {}

    class Stopped:
        def run(self, **_kwargs: object) -> None:
            pass

    def recorder(*_args: object, **kwargs: object) -> Stopped:
        received.update(kwargs)
        return Stopped()

    monkeypatch.setattr(server, "build_server", recorder)
    assert (
        server.main(
            ["--root", ".", "--names", "project", "--name-table", f"{spec}:TABLE"]
        )
        == 0
    )
    assert received["names"] == "project"
    table = cast(NameTable, received["table"])
    assert table.mint("case_id", "x") == "A" * 22


def test_under_clear_the_server_starts_with_no_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, object] = {}

    class Stopped:
        def run(self, **_kwargs: object) -> None:
            pass

    def recorder(*_args: object, **kwargs: object) -> Stopped:
        received.update(kwargs)
        return Stopped()

    monkeypatch.setattr(server, "build_server", recorder)
    assert server.main(["--root", ".", "--names", "clear"]) == 0
    assert received == {"names": "clear", "table": None}


@pytest.mark.parametrize(
    ("names", "table", "said"),
    [
        ("project", None, "--names project needs --name-table"),
        ("clear", object(), "--name-table is read only under --names project"),
        ("refuse", None, "--names takes clear or project"),
    ],
)
def test_build_server_refuses_what_the_command_line_refuses(
    names: str, table: object, said: str
) -> None:
    """The same rule for a program that builds the server itself."""
    with pytest.raises(UsageError, match=said):
        server.build_server(".", None, None, names=names, table=table)  # pyright: ignore[reportArgumentType]


def test_a_name_table_spec_needs_its_attribute(tmp_path: Path) -> None:
    spec = tmp_path / "table.py"
    spec.write_text(TABLE_SOURCE, encoding="utf-8")
    with pytest.raises(UsageError, match="names no attribute"):
        load_name_table(str(spec))
    with pytest.raises(UsageError, match="has no attribute 'MISSING'"):
        load_name_table(f"{spec}:MISSING")
    assert load_name_table(f"{spec}:TABLE").lookup("x") is None
