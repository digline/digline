"""A configuration field's verb is true in both regimes. (#275)

The report and the reading say a field the provider **reported** was
"reported", and one the suite **sent** was "sent" or "configured" (ADR 0005 §9;
ADR 0020, amended). Which is which was decided by looking the key up in
`OBSERVED_FIELDS`. A projection tokenises configuration keys, so on a projected
document the lookup missed and every field got the verb of a sent one: a
resolved model "not sent for the reference", a reported field "configured
with".

The verb is now picked three ways (`render.field_verb`): reported, sent, or —
where the key is a token and which of the two cannot be told — "recorded",
which is true of both. **It depends on the regime, and that is the price of
the distinction**: one verb everywhere would be true, and would lose in clear
what the two records ruled worth saying. So both halves are held here: the
projected sentence is the neutral one, and the clear one keeps its verb.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from digline.core import ConfigValue, Run, SystemConfig, compare, project_served
from digline.report import LOCALES, Locale, phrase
from digline.report.explain import explain_text, facts
from digline.report.render import config_changes
from test_projection import Table

type Values = Mapping[str, ConfigValue]

FIRST_PARTY: Values = {"provider": "openai", "model": "gpt-5.6-sol"}


def a_run(created_at: str, values: Values) -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="c0ffee00c0ffee00",
        created_at=created_at,
        target_config=SystemConfig(values=values),
    )


def pair(before: Values, after: Values, *, projected: bool) -> tuple[Run, Run]:
    """`(run, baseline)`, in clear or as two projections from one table."""
    baseline = a_run("2026-09-01T00:00:00+00:00", before)
    run = a_run("2026-09-02T00:00:00+00:00", after)
    if projected:
        table = Table()
        return project_served(run, table), project_served(baseline, table)
    return run, baseline


def changes(before: Values, after: Values, *, projected: bool) -> str:
    run, baseline = pair(before, after, projected=projected)
    return config_changes(compare(run, baseline).target_config_deltas, "en")


def words(locale: Locale, key: str) -> str:
    """A sentence's text with its placeholders cut out: what it says around the
    names and values, which are tokens on a projected document."""
    text = phrase(locale, key, field="\0", name="\0", before="\0", after="\0")
    return max(text.split("\0"), key=len).strip(" ,.;")


# -- Case 3: the report's `new` and `missing`.


@pytest.mark.parametrize(
    ("before", "after", "clear", "projected"),
    [
        pytest.param(
            FIRST_PARTY,
            {**FIRST_PARTY, "resolved_model": "gpt-5.6-sol-20260901"},
            "not reported for the reference",
            "not recorded for the reference",
            id="reported-new",
        ),
        pytest.param(
            {**FIRST_PARTY, "resolved_model": "gpt-5.6-sol-20260901"},
            FIRST_PARTY,
            "no longer reported",
            "no longer recorded",
            id="reported-missing",
        ),
        pytest.param(
            FIRST_PARTY,
            {**FIRST_PARTY, "temperature": 0.7},
            "not sent for the reference",
            "not recorded for the reference",
            id="sent-new",
        ),
        pytest.param(
            {**FIRST_PARTY, "temperature": 0.7},
            FIRST_PARTY,
            "no longer sent",
            "no longer recorded",
            id="sent-missing",
        ),
    ],
)
def test_the_report_says_recorded_where_it_cannot_tell(
    before: Values, after: Values, clear: str, projected: str
) -> None:
    """The first case is #275's measured one. The sent ones are the control that
    the clear distinction survived: "not sent for the reference" on a parameter
    is information, and it stays."""
    assert changes(before, after, projected=False).endswith(clear)
    assert changes(before, after, projected=True).endswith(projected)


# -- Case 2: the reading's `changed` and `alone`.


def reading(
    before: Values,
    after: Values,
    *,
    projected: bool,
    locale: Locale,
    alone: bool,
) -> str:
    run, baseline = pair(before, after, projected=projected)
    found = facts(run) if alone else facts(run, compare(run, baseline))
    return "\n".join(explain_text(found, locale=locale))


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("alone", [False, True], ids=["changed", "alone"])
@pytest.mark.parametrize(
    ("field", "verb"),
    [("resolved_model", ".observed"), ("temperature", "")],
    ids=["reported", "sent"],
)
def test_the_reading_says_recorded_where_it_cannot_tell(
    locale: Locale, alone: bool, field: str, verb: str
) -> None:
    """Projected, the reported field said "was configured with": nobody
    configured a resolved model. In clear each field keeps its own verb."""
    before = {**FIRST_PARTY, field: "x-1"}
    after = {**FIRST_PARTY, field: "x-2"}
    outcome = "alone" if alone else "changed"
    key = f"explain.setting.target.{outcome}"

    clear = reading(before, after, projected=False, locale=locale, alone=alone)
    assert words(locale, key + verb) in clear

    projected = reading(before, after, projected=True, locale=locale, alone=alone)
    assert words(locale, key + ".recorded") in projected
    assert words(locale, key) not in projected
    assert words(locale, key + ".observed") not in projected
