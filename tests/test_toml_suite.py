"""The declarative format, against ADR 0007's test plan.

The plan is written in the record and this file answers it, minus the two parts
that live where they belong: the twin property is `test_toml_twin.py` (written
first, as the guardrail the loader was built against), and the refusals are
`test_toml_errors.py` (a catalogue, tested as one).

What is left is here, and it is mostly one question asked many ways: **does a
suite that is data behave exactly like the suite that is code?** Not "does it
parse" — the parser is `tomllib` and it is not ours — but does it produce the
same objects, refuse the same things, and reach the same failures at the same
moment.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from tests._providers import BUCKET, FakeJudge, FakeTarget

from digline import core
from digline.cli.errors import UsageError
from digline.cli.toml_suite import (
    AGGREGATES,
    ASSERTIONS,
    PYTHON_ONLY,
    load_toml_suite,
)
from digline.core import Faithfulness, LlmRubric
from digline.run import Suite
from digline.targets import HttpTarget

SUITE = """
[suite]
tenant = "northwind"
environment = "staging"
name = "support"
cases = "cases.json"
"""

TARGET = """
[target]
type = "http"
url = "http://localhost:8080/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"
"""

CONTAINS = """
[[assertions]]
type = "contains"
needle = "Northwind Support"
"""

ONE_CASE = json.dumps([{"id": "a", "vars": {"question": "?"}}])

Build = Callable[..., Suite]


@pytest.fixture
def build(tmp_path: Path, fake_provider: None) -> Build:
    """Write a suite and load it. Raises `UsageError` like the CLI would."""

    def load(body: str = SUITE + TARGET + CONTAINS, *, cases: str = ONE_CASE) -> Suite:
        (tmp_path / "suite.toml").write_text(body, encoding="utf-8")
        (tmp_path / "cases.json").write_text(cases, encoding="utf-8")
        return load_toml_suite(tmp_path / "suite.toml")[0]

    return load


@pytest.fixture
def target(tmp_path: Path, fake_provider: None) -> Callable[[str], object]:
    def load(body: str) -> object:
        (tmp_path / "suite.toml").write_text(SUITE + body + CONTAINS, encoding="utf-8")
        (tmp_path / "cases.json").write_text(ONE_CASE, encoding="utf-8")
        return load_toml_suite(tmp_path / "suite.toml")[1]

    return load


# --------------------------------------------------------------------------- #
# The token table cannot fall behind the package
# --------------------------------------------------------------------------- #


def exported(base: type) -> set[str]:
    """Every concrete subclass of `base` that `digline.core` exports."""
    return {
        name
        for name in core.__all__
        if isinstance(found := getattr(core, name), type)
        and issubclass(found, base)
        and found is not base
    }


def test_every_token_names_a_class_the_package_exports() -> None:
    """A token is a public name in a public format, so it cannot point at
    something a reader has no other way of meeting."""
    for token, cls in {**ASSERTIONS, **AGGREGATES}.items():
        assert cls.__name__ in core.__all__, token
        assert getattr(core, cls.__name__) is cls, token


def test_no_assertion_can_ship_without_a_token() -> None:
    """The failure this prevents is the format silently falling behind the
    engine: an assertion added to the core, released, documented in
    `metrics.md`, and unwritable in TOML with nothing anywhere saying so.

    A new check is either buildable from data — then it needs a token — or it
    is not, and then it belongs in `PYTHON_ONLY`, where it gets a sentence
    instead. Both are a line in `toml_suite.py`; neither is optional.
    """
    from digline.core.aggregate import RunAssertionBase
    from digline.core.assertions import AssertionBase

    covered = {cls.__name__ for cls in ASSERTIONS.values()}
    covered |= {cls.__name__ for cls in AGGREGATES.values()}
    covered |= {"".join(p.title() for p in token.split("_")) for token in PYTHON_ONLY}

    shipped = exported(AssertionBase) | exported(RunAssertionBase)
    missing = sorted(shipped - covered)
    assert not missing, (
        f"{missing} is exported by digline.core and has no token in "
        "toml_suite.ASSERTIONS/AGGREGATES and no sentence in PYTHON_ONLY. "
        "A data suite cannot ask for it and nothing says why."
    )


def test_the_two_token_families_do_not_overlap() -> None:
    assert not set(ASSERTIONS) & set(AGGREGATES)


# --------------------------------------------------------------------------- #
# Every Suite refusal, in TOML
# --------------------------------------------------------------------------- #


def test_a_suite_with_no_assertions_is_refused(build: Build) -> None:
    with pytest.raises(UsageError, match="vacuously"):
        build(SUITE + TARGET)


def test_a_suite_with_no_cases_is_refused(build: Build) -> None:
    with pytest.raises(UsageError, match="no cases"):
        build(cases="[]")


def test_a_duplicate_case_id_is_refused(build: Build) -> None:
    """Ids are how a result finds its counterpart in the baseline."""
    with pytest.raises(UsageError, match="twice"):
        build(cases=json.dumps([{"id": "a"}, {"id": "a"}]))


def test_sampling_without_a_floor_is_refused(build: Build) -> None:
    with pytest.raises(UsageError, match="min_agreement"):
        build(SUITE + "samples = 3\n" + TARGET + CONTAINS)


def test_a_ratio_no_sample_count_can_produce_is_refused(build: Build) -> None:
    """`"2/5"` over three samples is a bar that cannot be met or missed."""
    with pytest.raises(UsageError, match="2/5|min_agreement"):
        build(SUITE + 'samples = 3\nmin_agreement = "2/5"\n' + TARGET + CONTAINS)


def test_an_aggregate_over_nothing_is_refused(build: Build) -> None:
    with pytest.raises(UsageError, match="which no assertion"):
        build(
            SUITE
            + TARGET
            + CONTAINS
            + '\n[[assertions]]\ntype = "precision"\nover = "rubric"\n'
            'threshold = "9/10"\ntolerance = "1/10"\n'
        )


def test_an_aggregate_over_two_checks_of_one_name_is_refused(build: Build) -> None:
    """Two `contains` in one suite is the ordinary case, and in TOML it is four
    lines — so this refusal is the one the format makes easiest to trip
    (ADR 0007 §2). The fix is the one that was always right: name one."""
    with pytest.raises(UsageError, match="2 assertions"):
        build(
            SUITE
            + TARGET
            + CONTAINS
            + CONTAINS
            + '\n[[assertions]]\ntype = "precision"\nover = "contains"\n'
            'threshold = "9/10"\ntolerance = "1/10"\n'
        )


def test_an_empty_needle_is_refused_as_it_is_in_python(build: Build) -> None:
    """`Contains("")` is a ValueError when the suite loads rather than a green
    run — and the loader adds nothing to make that true."""
    with pytest.raises(UsageError):
        build(SUITE + TARGET + '\n[[assertions]]\ntype = "contains"\nneedle = ""\n')


# --------------------------------------------------------------------------- #
# The target, both forms
# --------------------------------------------------------------------------- #


def test_an_http_target_is_built_with_its_declared_paths(
    target: Callable[[str], object],
) -> None:
    built = target(TARGET)
    assert isinstance(built, HttpTarget)
    assert built.url == "http://localhost:8080/answer"
    assert built.output_path == "data"
    assert built.body == {"question": "case.vars.question"}


def test_a_provider_target_is_the_plugin_class_with_its_settings(
    target: Callable[[str], object],
) -> None:
    built = target(
        '\n[target]\ntype = "provider"\nprovider = "fake/m"\ntemperature = 0.2\n'
    )
    assert isinstance(built, FakeTarget)
    assert built.model == "m"
    assert built.temperature == 0.2


def test_a_bucket_of_keywords_does_not_make_a_plugin_permissive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0007 §5 admits the parameters a plugin *exposes*, and a `**kwargs`
    bucket exposes none. Without this, whether `temperture` is caught would
    depend on how the plugin happens to be written."""
    from importlib.metadata import EntryPoint

    from digline.targets.registry import GROUP

    monkeypatch.setattr(
        "digline.targets.registry._entry_points",
        lambda: {
            "bucket": EntryPoint(
                name="bucket", value="tests._providers:BUCKET", group=GROUP
            )
        },
    )
    assert BUCKET.target.__name__ == "BucketTarget"
    (tmp_path / "cases.json").write_text(ONE_CASE, encoding="utf-8")
    (tmp_path / "suite.toml").write_text(
        SUITE
        + '\n[target]\ntype = "provider"\nprovider = "bucket/m"\ntemperture = 0.2\n'
        + CONTAINS,
        encoding="utf-8",
    )
    with pytest.raises(UsageError, match="temperture"):
        load_toml_suite(tmp_path / "suite.toml")


