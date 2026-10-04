"""An assertion of the wrong shape is refused when the suite is assembled.

The protocol is duck-typed, so nothing asked for `name`, `identity`,
`threshold` or `tolerance` until the first reader did. Measured at `e82dc2b`:
each missing one was an `AttributeError` at first use, in `config_hash` or
while the run was prepared, and exited 70. A user's mistake read as digline
failing (#420). A check with no `__call__` exited 0, with an errored verdict
on every case, after every call to the target had been paid for.

ADR 0041 §4.1 rule 2 already rules this: the missing sentence is digline's
defect. The repair writes the sentence, a refusal with where the class is
written, and makes it before anything is paid for. The `Suite`'s lists are
frozen too, because an `append` after construction skipped every check in
`__post_init__`, not only this one.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from tests._helpers import cli, git, suite_source

from digline.cli import EXIT_USAGE
from digline.core import AssertionShapeError, Contains
from digline.run import Case, Suite

SUITE = ("--suite", "suite_qa.py")

MEMBERS = {
    "name": "    name: str = 'mine'\n",
    "identity": "    identity: str = 'mine-1'\n",
    "threshold": "    threshold: float = 0.5\n",
    "tolerance": "    tolerance: float = 0.0\n",
}
CALL = "    def __call__(self, inputs):\n        raise AssertionError('never called')\n"


def declaring(body: str, *, field: str = "assertions") -> str:
    """The shared suite, with a check of the user's own added to `field`
    through the constructor, which runs `__post_init__`."""
    return suite_source() + (
        "\nimport dataclasses\n\n\n"
        "@dataclasses.dataclass(frozen=True)\n"
        f"class Mine:\n{body}\n\n"
        f"suite = dataclasses.replace(suite, {field}=[*suite.{field}, Mine()])\n"
    )


def committed(root: Path, source: str) -> Path:
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "suite_qa.py").write_text(source, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def nothing_was_run(root: Path) -> bool:
    return not list((root / ".digline").rglob("runs/**/*.json"))


@pytest.mark.parametrize("missing", list(MEMBERS))
def test_a_check_missing_a_member_digline_reads_is_refused_before_the_run(
    tmp_path: Path, missing: str
) -> None:
    body = "".join(text for name, text in MEMBERS.items() if name != missing) + CALL
    root = committed(tmp_path, declaring(body))

    done = cli(root, "run", *SUITE)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "AssertionShapeError: Mine, defined at " in done.stderr
    assert f"is declared as an assertion and has no `{missing}`" in done.stderr
    assert "Traceback" not in done.stderr
    assert nothing_was_run(root)


def test_the_refusal_names_where_the_class_is_written(tmp_path: Path) -> None:
    """The location is read from the class's own code objects, never from the
    file: the core reads none."""
    body = MEMBERS["name"] + CALL
    root = committed(tmp_path, declaring(body))
    line = next(
        number
        for number, text in enumerate(
            (root / "suite_qa.py").read_text(encoding="utf-8").splitlines(), start=1
        )
        if "def __call__" in text
    )

    done = cli(root, "run", *SUITE)

    assert f"suite_qa.py:{line} is declared as an assertion" in done.stderr
    assert "has no `identity`, `threshold`, `tolerance`" in done.stderr


def test_a_check_that_cannot_be_called_is_refused_before_anything_is_paid(
    tmp_path: Path,
) -> None:
    """It exited 0, with an errored verdict on every case, once every call to
    the target had been paid for. Refuse before paying is the rule preflight
    already keeps for a model that has no price."""
    root = committed(tmp_path, declaring("".join(MEMBERS.values())))

    done = cli(root, "run", *SUITE)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "has no `__call__`" in done.stderr
    assert nothing_was_run(root)


def test_a_run_assertion_of_the_wrong_shape_is_refused(tmp_path: Path) -> None:
    root = committed(
        tmp_path, declaring(MEMBERS["name"] + CALL, field="run_assertions")
    )

    done = cli(root, "run", *SUITE)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "is declared as a run assertion and has no `identity`" in done.stderr
    assert "`over`, `requires_label`" in done.stderr
    assert "Inherit RunAssertionBase" in done.stderr


def test_appending_after_the_suite_is_built_is_refused_on_the_suites_line(
    tmp_path: Path,
) -> None:
    """The bypass. Every check in `Suite.__post_init__` is made once, so a list
    appended to afterwards skipped all of them. A tuple has no `append`, and
    the mistake becomes the suite's own, refused with its line (ADR 0041 §4.1
    rule 3). It still exits 64."""
    root = committed(tmp_path, suite_source() + "\nsuite.assertions.append(None)\n")

    done = cli(root, "run", *SUITE)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "raised AttributeError" in done.stderr
    assert "while it was being loaded" in done.stderr
    assert "suite_qa.py:" in done.stderr


@pytest.mark.parametrize("field", ["assertions", "cases", "run_assertions"])
def test_the_suites_lists_are_frozen(field: str) -> None:
    """Each handed over as a list. `run_assertions` defaults to `()`, which is a
    tuple already, so leaving it out would test nothing.

    `run_assertions` was frozen on `main` before #420, because `expand_by_group`
    returns a tuple. For it this is a pin, not a repair: it passes without
    the change, and a mutation control confirmed that. It is here so that
    the day the expansion returns a list, a test says so."""
    suite = Suite(
        tenant="acme-bank",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="Rome")],
        cases=[Case(id="capital-it")],
        run_assertions=[],
    )
    assert isinstance(getattr(suite, field), tuple)


def test_the_check_is_the_same_for_a_library_caller() -> None:
    """Not a front end's rule: `Suite` refuses it wherever it is built."""

    @dataclasses.dataclass(frozen=True)
    class Bare:
        name: str = "bare"

    with pytest.raises(AssertionShapeError, match="has no `identity`"):
        Suite(
            tenant="acme-bank",
            environment="staging",
            name="qa",
            assertions=[Contains(needle="Rome"), Bare()],  # type: ignore[list-item]
            cases=[Case(id="capital-it")],
        )
