"""A refusal in fields, and who wrote each one. (ADR 0043 §1, §2, §5, §6)

`tests/test_quoted_wraps.py` holds that every wrap goes through the carrier,
and `packages/digline-mcp/tests/test_boundary.py` that no member of the class
carries a case to an agent. This holds the pieces in between: what a
`Quoted` renders, and how its author is read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from digline.core import Quoted, RefusedError
from digline.host import UsageError, load_suite, to_withhold, written_by_digline
from digline.host.loader import refused_exit
from digline.wire import WITHHELD, refusal_text

MARKER = "IT60X0542811101"


def agent(refusal: BaseException) -> str:
    """What the MCP server renders, without the server."""
    return refusal_text(refusal, to_withhold(refusal))


def refused_loading(tmp_path: Path, source: str) -> UsageError:
    (tmp_path / "suite.py").write_text(source, encoding="utf-8")
    with pytest.raises(UsageError) as caught:
        load_suite(str(tmp_path / "suite.py"))
    return caught.value


# --------------------------------------------------------------------------- #
# The carrier
# --------------------------------------------------------------------------- #


def test_the_whole_sentence_is_str_and_the_withheld_one_keeps_the_rest() -> None:
    try:
        raise ValueError(f"bad row {MARKER}")
    except ValueError as exc:
        quoted = Quoted.of(
            exc,
            "x.py raised ",
            ", while loading.",
            locations=("x.py:3", "x.py:9"),
            reproduce="python x.py",
        )
    assert str(quoted) == (
        f"x.py raised ValueError: bad row {MARKER} at x.py:3, reached from "
        "x.py:9, while loading. For the full traceback, run: python x.py"
    )
    assert quoted.rendered(withheld="(withheld)") == (
        "x.py raised ValueError at x.py:3, reached from x.py:9, while loading. "
        "(withheld) For the full traceback, run: python x.py"
    )


def test_a_refusal_built_from_one_says_the_whole_sentence() -> None:
    """`str()` of the refusal is what the command line prints, unchanged."""
    quoted = Quoted.of(ValueError("why"), "it failed: ", named=False)
    assert str(UsageError(quoted)) == "it failed: why"
    assert str(RefusedError(quoted)) == "it failed: why"


@pytest.mark.parametrize(
    ("code", "whole", "withheld"),
    [
        (3, "SystemExit(3)", "SystemExit(3)"),
        (0, "SystemExit(0)", "SystemExit(0)"),
        (None, "SystemExit(None)", "SystemExit(None)"),
        (f"row {MARKER}", f"SystemExit('row {MARKER}')", "SystemExit(…)"),
    ],
)
def test_an_int_exit_code_is_code_and_anything_else_a_message(
    code: object, whole: str, withheld: str
) -> None:
    """§5: `sys.exit(3)` keeps its code everywhere, and `sys.exit("…")` loses
    its text where the message is withheld."""
    quoted = Quoted.of(SystemExit(code), "")
    assert str(quoted) == whole
    assert quoted.rendered(withheld="W").startswith(withheld)


# --------------------------------------------------------------------------- #
# Who wrote it, by frame
# --------------------------------------------------------------------------- #


def test_a_refusal_raised_here_is_not_digline_s_whatever_its_type() -> None:
    """§1: being in `REFUSALS` says *on purpose*, not *written by digline*."""
    try:
        raise RefusedError(f"refused {MARKER}")
    except RefusedError as exc:
        assert not written_by_digline(exc)
        said = agent(exc)
    assert MARKER not in said
    assert "raised RefusedError at " in said, said
    assert WITHHELD in said


def test_a_refusal_digline_wrote_crosses_whole() -> None:
    """The control: the core's own sentence, raised in the core."""
    from digline.core import Contains

    with pytest.raises(RefusedError) as caught:
        Contains(needle="")
    assert written_by_digline(caught.value)
    assert agent(caught.value) == str(caught.value)


def test_a_wrap_is_as_much_digline_s_as_what_it_quotes() -> None:
    """Through every wrap: digline's sentence around a library's message is
    not digline's. `re` raises in its own frames, so `Regex` quotes a library,
    and keeps only the position it read off the exception."""
    from digline.core import Regex

    with pytest.raises(RefusedError) as caught:
        Regex(pattern="(unclosed")
    assert not written_by_digline(caught.value)
    said = agent(caught.value)
    assert said.startswith("Regex.pattern does not compile at position 0: "), said
    assert "missing )" not in said
    assert "missing )" in str(caught.value)


def test_an_exception_never_raised_is_nobody_s() -> None:
    """`refused_exit` builds its refusal without raising it, and a refusal with
    no frame is not taken for digline's."""
    try:
        sys.exit(f"bad row {MARKER}")
    except SystemExit as exc:
        refused = refused_exit(exc)
    assert refused is not None
    assert MARKER in str(refused)
    assert MARKER not in agent(refused)


# --------------------------------------------------------------------------- #
# The loader
# --------------------------------------------------------------------------- #


def test_a_missing_module_keeps_its_name_on_both_front_ends(tmp_path: Path) -> None:
    """§5: the import system's own sentence is rebuilt from its attributes, so
    it is digline's, and the `uvx` diagnosis survives."""
    refused = refused_loading(tmp_path, "import digline_plugin_not_installed\n")
    assert "No module named 'digline_plugin_not_installed'" in agent(refused)


def test_a_name_that_cannot_be_imported_keeps_it_too(tmp_path: Path) -> None:
    """The other template: `cannot import name 'y' from 'x' (…)`."""
    refused = refused_loading(tmp_path, "from json import no_such_name\n")
    said = agent(refused)
    assert "cannot import name 'no_such_name' from 'json'" in said, said


def test_an_import_error_in_free_text_loses_the_text(tmp_path: Path) -> None:
    refused = refused_loading(
        tmp_path, f"raise ImportError('no adapter for {MARKER}', name='{MARKER}')\n"
    )
    assert MARKER in str(refused)
    said = agent(refused)
    assert MARKER not in said, said
    assert "could not import a module: ImportError." in said, said


def test_a_suite_that_does_not_parse_keeps_its_line_and_column(
    tmp_path: Path,
) -> None:
    """§6, amended: `compile()` is a builtin, so its frame is digline's, and
    "keyword argument repeated" quotes a name written in a case. The site is
    declared, and the frame does not decide."""
    refused = refused_loading(tmp_path, f"x = dict({MARKER}=1,\n         {MARKER}=2)\n")
    assert f"keyword argument repeated: {MARKER}" in str(refused)
    said = agent(refused)
    assert MARKER not in said, said
    assert " does not parse at line 2, column 10: SyntaxError. " in said, said


def test_a_refusal_the_suite_raises_is_refused_with_its_location(
    tmp_path: Path,
) -> None:
    """ADR 0041 §4.1 rule 1, amended: a refusal type raised by the suite is
    refused as any other exception from its code is, with the location and the
    command, instead of passing through as digline's."""
    refused = refused_loading(
        tmp_path,
        f"from digline.core import RefusedError\nraise RefusedError('{MARKER}')\n",
    )
    whole = str(refused)
    assert f"raised RefusedError: {MARKER} at {tmp_path.resolve()}" in whole, whole
    assert "For the full traceback, run:" in whole
    assert MARKER not in agent(refused)
