"""Who wrote an `OSError`'s message, and what of it reaches an agent. (#451)

ADR 0043 §1 read who wrote a message from the innermost frame, and set `OSError`
apart until #451: digline's own reads go through `pathlib`, so their innermost
frame is the standard library's and the rule would charge them to the suite.
Measured for #451, that was half of it. `os.replace` and `os.open` are C
functions, so an `OSError` from them already had digline's frame. And the
innermost frame cannot tell digline's read through `pathlib` (P6) from the
suite's (P3), which have the same one. What tells them apart is the first frame
outside the standard library: who asked.

So for an `OSError` **the type chooses which frame is read, and the frame says
who wrote it**. Its message is digline's when digline asked and the words are
the system's own, rebuilt from the exception's attributes as `ImportError`'s
are (§5). P1 to P6 are the six shapes measured for #451; the rest are the
edges of the rule. (ADR 0043 §1, amended with #451)
"""

from __future__ import annotations

import os
import socket
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

import digline
from digline.host import (
    UsageError,
    authorship,
    load_suite,
    to_withhold,
    written_by_digline,
)
from digline.host.authorship import frames_outside, raised_inside_digline
from digline.store import FileResultStore
from digline.store.file_store import (
    _write_atomic,  # pyright: ignore[reportPrivateUsage]
)
from digline.targets import HttpTarget
from digline.wire import WITHHELD, refusal_text

MARKER = "IT60X0542811101"

#: A suite with the case in reach, as `packages/digline-mcp/tests/test_boundary.py`
#: writes one: the marker is a case's data.
HEAD = f"""
from pathlib import Path

from digline.core import Contains
from digline.run import Case, Response, Suite

ROW = {{"iban": "{MARKER}"}}
suite = Suite(
    tenant="acme",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one", vars=ROW)],
)

def target(case):
    return Response(output="Rome", input="q", cost_usd=0.0, latency_ms=1.0)
"""

#: A TOML suite that loads with nothing listening: a target is not contacted
#: until a run.
TOML = """
[suite]
tenant = "acme"
environment = "staging"
name = "qa"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "answer"

[[assertions]]
type = "contains"
needle = "Rome"
"""

#: A file name inside digline's own directory. Nothing is written there: the
#: frame rule reads the name a frame was compiled under, as
#: `packages/digline-mcp/tests/test_errors.py` does. (ADR 0043 §5, amended)
INSIDE_DIGLINE = str(Path(digline.__file__).resolve().parent / "_raised_by_a_test.py")

without_mode_000 = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="mode 000 denies nothing to root, and Windows has no such mode",
)


def agent(refusal: BaseException) -> str:
    """What the MCP server renders, without the server."""
    return refusal_text(refusal, to_withhold(refusal))


@contextmanager
def mode_000(path: Path) -> Generator[None]:
    path.chmod(0)
    try:
        yield
    finally:
        path.chmod(0o644)


def refused_loading(tmp_path: Path, source: str) -> UsageError:
    (tmp_path / "suite.py").write_text(source, encoding="utf-8")
    with pytest.raises(UsageError) as caught:
        load_suite(str(tmp_path / "suite.py"))
    return caught.value


# --------------------------------------------------------------------------- #
# P1 to P3: the suite's, refused with its location, its message withheld
# --------------------------------------------------------------------------- #

SUITE_RAISES = {
    "P1 FileNotFoundError(row)": "raise FileNotFoundError(ROW['iban'])\n",
    "P2 open(row), a builtin": "open('/nonexistent/' + ROW['iban'])\n",
    "P3 Path(row).read_text(), through pathlib": (
        "Path('/nonexistent/' + ROW['iban']).read_text()\n"
    ),
}


