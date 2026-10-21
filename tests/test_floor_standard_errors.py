"""ADR 0050, the second of *Five things this carries*: a declared floor width.

Phase 1 of #496. `floor_standard_errors` is how wide a dispersion-based floor
is, in standard errors of the mean, and the author of a check declares it or
leaves it out. In this phase the declaration exists, travels in the document,
joins `config_hash` where it is declared, and **moves nothing**: no floor reads
it yet, and `compare()` decides every movement as it did.

Three tests here guard the two ways the field could have done damage on the day
it landed, and each is the shape of a mistake that was nearly made:

- **`config_hash` must not move for a suite that declares nothing.** A field
  that entered every suite's hash would unpromote every baseline and rename
  every stored run (ADR 0014 §1). The hashes below are what `main` computed at
  8c59027, before the field existed.
- **`identity` must not move when the width moves.** `compare()` pairs on it,
  so a width inside it would turn a changed width into a `new` plus a
  `missing`. `Repeated` is the trap inside the trap: its identity fingerprints
  `inner` whole, so the field has to be kept out of it there as well, and an
  undeclared width must leave a `Repeated` check's identity exactly as it was.
- **A boolean is not a width.** `isinstance(True, int)` is true, so without its
  refusal `floor_standard_errors=True` would mean one standard error in silence.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from digline.core import (
    Accuracy,
    AssertionBase,
    CaseResult,
    Comparison,
    Contains,
    CostBudget,
    EvaluatorInputs,
    FromAutoevals,
    Regex,
    Repeated,
    Run,
    Score,
    Verdict,
    combine_samples,
    compare,
    error_verdict,
    redact,
    run_from_json,
    run_to_json,
)
from digline.core.refused import RefusedError
from digline.core.run import SCHEMA_VERSION, config_hash, pricing_digest, run_from_dict
from digline.host.toml_suite import AGGREGATES, ASSERTIONS, load_toml_suite
from digline.report import Locale, render_html
from digline.report.render import rule_lines
from digline.run import Case, Suite
from digline.store.migrate import upgrade_document

FIELD = "floor_standard_errors"
CREATED = "2026-01-01T00:00:00+00:00"


def make_run(verdicts: Sequence[Verdict], *, config: str = "h") -> Run:
    return Run(
        tenant="acme",
        environment="staging",
        suite="s",
        config_hash=config,
        created_at=CREATED,
        results=(CaseResult(case_id="c1", verdicts=tuple(verdicts)),),
    )


def judged(assertion: Any, output: str = "hello there") -> Verdict:
    """What the assertion itself returns, so its own constructor is tested."""
    verdict = assertion(EvaluatorInputs(output=output))
    assert isinstance(verdict, Verdict)
    return verdict


# --------------------------------------------------------------------------- #
# Where the field is declared
# --------------------------------------------------------------------------- #


def test_every_check_about_a_case_declares_it_and_no_aggregate_does() -> None:
    per_case = [*ASSERTIONS.values(), FromAutoevals]
    missing = [
        cls.__name__ for cls in per_case if FIELD not in {f.name for f in fields(cls)}
    ]
    assert not missing, f"no `{FIELD}` field on: {missing}"
    # Aggregates are outside ADR 0050 (its *Context*, and the second decision).
    on_aggregates = [
        cls.__name__
        for cls in AGGREGATES.values()
        if FIELD in {f.name for f in fields(cls)}
    ]
    assert not on_aggregates


def test_it_is_outside_identity_on_every_class_that_declares_it() -> None:
    assert FIELD in AssertionBase.IDENTITY_EXCLUDED
    assert FIELD in FromAutoevals.IDENTITY_EXCLUDED


def test_repeated_copies_it_from_inner_and_takes_none_of_its_own() -> None:
    inner = Contains(needle="hello", floor_standard_errors=2)
    wrapped = Repeated(inner=inner, samples=3, min_agreement="2/3")
    assert wrapped.floor_standard_errors == 2
    with pytest.raises(TypeError):
        Repeated(
            inner=inner,
            samples=3,
            min_agreement="2/3",
            floor_standard_errors=1,  # pyright: ignore[reportCallIssue]
        )


# --------------------------------------------------------------------------- #
# identity does not move, and the verdicts stay paired
# --------------------------------------------------------------------------- #


def test_identity_does_not_move_when_the_width_moves() -> None:
    undeclared = Contains(needle="hello")
    one = Contains(needle="hello", floor_standard_errors=1)
    two = Contains(needle="hello", floor_standard_errors=2)
    assert undeclared.identity == one.identity == two.identity == "486b53ae32469ecf"


def test_a_repeated_checks_identity_does_not_move_either() -> None:
    """`Repeated` fingerprints `inner` whole, through `asdict`, so a width on
    `inner` would reach its identity unless kept out there too — and the field
    merely existing, at `None`, would change every `Repeated` identity in every
    stored baseline. `c73e8b47d3e65471` is this check's identity on `main` at
    8c59027."""

    def wrapped(width: float | None = None) -> Repeated:
        inner = Contains(needle="hello", tolerance=0.05, floor_standard_errors=width)
        return Repeated(inner=inner, samples=3, min_agreement="2/3")

    assert wrapped().identity == "c73e8b47d3e65471"
    assert wrapped(1).identity == "c73e8b47d3e65471"
    assert wrapped(2).identity == "c73e8b47d3e65471"


def test_a_moved_width_pairs_the_verdicts_instead_of_a_new_and_a_missing() -> None:
    before = judged(Contains(needle="hello", floor_standard_errors=1))
    now = judged(Contains(needle="hello", floor_standard_errors=2))
    deltas = compare(make_run([now]), make_run([before])).deltas
    assert [(d.scope, d.outcome) for d in deltas] == [("case", "unchanged")]
    assert deltas[0].current is not None and deltas[0].baseline is not None


# --------------------------------------------------------------------------- #
# config_hash: it moves where a width is declared, and nowhere else
# --------------------------------------------------------------------------- #

CHECKS = (
    Contains(needle="hello"),
    Regex(pattern="^h", tolerance=0.1),
    CostBudget(max_usd=0.02, tolerance=0.05),
)


def undeclared() -> tuple[Any, ...]:
    """`CHECKS`, with `None` passed for the width rather than left out."""
    return (
        Contains(needle="hello", floor_standard_errors=None),
        Regex(pattern="^h", tolerance=0.1, floor_standard_errors=None),
        CostBudget(max_usd=0.02, tolerance=0.05, floor_standard_errors=None),
    )


def test_config_hash_does_not_move_for_a_suite_that_declares_nothing() -> None:
    """The damage ADR 0014 §1 describes, guarded: every baseline unpromotable
    and every run renamed on the day of the release. The literals are what
    `main` computed at 8c59027, before the field existed. `None` passed
    explicitly is the same declaration as leaving it out."""
    for checks in (CHECKS, undeclared()):
        assert config_hash(checks) == "18d4f01827c1c0d4"
        assert config_hash(checks, samples=5, min_agreement=0.6) == "f30479048c7413d9"
        gate = Accuracy(over="check", threshold="1/2", tolerance=0.0)
        assert config_hash(checks, run_assertions=(gate,)) == "d380809b62635dcb"
        price = pricing_digest("m", {"input": 1.0, "output": 2.0})
        assert config_hash(checks, pricing=price) == "23505e5ab469fa01"
    inner = Contains(needle="hello", tolerance=0.05, floor_standard_errors=None)
    repeated = Repeated(inner=inner, samples=3, min_agreement="2/3")
    assert config_hash((repeated,)) == "cdbecb760efae9f1"


def test_config_hash_moves_when_the_width_moves() -> None:
    def suite_hash(width: float | None) -> str:
        return config_hash(
            (Contains(needle="hello", floor_standard_errors=width), *CHECKS[1:])
        )

    hashes = {suite_hash(None), suite_hash(1), suite_hash(2), suite_hash(2.5)}
    assert len(hashes) == 4
    assert suite_hash(None) == "18d4f01827c1c0d4"


def test_config_hash_tells_a_width_from_a_price() -> None:
    """Both are appended only where declared; neither may read as the other."""
    price = pricing_digest("m", {"input": 1.0, "output": 2.0})
    declared = (Contains(needle="hello", floor_standard_errors=2), *CHECKS[1:])
    assert config_hash(declared) != config_hash(CHECKS, pricing=price)
    assert config_hash(declared, pricing=price) not in {
        config_hash(declared),
        config_hash(CHECKS, pricing=price),
    }


def test_the_suite_hash_reads_the_width_through_repeated() -> None:
    def hashed(width: float | None) -> str:
        inner = Contains(needle="hello", floor_standard_errors=width)
        return config_hash((Repeated(inner=inner, samples=3, min_agreement="2/3"),))

    assert hashed(None) != hashed(2)


# --------------------------------------------------------------------------- #
# What is refused
# --------------------------------------------------------------------------- #

REFUSED: tuple[object, ...] = (
    0,
    0.0,
    -1,
    -0.5,
    math.nan,
    math.inf,
    -math.inf,
    True,
    False,
)


@pytest.mark.parametrize("width", REFUSED, ids=repr)
def test_a_suite_refuses_a_width_that_is_not_a_positive_finite_number(
    width: object,
) -> None:
    with pytest.raises(RefusedError, match=FIELD):
        Suite(
            tenant="acme",
            environment="staging",
            name="s",
            assertions=[Contains(needle="hello", floor_standard_errors=width)],  # pyright: ignore[reportArgumentType]
            cases=[Case(id="one")],
        )


@pytest.mark.parametrize("width", REFUSED, ids=repr)
def test_config_hash_refuses_it_too(width: object) -> None:
    with pytest.raises(ValueError, match=FIELD):
        config_hash((Contains(needle="hello", floor_standard_errors=width),))  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("width", REFUSED, ids=repr)
def test_a_verdict_refuses_it_too(width: object) -> None:
    with pytest.raises(ValueError, match=FIELD):
        Verdict(
            score=Score(name="contains", score=1.0),
            threshold=1.0,
            status="pass",
            reason="found",
            assertion_id="id",
            floor_standard_errors=width,  # pyright: ignore[reportArgumentType]
        )


def test_an_integer_width_is_a_width() -> None:
    verdict = judged(Contains(needle="hello", floor_standard_errors=2))
    assert verdict.floor_standard_errors == 2.0


# --------------------------------------------------------------------------- #
# The document: present where declared, absent where not, never null
# --------------------------------------------------------------------------- #


def test_the_width_round_trips_through_the_document() -> None:
    run = make_run([judged(Contains(needle="hello", floor_standard_errors=2))])
    text = run_to_json(run)
    assert json.loads(text)["results"][0]["verdicts"][0][FIELD] == 2.0
    assert run_from_json(text).results[0].verdicts[0].floor_standard_errors == 2.0


def test_an_undeclared_width_writes_no_key_at_all() -> None:
    run = make_run([judged(Contains(needle="hello"))])
    verdict = json.loads(run_to_json(run))["results"][0]["verdicts"][0]
    assert FIELD not in verdict
    assert (
        run_from_json(run_to_json(run)).results[0].verdicts[0].floor_standard_errors
        is None
    )


@pytest.mark.parametrize("written", [None, True, 0, -1, "2"], ids=repr)
def test_a_document_that_writes_it_wrongly_is_refused(written: object) -> None:
    """Absent is the only way to say *not declared*. A `null` is a value where
    there is none, and the rest are not widths."""
    document = json.loads(run_to_json(make_run([judged(Contains(needle="hello"))])))
    document["results"][0]["verdicts"][0][FIELD] = written
    with pytest.raises(ValueError):
        run_from_dict(document)


def test_redaction_keeps_the_width() -> None:
    """A declaration like a tolerance, so it crosses like one (ADR 0014 §1,
    third condition, answered in ADR 0050)."""
    run = make_run([judged(Contains(needle="hello", floor_standard_errors=2))])
    assert redact(run).results[0].verdicts[0].floor_standard_errors == 2.0


def test_an_errored_verdict_carries_the_width() -> None:
    verdict = error_verdict(Contains(needle="hello", floor_standard_errors=2), "boom")
    assert verdict.floor_standard_errors == 2.0


def test_the_fold_carries_the_width() -> None:
    check = Contains(needle="hello", floor_standard_errors=2)
    folded = combine_samples(
        [judged(check), judged(check, "nothing"), judged(check)], min_agreement=2 / 3
    )
    assert folded.floor_standard_errors == 2.0


def test_a_toml_suite_declares_it_as_a_key(tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_text("Answer.\n", encoding="utf-8")
    (tmp_path / "cases.json").write_text('[{"id": "one"}]', encoding="utf-8")
    (tmp_path / "suite.toml").write_text(
        "[suite]\n"
        'tenant = "acme"\nenvironment = "staging"\nname = "s"\n'
        'cases = "cases.json"\n\n'
        '[target]\ntype = "provider"\nprovider = "openai/gpt-5"\n'
        'prompt_file = "prompt.md"\nmax_tokens = 100\n\n'
        '[[assertions]]\ntype = "contains"\nneedle = "hello"\n'
        "floor_standard_errors = 2\n",
        encoding="utf-8",
    )
    suite, _target = load_toml_suite(tmp_path / "suite.toml", root=tmp_path)
    (check,) = suite.assertions
    assert getattr(check, FIELD) == 2


# --------------------------------------------------------------------------- #
# Schema 20, and the step that writes nothing
# --------------------------------------------------------------------------- #


def test_migrating_a_schema_19_document_writes_nothing() -> None:
    assert SCHEMA_VERSION == 20
    current = json.loads(run_to_json(make_run([judged(Contains(needle="hello"))])))
    at_nineteen = {**current, "schema_version": 19}
    upgraded = upgrade_document(at_nineteen)
    assert upgraded == current
    run_from_dict(upgraded)


# --------------------------------------------------------------------------- #
# compare() reads it and ignores it; the rules that moved name it
# --------------------------------------------------------------------------- #


def spread_baseline(width: float | None) -> Verdict:
    """A graded check whose baseline's samples spread, so a floor exists today."""
    check = Regex(pattern="^h", tolerance=0.0, floor_standard_errors=width)
    samples = [judged(check, "hello"), judged(check, "nope"), judged(check, "hello")]
    return combine_samples(samples, min_agreement=2 / 3)


