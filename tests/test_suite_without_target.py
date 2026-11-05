"""A suite that calls no target may declare none, and one with capture may hold
no case yet. (ADR 0059 §1)

- **No case yet.** A suite that declares `[capture]` is valid with no case:
  the first `digline record import` is what writes them. Its run judges
  nothing and exits 2, never a green. Without capture an empty suite is still
  refused.
- **No target.** A suite whose cases are all reviewed answers or calibration
  cases, which the run never calls the target for, may leave the target out.
  It runs, is judged again and is promoted as any suite is. A case the target
  answers, added later, is refused at load, with the case named.

Both forms, TOML and Python.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.cli.main import main
from digline.core import RefusedError
from digline.host import load_suite, load_target
from digline.host.errors import UsageError
from digline.host.unasked import NoTarget

CAPTURE_TOML = """
[suite]
tenant = "acme"
environment = "dev"
name = "screening"
cases = ["captured.json"]

[capture]
cases_file = "captured.json"
repository = "private"

[[assertions]]
type = "contains"
needle = "x"
"""

REVIEWED_TOML = """
[suite]
tenant = "acme"
environment = "dev"
name = "screening"
cases = "cases.json"
samples = 2
min_agreement = "2/2"

[[assertions]]
type = "llm_rubric"
rubric = "r"
judge = "fake/m"
threshold = 0.7
tolerance = 0.05
"""

REVIEWED = {
    "id": "said",
    "reviewed_answer": {
        "output": "fourteen days",
        "check": "llm_rubric",
        "good": True,
        "input": "How long is the refund window?",
    },
}

PYTHON = """
from digline.core import JudgeReply, LlmRubric
from digline.run import CaptureSource, Case, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="agreed")


suite = Suite(
    tenant="acme",
    environment="dev",
    name="screening",
    assertions=[LlmRubric(rubric="r", judge=judge, threshold=0.7, tolerance=0.05)],
    cases=%(cases)s,
    samples=2,
    min_agreement="2/2",
    capture=%(capture)s,
)
%(target)s
"""

CAPTURE = 'CaptureSource(cases_file="captured.json", repository="private")'

SAID = (
    '[Case(id="said", reviewed_answer=ReviewedAnswer(output="fourteen days", '
    'check="llm_rubric", good=True, input="How long?"))]'
)


def import_listing(root: Path, suite: str) -> int:
    return main(
        [
            "record",
            "import",
            "--tenant",
            "acme",
            "--suite",
            str(root / suite),
            "--root",
            str(root),
        ]
    )


# -- no case yet ------------------------------------------------------------- #


def test_a_toml_suite_with_capture_and_no_case_loads_and_imports(
    tmp_path: Path,
) -> None:
    (tmp_path / "suite.toml").write_text(CAPTURE_TOML, encoding="utf-8")
    suite, loaded = load_suite(str(tmp_path / "suite.toml"), root=tmp_path)
    assert suite.cases == ()
    # And no target, since no case calls one.
    assert isinstance(load_target(None, loaded, "suite.toml"), NoTarget)
    assert import_listing(tmp_path, "suite.toml") == 0


def test_a_python_suite_with_capture_and_no_case_loads_and_imports(
    tmp_path: Path,
) -> None:
    (tmp_path / "suite.py").write_text(
        PYTHON % {"cases": "[]", "target": "", "capture": CAPTURE}, encoding="utf-8"
    )
    suite, loaded = load_suite(str(tmp_path / "suite.py"), root=tmp_path)
    assert suite.cases == ()
    assert isinstance(load_target(None, loaded, "suite.py"), NoTarget)
    assert import_listing(tmp_path, "suite.py") == 0


def test_a_suite_with_no_case_runs_and_judges_nothing_never_a_green(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "suite.toml").write_text(CAPTURE_TOML, encoding="utf-8")
    assert (
        main(["run", "--suite", str(tmp_path / "suite.toml"), "--root", str(tmp_path)])
        == 2
    )
    assert "None of the cases this suite measures was judged" in capsys.readouterr().err


def test_without_capture_an_empty_suite_is_still_refused(tmp_path: Path) -> None:
    (tmp_path / "suite.py").write_text(
        PYTHON % {"cases": "[]", "target": "", "capture": "None"}, encoding="utf-8"
    )
    with pytest.raises(RefusedError, match="declares no cases, and no capture"):
        load_suite(str(tmp_path / "suite.py"), root=tmp_path)


# -- no target --------------------------------------------------------------- #


def test_a_toml_suite_of_reviewed_answers_needs_no_target(
    tmp_path: Path, fake_provider: None
) -> None:
    (tmp_path / "suite.toml").write_text(REVIEWED_TOML, encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps([REVIEWED]), encoding="utf-8")
    _, loaded = load_suite(str(tmp_path / "suite.toml"), root=tmp_path)
    assert isinstance(load_target(None, loaded, "suite.toml"), NoTarget)


def test_a_case_the_target_answers_needs_the_target_and_says_why(
    tmp_path: Path, fake_provider: None
) -> None:
    (tmp_path / "suite.toml").write_text(REVIEWED_TOML, encoding="utf-8")
    cases = [REVIEWED, {"id": "asked", "vars": {"question": "?"}}]
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    with pytest.raises(UsageError) as refused:
        load_suite(str(tmp_path / "suite.toml"), root=tmp_path)
    said = str(refused.value)
    assert "no [target] table, and every suite needs one" in said
    assert "case 'asked' is neither a reviewed answer nor a calibration case" in said


def test_a_python_suite_with_a_case_the_target_answers_and_no_target_is_refused(
    tmp_path: Path,
) -> None:
    cases = SAID[:-1] + ', Case(id="asked")]'
    (tmp_path / "suite.py").write_text(
        PYTHON % {"cases": cases, "target": "", "capture": CAPTURE}, encoding="utf-8"
    )
    _, loaded = load_suite(str(tmp_path / "suite.py"), root=tmp_path)
    with pytest.raises(UsageError, match="case 'asked' is neither"):
        load_target(None, loaded, "suite.py")


def commands(root: Path, target: str, capsys: pytest.CaptureFixture[str]) -> list[int]:
    """`run`, `rejudge` and `promote` on the suite, with `target` as its last
    line, and each one's exit."""
    root.mkdir()
    (root / "suite.py").write_text(
        PYTHON % {"cases": SAID, "target": target, "capture": CAPTURE},
        encoding="utf-8",
    )
    spec = str(root / "suite.py")
    exits = [main(["run", "--suite", spec, "--root", str(root)])]
    key = capsys.readouterr().out.strip().splitlines()[-1]
    exits.append(main(["rejudge", "--suite", spec, "--run", key, "--root", str(root)]))
    exits.append(
        main(
            [
                "promote",
                "--suite",
                spec,
                "--run",
                key,
                "--replacing",
                "none",
                "--root",
                str(root),
            ]
        )
    )
    capsys.readouterr()
    return exits


def test_run_rejudge_and_promote_treat_a_suite_with_no_target_as_today(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same suite with a target and without: the three commands answer
    alike, the run green, the re-judge refused for the answers nobody kept,
    the promotion done."""
    with_target = commands(
        tmp_path / "with", "def target(case):\n    raise AssertionError", capsys
    )
    without = commands(tmp_path / "without", "", capsys)
    assert with_target == without == [0, 64, 0]
