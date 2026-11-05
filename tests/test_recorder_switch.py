"""The recorder's switch, its refusals, its interval, its sample and its ceiling,
and the three `digline record` commands. (ADR 0058 §10)

What is held here:

- in production, a tenant function, the three refusals of §10 one by one,
  loud when the client is wrapped, and none of them in development;
  `DIGLINE_RECORD=1` refused in production; a directory that cannot be written
  refused too;
- the file wins over the environment where it exists;
- the file is read again at the interval, on an injected clock, and a file
  that turns invalid switches the recorder off and counts `config invalid`;
- a sample drawn per call on an injected generator, to the exact count; an
  episode drawn once, its children in or out with it;
- the ceiling: the recorder stops, counts `ceiling`, leaves its marker, and
  the status says so from another reader;
- `digline record on`, `off` and `status`, on a temporary directory;
- the commit an episode reads, cached until the next look.
"""

from __future__ import annotations

import importlib
import json
import os
import random
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.cli.main import main
from digline.host import recorder_status, switch_off, switch_on
from digline.recorder import (
    RecordedClient,
    RecorderStartError,
    episode,
    parse_switch,
    wrap,
)
from digline.store.file_store import (
    _NAME_RE,  # pyright: ignore[reportPrivateUsage]
    CEILING_MARKER_FILENAME,
    RECORDER_FILENAME,
    RECORDINGS_DIRNAME,
    STORE_DIRNAME,
    FileResultStore,
)
from digline.wire import EXIT_USAGE

SDKS = ("anthropic", "httpx2")

