"""The two-run report: `diff()`, its copy, its command, and the view's two modes.

ADR 0008's test plan, in the order it is written there. The two that would catch
this ADR being undone are `test_swapping_the_arguments_swaps_the_columns` and
`test_the_report_carries_no_verdict_vocabulary`: the first is the property the
whole command turns on, the second is the copy that makes it readable as one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from tests._helpers import cli, run_key, write_suite

from digline.cli import EXIT_OK, EXIT_USAGE
from digline.core import (
    Artifact,
    CaseResult,
    DifferentJudgesError,
    DifferentSuitesError,
    Run,
    Score,
    SystemConfig,
    Verdict,
    diff,
)
from digline.report import LOCALES, Locale, pages
from digline.report import diff as diff_report

LEFT_AT = "2026-09-04T09:12:33+00:00"
RIGHT_AT = "2026-09-04T11:40:07+00:00"
LABELS = ("2026-09-04 09:12", "2026-09-04 11:40")

JUDGE = SystemConfig(
    values={"provider": "anthropic", "model": "haiku"},
    identities=("anthropic/haiku",),
)


def verdict(
    name: str,
    score: float | None,
    *,
    threshold: float = 0.5,
    tolerance: float = 0.0,
    samples: tuple[float, ...] = (),
) -> Verdict:
    """`status` is derived, never passed in — `Verdict` refuses one that
    contradicts score-against-threshold, so there is nothing to override."""
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=threshold,
            tolerance=tolerance,
            status="error",
            reason="the judge did not answer",
            assertion_id=f"id-{name}",
        )
    return Verdict(
        score=Score(
            name=name,
            score=score,
            samples=samples,
            sample_min=min(samples) if samples else None,
            sample_max=max(samples) if samples else None,
        ),
        threshold=threshold,
        tolerance=tolerance,
        status="pass" if score >= threshold else "fail",  # type: ignore[arg-type]
        reason="judged",
        assertion_id=f"id-{name}",
    )


def run_of(
    *verdicts: Verdict,
    case: str = "case-1",
    created_at: str = LEFT_AT,
    cfg: str = "hash-a",
    tenant: str = "acme",
    suite: str = "qa",
    judge: SystemConfig = JUDGE,
    target: SystemConfig | None = None,
    aggregate: tuple[Verdict, ...] = (),
    artifacts: dict[str, Artifact] | None = None,
) -> Run:
    return Run(
        tenant=tenant,
        environment="staging",
        suite=suite,
        config_hash=cfg,
        created_at=created_at,
        results=(CaseResult(case_id=case, verdicts=verdicts),),
        aggregate=aggregate,
        judge_config=judge,
        target_config=target or SystemConfig(),
        artifacts=artifacts or {},
    )


# --------------------------------------------------------------------------- #
# The property: swapping the arguments swaps the columns and nothing else
# --------------------------------------------------------------------------- #


def mirrored_pairs() -> list[tuple[str, Run, Run]]:
    """Several shapes, because the promise is about every report and a single
    example proves it for one shape only. Each entry is named so a failure says
    which shape broke."""
    sampled_high = verdict("rubric", 0.95, samples=(0.9, 1.0), tolerance=0.02)
    sampled_low = verdict("rubric", 0.80, samples=(0.75, 0.85), tolerance=0.02)
    overlapping = verdict("rubric", 0.86, samples=(0.70, 0.95), tolerance=0.02)
    return [
        (
            "a plain numeric difference",
            run_of(verdict("contains", 0.9), created_at=LEFT_AT),
            run_of(verdict("contains", 0.4), created_at=RIGHT_AT),
        ),
        (
            "a flip in one direction",
            run_of(verdict("contains", 1.0), created_at=LEFT_AT),
            run_of(verdict("contains", 0.0), created_at=RIGHT_AT),
        ),
        (
            "a flip in the other direction",
            run_of(verdict("contains", 0.0), created_at=LEFT_AT),
            run_of(verdict("contains", 1.0), created_at=RIGHT_AT),
        ),
        (
            "disjoint intervals",
            run_of(sampled_high, created_at=LEFT_AT),
            run_of(sampled_low, created_at=RIGHT_AT),
        ),
        (
            "overlapping intervals",
            run_of(sampled_high, created_at=LEFT_AT),
            run_of(overlapping, created_at=RIGHT_AT),
        ),
        (
            "one side sampled and the other not",
            run_of(sampled_high, created_at=LEFT_AT),
            run_of(verdict("rubric", 0.80, tolerance=0.02), created_at=RIGHT_AT),
        ),
        (
            "a check present on one side only",
            run_of(verdict("contains", 0.9), verdict("extra", 0.5), created_at=LEFT_AT),
            run_of(verdict("contains", 0.9), created_at=RIGHT_AT),
        ),
        (
            "a check that could not run",
            run_of(verdict("contains", None), created_at=LEFT_AT),
            run_of(verdict("contains", 0.9), created_at=RIGHT_AT),
        ),
        (
            "an aggregate beside the cases",
            run_of(
                verdict("contains", 0.9),
                created_at=LEFT_AT,
                aggregate=(verdict("precision", 0.90, samples=(0.85, 0.95)),),
            ),
            run_of(
                verdict("contains", 0.9),
                created_at=RIGHT_AT,
                aggregate=(verdict("precision", 0.60, samples=(0.55, 0.65)),),
            ),
        ),
        (
            "two systems that differ",
            run_of(
                verdict("contains", 0.9),
                created_at=LEFT_AT,
                target=SystemConfig(
                    values={"provider": "p", "model": "m", "temperature": 0.3}
                ),
            ),
            run_of(
                verdict("contains", 0.4),
                created_at=RIGHT_AT,
                target=SystemConfig(
                    values={"provider": "p", "model": "m", "temperature": 0.7}
                ),
            ),
        ),
    ]


MIRROR: dict[str, str] = {
    "only_left": "only_right",
    "only_right": "only_left",
    "differs": "differs",
    "same": "same",
    "errored": "errored",
    "left": "right",
    "right": "left",
    "neither": "neither",
}


@pytest.mark.parametrize("name,left,right", mirrored_pairs(), ids=lambda v: v)
def test_swapping_the_arguments_swaps_the_columns(
    name: str, left: Run, right: Run
) -> None:
    """The property ADR 0008 §2 turns on, and the reason `diff` is a command of
    its own: there is no perspective to preserve, so there is nothing a swap can
    change except which column is which.

    Everything that has a side is exchanged; everything that does not is equal.
    `delta` negates, which is the two columns moving rather than the fact.
    """
    there, back = diff(left, right), diff(right, left)

    assert there.total == back.total
    assert there.differing == back.differing
    assert there.within_tolerance == back.within_tolerance
    assert there.errored == back.errored
    assert there.interval_pairs == back.interval_pairs
    assert (there.favours_left, there.favours_right) == (
        back.favours_right,
        back.favours_left,
    )
    assert (there.only_left, there.only_right) == (back.only_right, back.only_left)
    assert (there.left_exceeds, there.right_exceeds) == (
        back.right_exceeds,
        back.left_exceeds,
    )

    assert len(there.checks) == len(back.checks)
    for here, over in zip(there.checks, back.checks, strict=True):
        assert (here.case_id, here.assertion, here.scope) == (
            over.case_id,
            over.assertion,
            over.scope,
        )
        assert MIRROR[here.outcome] == over.outcome
        assert MIRROR[here.favours] == over.favours
        assert here.flipped is over.flipped
        assert here.tolerance == over.tolerance
        assert here.intervals_overlap is over.intervals_overlap
        assert here.intervals_disjoint is over.intervals_disjoint
        assert here.left_interval == over.right_interval
        assert here.right_interval == over.left_interval
        assert here.left == over.right and here.right == over.left
        if here.delta is None:
            assert over.delta is None
        else:
            assert over.delta == pytest.approx(-here.delta)


@pytest.mark.parametrize("name,left,right", mirrored_pairs(), ids=lambda v: v)
def test_the_sentence_swaps_with_the_columns(name: str, left: Run, right: Run) -> None:
    """The rendered sentence is the property too, not only the value it is built
    from: a count that swapped correctly and a sentence that named the wrong run
    would pass the test above and be wrong in the only place anybody reads."""
    labels = ("left-run", "right-run")
    there = diff_report.sentence(diff(left, right), locale="en", labels=labels)
    back = diff_report.sentence(
        diff(right, left), locale="en", labels=(labels[1], labels[0])
    )
    assert there == back


# --------------------------------------------------------------------------- #
# The refusals of §3
# --------------------------------------------------------------------------- #


def test_a_crossed_tenant_is_refused() -> None:
    """Fixed decision 8 does not become negotiable because the output is a
    report: one customer's numbers read as another's is arithmetically valid and
    factually nonsense in any document."""
    left = run_of(verdict("contains", 0.9), tenant="acme")
    right = run_of(verdict("contains", 0.9), tenant="globex")
    with pytest.raises(ValueError, match="cannot diff across tenants"):
        diff(left, right)


def test_two_suites_sharing_a_fingerprint_are_refused_on_the_name() -> None:
    """The same checks at the same bars over different cases produce the same
    `config_hash` legitimately. A report that named one suite while diffing two
    would be wrong in its header and nowhere else."""
    left = run_of(verdict("contains", 0.9), suite="qa")
    right = run_of(verdict("contains", 0.9), suite="acceptance")
    with pytest.raises(ValueError, match="cannot diff across suites"):
        diff(left, right)


def test_different_rules_are_refused_by_config_hash() -> None:
    left = run_of(verdict("contains", 0.9), cfg="hash-a")
    right = run_of(verdict("contains", 0.9), cfg="hash-b")
    with pytest.raises(DifferentSuitesError) as caught:
        diff(left, right)
    said = str(caught.value)
    assert "compare the rulers, not the systems" in said
    # The remedy, named. A refusal that does not say what to do instead is a
    # refusal that gets worked around.
    assert "re-run one side under the other's suite" in said


def test_different_judges_are_refused() -> None:
    other = SystemConfig(
        values={"provider": "openai", "model": "mini"},
        identities=("openai/mini",),
    )
    with pytest.raises(DifferentJudgesError) as caught:
        diff(
            run_of(verdict("rubric", 0.9), judge=JUDGE),
            run_of(verdict("rubric", 0.9), judge=other),
        )
    said = str(caught.value)
    assert "the instruments differ" in said
    assert "anthropic/haiku" in said and "openai/mini" in said
    assert "re-run one side under the other's judge" in said


def test_a_judge_recorded_on_one_side_only_is_refused() -> None:
    """The fourth state of the identity set, and the one that needed a decision.

    This is ADR 0005's `unknown`, and refusing on it is **not** reporting
    unknown-as-a-change — it is declining to report, which is what §5 protects.
    `compare()` may not refuse because the cure would be re-promoting a
    baseline; `diff()` may, because the cure is one re-run. (ADR 0008 §3)
    """
    with pytest.raises(DifferentJudgesError) as caught:
        diff(
            run_of(verdict("rubric", 0.9), judge=JUDGE),
            run_of(verdict("rubric", 0.9), judge=SystemConfig()),
        )
    said = str(caught.value)
    assert "cannot be established" in said
    assert "records none" in said


def test_two_suites_with_no_judge_at_all_are_diffable() -> None:
    """A suite of `Contains` and `Regex` declares no instrument, and so does a
    plain-function judge in a test. Refusing here would exclude most suites from
    the feature, which is not what "the instruments differ" means."""
    blank = SystemConfig()
    result = diff(
        run_of(verdict("contains", 0.9), judge=blank),
        run_of(verdict("contains", 0.4), judge=blank),
    )
    assert result.differing == 1
    assert result.judges == ()


# --------------------------------------------------------------------------- #
# What "differs" means (§4)
# --------------------------------------------------------------------------- #


def test_a_difference_counts_only_if_it_exceeds_both_declared_tolerances() -> None:
    """The `max` of §4, and the one case it exists for.

    Equal `config_hash` makes the two tolerances equal in every real suite; a
    suite declaring one identity twice at two tolerances is the crack, and a
    `left.tolerance` there would break symmetry.
    """
    wide = run_of(verdict("rubric", 0.90, tolerance=0.20))
    narrow = run_of(verdict("rubric", 0.80, tolerance=0.01))
    for a, b in ((wide, narrow), (narrow, wide)):
        (check,) = diff(a, b).checks
        assert check.tolerance == 0.20
        assert check.outcome == "same"


def test_a_flip_always_counts_and_carries_no_interval() -> None:
    """A tolerance is a statement about scores; a flip is a statement about
    outcomes. And the interval stays off it for ADR 0006 §6's reason: the
    intervals did not decide it, and a reader invited to check the scores
    against them would find both inside."""
    left = run_of(
        verdict("rubric", 0.55, threshold=0.5, tolerance=0.9, samples=(0.0, 1.0))
    )
    right = run_of(
        verdict("rubric", 0.45, threshold=0.5, tolerance=0.9, samples=(0.0, 1.0))
    )
    (check,) = diff(left, right).checks
    assert check.outcome == "differs" and check.flipped
    assert check.favours == "left"
    assert not check.intervals_overlap and not check.intervals_disjoint
    said = diff_report.detail(check, locale="en", labels=LABELS)
    assert "Observed intervals" not in said


def test_overlapping_intervals_are_evidence_and_never_an_excuse() -> None:
    """The one place diff parts from `compare()`: there the baseline's interval
    *decides*, because approval gives it the standing to say what its own noise
    is. Here neither run has that standing, so the difference is counted and the
    overlap is printed beside it."""
    left = run_of(verdict("rubric", 0.90, samples=(0.70, 0.99), tolerance=0.01))
    right = run_of(verdict("rubric", 0.75, samples=(0.60, 0.95), tolerance=0.01))
    (check,) = diff(left, right).checks
    assert check.outcome == "differs"
    assert check.intervals_overlap and not check.intervals_disjoint
    assert diff(left, right).differing == 1
    said = diff_report.detail(check, locale="en", labels=LABELS)
    assert "not distinguishable by this check" in said


def test_aggregates_participate_under_the_same_rules() -> None:
    left = run_of(
        verdict("contains", 0.9),
        aggregate=(verdict("precision", 0.90, samples=(0.88, 0.92)),),
    )
    right = run_of(
        verdict("contains", 0.9),
        aggregate=(verdict("precision", 0.60, samples=(0.58, 0.62)),),
    )
    result = diff(left, right)
    (aggregate,) = [c for c in result.checks if c.scope == "run"]
    assert aggregate.case_id == ""
    assert aggregate.outcome == "differs" and aggregate.favours == "left"
    assert aggregate.intervals_disjoint
    assert result.left_exceeds == 1


# --------------------------------------------------------------------------- #
# Mixed sampled and unsampled sides
# --------------------------------------------------------------------------- #


def test_a_pair_measured_on_one_side_only_is_left_out_of_the_population() -> None:
    """A check sampled on one side has one interval and no second one to be
    disjoint from. Counted as a difference, excluded from the count that says
    the difference exceeds both intervals, and shown with the interval it has.
    """
    left = run_of(verdict("rubric", 0.95, samples=(0.90, 1.0), tolerance=0.01))
    right = run_of(verdict("rubric", 0.60, tolerance=0.01))
    result = diff(left, right)
    (check,) = result.checks

    assert check.outcome == "differs" and check.favours == "left"
    assert check.left_interval.known and not check.right_interval.known
    assert not check.intervals_overlap and not check.intervals_disjoint
    assert result.interval_pairs == 0
    assert result.left_exceeds == 0

    said = diff_report.sentence(result, locale="en", labels=LABELS)
    # The failing version of this test is the one that prints "0 of …": a
    # sentence about an absent measurement reads as a null result. (§4)
    assert "exceed" not in said and "exceeds" not in said
    assert "0 of" not in said


def test_the_interval_sentence_appears_once_both_sides_measured() -> None:
    left = run_of(verdict("rubric", 0.95, samples=(0.90, 1.0), tolerance=0.01))
    right = run_of(verdict("rubric", 0.60, samples=(0.55, 0.65), tolerance=0.01))
    said = diff_report.sentence(diff(left, right), locale="en", labels=LABELS)
    assert "1 of 2026-09-04 09:12's advantages exceeds both runs' observed" in said


# --------------------------------------------------------------------------- #
# The copy, in both locales
# --------------------------------------------------------------------------- #


#: Words that assert one side is the standard. None of them may reach a diff.
VERDICT_WORDS = (
    "reference",
    "riferimento",
    "regressed",
    "improved",
    "worse",
    "peggior",
    "baseline",
    "got better",
    "still",
)


def rendered(locale: Locale) -> str:
    """One report exercising every row shape, as a reader sees it."""
    left = run_of(
        verdict("contains", 1.0),
        verdict("rubric", 0.95, samples=(0.90, 1.0), tolerance=0.01),
        verdict("only-here", 0.5),
        verdict("broken", None),
        created_at=LEFT_AT,
        target=SystemConfig(values={"provider": "p", "model": "m", "temperature": 0.3}),
        aggregate=(verdict("precision", 0.9, samples=(0.85, 0.95)),),
        artifacts={"prompt.md": Artifact(sha="a" * 64, text="one\ntwo\n")},
    )
    right = run_of(
        verdict("contains", 0.0),
        verdict("rubric", 0.60, samples=(0.55, 0.65), tolerance=0.01),
        verdict("broken", 0.9),
        created_at=RIGHT_AT,
        target=SystemConfig(values={"provider": "p", "model": "m", "temperature": 0.7}),
        aggregate=(verdict("precision", 0.5, samples=(0.45, 0.55)),),
        artifacts={"prompt.md": Artifact(sha="b" * 64, text="one\nthree\n")},
    )
    difference = diff(left, right)
    parts = [
        diff_report.sentence(difference, locale=locale, labels=LABELS),
        *diff_report.header_lines(difference, locale=locale, labels=LABELS),
        *diff_report.summary_lines(difference, locale=locale, labels=LABELS),
    ]
    return "\n".join(parts)


@pytest.mark.parametrize("locale", LOCALES)
def test_the_report_carries_no_verdict_vocabulary(locale: Locale) -> None:
    """The copy test ADR 0008 §2 asks for, and the one to read first when the
    report starts sounding like a comparison again.

    Every word here asserts that one side is the standard. Neither side is, and
    a copy change that reintroduces one should fail here rather than in a
    reader's hands.
    """
    text = rendered(locale).lower()
    found = [word for word in VERDICT_WORDS if word in text]
    assert not found, f"{locale}: the diff report says {found}"


@pytest.mark.parametrize("locale", LOCALES)
def test_the_report_renders_in_full_in_both_locales(locale: Locale) -> None:
    """A missing key raises rather than rendering an empty cell, so this is the
    check that every `diff.*` string exists in both tables."""
    text = rendered(locale)
    assert LABELS[0] in text and LABELS[1] in text
    assert "temperature 0.3" in text and "0.7" in text
    assert "prompt.md" in text
    assert "anthropic/haiku" in text
    assert "{" not in text, "an unformatted placeholder reached the reader"


def test_the_two_locales_say_the_same_things_about_the_same_report() -> None:
    """Not the same words — the same rows. A locale that silently dropped a
    line would read as a shorter report rather than as a broken one."""
    assert len(rendered("en").splitlines()) == len(rendered("it").splitlines())


def test_dates_are_not_localized() -> None:
    """`text.py`'s rule: a report is a committed artifact and two renderings of
    it must diff line by line. The month is a number and stays one."""
    assert diff_report.when(LEFT_AT) == "2026-09-04 09:12"
    assert diff_report.when(LEFT_AT, seconds=True) == "2026-09-04 09:12:33"
    assert diff_report.when("not a timestamp") == "not a timestamp"


def test_labels_escalate_to_seconds_before_giving_up() -> None:
    """Two candidates launched back to back land in the same minute, and that is
    the ordinary shape of this command rather than an edge of it."""
    same_minute = ("2026-09-04T09:12:33+00:00", "2026-09-04T09:12:51+00:00")
    assert diff_report.run_labels(*same_minute, left_key="k1", right_key="k2") == (
        "2026-09-04 09:12:33",
        "2026-09-04 09:12:51",
    )
    same_second = ("2026-09-04T09:12:33.1+00:00", "2026-09-04T09:12:33.9+00:00")
    assert diff_report.run_labels(*same_second, left_key="k1", right_key="k2") == (
        "k1",
        "k2",
    )


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #


SUITE = ("--suite", "suite_qa.py")


def dig(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """The CLI against the standard suite. `cli` takes the repository, not the
    result of another call — a helper this thin is worth having so the tests
    below read as commands rather than as argument lists."""
    return cli(repo, args[0], *SUITE, *args[1:])


def two_runs(repo: Path) -> tuple[str, str]:
    """Two runs of the standard suite, the second scoring lower on one check."""
    first = run_key(repo)
    write_suite(repo, fr_score="0.4")
    second = run_key(repo)
    return first, second


def test_diff_exits_zero_on_a_report_full_of_differences(repo: Path) -> None:
    """The test that would catch decision 1 being quietly undone, and the one to
    read first if this ADR ever looks like it stopped being true.

    `exit_code()` is never reached from `cmd_diff`: a verdict exists only
    against an approved reference, and neither of these runs was approved.
    """
    first, second = two_runs(repo)
    done = dig(repo, "diff", first, second)
    assert done.returncode == EXIT_OK, done.stderr
    assert "differ" in done.stdout


def test_diff_never_gates_even_where_compare_does(repo: Path) -> None:
    """The pair that makes the two exit-code contracts visible side by side: the
    same movement, judged against an approved reference and against a run
    nobody approved."""
    first, second = two_runs(repo)
    dig(repo, "promote", "--run", first)

    gated = dig(repo, "compare", "--run", second)
    assert gated.returncode != EXIT_OK

    ungated = dig(repo, "diff", first, second)
    assert ungated.returncode == EXIT_OK


def test_latest_resolves_on_either_positional(repo: Path) -> None:
    first, _second = two_runs(repo)
    done = dig(repo, "diff", first, "latest")
    assert done.returncode == EXIT_OK, done.stderr
    done = dig(repo, "diff", "latest", first)
    assert done.returncode == EXIT_OK, done.stderr


def test_a_run_diffed_with_itself_is_refused(repo: Path) -> None:
    first, _second = two_runs(repo)
    done = dig(repo, "diff", first, first)
    assert done.returncode == EXIT_USAGE
    assert "has nothing to report" in done.stderr


def test_a_refusal_is_a_usage_error_and_not_a_verdict(repo: Path) -> None:
    """`EXIT_USAGE`, never `EXIT_WORSE`: *the report could not be produced* is a
    different thing from *the report says something you dislike*, and only the
    first is a non-zero exit."""
    first, _second = two_runs(repo)
    # A moved threshold moves `config_hash`, and that is the refusal a developer
    # tuning a bar between two candidate runs will actually meet. Edited after
    # `two_runs`, which rewrites the suite from its template.
    suite = repo / "suite_qa.py"
    suite.write_text(
        suite.read_text(encoding="utf-8").replace("threshold=0.7", "threshold=0.9"),
        encoding="utf-8",
    )
    third = run_key(repo)

    done = dig(repo, "diff", first, third)
    assert done.returncode == EXIT_USAGE, done.stdout
    assert "compare the rulers, not the systems" in done.stderr
    # And never EXIT_WORSE. `exit_code()` is not reachable from `cmd_diff`, so
    # a 1 here would mean the two contracts had been merged after all.
    assert done.returncode != 1


def test_the_json_is_symmetric_and_has_no_verdict_field(repo: Path) -> None:
    """`Headline` is not reused and no diff-shaped equivalent exists, so there
    is nothing here for a pipeline to gate on. The absence is the point. (§1)"""
    first, second = two_runs(repo)
    there = json.loads(dig(repo, "diff", first, second, "--json", "full").stdout)
    back = json.loads(dig(repo, "diff", second, first, "--json", "full").stdout)

    assert "worse" not in json.dumps(there)
    assert "unjudged" not in json.dumps(there)
    assert there["output_version"] == 1

    assert there["counts"]["favours_left"] == back["counts"]["favours_right"]
    assert there["counts"]["favours_right"] == back["counts"]["favours_left"]
    assert there["counts"]["differing"] == back["counts"]["differing"]
    assert there["runs"]["left"] == back["runs"]["right"]
    assert there["runs"]["right"] == back["runs"]["left"]
    for here, over in zip(there["checks"], back["checks"], strict=True):
        assert here["left"] == over["right"] and here["right"] == over["left"]


def test_the_locale_defaults_to_english_like_every_terminal_output(
    repo: Path,
) -> None:
    """The terminal rule, not the document one. A future HTML diff document
    takes the mandatory flag like every other document. (§2)"""
    first, second = two_runs(repo)
    english = dig(repo, "diff", first, second).stdout
    assert "checks differ" in english or "check differs" in english

    italian = dig(repo, "diff", "--locale", "it", first, second).stdout
    assert "controll" in italian
    assert "differ" not in italian


# --------------------------------------------------------------------------- #
# The view's two modes (§6)
# --------------------------------------------------------------------------- #


def test_the_view_renders_the_verdict_against_the_baseline() -> None:
    """A run held against an approved reference *is* `compare()`'s question, and
    the existing document is the right answer to it."""
    left = run_of(verdict("contains", 1.0), created_at=LEFT_AT)
    right = run_of(verdict("contains", 0.0), created_at=RIGHT_AT)
    page = pages.compare_page(right, left, locale="en", suite="qa")
    assert "Did it get worse?" in page


def test_the_view_renders_the_diff_against_any_other_run() -> None:
    """The deviation ADR 0008 §6 closes. Before it, this pair arrived under a
    heading asking "Did it get worse?" beside a column called "Reference"."""
    left = run_of(verdict("contains", 1.0), created_at=LEFT_AT)
    right = run_of(verdict("contains", 0.0), created_at=RIGHT_AT)
    page = pages.diff_page(left, right, locale="en", suite="qa", keys=("k1", "k2"))
    assert "Did it get worse?" not in page
    assert "Reference" not in page
    assert "1 of 1 checks differs" in page
    assert LABELS[0] in page and LABELS[1] in page


def test_the_view_route_chooses_on_the_baseline_and_nothing_else(repo: Path) -> None:
    """End to end, because the choice is made in the route rather than in a
    page: a wiring mistake would render a correct page for the wrong pair."""
    first, second = two_runs(repo)
    dig(repo, "promote", "--run", first)
    served = _serve(repo)
    try:
        against_baseline = _get(served, f"/compare?run={second}&against={first}")
        assert "Did it get worse?" in against_baseline

        the_other_way = _get(served, f"/compare?run={first}&against={second}")
        assert "Did it get worse?" not in the_other_way
        assert "checks differ" in the_other_way or "check differs" in the_other_way

        default = _get(served, f"/compare?run={second}")
        assert "Did it get worse?" in default
    finally:
        served.terminate()
        served.wait(timeout=10)


def _serve(repo: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "digline.cli",
            "view",
            "--suite",
            "suite_qa.py",
            "--port",
            "0",
        ],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    line = process.stdout.readline()
    process.stdout.close()
    match = __import__("re").search(r"http://[\d.]+:(\d+)/", line)
    assert match is not None, line
    process.digline_port = int(match.group(1))  # type: ignore[attr-defined]
    return process


def _get(process: subprocess.Popen[str], path: str) -> str:
    import urllib.request

    port = process.digline_port  # type: ignore[attr-defined]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as reply:
        return reply.read().decode("utf-8")
