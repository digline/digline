"""A projected document, rendered: the report names nothing and still reads.

A served page shows projected documents (ADR 0038), so both renderers meet
documents whose names are tokens. Nothing measured that before. These tests
are what a served projection is worth: if a renderer broke on a token, or
printed a name the projection had removed, a way to project the run under
review would buy nothing. (ADR 0038 §1, §2)
"""

from __future__ import annotations

import pytest
from tests.test_projection import NAMES, Table, promoted

from digline.core import Run, compare, project
from digline.report import Locale, headline, render_html, render_run_html

LOCALES: tuple[Locale, ...] = ("en", "it")


def tokens_in(html: str, table: Table) -> set[str]:
    return {token for token in table.rows.values() if token in html}


@pytest.mark.parametrize("locale", LOCALES)
def test_a_projected_reference_renders_on_its_own_and_names_nothing(
    locale: Locale,
) -> None:
    table = Table()
    html = render_run_html(project(promoted(), table), locale=locale)
    for name in NAMES:
        assert name not in html, name
    # The names are there as tokens, so the page still says which case is which.
    assert table.token("case_id", "rossi-mario-overdraft") in html


@pytest.mark.parametrize("locale", LOCALES)
def test_a_projected_reference_renders_against_itself_and_names_nothing(
    locale: Locale,
) -> None:
    table = Table()
    reference: Run = project(promoted(), table)
    html = render_html(
        compare(reference, reference),
        reference,
        reference,
        locale=locale,
        declared=None,
    )
    for name in NAMES:
        assert name not in html, name
    assert tokens_in(html, table)
    assert not headline(
        compare(reference, reference),
        reference,
        reference,
        locale=locale,
        declared=None,
    ).worse
