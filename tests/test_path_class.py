"""A name from outside the perimeter is a path segment only once
`checked_name` has taken it. (P-1515; CodeQL alerts 111-130, GHSA-j878-2v6m-m4vx)

CodeQL's high alerts on `py/path-injection` are one class: a tenant, a suite,
a run key or a cases file reaching a path. In 1.1 they arrive from further
out: an address of `digline view`, the proxy's headers and path, a recording
file anybody may write, a `[capture]` table. Each entry is here, held to the
one function at the store's edge, `digline.store.checked_name`, or shown to
be a value that never becomes a path. The view's addresses and the proxy's
headers are in `tests/test_view_recorder.py` and `tests/test_record_proxy.py`,
beside the servers they need.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from digline import recorder
from digline.cli import EXIT_USAGE
from digline.cli.main import main
from digline.host.recording import recorder_status
from digline.store import PathRefusedError, checked_name

CLIMBS = ("../outside", "..", "a/b", "acme\n", "acme\r", "\nacme", "")


@pytest.mark.parametrize("name", CLIMBS)
def test_the_one_function_refuses_anything_but_a_single_safe_segment(name: str) -> None:
    with pytest.raises(PathRefusedError, match="invalid tenant name"):
        checked_name(name, "tenant")


def test_a_final_newline_is_not_a_name_any_more() -> None:
    """`$` matched before a final newline, so `acme\\n` passed and became a
    tenant directory from a POST to `digline view`. `fullmatch`, and `\\Z`."""
    assert checked_name("acme", "tenant") == "acme"
    with pytest.raises(PathRefusedError):
        checked_name("acme\n", "tenant")


def test_the_refusal_names_the_field_and_cuts_the_value() -> None:
    with pytest.raises(PathRefusedError) as refused:
        checked_name("../" + "x" * 80, "suite")
    message = str(refused.value)
    assert message.startswith("invalid suite name: '../" + "x" * 37 + "' ")
    assert "x" * 38 not in message


@pytest.mark.parametrize(
    "command",
    [
        ["record", "on", "--tenant"],
        ["record", "off", "--tenant"],
        ["record", "status", "--tenant"],
    ],
)
@pytest.mark.parametrize("name", ["../outside", "acme\n"])
def test_a_tenant_on_the_command_line_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: list[str], name: str
) -> None:
    code = main([*command, name, "--root", str(tmp_path)])
    _, err = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "invalid tenant name" in err
    assert (
        not (tmp_path / ".digline").exists()
        or [path.name for path in (tmp_path / ".digline").iterdir() if path.is_dir()]
        == []
    )


def plant_switch(root: Path) -> None:
    """A switch where `.digline/../outside` leads: outside the store."""
    (root / ".digline").mkdir(parents=True)
    (root / "outside").mkdir()
    (root / "outside" / "recorder.toml").write_text("on = true\n", encoding="utf-8")


@pytest.mark.parametrize("name", ["../outside", "acme\n"])
def test_wrap_refuses_a_tenant_that_is_not_a_name(tmp_path: Path, name: str) -> None:
    """Measured before: `wrap(tenant="../outside")` read and obeyed a switch
    file outside `.digline/`."""
    import anthropic

    plant_switch(tmp_path)
    with pytest.raises(recorder.RecorderStartError, match="invalid tenant name"):
        recorder.wrap(
            anthropic.Anthropic(api_key="x"), app="a", tenant=name, root=tmp_path
        )


def test_a_production_tenant_that_is_not_a_name_is_not_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The function's answer is asked at every call, so it is checked at every
    call: a call for `../outside` is counted `tenant` and nothing is read or
    written for it."""
    import anthropic

    plant_switch(tmp_path)
    client: Any = recorder.wrap(
        anthropic.Anthropic(api_key="x"),
        app="a",
        tenant=_constant("../outside"),
        root=tmp_path,
    )
    state = client._digline_state  # pyright: ignore[reportPrivateUsage]
    assert state.switches == {}
    assert recorder._tenant_of(state) is None  # pyright: ignore[reportPrivateUsage]


