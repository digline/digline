"""The suite a tool names has to be inside this server's repository.

ADR 0011 §8 says "one server, one repository", and until 0.1.1 nothing enforced
it: `suite` arrived from a tool call and went to `load_suite`, which **executes**
a `.py`. Every tool was therefore a way to run a file from anywhere on the disk —
including the reading tools, which declare `read_only_hint=True` (five then,
seven since `explain` and `log` in 0.1.3), the annotation a client reads to
decide it may call something without asking a person first.

So the test that matters is not "was it refused" but **"did it run"**: the suite
outside the root writes a file, and every case here asserts that file was never
written. A refusal that arrived after the exec would look identical from the
outside and would be worth nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from digline.wire import EXIT_USAGE
from digline_mcp import server
from digline_mcp.server import build_server

#: A suite that is valid — it loads, it has a target, it would run — so that
#: what is being tested is the boundary and not a parse error somewhere.
OUTSIDE_SUITE = """
from pathlib import Path

Path({sentinel!r}).write_text("executed")

from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="The capital is Rome.", input="q", cost_usd=0.01,
                    latency_ms=100.0)
"""

#: Every tool, with the arguments it needs beyond `suite`. All eight, because the
#: defect was in the funnel they all cross and a fix that reached seven of them
#: would leave the eighth as the whole vulnerability.
TOOLS: tuple[tuple[str, dict[str, object]], ...] = (
    ("list_runs", {}),
    ("get_run", {}),
    ("get_baseline", {}),
    ("log", {}),
    ("compare", {}),
    ("diff", {"run1": "latest", "run2": "latest"}),
    ("explain", {}),
    ("run", {"acknowledge_calls": 1}),
)


@pytest.fixture
def outside(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A root, a suite that is not in it, and the file that suite would write."""
    root = tmp_path / "repo"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    sentinel = tmp_path / "executed"
    suite = elsewhere / "suite_qa.py"
    suite.write_text(OUTSIDE_SUITE.format(sentinel=str(sentinel)), encoding="utf-8")
    return root, suite, sentinel


def call(root: Path, name: str, arguments: dict[str, object]) -> str:
    async def go() -> str:
        server = build_server(str(root), None, None, names="clear", table=None)
        try:
            result = await server.call_tool(name, arguments)
        except ToolError as refusal:
            return str(refusal)
        assert isinstance(result, CallToolResult)
        return ""

    return anyio.run(go)


@pytest.mark.parametrize(("name", "extra"), TOOLS, ids=[n for n, _ in TOOLS])
def test_a_suite_outside_the_root_is_refused_and_never_runs(
    outside: tuple[Path, Path, Path], name: str, extra: dict[str, object]
) -> None:
    root, suite, sentinel = outside
    refusal = call(root, name, {"suite": str(suite), **extra})
    assert "one server, one repository" in refusal, refusal
    assert "ADR 0011 §8" in refusal
    # The line the whole file exists for.
    assert not sentinel.exists(), f"{name} executed a suite outside {root}"


@pytest.mark.parametrize(("name", "extra"), TOOLS, ids=[n for n, _ in TOOLS])
def test_a_traversal_out_of_the_root_is_refused_and_never_runs(
    outside: tuple[Path, Path, Path], name: str, extra: dict[str, object]
) -> None:
    """The same escape written relatively, which is how it would actually
    arrive: a path that looks like it is inside until it is resolved."""
    root, _suite, sentinel = outside
    spec = "../elsewhere/suite_qa.py"
    refusal = call(root, name, {"suite": spec, **extra})
    assert "one server, one repository" in refusal, refusal
    assert not sentinel.exists(), f"{name} executed a suite outside {root}"


def test_the_refusal_names_the_path_it_resolved_to(
    outside: tuple[Path, Path, Path],
) -> None:
    """A relative spec and the file it lands on are different sentences, and the
    one worth printing is the second: `../elsewhere/suite_qa.py` tells a reader
    nothing about which repository it left."""
    root, suite, _sentinel = outside
    refusal = call(root, "list_runs", {"suite": "../elsewhere/suite_qa.py"})
    assert str(suite) in refusal
    assert str(root.resolve()) in refusal


def test_a_module_path_is_refused_because_it_cannot_be_placed(
    outside: tuple[Path, Path, Path],
) -> None:
    """The dotted form resolves through `sys.path`, so this server cannot say it
    is in the repository — and a perimeter that cannot check is not one. The CLI
    still takes it: a person's tool has no perimeter to keep."""
    root, _suite, _sentinel = outside
    refusal = call(root, "list_runs", {"suite": "some.installed.module"})
    assert "names no file inside" in refusal
    assert "sys.path" in refusal


def test_a_suite_inside_the_root_still_loads(repo: Path) -> None:
    """The guard on the guard: a containment check that refused everything would
    pass every test above and ship a server that does nothing."""
    assert call(repo, "list_runs", {"suite": "suite_qa.py"}) == ""
    assert call(repo, "list_runs", {"suite": str(repo / "suite_qa.py")}) == ""


