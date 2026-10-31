"""`digline run` says where the run went and what to type next. (B0, P-1072)

Two lines on standard error, after the key, which stays alone on standard
output:

    digline: recorded <the path of the document this run wrote>
    digline: next: <command>  # <what it does>

The `# …` is a shell comment on purpose: the line without its prefix can be
pasted whole and it runs.

Seven states, and a fixed count of each line in each:

| state                                           | recorded | next    |
|-------------------------------------------------|----------|---------|
| 1. no reference                                 | 1        | promote |
| 1b. no reference, a run `promote` would refuse  | 1        | explain |
| 2. a reference present                          | 1        | compare |
| 3. a reference accepted on its schema, by flag  | 1        | migrate |
| 4. written, nothing judged                      | 1        | none    |
| 5. refused on the reference's schema            | 0        | none    |
| 6. failed before writing                        | 0        | none    |

- `recorded` comes out if and only if a document was written, and it names a
  path that exists.
- `next` names a command that uses what this run produced. State 4 produced
  nothing to use, so it says none, with a reference present too.
- `next` never names a command this run's own state will make refused. State
  1b is a run with a case that could not be judged, or any refusal its
  document carries: `promote` refuses it, so `next` names `explain`. (#844)
- States 5 and 6 carry their instruction in the refusal.
- `run` says nothing about whether the reference is any good: a file there is
  enough to name `compare`, and `compare` judges it. State 3 is not a
  judgement either: it is what the person declared with
  `--accepting-baseline-schema`, that the reference is at an older schema, and
  `compare` refuses such a reference until it is migrated.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from tests._helpers import cli

from digline.cli import EXIT_OK, EXIT_UNJUDGED, EXIT_USAGE
from digline.core.run import SCHEMA_VERSION

RECORDED = "digline: recorded "
NEXT = "digline: next: "
PROMOTE_SAYS = "  # keeps this run as the reference"
COMPARE_SAYS = "  # says whether anything got worse"
MIGRATE_SAYS = "  # brings the store to this digline's schema"

SUITE = """
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="dev",
    name="hello",
    assertions=[Contains(needle="hello")],
    cases=[Case(id="greet")],
)


def target(case):
    return Response(output="hello world")
