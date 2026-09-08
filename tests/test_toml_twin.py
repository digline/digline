"""The guardrail: a TOML suite and its Python twin are the same suite.

ADR 0007 §9. This is the property the whole format is built against, and it is
written before the loader rather than after it: *"if that ever stops being
true, the format has forked the engine, and the fork is the defect."*

What "the same" means, precisely, and why it is not one assertion:

- **The objects are equal** wherever the suite is data all the way down. Frozen
  dataclasses compare by field, so this is the strongest statement available
  and it covers cases, thresholds, tolerances, names and order.
- **The identities and the `config_hash` are equal always**, including with a
  judge in the suite. That is the operative half: `config_hash` is what decides
  whether a stored baseline is still the reference for this suite, so equality
  here is what lets a suite be ported from one form to the other without
  re-baselining.

The two are not the same statement, because a judge is an object and two judge
instances built from one coordinate are equal only in the sense `canonical()`
uses — their type. `AnthropicJudge` defines no `__eq__` and should not; what
travels into the fingerprint is the instrument's type and identity, which is
exactly what ADR 0005 §4 records.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests._providers import FakeJudge

from digline.cli.toml_suite import load_toml_suite
from digline.core import (
    Contains,
    CostBudget,
    Length,
    LlmRubric,
    Precision,
    Regex,
    Repeated,
)
from digline.core.run import config_hash
from digline.run import Case, Suite

TWIN = Path(__file__).resolve().parent / "fixtures" / "twin"

RUBRIC = "Does the reply answer the question in at most three sentences?"


def python_twin(judge: object) -> Suite:
    """`tests/fixtures/twin/suite.toml`, written the other way.

    The judge is passed in so that one call can build the suite with the very
    instrument the TOML form resolved to, and another can build it with a
    second instance of the same class.
    """
    return Suite(
        tenant="northwind",
        environment="staging",
        name="support",
        samples=3,
        min_agreement="2/3",
        assertions=[
            Contains(needle="Northwind Support"),
            Regex(pattern="^[A-Z]", name="starts_capitalised"),
            Length(maximum=400, unit="characters"),
            Repeated(
                inner=LlmRubric(
                    rubric=RUBRIC,
                    judge=judge,  # type: ignore[arg-type]
                    threshold=0.7,
                    tolerance=0.05,
                ),
                samples=3,
                min_agreement="2/3",
            ),
            CostBudget(max_usd=0.02, tolerance=0.05),
        ],
        run_assertions=[
            Precision(
                over="contains", threshold="9/10", tolerance="1/10", by_group=True
            ),
        ],
        cases=[
            Case(
                id="where-is-my-order",
                vars={
                    "question": (
                        "I ordered a kettle on Monday, order 4821. Where is it?"
                    )
                },
                label="positive",
                group="orders",
            ),
            Case(
                id="how-do-i-return",
                vars={"question": "The jacket does not fit. How do I send it back?"},
                expected="Any item, within 30 days, unused.",
                label="positive",
                group="returns",
            ),
            Case(
                id="refund-status",
                vars={"question": "Where is my refund?"},
                label="negative",
                suspended="the refund API is down, ticket 412",
            ),
        ],
    )


@pytest.fixture
def loaded(fake_provider: None) -> Suite:
    """The TOML half, loaded with the fake provider registered."""
    suite, _target = load_toml_suite(TWIN / "suite.toml")
    return suite


def fingerprint(suite: Suite) -> str:
    return config_hash(
        suite.assertions,
        samples=suite.samples,
        min_agreement=(
            None if suite.min_agreement is None else float(suite.min_agreement)
        ),
        run_assertions=suite.run_assertions,
    )


# --------------------------------------------------------------------------- #
# The whole suite, both ways
# --------------------------------------------------------------------------- #


def test_the_two_forms_produce_the_same_configuration_fingerprint(
    loaded: Suite,
) -> None:
    """The operative property: a baseline promoted from one form is the
    reference for the other."""
    assert fingerprint(loaded) == fingerprint(python_twin(FakeJudge("m")))


def test_every_assertion_has_the_identity_its_python_twin_has(
    loaded: Suite,
) -> None:
    """Per check rather than per suite, so a failure names which one moved —
    `config_hash` sorts and would only say that something did."""
    twin = python_twin(FakeJudge("m"))
    assert [a.name for a in loaded.assertions] == [a.name for a in twin.assertions]
    for mine, theirs in zip(loaded.assertions, twin.assertions, strict=True):
        assert mine.identity == theirs.identity, mine.name
        assert mine.threshold == theirs.threshold, mine.name
        assert mine.tolerance == theirs.tolerance, mine.name
    for mine, theirs in zip(loaded.run_assertions, twin.run_assertions, strict=True):
        assert mine.identity == theirs.identity, mine.name


def test_the_data_half_of_the_suite_is_equal_object_for_object(
    loaded: Suite,
) -> None:
    """Everything that is data all the way down compares by value, so this is
    an equality and not a fingerprint."""
    twin = python_twin(FakeJudge("m"))
    assert list(loaded.cases) == list(twin.cases)
    assert list(loaded.run_assertions) == list(twin.run_assertions)
    # Every assertion but the one holding the judge.
    assert list(loaded.assertions[:3]) == list(twin.assertions[:3])
    assert loaded.assertions[4] == twin.assertions[4]


def test_a_case_without_a_group_is_in_no_group(loaded: Suite) -> None:
    """`refund-status` declares none, so it is counted in the whole-run
    aggregate and in nothing else. There is no bucket named after the absence
    of a label (ADR 0010 §2)."""
    assert {c.id: c.group for c in loaded.cases} == {
        "where-is-my-order": "orders",
        "how-do-i-return": "returns",
        "refund-status": None,
    }
    assert loaded.groups() == ("orders", "returns")


def test_the_perimeter_and_the_sampling_carry_across(loaded: Suite) -> None:
    twin = python_twin(FakeJudge("m"))
    assert loaded.tenant == twin.tenant
    assert loaded.environment == twin.environment
    assert loaded.name == twin.name
    assert loaded.samples == twin.samples
    assert loaded.min_agreement == twin.min_agreement
    # A data suite cannot widen what leaves the perimeter (ADR 0007 §7).
    assert loaded.disclosure == twin.disclosure


def test_the_declared_order_is_the_order_that_survives(loaded: Suite) -> None:
    """Report order is the author's, and the loader does not sort it."""
    assert [a.name for a in loaded.assertions] == [
        "contains",
        "starts_capitalised",
        "length",
        "llm_rubric",
        "cost_budget",
    ]


