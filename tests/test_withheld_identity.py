"""A withheld field is not an unchanged one.

At a named endpoint — an aggregator, a corporate gateway, a self-hosted server
behind `base_url` — `resolved_model` is a perimeter field and is withheld inside
the comparison (ADR 0005 §9, 0.12.1). Every other field could match while the
model behind the endpoint changed, and until this was fixed the headline read
that as "the same configuration as the reference": a withheld identity read as
confirmation. Nothing leaked; the sentence asserted what it did not know.

**The sentence counts the withheld fields and names none** (#275). It used to
say "the answering model is withheld", chosen by finding a withheld field in
`OBSERVED_FIELDS`, and that lookup was wrong three ways:

- on a projected document the key is a token, so the lookup missed and a model
  that changed behind a named endpoint read as "the same configuration" again;
- in clear, a `base_url` that moved is not in the set, so the endpoint moved
  under "the same configuration";
- in clear, a withheld `fingerprint` is in the set, so "the answering model is
  withheld" was said with the answering model in clear beside it.

So every case here runs in both regimes, and says the same thing in both. The
price, declared: in clear at a named endpoint, a count stands where the
answering model used to be named.
"""

from __future__ import annotations

import pytest

from digline.core import Run, SystemConfig, compare, project_served
from digline.report import LOCALES, Locale, headline, phrase
from test_projection import Table

GATEWAY = "https://llm-gateway.internal.example/v1"
REGIMES = ("clear", "projected")


def a_run(created_at: str, values: dict[str, str]) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="c0ffee00c0ffee00",
        created_at=created_at,
        target_config=SystemConfig(values=values),
    )


def sentence(
    before: dict[str, str], after: dict[str, str], locale: Locale, regime: str
) -> str:
    baseline = a_run("2026-09-01T00:00:00+00:00", before)
    run = a_run("2026-09-02T00:00:00+00:00", after)
    if regime == "projected":
        # One table for both, which is how two projections pair (ADR 0038 §3).
        table = Table()
        baseline, run = project_served(baseline, table), project_served(run, table)
    return headline(compare(run, baseline), run, baseline, locale=locale).sentence


def withheld(locale: Locale, count: int) -> str:
    if count == 1:
        return phrase(locale, "fact.target_config.withheld.one")
    return phrase(locale, "fact.target_config.withheld.many", count=count)


def changed(locale: Locale) -> str:
    """The changed sentence up to where the changes begin: the values may be
    tokens, so the test asserts on the words around them."""
    return phrase(locale, "fact.target_config.changed", changes="\0").split("\0")[0]


@pytest.mark.parametrize("regime", REGIMES)
@pytest.mark.parametrize("locale", LOCALES)
def test_a_withheld_answering_model_is_not_the_same_configuration(
    locale: Locale, regime: str
) -> None:
    """The two runs are behind the same named endpoint and answered as two
    different models. The comparison cannot see that — and must not claim the
    opposite, in clear or projected. Projected, this was #275's first case."""
    declared = {"provider": "openai", "model": "gpt-5.6-sol", "base_url": GATEWAY}
    said = sentence(
        {**declared, "resolved_model": "a"},
        {**declared, "resolved_model": "b"},
        locale,
        regime,
    )
    # Two: the endpoint, and the answering model behind it.
    assert withheld(locale, 2) in said
    assert phrase(locale, "fact.target_config.unchanged") not in said
    # Neither answering model reaches the sentence: the value stays withheld.
    assert " a " not in f" {said} " and " b " not in f" {said} "


@pytest.mark.parametrize("regime", REGIMES)
@pytest.mark.parametrize("locale", LOCALES)
def test_an_endpoint_that_moved_is_not_the_same_configuration(
    locale: Locale, regime: str
) -> None:
    """`base_url` is withheld and is not in `OBSERVED_FIELDS`, so in clear the
    endpoint moved and the headline said "the same configuration". Not one of
    #275's cases, which were about projections: found while checking that the
    new sentence did not make the clear one worse."""
    declared = {"provider": "openai", "model": "gpt-5.6-sol"}
    said = sentence(
        {**declared, "base_url": GATEWAY},
        {**declared, "base_url": "https://elsewhere.example/v1"},
        locale,
        regime,
    )
    assert withheld(locale, 1) in said
    assert phrase(locale, "fact.target_config.unchanged") not in said


@pytest.mark.parametrize("regime", REGIMES)
@pytest.mark.parametrize("locale", LOCALES)
def test_a_withheld_fingerprint_is_not_a_withheld_answering_model(
    locale: Locale, regime: str
) -> None:
    """First party: the answering model is in clear and did not move, and only
    the fingerprint is withheld. "The answering model is withheld" was false
    here in clear, because `OBSERVED_FIELDS` holds `fingerprint` beside
    `resolved_model`. Found with the one above."""
    declared = {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "resolved_model": "gpt-5.6-sol-20260901",
    }
    said = sentence(
        {**declared, "fingerprint": "fp_1"},
        {**declared, "fingerprint": "fp_2"},
        locale,
        regime,
    )
    assert withheld(locale, 1) in said
    assert phrase(locale, "fact.target_config.unchanged") not in said
    assert "fp_1" not in said and "fp_2" not in said


@pytest.mark.parametrize("regime", REGIMES)
@pytest.mark.parametrize("locale", LOCALES)
def test_a_first_party_endpoint_still_reads_as_the_same_configuration(
    locale: Locale, regime: str
) -> None:
    """The other half of the pair: where nothing was withheld, the sentence that
    was true stays exactly as it was."""
    values = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "resolved_model": "claude-haiku-4-5-20251001",
    }
    said = sentence(values, values, locale, regime)
    assert phrase(locale, "fact.target_config.unchanged") in said
    assert withheld(locale, 1) not in said


@pytest.mark.parametrize("regime", REGIMES)
@pytest.mark.parametrize("locale", LOCALES)
def test_a_change_behind_a_named_endpoint_is_still_reported_as_a_change(
    locale: Locale, regime: str
) -> None:
    """A field that moved still wins: the withheld clause only replaces the
    sentence that claimed nothing moved."""
    base = {"provider": "openai", "model": "gpt-5.6-sol", "base_url": GATEWAY}
    said = sentence(
        {**base, "temperature": "0.2", "resolved_model": "a"},
        {**base, "temperature": "0.7", "resolved_model": "a"},
        locale,
        regime,
    )
    assert changed(locale) in said
    assert withheld(locale, 2) not in said
