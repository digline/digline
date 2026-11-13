"""`excluded_at_promotion` as a document holds it: schema 24. (ADR 0065 §1)

Written from the mistakes each test prevents: a reference that claims to have
left out a case it still holds; a null or a malformed entry read as *nothing
excluded*; a step from 23 that invents an exclusion; a projection that lets a
case's name or a person's through; and a page that writes a name raw.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.test_projection import Table, promoted

from digline.core import (
    Exclusion,
    is_token,
    project,
    redact,
    run_from_json,
    run_to_json,
)
from digline.core.run import SCHEMA_VERSION
from digline.report import pages
from digline.store import upgrade_document

AT = "2026-11-13T09:00:00+00:00"
LEFT_OUT = Exclusion(case_id="said-no", by="Ada Rossi", at=AT)


def test_the_schema_is_twenty_four() -> None:
    assert SCHEMA_VERSION == 24


def test_an_exclusion_round_trips_and_absent_is_nothing_excluded() -> None:
    reference = replace(promoted(), excluded_at_promotion=(LEFT_OUT,))
    assert run_from_json(run_to_json(reference)) == reference
    whole = json.loads(run_to_json(promoted()))
    assert "excluded_at_promotion" not in whole
    assert run_from_json(json.dumps(whole)).excluded_at_promotion == ()


@pytest.mark.parametrize(
    "written",
    [
        None,
        "said-no",
        [{"case_id": "said-no", "by": "Ada"}],
        [{"case_id": "said-no", "by": "Ada", "at": AT, "why": "x"}],
        [{"case_id": "said-no", "by": 7, "at": AT}],
        [["said-no", "Ada", AT]],
    ],
)
def test_a_malformed_exclusion_is_refused_never_read_as_none(written: object) -> None:
    document = json.loads(run_to_json(promoted()))
    document["excluded_at_promotion"] = written
    with pytest.raises(ValueError, match="excluded_at_promotion"):
        run_from_json(json.dumps(document))


def test_a_reference_cannot_exclude_a_case_it_holds() -> None:
    held = promoted().results[0].case_id
    with pytest.raises(ValueError, match="still carries"):
        replace(promoted(), excluded_at_promotion=(Exclusion(held, "Ada", AT),))


def test_a_case_is_excluded_once() -> None:
    with pytest.raises(ValueError, match="names a case twice"):
        replace(promoted(), excluded_at_promotion=(LEFT_OUT, LEFT_OUT))


def test_an_exclusion_names_a_person() -> None:
    with pytest.raises(ValueError, match="by a person who said so"):
        Exclusion(case_id="said-no", by="", at=AT)


def test_the_step_from_twenty_three_writes_nothing() -> None:
    current = json.loads(run_to_json(promoted()))
    older = {**current, "schema_version": 23}
    assert upgrade_document(older) == current


def test_redaction_carries_it() -> None:
    reference = replace(promoted(), excluded_at_promotion=(LEFT_OUT,))
    assert redact(reference).excluded_at_promotion == (LEFT_OUT,)


def test_a_projection_tokenises_the_case_and_the_person() -> None:
    table = Table()
    reference = replace(promoted(), excluded_at_promotion=(LEFT_OUT,))
    [item] = project(reference, table).excluded_at_promotion
    assert item.case_id == table.token("case_id", "said-no")
    assert item.by == table.token("person", "Ada Rossi")
    assert is_token(item.case_id) and is_token(item.by)
    assert item.at == AT
    assert "Ada Rossi" not in run_to_json(project(reference, Table()))


def test_the_runs_page_says_it_escaped() -> None:
    page = pages.runs_page(
        [],
        baseline_key=None,
        config_hash="0" * 16,
        locale="en",
        suite="support",
        allow_promote=False,
        refused={},
        excluded=(Exclusion(case_id="said-no", by="<b>Ada</b>", at=AT),),
    )
    assert "excluded at promotion from the reference: said-no, by" in page
    assert "<b>Ada</b>" not in page
    assert "&lt;b&gt;Ada&lt;/b&gt;" in page


def test_the_runs_page_says_nothing_where_nothing_was_excluded() -> None:
    page = pages.runs_page(
        [],
        baseline_key=None,
        config_hash="0" * 16,
        locale="en",
        suite="support",
        allow_promote=False,
        refused={},
    )
    assert "excluded at promotion" not in page
