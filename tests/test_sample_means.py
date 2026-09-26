"""The fold of folds, stamped and left out of shape. (ADR 0024 §6.5)

A `Score` whose samples are means of judgements, not judgements, carries
`sample_means`. It is stamped in `combine_samples`, on the mechanism, because
the list of cases that produce such a fold was wrong three times before it was
measured. The shape reading leaves those verdicts out and counts them, and on
the reference side it pairs by identity: the rule errs toward leaving a verdict
out, never toward misreading one.

The cross-version tests at the bottom run 0.14.1's own source, taken from its
tag, and are skipped where the tags are absent.
"""

from __future__ import annotations

import io
import itertools
import json
import os
import subprocess
import sys
import tarfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import stamp_journal_format

from digline.core import (
    CaseResult,
    JudgeReply,
    LlmRubric,
    Repeated,
    Run,
    Score,
    Verdict,
    combine_samples,
    compare,
    redact,
    run_from_json,
    run_to_json,
    without_responses,
)
from digline.core.run import SCHEMA_VERSION, run_to_dict
from digline.host import measure, prepare
from digline.report import explain_text, facts, headline, shape
from digline.run import Case, Response, Suite, execute, rejudge
from digline.store import FileResultStore, journal_key
from digline.store.migrate import upgrade_document
from digline.wire import compare_json

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"


def alternating() -> LlmRubric:
    """A judge that has collapsed to binary and cannot make up its mind: the one
    picture shape exists to catch, and the one a fold of folds hides."""
    scores: Iterator[float] = itertools.cycle([0.0, 1.0])
    return LlmRubric(
        rubric="right?",
        judge=lambda prompt: JudgeReply(score=next(scores), reason=prompt[:1]),
        threshold=0.5,
        tolerance=0.05,
    )


def twice(inner: Any) -> Repeated:
    return Repeated(inner=inner, samples=2, min_agreement="1/2")


def answering(case: Case) -> Response:
    return Response(output="Rome", input="capital?")


def suite(assertion: Any, samples: int = 1, **extra: Any) -> Suite:
    fields: dict[str, Any] = {
        "tenant": "acme",
        "environment": "dev",
        "name": "qa",
        "assertions": [assertion],
        "cases": [Case(id="one"), Case(id="two")],
        "samples": samples,
    }
    if samples > 1:
        fields["min_agreement"] = f"1/{samples}"
    fields.update(extra)
    return Suite(**fields)


def stored(declared: Suite, **extra: Any) -> Verdict:
    return (
        execute(declared, answering, created_at=CREATED, **extra).results[0].verdicts[0]
    )


# --------------------------------------------------------------------------- #
# Where it is stamped: on the mechanism, measured through the driver
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("declared", "samples", "means"),
    [
        (lambda: alternating(), 2, False),
        (lambda: twice(alternating()), 1, False),
        (lambda: twice(alternating()), 2, True),
        (lambda: twice(twice(alternating())), 1, True),
    ],
    ids=["check-sampled", "repeated-unsampled", "repeated-sampled", "nested-unsampled"],
)
def test_the_stamp_follows_the_mechanism_not_a_list_of_cases(
    declared: Any, samples: int, means: bool
) -> None:
    """The table in §6.5, row for row. The nested row is the one §6.2's
    amendment called exact."""
    verdict = stored(suite(declared(), samples=samples))
    assert verdict.score.sample_means is means
    assert verdict.score.samples == ((0.5, 0.5) if means else (0.0, 1.0))


def test_a_judge_samples_replay_of_a_repeated_check_is_the_third_road() -> None:
    """`fold_judgements` records each answer's first judgement, and for a
    `Repeated` check that judgement is already a fold."""
    declared = suite(twice(alternating()), samples=2, record_responses=True)
    source = execute(declared, answering, created_at=CREATED)
    replay = rejudge(declared, source, key="k", created_at=LATER, judge_samples=2)
    verdict = replay.results[0].verdicts[0]
    assert "judge_samples" in verdict.score.metadata
    assert verdict.score.sample_means


def test_a_fold_of_one_is_that_verdict_and_an_errored_fold_is_not_stamped() -> None:
    single = stored(suite(twice(alternating())))
    assert combine_samples([single], min_agreement=1.0) is single
    errored = Verdict(
        score=Score(name="llm_rubric"),
        threshold=0.5,
        status="error",
        reason="mute",
        assertion_id=single.assertion_id,
    )
    folded = combine_samples([errored, errored], min_agreement=1.0)
    assert not folded.score.sample_means and not folded.score.samples