@pytest.mark.parametrize("raises", list(SUITE_RAISES))
def test_an_os_error_the_suite_raises_is_refused_with_its_location(
    tmp_path: Path, raises: str
) -> None:
    """ADR 0041 §4.1 rule 1 passed an `OSError` through whatever its frame, so
    the suite's arrived bare: no location on the command line, and on the MCP
    the SDK's *Error executing tool*. Now it is the suite's by its frame, and
    refused as every other exception from the suite's code is, at the line
    after `HEAD`'s last."""
    refused = refused_loading(tmp_path, HEAD + SUITE_RAISES[raises])
    whole = str(refused)
    assert MARKER in whole, whole
    line = HEAD.count("\n") + 1
    assert f"at {tmp_path.resolve() / 'suite.py'}:{line}" in whole, whole
    assert "For the full traceback, run:" in whole, whole
    said = agent(refused)
    assert MARKER not in said, said
    assert WITHHELD in said, said


def test_a_location_is_never_the_standard_library_s(tmp_path: Path) -> None:
    """P3's location is the suite's line, not the line in `pathlib` the system
    call happens to sit under: that line says nothing about who asked."""
    refused = refused_loading(
        tmp_path, HEAD + SUITE_RAISES["P3 Path(row).read_text(), through pathlib"]
    )
    said = agent(refused)
    assert "pathlib" not in said, said


# --------------------------------------------------------------------------- #
# P4 to P6: digline's own, whole on both front ends
# --------------------------------------------------------------------------- #


def test_p4_a_cases_file_digline_could_not_find_is_digline_s(tmp_path: Path) -> None:
    """`_cases` wraps the `OSError` of its own read. Its frame was `pathlib`'s,
    so the agent was told *"Its message was not written by digline and may
    quote a case's data"* about digline's own read."""
    (tmp_path / "suite.toml").write_text(TOML, encoding="utf-8")
    with pytest.raises(UsageError) as caught:
        load_suite(str(tmp_path / "suite.toml"))
    assert written_by_digline(caught.value)
    said = agent(caught.value)
    assert said == str(caught.value)
    assert "No such file or directory" in said, said


@without_mode_000
def test_p5_a_suite_file_digline_could_not_read_is_digline_s(tmp_path: Path) -> None:
    suite = tmp_path / "suite.toml"
    suite.write_text(TOML, encoding="utf-8")
    with mode_000(suite), pytest.raises(UsageError) as caught:
        load_suite(str(suite))
    said = agent(caught.value)
    assert said == str(caught.value)
    assert "Permission denied" in said, said


@without_mode_000
def test_p6_a_baseline_digline_could_not_read_is_digline_s(tmp_path: Path) -> None:
    """Bare, with no wrap: the store reads through `pathlib`, and the
    `PermissionError` reaches a front end as it is."""
    baselines = tmp_path / ".digline" / "acme" / "baselines"
    baselines.mkdir(parents=True)
    baseline = baselines / "qa.json"
    baseline.write_text("{}", encoding="utf-8")
    with mode_000(baseline), pytest.raises(PermissionError) as caught:
        FileResultStore(tmp_path).read_baseline("acme", "qa")
    assert raised_inside_digline(caught.value)
    said = agent(caught.value)
    assert said == str(caught.value)
    assert WITHHELD not in said


# --------------------------------------------------------------------------- #
# The edges of the rule
# --------------------------------------------------------------------------- #


def test_a_c_function_digline_calls_was_already_digline_s(tmp_path: Path) -> None:
    """`os.replace` has no Python frame, so the innermost one is digline's.
    It was the half of §1's exception that did not hold: the same act, digline
    doing I/O, read as digline's here and as the suite's through `pathlib`."""
    directory = tmp_path / "taken"
    directory.mkdir()
    (directory / "f").write_text("x", encoding="utf-8")
    with pytest.raises(OSError) as caught:
        _write_atomic(directory, "{}")
    assert written_by_digline(caught.value)


@without_mode_000
def test_a_standard_module_digline_calls_is_digline_s(tmp_path: Path) -> None:
    """`tempfile.mkstemp` is Python, so the innermost frame is `tempfile`'s."""
    directory = tmp_path / "read-only"
    directory.mkdir()
    directory.chmod(0o500)
    try:
        with pytest.raises(PermissionError) as caught:
            _write_atomic(directory / "x.json", "{}")
    finally:
        directory.chmod(0o755)
    assert written_by_digline(caught.value)


