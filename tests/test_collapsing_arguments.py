"""A declared argument that `canonical` would reduce to its type's name is
refused when the check is built. (ADR 0018 §5, noted 2026-11-04)

Measured on 2026-11-02 and again before this repair: a date-time declared in
a TOML suite became `"<datetime>"`, so the right value sent as JSON text
failed and only the placeholder text passed; a `date` declared in Python
passed against any other `date`. One check unsatisfiable, the other vacuous.

What is held here:

- `collapsing` finds what `canonical` collapses, by `canonical`'s own
  branches, and the two agree on every sample;
- `ToolCalledWith` refuses such an argument, saying where it is and what to
  declare instead, and a TOML suite meets the same sentence at load;
- what `canonical` keeps distinct is still declared, and still matches;
- an `expected` holding a date does not reach `Equals` collapsed: a cases
  file is JSON, and `Equals` compares a nested value as it is.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from digline.core import Equals, EvaluatorInputs, RefusedError, ToolCalledWith
from digline.core.types import canonical, collapsing
from digline.host.errors import UsageError
from digline.host.toml_suite import load_toml_suite


@dataclass(frozen=True)
class Slot:
    when: datetime.date


@dataclass(frozen=True)
class Seat:
    row: int


def a_function() -> None:
    return None


#: What `canonical` reduces to a type's name, at a path a sentence can name.
COLLAPSING: list[tuple[object, str, str]] = [
    (datetime.date(1999, 9, 9), "", "date"),
    (datetime.datetime(1999, 9, 9, 9), "", "datetime"),
    (datetime.time(9), "", "time"),
    (datetime.timedelta(days=1), "", "timedelta"),
    (object(), "", "object"),
    (int, "", "type"),
    (a_function, "", "function"),
    (Path("/x"), "", type(Path("/x")).__name__),
    (1 + 2j, "", "complex"),
    ({"when": datetime.date(1999, 9, 9)}, '["when"]', "date"),
    ({"a": [1, {"b": datetime.time(9)}]}, '["a"][1]["b"]', "time"),
    (Slot(when=datetime.date(1999, 9, 9)), '["when"]', "date"),
    (
        {"tags": frozenset({datetime.date(1999, 9, 9)})},
        '["tags"], an element of a set,',
        "date",
    ),
]

#: What `canonical` keeps, each value distinct from another of its type.
KEPT: list[object] = [
    None,
    True,
    7,
    "1999-09-09T09:00:00Z",
    0.5,
    float("nan"),
    b"\x00",
    bytearray(b"\x01"),
    {"a": [1, "b", None]},
    ("x", 2),
    frozenset({"a", "b"}),
    Seat(row=3),
]


def type_names_in(value: object) -> set[str]:
    """Every `"<Name>"` string in a canonical form."""
    if isinstance(value, str):
        return {value[1:-1]} if value.startswith("<") and value.endswith(">") else set()
    if isinstance(value, dict):
        return set().union(*(type_names_in(v) for v in value.values()))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownMemberType]
    if isinstance(value, list):
        return set().union(*(type_names_in(v) for v in value))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return set()


@pytest.mark.parametrize(
    ("value", "at", "name"), COLLAPSING, ids=[f"{n}{a}" for _, a, n in COLLAPSING]
)
def test_collapsing_finds_what_canonical_reduces_to_its_type(
    value: object, at: str, name: str
) -> None:
    assert collapsing(value) == (at, name)
    assert name in type_names_in(canonical(value))


@pytest.mark.parametrize("value", KEPT, ids=[type(v).__name__ for v in KEPT])
def test_collapsing_lets_through_what_canonical_keeps(value: object) -> None:
    assert collapsing(value) is None
    assert not type_names_in(canonical(value))


# -- the refusal, in Python ----------------------------------------------------- #


@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        ({"when": datetime.date(1999, 9, 9)}, 'arguments["when"] is a date'),
        ({"check": a_function}, 'arguments["check"] is a function'),
        ({"kind": int}, 'arguments["kind"] is a type'),
        ({"slot": {"at": [datetime.time(9)]}}, 'arguments["slot"]["at"][0] is a time'),
        (
            {"slot": Slot(when=datetime.date(1999, 9, 9))},
            'arguments["slot"]["when"] is a date',
        ),
    ],
    ids=["date", "function", "class", "nested", "dataclass-field"],
)
def test_tool_called_with_refuses_an_argument_that_collapses(
    arguments: dict[str, object], said: str
) -> None:
    with pytest.raises(RefusedError) as refused:
        ToolCalledWith(tool="book", arguments=arguments)
    sentence = str(refused.value)
    assert said in sentence
    assert "ISO 8601" in sentence
    assert "in quotes in a TOML suite" in sentence


def test_what_canonical_keeps_is_declared_and_still_matches() -> None:
    check = ToolCalledWith(
        tool="book",
        arguments={"when": "1999-09-09T09:00:00Z", "seats": [1, 2], "vip": True},
    )
    sent = '{"when": "1999-09-09T09:00:00Z", "seats": [1, 2], "vip": true}'
    other = '{"when": "2031-01-01T00:00:00Z", "seats": [1, 2], "vip": true}'
    assert judged(check, sent) == "pass"
    assert judged(check, other) == "fail"


def judged(check: ToolCalledWith, sent: object) -> str:
    inputs = EvaluatorInputs(
        output="ok",
        metadata={"response": {"tool_calls": [{"tool": "book", "arguments": sent}]}},
    )
    return check(inputs).status


# -- the refusal, from TOML ------------------------------------------------------ #

SUITE = """
[suite]
tenant = "acme"
environment = "test"
name = "bookings"
cases = "cases.json"