def _constant(value: str) -> Callable[[], str]:
    return lambda: value


def recording(**fields: str) -> dict[str, object]:
    document: dict[str, object] = {
        "recording_version": 1,
        "source_tenant": "acme",
        "app": "app",
        "suite": "refunds",
        "case": {"messages": [{"role": "user", "content": "q"}]},
        "setup": {"model": "m"},
        "setup_digest": "0000000000000000",
        "response": {"output": "a", "kind": "text", "input": "[]", "latency_ms": 1.0},
        "recorded_at": "2026-11-05T08:00:00+00:00",
    }
    document.update(fields)
    return document


def test_a_recordings_suite_and_app_are_values_never_paths(tmp_path: Path) -> None:
    """The format is public, so a file's `suite` and `app` may be anything a
    writer chose. Neither is a segment of any path: the status reads them as
    names of groups, and nothing is made for them."""
    place = tmp_path / ".digline" / "acme" / "recordings" / "j1-aaaaaaaa"
    place.mkdir(parents=True)
    (place / "000001.json").write_text(
        json.dumps(recording(suite="../x", app="../../y")), encoding="utf-8"
    )
    (status,) = recorder_status(tmp_path, "acme")
    assert [suite.suite for suite in status.suites] == ["../x"]
    assert sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file()
    ) == [".digline/acme/recordings/j1-aaaaaaaa/000001.json"]


def test_a_recording_whose_tenant_climbs_is_not_read(tmp_path: Path) -> None:
    """`source_tenant` is compared with the directory the file sits in, and a
    file filed under `acme` that says `../outside` is not a recording of
    either: counted unreadable."""
    place = tmp_path / ".digline" / "acme" / "recordings" / "j1-aaaaaaaa"
    place.mkdir(parents=True)
    (place / "000001.json").write_text(
        json.dumps(recording(source_tenant="../outside")), encoding="utf-8"
    )
    (status,) = recorder_status(tmp_path, "acme")
    assert status.unreadable == 1
    assert status.suites == ()


def test_a_directory_that_is_not_a_name_is_no_tenant_of_the_status(
    tmp_path: Path,
) -> None:
    """Listing every tenant reads the directories under `.digline/`. One whose
    name is not a name, as `acme\\n` from before `fullmatch`, is left out
    rather than refusing every tenant's status beside it."""
    for name in ("acme", "acme\n"):
        (tmp_path / ".digline" / name).mkdir(parents=True)
        (tmp_path / ".digline" / name / "recorder.toml").write_text(
            "on = true\n", encoding="utf-8"
        )
    assert [tenant.tenant for tenant in recorder_status(tmp_path)] == ["acme"]


def test_a_cases_file_outside_the_repository_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`[capture]`'s `cases_file` is where the import writes. Outside the
    perimeter it is refused, by `within_perimeter`, GHSA-j878's other half,
    before anything is read or written."""
    root = tmp_path / "project"
    root.mkdir()
    secret = tmp_path / "secret.json"
    secret.write_text("[]", encoding="utf-8")
    (root / "cases.json").write_text(
        '[{"id": "mine", "vars": {"messages": []}}]', encoding="utf-8"
    )
    (root / "suite.toml").write_text(
        """[suite]
tenant = "acme"
environment = "dev"
name = "refunds"
cases = ["cases.json"]
samples = 2
min_agreement = "2/2"

[capture]
cases_file = "../secret.json"
repository = "private"
check = "llm_rubric"

[[assertions]]
type = "llm_rubric"
rubric = "Is it right?"
judge = "openai/gpt-4o-mini"
threshold = 0.7
tolerance = 0.05

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "answer"

  [target.body]
  messages = "case.vars.messages"
""",
        encoding="utf-8",
    )
    code = main(
        [
            "record",
            "import",
            "--tenant",
            "acme",
            "--suite",
            str(root / "suite.toml"),
            "--root",
            str(root),
            "--good",
            "x",
            "--by",
            "Ada",
        ]
    )
    _, err = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "capture" in err
    assert secret.read_text(encoding="utf-8") == "[]"
