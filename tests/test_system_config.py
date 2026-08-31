"""The configuration of the system under test, recorded beside the verdicts.

ADR 0005. The measurement it closes is the one in `test_a_changed_temperature_is
_named_not_hashed`: before this, two runs at two temperatures were the same
document, `compare()` said "the configuration is the same as the reference", and
that sentence was true about the rules and false about everything a reader
understood by it.

The rest guards the two edges. A parameter is a measurement of the system and
travels; `base_url` is the client's topology and gets the artifact treatment
instead (ADR 0003 §4). And a baseline promoted before any of this existed must
keep comparing — `unknown`, never a wall of fabricated changes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from tests._helpers import cli, git

from digline.core import (
    ConfigValue,
    Contains,
    Disclosure,
    JudgeReply,
    LlmRubric,
    Repeated,
    Run,
    Score,
    SystemConfig,
    Verdict,
    compare,
    redact,
)
from digline.core.run import SCHEMA_VERSION, run_from_json, run_to_json
from digline.report import config_lines, headline, render_html
from digline.run import Case, Response, Suite, execute, judge_config, target_config
from digline.store import FileResultStore, RunRef
from digline.store.migrate import upgrade_document

ANTHROPIC: dict[str, ConfigValue] = {
    "provider": "anthropic",
    "model": "claude-sonnet-5",
    "max_tokens": 1024,
}


# --------------------------------------------------------------------------- #
# What a target and a judge declare
# --------------------------------------------------------------------------- #


class ConfiguredTarget:
    """A target that can say how it was set up, like every `ProviderTarget`."""

    def __init__(self, **config: ConfigValue) -> None:
        self._config: dict[str, ConfigValue] = {**ANTHROPIC, **config}

    @property
    def config(self) -> Mapping[str, ConfigValue]:
        return dict(self._config)

    def __call__(self, case: Case) -> Response:
        return Response(output="The capital is Rome.", cost_usd=0.01)


class ConfiguredJudge:
    def __init__(self, model: str = "claude-haiku-4-5", **extra: ConfigValue) -> None:
        self._config: dict[str, ConfigValue] = {
            "provider": "anthropic",
            "model": model,
            **extra,
        }

    @property
    def config(self) -> Mapping[str, ConfigValue]:
        return dict(self._config)

    def __call__(self, prompt: str) -> JudgeReply:
        return JudgeReply(score=1.0, reason="fine")


def a_suite(*, assertions: object = None) -> Suite:
    return Suite(
        tenant="acme-bank",
        environment="staging",
        name="qa",
        assertions=assertions or [Contains(needle="Rome")],  # type: ignore[arg-type]
        cases=[Case(id="capital-it")],
    )


def test_the_run_records_what_the_target_declared() -> None:
    run = execute(
        a_suite(),
        ConfiguredTarget(temperature=0.7),
        created_at="2026-08-31T00:00:00Z",
    )
    assert run.target_config.values == {**ANTHROPIC, "temperature": 0.7}


def test_a_plain_function_target_declares_nothing() -> None:
    """Most targets are functions and have no model at all. Absent has to stay
    absent — and, in `compare()` below, must not read as a change."""
    run = execute(
        a_suite(),
        lambda case: Response(output="Rome"),
        created_at="2026-08-31T00:00:00Z",
    )
    assert not run.target_config.recorded
    assert not run.judge_config.recorded


def test_the_judge_is_collected_from_the_assertion_that_holds_it() -> None:
    """A target is bound once per run; a judge is bound per assertion, so it is
    found rather than received (ADR 0005 §6)."""
    suite = a_suite(
        assertions=[
            Contains(needle="Rome"),
            LlmRubric(
                rubric="answers?",
                judge=ConfiguredJudge(),
                threshold=0.7,
                tolerance=0.05,
            ),
        ]
    )
    assert judge_config(suite).values == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
    }


def test_a_judge_inside_a_wrapper_is_still_found() -> None:
    """`Repeated` is where a judge hides: an assertion holding an assertion
    holding the judge. A collector that stopped at the first level would record
    nothing for the suites that grade most carefully."""
    suite = a_suite(
        assertions=[
            Repeated(
                inner=LlmRubric(
                    rubric="answers?",
                    judge=ConfiguredJudge(),
                    threshold=0.7,
                    tolerance=0.05,
                ),
                samples=3,
                min_agreement="2/3",
            )
        ]
    )
    assert judge_config(suite).values["model"] == "claude-haiku-4-5"


def test_two_judges_on_one_model_record_that_model() -> None:
    """The ordinary case even with two judges: ADR 0004 §1 makes `ScoreJudge`
    and `ClaimCountJudge` two objects normally built the same way."""
    suite = a_suite(
        assertions=[
            LlmRubric(
                rubric="a", judge=ConfiguredJudge(), threshold=0.7, tolerance=0.05
            ),
            LlmRubric(
                rubric="b", judge=ConfiguredJudge(), threshold=0.7, tolerance=0.05
            ),
        ]
    )
    assert judge_config(suite).values["model"] == "claude-haiku-4-5"


def two_judge_suite(first: str = "haiku", second: str = "opus") -> Suite:
    return a_suite(
        assertions=[
            LlmRubric(
                rubric="a",
                judge=ConfiguredJudge(first),
                threshold=0.7,
                tolerance=0.05,
            ),
            LlmRubric(
                rubric="b",
                judge=ConfiguredJudge(second),
                threshold=0.7,
                tolerance=0.05,
            ),
        ]
    )


def test_two_judges_of_different_identity_are_both_recorded() -> None:
    """The blind spot ADR 0005 §4 exists to close.

    Two models grading is two instruments, and there is no single set-up to
    record — but *which* instruments graded must still be, or replacing one of
    the two goes unseen, which is the very change this half of the ADR is for.
    """
    config = judge_config(two_judge_suite())
    assert config.identities == ("anthropic/haiku", "anthropic/opus")
    # No merged scalars: with two instruments in play there is no one
    # `max_tokens`, and inventing one would describe a judge nobody built.
    assert config.values == {}
    assert config.recorded


def test_two_judges_sharing_an_identity_keep_what_they_agree_on() -> None:
    """A `ScoreJudge` and a `ClaimCountJudge` on one model is the ordinary
    two-judge suite (ADR 0004 §1), so it keeps its set-up — minus any scalar
    the two disagree on."""
    suite = a_suite(
        assertions=[
            LlmRubric(
                rubric="a",
                judge=ConfiguredJudge(max_tokens=400),
                threshold=0.7,
                tolerance=0.05,
            ),
            LlmRubric(
                rubric="b",
                judge=ConfiguredJudge(max_tokens=800),
                threshold=0.7,
                tolerance=0.05,
            ),
        ]
    )
    config = judge_config(suite)
    assert config.identities == ("anthropic/claude-haiku-4-5",)
    assert config.values == {"provider": "anthropic", "model": "claude-haiku-4-5"}


def test_a_judge_that_names_no_instrument_records_none() -> None:
    """A hand-written fake judge answers `config` with nothing, exactly as a
    plain-function target does."""

    class Anonymous:
        @property
        def config(self) -> Mapping[str, ConfigValue]:
            return {}

        def __call__(self, prompt: str) -> JudgeReply:
            return JudgeReply(score=1.0, reason="fine")

    suite = a_suite(
        assertions=[
            LlmRubric(rubric="a", judge=Anonymous(), threshold=0.7, tolerance=0.05)
        ]
    )
    assert not judge_config(suite).recorded


def test_a_configuration_must_say_who_answered() -> None:
    with pytest.raises(ValueError, match="cannot say who answered"):
        SystemConfig(values={"temperature": 0.7})


def test_a_nested_value_is_refused_where_it_is_written() -> None:
    """A configuration is diffed field by field and rendered by value, so a
    mapping in it would reach the report as a delta nobody can read."""
    with pytest.raises(ValueError, match="not a scalar"):
        SystemConfig(values={**ANTHROPIC, "thinking": {"budget": 2000}})  # type: ignore[dict-item]


def test_the_target_config_helper_ignores_a_target_that_cannot_answer() -> None:
    assert not target_config(object()).recorded


# --------------------------------------------------------------------------- #
# Through the run file and into the baseline
# --------------------------------------------------------------------------- #


def a_run(
    *,
    target: Mapping[str, ConfigValue] | None = None,
    judge: Mapping[str, ConfigValue] | None = None,
    judges: tuple[str, ...] = (),
) -> Run:
    return Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg",
        created_at="2026-08-31T00:00:00Z",
        results=(),
        target_config=SystemConfig(values=target or {}),
        judge_config=SystemConfig(values=judge or {}, identities=judges),
    )


def test_the_configuration_survives_the_round_trip() -> None:
    run = a_run(
        target={**ANTHROPIC, "temperature": 0.7},
        judge={"provider": "anthropic", "model": "claude-haiku-4-5"},
    )
    document = json.loads(run_to_json(run))
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["target_config"]["values"]["temperature"] == 0.7
    assert run_from_json(run_to_json(run)) == run


def test_a_configuration_nobody_declared_is_absent_rather_than_emptied() -> None:
    document = json.loads(run_to_json(a_run()))
    assert document["target_config"] == {}
    assert document["judge_config"] == {}


def test_the_baseline_carries_the_configuration_that_produced_it(
    tmp_path: Path,
) -> None:
    """Promotion is a copy of the run file, so this is what makes a baseline
    self-contained evidence rather than a column of numbers (ADR 0005 §3)."""
    store = FileResultStore(tmp_path)
    ref = store.write_run(a_run(target={**ANTHROPIC, "temperature": 0.3}))
    promoted = store.promote_baseline(ref, "cfg")
    assert promoted.target_config.values["temperature"] == 0.3

    reread = store.read_baseline("acme-bank", "qa")
    assert reread is not None
    assert reread.target_config.values["temperature"] == 0.3


def test_a_document_with_a_nested_value_is_refused_on_the_way_in() -> None:
    document = json.loads(run_to_json(a_run(target=dict(ANTHROPIC))))
    document["target_config"]["values"]["thinking"] = {"budget": 2000}
    with pytest.raises(ValueError, match="target_config"):
        run_from_json(json.dumps(document))


# --------------------------------------------------------------------------- #
# The named delta
# --------------------------------------------------------------------------- #


def test_a_changed_temperature_is_named_not_hashed() -> None:
    """The measurement ADR 0005 was opened on.

    Two runs of one suite at two temperatures: the rules did not move, so
    `config_hash` is right to be equal and the runs are right to stay
    comparable. What was missing is the *other* fact, by name and by value.
    """
    now = a_run(target={**ANTHROPIC, "temperature": 0.7})
    before = a_run(target={**ANTHROPIC, "temperature": 0.3})
    comparison = compare(now, before)

    assert not comparison.config_changed  # the rules are the same
    assert comparison.target_config_changed  # the system is not
    (delta,) = comparison.config_changes
    assert (delta.field, delta.before, delta.after) == ("temperature", 0.3, 0.7)


def test_a_parameter_that_appears_is_new_and_one_that_stops_is_missing() -> None:
    now = a_run(target={**ANTHROPIC, "temperature": 0.7})
    before = a_run(target={**ANTHROPIC, "region": "eu-west-1"})
    outcomes = {d.field: d.outcome for d in compare(now, before).target_config_deltas}
    assert outcomes == {
        "provider": "same",
        "model": "same",
        "max_tokens": "same",
        "temperature": "new",
        "region": "missing",
    }


def test_an_unchanged_configuration_is_not_a_change() -> None:
    run = a_run(target=dict(ANTHROPIC))
    comparison = compare(run, a_run(target=dict(ANTHROPIC)))
    assert not comparison.target_config_changed
    assert [d.outcome for d in comparison.target_config_deltas] == ["same"] * 3


def test_two_targets_that_declared_nothing_produce_no_deltas() -> None:
    """Absent stays absent. A suite of plain-function targets must not grow a
    section about a configuration nobody has."""
    comparison = compare(a_run(), a_run())
    assert comparison.target_config_deltas == ()
    assert not comparison.target_config_changed


def test_replacing_one_of_two_judges_is_seen() -> None:
    """The case the first shape missed. A suite grading with two instruments
    swaps one of them; nothing else moves. That has to arrive as a change —
    and as the strong one, because a delta measured on two different scales is
    not a delta."""
    now = a_run(judges=("anthropic/haiku", "openai/gpt-5-mini"))
    before = a_run(judges=("anthropic/haiku", "anthropic/opus"))
    comparison = compare(now, before)

    assert comparison.judge_config_changed
    assert comparison.comparability_reduced
    outcomes = {
        (d.before or d.after): d.outcome for d in comparison.judge_config_deltas
    }
    assert outcomes == {
        "anthropic/haiku": "same",
        "anthropic/opus": "missing",
        "openai/gpt-5-mini": "new",
    }


def test_the_same_two_judges_are_not_a_change() -> None:
    now = a_run(judges=("anthropic/haiku", "anthropic/opus"))
    comparison = compare(now, a_run(judges=("anthropic/opus", "anthropic/haiku")))
    assert not comparison.judge_config_changed
    assert not comparison.comparability_reduced


def test_a_second_judge_joining_does_not_fabricate_scalar_changes() -> None:
    """One judge becomes two: the set-up stops being recordable, and that is
    not the same as a `max_tokens` that was removed. The identity rows carry
    the change; no scalar row claims one."""
    now = a_run(judges=("anthropic/haiku", "anthropic/opus"))
    before = a_run(
        judge={"provider": "anthropic", "model": "haiku", "max_tokens": 400},
        judges=("anthropic/haiku",),
    )
    deltas = compare(now, before).judge_config_deltas
    assert {d.field for d in deltas} == {"judge"}
    assert "max_tokens" not in {d.field for d in deltas}


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "openai/gpt-5-mini was added as a judge"),
        ("it", "openai/gpt-5-mini è stato aggiunto come giudice"),
    ],
)
def test_the_report_names_the_instrument_that_joined(
    locale: str, expected: str
) -> None:
    """An instrument is not a value, so it does not read as one: `model a → b`
    would be a lie about a suite that now grades with three."""
    now = a_run(judges=("anthropic/haiku", "openai/gpt-5-mini"))
    before = a_run(judges=("anthropic/haiku", "anthropic/opus"))
    document = render_html(compare(now, before), now, before, locale=locale)  # type: ignore[arg-type]
    assert expected in document
    assert "anthropic/opus" in document


def test_two_judges_survive_the_round_trip() -> None:
    run = a_run(judges=("openai/gpt-5-mini", "anthropic/haiku"))
    document = json.loads(run_to_json(run))
    # Sorted, so two runs listing the same judges in two orders are one
    # document.
    assert document["judge_config"]["identities"] == [
        "anthropic/haiku",
        "openai/gpt-5-mini",
    ]
    assert "values" not in document["judge_config"]
    assert run_from_json(run_to_json(run)) == run


def test_an_object_may_not_answer_what_graded_this_twice() -> None:
    with pytest.raises(ValueError, match="twice"):
        SystemConfig(
            values={"provider": "anthropic", "model": "haiku"},
            identities=("anthropic/opus",),
        )


def test_a_judge_change_is_reported_and_flagged_as_less_comparable() -> None:
    """A target change moves the thing measured; a judge change moves the
    scale. The second is the stronger statement and is made as one."""
    now = a_run(judge={"provider": "anthropic", "model": "claude-haiku-4-5"})
    before = a_run(judge={"provider": "anthropic", "model": "claude-opus-4"})
    comparison = compare(now, before)
    assert comparison.judge_config_changed
    assert comparison.comparability_reduced
    (delta,) = comparison.config_changes or comparison.judge_config_deltas[:1]
    assert delta.field == "model"


def test_compare_reports_a_configuration_change_and_never_refuses_it() -> None:
    """The whole reason this is not in `config_hash`: the comparison old model
    against new, with the score deltas beside it, is the experiment."""
    now = a_run(target={**ANTHROPIC, "model": "claude-haiku-4-5"})
    before = a_run(target=dict(ANTHROPIC))
    assert compare(now, before).target_config_changed  # no raise


# --------------------------------------------------------------------------- #
# The baseline promoted before any of this existed
# --------------------------------------------------------------------------- #


def test_a_baseline_without_a_configuration_yields_unknown() -> None:
    """The compatibility test, and the one that decides whether a year of
    promoted baselines has to be promoted again. It does not."""
    now = a_run(target={**ANTHROPIC, "temperature": 0.7})
    comparison = compare(now, a_run())

    assert {d.outcome for d in comparison.target_config_deltas} == {"unknown"}
    assert not comparison.target_config_changed
    assert comparison.config_changes == ()


def test_a_schema_seven_document_migrates_to_an_empty_configuration() -> None:
    document = json.loads(run_to_json(a_run(target=dict(ANTHROPIC))))
    document["schema_version"] = 7
    del document["target_config"]
    del document["judge_config"]

    upgraded = upgrade_document(document)
    assert upgraded["schema_version"] == SCHEMA_VERSION
    # Nothing is reconstructed: the model that answered is not in the document,
    # and a plausible one put there would be the invention migration refuses.
    assert upgraded["target_config"] == {}
    assert not run_from_json(json.dumps(upgraded)).target_config.recorded


def test_the_headline_says_it_is_not_known_rather_than_unchanged() -> None:
    now = a_run(target={**ANTHROPIC, "temperature": 0.7})
    before = a_run()
    head = headline(compare(now, before), now, before, locale="en")
    assert "is not known" in head.sentence
    assert not head.target_config_changed


# --------------------------------------------------------------------------- #
# The perimeter: one special field, one existing rule
# --------------------------------------------------------------------------- #


def test_a_model_and_a_temperature_travel_in_clear() -> None:
    """They are measurements of the system, which is what decision 9 lets
    cross. Withholding them would cost the feature and protect nothing."""
    run = a_run(
        target={"provider": "openai", "model": "gpt-5", "temperature": 0.7},
        judge={"provider": "openai", "model": "gpt-5-mini"},
    )
    kept = redact(run)
    assert kept.target_config.values["model"] == "gpt-5"
    assert kept.target_config.values["temperature"] == 0.7
    assert kept.judge_config.values["model"] == "gpt-5-mini"


def test_a_base_url_is_withheld_and_not_dropped() -> None:
    """An internal gateway hostname is topology, and often names the customer.
    It gets the artifact treatment: the value goes, the key stays as withheld,
    and the comparison answers `unknown` (ADR 0003 §4, ADR 0005 §2)."""
    run = a_run(
        target={"provider": "openai", "model": "gpt-5", "base_url": "gw.internal.acme"}
    )
    kept = redact(run)

    assert "base_url" not in kept.target_config.values
    assert kept.target_config.withheld == frozenset({"base_url"})
    # The key survives and the value does not: "this run kept it back" and
    # "this run never had one" are different facts, and a reader is owed both.
    document = json.loads(run_to_json(kept))
    assert "gw.internal.acme" not in json.dumps(document)
    assert document["target_config"]["withheld"] == ["base_url"]
    assert "base_url" not in document["target_config"]["values"]


def test_no_disclosure_releases_a_base_url() -> None:
    """One special field, one existing rule, no new mechanism: there is no
    `Disclosure` member for this, so the prudent default cannot be turned off
    by forgetting to think about it."""
    run = a_run(
        target={"provider": "openai", "model": "gpt-5", "base_url": "gw.internal.acme"}
    )
    kept = redact(run, Disclosure(artifacts=True, run_metadata=frozenset({"base_url"})))
    assert "base_url" not in kept.target_config.values


def test_a_withheld_field_compares_as_unknown_never_as_same() -> None:
    """`same` on a value nobody has would be a guess wearing the clothes of a
    finding."""
    now = redact(
        a_run(target={"provider": "openai", "model": "gpt-5", "base_url": "gw.acme"})
    )
    before = a_run(
        target={"provider": "openai", "model": "gpt-5", "base_url": "gw.acme"}
    )
    outcomes = {d.field: d.outcome for d in compare(now, before).target_config_deltas}
    assert outcomes["base_url"] == "unknown"
    assert outcomes["model"] == "same"


def test_a_run_claiming_redaction_may_not_still_carry_a_base_url() -> None:
    """`redacted` is verified rather than believed, here as everywhere: a flag
    that announces a guarantee nothing provides is worse than no flag."""
    with pytest.raises(ValueError, match="base_url"):
        Run(
            tenant="t",
            environment="staging",
            suite="qa",
            config_hash="cfg",
            created_at="2026-08-31T00:00:00Z",
            target_config=SystemConfig(
                values={"provider": "openai", "model": "gpt-5", "base_url": "gw.acme"}
            ),
            redacted=True,
        )


def test_the_redacted_report_still_names_the_model_and_hides_the_host() -> None:
    """World 2's whole ask: hand world 3 a document saying the model changed
    without handing over the endpoint the customer's gateway sits on."""
    now = redact(
        a_run(
            target={"provider": "openai", "model": "gpt-5", "base_url": "gw.acme.local"}
        )
    )
    before = a_run(
        target={"provider": "openai", "model": "gpt-4o", "base_url": "gw.acme.local"}
    )
    document = render_html(compare(now, before), now, before, locale="it")
    assert "gpt-4o" in document and "gpt-5" in document
    assert "gw.acme.local" not in document
    assert "non incluso" in document