[target]
type = "http"
url = "http://localhost:8080/answer"
output_path = "data"
tool_calls_path = "calls"

  [target.body]
  question = "case.vars.question"

[[assertions]]
type = "tool_called_with"
tool = "book"
arguments = {{ when = {when} }}
"""


def load(tmp_path: Path, when: str, cases: str = '[{"id": "a"}]') -> Any:
    (tmp_path / "suite.toml").write_text(SUITE.format(when=when), encoding="utf-8")
    (tmp_path / "cases.json").write_text(cases, encoding="utf-8")
    return load_toml_suite(tmp_path / "suite.toml")[0]


@pytest.mark.parametrize(
    ("literal", "name"),
    [
        ("1999-09-09T09:00:00Z", "datetime"),
        ("1999-09-09T09:00:00", "datetime"),
        ("1999-09-09", "date"),
        ("09:00:00", "time"),
    ],
    ids=["offset-date-time", "local-date-time", "local-date", "local-time"],
)
def test_a_toml_date_or_time_literal_is_refused_at_load(
    tmp_path: Path, literal: str, name: str
) -> None:
    with pytest.raises(UsageError) as refused:
        load(tmp_path, literal)
    sentence = str(refused.value)
    assert "suite.toml, [[assertions]] #1, `tool_called_with`" in sentence
    assert f'arguments["when"] is a {name}' in sentence
    assert "in quotes in a TOML suite" in sentence


def test_the_same_value_in_quotes_loads_and_matches(tmp_path: Path) -> None:
    [check] = load(tmp_path, '"1999-09-09T09:00:00Z"').assertions
    assert judged(check, '{"when": "1999-09-09T09:00:00Z"}') == "pass"
    assert judged(check, '{"when": "<datetime>"}') == "fail"


# -- Equals: measured, and held as it is ---------------------------------------- #


def test_a_cases_file_cannot_carry_a_date_into_expected(tmp_path: Path) -> None:
    """A cases file is JSON, and JSON has no date: a TOML-shaped one is
    refused before any case exists, so no date reaches `Equals` from TOML."""
    with pytest.raises(UsageError, match="is not valid JSON"):
        load(tmp_path, '"x"', cases='[[cases]]\nid = "a"\nexpected = 1999-09-09\n')


@pytest.mark.parametrize(
    "written",
    ['[{ id = "a", expected = 1999-09-09 }]', '{ id = "a", expected = "secret" }'],
    ids=["array", "table"],
)
def test_cases_written_in_the_suite_are_refused_without_quoting_them(
    tmp_path: Path, written: str
) -> None:
    """The refusal names the file and the key, and quotes nothing of what was
    written there: a case is the end company's payload."""
    body = SUITE.format(when='"x"').replace(
        'cases = "cases.json"', f"cases = {written}"
    )
    (tmp_path / "suite.toml").write_text(body, encoding="utf-8")
    with pytest.raises(UsageError) as refused:
        load_toml_suite(tmp_path / "suite.toml")
    sentence = str(refused.value)
    assert sentence == (
        "suite.toml, [suite]: `cases` must be the path of a JSON file or an "
        "array of paths, not a table or cases written in the suite"
    )


def test_equals_compares_a_nested_date_as_it_is() -> None:
    """`Equals` normalises containers and leaves a value as it is, so two
    dates are compared as dates: not collapsed."""
    check = Equals()
    same = EvaluatorInputs(
        output={"when": datetime.date(1999, 9, 9)},
        expected={"when": datetime.date(1999, 9, 9)},
    )
    other = EvaluatorInputs(
        output={"when": datetime.date(2031, 1, 1)},
        expected={"when": datetime.date(1999, 9, 9)},
    )
    assert check(same).status == "pass"
    assert check(other).status == "fail"
