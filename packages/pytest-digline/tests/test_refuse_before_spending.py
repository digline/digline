"""`--digline-run` reads the baseline's schema before it spends. (#621)

This plugin always compares, so a run made against a baseline it cannot read is
paid for and refused a moment later, by `need_baseline`, with pytest's 4. It
refuses before the first call now, with the same 4: the session's exit status
does not move, the money does. There is no way to accept here, because there is
nothing a run could be for in a session that then compares.

The test counts the target's calls. The exit status is the same before and
after the repair, so a test that read only the status would be green either
way.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

Baseline = Callable[[dict[str, str], dict[str, str]], Path]

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}

COUNTED = """
_answer = target

def target(case):
    import pathlib
    log = pathlib.Path(__file__).with_name("target.log")
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("1\\n")
    return _answer(case)
"""


def test_a_newer_baseline_is_refused_before_the_target_is_called(
    pytester: pytest.Pytester, baseline: Baseline
) -> None:
    path = baseline(FINE, FINE)
    path.write_text(path.read_text(encoding="utf-8") + COUNTED, encoding="utf-8")
    (stored,) = pytester.path.glob(".digline/*/baselines/*.json")
    document = json.loads(stored.read_text(encoding="utf-8"))
    document["schema_version"] += 1
    stored.write_text(json.dumps(document), encoding="utf-8")
    runs = len(list(pytester.path.glob(".digline/*/runs/*/*.json")))

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert not (pytester.path / "target.log").exists()
    assert len(list(pytester.path.glob(".digline/*/runs/*/*.json"))) == runs
    result.stderr.fnmatch_lines(["*DocumentRefusedError*schema*"])