# --------------------------------------------------------------------------- #
# What the reader sees
# --------------------------------------------------------------------------- #


def scored(name: str, value: float) -> Verdict:
    return Verdict(
        score=Score(name=name, score=value),
        threshold=0.5,
        status="pass" if value >= 0.5 else "fail",
        reason="judged",
        assertion_id=name,
    )


def regression_runs() -> tuple[Run, Run]:
    """One check that dropped, and a temperature that moved with it."""
    from digline.core import CaseResult

    now = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg",
        created_at="2026-08-31T00:00:00Z",
        results=(CaseResult(case_id="capital-it", verdicts=(scored("quality", 0.2),)),),
        target_config=SystemConfig(values={**ANTHROPIC, "temperature": 0.7}),
    )
    before = Run(
        tenant="acme-bank",
        environment="staging",
        suite="qa",
        config_hash="cfg",
        created_at="2026-08-30T00:00:00Z",
        results=(CaseResult(case_id="capital-it", verdicts=(scored("quality", 0.9),)),),
        target_config=SystemConfig(values={**ANTHROPIC, "temperature": 0.3}),
    )
    return now, before


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "coincides with temperature 0.3 → 0.7"),
        ("it", "coincide con temperature 0.3 → 0.7"),
    ],
)
def test_the_report_says_a_drop_coincided_with_the_change(
    locale: str, expected: str
) -> None:
    """The sentence the ADR exists for. Not a claim of cause — `coincides` is
    the strongest word two facts in one comparison support — but it is what
    makes a reviewer check the configuration before blaming the prompt."""
    now, before = regression_runs()
    document = render_html(compare(now, before), now, before, locale=locale)  # type: ignore[arg-type]
    assert expected in document