def test_the_stamp_needs_samples_to_qualify() -> None:
    with pytest.raises(ValueError, match="no samples"):
        Score(name="x", score=0.5, sample_means=True)


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #


def test_it_is_written_only_when_true_beside_samples() -> None:
    folded = run_to_dict(
        execute(suite(twice(alternating()), samples=2), answering, created_at=CREATED)
    )
    plain = run_to_json(
        execute(suite(twice(alternating())), answering, created_at=CREATED)
    )
    verdict = folded["results"][0]["verdicts"][0]  # type: ignore[index]
    assert verdict["sample_means"] is True
    assert "sample_means" not in plain


def test_it_reads_back() -> None:
    run = execute(suite(twice(alternating()), samples=2), answering, created_at=CREATED)
    again = run_from_json(run_to_json(run))
    assert all(v.score.sample_means for c in again.results for v in c.verdicts)


@pytest.mark.parametrize("value", [False, "true", 1, None], ids=str)
def test_anything_but_true_is_refused_by_name(value: object) -> None:
    run = execute(suite(twice(alternating()), samples=2), answering, created_at=CREATED)
    document = json.loads(run_to_json(run))
    document["results"][0]["verdicts"][0]["sample_means"] = value
    with pytest.raises(ValueError, match="'sample_means' is written only as true"):
        run_from_json(json.dumps(document))


# --------------------------------------------------------------------------- #
# The passenger rule (ADR 0014 §1)
# --------------------------------------------------------------------------- #


def test_it_leaves_identity_and_config_hash_alone() -> None:
    declared = suite(twice(alternating()), samples=2)
    run = execute(declared, answering, created_at=CREATED)
    assert run.config_hash == declared.config_hash()
    assert run.results[0].verdicts[0].assertion_id == twice(alternating()).identity


def test_it_crosses_with_the_samples_it_qualifies() -> None:
    """Kept by `redact()` and by promotion: a baseline is what this reading
    reads."""
    run = execute(suite(twice(alternating()), samples=2), answering, created_at=CREATED)
    for kept in (redact(run), without_responses(run)):
        assert all(v.score.sample_means for c in kept.results for v in c.verdicts)
    assert '"sample_means": true' in run_to_json(redact(run))


def test_the_step_writes_nothing() -> None:
    run = execute(suite(twice(alternating()), samples=2), answering, created_at=CREATED)
    current = run_to_dict(run)
    unstamped = json.loads(json.dumps(current))
    for case in unstamped["results"]:
        for verdict in case["verdicts"]:
            del verdict["sample_means"]
    # 13 -> 14 writes nothing either (ADR 0025 §7), so a schema-12 document
    # still arrives here unchanged but for its version.
    # 16 -> 17 writes only onto a calibration band, and this run has none.
    assert SCHEMA_VERSION == 17
    assert upgrade_document({**unstamped, "schema_version": 12}) == unstamped


# --------------------------------------------------------------------------- #
# The reading
# --------------------------------------------------------------------------- #


def as_run(verdicts: Sequence[Verdict], created_at: str) -> Run:
    return Run(
        tenant="acme",
        environment="dev",
        suite="qa",
        config_hash="h",
        created_at=created_at,
        results=tuple(CaseResult(f"c{i}", (v,)) for i, v in enumerate(verdicts)),
    )


def judged(
    samples: tuple[float, ...], *, means: bool = False, identity: str = "id-r"
) -> Verdict:
    return Verdict(
        score=Score(
            name="llm_rubric",
            score=round(sum(samples) / len(samples), 6),
            samples=samples,
            sample_min=min(samples),
            sample_max=max(samples),
            sample_means=means,
        ),
        threshold=0.5,
        status="pass",
        reason="r",
        assertion_id=identity,
        judged=True,
    )


