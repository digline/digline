"""The gate is not traffic: a `digline run` leaves a marker while it is in
progress, every writer of recordings in another process still records a call
made then and marks it the gate's, and every reader keeps it apart. (ADR 0058
§4 and ADR 0062 §2, as amended 2026-11-05)

The end-to-end case is the one the marker exists for: `digline run`, as a
process of its own, with a `[target] http` pointed at an application that
calls its model through `digline record proxy`.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests.test_record_proxy import Upstream, proxying
from tests.test_recorder_switch import an_anthropic, ask

from digline import recorder
from digline.cli.main import main
from digline.core.recording import (
    GATE_ORIGIN,
    Recording,
    RecordingRefusedError,
    recording_from_dict,
    recording_to_dict,
)
from digline.core.run import key_of
from digline.host import gate, recorder_status, switch_on
from digline.host.gate import GATE_DIRECTORY, gate_markers, marking
from digline.host.importing import read_recordings
from digline.host.measure import measure, prepare
from digline.run import Case, Response, Suite
from digline.store.file_store import FileResultStore

#: The SDKs this module loads leave with it, as in `tests/test_record_proxy.py`.
SDKS = ("anthropic", "openai", "httpx2")

KEY = "2026-11-05T12-30-00-123456-00-00-0123456789abcdef"


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


def place(root: Path) -> Path:
    return root.joinpath(".digline", "acme", *GATE_DIRECTORY)


def plant(root: Path, name: str, document: object, *, age: float = 0.0) -> Path:
    """A marker as a run writes one, its time set back by `age` seconds."""
    directory = place(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        document if isinstance(document, str) else json.dumps(document),
        encoding="utf-8",
    )
    then = time.time() - age
    os.utime(path, (then, then))
    return path


def marker(run_id: str = KEY) -> dict[str, object]:
    return {"run_id": run_id, "pid": 1, "started_at": "x", "suite": "triage"}


# -- the marker ----------------------------------------------------------------- #


def test_a_run_in_progress_has_a_marker_and_leaves_nothing_when_it_ends(
    tmp_path: Path,
) -> None:
    with marking(
        tmp_path,
        "acme",
        run_id=KEY,
        started_at="2026-11-05T12:30:00+00:00",
        suite="triage",
    ):
        [path] = list(place(tmp_path).iterdir())
        assert path.name == f"{os.getpid()}-{KEY}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "run_id": KEY,
            "pid": os.getpid(),
            "started_at": "2026-11-05T12:30:00+00:00",
            "suite": "triage",
        }
        assert gate_markers(tmp_path, "acme").run_id == KEY
    assert not place(tmp_path).exists()
    assert place(tmp_path).parent.is_dir()


def test_a_run_that_raises_removes_its_marker_too(tmp_path: Path) -> None:
    with (
        pytest.raises(RuntimeError, match="the target broke"),
        marking(tmp_path, "acme", run_id=KEY, started_at="x", suite="triage"),
    ):
        raise RuntimeError("the target broke")
    assert not place(tmp_path).exists()


def test_another_runs_marker_keeps_the_directory_and_its_own_place(
    tmp_path: Path,
) -> None:
    other = plant(tmp_path, "1-other.json", marker("other"))
    with marking(tmp_path, "acme", run_id=KEY, started_at="x", suite="triage"):
        assert len(gate_markers(tmp_path, "acme").live) == 2
    assert [path.name for path in place(tmp_path).iterdir()] == [other.name]


def test_the_heart_touches_the_marker_so_a_long_run_stays_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "HEARTBEAT_SECONDS", 0.05)
    with marking(tmp_path, "acme", run_id=KEY, started_at="x", suite="triage"):
        [path] = list(place(tmp_path).iterdir())
        then = time.time() - 1000
        os.utime(path, (then, then))
        assert gate_markers(tmp_path, "acme").live == ()
        deadline = time.monotonic() + 5
        while not gate_markers(tmp_path, "acme").live and time.monotonic() < deadline:
            time.sleep(0.05)
        assert gate_markers(tmp_path, "acme").run_id == KEY


def test_a_marker_untouched_past_the_staleness_is_a_run_that_died(
    tmp_path: Path,
) -> None:
    plant(tmp_path, f"1-{KEY}.json", marker(), age=gate.STALE_SECONDS + 60)
    plant(tmp_path, "2-live.json", marker("live"), age=gate.STALE_SECONDS - 60)
    found = gate_markers(tmp_path, "acme")
    assert [m.run_id for m in found.stale] == [KEY]
    assert [m.run_id for m in found.live] == ["live"]
    assert found.run_id == "live"


@pytest.mark.parametrize(
    "markers",
    [
        [("1-a.json", marker("a")), ("2-b.json", marker("b"))],
        [("1-a.json", "not JSON")],
        [("1-a.json", "[]")],
        [("1-a.json", marker(""))],
    ],
    ids=["two runs", "not JSON", "not an object", "an empty run_id"],
)
def test_the_gate_without_a_run_where_the_call_cannot_say_which(
    tmp_path: Path, markers: list[tuple[str, object]]
) -> None:
    for name, document in markers:
        plant(tmp_path, name, document)
    found = gate_markers(tmp_path, "acme")
    assert found.live
    assert found.run_id is None
    assert recorder._gate(tmp_path, "acme") == (GATE_ORIGIN, None)  # pyright: ignore[reportPrivateUsage]


def test_a_name_no_reader_reads_is_no_marker(tmp_path: Path) -> None:
    plant(tmp_path, f".1-{KEY}.json.partial", marker())
    plant(tmp_path, f"1-{KEY}.txt", marker())
    assert gate_markers(tmp_path, "acme").live == ()
    assert recorder._gate(tmp_path, "acme") == (None, None)  # pyright: ignore[reportPrivateUsage]


# -- the document --------------------------------------------------------------- #


def a_recording(**fields: Any) -> Recording:
    return recording_from_dict(
        {
            "recording_version": 1,
            "source_tenant": "acme",
            "app": "app",
            "suite": "triage",
            "case": {"messages": [{"role": "user", "content": "q"}]},
            "setup": {"model": "m"},
            "setup_digest": "0000000000000000",
            "response": {
                "output": "a",
                "kind": "text",
                "input": "[]",
                "latency_ms": 1.0,
            },
            "recorded_at": "2026-11-05T08:00:00+00:00",
            **fields,
        }
    )


def test_origin_and_run_id_are_written_where_they_are_and_absent_otherwise() -> None:
    marked = a_recording(origin="gate", run_id=KEY)
    assert (marked.origin, marked.run_id) == ("gate", KEY)
    document = recording_to_dict(marked)
    assert (document["origin"], document["run_id"]) == ("gate", KEY)
    assert recording_from_dict(document) == marked
    alone = recording_to_dict(a_recording(origin="gate"))
    assert alone["origin"] == "gate"
    assert "run_id" not in alone
    plain = recording_to_dict(a_recording())
    assert "origin" not in plain
    assert "run_id" not in plain


@pytest.mark.parametrize(
    ("fields", "refusal"),
    [
        ({"origin": "application"}, "origin is 'gate' or absent"),
        ({"run_id": KEY}, "run_id without origin"),
        ({"origin": "gate", "run_id": ""}, "run_id must be a non-empty string"),
    ],
)
def test_a_document_that_says_otherwise_is_refused(
    fields: dict[str, str], refusal: str
) -> None:
    with pytest.raises(RecordingRefusedError, match=refusal):
        a_recording(**fields)


# -- the writers ---------------------------------------------------------------- #


def written(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline" / "acme" / "recordings").glob("*/*.json"))
        if not path.name.startswith(".")
    ]


def test_the_wrapper_records_a_call_made_during_a_run_and_marks_it(
    tmp_path: Path,
) -> None:
    """The wrapper outside `running()`, in a process a run is not: the case of
    an application in Python that records itself, called by the run."""
    switch_on(tmp_path, "acme", production=False, ceiling=10_000_000)
    client = recorder.wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    plant(tmp_path, f"1-{KEY}.json", marker())
    ask(client)
    first, second = written(tmp_path)
    assert "origin" not in first
    assert (second["origin"], second["run_id"]) == ("gate", KEY)


def test_a_stale_marker_does_not_mark(tmp_path: Path) -> None:
    switch_on(tmp_path, "acme", production=False, ceiling=10_000_000)
    client = recorder.wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    plant(tmp_path, f"1-{KEY}.json", marker(), age=gate.STALE_SECONDS + 60)
    ask(client)
    [only] = written(tmp_path)
    assert "origin" not in only


def test_an_episode_is_marked_as_its_calls_are(tmp_path: Path) -> None:
    switch_on(tmp_path, "acme", production=False, ceiling=10_000_000)
    client = recorder.wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    plant(tmp_path, f"1-{KEY}.json", marker())
    with recorder.episode(client, suite="agent", case={"m": "q"}):
        ask(client)
    episodes = [d for d in written(tmp_path) if "id" in d]
    calls = [d for d in written(tmp_path) if "id" not in d]
    assert [(d["origin"], d["run_id"]) for d in episodes] == [("gate", KEY)]
    assert [(d["origin"], d["run_id"]) for d in calls] == [("gate", KEY)]


# -- the run -------------------------------------------------------------------- #


class Looking:
    """A target that reads, at its call, what a writer would read."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.seen: list[str | None] = []

    def __call__(self, case: Case) -> Response:
        self.seen.append(gate_markers(self.root, "acme").run_id)
        return Response(output="fine", latency_ms=1.0)


