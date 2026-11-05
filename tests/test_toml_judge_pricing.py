"""A judge named in a `suite.toml` whose model its plugin does not price.
(ADR 0007 §3, dated note of 2026-11-05)

A suite.py passes `pricing=` to the judge; a `suite.toml` had no way to, so
every check that judge judged errored with its cost not known, and the
sentence said `pricing=`, which a TOML file cannot write. Now:

- the suite is refused when it loads, before anything is spent, and the
  sentence names the TOML key;
- `judge_pricing`, beside `judge`, declares the rates in the shape
  `[target.pricing]` has, and the judge prices with them;
- a model the plugin lists needs nothing.

The real Anthropic plugin builds the judge: building one calls nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digline.core import LlmRubric
from digline.host.errors import UsageError
from digline.host.toml_suite import load_toml_suite
from digline.targets import Pricing

SUITE = """
[suite]
tenant = "acme"
environment = "dev"
name = "priced"
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


def test_an_unpriced_judge_is_refused_at_load_naming_the_toml_key(
    tmp_path: Path,
) -> None:
    with pytest.raises(UsageError) as refused:
        load(tmp_path, 'judge = "anthropic/claude-not-listed"')
    said = str(refused.value)
    assert "'claude-not-listed', which anthropic's price list does not have" in said
    assert "judge_pricing = { input_per_mtok" in said
    assert "pricing=" not in said.replace("judge_pricing =", "")


def test_judge_pricing_prices_the_judge_with_the_rates_it_declares(
    tmp_path: Path,
) -> None:
    rubric = load(
        tmp_path,
        'judge = "anthropic/claude-not-listed"\n'
        "judge_pricing = { input_per_mtok = 1.0, output_per_mtok = 5.0 }",
    )
    pricing = getattr(rubric.judge, "pricing")  # noqa: B009 — the judge is a protocol
    assert isinstance(pricing, Pricing)
    price = pricing.per_model["claude-not-listed"]
    assert (price.input_per_mtok, price.output_per_mtok) == (1.0, 5.0)


def test_a_model_the_plugin_lists_needs_no_judge_pricing(tmp_path: Path) -> None:
    rubric = load(tmp_path, 'judge = "anthropic/claude-haiku-4-5"')
    pricing = getattr(rubric.judge, "pricing")  # noqa: B009 — the judge is a protocol
    assert isinstance(pricing, Pricing)
    assert pricing.knows("claude-haiku-4-5")


def test_judge_pricing_with_no_judge_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="prices the judge `judge` names"):
        load(
            tmp_path,
            "judge_pricing = { input_per_mtok = 1.0, output_per_mtok = 5.0 }",
        )


def test_judge_pricing_needs_both_rates(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="`output_per_mtok` is missing"):
        load(
            tmp_path,
            'judge = "anthropic/claude-not-listed"\n'
            "judge_pricing = { input_per_mtok = 1.0 }",
        )