def test_the_aggregate_is_routed_to_run_assertions(loaded: Suite) -> None:
    """Written in the same `[[assertions]]` list, it lands where `Suite` keeps
    it — the split is the loader's job, not the author's (ADR 0007 §2).

    And it arrives expanded, because the fixture sets `by_group = true`: one
    whole-run instance, then the groups the cases declare, in sorted order.
    The names are asserted literally because they are a public format — they
    land in every run file this suite produces (ADR 0010 §3).
    """
    assert [a.name for a in loaded.run_assertions] == [
        "precision",
        "precision[group=orders]",
        "precision[group=returns]",
    ]
    assert "precision" not in [a.name for a in loaded.assertions]


def test_a_grouped_aggregate_expands_the_same_in_both_forms(loaded: Suite) -> None:
    """The operative property of ADR 0010 §2 seen through ADR 0007 §9.

    `by_group` is a key in a data file and an argument in Python, and the
    expansion it triggers happens in `Suite.__post_init__` — below both. So a
    suite ported between the forms keeps not just its checks but the gates the
    expansion invented for it, identity for identity, and its baseline stays
    the reference. Object equality rather than a fingerprint: an expanded
    aggregate is a frozen dataclass and carries `group` and `name` as fields,
    so equality is the strongest statement available and covers the naming too.
    """
    twin = python_twin(FakeJudge("m"))
    assert list(loaded.run_assertions) == list(twin.run_assertions)
    # Narrowed to the concrete class rather than read off `RunAssertion`: the
    # Protocol deliberately declares neither `group` nor `by_group`, so that a
    # third-party aggregate satisfying it structurally goes on doing so
    # (ADR 0010 §6). A type checker holding this test to that is the rule
    # working, not the rule getting in the way.
    scoped = [a for a in loaded.run_assertions if isinstance(a, Precision)]
    assert len(scoped) == len(loaded.run_assertions)
    assert [a.group for a in scoped] == [None, "orders", "returns"]
    # And the whole-run instance is untouched by the flag: same identity as the
    # one a suite without groups declares, which is what lets the expansion add
    # rather than replace (ADR 0010 §4).
    assert (
        loaded.run_assertions[0].identity
        == Precision(over="contains", threshold="9/10", tolerance="1/10").identity
    )


def test_the_judge_is_the_instrument_the_coordinate_named(loaded: Suite) -> None:
    """`judge = "fake/m"` resolves through the entry point to the plugin's own
    class, constructed with the model half of the coordinate."""
    repeated = loaded.assertions[3]
    assert isinstance(repeated, Repeated)
    rubric = repeated.inner
    assert isinstance(rubric, LlmRubric)
    assert isinstance(rubric.judge, FakeJudge)
    assert rubric.judge.model == "m"
