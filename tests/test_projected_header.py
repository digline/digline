"""A projected document says so in its header, beside the redacted line. (#313)

Until this, the header was decided from `redacted` alone, and a projected page
said only *"produced from redacted data"*, which is true of a document in
clear too. Written from the mistake each test prevents: the line missing on a
projected document, the line on a document that is not projected, and the line
put in place of the redacted one rather than beside it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from tests.test_project_served import unpromoted
from tests.test_projection import Table, promoted

from digline.core import NOTHING_EXTRA, compare, project, project_served, redact
from digline.report import Locale, render_html, render_run_html
from digline.report.text import phrase

LOCALES: tuple[Locale, ...] = ("en", "it")


def says(html: str, locale: Locale, key: str) -> bool:
    return f"<dt>{phrase(locale, key)}</dt>" in html


@pytest.mark.parametrize("locale", LOCALES)
def test_a_projected_run_on_its_own_says_its_names_were_replaced(
    locale: Locale,
) -> None:
    html = render_run_html(project_served(unpromoted(), Table()), locale=locale)
    assert says(html, locale, "header.projected")
    assert says(html, locale, "header.redacted")


@pytest.mark.parametrize("locale", LOCALES)
def test_a_projected_comparison_says_its_names_were_replaced(locale: Locale) -> None:
    table = Table()
    reference = project(promoted(), table)
    served = project_served(unpromoted(), table)
    html = render_html(
        compare(served, reference), served, reference, locale=locale, declared=None
    )
    assert says(html, locale, "header.projected")
    assert says(html, locale, "header.redacted")


@pytest.mark.parametrize("locale", LOCALES)
def test_a_redacted_document_in_clear_does_not_claim_tokens(locale: Locale) -> None:
    run = redact(unpromoted(), NOTHING_EXTRA)
    reference = redact(promoted(), NOTHING_EXTRA)
    alone = render_run_html(run, locale=locale)
    against = render_html(
        compare(run, reference), run, reference, locale=locale, declared=None
    )
    for html in (alone, against):
        assert says(html, locale, "header.redacted")
        assert not says(html, locale, "header.projected")


@pytest.mark.parametrize("locale", LOCALES)
def test_a_document_in_clear_says_neither(locale: Locale) -> None:
    run = unpromoted()
    reference = replace(promoted(), created_at="2026-09-01T00:00:00+00:00")
    alone = render_run_html(run, locale=locale)
    against = render_html(
        compare(run, reference), run, reference, locale=locale, declared=None
    )
    for html in (alone, against):
        assert not says(html, locale, "header.redacted")
        assert not says(html, locale, "header.projected")


def test_the_line_says_where_the_names_are_in_every_locale() -> None:
    """The part that tells the reader what to do."""
    assert "data owner" in phrase("en", "header.projected.value")
    assert "titolare dei dati" in phrase("it", "header.projected.value")
