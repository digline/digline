"""A count is read as declared, never converted into one. (#367)

`Run.judge_samples` was read with `int(raw.get("judge_samples") or 0)`, the
coercion #350 removed from `schema_version`, applied to a count:

- `5.9` and `2.5` were truncated to a count the replay did not use;
- `0.9`, `false`, `""`, `0.0` and `null` read as `0`, a replay that never
  measured the judge's range;
- `"5"` read as 5;
- `true` was refused with a sentence about `1`, a value the file does not hold;
- `"x"` was refused with `int()`'s message, which echoes the file's text.

Each refusal test here fails on the tree before #367. An integer, an explicit
`0` and an absent key read as they always did.
"""

from __future__ import annotations

from typing import Any

import pytest

from digline.core import CaseResult, Run, Score, Verdict
from digline.core.run import DocumentRefusedError, run_from_dict, run_to_dict

#: Text a terminal or a page would act on, if a refusal echoed it.
HOSTILE = "\x1b[2K\r‮FORGED"


def a_replay() -> dict[str, Any]:
    """A replay's document: the one kind of run that may carry the count."""
    verdict = Verdict(
        score=Score(name="contains", score=1.0),
        threshold=1.0,
        tolerance=0.0,
        status="pass",
        reason="found",
        assertion_id="contains-1",
    )
    return run_to_dict(
        Run(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash="hash-a",
            created_at="2026-01-02T10:00:00+00:00",
            results=(CaseResult("case-1", (verdict,)),),
            rejudged_from="2026-01-01T10-00-00Z-hash-a",
            judge_samples=5,
        )
    )


def declaring(value: object) -> dict[str, Any]:
    document = a_replay()
    document["judge_samples"] = value
    return document


# --------------------------------------------------------------------------- #
# What reads as it always did
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [0, 2, 5])
def test_an_integer_is_read_as_itself(value: int) -> None:
    assert run_from_dict(declaring(value)).judge_samples == value


def test_an_absent_count_is_zero() -> None:
    """How `run_to_dict` writes a run that did not measure the judge."""
    document = a_replay()
    del document["judge_samples"]
    assert run_from_dict(document).judge_samples == 0


# --------------------------------------------------------------------------- #
# What `int()` converted, and is now refused by its type
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("5", "string"),
        (5.9, "number"),
        (2.5, "number"),
        (0.9, "number"),
        (0.0, "number"),
        (True, "boolean"),
        (False, "boolean"),
        (None, "null"),
        ([5], "array"),
        ("", "string"),
        ("x", "string"),
        (HOSTILE, "string"),
    ],
    ids=repr,
)
def test_anything_but_an_integer_is_refused_by_its_type(
    value: object, kind: str
) -> None:
    """Named by field and JSON type, never by value: `true` no longer reads as a
    sentence about `1`, and `"x"` or a control sequence never reach stderr."""
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_dict(declaring(value))
    message = str(refused.value)
    assert f"'judge_samples' is a JSON {kind}, not an integer" in message
    assert "is 1:" not in message
    if isinstance(value, str) and value:
        assert value not in message


# --------------------------------------------------------------------------- #
# What the count may be is still `__post_init__`'s rule
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [1, -3])
def test_an_integer_the_count_cannot_be_is_still_refused(value: int) -> None:
    """The type is the reader's; 0-or-at-least-2 is the run's, and it now sees
    the number the file holds rather than what `int()` made of it."""
    with pytest.raises(DocumentRefusedError, match=f"Run.judge_samples is {value}:"):
        run_from_dict(declaring(value))