"""

DOWN = SUITE.replace(
    'return Response(output="hello world")', 'raise TimeoutError("the app is down")'
)


def lines(stderr: str, prefix: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith(prefix)]


def repo(root: Path, source: str = SUITE, name: str = "suite.py") -> Path:
    (root / name).write_text(source, encoding="utf-8")
    return root


def promote(root: Path, suite: str = "suite.py") -> None:
    done = cli(
        root, "promote", "--suite", suite, "--run", "latest", "--replacing", "none"
    )
    assert done.returncode == EXIT_OK, done.stderr


def recorded_path(root: Path, line: str) -> Path:
    return root / line.removeprefix(RECORDED)


# --------------------------------------------------------------------------- #
# The six rows
# --------------------------------------------------------------------------- #


def test_no_reference_says_recorded_and_next_promote(tmp_path: Path) -> None:
    ran = cli(repo(tmp_path), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    assert recorded_path(tmp_path, recorded).is_file()
    assert lines(ran.stderr, NEXT) == [
        "digline: next: digline promote --suite suite.py --run latest "
        f"--replacing none{PROMOTE_SAYS}"
    ]


def test_a_reference_present_says_recorded_and_next_compare(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    assert recorded_path(root, recorded).is_file()
    assert lines(ran.stderr, NEXT) == [
        f"digline: next: digline compare --suite suite.py --run latest{COMPARE_SAYS}"
    ]


def older_reference(root: Path) -> int:
    """Promote a run, then mark the reference one schema older: what a store
    an earlier digline wrote looks like to this one. The schema it now says."""
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    (baseline,) = (root / ".digline").glob("*/baselines/hello.json")
    document = json.loads(baseline.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    baseline.write_text(json.dumps(document), encoding="utf-8")
    return SCHEMA_VERSION - 1


def test_a_reference_accepted_on_its_schema_says_next_migrate(tmp_path: Path) -> None:
    """The run went through because the person named the reference's schema.
    `compare` refuses that reference until it is migrated, so the command after
    the run is `migrate`, and pasted, it lets `compare` read the reference."""
    root = repo(tmp_path)
    older = older_reference(root)
    ran = cli(
        root, "run", "--suite", "suite.py", "--accepting-baseline-schema", str(older)
    )
    assert ran.returncode == EXIT_OK, ran.stderr
    assert len(lines(ran.stderr, RECORDED)) == 1
    assert lines(ran.stderr, NEXT) == [
        f"digline: next: digline migrate --suite suite.py{MIGRATE_SAYS}"
    ]
    pasted(root, lines(ran.stderr, NEXT)[0])
    compared = cli(root, "compare", "--suite", "suite.py", "--run", "latest")
    assert compared.returncode == EXIT_OK, compared.stderr


def test_the_migrate_line_repeats_the_options_that_move_where_it_looks(
    tmp_path: Path,
) -> None:
    """`migrate` takes `--root`, `--tenant` and `--env`, and no target."""
    store = tmp_path / "store"
    store.mkdir()
    repo(tmp_path)
    given = ("--root", "store", "--tenant", "acme", "--env", "dev")
    assert cli(tmp_path, "run", "--suite", "suite.py", *given).returncode == EXIT_OK
    promoted = cli(
        tmp_path, "promote", "--suite", "suite.py", "--run", "latest",
        "--replacing", "none", *given,
    )  # fmt: skip
    assert promoted.returncode == EXIT_OK, promoted.stderr
    (baseline,) = store.glob(".digline/*/baselines/hello.json")
    document = json.loads(baseline.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    baseline.write_text(json.dumps(document), encoding="utf-8")
    ran = cli(
        tmp_path, "run", "--suite", "suite.py", *given,
        "--target", "suite.py:target",
        "--accepting-baseline-schema", str(SCHEMA_VERSION - 1),
    )  # fmt: skip
    assert ran.returncode == EXIT_OK, ran.stderr
    assert lines(ran.stderr, NEXT) == [
        "digline: next: digline migrate --suite suite.py "
        f"--root store --tenant acme --env dev{MIGRATE_SAYS}"
    ]
    pasted(tmp_path, lines(ran.stderr, NEXT)[0])


def test_nothing_judged_says_recorded_and_no_next(tmp_path: Path) -> None:
    ran = cli(repo(tmp_path, DOWN), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_UNJUDGED, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    assert recorded_path(tmp_path, recorded).is_file()
    assert lines(ran.stderr, NEXT) == []


def test_nothing_judged_says_no_next_with_a_reference_present(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    repo(root, DOWN)
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_UNJUDGED, ran.stderr
    assert len(lines(ran.stderr, RECORDED)) == 1
    assert lines(ran.stderr, NEXT) == []


def test_a_refusal_on_the_schema_says_neither(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    (baseline,) = (root / ".digline").glob("*/baselines/hello.json")
    document = json.loads(baseline.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    baseline.write_text(json.dumps(document), encoding="utf-8")
    runs_before = sorted((root / ".digline").glob("*/runs/*/*.json"))
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_USAGE, ran.stderr
    assert "could not be compared" in ran.stderr
    assert lines(ran.stderr, RECORDED) == []
    assert lines(ran.stderr, NEXT) == []
    assert sorted((root / ".digline").glob("*/runs/*/*.json")) == runs_before


def test_a_failure_before_writing_says_neither(tmp_path: Path) -> None:
    source = SUITE.replace("def target(case):", "def not_the_target(case):")
    ran = cli(repo(tmp_path, source), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_USAGE, ran.stderr
    assert "has no attribute 'target'" in ran.stderr
    assert lines(ran.stderr, RECORDED) == []
    assert lines(ran.stderr, NEXT) == []
    assert not list(tmp_path.glob(".digline/*/runs/*/*.json"))


# --------------------------------------------------------------------------- #
# The rules the table holds
# --------------------------------------------------------------------------- #


def test_the_key_stays_alone_on_standard_output(tmp_path: Path) -> None:
    """The action reads standard output as the run key."""
    ran = cli(repo(tmp_path), "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (key,) = ran.stdout.splitlines()
    assert RECORDED not in ran.stdout and NEXT not in ran.stdout
    assert lines(ran.stderr, RECORDED) == [
        f"digline: recorded .digline/acme/runs/hello/{key}.json"
    ]


def test_the_recorded_path_is_read_from_where_the_command_ran(tmp_path: Path) -> None:
    """Relative to `--root`, which is where `.digline/` is: the path a person
    reads from the folder they typed the command in."""
    store = tmp_path / "store"
    store.mkdir()
    repo(tmp_path)
    ran = cli(tmp_path, "run", "--suite", "suite.py", "--root", "store")
    assert ran.returncode == EXIT_OK, ran.stderr
    (recorded,) = lines(ran.stderr, RECORDED)
    path = recorded.removeprefix(RECORDED)
    assert path.startswith("store/.digline/")
    assert (tmp_path / path).is_file()


def test_next_repeats_the_options_that_move_where_it_looks(tmp_path: Path) -> None:
    """`--root`, `--tenant` and `--env` on both commands, `--target` on
    `promote` alone: `compare` takes no target."""
    store = tmp_path / "store"
    store.mkdir()
    repo(tmp_path)
    given = ("--root", "store", "--tenant", "acme", "--env", "dev")
    ran = cli(
        tmp_path, "run", "--suite", "suite.py", *given, "--target", "suite.py:target"
    )
    assert ran.returncode == EXIT_OK, ran.stderr
    assert lines(ran.stderr, NEXT) == [
        "digline: next: digline promote --suite suite.py --run latest "
        "--replacing none --root store --tenant acme --env dev "
        f"--target suite.py:target{PROMOTE_SAYS}"
    ]
    promote_line = lines(ran.stderr, NEXT)[0]
    pasted(tmp_path, promote_line)
    again = cli(tmp_path, "run", "--suite", "suite.py", *given)
    assert lines(again.stderr, NEXT) == [
        "digline: next: digline compare --suite suite.py --run latest "
        f"--root store --tenant acme --env dev{COMPARE_SAYS}"
    ]


def pasted(root: Path, line: str) -> subprocess.CompletedProcess[str]:
    """The line without its prefix, run as a shell would: the comment dropped,
    the words split as the shell splits them, `digline` as this interpreter's."""
    words = shlex.split(line.removeprefix("digline: next: "), comments=True)
    assert words[0] == "digline"
    done = subprocess.run(
        [sys.executable, "-m", "digline.cli", *words[1:]],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == EXIT_OK, done.stderr
    return done


def test_each_next_line_pasted_whole_runs(tmp_path: Path) -> None:
    root = repo(tmp_path)
    first = cli(root, "run", "--suite", "suite.py")
    (promote_line,) = lines(first.stderr, NEXT)
    pasted(root, promote_line)
    second = cli(root, "run", "--suite", "suite.py")
    (compare_line,) = lines(second.stderr, NEXT)
    compared = pasted(root, compare_line)
    assert "Nothing got worse" in compared.stdout


def test_a_suite_path_with_a_space_is_quoted_so_it_pastes(tmp_path: Path) -> None:
    root = repo(tmp_path, name="my suite.py")
    ran = cli(root, "run", "--suite", "my suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (line,) = lines(ran.stderr, NEXT)
    assert "--suite 'my suite.py'" in line
    pasted(root, line)


def test_a_reference_compare_would_refuse_still_names_compare(tmp_path: Path) -> None:
    """A file there is enough: whether it is a usable reference is `compare`'s
    to say, and `run` judges nothing about it."""
    root = repo(tmp_path)
    assert cli(root, "run", "--suite", "suite.py").returncode == EXIT_OK
    promote(root)
    (baseline,) = (root / ".digline").glob("*/baselines/hello.json")
    baseline.write_text("not json", encoding="utf-8")
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    assert lines(ran.stderr, NEXT) == [
        f"digline: next: digline compare --suite suite.py --run latest{COMPARE_SAYS}"
    ]


# --------------------------------------------------------------------------- #
# #844: `next` never names a command this run's own state will refuse
# --------------------------------------------------------------------------- #

EXPLAIN_SAYS = "  # reads this run back; promote would refuse it"

#: #844's suite: a judge that raises on the cases named, and a `Contains` that
#: passes on every case, so the run is never one that judged nothing.
JUDGED = """
from digline.core import Contains, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

RAISE_ON = %s


def judge(prompt):
    if any(f"[{case}]" in prompt for case in RAISE_ON):
        raise RuntimeError("judge unavailable")
    return JudgeReply(score=0.9, reason="fine")


def target(case):
    return Response(output=f"hello world [{case.id}]")


suite = Suite(
    tenant="t",
    environment="e",
    name="lent",
    assertions=[
        LlmRubric(rubric="is it good", judge=judge, threshold=0.5, tolerance=0.1),
        Contains("hello"),
    ],
    cases=[Case(id=f"c{i}") for i in range(1, 5)],
)
"""

#: The judge raises on no case, on one, and on all four: the issue measured
#: the last, and named the second as not measured.
RAISING = {
    "no case errored": "set()",
    "one case errored": '{"c1"}',
    "every case errored": '{"c1", "c2", "c3", "c4"}',
}


def promote_as_typed(root: Path) -> subprocess.CompletedProcess[str]:
    return cli(
        root, "promote", "--suite", "suite.py", "--run", "latest", "--replacing", "none"
    )


def run_judged(root: Path, raising: str) -> str:
    repo(root, JUDGED % RAISING[raising])
    ran = cli(root, "run", "--suite", "suite.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    (line,) = lines(ran.stderr, NEXT)
    return line


def test_a_run_promote_would_refuse_is_not_told_to_promote(tmp_path: Path) -> None:
    """#844, as the issue measured it: every judge call raised, `run` said
    `next: digline promote …`, and that command, typed as printed, exited 64
    with `ErroredRunError`. The line names `explain` instead."""
    line = run_judged(tmp_path, "every case errored")
    assert line == (
        f"digline: next: digline explain --suite suite.py --run latest{EXPLAIN_SAYS}"
    )


def test_one_errored_case_is_enough_to_name_explain(tmp_path: Path) -> None:
    """The case the issue did not measure: one case errored beside three
    judged. `promote` refuses that run too, so `run` may not name it."""
    line = run_judged(tmp_path, "one case errored")
    assert "digline promote" not in line, line
    assert "digline explain" in line, line


def test_a_run_promote_accepts_is_still_told_to_promote(tmp_path: Path) -> None:
    """The control: the judge answers, and the line names `promote`."""
    line = run_judged(tmp_path, "no case errored")
    assert line == (
        "digline: next: digline promote --suite suite.py --run latest "
        f"--replacing none{PROMOTE_SAYS}"
    )


@pytest.mark.parametrize("raising", list(RAISING))
def test_next_never_names_a_command_this_run_will_refuse(
    tmp_path: Path, raising: str
) -> None:
    """The closing criterion of #844, which can fail: the `next` line, typed as
    printed, is never refused. `promote` is typed as well, in every state, so
    each state says which side of the criterion it is on: where `promote`
    refuses, the line names something else, and what it names runs."""
    line = run_judged(tmp_path, raising)
    words = shlex.split(line.removeprefix(NEXT), comments=True)
    done = subprocess.run(
        [sys.executable, "-m", "digline.cli", *words[1:]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # A verdict is not a refusal: `explain` says 2 about a run with a case that
    # could not be judged, and 0, 1 and 2 each mean digline ran.
    assert done.returncode in (EXIT_OK, EXIT_UNJUDGED), done.stderr
    assert "Error:" not in done.stderr, done.stderr
    if words[1] == "explain":
        assert "could not be judged" in done.stdout, done.stdout
        assert promote_as_typed(tmp_path).returncode == EXIT_USAGE
    else:
        assert words[1] == "promote"
