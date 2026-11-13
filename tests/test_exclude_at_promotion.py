"""A case left out of a reference by name, and the cases a run was made with.
(ADR 0065)

Found in a first use outside the project, on a Java application with a judged
suite: a reviewed answer the judge contradicted was removed from the suite
after the run, and `promote` refused the run on that case, with no way to
leave it out. Measured at `7264c725`: exit 64, condition 12, naming a case the
suite no longer declared. And a run of one case, promoted after a second was
declared, passed with the same `config_hash`.

Here the same story through the command line: condition 13 says it first, by
name, with `--exclude`; `--exclude CASE --by NAME` writes the reference without
the case and records it; the run file is not touched; `compare` and `where`
say what changed; and each limit of §1 is refused by name, beside a control
that promotes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli

from digline.cli import EXIT_OK, EXIT_USAGE

SUITE = """\
from digline.core import Accuracy, Contains, JudgeReply, LlmRubric
from digline.run import Case, Response, ReviewedAnswer, Suite


def judge(prompt):
    return JudgeReply(score=1.0, reason="fine")


def target(case):
    return Response(output="yes", cost_usd=0.0)


suite = Suite(
    tenant="acme", environment="dev", name="support",
    assertions=[
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.05),
        Contains(needle="yes", name="agrees"),
    ],
    run_assertions=[{aggregate}],
    cases=[{cases}],
    samples=2, min_agreement="2/2",
)
"""
KEPT = 'Case(id="kept", label="positive")'
#: A person's no, which the judge passes: the contradiction of the story.
SAID_NO = (
    'Case(id="said-no", reviewed_answer=ReviewedAnswer('
    'output="wrong", check="llm_rubric", good=False, input="q"))'
)
OTHER = 'Case(id="other", label="positive")'
ACCURACY = 'Accuracy(over="agrees", threshold=0.5, tolerance=0.05)'
RUNS = Path(".digline") / "acme" / "runs" / "support"
BASELINE = Path(".digline") / "acme" / "baselines" / "support.json"


def write(root: Path, *cases: str, aggregate: str = "") -> None:
    (root / "suite.py").write_text(
        SUITE.format(cases=", ".join(cases), aggregate=aggregate), encoding="utf-8"
    )


def ran(root: Path) -> str:
    """Run the suite as it is now, and return the run's key."""
    done = cli(root, "run", "--suite", "suite.py")
    assert done.returncode in (0, 1, 2), done.stderr
    return done.stdout.strip().splitlines()[-1]


def promote(root: Path, key: str, *extra: str, replacing: str = "none"):
    return cli(
        root,
        "promote",
        "--suite",
        "suite.py",
        "--run",
        key,
        "--replacing",
        replacing,
        *extra,
    )


@pytest.fixture
def dropped(tmp_path: Path) -> tuple[Path, str]:
    """The story: a run with the contradicted reviewed answer, then the answer
    removed from the suite."""
    write(tmp_path, KEPT, SAID_NO)
    key = ran(tmp_path)
    write(tmp_path, KEPT)
    return tmp_path, key


# -- condition 13 ------------------------------------------------------------ #


def test_the_dropped_case_is_named_with_the_flag_before_the_judge(
    dropped: tuple[Path, str],
) -> None:
    root, key = dropped
    done = promote(root, key)
    assert done.returncode == EXIT_USAGE
    assert "CasesChangedError" in done.stderr
    assert "no longer declares (said-no)" in done.stderr
    assert "--exclude CASE --by NAME" in done.stderr
    # Before 12: the person is not sent to the judge first.
    assert "contradicted a person" not in done.stderr
    assert not (root / BASELINE).exists()


def test_a_case_the_suite_added_is_named_with_run_again(tmp_path: Path) -> None:
    """The other half: what 1.2.0 promoted with exit 0, measured at
    `7264c725`, is refused, and the remedy is a new run."""
    write(tmp_path, KEPT)
    key = ran(tmp_path)
    write(tmp_path, KEPT, OTHER)
    done = promote(tmp_path, key)
    assert done.returncode == EXIT_USAGE
    assert "the suite declares 1 case(s) the run never ran (other)" in done.stderr
    assert "run the suite again" in done.stderr


