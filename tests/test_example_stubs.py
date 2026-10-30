"""Each example's stub is a second witness: it writes a line for every call it
receives, and nothing when it receives none.

Three examples answer over HTTP from a stub that stands in for the application:
`quickstart-toml`'s `stub.py`, a process of its own, and `langchain4j`'s
`stub.py` and `external-app`'s `server.py`, which the suite starts in its own
process. Until 2026-10-30 all three silenced `log_message`, so a sentence such
as *"Nothing was called"* was digline's word and nobody else's.

Every stub now writes, on standard error, one line per call, in one format:

    stub: call <n> POST <path> <field>=<value>

where `<field>` is what tells one case from another, `question` or `text`. The
liveness `HEAD` that digline sends before the first case is not a call to the
target, costs nothing, and writes no line.

**Both halves are held, for each stub:**
- a run that calls writes exactly as many lines as `digline run` announced
  calls to the target;
- a run that digline refuses before calling, here because the baseline is at a
  schema this digline does not read, writes none, beside its own *"Nothing was
  called"*.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from tests._helpers import cli, copy_tracked

from digline.cli import EXIT_OK, EXIT_USAGE
from digline.core.run import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]

#: A stub's line for one call.
CALL = re.compile(r"^stub: call (\d+) POST (/\S+) (question|text)=.+$")

#: The announced number of calls, from `digline run`'s plan sentence.
PLANNED = re.compile(r"= (\d+) calls? to the target")

#: Each example with a stub, its suite file, and whether the stub is a process
#: of its own (`quickstart-toml`) or starts inside the suite.
STUBS = {
    "quickstart-toml": ("suite.toml", True),
    "langchain4j": ("suite.py", False),
    "external-app": ("suite.py", False),
}


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def _own_process_stub(workdir: Path, log: Path) -> Generator[None]:
    """`quickstart-toml`'s stub on a port of its own, its stderr kept in `log`."""
    port = _free_port()
    suite = workdir / "suite.toml"
    text = suite.read_text(encoding="utf-8")
    url = 'url = "http://127.0.0.1:8730/answer"'
    assert text.count(url) == 1
    suite.write_text(
        text.replace(url, f'url = "http://127.0.0.1:{port}/answer"'), encoding="utf-8"
    )
    with log.open("w", encoding="utf-8") as err:
        process = subprocess.Popen(  # noqa: S603 - our own stub, in our own tree
            [sys.executable, "-u", "stub.py"],
            cwd=workdir,
            env={**os.environ, "STUB_PORT": str(port)},
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
        )
        try:
            said: list[str] = []
            out = process.stdout
            assert out is not None
            reader = threading.Thread(target=lambda: said.append(out.readline()))
            reader.start()
            reader.join(10)
            assert said and said[0].strip().endswith(f":{port}/answer"), said
            yield
        finally:
            process.terminate()
            process.wait(timeout=10)
            if process.stdout is not None:
                process.stdout.close()


def _calls(text: str) -> list[str]:
    return [line for line in text.splitlines() if CALL.match(line)]


def _make_unreadable(workdir: Path) -> None:
    """The copy's committed baseline, declared at the schema before this one."""
    (baseline,) = sorted(workdir.glob(".digline/*/baselines/*.json"))
    document = json.loads(baseline.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    baseline.write_text(json.dumps(document), encoding="utf-8")


def _copy(name: str, tmp_path: Path) -> Path:
    workdir = tmp_path / name
    copy_tracked(ROOT / "examples" / name, workdir)
    return workdir


def _stub_lines(
    name: str, ran: subprocess.CompletedProcess[str], log: Path
) -> list[str]:
    """The call lines this stub wrote: in its own log for a stub that is a
    process of its own, on `digline run`'s stderr for one the suite starts."""
    if STUBS[name][1]:
        return _calls(log.read_text(encoding="utf-8"))
    return _calls(ran.stderr)


@pytest.mark.parametrize("name", sorted(STUBS))
def test_a_run_that_calls_gets_a_stub_line_per_call(name: str, tmp_path: Path) -> None:
    suite, own_process = STUBS[name]
    workdir = _copy(name, tmp_path)
    log = tmp_path / f"{name}.stub.log"
    with _own_process_stub(workdir, log) if own_process else _nothing():
        ran = cli(workdir, "run", "--suite", suite)
        assert ran.returncode == EXIT_OK, ran.stderr
        planned = PLANNED.search(ran.stderr)
        assert planned is not None, ran.stderr
        lines = _stub_lines(name, ran, log)
    assert len(lines) == int(planned.group(1)), (lines, ran.stderr)
    numbers = [int(m.group(1)) for line in lines if (m := CALL.match(line))]
    assert numbers == list(range(1, len(lines) + 1))


@pytest.mark.parametrize("name", sorted(STUBS))
def test_a_run_digline_refuses_gets_no_stub_line(name: str, tmp_path: Path) -> None:
    """The stub is up and listening, and digline refuses before the first call:
    its own sentence says *Nothing was called*, and the stub says the same by
    writing nothing."""
    suite, own_process = STUBS[name]
    workdir = _copy(name, tmp_path)
    _make_unreadable(workdir)
    log = tmp_path / f"{name}.stub.log"
    with _own_process_stub(workdir, log) if own_process else _nothing():
        refused = cli(workdir, "run", "--suite", suite)
        lines = _stub_lines(name, refused, log)
    assert refused.returncode == EXIT_USAGE, refused.stderr
    assert "Nothing was called" in refused.stderr
    assert lines == [], lines


@contextmanager
def _nothing() -> Generator[None]:
    yield