def test_a_stamped_verdict_is_left_out_and_counted_never_read() -> None:
    """`(0.5, 0.5)` read as judgements is 0% at the extremes: the opposite of a
    judge alternating 0 and 1.

    **The second verdict is a different identity since 0.16.0**, and the change
    is worth its paragraph. This fixture used to give both verdicts the same
    `assertion_id`, one stamped and one not, and compare the run with itself —
    so once the compensation became symmetric the unstamped one was left out
    too, and the numbers read `(2, 0, 0)` instead of `(1, 2, 2)`.

    That shape cannot occur in a written document. `sample_means` is stamped in
    `combine_samples`, so within one run it is uniform for a check: every case's
    verdict of that identity is a fold or none is. The one verdict that escapes
    the stamp is an all-errored fold, and `_count` never sees an errored verdict.
    So a mixed identity means a document somebody edited — which is exactly what
    the symmetric rule is there to refuse to read.

    The fixture therefore uses two identities, which is what it was always
    about: one stamped check left out and counted, one unstamped check read.

    **That reachability was established before this fixture was touched, and
    the order is the point.** A test whose numbers move is a loosened assertion
    unless somebody first showed the old numbers described a document that
    cannot be written. Read in six months, this paragraph is the difference
    between a correction and a test quietly taught to agree with the code.
    (0.15.0 delta-pass §3)
    """
    now = as_run(
        [judged((0.5, 0.5), means=True), judged((0.0, 1.0), identity="id-other")],
        LATER,
    )
    read = {item.assertion_id: item for item in shape(compare(now, now))}
    stamped, plain = read["id-r"], read["id-other"]
    assert (plain.run.sample_means, plain.run.scores, plain.run.extremes) == (0, 2, 2)
    assert (stamped.run.sample_means, stamped.run.scores) == (1, 0)


def test_the_reference_pairs_by_identity_with_the_run() -> None:
    """A 0.14.x reference holds the fold unstamped. Where the run stamped the
    check, the reference's sampled, unstamped verdicts of that identity are left
    out and counted, not read as judgements."""
    now = as_run([judged((0.5, 0.5), means=True)] * 2, LATER)
    before = as_run([judged((0.5, 0.5))] * 2, CREATED)
    [item] = shape(compare(now, before))
    assert item.reference is not None
    assert (item.reference.sample_means, item.reference.scores) == (2, 0)


def test_a_stripped_run_stamp_is_recovered_from_the_reference() -> None:
    """The pairing, the other way round — and the half that was missing.

    The compensation was passed only on the reference branch, so a stripped
    *baseline* stamp was recovered and a stripped *run* stamp was believed.
    Measured before the fix, on this exact pair: the run side read
    `sample_means=0, scores=4, extremes=0` — four means read as judgements at 0%
    at the extremes, which is the precise opposite of a judge alternating 0 and
    1, and the forgery form of the residue ADR 0024 §6.5 declares.

    The rule is one rule and applies to both sides: err toward leaving a verdict
    out, never toward misreading one. (0.15.0 delta-pass §3)
    """
    now = as_run([judged((0.5, 0.5))] * 2, LATER)
    before = as_run([judged((0.5, 0.5), means=True)] * 2, CREATED)

    [item] = shape(compare(now, before))

    assert (item.run.sample_means, item.run.scores) == (2, 0)
    assert item.run.extremes == 0


def test_an_unstamped_run_against_an_unstamped_reference_is_still_read() -> None:
    """The residue, asserted so the fix is not read as closing more than it
    does. Where neither side stamped, nothing in the data says the samples are
    means, and the reading has no way to know — which is what ADR 0024 §6.5
    already states and what re-promotion fixes."""
    now = as_run([judged((0.5, 0.5))] * 2, LATER)
    before = as_run([judged((0.5, 0.5))] * 2, CREATED)

    [item] = shape(compare(now, before))

    assert (item.run.sample_means, item.run.scores) == (0, 4)


def test_the_pairing_touches_no_other_identity() -> None:
    now = as_run(
        [judged((0.5, 0.5), means=True), judged((0.0, 1.0), identity="id-other")],
        LATER,
    )
    before = as_run(
        [judged((0.5, 0.5)), judged((0.0, 1.0), identity="id-other")], CREATED
    )
    other = next(
        item for item in shape(compare(now, before)) if item.assertion_id == "id-other"
    )
    assert other.reference is not None
    assert (other.reference.sample_means, other.reference.extremes) == (0, 2)


def test_the_residue_is_read_as_it_always_was() -> None:
    """The one pairing the reading cannot reach, pinned so that reaching it is a
    decision: an unstamped run against an unstamped sampled reference."""
    now = as_run([judged((0.0, 1.0))], LATER)
    before = as_run([judged((0.5, 0.5))], CREATED)
    [item] = shape(compare(now, before))
    assert item.reference is not None
    assert (item.reference.sample_means, item.reference.scores) == (0, 2)