def test_the_control_a_run_of_the_suites_own_cases_promotes(tmp_path: Path) -> None:
    write(tmp_path, KEPT, OTHER)
    done = promote(tmp_path, ran(tmp_path))
    assert done.returncode == EXIT_OK, done.stderr
    assert "excluded_at_promotion" not in (tmp_path / BASELINE).read_text("utf-8")


# -- --exclude ---------------------------------------------------------------- #


def test_exclude_writes_the_reference_without_the_case_and_says_who(
    dropped: tuple[Path, str],
) -> None:
    root, key = dropped
    [run_file] = (root / RUNS).glob("*.json")
    before = run_file.read_bytes()
    done = promote(root, key, "--exclude", "said-no", "--by", "Ada Rossi")
    assert done.returncode == EXIT_OK, done.stderr
    assert "excluded at promotion: said-no, by Ada Rossi" in done.stdout
    reference = json.loads((root / BASELINE).read_text("utf-8"))
    assert [case["case_id"] for case in reference["results"]] == ["kept"]
    [excluded] = reference["excluded_at_promotion"]
    assert (excluded["case_id"], excluded["by"]) == ("said-no", "Ada Rossi")
    assert excluded["at"] == reference["promoted_at"] != ""
    # The run is the measurement, and it is not touched.
    assert run_file.read_bytes() == before


def test_exclude_without_by_is_refused_by_name(dropped: tuple[Path, str]) -> None:
    root, key = dropped
    done = promote(root, key, "--exclude", "said-no")
    assert done.returncode == EXIT_USAGE
    assert "ExclusionRefusedError" in done.stderr
    assert "names nobody" in done.stderr
    assert not (root / BASELINE).exists()


def test_by_without_exclude_is_refused(tmp_path: Path) -> None:
    write(tmp_path, KEPT)
    done = promote(tmp_path, ran(tmp_path), "--by", "Ada Rossi")
    assert done.returncode == EXIT_USAGE
    assert "--by names who leaves a case out" in done.stderr
    assert not (tmp_path / BASELINE).exists()


def test_a_case_the_run_does_not_carry_is_refused(dropped: tuple[Path, str]) -> None:
    root, key = dropped
    done = promote(root, key, "--exclude", "nowhere", "--by", "Ada Rossi")
    assert done.returncode == EXIT_USAGE
    assert "carries no case nowhere" in done.stderr
    assert not (root / BASELINE).exists()


def test_a_case_the_suite_still_declares_is_refused(tmp_path: Path) -> None:
    """Limit 2: excluding a case that still gates would get round 3, 5 and
    12. The story without the suite's edit: `said-no` is still declared."""
    write(tmp_path, KEPT, SAID_NO)
    key = ran(tmp_path)
    done = promote(tmp_path, key, "--exclude", "said-no", "--by", "Ada Rossi")
    assert done.returncode == EXIT_USAGE
    assert "the suite still declares said-no" in done.stderr
    assert not (tmp_path / BASELINE).exists()


def test_a_run_with_run_level_checks_excludes_nothing(tmp_path: Path) -> None:
    """Limit 3, with its control: the same story with an aggregate refuses
    the exclusion; the story without one, above, promotes."""
    write(tmp_path, KEPT, OTHER, aggregate=ACCURACY)
    key = ran(tmp_path)
    write(tmp_path, KEPT, aggregate=ACCURACY)
    done = promote(tmp_path, key, "--exclude", "other", "--by", "Ada Rossi")
    assert done.returncode == EXIT_USAGE
    assert "has run-level checks" in done.stderr
    assert not (tmp_path / BASELINE).exists()


# -- what compare and where say ---------------------------------------------- #


def test_compare_says_the_exclusion_and_moves_no_exit_code(
    dropped: tuple[Path, str],
) -> None:
    root, key = dropped
    assert promote(root, key, "--exclude", "said-no", "--by", "Ada").returncode == 0
    after = ran(root)
    done = cli(root, "compare", "--suite", "suite.py", "--run", after)
    assert done.returncode == EXIT_OK, done.stdout + done.stderr
    assert (
        "1 case was excluded at promotion from the reference: said-no, by Ada."
        in done.stdout
    )
    full = json.loads(
        cli(
            root, "compare", "--suite", "suite.py", "--run", after, "--json", "full"
        ).stdout
    )
    assert (full["cases_excluded"], full["exit_code"]) == (1, 0)
    [item] = full["excluded_at_promotion"]
    assert (item["case_id"], item["by"]) == ("said-no", "Ada")


