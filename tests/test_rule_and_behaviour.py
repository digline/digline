"""A moved bar says the rule changed, and does not say the behaviour did not.

When a check flips and its threshold moved, the detail sentence named the bar
and concluded *"so this is a change of rule rather than of behaviour"*. Measured
for #642 on a check outside `Repeated`: the bar raised from 0.7 to 0.8 while the
judge fell from 0.75 to 0.5, and the sentence said the behaviour had not
changed. It had.

So the sentence is two sentences now. Where the score held, by the rule
`compare()` reads a movement with, within the check's tolerance, the bar alone
explains the flip and the old words stand. Where the score moved beyond it,
both changed, and the sentence names both. It is the pair of the `unpaired`
clause beside the headline: that one keeps *Nothing got worse* from being read
as *every check was compared*, and this one keeps *the rule changed* from being
read as *the behaviour did not*.
"""

from __future__ import annotations

import pytest

from digline.core import JudgeReply, LlmRubric, compare
from digline.report import summary_lines
from digline.report.text import LOCALES, Locale, phrase
from digline.run import Case, Response, Suite, execute

REFERENCE_AT = "2026-10-26T10:00:00+00:00"
RUN_AT = "2026-10-26T11:00:00+00:00"


def target(case: Case) -> Response:
    return Response(output="Rome")


def suite(threshold: float, score: float) -> Suite:
    def judge(prompt: str) -> JudgeReply:
        return JudgeReply(score=score, reason="judged")

    return Suite(
        tenant="acme",
        environment="dev",
        name="qa",
        assertions=[
            LlmRubric(
                rubric="Is it right?", judge=judge, threshold=threshold, tolerance=0.05
            )
        ],
        cases=[Case(id="one")],
    )


def detail(before: Suite, after: Suite, locale: Locale) -> str:
    reference = execute(before, target, created_at=REFERENCE_AT)
    run = execute(after, target, created_at=RUN_AT)
    comparison = compare(run, reference)
    assert comparison.counts["regressed"] == 1
    (line,) = summary_lines(comparison, run, reference, locale=locale)
    return line


def bar(locale: Locale, key: str) -> str:
    return phrase(locale, key, before_threshold="0.700000", now_threshold="0.800000")


@pytest.mark.parametrize("locale", LOCALES)
def test_a_bar_that_moved_alone_is_a_change_of_rule(locale: Locale) -> None:
    """The score held at 0.75 and the bar rose to 0.8: the flip is the rule's
    doing alone, and today's sentence says exactly that."""
    line = detail(suite(0.7, 0.75), suite(0.8, 0.75), locale)

    assert bar(locale, "detail.threshold_moved") in line
    assert bar(locale, "detail.threshold_moved.score_moved") not in line


@pytest.mark.parametrize("locale", LOCALES)
def test_a_bar_that_moved_beside_a_fall_names_both(locale: Locale) -> None:
    """The bar rose to 0.8 and the score fell to 0.5, far beyond the tolerance:
    the rule and the behaviour both changed, and the sentence must not say that
    one excludes the other."""
    line = detail(suite(0.7, 0.75), suite(0.8, 0.5), locale)

    assert bar(locale, "detail.threshold_moved.score_moved") in line
    assert bar(locale, "detail.threshold_moved") not in line
