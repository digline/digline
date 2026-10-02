"""A flag is read as declared, never converted into one. (#379)

`redacted`, `projected` and a case's `suspended` were read with `bool()`, under
which every non-empty string is true and `0`, `""` and `null` are false:

- a plain run declaring `"redacted": "false"` (or `1`, or `[0]`) was read as
  redacted, so the reader never read its reasons — and promoting it committed
  a baseline declaring `"redacted": true`, with no reason left, still carrying
  the run's metadata. No refusal at any step;
- a suspended case declaring `"suspended": 0` (or `""`, or `null`) was read as
  a case that was not suspended, and its reason was never read;
- the rest were refused with a sentence about something else: a missing
  `reason`, a `config_hash` that is not a digest, a configuration missing its
  model.

Each refusal test here fails on the tree before #379. A JSON boolean reads as
it always did.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from digline.core import CaseResult, Run, Score, Verdict
from digline.core.run import (
    DocumentRefusedError,
    case_from_dict,
    run_from_dict,
    run_to_dict,
)
from digline.store import FileResultStore

#: Text a terminal or a page would act on, if a refusal echoed it.
HOSTILE = "\x1b[2K\r‮FORGED"

#: Every JSON type that is not a boolean, with the falsy and truthy values
#: `bool()` read as `False` and as `True`.
NOT_A_BOOLEAN: list[tuple[object, str]] = [
    ("false", "string"),
    ("true", "string"),
    ("no", "string"),
    ("", "string"),
    (HOSTILE, "string"),
    (0, "number"),
    (1, "number"),
    (0.0, "number"),
    (None, "null"),
    ([], "array"),
    ([0], "array"),
    ({}, "object"),
]


def a_plain_run() -> Run:
    """A run whose file holds its reasons, and payload beside them."""
    verdict = Verdict(
        score=Score(
            name="contains", score=1.0, metadata={"quote": "Mario Rossi owes 1499"}
        ),
        threshold=1.0,
        tolerance=0.0,
        status="pass",
        reason="The reply names Mario Rossi",
        assertion_id="contains-1",
    )
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash="hash-a",
        created_at="2026-01-02T10:00:00+00:00",
        results=(
            CaseResult("case-1", (verdict,)),
            CaseResult("case-2", (), suspended="Rossi asked to stop"),
        ),
        metadata={"customer": "Mario Rossi"},
    )


def declaring(field: str, value: object) -> dict[str, Any]:
    document = run_to_dict(a_plain_run())
    document[field] = value
    return document


# --------------------------------------------------------------------------- #
# What reads as it always did
# --------------------------------------------------------------------------- #


def test_a_plain_run_reads_as_plain() -> None:
    run = run_from_dict(run_to_dict(a_plain_run()))
    assert (run.redacted, run.projected) == (False, False)
    assert run.results[0].verdicts[0].reason == "The reply names Mario Rossi"
    assert run.results[1].suspended == "Rossi asked to stop"


def test_a_suspended_case_reads_as_suspended() -> None:
    record = {"case_id": "c", "suspended": True, "suspended_reason": "down"}
    assert case_from_dict(record, redacted=False).suspended == "down"


# --------------------------------------------------------------------------- #
# What `bool()` converted, and is now refused by its type
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", ["redacted", "projected"])
@pytest.mark.parametrize(("value", "kind"), NOT_A_BOOLEAN, ids=repr)
def test_a_run_flag_that_is_not_a_boolean_is_refused(
    field: str, value: object, kind: str
) -> None:
    """Named by field and JSON type, never by value — and never by a sentence
    about a reason, a digest or a configuration the flag did not mention."""
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_dict(declaring(field, value))
    message = str(refused.value)
    assert f"run: {field!r} is a JSON {kind}, not a boolean" in message
    if value == HOSTILE:
        assert HOSTILE not in message


@pytest.mark.parametrize(("value", "kind"), NOT_A_BOOLEAN, ids=repr)
def test_a_case_flag_that_is_not_a_boolean_is_refused(value: object, kind: str) -> None:
    """The falsy half read a suspended case as one that was not, and dropped
    its reason; the truthy half read a plain case as suspended."""
    record = {"case_id": "c", "suspended": value, "suspended_reason": "down"}
    with pytest.raises(DocumentRefusedError) as refused:
        case_from_dict(record, redacted=False)
    message = str(refused.value)
    assert f"case result: 'suspended' is a JSON {kind}, not a boolean" in message
    if value == HOSTILE:
        assert HOSTILE not in message


@pytest.mark.parametrize("field", ["redacted", "projected"])
def test_an_absent_run_flag_is_refused_by_name(field: str) -> None:
    document = run_to_dict(a_plain_run())
    del document[field]
    with pytest.raises(
        DocumentRefusedError, match=f"missing the mandatory field '{field}'"
    ):
        run_from_dict(document)


# --------------------------------------------------------------------------- #
# The promotion that committed the misreading
# --------------------------------------------------------------------------- #


def test_a_plain_run_declaring_redacted_as_a_string_is_never_promoted(
    tmp_path: Path,
) -> None:
    """Before #379 this promotion succeeded, and the committed baseline said
    `"redacted": true`, held no reason, and still held `"customer": "Mario
    Rossi"`: a misreading, a false declaration in git, and the content that
    declaration denies — in one gesture, refused nowhere."""
    store = FileResultStore(tmp_path)
    ref = store.write_run(a_plain_run())
    path = store.run_path(ref)
    written = path.read_text(encoding="utf-8")
    assert written.count('"redacted": false') == 1
    path.write_text(
        written.replace('"redacted": false', '"redacted": "false"'), encoding="utf-8"
    )

    with pytest.raises(DocumentRefusedError, match="'redacted' is a JSON string"):
        store.promote_baseline(
            ref,
            "hash-a",
            expected_baseline=None,
            promoted_at="2026-01-03T10:00:00+00:00",
        )
    assert not store.baseline_path("acme", "qa").exists()