def test_a_drop_without_a_configuration_change_says_nothing_extra() -> None:
    now, before = regression_runs()
    same = Run(
        tenant=before.tenant,
        environment=before.environment,
        suite=before.suite,
        config_hash=before.config_hash,
        created_at=before.created_at,
        results=before.results,
        target_config=now.target_config,
    )
    document = render_html(compare(now, same), now, same, locale="en")
    assert "coincides with" not in document


def test_the_two_sentences_do_not_both_say_configuration() -> None:
    """They sat next to each other and meant two different things: the rules
    that judge, and the system that answered. The first one names the suite."""
    now, before = regression_runs()
    sentence = headline(compare(now, before), now, before, locale="en").sentence
    assert "The suite is unchanged from the reference." in sentence
    assert "answered under a different configuration" in sentence
    assert sentence.count("configuration") == 1


def test_the_terminal_names_the_change_on_one_line() -> None:
    now, before = regression_runs()
    assert config_lines(compare(now, before), locale="en") == (
        "system · temperature 0.3 → 0.7",
    )


def test_a_temperature_reads_as_a_temperature_and_not_as_a_score() -> None:
    """`0.7` is a number somebody typed; `0.700000` would read as a measurement
    it is not."""
    now, before = regression_runs()
    line = config_lines(compare(now, before), locale="en")[0]
    assert "0.700000" not in line