@pytest.mark.parametrize(
    ("locale", "run_says", "reference_says"),
    [
        (
            "en",
            "2 verdicts are left out: their per-judgement scores were not recorded",
            "In the reference, 2 verdicts are left out",
        ),
        (
            "it",
            "2 verdetti sono esclusi: i loro punteggi per giudizio non sono",
            "Nel riferimento, 2 verdetti sono esclusi",
        ),
    ],
)
def test_the_line_names_both_absences(
    locale: str, run_says: str, reference_says: str
) -> None:
    now = as_run([judged((0.5, 0.5), means=True)] * 2, LATER)
    before = as_run([judged((0.5, 0.5))] * 2, CREATED)
    comparison = compare(now, before)
    lines = explain_text(facts(now, comparison), locale=locale)  # type: ignore[arg-type]
    [line] = [ln for ln in lines if ln.startswith("llm_rubric:")]
    assert run_says in line and reference_says in line
    assert "0.0%" not in line


def test_the_wire_carries_the_count() -> None:
    now = as_run([judged((0.5, 0.5), means=True)], LATER)
    comparison = compare(now, now)
    head = headline(comparison, now, now, locale="en")
    [item] = compare_json(comparison, head, baseline=now, full=True)["shape"]  # type: ignore[misc]
    assert item["run"]["sample_means"] == 1  # type: ignore[index]


# --------------------------------------------------------------------------- #
# The old reader, from its tag — and why this passenger needs the bump
# --------------------------------------------------------------------------- #


def old_source(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    archive = subprocess.run(  # noqa: S603
        ["git", "archive", "v0.14.1", "src"],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        pytest.skip("v0.14.1 is not in this checkout (shallow clone, no tags)")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(tmp_path / "old", filter="data")
    return tmp_path / "old" / "src"


def run_old(source: Path, code: str, *args: str) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import digline; print(digline.__file__); " + code,
            *args,
        ],
        env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True,
        text=True,
        check=False,
    )
    # Proof the old source is what ran, not this checkout's editable install.
    assert done.stdout.startswith(str(source)), done.stdout + done.stderr
    return done


def folded_document(tmp_path: Path, schema: int) -> Path:
    written = json.loads(
        run_to_json(
            execute(
                suite(twice(alternating()), samples=2), answering, created_at=CREATED
            )
        )
    )
    written["schema_version"] = schema
    path = tmp_path / f"run-{schema}.json"
    path.write_text(json.dumps(written), encoding="utf-8")
    return path


def test_0_14_1_refuses_a_schema_13_document_on_its_version(tmp_path: Path) -> None:
    source = old_source(tmp_path)
    done = run_old(
        source,
        "import sys, digline.core as c; "
        "c.run_from_json(open(sys.argv[1], encoding='utf-8').read())",
        str(folded_document(tmp_path, 13)),
    )
    assert done.returncode != 0
    assert "schema_version 13 is not supported (expected 12)" in done.stderr, (
        done.stderr
    )


def test_without_the_bump_0_14_1_would_read_means_as_judgements(tmp_path: Path) -> None:
    """Why this passenger, unlike the nameless call, is justified by the bump's
    refusal. Stamped 12, 0.14.1 ignores the key and reads the fold as
    judgements: nothing inside the verdict refuses it by name."""
    source = old_source(tmp_path)
    done = run_old(
        source,
        "import sys, digline.core as c; "
        "r = c.run_from_json(open(sys.argv[1], encoding='utf-8').read()); "
        "print('SAMPLES', r.results[0].verdicts[0].score.samples)",
        str(folded_document(tmp_path, 12)),
    )
    assert done.returncode == 0, done.stderr
    assert "SAMPLES (0.5, 0.5)" in done.stdout, done.stdout