def test_measure_marks_the_run_while_it_calls_and_removes_the_mark_after(
    tmp_path: Path,
) -> None:
    from digline.core import Contains

    suite = Suite(
        tenant="acme",
        environment="dev",
        name="triage",
        assertions=[Contains(needle="fine")],
        cases=[Case(id="one"), Case(id="two")],
    )
    target = Looking(tmp_path)
    prepared = prepare(
        suite, target, now="2026-11-05T12:30:00+00:00", git_commit=None, artifacts={}
    )
    measured = measure(
        suite,
        target,
        store=FileResultStore(tmp_path),
        prepared=prepared,
        marker_root=tmp_path,
    )
    key = key_of(measured.run.created_at, measured.run.config_hash)
    assert target.seen == [key, key]
    assert not place(tmp_path).exists()


# -- the readers ---------------------------------------------------------------- #


def file_recordings(root: Path) -> None:
    """One recording of the application's, two of the gate's."""
    directory = root / ".digline" / "acme" / "recordings" / "j1-aaaaaaaa"
    directory.mkdir(parents=True)
    for n, fields in enumerate(
        [{}, {"origin": "gate", "run_id": KEY}, {"origin": "gate"}], 1
    ):
        (directory / f"{n:06d}.json").write_text(
            json.dumps(recording_to_dict(a_recording(**fields))), encoding="utf-8"
        )