# --------------------------------------------------------------------------- #
# End to end, through the command line
# --------------------------------------------------------------------------- #

SUITE = """\
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="capital-it")],
)


class Target:
    def __init__(self, temperature):
        self.temperature = temperature

    @property
    def config(self):
        return {
            "provider": "anthropic",
            "model": "claude-sonnet-5",
            "max_tokens": 1024,
            "temperature": self.temperature,
        }

    def __call__(self, case):
        return Response(output="The capital is Rome.", cost_usd=0.01)


target = Target(%(temperature)s)
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "suite_qa.py").write_text(SUITE % {"temperature": "0.3"}, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def key_of(project: Path) -> str:
    done = cli(project, "run", "--suite", "suite_qa.py")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_the_cycle_records_promotes_and_then_names_the_delta(project: Path) -> None:
    """Run, promote, change the temperature, run again, compare — and the
    terminal says which parameter moved rather than that something did."""
    cli(project, "promote", "--suite", "suite_qa.py", "--run", key_of(project))
    (project / "suite_qa.py").write_text(
        SUITE % {"temperature": "0.7"}, encoding="utf-8"
    )

    key = key_of(project)
    stored = FileResultStore(project).read_run(
        RunRef(tenant="acme-bank", suite="qa", key=key)
    )
    assert stored.target_config.values["temperature"] == 0.7

    done = cli(project, "compare", "--suite", "suite_qa.py", "--run", key)
    assert "temperature 0.3 → 0.7" in done.stdout
    assert "different configuration" in done.stdout


def test_the_json_output_carries_the_named_deltas(project: Path) -> None:
    cli(project, "promote", "--suite", "suite_qa.py", "--run", key_of(project))
    (project / "suite_qa.py").write_text(
        SUITE % {"temperature": "0.7"}, encoding="utf-8"
    )
    done = cli(
        project,
        "compare",
        "--suite",
        "suite_qa.py",
        "--run",
        key_of(project),
        "--json",
        "full",
    )
    payload = json.loads(done.stdout)
    assert payload["target_config_changed"] is True
    assert {
        "field": "temperature",
        "outcome": "changed",
        "before": 0.3,
        "after": 0.7,
        "withheld": False,
    } in payload["target_config_deltas"]
