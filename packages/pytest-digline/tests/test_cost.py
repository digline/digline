"""The cost question: what a pytest invocation is allowed to spend. (ADR 0013 §2)

pytest is a command people run on a keystroke, in a watcher, in a pre-commit
hook. The default here calls nothing, and the flag that does is refused in the
one place where calling would be absurd.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _cycle import cycle

#: A suite whose target fails the test if it is ever called. The refusal is
#: proved by the provider never being reached, not by counting calls afterwards:
#: a count read after the fact is a count read after the money was spent.
EXPLODING = """
import pathlib
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="support",
    assertions=[Contains(needle="Acme")],
    cases=[Case(id="alpha")],
)

def target(case: Case) -> Response:
    pathlib.Path("CALLED").write_text("the provider was reached", encoding="utf-8")
    raise SystemExit("the target was called during --collect-only")
"""


def test_collect_only_refuses_to_run_the_suite(pytester: pytest.Pytester) -> None:
    """The refusal, and it happens before anything can be called.

    `--collect-only` exists to list test names. A plugin that spent a hundred
    model calls answering it would be the worst defect this package could ship.
    """
    path = pytester.path / "suite.py"
    path.write_text(EXPLODING, encoding="utf-8")

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run", "--collect-only"
    )

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*--digline-run*--collect-only*"])
    assert not (pytester.path / "CALLED").exists(), (
        "the target was reached under --collect-only: the refusal in "
        "pytest_configure did not happen before collection"
    )


def test_collect_only_alone_lists_the_checks_and_costs_nothing(
    pytester: pytest.Pytester,
    baseline: Callable[[dict[str, str], dict[str, str]], Path],
) -> None:
    """The other half of the refusal's message, which has to be true.

    It tells the reader that `--collect-only` alone lists the checks against the
    run already stored. A message naming a command that does not work is worse
    than no message.
    """
    path = baseline(
        {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"},
        {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"},
    )
    result = pytester.runpytest_subprocess("--digline-suite", str(path), "--co", "-q")

    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        ["*suite.py::alpha::contains*", "*suite.py::gamma*"], consecutive=False
    )


def test_the_default_makes_no_call_at_all(
    pytester: pytest.Pytester,
    baseline: Callable[[dict[str, str], dict[str, str]], Path],
) -> None:
    """Compare-only is the default, and 'compare-only' means the target is never
    reached — not that it is reached cheaply."""
    path = baseline(
        {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"},
        {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"},
    )
    # Replaced *after* the two runs exist: from here on, any call explodes.
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "return Response(", "raise SystemExit('called'); return Response("
        ),
        encoding="utf-8",
    )
    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    assert result.ret == pytest.ExitCode.OK


def test_digline_run_says_what_it_will_cost_before_it_spends_it(
    pytester: pytest.Pytester,
    repo: Callable[[dict[str, str]], Path],
) -> None:
    """`AGENTS.md` §7 and ADR 0006 §8, unchanged and not optional.

    Sampling multiplies spend and the multiplication is what surprises people.
    On stderr, where a shell capturing stdout still sees it.
    """
    path = repo({"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"})
    cycle(path, pytester.path, promote=True)

    result = pytester.runpytest_subprocess(
        "--digline-suite", str(path), "--digline-run"
    )
    result.stderr.fnmatch_lines(["*calls to the target*"])
