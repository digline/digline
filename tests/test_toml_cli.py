"""The declarative format, through the command line.

`test_toml_suite.py` asks whether the loader builds the right objects. This
asks the question a user asks: **does `digline run --suite suite.toml` do what
`digline run --suite suite.py` does?** The whole cycle — run, promote, compare,
and the exit codes that are the answer — against a real endpoint, with a suite
that contains no Python at all.

`main()` is called in this process rather than through `subprocess`, unlike
`test_cli.py`, for one reason: a provider plugin is resolved from installed
metadata, and a fake one registered with `monkeypatch` does not survive a fork.
What is under test here is the CLI's own dispatch, and that is the same code
either way.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from digline.cli import EXIT_OK, EXIT_USAGE, EXIT_WORSE
from digline.cli.main import main

ANSWER = "Order 4821 ships Thursday. — Northwind Support"

SUITE = """
[suite]
tenant = "northwind"
environment = "staging"
name = "support"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:{port}/answer"
output_path = "data"
cost_path = "usage.cost_usd"

  [target.body]
  question = "case.vars.question"

[[assertions]]
type = "contains"
needle = "Northwind Support"

[[assertions]]
type = "cost_budget"
max_usd = 0.02
tolerance = 0.05
"""

CASES = json.dumps(
    [{"id": "where-is-my-order", "vars": {"question": "Where is order 4821?"}}]
)


class Endpoint(BaseHTTPRequestHandler):
    """An application digline cannot import, which is the case the format is
    for. It echoes the body so a test can see what the suite declared."""

    answer = ANSWER
    #: What the last POST carried. The only way to see the rendered body: the
    #: payload does not travel into a run by default (fixed decision 9), so the
    #: run document cannot answer this question and should not be able to.
    posted: dict[str, object] = {}

    def do_HEAD(self) -> None:  # noqa: N802 - the base class names it
        self.send_response(200)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - the base class names it
        length = int(self.headers["Content-Length"])
        posted = json.loads(self.rfile.read(length))
        type(self).posted = posted
        payload = {
            "data": type(self).answer,
            "usage": {"cost_usd": 0.004},
            "echo": posted,
        }
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Quiet: the test's output is the test's.

        The parameter is named as the base class names it — pyright checks the
        override, and `format` shadowing a builtin is theirs, not ours.
        """


@pytest.fixture
def endpoint() -> Iterator[int]:
    """The application, on a port the operating system picks."""
    Endpoint.answer = ANSWER
    Endpoint.posted = {}
    server = HTTPServer(("127.0.0.1", 0), Endpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def workdir(tmp_path: Path, endpoint: int, fake_provider: None) -> Path:
    (tmp_path / "suite.toml").write_text(SUITE.format(port=endpoint), encoding="utf-8")
    (tmp_path / "cases.json").write_text(CASES, encoding="utf-8")
    return tmp_path


def digline(workdir: Path, *args: str) -> int:
    return main([*args, "--suite", str(workdir / "suite.toml"), "--root", str(workdir)])


# --------------------------------------------------------------------------- #
# The cycle, with no Python anywhere
# --------------------------------------------------------------------------- #


def test_the_whole_cycle_runs_from_a_suite_that_is_data(
    workdir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """run, promote, compare — and the exit code is the answer, exactly as the
    front page says of the Python form."""
    assert digline(workdir, "run") == EXIT_OK
    assert digline(workdir, "promote", "--run", "latest") == EXIT_OK
    assert digline(workdir, "compare", "--run", "latest") == EXIT_OK
    assert "Nothing got worse" in capsys.readouterr().out


def test_a_regression_in_a_data_suite_exits_one(
    workdir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sign-off leaves the answer, and the gate has to notice."""
    assert digline(workdir, "run") == EXIT_OK
    assert digline(workdir, "promote", "--run", "latest") == EXIT_OK

    Endpoint.answer = "Order 4821 ships Thursday."
    assert digline(workdir, "run") == EXIT_OK
    assert digline(workdir, "compare", "--run", "latest") == EXIT_WORSE
    assert "contains" in capsys.readouterr().out


def test_the_run_lands_in_the_repository_the_suite_sits_in(workdir: Path) -> None:
    """`.digline/<tenant>/` inside the user's repo, whatever the suite is
    written in (fixed decision 2)."""
    assert digline(workdir, "run") == EXIT_OK
    assert (workdir / ".digline" / "northwind" / "runs" / "support").is_dir()
    assert (workdir / ".digline" / ".gitignore").is_file()


def test_the_declared_body_is_what_was_posted(workdir: Path) -> None:
    """The table is the payload, with this case's value in it.

    Asserted on what the endpoint received, not on what the run recorded: an
    unresolved `"case.vars.question"` would have been posted happily and every
    assertion would still have passed, so the run document cannot tell the two
    apart. The application can.
    """
    assert digline(workdir, "run") == EXIT_OK
    assert Endpoint.posted == {"question": "Where is order 4821?"}


# --------------------------------------------------------------------------- #
# What the command line refuses
# --------------------------------------------------------------------------- #


def test_target_is_refused_beside_a_data_suite(
    workdir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A flag pointing at a Python attribute would be the escape hatch ADR 0007
    §5 refuses, entered through the command line."""
    code = main(
        [
            "run",
            "--suite",
            str(workdir / "suite.toml"),
            "--root",
            str(workdir),
            "--target",
            "somewhere:target",
        ]
    )
    assert code == EXIT_USAGE
    message = capsys.readouterr().err
    assert "--target does not apply" in message
    assert "suite.py" in message


def test_a_missing_toml_file_says_where_it_looked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["run", "--suite", str(tmp_path / "nope.toml"), "--root", str(tmp_path)]
    )
    assert code == EXIT_USAGE
    assert "no such file" in capsys.readouterr().err


def test_the_extension_is_what_chooses_the_format(
    workdir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No flag decides this. A file named `.toml` that holds Python is a TOML
    parse error, not an import — which is the point: the suffix is the whole
    rule (ADR 0007 §6)."""
    (workdir / "confused.toml").write_text("suite = Suite(", encoding="utf-8")
    code = main(
        [
            "run",
            "--suite",
            str(workdir / "confused.toml"),
            "--root",
            str(workdir),
        ]
    )
    assert code == EXIT_USAGE
    assert "not valid TOML" in capsys.readouterr().err