def test_every_reader_but_the_status_leaves_the_gate_out(tmp_path: Path) -> None:
    file_recordings(tmp_path)
    found, unreadable = read_recordings(FileResultStore(tmp_path), "acme")
    assert unreadable == 0
    assert [r.origin for r in found] == [None]


def test_the_status_counts_the_gate_apart_and_names_a_marker_left_behind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file_recordings(tmp_path)
    plant(tmp_path, f"1-{KEY}.json", marker(), age=gate.STALE_SECONDS + 60)
    plant(tmp_path, "2-x.json", "not JSON", age=gate.STALE_SECONDS + 60)
    [tenant] = recorder_status(tmp_path, "acme")
    [suite] = tenant.suites
    assert (suite.calls, suite.from_gate) == (1, 2)
    assert tenant.stale_gate_markers == (KEY, None)

    assert main(["record", "status", "--root", str(tmp_path), "--json"]) == 0
    [document] = json.loads(capsys.readouterr().out)["tenants"]
    assert document["recordings"]["stale_gate_markers"] == [KEY, None]
    assert document["recordings"]["suites"][0]["from_gate"] == 2
    assert document["recordings"]["suites"][0]["calls"] == 1

    assert main(["record", "status", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "    2 from gate runs, kept apart: not listed, imported or compared" in out
    assert (
        "  gate markers: 2 left by a run that did not remove it, older than 2 "
        f"minutes and ignored: {KEY}, unreadable"
    ) in out


# -- end to end ----------------------------------------------------------------- #

SUITE = """\
from digline.core import JudgeReply, LlmRubric
from digline.run import Case, CaptureSource, Suite
from digline.targets import HttpTarget


def judge(prompt):
    return JudgeReply(score=1.0, reason="r")


suite = Suite(
    tenant="acme", environment="dev", name="triage",
    assertions=[LlmRubric(rubric="right?", judge=judge, threshold=0.7, tolerance=0.05)],
    cases=[Case(id="capital", vars={"question": "capital of France?"})],
    samples=2,
    min_agreement="2/2",
    capture=CaptureSource(
        cases_file="captured.json", repository="private", check="llm_rubric"
    ),
)
target = HttpTarget(
    url=%(url)r, body={"question": "case.vars.question"}, output_path="answer"
)
"""


class App:
    """An application that answers a question by asking its model through
    the proxy, and a `HEAD` without asking anything."""

    def __init__(self, proxy: str) -> None:
        owner = self
        self.heads = 0

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

            def do_HEAD(self) -> None:  # noqa: N802
                owner.heads += 1
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                asked = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                answer = owner.ask(str(asked["question"]))
                data = json.dumps({"answer": answer}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.proxy = proxy
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/answer"

    def ask(self, question: str) -> str:
        host, port = self.proxy.removeprefix("http://").split(":")
        connection = http.client.HTTPConnection(host, int(port), timeout=10)
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps(
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": question}],
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer sk-test",
                "X-Digline-Suite": "triage",
            },
        )
        reply = json.loads(connection.getresponse().read())
        connection.close()
        return str(reply["choices"][0]["message"]["content"])


def test_a_run_against_an_app_behind_the_proxy_is_recorded_as_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    upstream = Upstream()
    proxy = proxying(tmp_path, upstream)
    app = App(f"http://127.0.0.1:{proxy.port}")
    try:
        (tmp_path / "suite.py").write_text(SUITE % {"url": app.url}, encoding="utf-8")
        ran = subprocess.run(
            [
                sys.executable,
                "-m",
                "digline.cli",
                "run",
                "--suite",
                "suite.py",
                "--root",
                str(tmp_path),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={
                k: v
                for k, v in os.environ.items()
                if k != recorder.ENVIRONMENT_VARIABLE
            },
            timeout=120,
        )
        assert ran.returncode == 0, ran.stderr
        # Outside any run: the application's own traffic, the control.
        app.ask("hours?")
    finally:
        proxy.stop()
        app.server.shutdown()
        upstream.server.shutdown()

    [run_file] = (tmp_path / ".digline" / "acme" / "runs").rglob("*.json")
    run = json.loads(run_file.read_text(encoding="utf-8"))
    key = key_of(run["created_at"], run["config_hash"])
    recordings = written(tmp_path)
    assert app.heads == 1
    # The two calls of the run, in the files' order, then the control's.
    assert [(d.get("origin"), d.get("run_id")) for d in recordings] == [
        ("gate", key),
        ("gate", key),
        (None, None),
    ]
    assert not place(tmp_path).exists()

    code = main(
        [
            "record",
            "import",
            "--tenant",
            "acme",
            "--suite",
            str(tmp_path / "suite.py"),
            "--root",
            str(tmp_path),
        ]
    )
    listing = capsys.readouterr().out
    assert code == 0
    assert "hours?" in listing
    assert "capital of France?" not in listing

    code = main(
        [
            "record",
            "status",
            "--tenant",
            "acme",
            "--root",
            str(tmp_path),
            "--suite",
            str(tmp_path / "suite.py"),
        ]
    )
    status, said = capsys.readouterr()
    assert code == 0, said
    assert (
        "    2 from gate runs, kept apart: not listed, imported or compared" in status
    )
    assert "never imported, 1 in all" in status