ANSWER: dict[str, object] = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "Paris"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 3},
}
QUESTION = [{"role": "user", "content": "Capital of France?"}]
PRODUCTION = 'on = true\nsample = 1\nredact = "none"\nceiling = 1000000\n'


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with the variable unset; the file decides."""
    monkeypatch.delenv(recorder.ENVIRONMENT_VARIABLE, raising=False)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(recorder, "_clock", lambda: now[0])
    return now


def an_anthropic() -> Any:
    httpx2 = importlib.import_module("httpx2")

    def handle(request: object) -> Any:
        return httpx2.Response(200, json=ANSWER)

    return importlib.import_module("anthropic").Anthropic(
        api_key="test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        max_retries=0,
    )


def switch(root: Path, tenant: str, text: str) -> Path:
    path = root / ".digline" / tenant / "recorder.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def ask(client: RecordedClient) -> None:
    client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage"
    )


def recordings(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
    ]


def counts(client: RecordedClient) -> dict[str, Any]:
    return dict(client.digline_counts)


def production(tenant: str = "acme") -> Callable[[], str]:
    return lambda: tenant


def test_the_layouts_names_are_the_stores() -> None:
    names = (
        recorder._STORE,  # pyright: ignore[reportPrivateUsage]
        recorder._SWITCH_FILE,  # pyright: ignore[reportPrivateUsage]
        recorder._RECORDINGS,  # pyright: ignore[reportPrivateUsage]
        recorder._CEILING_MARKER,  # pyright: ignore[reportPrivateUsage]
    )
    assert names == (
        STORE_DIRNAME,
        RECORDER_FILENAME,
        RECORDINGS_DIRNAME,
        CEILING_MARKER_FILENAME,
    )
    # And the rule a tenant is held to, which a directory of the layout is.
    assert recorder._NAME.pattern == _NAME_RE.pattern  # pyright: ignore[reportPrivateUsage]


# -- the three refusals ------------------------------------------------------- #

REFUSALS = {
    "redact": "no declared redaction",
    "sample": "no declared sampling",
    "ceiling": "no ceiling on the size of its recordings",
}


@pytest.mark.parametrize("left_out", sorted(REFUSALS))
def test_production_refuses_a_switch_missing_one_of_three(
    tmp_path: Path, left_out: str
) -> None:
    text = "".join(
        line + "\n" for line in PRODUCTION.splitlines() if not line.startswith(left_out)
    )
    switch(tmp_path, "acme", text)
    with pytest.raises(RecorderStartError, match=REFUSALS[left_out]) as refused:
        wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)
    # One refusal at a time: the other two were declared.
    for other, sentence in REFUSALS.items():
        if other != left_out:
            assert sentence not in str(refused.value)


@pytest.mark.parametrize("left_out", sorted(REFUSALS))
def test_development_gives_a_default_where_production_refuses(
    tmp_path: Path, left_out: str
) -> None:
    text = "".join(
        line + "\n" for line in PRODUCTION.splitlines() if not line.startswith(left_out)
    )
    switch(tmp_path, "acme", text)
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    assert len(recordings(tmp_path)) == 1


def test_production_with_all_three_missing_names_all_three(tmp_path: Path) -> None:
    switch(tmp_path, "acme", "on = true\n")
    with pytest.raises(RecorderStartError) as refused:
        wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)
    for sentence in REFUSALS.values():
        assert sentence in str(refused.value)


def test_production_switched_off_needs_nothing_declared(tmp_path: Path) -> None:
    switch(tmp_path, "acme", "on = false\n")
    client = wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)
    ask(client)
    assert recordings(tmp_path) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes a read-only directory")
def test_production_refuses_a_directory_it_cannot_write(tmp_path: Path) -> None:
    path = switch(tmp_path, "acme", PRODUCTION)
    path.parent.chmod(0o500)
    try:
        with pytest.raises(RecorderStartError, match="not a writable directory"):
            wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)
    finally:
        path.parent.chmod(0o700)


def test_production_refuses_the_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    switch(tmp_path, "acme", PRODUCTION)
    with pytest.raises(RecorderStartError, match="no redaction and no sampling"):
        wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)


def test_production_records_each_tenant_by_its_own_file(tmp_path: Path) -> None:
    switch(tmp_path, "acme", PRODUCTION)
    switch(tmp_path, "globex", "on = false\n")
    served = iter(["acme", "globex", "initech"])
    client = wrap(
        an_anthropic(), app="support", tenant=lambda: next(served), root=tmp_path
    )
    for _ in range(3):
        ask(client)
    assert [found["source_tenant"] for found in recordings(tmp_path)] == ["acme"]
    assert counts(client)["not_recorded"] == {"off for this tenant": 2}


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("on = true\nsampel = 1\n", "does not read: sampel"),
        ('on = true\nredact = "hash"\n', "is not implemented"),
        ("on = true\nsample = 0\n", "above 0 and at most 1"),
        ("on = true\nsample = 1.5\n", "above 0 and at most 1"),
        ("on = true\nsample = true\n", "above 0 and at most 1"),
        ("on = true\nceiling = 0\n", "whole number of bytes"),
        ("on = true\nceiling = 1.5\n", "whole number of bytes"),
        ("on = true\ninterval = 0\n", "seconds above 0"),
        ('on = "yes"\n', "on = true or on = false"),
        ("sample = 1\n", "on = true or on = false"),
        ("on = = true\n", "not valid TOML"),
    ],
)
def test_a_switch_file_that_is_wrong_is_refused_by_name(text: str, match: str) -> None:
    with pytest.raises(RecorderStartError, match=match):
        parse_switch(text, where="recorder.toml", production=False)


def test_in_production_an_invalid_file_is_refused_when_the_client_is_wrapped(
    tmp_path: Path,
) -> None:
    switch(tmp_path, "acme", PRODUCTION + "sampel = 1\n")
    with pytest.raises(RecorderStartError, match="does not read: sampel"):
        wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)


def test_in_development_an_invalid_file_warns_once_and_records_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], clock: list[float]
) -> None:
    switch(tmp_path, "acme", 'on = true\nredact = "hash"\n')
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    ask(client)
    err = capsys.readouterr().err
    assert err.count("digline recorder: not recording for this tenant:") == 1
    assert "redact = 'hash' is not implemented" in err
    assert recordings(tmp_path) == []
    assert counts(client)["not_recorded"] == {"config invalid": 1}


def test_a_file_that_declares_production_is_held_to_it_in_development(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    switch(tmp_path, "acme", "on = true\nproduction = true\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    assert "no declared redaction" in capsys.readouterr().err
    assert recordings(tmp_path) == []


# -- the file and the environment --------------------------------------------- #


def test_the_file_wins_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    switch(tmp_path, "acme", "on = false\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    assert recordings(tmp_path) == []


def test_without_a_file_the_environment_decides_in_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    assert len(recordings(tmp_path)) == 1


def test_a_file_on_records_without_the_environment(tmp_path: Path) -> None:
    switch(tmp_path, "acme", "on = true\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    assert len(recordings(tmp_path)) == 1


# -- the interval ------------------------------------------------------------- #


def test_the_file_is_read_again_at_the_interval_and_not_before(
    tmp_path: Path, clock: list[float]
) -> None:
    path = switch(tmp_path, "acme", "on = false\ninterval = 10\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    path.write_text("on = true\ninterval = 10\n", encoding="utf-8")
    clock[0] += 9
    ask(client)
    assert recordings(tmp_path) == []
    clock[0] += 2
    ask(client)
    assert len(recordings(tmp_path)) == 1


def test_a_file_that_turns_invalid_switches_off_and_counts(
    tmp_path: Path, clock: list[float]
) -> None:
    path = switch(tmp_path, "acme", "on = true\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    path.write_text('on = true\nredact = "hash"\n', encoding="utf-8")
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    ask(client)
    ask(client)
    assert len(recordings(tmp_path)) == 1
    assert counts(client)["not_recorded"] == {"config invalid": 1}


def test_a_file_that_appears_switches_on_without_a_restart(
    tmp_path: Path, clock: list[float]
) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    switch(tmp_path, "acme", "on = true\n")
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    ask(client)
    assert len(recordings(tmp_path)) == 1


# -- the sample --------------------------------------------------------------- #

#: How many of `random.Random(58)`'s first 100 draws are below 0.5: 53,
#: written as a number, and replayed from the generator in the test, so the
#: count is held twice and the recorder must draw once per call, in order.
SAMPLED_OF_100 = 53


def test_a_sample_is_drawn_once_per_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recorder, "_draw", random.Random(58).random)
    switch(tmp_path, "acme", "on = true\nsample = 0.5\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    for _ in range(100):
        ask(client)
    replay = random.Random(58)
    assert sum(replay.random() < 0.5 for _ in range(100)) == SAMPLED_OF_100
    assert len(recordings(tmp_path)) == SAMPLED_OF_100
    assert counts(client)["not_recorded"] == {"sampled out": 100 - SAMPLED_OF_100}


def test_sample_one_records_everything_and_draws_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never() -> float:
        raise AssertionError("a draw at sample = 1")

    monkeypatch.setattr(recorder, "_draw", never)
    switch(tmp_path, "acme", "on = true\nsample = 1\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    for _ in range(5):
        ask(client)
    assert len(recordings(tmp_path)) == 5


def test_an_episode_is_drawn_once_with_its_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draws = [0.9, 0.1]
    drawn: list[float] = []

    def draw() -> float:
        drawn.append(draws[len(drawn)])
        return drawn[-1]

    monkeypatch.setattr(recorder, "_draw", draw)
    switch(tmp_path, "acme", "on = true\nsample = 0.5\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    with episode(client, suite="agent", case={"m": "q"}):  # drawn out
        for _ in range(3):
            ask(client)
        with episode(client, suite="inner", case={"m": "q"}):
            ask(client)
    assert recordings(tmp_path) == []
    with episode(client, suite="agent", case={"m": "q"}):  # drawn in
        for _ in range(3):
            ask(client)
        with episode(client, suite="inner", case={"m": "q"}):
            ask(client)
    assert drawn == [0.9, 0.1]
    found = recordings(tmp_path)
    assert sorted(item["suite"] for item in found) == [
        "agent",
        "inner",
        "triage",
        "triage",
        "triage",
        "triage",
    ]


# -- the ceiling -------------------------------------------------------------- #


def test_at_the_ceiling_the_recorder_stops_marks_and_says_so(tmp_path: Path) -> None:
    switch(tmp_path, "acme", "on = true\nceiling = 1\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    for _ in range(3):
        ask(client)
    assert len(recordings(tmp_path)) == 1
    assert counts(client)["not_recorded"] == {"ceiling": 2}
    marker = FileResultStore(tmp_path).ceiling_marker_path("acme")
    assert json.loads(marker.read_text(encoding="utf-8"))["ceiling"] == 1
    [status] = recorder_status(tmp_path, "acme")
    assert status.stopped_at_ceiling
    assert status.ceiling == 1
    assert status.size > 1


def test_the_ceiling_counts_what_another_process_wrote(
    tmp_path: Path, clock: list[float]
) -> None:
    switch(tmp_path, "acme", "on = true\nceiling = 3000\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    # Another process's recordings, seen only at the next look.
    other = tmp_path / ".digline" / "acme" / "recordings" / "p1-0000abcd"
    other.mkdir()
    (other / "000001.json").write_text(json.dumps("x" * 5000), encoding="utf-8")
    ask(client)
    assert len(recordings(tmp_path)) == 3  # two of this process, one foreign
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    ask(client)
    assert counts(client)["not_recorded"] == {"ceiling": 1}


def test_a_ceiling_raised_lets_the_recorder_record_again(
    tmp_path: Path, clock: list[float]
) -> None:
    path = switch(tmp_path, "acme", "on = true\nceiling = 1\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    ask(client)
    marker = FileResultStore(tmp_path).ceiling_marker_path("acme")
    assert marker.is_file()
    path.write_text("on = true\nceiling = 100000000\n", encoding="utf-8")
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    ask(client)
    assert len(recordings(tmp_path)) == 2
    assert not marker.exists()


# -- the commit, cached until the next look ------------------------------------ #


def test_the_commit_is_read_once_until_the_next_look(
    tmp_path: Path, clock: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = importlib.import_module("digline.host.environment")
    read: list[Path] = []

    def git_commit(root: Path) -> str | None:
        read.append(root)
        return "a" * 40

    monkeypatch.setattr(environment, "git_commit", git_commit)
    switch(tmp_path, "acme", "on = true\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    for _ in range(2):
        with episode(client, suite="agent", case={"m": "q"}):
            ask(client)
    assert len(read) == 1
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    with episode(client, suite="agent", case={"m": "q"}):
        ask(client)
    assert len(read) == 2


# -- the commands ------------------------------------------------------------- #


def test_record_on_writes_the_file_the_recorder_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "record",
            "on",
            "--tenant",
            "acme",
            "--root",
            str(tmp_path),
            "--sample",
            "0.25",
        ]
    )
    assert code == 0
    path = FileResultStore(tmp_path).recorder_path("acme")
    assert path.read_text(encoding="utf-8") == "on = true\nsample = 0.25\n"
    assert "development" in capsys.readouterr().out
    # The generated `.gitignore` is there, so the switch is never committed.
    gitignore = (tmp_path / ".digline" / ".gitignore").read_text(encoding="utf-8")
    assert "*/recorder.toml" in gitignore


def test_record_on_in_production_refuses_what_the_recorder_would(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "record",
            "on",
            "--tenant",
            "acme",
            "--root",
            str(tmp_path),
            "--production",
            "--sample",
            "0.1",
        ]
    )
    assert code == EXIT_USAGE
    error = capsys.readouterr().err
    assert "no declared redaction" in error
    assert "no ceiling on the size of its recordings" in error
    assert "no declared sampling" not in error
    assert not FileResultStore(tmp_path).recorder_path("acme").exists()


def test_record_on_in_production_with_all_three_is_what_wrap_accepts(
    tmp_path: Path,
) -> None:
    path = switch_on(
        tmp_path, "acme", production=True, sample=0.5, redact="none", ceiling=1000
    )
    assert path.read_text(encoding="utf-8") == (
        'on = true\nsample = 0.5\nredact = "none"\nceiling = 1000\nproduction = true\n'
    )
    wrap(an_anthropic(), app="support", tenant=production(), root=tmp_path)


def test_record_off_keeps_the_rest(tmp_path: Path) -> None:
    switch_on(tmp_path, "acme", production=False, sample=0.5, ceiling=1000)
    code = main(["record", "off", "--tenant", "acme", "--root", str(tmp_path)])
    assert code == 0
    path = FileResultStore(tmp_path).recorder_path("acme")
    assert path.read_text(encoding="utf-8") == (
        "on = false\nsample = 0.5\nceiling = 1000\n"
    )
    switch_off(tmp_path, "globex")
    assert FileResultStore(tmp_path).recorder_path("globex").read_text(
        encoding="utf-8"
    ) == ("on = false\n")


def test_record_status_counts_by_suite_and_orphans(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    switch_on(tmp_path, "acme", production=False, ceiling=10_000_000)
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    ask(client)
    with episode(client, suite="agent", case={"m": "q"}):
        ask(client)
    code = main(["record", "status", "--root", str(tmp_path), "--json"])
    assert code == 0
    document = json.loads(capsys.readouterr().out)
    [tenant] = document["tenants"]
    assert tenant["tenant"] == "acme"
    assert tenant["switch"]["state"] == "valid"
    assert tenant["switch"]["on"] is True
    assert tenant["switch"]["declared"] == ["on", "ceiling"]
    assert tenant["switch"]["sample"] == 1.0
    assert "no declared redaction" in tenant["switch"]["production_refusal"]
    assert tenant["recordings"]["suites"] == [
        {
            "suite": "agent",
            "calls": 0,
            "episodes": 1,
            "orphans": 0,
            "inside_episodes": 0,
            "interrupted": 0,
            "not_recorded": {},
            "noted": {},
            "imported": None,
            "since_last_import": None,
        },
        {
            "suite": "triage",
            "calls": 2,
            "episodes": 0,
            "orphans": 0,
            "inside_episodes": 1,
            "interrupted": 0,
            "not_recorded": {},
            "noted": {},
            "imported": None,
            "since_last_import": None,
        },
    ]
    assert tenant["recordings"]["stopped_at_ceiling"] is False
    assert tenant["recordings"]["size"] == sum(
        path.stat().st_size
        for path in (tmp_path / ".digline").glob("acme/recordings/*/*.json")
    )
    code = main(["record", "status", "--root", str(tmp_path)])
    assert code == 0
    text = capsys.readouterr().out
    assert "tenant 'acme' · recording on" in text
    assert "sample 1.0 (default)" in text
    # Each suite says what it holds: no "0 episodes" beside the calls whose
    # episode is in another suite, and no "0 calls" beside the episode.
    assert "suite triage: 2 calls, 1 inside an episode, 0 orphans; " in text
    assert "suite agent: 1 episode; " in text
    assert "since the last import: not read (pass --suite)" in text
    # A development file: what production would refuse is not printed.
    assert "production" not in text


def test_record_status_says_interrupted_episodes_one_by_one_and_the_size(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    switch_on(tmp_path, "acme", production=False, ceiling=10_000_000)
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    with episode(client, suite="agent", case={"m": "q"}):
        ask(client)
    with (
        pytest.raises(RuntimeError, match="gave up"),
        episode(client, suite="agent", case={"m": "r"}),
    ):
        ask(client)
        raise RuntimeError("the agent gave up")
    client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="lookup"
    )
    assert main(["record", "status", "--root", str(tmp_path), "--json"]) == 0
    [tenant] = json.loads(capsys.readouterr().out)["tenants"]
    agent, lookup, triage = tenant["recordings"]["suites"]
    assert (agent["episodes"], agent["interrupted"]) == (2, 1)
    assert (lookup["calls"], triage["calls"], triage["interrupted"]) == (1, 2, 0)
    size = tenant["recordings"]["size"]
    assert main(["record", "status", "--root", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "suite agent: 2 episodes, 1 interrupted; " in text
    assert "suite lookup: 1 call, 0 orphans; " in text
    assert "suite triage: 2 calls, 2 inside episodes, 0 orphans; " in text
    # The size is the recordings as written, the measure the ceiling is held
    # against, and the line says the disk holds more.
    assert (
        f"size:       {size} bytes of recordings (as written; disk use is "
        "higher), ceiling 10000000\n"
    ) in text


def test_record_on_prints_the_values_the_file_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["record", "on", "--tenant", "acme", "--root", str(tmp_path)]
    assert main([*argv, "--sample", "0.5"]) == 0
    assert main(["record", "off", "--tenant", "acme", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    # On again, with no option: the sample left from before is kept, and said.
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert (
        "values: on true, sample 0.5, redact none (default), "
        "ceiling 104857600 bytes (default), interval 5.0 s (default)"
    ) in out


def test_record_on_says_what_production_is_in_every_language(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Production is an application that resolves its tenant per request,
    whatever language it is in, and the proxy, which takes one tenant, never
    is: the sentence names the three doors, not a Python function alone."""
    assert main(["record", "on", "--tenant", "acme", "--root", str(tmp_path)]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert (
        "an application that resolves its tenant per request is production "
        "(wrap(tenant=callable) in Python, DiglineRecorder.production in Java; "
        "the proxy's --tenant is never production)"
    ) in out
    assert "names its tenant with a function" not in out


def test_the_counts_are_written_at_the_tick_never_per_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    def out() -> float:
        return 0.99

    monkeypatch.setattr(recorder, "_draw", out)
    switch(tmp_path, "acme", "on = true\nsample = 0.5\n")
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    counts_files = list((tmp_path / ".digline").glob("acme/recordings/*/.counts"))
    for _ in range(100):
        ask(client)
    assert counts(client)["not_recorded"] == {"sampled out": 100}
    # A hundred outcomes inside one interval, and not one write.
    assert (
        list((tmp_path / ".digline").glob("acme/recordings/*/.counts"))
        == counts_files
        == []
    )
    clock[0] += recorder.DEFAULT_INTERVAL + 1
    ask(client)  # the tick: the look writes what the hundred counted
    [written] = (tmp_path / ".digline").glob("acme/recordings/*/.counts")
    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["suites"]["triage"]["not_recorded"] == {"sampled out": 100}


def test_the_counts_outlive_the_process_and_status_reads_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    switch(tmp_path, "acme", "on = true\n")
    program = (
        "import datetime, anthropic, httpx2\n"
        "import digline.recorder as r\n"
        f"body = {ANSWER!r}\n"
        "http = httpx2.Client(transport=httpx2.MockTransport("
        "lambda q: httpx2.Response(200, json=body)))\n"
        "c = r.wrap(anthropic.Anthropic(api_key='t', http_client=http), "
        f"app='a', tenant='acme', root={str(tmp_path)!r})\n"
        "c.messages.create(model='m', max_tokens=5, suite='triage', messages=["
        "{'role': 'user', 'content': 'q', 'when': datetime.date(2026, 11, 3)}])\n"
        "c.messages.create(model='m', max_tokens=5, suite='triage', messages=["
        "{'role': 'user', 'content': 'q'}])\n"
    )
    import subprocess

    done = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    [status] = recorder_status(tmp_path, "acme")
    [triage] = status.suites
    assert (triage.calls, dict(triage.not_recorded)) == (1, {"not JSON": 1})
    assert main(["record", "status", "--root", str(tmp_path)]) == 0
    assert "    not recorded: not JSON 1" in capsys.readouterr().out


def test_record_status_counts_an_orphan(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    switch_on(tmp_path, "acme", production=False)
    client = wrap(an_anthropic(), app="support", tenant="acme", root=tmp_path)
    with episode(client, suite="agent", case={"m": "q"}), ThreadPoolExecutor(1) as pool:
        pool.submit(ask, client).result()
    [status] = recorder_status(tmp_path)
    triage = [suite for suite in status.suites if suite.suite == "triage"]
    assert [(suite.calls, suite.orphans) for suite in triage] == [(1, 1)]


def test_record_status_says_an_invalid_file_and_an_empty_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["record", "status", "--root", str(tmp_path)]) == 0
    assert "no tenant under" in capsys.readouterr().out
    switch(tmp_path, "acme", "on = true\nsampel = 1\n")
    [status] = recorder_status(tmp_path)
    assert status.switch == "invalid"
    assert status.refusal is not None and "sampel" in status.refusal
    assert not status.on


@pytest.mark.parametrize(
    ("argv", "match"),
    [
        (
            ["record", "off", "--sample", "0.5"],
            "--sample belongs to `digline record on`",
        ),
        (["record", "status", "--production"], "--production belongs to"),
        (["record", "on", "--json"], "--json belongs to `digline record status`"),
        (["record", "on"], "needs --tenant"),
        (["record", "off"], "needs --tenant"),
    ],
)
def test_record_refuses_an_option_of_another_action(
    tmp_path: Path, argv: list[str], match: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*argv, "--root", str(tmp_path)]) == EXIT_USAGE
    assert match in capsys.readouterr().err
    assert not (tmp_path / ".digline").exists()


def test_record_on_refuses_a_redaction_not_implemented(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["record", "on", "--tenant", "acme", "--root", str(tmp_path)]
    assert main([*argv, "--redact", "hash"]) == EXIT_USAGE
    assert "is not implemented" in capsys.readouterr().err
    assert not FileResultStore(tmp_path).recorder_path("acme").exists()
