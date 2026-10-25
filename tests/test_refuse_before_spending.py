"""`run` and `rejudge` read the baseline's schema before they spend. (#621)

A baseline at a schema this digline cannot read makes every comparison exit 64,
so a run made against it is paid for and cannot be compared. Until #621 `run`
called the target, wrote the run beside the unreadable baseline and exited 0,
and `rejudge` called the judge the same way.

**The tests count the calls.** The suite's target and judge append a line per
call, and every refusal here asserts that no line was written. A test that read
only the exit code would be green with the refusal raised after the spending,
which is exactly the repair that does not repair this.

**Only a schema refusal is anticipated, and that is a choice held here.** A
baseline whose JSON is broken, or that declares another tenant, raises from the
same read, and both are left to `compare`: anticipating them would make `run`
depend on the whole shape of the baseline, which is `compare`'s work. The
schema is told apart by the attribute `DocumentRefusedError` carries, not by
its type, which a broken file shares.

**Both directions, after ADR 0014 §5: the refusal is symmetric, the advice is
not.** A newer baseline asks for a newer digline and must not say `migrate`,
which §5 names as the wrong advice that way; an older one names `migrate`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _helpers import cli
from digline.cli import EXIT_OK, EXIT_USAGE
from digline.core import DocumentRefusedError, run_from_json
from digline.core.run import SCHEMA_VERSION

SUITE = """
from pathlib import Path
from digline.core import Contains, LlmRubric, JudgeReply
from digline.run import Case, Response, Suite

HERE = Path(__file__).parent


def _count(name):
    with open(HERE / name, "a", encoding="utf-8") as log:
        log.write("1\\n")


def judge(prompt):
    _count("judge.log")
    return JudgeReply(score=1.0, reason="looked")


suite = Suite(
    tenant="acme",
    environment="staging",
    name="probe",
    assertions=[
        Contains(needle="Rome"),
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.1),
    ],
    cases=[Case(id="one"), Case(id="two")],
    record_responses=True,
)


def target(case):
    _count("target.log")
    return Response(output="Rome", input="capital?")
"""

FLAG = "--accepting-baseline-schema"


def _calls(root: Path, name: str) -> int:
    log = root / name
    return len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0


def _runs(root: Path) -> int:
    return len(list((root / ".digline").glob("*/runs/*/*.json")))


def _run(root: Path, *extra: str) -> tuple[int, str, str]:
    done = cli(root, "run", "--suite", "suite.py", *extra)
    return done.returncode, done.stdout.strip(), done.stderr


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A repository with one run promoted as the baseline."""
    (tmp_path / "suite.py").write_text(SUITE, encoding="utf-8")
    code, key, err = _run(tmp_path)
    assert code == EXIT_OK, err
    done = cli(
        tmp_path, "promote", "--suite", "suite.py", "--run", key, "--replacing", "none"
    )
    assert done.returncode == EXIT_OK, done.stderr
    return tmp_path


def _baseline(root: Path) -> Path:
    (path,) = (root / ".digline").glob("*/baselines/probe.json")
    return path


def _declare(root: Path, schema: int) -> None:
    path = _baseline(root)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = schema
    path.write_text(json.dumps(document), encoding="utf-8")


NEWER = SCHEMA_VERSION + 1
OLDER = SCHEMA_VERSION - 1


def test_the_schema_refusal_carries_the_schema_and_a_broken_file_does_not() -> None:
    """The attribute is what tells the two apart, since the type cannot."""
    with pytest.raises(DocumentRefusedError) as schema:
        run_from_json(json.dumps({"schema_version": NEWER}))
    assert schema.value.declared_schema == NEWER
    with pytest.raises(DocumentRefusedError) as broken:
        run_from_json("{ not json")
    assert broken.value.declared_schema is None


def test_run_refuses_a_newer_baseline_before_calling_the_target(store: Path) -> None:
    _declare(store, NEWER)
    before = (_calls(store, "target.log"), _calls(store, "judge.log"), _runs(store))
    code, _, err = _run(store)
    assert code == EXIT_USAGE, err
    assert (_calls(store, "target.log"), _calls(store, "judge.log"), _runs(store)) == (
        before
    )
    assert f"schema {NEWER}" in err
    assert "Upgrade digline" in err
    assert "migrate" not in err


