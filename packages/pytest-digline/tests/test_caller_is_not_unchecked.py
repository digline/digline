"""The test module that drove the run is not counted as unchecked (#623).

Under pytest, a test module beside the suite that imports the application is
the normal arrangement (ADR 0052, decision 2). pytest imports it when it
collects it, before the plugin loads the suite, so by provenance it was in
`modules_unchecked`: on `examples/classifier`, `['app', 'test_app_first']`.
It is the caller, not something the run called, and it is left out. The
application module the test imported is still counted: the run called it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

APP = """
ANSWER = "Acme"
"""

SUITE = """
import app
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="caller",
    assertions=[Contains(needle="Acme")],
    cases=[Case(id="alpha")],
)


def target(case):
    return Response(output=app.ANSWER, input="who?")
"""

TEST_FIRST = """
import app


def test_app_first():
    assert app.ANSWER == "Acme"
"""


def _project(root: Path) -> Path:
    (root / "app.py").write_text(APP, encoding="utf-8")
    (root / "test_app_first.py").write_text(TEST_FIRST, encoding="utf-8")
    suite = root / "suite.py"
    suite.write_text(SUITE, encoding="utf-8")
    return suite


def _recorded(root: Path) -> list[str]:
    (path,) = sorted((root / ".digline" / "acme" / "runs" / "caller").glob("*.json"))
    return json.loads(path.read_text(encoding="utf-8"))["modules_unchecked"]


def test_the_test_module_that_drove_the_run_is_not_counted(
    pytester: pytest.Pytester,
) -> None:
    suite = _project(pytester.path)
    pytester.runpytest_subprocess("--digline-suite", str(suite), "--digline-run")
    assert _recorded(pytester.path) == ["app"]
