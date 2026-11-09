"""What the import's listing and a promotion's refusal say, in words a person
reads. (P-1588)

- The listing counts in the singular where there is one: `1 call attached`,
  `1 interrupted episode`, `1 orphan`, `1 file that is not a readable
  recording`; it said `1 calls attached` and `1 interrupted episodes`.
- `promote`'s refusal of a run where a check contradicted a person is its
  sentence alone on standard error, where it was `digline:
  ContradictedRunError: …`. Every other refusal keeps its class's name, which
  `docs/` quotes.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.test_recorder_import import listed, recorded, suite_file

from digline.cli.main import main
from digline.host.importing import ImportListing, _say_answer, closing_lines  # pyright: ignore[reportPrivateUsage]
from digline.store import ConfigMismatchError, ContradictedRunError

#: The module, not the function `digline.cli` exports under the same name.
cli = importlib.import_module("digline.cli.main")


@pytest.fixture
def found(tmp_path: Path) -> ImportListing:
    recorded(tmp_path)
    suite_file(tmp_path)
    listing: ImportListing = listed(tmp_path)
    return listing


def test_one_of_each_is_said_in_the_singular(found: ImportListing) -> None:
    one = dataclasses.replace(
        found, orphans=1, detached=1, interrupted=1, oversize=0, unreadable=1
    )
    line = closing_lines(one)[0]
    assert line.endswith(
        "not cases: 1 orphan, 1 call whose episode is not among the files, "
        "1 interrupted episode, 0 over the ceiling of a recording, 1 file that "
        "is not a readable recording"
    )


def test_two_of_each_are_said_in_the_plural(found: ImportListing) -> None:
    two = dataclasses.replace(
        found, orphans=2, detached=2, interrupted=2, oversize=0, unreadable=2
    )
    line = closing_lines(two)[0]
    assert line.endswith(
        "not cases: 2 orphans, 2 calls whose episode is not among the files, "
        "2 interrupted episodes, 0 over the ceiling of a recording, 2 files that "
        "are not readable recordings"
    )


@pytest.mark.parametrize(
    ("attached", "said"), [(1, "1 call attached"), (2, "2 calls attached")]
)
def test_an_answers_calls_attached_agree_with_their_count(
    found: ImportListing, attached: int, said: str
) -> None:
    answer = dataclasses.replace(found.answers[0], attached=attached)
    assert f" · {said}" in _say_answer(answer)[0]


def refusing(error: Exception) -> Callable[[argparse.Namespace], int]:
    def promote(args: argparse.Namespace) -> int:
        raise error

    return promote


def test_a_contradicted_promotion_is_its_sentence_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentence = "run K: a check on the steps contradicted a person on 1 reviewed answer"
    monkeypatch.setattr(cli, "cmd_promote", refusing(ContradictedRunError(sentence)))
    assert (
        main(
            ["promote", "--suite", "suite.py", "--run", "latest", "--replacing", "none"]
        )
        == 64
    )
    assert capsys.readouterr().err == f"digline: {sentence}\n"


def test_every_other_refusal_keeps_its_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control: the handler did not drop every name."""
    monkeypatch.setattr(cli, "cmd_promote", refusing(ConfigMismatchError("moved")))
    assert (
        main(
            ["promote", "--suite", "suite.py", "--run", "latest", "--replacing", "none"]
        )
        == 64
    )
    assert capsys.readouterr().err == "digline: ConfigMismatchError: moved\n"
