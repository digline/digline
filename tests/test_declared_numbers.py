"""A number, a count and a flag are read as declared, never converted. (#379)

The second half of #379. `float()`, `int()` and `bool()` read what a run
document declares and turned it into something else:

- **A verdict's `tolerance` of `true` or `Infinity` turned a drop from 0.95 to
  0.6 into *unchanged*, and `compare` stayed green.** `Infinity` and `NaN` are
  not JSON, but Python's parser accepts them, and `Verdict` accepted both even
  when built in code — `inf < 0.0` is false, so the one check there was let it
  through. That is a vacuous green inside the gate.
- usage counts and the bill line truncated: `5.9` read as 5, `0.9` as 0,
  `true` as 1, `"5"` as 5, and a `null` cache count as 0;
- `threshold`, `spent_usd`, `cost_usd` and `latency_ms` read `"0.5"` as 0.5 and
  `true` as 1.0; `cost_usd` and `latency_ms` took `NaN` and `Infinity`;
- `canary`, `judged`, `withheld` and `oversize` read `"false"` as true, and
  `null` as false.

Every refusal test here fails on the tree before #379. What a released digline
writes reads as it always did, and an `int` where a number is declared is
accepted: JSON does not tell `1` from `1.0`.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from digline.core import CaseResult, Run, Score, Verdict, compare
from digline.core.calibration import CalibrationBand
from digline.core.run import (
    CallTotals,
    DocumentRefusedError,
    RecordedResponse,
    RunUsage,
    run_from_dict,
    run_from_json,
    run_to_dict,
)
from digline.core.types import Usage
from digline.store import FileResultStore
from digline.store.protocol import JournalHeader

#: Text a terminal or a page would act on, if a refusal echoed it.
HOSTILE = "\x1b[2K\r‮FORGED"

Document = dict[str, Any]
Locate = Callable[[Document], dict[str, Any]]


def verdict(score: float, tolerance: float = 0.05) -> Verdict:
    return Verdict(
        score=Score(name="judge", score=score),
        threshold=0.5,
        tolerance=tolerance,
        status="pass",
        reason="r",
        assertion_id="j-1",
    )


def a_run() -> Run:
    """A run that carries every field this file reads."""
    usage = Usage(
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
        thinking_tokens=7,
    )
    answer = RecordedResponse(
        output="hello", kind="text", cost_usd=0.01, latency_ms=120.0, usage=usage
    )
    return Run(
        tenant="acme",
        environment="test",
        suite="qa",
        config_hash="hash-a",
        created_at="2026-01-02T10:00:00+00:00",
        results=(
            CaseResult("c1", (verdict(0.9),), responses=(answer,)),
            CaseResult("c2", (verdict(0.9),), canary=True),
            CaseResult(
                "cal",
                (verdict(0.9),),
                calibration=CalibrationBand("judge", 0.4, 0.8, "j-1"),
            ),
        ),
        usage=RunUsage(
            target=CallTotals(calls=5, counted=5, tokens=usage, spent_usd=0.02)
        ),
    )


def at(locate: Locate, field: str, value: object) -> Document:
    document = copy.deepcopy(run_to_dict(a_run()))
    locate(document)[field] = value
    return document


def first_verdict(d: Document) -> dict[str, Any]:
    return d["results"][0]["verdicts"][0]


def first_answer(d: Document) -> dict[str, Any]:
    return d["results"][0]["responses"][0]


def target_line(d: Document) -> dict[str, Any]:
    return d["usage"]["target"]


def target_tokens(d: Document) -> dict[str, Any]:
    return d["usage"]["target"]["tokens"]


def answer_tokens(d: Document) -> dict[str, Any]:
    return d["results"][0]["responses"][0]["usage"]


def band(d: Document) -> dict[str, Any]:
    return d["results"][2]["calibration"]


def canary_case(d: Document) -> dict[str, Any]:
    return d["results"][1]


# --------------------------------------------------------------------------- #
# The vacuous green: a tolerance that holds every movement
# --------------------------------------------------------------------------- #


def a_drop() -> tuple[Document, Document]:
    """A baseline at 0.95 and a current run at 0.6: a regression."""

    def at_score(score: float, created: str) -> Document:
        return run_to_dict(
            Run(
                tenant="acme",
                environment="test",
                suite="qa",
                config_hash="hash-a",
                created_at=created,
                results=(CaseResult("c1", (verdict(score),)),),
            )
        )

    return (
        at_score(0.95, "2026-01-02T10:00:00+00:00"),
        at_score(0.6, "2026-01-03T10:00:00+00:00"),
    )


def test_the_drop_is_a_regression_as_written() -> None:
    """The control: what the two documents say when nobody touched them."""
    baseline, current = a_drop()
    comparison = compare(run_from_dict(current), run_from_dict(baseline))
    assert comparison.regressed


@pytest.mark.parametrize(
    ("literal", "refusal"),
    [
        ("true", "'tolerance' is a JSON boolean, not a number"),
        ("Infinity", "'tolerance' is NaN or Infinity, which are not JSON numbers"),
        ("NaN", "'tolerance' is NaN or Infinity, which are not JSON numbers"),
    ],
)
def test_a_tolerance_that_would_hold_the_drop_is_refused(
    literal: str, refusal: str
) -> None:
    """Before #379, `true` and `Infinity` in the current run's file compared
    the drop as *unchanged* and `compare` stayed green. Written into the bytes,
    as a file holds them: `Infinity` is not something `json.dumps` produces
    from a dict without `allow_nan`, and the reader must meet the literal."""
    baseline, current = a_drop()
    text = json.dumps(current).replace('"tolerance": 0.05', f'"tolerance": {literal}')
    assert f'"tolerance": {literal}' in text
    with pytest.raises(DocumentRefusedError, match=refusal):
        run_from_json(text)
    assert run_from_dict(baseline)  # the other side is not what is refused


@pytest.mark.parametrize("tolerance", [math.inf, math.nan])
def test_a_verdict_built_in_code_refuses_a_tolerance_that_is_not_finite(
    tolerance: float,
) -> None:
    """The reader is one door; a value built in code is the other. `inf < 0.0`
    and `nan < 0.0` are both false, so the negative check let them in."""
    with pytest.raises(ValueError, match="Verdict.tolerance must be a finite number"):
        verdict(0.9, tolerance=tolerance)


# --------------------------------------------------------------------------- #
# Numbers: a JSON number, finite, never a boolean
# --------------------------------------------------------------------------- #

NUMBERS: list[tuple[str, Locate, str]] = [
    ("verdict", first_verdict, "threshold"),
    ("verdict", first_verdict, "tolerance"),
    ("verdict", first_verdict, "score"),
    ("target", target_line, "spent_usd"),
    ("recorded response", first_answer, "cost_usd"),
    ("recorded response", first_answer, "latency_ms"),
    ("case result calibration", band, "low"),
    ("case result calibration", band, "high"),
]

NOT_A_NUMBER: list[tuple[object, str]] = [
    (True, "boolean"),
    (False, "boolean"),
    ("0.5", "string"),
    ("", "string"),
    (HOSTILE, "string"),
    ([0.5], "array"),
    ({}, "object"),
]


@pytest.mark.parametrize(
    ("where", "locate", "field"), NUMBERS, ids=lambda x: x if isinstance(x, str) else ""
)
@pytest.mark.parametrize(("value", "kind"), NOT_A_NUMBER, ids=repr)
def test_a_number_that_is_not_one_is_refused_by_its_type(
    where: str, locate: Locate, field: str, value: object, kind: str
) -> None:
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_dict(at(locate, field, value))
    message = str(refused.value)
    assert f"{where}: {field!r} is a JSON {kind}, not a number" in message
    assert HOSTILE not in message


@pytest.mark.parametrize(
    ("where", "locate", "field"), NUMBERS, ids=lambda x: x if isinstance(x, str) else ""
)
@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan], ids=repr)
def test_a_number_that_is_not_finite_is_refused(
    where: str, locate: Locate, field: str, value: float
) -> None:
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_dict(at(locate, field, value))
    assert f"{where}: {field!r} is NaN or Infinity" in str(refused.value)


def test_an_integer_where_a_number_is_declared_is_read_as_that_number() -> None:
    """JSON does not tell `1` from `1.0`, and another program may write either."""
    run = run_from_dict(at(first_answer, "cost_usd", 1))
    cost = run.results[0].responses[0].cost_usd
    assert cost == 1.0
    assert isinstance(cost, float)


def test_a_null_cost_is_refused_rather_than_read_as_unmeasured() -> None:
    """Absent is *not measured*. No digline ever wrote `null` here — every
    writer of `cost_usd` and `latency_ms` was guarded by `is not None`."""
    with pytest.raises(DocumentRefusedError, match="'cost_usd' is a JSON null"):
        run_from_dict(at(first_answer, "cost_usd", None))
    document = run_to_dict(a_run())
    del first_answer(document)["cost_usd"]
    assert run_from_dict(document).results[0].responses[0].cost_usd is None


def test_an_errored_verdict_still_writes_its_score_as_null() -> None:
    errored = Verdict(
        score=Score(name="judge", score=None),
        threshold=0.5,
        tolerance=0.05,
        status="error",
        reason="the judge did not answer",
        assertion_id="j-1",
    )
    document = run_to_dict(
        Run(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash="hash-a",
            created_at="2026-01-02T10:00:00+00:00",
            results=(CaseResult("c1", (errored,)),),
        )
    )
    assert run_from_dict(document).results[0].verdicts[0].score.score is None


# --------------------------------------------------------------------------- #
# Samples: an array of numbers
# --------------------------------------------------------------------------- #


def sampled() -> Document:
    sampled_verdict = Verdict(
        score=Score(
            name="judge",
            score=0.75,
            samples=(0.5, 1.0),
            sample_min=0.5,
            sample_max=1.0,
        ),
        threshold=0.5,
        tolerance=0.05,
        status="pass",
        reason="r",
        assertion_id="j-1",
    )
    return run_to_dict(
        Run(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash="hash-a",
            created_at="2026-01-02T10:00:00+00:00",
            results=(CaseResult("c1", (sampled_verdict,)),),
        )
    )


def test_samples_read_as_written() -> None:
    score = run_from_dict(sampled()).results[0].verdicts[0].score
    assert (score.samples, score.sample_min, score.sample_max) == ((0.5, 1.0), 0.5, 1.0)


@pytest.mark.parametrize(
    ("samples", "refusal"),
    [
        ("01", "'samples' is a JSON string, not an array"),
        ([0.5, "1.0"], "'samples' is a JSON string, not a number"),
        ([0.5, True], "'samples' is a JSON boolean, not a number"),
        (None, "'samples' is a JSON null, not an array"),
    ],
    ids=repr,
)
def test_samples_that_are_not_an_array_of_numbers_are_refused(
    samples: object, refusal: str
) -> None:
    """`float()` over the string `"01"` read it as the samples 0.0 and 1.0,
    one per character."""
    document = sampled()
    first_verdict(document)["samples"] = samples
    with pytest.raises(DocumentRefusedError, match=refusal):
        run_from_dict(document)


@pytest.mark.parametrize("field", ["sample_min", "sample_max"])
def test_an_interval_end_that_is_not_a_number_is_refused(field: str) -> None:
    document = sampled()
    first_verdict(document)[field] = "0.5"
    with pytest.raises(DocumentRefusedError, match=f"'{field}' is a JSON string"):
        run_from_dict(document)


# --------------------------------------------------------------------------- #
# Counts: an integer, never a boolean
# --------------------------------------------------------------------------- #

COUNTS: list[tuple[str, Locate, str]] = [
    ("target", target_line, "calls"),
    ("target", target_line, "counted"),
    ("target", target_tokens, "input_tokens"),
    ("target", target_tokens, "output_tokens"),
    ("target", target_tokens, "cache_read_tokens"),
    ("target", target_tokens, "cache_write_tokens"),
    ("target", target_tokens, "thinking_tokens"),
    ("recorded response", answer_tokens, "input_tokens"),
    ("recorded response", answer_tokens, "cache_read_tokens"),
]

NOT_A_COUNT: list[tuple[object, str]] = [
    (5.9, "number"),
    (0.9, "number"),
    (5.0, "number"),
    (True, "boolean"),
    ("5", "string"),
    (HOSTILE, "string"),
    ([5], "array"),
]


@pytest.mark.parametrize(
    ("where", "locate", "field"), COUNTS, ids=lambda x: x if isinstance(x, str) else ""
)
@pytest.mark.parametrize(("value", "kind"), NOT_A_COUNT, ids=repr)
def test_a_count_that_is_not_an_integer_is_refused_by_its_type(
    where: str, locate: Locate, field: str, value: object, kind: str
) -> None:
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_dict(at(locate, field, value))
    message = str(refused.value)
    assert f"{where}: {field!r} is a JSON {kind}, not an integer" in message
    # Said once: the response's own `try` no longer prefixes it a second time.
    assert message.count(where) == 1
    assert HOSTILE not in message


@pytest.mark.parametrize("field", ["cache_read_tokens", "cache_write_tokens"])
def test_a_null_cache_count_is_refused_and_an_absent_one_is_zero(field: str) -> None:
    """`or 0` read `null` as 0. No writer ever wrote `null` here: the key is
    written only when the count is not zero, and no migration touches usage."""
    with pytest.raises(DocumentRefusedError, match=f"'{field}' is a JSON null"):
        run_from_dict(at(target_tokens, field, None))
    document = run_to_dict(a_run())
    del target_tokens(document)[field]
    assert getattr(run_from_dict(document).usage.target.tokens, field) == 0  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Flags written only when true
# --------------------------------------------------------------------------- #

FLAGS: list[tuple[str, Locate, str]] = [
    ("case result", canary_case, "canary"),
    ("verdict", first_verdict, "judged"),
    ("recorded response", first_answer, "withheld"),
    ("recorded response", first_answer, "oversize"),
]

NOT_A_BOOLEAN: list[tuple[object, str]] = [
    ("false", "string"),
    ("", "string"),
    (0, "number"),
    (1, "number"),
    (None, "null"),
    ([0], "array"),
]


@pytest.mark.parametrize(
    ("where", "locate", "field"), FLAGS, ids=lambda x: x if isinstance(x, str) else ""
)
@pytest.mark.parametrize(("value", "kind"), NOT_A_BOOLEAN, ids=repr)
def test_a_flag_that_is_not_a_boolean_is_refused(
    where: str, locate: Locate, field: str, value: object, kind: str
) -> None:
    """`"false"` read a plain case as a canary, a deterministic check as
    judged; `null` read a canary as a plain case."""
    with pytest.raises(DocumentRefusedError) as refused:
        run_from_dict(at(locate, field, value))
    assert f"{where}: {field!r} is a JSON {kind}, not a boolean" in str(refused.value)


def test_flags_read_as_written() -> None:
    run = run_from_dict(run_to_dict(a_run()))
    assert [case.canary for case in run.results] == [False, True, False]
    answer = run.results[0].responses[0]
    assert (answer.withheld, answer.oversize) == (False, False)
    assert not run.results[0].verdicts[0].judged


def test_an_artifact_withheld_flag_that_is_not_a_boolean_is_refused() -> None:
    document = run_to_dict(a_run())
    document["artifacts"] = {"prompts/a.md": {"sha": "abc", "withheld": "false"}}
    with pytest.raises(DocumentRefusedError, match="'withheld' is a JSON string"):
        run_from_dict(document)


# --------------------------------------------------------------------------- #
# The journal header
# --------------------------------------------------------------------------- #


def test_a_journal_header_declaring_recording_as_a_string_is_refused(
    tmp_path: Path,
) -> None:
    """`bool("false")` is true: a resume would have recorded the answers the
    run it continues chose not to. A journal is surveyed, not raised, so the
    refusal arrives as the pending run's reason."""
    store = FileResultStore(tmp_path)
    journal = store.open_journal(
        JournalHeader(
            tenant="acme",
            environment="test",
            suite="qa",
            config_hash="hash-a",
            cases_digest="d",
            created_at="2026-01-02T10:00:00+00:00",
            started_at="2026-01-02T10:00:00+00:00",
            digline_version="0.26.0",
            record_responses=False,
        )
    )
    written = journal.path.read_text(encoding="utf-8")
    assert written.count('"record_responses":false') == 1
    journal.path.write_text(
        written.replace('"record_responses":false', '"record_responses":"false"'),
        encoding="utf-8",
    )
    (pending,) = store.pending("acme", "qa")
    assert pending.refusal is not None
    assert "journal header: 'record_responses' is a JSON string" in pending.refusal
