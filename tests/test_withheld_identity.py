"""A withheld answering model is not an unchanged one.

At a named endpoint — an aggregator, a corporate gateway, a self-hosted server
behind `base_url` — `resolved_model` is a perimeter field and is withheld inside
the comparison (ADR 0005 §9, 0.12.1). Every other field could match while the
model behind the endpoint changed, and until this was fixed the headline read
that as "the same configuration as the reference": a withheld identity read as
confirmation. Nothing leaked; the sentence asserted what it did not know.
"""

from __future__ import annotations

import pytest

from digline.core import Run, SystemConfig, compare
from digline.report import LOCALES, Locale, headline, phrase

GATEWAY = "https://llm-gateway.internal.example/v1"


def a_run(created_at: str, values: dict[str, str]) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="abc",
        created_at=created_at,
        target_config=SystemConfig(values=values),
    )


def sentence(baseline: Run, run: Run, locale: Locale) -> str:
    return headline(compare(run, baseline), run, baseline, locale=locale).sentence


@pytest.mark.parametrize("locale", LOCALES)
def test_a_withheld_answering_model_is_not_the_same_configuration(
    locale: Locale,
) -> None:
    """The two runs are behind the same named endpoint and answered as two
    different models. The comparison cannot see that — and must not claim the
    opposite."""
    declared = {"provider": "openai", "model": "gpt-5.6-sol", "base_url": GATEWAY}
    baseline = a_run("2026-09-01T00:00:00+00:00", {**declared, "resolved_model": "a"})
    run = a_run("2026-09-02T00:00:00+00:00", {**declared, "resolved_model": "b"})

    said = sentence(baseline, run, locale)
    assert phrase(locale, "fact.target_config.withheld_identity") in said
    assert phrase(locale, "fact.target_config.unchanged") not in said
    # Neither answering model reaches the sentence: the value stays withheld.
    assert " a " not in f" {said} " and " b " not in f" {said} "


@pytest.mark.parametrize("locale", LOCALES)
def test_a_first_party_endpoint_still_reads_as_the_same_configuration(
    locale: Locale,
) -> None:
    """The other half of the pair: where nothing was withheld, the sentence that
    was true stays exactly as it was."""
    values = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "resolved_model": "claude-haiku-4-5-20251001",
    }
    baseline = a_run("2026-09-01T00:00:00+00:00", values)
    run = a_run("2026-09-02T00:00:00+00:00", values)

    said = sentence(baseline, run, locale)
    assert phrase(locale, "fact.target_config.unchanged") in said
    assert phrase(locale, "fact.target_config.withheld_identity") not in said


@pytest.mark.parametrize("locale", LOCALES)
def test_a_change_behind_a_named_endpoint_is_still_reported_as_a_change(
    locale: Locale,
) -> None:
    """A field that is in clear and moved still wins: the withheld clause only
    replaces the sentence that claimed nothing moved."""
    base = {"provider": "openai", "model": "gpt-5.6-sol", "base_url": GATEWAY}
    baseline = a_run(
        "2026-09-01T00:00:00+00:00",
        {**base, "temperature": "0.2", "resolved_model": "a"},
    )
    run = a_run(
        "2026-09-02T00:00:00+00:00",
        {**base, "temperature": "0.7", "resolved_model": "a"},
    )
    said = sentence(baseline, run, locale)
    assert "0.7" in said
    assert phrase(locale, "fact.target_config.withheld_identity") not in said