def test_compare_names_the_cases_on_one_side_only(tmp_path: Path) -> None:
    write(tmp_path, KEPT)
    assert promote(tmp_path, ran(tmp_path)).returncode == EXIT_OK
    write(tmp_path, OTHER)
    after = ran(tmp_path)
    done = cli(tmp_path, "compare", "--suite", "suite.py", "--run", after, "--json")
    payload = json.loads(done.stdout)
    assert (payload["cases_added"], payload["cases_removed"]) == (1, 1)
    assert (
        "The cases changed since the reference: 1 added (other); 1 removed (kept)."
        in payload["sentence"]
    )
    # Reported, never gated: the run's own verdicts decide its code.
    assert payload["exit_code"] == done.returncode


def test_compare_says_nothing_of_cases_where_they_are_the_same(
    tmp_path: Path,
) -> None:
    """The control for the two above."""
    write(tmp_path, KEPT)
    assert promote(tmp_path, ran(tmp_path)).returncode == EXIT_OK
    after = ran(tmp_path)
    payload = json.loads(
        cli(tmp_path, "compare", "--suite", "suite.py", "--run", after, "--json").stdout
    )
    assert (payload["cases_added"], payload["cases_removed"]) == (0, 0)
    assert payload["cases_excluded"] == 0
    assert "cases changed" not in payload["sentence"]


def test_where_stops_at_the_dropped_case_before_the_judge(
    dropped: tuple[Path, str],
) -> None:
    root, _ = dropped
    payload = json.loads(
        cli(root, "where", "--tenant", "acme", "--suite", "suite.py", "--json").stdout
    )
    assert (payload["state"], payload["count"]) == ("cases_changed", 1)
    assert payload["next"]["command"].startswith("digline run --suite")


def test_where_without_the_edit_reads_the_judge(tmp_path: Path) -> None:
    """The control: the same run with the suite unchanged stops at the judge."""
    write(tmp_path, KEPT, SAID_NO)
    ran(tmp_path)
    payload = json.loads(
        cli(
            tmp_path, "where", "--tenant", "acme", "--suite", "suite.py", "--json"
        ).stdout
    )
    assert payload["state"] == "judge_disagrees"


# -- what explain says ------------------------------------------------------- #


def test_explain_says_both_after_the_counts_in_the_terminal_alone(
    dropped: tuple[Path, str],
) -> None:
    """The two sentences `compare` says, among the facts after the counts, as
    text: `--json` carries neither, as it carries no judge's words. (P-1676)"""
    root, key = dropped
    assert promote(root, key, "--exclude", "said-no", "--by", "Ada").returncode == 0
    write(root, KEPT, OTHER)
    after = ran(root)
    done = cli(root, "explain", "--suite", "suite.py", "--run", after)
    lines = done.stdout.splitlines()
    changed = "The cases changed since the reference: 1 added (other)."
    excluded = "1 case was excluded at promotion from the reference: said-no, by Ada."
    at = [index for index, line in enumerate(lines) if line.startswith(changed)]
    assert at, done.stdout
    assert lines[at[0] + 1] == excluded
    # After the counts, before the settings: the first blank line closes the
    # counts, and it comes after both.
    assert lines.index("") == at[0] + 2
    assert "2 cases ran." in lines[: at[0]]
    payload = cli(
        root, "explain", "--suite", "suite.py", "--run", after, "--json"
    ).stdout
    assert "said-no" not in payload
    assert "cases changed" not in payload
    assert "excluded at promotion" not in payload


def test_explain_says_nothing_of_cases_where_they_are_the_same(
    tmp_path: Path,
) -> None:
    """The control: the same cases on both sides, nothing excluded."""
    write(tmp_path, KEPT)
    assert promote(tmp_path, ran(tmp_path)).returncode == EXIT_OK
    after = ran(tmp_path)
    done = cli(tmp_path, "explain", "--suite", "suite.py", "--run", after)
    assert "cases changed" not in done.stdout
    assert "excluded at promotion" not in done.stdout
