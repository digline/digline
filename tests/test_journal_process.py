"""Which process a journal belongs to, and whether it is still running. (#478)

A journal whose process is alive looked exactly like one whose process was
killed, so `run` invited a `--resume` of a run another process was still
executing, and the resume was accepted: two processes on one key, both paying
for the cases neither had finished. Each leg's header now records the process
and the host that opened it, and the invitation says whether that process is
running, has ended, or cannot be told from here. **It stays an invitation**:
nothing is refused and no lock is taken (ADR 0017 §5).

The process is the **last** leg's: after a resume, the first leg's process is
the one that was killed. And it is never a fact the run asserts, so
`differences()` must not see it: every leg is opened by another process, and a
resume compared on its pid would never be accepted.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from tests._helpers import cli
from tests.test_journal import (
    JOURNALLED_SUITE,
    SUITE,
    TENANT,
    Counting,
    a_suite,
    killed,
    launch,
    legs,
    records,
)

from digline.host import process_state, this_process
from digline.store import FileResultStore

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="a pid is probed with a POSIX signal 0"
)


def test_differences_ignores_the_process_and_the_host(tmp_path: Path) -> None:
    """Pinned because nothing held it: the list `differences()` reads is the
    facts a run document asserts, and these two are not among them."""
    _, prepared = launch(tmp_path, a_suite(), Counting())
    header = prepared.header
    other = replace(header, pid=(header.pid or 0) + 1, host="another-host")
    assert header.differences(other) == ()
    assert other.differences(header) == ()


def test_prepare_records_this_process_and_this_host(tmp_path: Path) -> None:
    _, prepared = launch(tmp_path, a_suite(), Counting())
    assert (prepared.header.pid, prepared.header.host) == this_process()
    assert this_process() == (os.getpid(), socket.gethostname())


def test_the_leg_s_header_carries_them_and_reads_them_back(tmp_path: Path) -> None:
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    (first,) = legs(tmp_path, key)
    header = records(first)[0]
    assert (header["pid"], header["host"]) == this_process()
    (found,) = FileResultStore(tmp_path).pending(TENANT, SUITE)
    assert (found.pid, found.host) == this_process()


def test_a_header_written_before_them_is_still_read(tmp_path: Path) -> None:
    """`JOURNAL_VERSION` does not move: a journal an older digline left is still
    finished by this one, with no process recorded."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    (first,) = legs(tmp_path, key)
    lines = first.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    del header["pid"], header["host"]
    first.write_text(
        "\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8"
    )
    (found,) = FileResultStore(tmp_path).pending(TENANT, SUITE)
    assert found.refusal == ""
    assert (found.pid, found.host) == (None, "")


def test_the_process_is_the_newest_leg_s(tmp_path: Path) -> None:
    """After a resume the first leg's process is the one that was killed, and
    the one that may still be running is the newest leg's."""
    key = killed(tmp_path, a_suite(), Counting(die_at=3))
    store, prepared = launch(tmp_path, a_suite(), Counting(), resume_key=key)
    store.open_journal(replace(prepared.header, pid=4242, host="the-second-host"))
    assert len(legs(tmp_path, key)) == 2
    (found,) = store.pending(TENANT, SUITE)
    assert found.refusal == "", found.refusal
    assert (found.pid, found.host) == (4242, "the-second-host")


# --- whether it is running --------------------------------------------------------


def test_this_process_is_running() -> None:
    assert process_state(os.getpid(), socket.gethostname()) == "running"


def test_a_process_that_exited_has_ended() -> None:
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    assert process_state(done.pid, socket.gethostname()) == "ended"


def test_another_host_cannot_be_told_from_here() -> None:
    assert process_state(os.getpid(), "not-" + socket.gethostname()) == "elsewhere"


def test_no_process_recorded_cannot_be_told_either() -> None:
    assert process_state(None, "") == "unknown"


# --- the invitation ----------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "suite.py").write_text(JOURNALLED_SUITE, encoding="utf-8")
    (tmp_path / "calls.txt").write_text("", encoding="utf-8")
    (tmp_path / "die.txt").write_text("2", encoding="utf-8")
    return tmp_path


def test_the_invitation_says_the_killed_process_has_ended(project: Path) -> None:
    assert cli(project, "run", "--suite", "suite.py").returncode == 9
    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    assert "was started and never written" in done.stderr
    assert "has ended" in done.stderr
    # Still an invitation, whatever the process is doing.
    assert "--resume" in done.stderr


def test_the_invitation_says_a_live_process_is_still_running(project: Path) -> None:
    """The case #478 is about, staged without a race: the killed leg's header is
    given this test's own pid, which is running for as long as the test is."""
    assert cli(project, "run", "--suite", "suite.py").returncode == 9
    (leg,) = sorted((project / ".digline").rglob("*.jsonl"))
    lines = leg.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["pid"], header["host"] = os.getpid(), socket.gethostname()
    leg.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8")
    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py")
    assert done.returncode == 0, done.stderr
    assert f"pid {os.getpid()}" in done.stderr
    assert "is still running" in done.stderr
    assert "--resume" in done.stderr


def test_the_invitation_says_another_host_cannot_be_told(project: Path) -> None:
    assert cli(project, "run", "--suite", "suite.py").returncode == 9
    (leg,) = sorted((project / ".digline").rglob("*.jsonl"))
    lines = leg.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["host"] = "build-agent-7"
    leg.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8")
    (project / "die.txt").write_text("99", encoding="utf-8")
    done = cli(project, "run", "--suite", "suite.py")
    assert "build-agent-7" in done.stderr
    assert "cannot be told from here" in done.stderr
    assert "--resume" in done.stderr
