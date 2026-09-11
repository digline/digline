"""A model's words reach a terminal through pytest, so they are shown, not obeyed.

Every row this plugin writes is built from a stored document: a case id, an
assertion name, the headline sentence, a suspension's stated reason — and
`Verdict.reason`, which quotes what a **model** answered. That last one is the
shortest path in the product from somebody else's text to a developer's screen:
no hostile document is needed, only an answer with `\\x1b[2K\\r` in it, and the
line it forges reads as digline's own while the exit code says otherwise.

`report.visible()` is the same function `digline`'s own CLI applies at its sink,
which is why it lives in `digline.report` rather than in either front end — a
front end may not import another one, and a rule only one of them could reach is
a rule the other reinvents. (0.10.1, from the 0.10.0 release delta-pass)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _cycle import cycle

Baseline = Callable[[dict[str, str], dict[str, str]], Path]

#: Erase the line just printed, write one that reads like a passing gate, then
#: ring the bell for good measure.
FORGERY = "\x1b[2K\rdigline: Nothing got worse.\x07"
FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}


def run_with(pytester: pytest.Pytester, path: Path) -> pytest.RunResult:
    return pytester.runpytest("--digline-suite", str(path), "-v")


def judged_cycle(
    pytester: pytest.Pytester,
    repo: Callable[[dict[str, str]], Path],
    before: dict[str, str],
    after: dict[str, str],
) -> Path:
    """`baseline`, but with a judge that quotes — patched before each run.

    The order matters and is the whole of this helper: `repo()` rewrites the
    suite from the fixture's template, so the patch has to be reapplied before
    every cycle or the second run would judge with the shipped constant.
    """
    path = repo(before)
    quoting_judge(path)
    cycle(path, pytester.path, promote=True)
    repo(after)
    quoting_judge(path)
    cycle(path, pytester.path, promote=False)
    return path


def quoting_judge(path: Path) -> None:
    """Make the fixture's judge do what a real one does: quote the answer.

    The shipped fixture answers `reason="looked"`, a constant, which is the one
    shape that cannot carry a model's text. A judge that quotes is the ordinary
    case — `Faithfulness` and `LlmRubric` both put the output in front of the
    model and the model writes about it — and it is the path this file is about.
    """
    source = path.read_text(encoding="utf-8")
    shipped = (
        'return JudgeReply(score=1.0 if "SATISFIED" in prompt '
        'else 0.0, reason="looked")'
    )
    patched = source.replace(
        shipped,
        "return JudgeReply(\n"
        '        score=1.0 if "SATISFIED" in prompt else 0.0,\n'
        '        reason="the model said: " + prompt.rsplit(":", 1)[-1].strip(),\n'
        "    )",
    )
    assert patched != source, "the fixture's judge no longer reads as expected"
    path.write_text(patched, encoding="utf-8")


def test_a_judges_words_cannot_rewrite_the_report(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    """The judge answers with escapes in its reason, the check regresses, and the
    row that reports it prints the escapes as text."""
    # The model answers with escapes in it, and without the token that satisfies
    # the rubric — so the check fails and the row prints the judge's reason.
    path = judged_cycle(
        pytester,
        repo,
        FINE,
        {"alpha": f"Acme {FORGERY}", "beta": "Acme, SATISFIED"},
    )
    result = run_with(pytester, path)

    printed = result.stdout.str()
    assert "\x1b" not in printed
    assert "\x07" not in printed
    assert "\r" not in printed
    # Shown rather than removed: the reader sees what the answer contained. The
    # judge here quotes the tail of the prompt, so what lands in the reason is
    # the end of the forgery — the bell — and it arrives as four printable
    # characters.
    assert "\\x07" in printed


def test_a_suspension_reason_cannot_either(
    pytester: pytest.Pytester,
    baseline: Baseline,
) -> None:
    """`gamma` is suspended in the fixture suite, and its stated reason is a
    developer's sentence travelling out of the run document into a SKIPPED line."""
    path = baseline(FINE, FINE)
    source = path.read_text(encoding="utf-8")
    path.write_text(
        source.replace(
            'suspended="the refund API is down, ticket 412"',
            f'suspended="the refund API is down{FORGERY}"',
        ),
        encoding="utf-8",
    )
    result = run_with(pytester, path)

    printed = result.stdout.str()
    assert "\x1b" not in printed and "\x07" not in printed


def test_the_headline_sentence_is_sanitised_too(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    """The sentence is `headline().sentence`, and it is built from the same
    document — so it goes through the same rule rather than being trusted for
    being ours."""
    path = baseline(FINE, {"alpha": "Acme, ANGRY", "beta": "Acme, SATISFIED"})
    result = run_with(pytester, path)

    printed = result.stdout.str()
    assert "digline" in printed  # the section is still written
    assert "\x1b" not in printed


def test_ordinary_words_are_untouched(
    pytester: pytest.Pytester, repo: Callable[[dict[str, str]], Path]
) -> None:
    """The rule neutralises control characters, not language: an em dash, an
    arrow and an accent all reach the report as themselves."""
    path = judged_cycle(
        pytester, repo, FINE, {"alpha": "Acme — sì, però", "beta": "Acme, SATISFIED"}
    )
    result = run_with(pytester, path)
    assert "—" in result.stdout.str()