@pytest.mark.parametrize("width", [None, 1, 2, 3.5])
def test_no_verdict_changes_whatever_the_width(width: float | None) -> None:
    """The comparison with a width declared on both sides is the comparison
    without one, field for field: the floor in this phase is the range, and the
    width is read by nothing that decides."""
    reference = compare(
        make_run([spread_baseline(None)]), make_run([spread_baseline(None)])
    )
    now = Regex(pattern="^h", tolerance=0.0, floor_standard_errors=width)
    moved = combine_samples(
        [judged(now, "hello"), judged(now, "hello"), judged(now, "hello")],
        min_agreement=2 / 3,
    )
    plain = Regex(pattern="^h", tolerance=0.0)
    moved_plain = combine_samples(
        [judged(plain, "hello"), judged(plain, "hello"), judged(plain, "hello")],
        min_agreement=2 / 3,
    )
    with_width = compare(make_run([moved]), make_run([spread_baseline(width)]))
    without = compare(make_run([moved_plain]), make_run([spread_baseline(None)]))

    def shape(c: Comparison) -> list[tuple[object, ...]]:
        return [
            (d.outcome, d.delta, d.reason, d.within_noise, d.noise_min, d.noise_max)
            for d in c.deltas
        ]

    assert shape(with_width) == shape(without)
    assert reference.deltas[0].outcome == "unchanged"