def test_the_root_is_never_implied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without `--root` the server does not start. Every tool loads the suite
    it is named under the root, and a `suite.py` is the project's code, so a
    root taken from the working directory the client launched in is how the
    suite of the wrong directory gets run. `server.json` declares it required,
    and this is what makes that declaration true."""

    def started(*_args: object) -> None:
        raise AssertionError("a server was built without a root")

    monkeypatch.setattr(server, "build_server", started)
    with pytest.raises(SystemExit) as stopped:
        server.main([])
    # 64 and no longer argparse's 2: a refused command line is a usage error,
    # as ADR 0008 §1 says for the CLI, and 2 is `EXIT_UNJUDGED`, a verdict
    # this server never gave. The same parser rule as `digline`'s.
    assert stopped.value.code == EXIT_USAGE
    assert "--root" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (
            ["--root", ".", "--names", "clear", "--no-such-flag"],
            "unrecognized arguments: --no-such-flag",
        ),
        (["--root"], "argument --root: expected one argument"),
    ],
    ids=["unknown flag", "missing value"],
)
def test_a_refused_command_line_exits_64(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    said: str,
) -> None:
    """`digline-mcp` is a second program with a parser of its own, and the
    usage error is the same fact there: 64, never `EXIT_UNJUDGED`'s 2.
    (ADR 0008 §1)"""

    def started(*_args: object) -> None:
        raise AssertionError("a server was built from a refused command line")

    monkeypatch.setattr(server, "build_server", started)
    with pytest.raises(SystemExit) as stopped:
        server.main(argv)
    assert said in capsys.readouterr().err
    assert stopped.value.code == EXIT_USAGE, (
        f"digline-mcp {' '.join(argv)} exited {stopped.value.code}, not 64"
    )


# --------------------------------------------------------------------------- #
# An option given different values is refused (#567)
# --------------------------------------------------------------------------- #


def options_taking_a_value(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Read off the server's own usage line, so an option added tomorrow is in
    the tests without anybody adding it here: every option followed by a
    metavar takes a value."""
    with pytest.raises(SystemExit):
        server.main(["--help"])
    usage = " ".join(capsys.readouterr().out.split("\n\n", 1)[0].split())
    return re.findall(r"(--[a-z-]+) (?:[A-Z]|\{)", usage)


def started_with(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> tuple[str | int | None, str, tuple[object, ...] | None]:
    """The exit code and stderr if the command line was refused, or the
    arguments `build_server` would have started with. No server starts."""
    received: list[tuple[object, ...]] = []

    class Stopped:
        def run(self, **_kwargs: object) -> None:
            pass

    def recorder(*args: object, **kwargs: object) -> Stopped:
        received.append((*args, *kwargs.values()))
        return Stopped()

    monkeypatch.setattr(server, "build_server", recorder)

    # A table named on the line is imported at start; here, a stand-in.
    def stand_in(spec: str) -> str:
        return spec

    monkeypatch.setattr(server, "load_name_table", stand_in)
    try:
        server.main(argv)
    except SystemExit as stopped:
        return stopped.code, capsys.readouterr().err, None
    return None, capsys.readouterr().err, received[0]


def test_the_server_has_options_that_take_a_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert options_taking_a_value(capsys) == [
        "--root",
        "--tenant",
        "--env",
        "--names",
        "--name-table",
    ]


# The options are listed by hand here, where the CLI's tests derive them from
# the parser: `main()` builds this parser inside itself, and there is no
# parser to read. `test_the_server_has_options_that_take_a_value` is what keeps
# the list in line with the usage line, so the asymmetry is chosen, not
# forgotten.
#: Two values each option accepts, and the rest of a line that starts: `--names`
#: takes one of its two words, and `--name-table` is read under `project`.
_VALUES: dict[str, tuple[str, str]] = {
    "--root": ("first", "second"),
    "--tenant": ("first", "second"),
    "--env": ("first", "second"),
    "--names": ("clear", "project"),
    "--name-table": ("first:table", "second:table"),
}


def _line(option: str, value: str, again: str) -> list[str]:
    rest = {"--root": ["--root", "r"], "--names": ["--names", "clear"]}
    if option == "--name-table":
        rest["--names"] = ["--names", "project"]
    rest.pop(option, None)
    return [
        *(arg for pair in rest.values() for arg in pair),
        option,
        value,
        option,
        again,
    ]


@pytest.mark.parametrize("option", list(_VALUES))
def test_an_option_given_two_values_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], option: str
) -> None:
    """Measured before this: `--root a --root b` started the server on `b`, and
    `--tenant` and `--env` kept their last value the same way."""
    first, second = _VALUES[option]
    argv = _line(option, first, second)
    code, err, started = started_with(monkeypatch, capsys, argv)
    assert code == EXIT_USAGE, (
        f"digline-mcp {' '.join(argv)} started with {started}: one of the two "
        "values was dropped without a word (#567)"
    )
    assert f"argument {option}: given different values ({first!r}, {second!r})" in err


@pytest.mark.parametrize("option", list(_VALUES))
def test_an_option_given_the_same_value_twice_is_accepted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], option: str
) -> None:
    same = _VALUES[option][0]
    argv = _line(option, same, same)
    code, err, started = started_with(monkeypatch, capsys, argv)
    assert started is not None, f"refused (exit {code}): {err}"
    assert same in started