# --------------------------------------------------------------------------- #
# The judge, from its coordinates
# --------------------------------------------------------------------------- #


def test_a_rubric_gets_the_score_judge_and_faithfulness_the_claim_judge(
    build: Build,
) -> None:
    """One coordinate answers for both, because ADR 0004 §1 makes every plugin
    ship both — and which one an assertion gets is decided by what it declares,
    not by a table of assertion names."""
    suite = build(
        SUITE + TARGET + '\n[[assertions]]\ntype = "llm_rubric"\nrubric = "r"\n'
        'judge = "fake/m"\nthreshold = 0.7\ntolerance = 0.05\n'
        '\n[[assertions]]\ntype = "faithfulness"\njudge = "fake/m"\n'
        "threshold = 0.8\ntolerance = 0.05\n"
    )
    rubric, faithful = suite.assertions
    assert isinstance(rubric, LlmRubric)
    assert isinstance(faithful, Faithfulness)
    assert isinstance(rubric.judge, FakeJudge)
    assert type(faithful.judge).__name__ == "FakeClaimJudge"


def test_the_model_half_of_a_coordinate_is_opaque(build: Build) -> None:
    """Only the first slash separates: a Bedrock inference profile is a model
    identifier with slashes of its own."""
    suite = build(
        SUITE + TARGET + '\n[[assertions]]\ntype = "llm_rubric"\nrubric = "r"\n'
        'judge = "fake/arn:aws:bedrock:eu-west-1:1:inference-profile/eu.x"\n'
        "threshold = 0.7\ntolerance = 0.05\n"
    )
    rubric = suite.assertions[0]
    assert isinstance(rubric, LlmRubric)
    assert isinstance(rubric.judge, FakeJudge)
    assert rubric.judge.model == ("arn:aws:bedrock:eu-west-1:1:inference-profile/eu.x")


