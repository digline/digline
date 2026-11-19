"""A judge set up in the `suite.toml`: `judge` as a table of four keys.
(ADR 0068 §1, §2, §4)

- the table builds the judge the same keyword arguments build in Python,
  compared by `config`;
- `max_tokens` and `temperature` reach the run's `judge_config`, and a key
  the table leaves out leaves the value the plugin's default gives;
- `pricing` prices a model the plugin's list does not have, so the judge's
  preflight, asked before the first call, lets it through;
- each wrong table is refused at load, by its key, each beside a control
  that loads.

The real plugins build the judges: building one calls nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.core import LlmRubric
from digline.host.errors import UsageError
from digline.host.toml_suite import load_toml_suite
from digline.run.driver import judge_config
from digline.targets import Pricing
from digline_anthropic import AnthropicJudge
from digline_openai import OpenAIJudge

SUITE = """
[suite]
tenant = "acme"
environment = "dev"
name = "tabled"
cases = "cases.json"

[[assertions]]
type = "llm_rubric"
rubric = "r"
threshold = 0.7
tolerance = 0.05
%s

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"
"""


def load(tmp_path: Path, judge: str) -> LlmRubric:
    (tmp_path / "suite.toml").write_text(SUITE % judge, encoding="utf-8")
    (tmp_path / "cases.json").write_text(
        json.dumps([{"id": "a", "vars": {"question": "?"}}]), encoding="utf-8"
    )
    suite, _ = load_toml_suite(tmp_path / "suite.toml")
    [rubric] = suite.assertions
    assert isinstance(rubric, LlmRubric)
    return rubric


def recorded(tmp_path: Path, judge: str) -> dict[str, object]:
    """The `judge_config` a run of the suite would record."""
    (tmp_path / "suite.toml").write_text(SUITE % judge, encoding="utf-8")
    (tmp_path / "cases.json").write_text(
        json.dumps([{"id": "a", "vars": {"question": "?"}}]), encoding="utf-8"
    )
    suite, _ = load_toml_suite(tmp_path / "suite.toml")
    return dict(judge_config(suite).values)


# ── The table builds the judge Python builds ─────────────────────────────── #


def test_a_table_builds_the_judge_the_same_arguments_build_in_python(
    tmp_path: Path,
) -> None:
    rubric = load(
        tmp_path,
        'judge = { model = "openai/gpt-5-mini", max_tokens = 2048, temperature = 0.3 }',
    )
    assert isinstance(rubric.judge, OpenAIJudge)
    python = OpenAIJudge(model="gpt-5-mini", max_tokens=2048, temperature=0.3)
    assert dict(rubric.judge.config) == dict(python.config)


def test_the_string_form_still_loads_and_grades_with_the_plugins_defaults(
    tmp_path: Path,
) -> None:
    rubric = load(tmp_path, 'judge = "openai/gpt-5-mini"')
    assert isinstance(rubric.judge, OpenAIJudge)
    assert dict(rubric.judge.config) == dict(OpenAIJudge(model="gpt-5-mini").config)


def test_a_table_with_the_model_alone_is_the_string_form(tmp_path: Path) -> None:
    tabled = recorded(tmp_path, 'judge = { model = "openai/gpt-5-mini" }')
    plain = recorded(tmp_path, 'judge = "openai/gpt-5-mini"')
    assert tabled == plain


# ── What reaches the run ─────────────────────────────────────────────────── #


def test_max_tokens_and_temperature_reach_the_runs_judge_config(
    tmp_path: Path,
) -> None:
    config = recorded(
        tmp_path,
        'judge = { model = "openai/gpt-5-mini", max_tokens = 2048, temperature = 0.3 }',
    )
    assert config["max_tokens"] == 2048
    assert config["temperature"] == 0.3
    assert "score_prompt_digest" in config


def test_a_setting_left_out_leaves_the_plugins_default(tmp_path: Path) -> None:
    config = recorded(
        tmp_path, 'judge = { model = "openai/gpt-5-mini", max_tokens = 2048 }'
    )
    assert config["max_tokens"] == 2048
    # A temperature that was not sent is absent, not zero (ADR 0005 §1).
    assert "temperature" not in config


def test_a_raised_max_tokens_is_a_judge_configuration_that_changed(
    tmp_path: Path,
) -> None:
    before = recorded(tmp_path, 'judge = { model = "anthropic/claude-haiku-4-5" }')
    after = recorded(
        tmp_path,
        'judge = { model = "anthropic/claude-haiku-4-5", max_tokens = 4096 }',
    )
    assert before["max_tokens"] != after["max_tokens"] == 4096


# ── The price from the table ─────────────────────────────────────────────── #


def test_pricing_in_the_table_unlocks_a_model_the_plugin_does_not_price(
    tmp_path: Path,
) -> None:
    unpriced = load(tmp_path, 'judge = { model = "anthropic/claude-not-listed" }')
    assert isinstance(unpriced.judge, AnthropicJudge)
    # The preflight the driver asks of every judge before the first call.
    with pytest.raises(Exception, match="claude-not-listed"):
        unpriced.judge.preflight()

    priced = load(
        tmp_path,
        'judge = { model = "anthropic/claude-not-listed", pricing = '
        "{ input_per_mtok = 1.0, output_per_mtok = 5.0, "
        "cache_read_per_mtok = 0.1, cache_write_per_mtok = 1.25 } }",
    )
    assert isinstance(priced.judge, AnthropicJudge)
    priced.judge.preflight()
    pricing = priced.judge.pricing
    assert isinstance(pricing, Pricing)
    price = pricing.per_model["claude-not-listed"]
    assert (
        price.input_per_mtok,
        price.output_per_mtok,
        price.cache_read_per_mtok,
        price.cache_write_per_mtok,
    ) == (1.0, 5.0, 0.1, 1.25)


# ── Refused at load, each beside a control that loads ────────────────────── #


def test_an_unknown_key_is_refused_by_name_listing_the_four(tmp_path: Path) -> None:
    with pytest.raises(UsageError) as refused:
        load(
            tmp_path,
            'judge = { model = "openai/gpt-5-mini", region = "eu-west-1" }',
        )
    said = str(refused.value)
    assert "`region` is not a key of a judge's table" in said
    assert "`model`, `max_tokens`, `temperature`, `pricing`" in said
    load(tmp_path, 'judge = { model = "openai/gpt-5-mini" }')


def test_a_table_with_no_model_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="no `model`"):
        load(tmp_path, "judge = { max_tokens = 2048 }")


@pytest.mark.parametrize("temperature", ["-0.1", "2.5", '"hot"', "true"])
def test_a_temperature_outside_zero_to_two_is_refused(
    tmp_path: Path, temperature: str
) -> None:
    with pytest.raises(
        UsageError, match="`temperature` is .*; it is a number from 0 to 2"
    ):
        load(
            tmp_path,
            f'judge = {{ model = "openai/gpt-5-mini", temperature = {temperature} }}',
        )


@pytest.mark.parametrize("temperature", ["0", "0.0", "2", "2.0"])
def test_a_temperature_at_either_end_loads(tmp_path: Path, temperature: str) -> None:
    config = recorded(
        tmp_path,
        f'judge = {{ model = "openai/gpt-5-mini", temperature = {temperature} }}',
    )
    assert config["temperature"] == float(temperature)


@pytest.mark.parametrize("max_tokens", ["1024.5", '"1024"', "0", "true"])
def test_a_max_tokens_that_is_not_a_whole_number_of_at_least_one_is_refused(
    tmp_path: Path, max_tokens: str
) -> None:
    with pytest.raises(UsageError, match="`max_tokens` is .*; it is a whole number"):
        load(
            tmp_path,
            f'judge = {{ model = "openai/gpt-5-mini", max_tokens = {max_tokens} }}',
        )
    assert (
        recorded(tmp_path, 'judge = { model = "openai/gpt-5-mini", max_tokens = 1 }')[
            "max_tokens"
        ]
        == 1
    )


def test_an_incomplete_pricing_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="`output_per_mtok` is missing"):
        load(
            tmp_path,
            'judge = { model = "anthropic/claude-not-listed", pricing = '
            "{ input_per_mtok = 1.0 } }",
        )


def test_judge_pricing_beside_a_table_is_two_prices_for_one_judge(
    tmp_path: Path,
) -> None:
    with pytest.raises(UsageError, match="two prices for one judge"):
        load(
            tmp_path,
            'judge = { model = "anthropic/claude-not-listed" }\n'
            "judge_pricing = { input_per_mtok = 1.0, output_per_mtok = 5.0 }",
        )
    # Beside a string it stays as it is.
    load(
        tmp_path,
        'judge = "anthropic/claude-not-listed"\n'
        "judge_pricing = { input_per_mtok = 1.0, output_per_mtok = 5.0 }",
    )


def test_a_temperature_the_plugin_refuses_is_refused_at_load_naming_the_entry(
    tmp_path: Path,
) -> None:
    with pytest.raises(UsageError) as refused:
        load(
            tmp_path,
            'judge = { model = "anthropic/claude-haiku-4-5", temperature = 0.2 }',
        )
    said = str(refused.value)
    assert "`judge`: anthropic could not be set up as a judge" in said
    assert "temperature" in said
    load(
        tmp_path, 'judge = { model = "anthropic/claude-haiku-4-5", max_tokens = 2048 }'
    )