@pytest.mark.parametrize(
    ("before_width", "after_width", "direction", "en", "it"),
    [
        (None, 2, "loosened", "(looser)", "(più larga)"),
        (1, 2, "loosened", "(looser)", "(più larga)"),
        (2, 1, "tightened", "(stricter)", "(più stretta)"),
        (2, None, "tightened", "(stricter)", "(più stretta)"),
    ],
)
def test_the_rules_that_moved_name_a_declared_width_and_its_direction(
    before_width: int | None, after_width: int | None, direction: str, en: str, it: str
) -> None:
    """A wider width forgives more and is looser; a narrower one is stricter.

    A width that appears where there was none forgives more, like one that
    rose, and one that goes away forgives less, like one that fell: the width
    is one of the rules a movement is read against, and a changed tolerance
    has carried a direction all along. (ADR 0050, the passenger rule, amended
    2026-10-21)
    """
    before = judged(Contains(needle="hello", floor_standard_errors=before_width))
    now = judged(Contains(needle="hello", floor_standard_errors=after_width))
    comparison = compare(make_run([now], config="b"), make_run([before], config="a"))
    (row,) = comparison.suite_deltas
    assert (row.field, row.outcome, row.direction, row.before, row.after) == (
        FIELD,
        "changed",
        direction,
        None if before_width is None else float(before_width),
        None if after_width is None else float(after_width),
    )
    words: dict[Locale, str] = {"en": en, "it": it}
    for locale, word in words.items():
        (line,) = rule_lines(comparison, locale=locale)
        assert "contains" in line
        assert line.endswith(word)


def test_a_width_moved_on_one_check_names_that_check_only() -> None:
    before = [
        judged(Contains(needle="hello", floor_standard_errors=1)),
        judged(Regex(pattern="^h")),
    ]
    now = [
        judged(Contains(needle="hello", floor_standard_errors=2)),
        judged(Regex(pattern="^h")),
    ]
    comparison = compare(make_run(now, config="b"), make_run(before, config="a"))
    assert [(r.rule, r.field, r.before, r.after) for r in comparison.suite_deltas] == [
        ("contains", FIELD, 1.0, 2.0)
    ]


def test_an_unchanged_width_names_nothing() -> None:
    check = Contains(needle="hello", floor_standard_errors=2)
    comparison = compare(make_run([judged(check)]), make_run([judged(check)]))
    assert comparison.suite_deltas == ()


def test_the_report_renders_a_moved_width_in_both_locales() -> None:
    before = make_run([judged(Contains(needle="hello"))], config="a")
    now = make_run(
        [judged(Contains(needle="hello", floor_standard_errors=2))], config="b"
    )
    comparison = compare(now, before)
    for locale in ("en", "it"):
        page = render_html(comparison, now, before, locale=locale, declared=None)
        assert "contains" in page