def test_this_reader_reads_the_fold_0_14_1_wrote_as_not_stamped(tmp_path: Path) -> None:
    """The other direction: 0.14.1's own unstamped fold migrates and reads here
    unchanged, and the pairing leaves it out against a stamped run."""
    source = old_source(tmp_path)
    write = (
        "import sys, itertools; from digline.core import *; from digline.run import *; "
        "s = itertools.cycle([0.0, 1.0]); "
        "check = Repeated(inner=LlmRubric(rubric='right?', "
        "judge=lambda p: JudgeReply(score=next(s), reason='r'), threshold=0.5, "
        "tolerance=0.05), samples=2, min_agreement='1/2'); "
        "suite = Suite(tenant='acme', environment='dev', name='qa', "
        "assertions=[check], cases=[Case(id='one'), Case(id='two')], samples=2, "
        "min_agreement='1/2'); "
        "open(sys.argv[1], 'w', encoding='utf-8').write(run_to_json(execute("
        "suite, lambda c: Response(output='Rome', input='capital?'), "
        "created_at='2026-01-01T00:00:00+00:00')))"
    )
    document = tmp_path / "old.json"
    written = run_old(source, write, str(document))
    assert written.returncode == 0, written.stderr
    old = json.loads(document.read_text(encoding="utf-8"))
    assert old["schema_version"] == 12
    assert "sample_means" not in document.read_text(encoding="utf-8")
    upgraded = upgrade_document(old)
    before = run_from_json(json.dumps(upgraded))
    assert not any(v.score.sample_means for c in before.results for v in c.verdicts)

    now = execute(suite(twice(alternating()), samples=2), answering, created_at=LATER)
    [item] = shape(compare(now, before))
    assert item.reference is not None
    assert (item.reference.sample_means, item.reference.scores) == (2, 0)


def test_a_0_14_1_resume_drops_the_stamp_and_writes_what_it_writes_anyway(
    tmp_path: Path,
) -> None:
    """A 0.14.1 reading a leg that holds a stamped verdict reads it without the
    key — the unstamped fold 0.14.1 writes for that suite anyway, which this
    reading already treats as not stamped. No new misreading.

    **Amended 2026-09-18, and again 2026-09-23.** The sentence this opened with
    — *the journal gets no refusal: its version does not move* — was true of
    schema 13 and is not true of a journal written now: ADR 0025 §11 moved the
    format to 2 for its bill line, and ADR 0029 §3 moved it to **3** so a resume
    cannot change which paths were pinned. So a current leg is refused before any
    of this is reached, and the test below asserts that first — by the number,
    which is why a journal bump lands here and will land here again. The original
    scenario is kept underneath it, on a leg stamped back to format 1: that is
    every 0.15.x journal, where the
    stamp really is dropped in silence and nothing refuses. The two assertions
    are different claims about different files, and losing the second one
    because the first became true would have retired a residue ADR 0024 §6.5
    still declares.
    """
    source = old_source(tmp_path)
    declared = suite(
        twice(alternating()),
        samples=2,
        cases=[Case(id="one"), Case(id="two"), Case(id="three")],
    )
    calls = 0

    def dying(case: Case) -> Response:
        nonlocal calls
        calls += 1
        if calls == 5:
            raise SystemExit(9)
        return answering(case)

    store = FileResultStore(tmp_path)
    prepared = prepare(
        declared, dying, now=CREATED, git_commit="deadbeef", artifacts={}
    )
    with pytest.raises(SystemExit):
        measure(declared, dying, store=store, prepared=prepared)  # pyright: ignore[reportArgumentType]
    key = journal_key(prepared.header)
    (here,) = store.pending("acme", "qa")
    assert here.key == key and not here.refusal
    assert all(r.verdicts[0].score.sample_means for r in here.done.values())

    reading = (
        "import sys; from digline.store import FileResultStore; "
        "(p,) = FileResultStore(sys.argv[1]).pending('acme', 'qa'); "
        "print('REFUSAL', repr(p.refusal)); "
        "print('SAMPLES', "
        "sorted(r.verdicts[0].score.samples for r in p.done.values()))"
    )

    # The journal as this digline writes it: format 2, refused by name, and the
    # cases are not handed over at all. This is the lock ADR 0025 §11 added.
    at_two = run_old(source, reading, str(tmp_path))
    assert at_two.returncode == 0, at_two.stderr
    assert "journal format 3" in at_two.stdout, at_two.stdout
    assert "SAMPLES []" in at_two.stdout, at_two.stdout

    # And the same journal as 0.15.x wrote one: format 1, no outer lock, the
    # stamp dropped in silence. The residue ADR 0024 §6.5 declares, still there.
    stamp_journal_format(tmp_path, "acme", "qa", key, 1)
    at_one = run_old(source, reading, str(tmp_path))
    assert at_one.returncode == 0, at_one.stderr
    assert "REFUSAL ''" in at_one.stdout, at_one.stdout
    assert "SAMPLES [(0.5, 0.5), (0.5, 0.5)]" in at_one.stdout, at_one.stdout
