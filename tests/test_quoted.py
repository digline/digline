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

from digline.core import (
    WITHHELD_WORDS,
    CalibrationBand,
    NameRef,
    Quoted,
    RefusedError,
    Withheld,
)
from digline.host import UsageError, load_suite, to_withhold, written_by_digline
from digline.host.authorship import quoted_in
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


def test_a_toml_suite_that_is_not_utf8_quotes_no_byte(tmp_path: Path) -> None:
    """§6, amended, the second site: `bytes.decode` is a builtin, so its frame
    was digline's, and its message quoted a byte of the file. Measured at
    58dfb60: *"can't decode byte 0xe8 in position 95"* reached the agent. Now
    nothing is quoted, on either front end, and the offset is digline's."""
    suite = tmp_path / "suite.toml"
    suite.write_bytes(b'[suite]\nname = "qa"\n# Mario Rossi \xe8\n')
    with pytest.raises(UsageError) as caught:
        load_suite(str(suite))
    whole = str(caught.value)
    assert whole == f"{suite} is not UTF-8 at byte 34", whole
    assert agent(caught.value) == whole


# --------------------------------------------------------------------------- #
# The names a sentence quotes (ADR 0054 §8)
# --------------------------------------------------------------------------- #


def _mint(kind: str, text: str) -> str:
    return f"<{kind}:{len(text)}>"


def test_a_name_reads_as_its_repr_in_clear_and_as_its_token_minted() -> None:
    """In clear the sentence is the one `{name!r}` wrote, so the command line
    reads what it read; minted, each name is its token, quoted the same way."""
    said = Quoted.said("case ", NameRef("case_id", "it's"), " is suspended")
    assert str(said) == 'case "it\'s" is suspended'
    assert said.rendered(withheld=None, mint=_mint) == "case '<case_id:4>' is suspended"
    assert said.names == (NameRef("case_id", "it's"),)


def test_a_check_s_name_is_minted_as_the_projection_mints_it() -> None:
    """The family and the group apart, as `project_check_name` does."""
    ref = NameRef("verdict_name", "accuracy[group=till]")
    assert ref.rendered(_mint) == "'<verdict_name:8>[group=<group:4>]'"


def test_a_wrap_keeps_the_names_of_the_refusal_it_quotes() -> None:
    """`run_from_dict` wraps a validation's refusal: the names inside it are
    still names, so the reader's prefix and the token both reach the agent."""
    inner = ValueError(Quoted.said("case ", NameRef("case_id", "x"), " is wrong"))
    wrapped = Quoted.of(inner, "", named=False).around(
        "the run could not be read: ", ""
    )
    assert wrapped.names == (NameRef("case_id", "x"),)
    assert str(wrapped) == "the run could not be read: case 'x' is wrong"
    assert (
        wrapped.rendered(withheld=None, mint=_mint)
        == "the run could not be read: case '<case_id:1>' is wrong"
    )


def test_a_wrap_of_a_plain_sentence_flattens_its_names() -> None:
    """The silent fallback, held so it stays visible: a refusal that is not
    built from a `Quoted` has no names to carry, and its text goes as it is.
    What catches a name in it is the names gate."""
    wrapped = Quoted.of(ValueError("case 'x' is wrong"), "", named=False)
    assert wrapped.names == ()
    assert wrapped.rendered(withheld=None, mint=_mint) == "case 'x' is wrong"


def test_the_agent_s_sentence_is_minted_when_a_mint_is_handed_over() -> None:
    refusal = RefusedError(Quoted.said("check ", NameRef("verdict_name", "lev")))
    assert refusal_text(refusal, None) == "check 'lev'"
    assert refusal_text(refusal, None, mint=_mint) == "check '<verdict_name:3>'"


def test_a_sentence_that_quotes_no_exception_is_digline_s() -> None:
    """No cause: what decides is the refusal's own frame, here digline's."""
    with pytest.raises(RefusedError) as refused:
        CalibrationBand.bounds("lev", 0.9, 0.1)
    assert quoted_in(refused.value) is not None
    assert written_by_digline(refused.value)
    assert to_withhold(refused.value) is None


def test_a_withheld_value_reads_in_clear_and_says_what_it_withholds_minted() -> None:
    """A value the projection lets through neither as a token nor in clear:
    the command line reads it, and an agent reads which kind of thing was
    kept back, one word per kind, never the value. (ADR 0054 §8)"""
    identity = Quoted.said("the identity ", Withheld("identity", "lev"), " is wrong")
    keys = Quoted.said(
        "metadata (", Withheld("run_metadata", "a, b", quoted=False), ")"
    )
    assert str(identity) == "the identity 'lev' is wrong"
    assert str(keys) == "metadata (a, b)"
    minted = identity.rendered(withheld=None, mint=_mint)
    assert "lev" not in minted
    assert minted == f"the identity {WITHHELD_WORDS['identity']} is wrong"
    assert keys.rendered(withheld=None, mint=_mint) == (
        f"metadata ({WITHHELD_WORDS['run_metadata']})"
    )
    assert WITHHELD_WORDS["identity"] != WITHHELD_WORDS["run_metadata"]
    assert identity.withheld == (Withheld("identity", "lev"),)
    assert identity.names == ()