def test_words_that_are_not_the_system_s_are_not_digline_s() -> None:
    """Digline asked, and urllib answered in words of its own:
    `<urlopen error [Errno …] …>`. A message a library or a peer wrote is
    somebody else's whoever asked, so only digline's sentence crosses, and the
    `errno`'s description it read off the exception."""
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        port = taken.getsockname()[1]
    target = HttpTarget(
        f"http://127.0.0.1:{port}/answer", body={"q": "x"}, output_path="answer"
    )
    with pytest.raises(Exception) as caught:
        target.preflight([])
    assert "<urlopen error" in str(caught.value)
    said = agent(caught.value)
    assert "<urlopen error" not in said, said


def test_a_module_frozen_into_the_interpreter_is_the_standard_library() -> None:
    """`os` is frozen since 3.11, so `os.fdopen`, which `file_store` calls,
    has a frame named `<frozen os>` and no file. Asked from digline's code, its
    `OSError` is digline's."""
    with pytest.raises(OSError) as caught:
        exec(  # noqa: S102
            compile("import os\nos.fdopen(987654)", INSIDE_DIGLINE, "exec"), {}
        )
    assert written_by_digline(caught.value)


def test_the_system_s_words_are_rebuilt_not_trusted() -> None:
    """An `errno` with words of its own, raised where digline's code is. The
    frame says digline asked, and the words still say they are not the
    system's."""
    with pytest.raises(OSError) as caught:
        exec(  # noqa: S102
            compile("raise OSError(2, words)", INSIDE_DIGLINE, "exec"),
            {"words": f"no such row {MARKER}"},
        )
    assert raised_inside_digline(caught.value)
    assert not written_by_digline(caught.value)
    assert MARKER not in agent(caught.value)


def test_a_suite_module_named_like_a_standard_one_is_not_the_standard_library(
    tmp_path: Path,
) -> None:
    """`colorsys` is a standard module's name. A suite's helper called
    `colorsys.py` is still the suite's: a frame is the standard library's by
    where its file is."""
    (tmp_path / "colorsys.py").write_text(
        "from pathlib import Path\n\n"
        "def read(row):\n"
        "    raise FileNotFoundError(2, 'No such file or directory', row)\n",
        encoding="utf-8",
    )
    refused = refused_loading(
        tmp_path,
        HEAD + "import colorsys\ncolorsys.read('/nonexistent/' + ROW['iban'])\n",
    )
    sys.modules.pop("colorsys", None)
    said = agent(refused)
    assert MARKER not in said, said
    assert str(tmp_path.resolve() / "colorsys.py") in said, said


@without_mode_000
def test_installed_packages_inside_the_standard_library_are_not_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On some installs `site-packages` is a directory inside the standard
    library's, and digline is installed in it. Laid out that way here, by
    putting digline's parent inside the standard library: digline's own read
    is still digline's, because installed packages are not the standard
    library wherever they sit."""
    installed = Path(digline.__file__).resolve().parent.parent
    monkeypatch.setattr(authorship, "_STDLIB", (*authorship._STDLIB, installed.parent))  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(authorship, "_INSTALLED", (installed,))
    baselines = tmp_path / ".digline" / "acme" / "baselines"
    baselines.mkdir(parents=True)
    baseline = baselines / "qa.json"
    baseline.write_text("{}", encoding="utf-8")
    with mode_000(baseline), pytest.raises(PermissionError) as caught:
        FileResultStore(tmp_path).read_baseline("acme", "qa")
    assert written_by_digline(caught.value)


def test_a_location_outside_digline_skips_only_the_standard_library() -> None:
    """For any other exception `frames_outside` is what it was: the standard
    library's frames are skipped for an `OSError` alone."""
    import json

    with pytest.raises(ValueError) as caught:
        json.loads("{")
    assert any("json" in at for at in frames_outside(caught.value))