# --------------------------------------------------------------------------- #
# Cases, always a file
# --------------------------------------------------------------------------- #


def test_a_case_carries_every_field_the_dataclass_has(build: Build) -> None:
    suite = build(
        cases=json.dumps(
            [
                {
                    "id": "a",
                    "vars": {"question": "?"},
                    "expected": "yes",
                    "context": ["one", "two"],
                    "metadata": {"quarter": "2026-Q3"},
                    "label": "positive",
                },
                {"id": "b", "suspended": "the API is down, ticket 412"},
            ]
        )
    )
    first, second = suite.cases
    assert first.vars == {"question": "?"}
    assert first.expected == "yes"
    assert list(first.context) == ["one", "two"]
    assert first.metadata == {"quarter": "2026-Q3"}
    assert first.label == "positive"
    assert second.suspended == "the API is down, ticket 412"


def test_a_cases_file_that_is_not_there_says_where_it_looked(build: Build) -> None:
    with pytest.raises(UsageError, match="could not be read"):
        build(SUITE.replace("cases.json", "elsewhere.json") + TARGET + CONTAINS)


def test_a_cases_file_that_is_not_an_array_is_refused(build: Build) -> None:
    with pytest.raises(UsageError, match="array of case objects"):
        build(cases=json.dumps({"id": "a"}))


# --------------------------------------------------------------------------- #
# What the format does not touch
# --------------------------------------------------------------------------- #


def test_a_data_suite_discloses_nothing_extra(build: Build) -> None:
    """Not settable, and the default is the closed one (ADR 0007 §7)."""
    assert build().disclosure == core.NOTHING_EXTRA


def test_artifacts_are_declared_relative_to_the_suite(build: Build) -> None:
    """The CLI resolves them against the suite's own directory, exactly as it
    does for a suite.py — so what is stored is what was written."""
    suite = build(SUITE + 'artifacts = ["prompt.md"]\n' + TARGET + CONTAINS)
    assert [str(p) for p in suite.artifacts] == ["prompt.md"]


# --------------------------------------------------------------------------- #
# A real plugin, resolved by coordinate
# --------------------------------------------------------------------------- #


def test_a_real_coordinate_resolves_and_an_unpriced_model_fails_preflight(
    tmp_path: Path,
) -> None:
    """The last line of ADR 0007's test plan, and the one that needs no fake:
    the coordinate resolves through the entry point a released plugin declares,
    the target is built, and the model that has no price is refused **before
    the first case** — where an unpriced model already fails for a suite.py.

    No key and no network: preflight prices the model against the plugin's own
    table, which is why it can be the thing that fails here.
    """
    pytest.importorskip("digline_anthropic")

    (tmp_path / "prompt.md").write_text("Answer: {{question}}", encoding="utf-8")
    (tmp_path / "cases.json").write_text(ONE_CASE, encoding="utf-8")
    (tmp_path / "suite.toml").write_text(
        SUITE + '\n[target]\ntype = "provider"\n'
        'provider = "anthropic/claude-not-a-real-model"\n'
        'prompt_file = "prompt.md"\nmax_tokens = 200\n' + CONTAINS,
        encoding="utf-8",
    )

    suite, built = load_toml_suite(tmp_path / "suite.toml")
    assert type(built).__name__ == "AnthropicTarget"

    with pytest.raises(ValueError, match="has no price"):
        cast("Any", built).preflight(suite.cases)
