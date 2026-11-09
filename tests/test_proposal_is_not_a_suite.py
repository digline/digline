"""No command of digline reads `suite.proposed.toml`. (ADR 0063 §3; P-1588)

`digline suggest` says so of the file it writes, and it was not true: given
as `--suite`, the proposal loaded, and `record import` stopped at its judge's
placeholder. Every command that loads a suite refuses the file by its name,
before reading it, and says to adopt its lines first. The control is the same
text under another name, which loads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.test_recorder_import import recorded, suite_file, toml_suite

from digline.cli.main import main
from digline.host import PROPOSAL, load_suite
from digline.wire import EXIT_USAGE

COMMANDS = {
    "record import": ["record", "import", "--tenant", "acme"],
    "run": ["run"],
    "list": ["list"],
    "compare": ["compare", "--run", "latest"],
}


@pytest.fixture
def proposal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A suite that loads, written under the proposal's name beside itself."""
    recorded(tmp_path)
    suite_file(tmp_path)
    loads = toml_suite(tmp_path)
    (tmp_path / PROPOSAL).write_text(loads.read_text(encoding="utf-8"), "utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_same_text_under_another_name_loads(proposal: Path) -> None:
    suite, _ = load_suite("suite.toml", root=proposal)
    assert suite.name


@pytest.mark.parametrize("words", COMMANDS.values(), ids=COMMANDS.keys())
def test_each_command_refuses_the_proposal_by_name(
    proposal: Path, words: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*words, "--suite", PROPOSAL, "--root", str(proposal)]) == EXIT_USAGE
    said = capsys.readouterr().err
    assert (
        f"digline: {PROPOSAL!r} is a proposal: adopt its lines into your suite "
        f"first. No command of digline reads {PROPOSAL} (ADR 0063 §3)"
    ) in said
