"""A version is read as declared, never converted into one. (#350)

`int()` read every `schema_version` the store opened, so a document's version
was whatever `int()` could make of it:

- `"x"`, `null` and a list raised out of `scan_runs`, outside its handler, and
  every list of the suite failed with them — `digline list` with a traceback
  and exit 1, which digline's exit table reads as "worse";
- `1.5` and `true` became 1, and were counted under a schema the file does not
  declare;
- **`18.0`, `18.9` and `"18"` became the current schema**, and the reader
  itself — not only the scan — read the file as a current run, which could
  then be listed, compared and promoted. The worst of the three, because
  nothing about it is visible.

Each test here fails on the tree before #350.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli, run_key

from digline.core.run import (
    SCHEMA_VERSION,
    DocumentRefusedError,
    declared_integer,
    declared_version,
)
from digline.store import FileResultStore, RunRef
from digline.store.migrate import migrate_file
from digline.wire import EXIT_OK

#: Every value `int()` accepted or crashed on, and none of them an integer.
NOT_AN_INTEGER: list[object] = [
    "x",
    None,
    ["x"],
    1.5,
    True,
    float(SCHEMA_VERSION),
    SCHEMA_VERSION + 0.9,
    str(SCHEMA_VERSION),
]

#: Text a terminal or a page would act on, if a refusal echoed it.
HOSTILE = "\x1b[2K\r‮FORGED"


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [0, 1, SCHEMA_VERSION, SCHEMA_VERSION + 1])
def test_an_integer_is_read_as_itself(value: int) -> None:
    assert declared_version({"schema_version": value}) == value


def test_an_absent_version_is_zero() -> None:
    """What a document from before `schema_version` looks like; `migrate`
    names what it lacks."""
    assert declared_version({}) == 0


@pytest.mark.parametrize("value", NOT_AN_INTEGER, ids=repr)
def test_anything_else_is_refused_naming_the_field(value: object) -> None:
    with pytest.raises(DocumentRefusedError, match="'schema_version' is a JSON "):
        declared_version({"schema_version": value})


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        (HOSTILE, "string"),
        (None, "null"),
        (True, "boolean"),
        (1.5, "number"),
        ([HOSTILE], "array"),
        ({"v": HOSTILE}, "object"),
    ],
)
def test_the_refusal_names_the_type_and_never_the_value(
    value: object, kind: str
) -> None:
    """The value is text from a file, and the sentence reaches a terminal and a
    page. Named by its JSON type, which is what the file's author wrote."""
    with pytest.raises(DocumentRefusedError) as raised:
        declared_integer({"leg": value}, "leg")

    assert str(raised.value) == f"'leg' is a JSON {kind}, not an integer"


def test_a_mandatory_integer_that_is_absent_is_refused_by_name() -> None:
    with pytest.raises(DocumentRefusedError, match="mandatory field 'leg'"):
        declared_integer({}, "leg")


# --------------------------------------------------------------------------- #
# Through the store
# --------------------------------------------------------------------------- #


def planted(repo: Path, value: object) -> tuple[FileResultStore, str, Path]:
    """A real run, and beside it a copy declaring `value` as its schema."""
    key = run_key(repo)
    store = FileResultStore(repo)
    stored = store.runs_dir("acme-bank") / "qa" / f"{key}.json"
    document = json.loads(stored.read_text(encoding="utf-8"))
    document["schema_version"] = value
    copy = stored.parent / "zz.json"
    copy.write_text(json.dumps(document), encoding="utf-8")
    return store, key, copy


@pytest.mark.parametrize("value", NOT_AN_INTEGER, ids=repr)
def test_the_reader_refuses_a_version_that_is_not_an_integer(
    repo: Path, value: object
) -> None:
    """The finding that matters: at `18.9` or `"18"` this read succeeded, and
    the file was a current run to everything above the store."""
    store, _key, _copy = planted(repo, value)

    with pytest.raises(DocumentRefusedError, match="'schema_version' is a JSON "):
        store.read_run(RunRef(tenant="acme-bank", suite="qa", key="zz"))


@pytest.mark.parametrize("value", NOT_AN_INTEGER, ids=repr)
def test_the_scan_counts_it_unreadable_and_keeps_the_rest(
    repo: Path, value: object
) -> None:
    """Not `skipped`: there is no schema to count it under, and `advice()`
    would point at `migrate`, which cannot recover it."""
    store, key, _copy = planted(repo, value)

    listing = store.scan_runs("acme-bank", "qa")

    assert [ref.key for ref in listing.runs] == [key]
    assert listing.unreadable == ("zz.json",)
    assert dict(listing.skipped) == {}
    assert listing.advice() == ()


@pytest.mark.parametrize("value", NOT_AN_INTEGER, ids=repr)
def test_migrate_refuses_it_with_the_true_sentence(repo: Path, value: object) -> None:
    """Not "schema 1 cannot be migrated", which `1.5` and `true` got, and not
    "already current", which `18.0` and `"18"` got."""
    _store, _key, copy = planted(repo, value)
    before = copy.read_bytes()

    with pytest.raises(DocumentRefusedError, match="'schema_version' is a JSON "):
        migrate_file(copy)

    assert copy.read_bytes() == before


def test_list_survives_it_and_says_it_left_one_out(repo: Path) -> None:
    """`null` made `digline list` exit 1 with a traceback: a crash read as a
    verdict."""
    _store, key, _copy = planted(repo, None)

    listed = cli(repo, "list", "--suite", "suite_qa.py")

    assert listed.returncode == EXIT_OK, listed.stderr
    assert key in listed.stdout
    assert "1 unreadable file(s)" in listed.stdout + listed.stderr
    assert "Traceback" not in listed.stderr
