"""A recording is written inside the store, never through a link out of it.
(ADR 0058 §4; the readers' rule since 0.7.2, GHSA-j878-2v6m-m4vx)

The defect this holds shut: `RecordingWriter` created `recordings/<process>/`
with `mkdir(parents=True)` and linked each recording into it, and checked
neither where the path resolved. A `recordings` directory committed as a
symbolic link, which the generated `.gitignore`'s `*/recordings/` does not
match because the pattern names directories only, took the application's
prompts and answers wherever the link pointed. The readers refused such a link;
the writer now refuses it too, and the application's call is not affected: the
call is counted as not recorded, by the recorder's own rule.

Each test is the delta-pass's probe over 1.1.1 (`probe1_symlink_recordings`),
made to fail on 1.1.1 and pass here.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.recorder import wrap
from digline.store.file_store import FileResultStore, PathRefusedError, RecordingWriter

REPLY: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "Paris"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 3},
}
SECRET = "my card is 4111 1111 1111 1111"


def an_anthropic() -> Any:
    httpx2 = importlib.import_module("httpx2")
    http = httpx2.Client(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=REPLY))
    )
    return importlib.import_module("anthropic").Anthropic(
        api_key="test", http_client=http, max_retries=0
    )


def files_under(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*") if path.is_file())


def record_one(project: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=project)
    reply = client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=[{"role": "user", "content": SECRET}],
        suite="triage",
    )
    # The application's call is never the recorder's to fail.
    assert reply.content[0].text == "Paris"  # pyright: ignore[reportAttributeAccessIssue]
    recorder._flush_shared(client._digline_state.shared)  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    return dict(client.digline_counts)


@pytest.fixture
def planted(tmp_path: Path) -> tuple[Path, Path]:
    """A repository whose store carries `acme/recordings` as a committed link
    to a directory outside it."""
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    FileResultStore(project).ensure_layout("acme")
    (project / ".digline" / "acme" / "recordings").symlink_to(outside)
    return project, outside


def test_the_link_is_one_a_clone_carries(planted: tuple[Path, Path]) -> None:
    """The route: the generated `.gitignore` does not keep such a link out of
    git, so a repository can carry it to whoever clones it."""
    project, _ = planted
    ignored = subprocess.run(
        ["git", "-C", str(project), "check-ignore", ".digline/acme/recordings"],
        capture_output=True,
        check=False,
    )
    assert ignored.returncode == 1


def test_a_recordings_link_out_of_the_store_is_not_written_through(
    planted: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, outside = planted
    counts = record_one(project, monkeypatch)
    assert files_under(outside) == []
    assert counts["recorded"] == 0
    assert sum(counts["not_recorded"].values()) == 1


def test_a_tenant_link_out_of_the_store_is_not_written_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".digline").mkdir()
    (project / ".digline" / "acme").symlink_to(outside)
    counts = record_one(project, monkeypatch)
    assert [p for p in files_under(outside) if "recordings" in p.parts] == []
    assert counts["recorded"] == 0


def test_the_writer_refuses_by_name(planted: tuple[Path, Path]) -> None:
    project, outside = planted
    with pytest.raises(PathRefusedError, match="outside"):
        RecordingWriter(FileResultStore(project)).place("acme")
    assert list(outside.iterdir()) == []


def test_a_store_that_is_itself_a_link_still_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control, and the case the readers keep legitimate: a `.digline`
    kept on another volume, reached by a link, is the store itself."""
    project, volume = tmp_path / "project", tmp_path / "volume"
    project.mkdir()
    volume.mkdir()
    (project / ".digline").symlink_to(volume)
    counts = record_one(project, monkeypatch)
    assert counts["recorded"] == 1
    written = [p for p in files_under(volume) if p.suffix == ".json" and p.name[0] != "."]
    assert any(SECRET in json.dumps(json.loads(p.read_text())) for p in written)


def test_the_ceiling_marker_is_not_written_through_a_link(
    planted: tuple[Path, Path],
) -> None:
    project, outside = planted
    recorder._mark_ceiling(project, "acme", 10, 20)  # pyright: ignore[reportPrivateUsage]
    assert list(outside.iterdir()) == []