def test_run_refuses_an_older_baseline_and_names_migrate(store: Path) -> None:
    _declare(store, OLDER)
    before = _calls(store, "target.log")
    code, _, err = _run(store)
    assert code == EXIT_USAGE, err
    assert _calls(store, "target.log") == before
    assert "digline migrate" in err
    assert "Upgrade digline" not in err


def test_rejudge_refuses_before_calling_the_judge(store: Path) -> None:
    """The same defect from the other command that spends: the judge is paid
    and the run it writes cannot be compared."""
    (source,) = (store / ".digline").glob("*/runs/*/*.json")
    _declare(store, NEWER)
    before = (_calls(store, "judge.log"), _runs(store))
    done = cli(store, "rejudge", "--suite", "suite.py", "--run", source.stem)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert (_calls(store, "judge.log"), _runs(store)) == before
    assert f"schema {NEWER}" in done.stderr


def test_without_a_baseline_a_first_run_is_not_refused(tmp_path: Path) -> None:
    (tmp_path / "suite.py").write_text(SUITE, encoding="utf-8")
    code, _, err = _run(tmp_path)
    assert code == EXIT_OK, err
    assert _calls(tmp_path, "target.log") == 2
    assert _runs(tmp_path) == 1


@pytest.mark.parametrize("schema", [NEWER, OLDER])
def test_naming_the_schema_runs_and_says_so(store: Path, schema: int) -> None:
    _declare(store, schema)
    before = (_calls(store, "target.log"), _runs(store))
    code, _, err = _run(store, FLAG, str(schema))
    assert code == EXIT_OK, err
    assert (_calls(store, "target.log"), _runs(store)) == (before[0] + 2, before[1] + 1)
    assert f"accepted, by {FLAG}, a baseline at schema {schema}" in err


def test_naming_another_schema_is_refused(store: Path) -> None:
    _declare(store, NEWER)
    before = _calls(store, "target.log")
    code, _, err = _run(store, FLAG, str(NEWER + 1))
    assert code == EXIT_USAGE, err
    assert _calls(store, "target.log") == before
    assert f"{FLAG} {NEWER + 1} names schema {NEWER + 1}" in err
    assert f"the baseline declares schema {NEWER}" in err


def test_naming_a_schema_where_the_baseline_is_readable_is_refused(store: Path) -> None:
    """As `--accepting-pin` naming a path where nothing moved: an acceptance of
    nothing is a mistake, not a no-op."""
    before = _calls(store, "target.log")
    code, _, err = _run(store, FLAG, str(SCHEMA_VERSION))
    assert code == EXIT_USAGE, err
    assert _calls(store, "target.log") == before
    assert "there is nothing to accept" in err


def test_a_broken_baseline_is_left_to_compare(store: Path) -> None:
    """The hard case: the same exception type, and not anticipated, because its
    `declared_schema` is empty. `run` spends, and the refusal comes at
    `compare`."""
    _baseline(store).write_text("{ this is not json", encoding="utf-8")
    before = _calls(store, "target.log")
    code, _, err = _run(store)
    assert code == EXIT_OK, err
    assert _calls(store, "target.log") == before + 2
    done = cli(store, "compare", "--suite", "suite.py", "--run", "latest")
    assert done.returncode == EXIT_USAGE
    assert "DocumentRefusedError" in done.stderr


def test_a_baseline_of_another_tenant_is_left_to_compare(store: Path) -> None:
    """A choice, held: `run` does not take on the rest of the baseline's
    shape. The tenant refusal still comes, at `compare`."""
    path = _baseline(store)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["tenant"] = "someone-else"
    path.write_text(json.dumps(document), encoding="utf-8")
    before = _calls(store, "target.log")
    code, _, err = _run(store)
    assert code == EXIT_OK, err
    assert _calls(store, "target.log") == before + 2
    done = cli(store, "compare", "--suite", "suite.py", "--run", "latest")
    assert done.returncode == EXIT_USAGE
    assert "TenantMismatchError" in done.stderr
