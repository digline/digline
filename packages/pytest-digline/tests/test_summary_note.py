"""The note `latest` leaves, under the headline it qualifies. (#433)

This plugin compares `latest` against the baseline, and until #433 it took the
key and dropped the note. The case that matters: the baseline was promoted from
a run newer than `latest`, so every row holds an older run against a newer
reference, and a red row there is not a regression.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _cycle import cycle

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}


def test_the_note_follows_the_headline_in_the_summary(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    path = repo(FINE)
    older = cycle(path, pytester.path, promote=False)
    newer = cycle(path, pytester.path, promote=True)
    (gone,) = (pytester.path / ".digline").glob(f"*/runs/**/{newer}.json")
    gone.unlink()

    # `-W error` too: the note is not a warning, so it cannot fail a session
    # that turns warnings into errors.
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "-W", "error")

    expected = (
        f"note: the baseline was promoted from run {newer}, newer than {older}, "
        "and that run was not read here"
    )
    text = result.stdout.str()
    assert expected in text
    assert text.index("= digline =") < text.index(expected)
    assert result.ret == 0, text


def test_no_note_when_latest_steps_over_nothing(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    """The control: a note on every session would be a line people learn to
    skip, and would pass the test above."""
    path = repo(FINE)
    cycle(path, pytester.path, promote=True)
    cycle(path, pytester.path, promote=False)

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    assert "note:" not in result.stdout.str()
