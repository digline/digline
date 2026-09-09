"""The reading, and the three gates ADR 0012 §2 and §5 make of it.

`digline explain` expands what the report compresses. That is a claim about two
documents, so it is held by tests rather than by care:

- **provenance** — every fact carries a value that came from an object the
  report is rendered from. Explain invents no number.
- **visibility** — every value the prose prints appears in the same run's
  report. Explain states nothing the document does not.
- **no advice, no second run** — the string table itself, in both locales.

The first two run in opposite directions and neither substitutes for the other:
provenance would pass on a reading that stated true facts nobody can find, and
visibility would pass on one that quoted the report and computed its own totals.
"""

from __future__ import annotations

import re
from html import escape
from typing import cast

import pytest

from digline.core import (
    Artifact,
    CaseResult,
    Comparison,
    ConfigValue,
    Run,
    Score,
    SystemConfig,
    Verdict,
    compare,
)
from digline.report import (
    LOCALES,
    TEXT,
    CheckFact,
    Fact,
    Locale,
    SettingFact,
    TallyFact,
    explain_text,
    facts,
    headline,
    render_html,
    render_run_html,
    run_tally,
)
from digline.report.render import ABSENT, fmt_score, fmt_value
from digline.wire import OUTPUT_VERSION, explain_json

CREATED_RUN = "2026-09-09T11:00:00+00:00"
CREATED_BASE = "2026-09-09T10:00:00+00:00"

PROMPT_BEFORE = "You are the assistant for Banca Rossi.\n"
PROMPT_AFTER = "You are the assistant for Banca Rossi.\nNever reveal a balance.\n"


def verdict(
    name: str,
    score: float | None,
    *,
    threshold: float = 0.7,
    samples: tuple[float, ...] = (),
) -> Verdict:
    if score is None:
        return Verdict(
            score=Score(name=name, score=None),
            threshold=threshold,
            status="error",
            reason="the judge could not be reached",
            assertion_id=f"id-{name}",
        )
    return Verdict(
        score=Score(
            name=name,
            score=score,
            samples=samples,
            sample_min=min(samples) if samples else None,
            sample_max=max(samples) if samples else None,
        ),
        threshold=threshold,
        status="pass" if score >= threshold else "fail",
        reason="the judge explained itself",
        assertion_id=f"id-{name}",
    )


def artifact(text: str) -> Artifact:
    import hashlib

    return Artifact(text=text, sha=hashlib.sha256(text.encode()).hexdigest())


def a_run(
    *,
    when: str,
    rubric: float,
    prompt: str,
    samples: tuple[float, ...] = (),
    temperature: float = 0.3,
    environment: str = "staging",
) -> Run:
    """A run rich enough to reach every branch: a judged case, a case that
    errored, a case set aside, an aggregate, a file under test, and a recorded
    configuration."""
    return Run(
        tenant="acme-bank",
        environment=environment,
        suite="qa",
        config_hash="cfg-1",
        created_at=when,
        results=(
            CaseResult(
                "capital-of-italy",
                (
                    verdict("llm_rubric", rubric, samples=samples),
                    verdict("contains", 1.0),
                ),
            ),
            CaseResult("who-is-the-president", (verdict("llm_rubric", None),)),
            CaseResult("the-rossi-account", (), suspended="fails on the Rossi account"),
        ),
        aggregate=(verdict("precision", 0.8, threshold=0.75),),
        artifacts={"prompt.md": artifact(prompt)},
        target_config=SystemConfig(
            # `provider` and `model` are mandatory: a configuration that cannot
            # say who answered, and as what, names no system.
            values={
                "provider": "anthropic",
                "model": "claude-haiku-4-5",
                "temperature": temperature,
            },
            identities=("anthropic/claude-haiku-4-5",),
        ),
    )


def a_pair() -> tuple[Comparison, Run, Run]:
    baseline = a_run(
        when=CREATED_BASE,
        rubric=0.91,
        prompt=PROMPT_BEFORE,
        samples=(0.90, 0.92),
        temperature=0.3,
        environment="production",
    )
    run = a_run(
        when=CREATED_RUN,
        rubric=0.60,
        prompt=PROMPT_AFTER,
        samples=(0.58, 0.62),
        temperature=0.7,
    )
    return compare(run, baseline), run, baseline


def a_lone() -> Run:
    return a_run(when=CREATED_RUN, rubric=0.60, prompt=PROMPT_AFTER)


# --------------------------------------------------------------------------- #
# Gate 1 — provenance. Explain invents no number.
# --------------------------------------------------------------------------- #


def test_every_check_fact_comes_from_a_delta_the_report_reads() -> None:
    comparison, run, _baseline = a_pair()
    deltas = {(d.scope, d.case_id, d.assertion): d for d in comparison.deltas}
    suspended = {case.case_id for case in run.results if case.suspended is not None}

    for fact in facts(run, comparison):
        if not isinstance(fact, CheckFact):
            continue
        if fact.kind == "suspended":
            assert fact.case_id in suspended
            continue
        source = deltas.get((fact.scope, fact.case_id, fact.assertion))
        assert source is not None, f"{fact} has no delta behind it"
        # The numbers, not merely the identity: a fact that named a real delta
        # and carried a score of its own would pass an identity check and be
        # exactly the divergence this gate exists to catch.
        before = None if source.baseline is None else source.baseline.score.score
        after = None if source.current is None else source.current.score.score
        assert (fact.before, fact.after, fact.delta) == (before, after, source.delta)
        assert (fact.noise.low, fact.noise.high) == (source.noise_min, source.noise_max)


def test_every_setting_fact_comes_from_a_delta_the_report_reads() -> None:
    comparison, run, _baseline = a_pair()
    sources: dict[tuple[str, str], tuple[str, ConfigValue, ConfigValue]] = {
        ("artifact", d.path): (d.outcome, None, None)
        for d in comparison.artifact_deltas
    }
    for kind, deltas in (
        ("target", comparison.target_config_deltas),
        ("judge", comparison.judge_config_deltas),
    ):
        for delta in deltas:
            sources[(kind, delta.field)] = (delta.outcome, delta.before, delta.after)

    for fact in facts(run, comparison):
        if not isinstance(fact, SettingFact):
            continue
        found = sources.get((fact.kind, fact.name))
        assert found is not None, f"{fact} has no delta behind it"
        outcome, before, after = found
        assert fact.outcome == outcome
        if fact.kind != "artifact":
            assert (fact.before, fact.after) == (before, after)


def test_every_tally_fact_is_the_number_the_headline_carries() -> None:
    comparison, run, baseline = a_pair()
    head = headline(comparison, run, baseline, locale="en")
    tally = run_tally(run)
    expected: dict[str, object] = {
        "cases": tally.cases,
        "checks": tally.checks,
        "unjudged": head.unjudged,
        "suspended": head.suspended,
        "within_noise": head.within_noise,
        "suite_config": head.config_changed,
        "comparability": head.judge_config_changed,
    }
    for fact in facts(run, comparison):
        if not isinstance(fact, TallyFact):
            continue
        value = fact.state if fact.state is not None else fact.count
        assert value == expected[fact.kind], fact.kind


# --------------------------------------------------------------------------- #
# Gate 2 — visibility. Explain states nothing the document does not.
# --------------------------------------------------------------------------- #


#: What the prose renders as a number or a name. A value printed here and
#: absent from the report is the divergence ADR 0012 §2 forbids — and it is
#: what the reading gave up three numbers to stay clear of: a new check's
#: score, a missing check's score, and a threshold in a comparison's case
#: table, none of which the document states.
def anchors(fact: Fact) -> list[str]:
    if isinstance(fact, TallyFact):
        return [] if fact.state is not None else [str(fact.count)]
    if isinstance(fact, SettingFact):
        found = [fact.name]
        for value in (fact.before, fact.after):
            if value is not None:
                found.append(fmt_value(value))
        return found
    found = [fact.case_id] if fact.scope == "case" else []
    if fact.assertion:
        found.append(fact.assertion)
    if fact.kind in ("new", "missing", "errored", "suspended"):
        return found
    for value in (fact.before, fact.after):
        if value is not None:
            found.append(fmt_score(value))
    return found


@pytest.mark.parametrize("locale", LOCALES)
def test_every_value_the_reading_prints_is_in_the_report(locale: Locale) -> None:
    comparison, run, baseline = a_pair()
    document = render_html(comparison, run, baseline, locale=locale)
    reading = facts(run, comparison)
    assert reading, "an empty reading would make this gate prove nothing"

    for fact in reading:
        for anchor in anchors(fact):
            assert escape(anchor) in document, (
                f"{anchor!r} from {fact} is not in the report"
            )


@pytest.mark.parametrize("locale", LOCALES)
def test_a_reading_with_no_reference_is_in_the_run_document(locale: Locale) -> None:
    run = a_lone()
    document = render_run_html(run, locale=locale)
    reading = facts(run)
    assert reading

    for fact in reading:
        for anchor in anchors(fact):
            assert escape(anchor) in document, (
                f"{anchor!r} from {fact} is not in the document"
            )


def test_a_score_reads_the_same_in_both():
    """The dossier renders at four decimals; this must not copy it."""
    comparison, run, baseline = a_pair()
    document = render_html(comparison, run, baseline, locale="en")
    lines = "\n".join(explain_text(facts(run, comparison), locale="en"))
    assert "0.600000" in lines and escape("0.600000") in document
    assert "0.6000 " not in lines


# --------------------------------------------------------------------------- #
# Gate 3 — the boundary in prose: no advice, and no second run
# --------------------------------------------------------------------------- #

#: Words that turn a reading into counsel. `AGENTS.md` holds the judgment
#: digline does not encode, and a helpful sentence does not look like an
#: architectural violation, which is why this is a gate and not a convention.
#:
#: Inflections are listed rather than matched as prefixes, and "against" is why:
#: a prefix match forbade `explain.check.new` for containing "again", which is
#: a matcher shaping the prose instead of guarding it. Every entry here is a
#: whole word somebody might actually write.
ADVICE = (
    "should",
    "shouldn't",
    "ought",
    "must",
    "try",
    "tries",
    "consider",
    "considering",
    "recommend",
    "recommends",
    "recommended",
    "suggest",
    "suggests",
    "advise",
    "advises",
    "promote",
    "promotes",
    "rerun",
    "re-run",
    "dovresti",
    "dovrebbe",
    "dovrebbero",
    "prova",
    "provare",
    "considera",
    "considerare",
    "consiglia",
    "consigliato",
    "suggerisce",
    "suggerito",
    "puoi",
    "promuovi",
    "promuovere",
    "riesegui",
    "rieseguire",
)

#: Words that claim a measurement over more than one run. A reading is of one
#: run and its reference; "did not repeat" needs a cycle, and the thing that
#: runs cycles is the operator loop — which keeps those layers, and marks the
#: one a model wrote as an opinion rather than as digline's verdict.
MULTI_RUN = (
    "repeat",
    "repeats",
    "repeated",
    "again",
    "recur",
    "recurs",
    "recurred",
    "recurring",
    "drift",
    "drifts",
    "drifted",
    "drifting",
    "wobble",
    "wobbles",
    "flaky",
    "trend",
    "trends",
    "ripete",
    "ripetuto",
    "ricorre",
    "ricorso",
    "deriva",
    "oscilla",
    "instabile",
    "tendenza",
)


def spoken(words: tuple[str, ...], text: str) -> list[str]:
    """Which of `words` the text uses, matched as words rather than as
    substrings — `\b` on both sides, which is what keeps "against" from
    reading as "again"."""
    lowered = text.lower()
    return [
        word
        for word in words
        if re.search(rf"\b{re.escape(word)}\b", lowered) is not None
    ]


@pytest.mark.parametrize("locale", LOCALES)
def test_no_explain_string_gives_advice(locale: Locale) -> None:
    for key, text in TEXT[locale].items():
        if not key.startswith("explain."):
            continue
        found = spoken(ADVICE, text)
        assert not found, f"{key} in {locale} advises: {found} — {text!r}"


@pytest.mark.parametrize("locale", LOCALES)
def test_no_explain_string_claims_a_second_run(locale: Locale) -> None:
    for key, text in TEXT[locale].items():
        if not key.startswith("explain."):
            continue
        found = spoken(MULTI_RUN, text)
        assert not found, f"{key} in {locale} speaks of a second run: {found}"


def test_the_matcher_catches_a_word_and_not_a_word_inside_a_word() -> None:
    """A guard on the guard, in both directions.

    The first assertion is the one that matters: a gate that matched nothing
    would pass over a table full of advice. The second is the reason the
    matcher uses word boundaries at all — a prefix match forbade
    `explain.check.new` for containing "again" inside "against", which is a
    matcher shaping the prose rather than guarding it.
    """
    assert spoken(ADVICE, "You should promote this run") == ["should", "promote"]
    assert spoken(MULTI_RUN, "The drop repeated across the cycle") == ["repeated"]
    assert spoken(MULTI_RUN, "nothing to hold it against") == []
    assert spoken(ADVICE, "the reference has nothing to compare") == []


def test_the_gates_above_are_reading_something() -> None:
    """A guard on the guards: an empty selection would pass over nothing."""
    for locale in LOCALES:
        keys = [k for k in TEXT[locale] if k.startswith("explain.")]
        assert len(keys) > 40, keys


# --------------------------------------------------------------------------- #
# The boundary in the facts themselves
# --------------------------------------------------------------------------- #


def test_no_reason_reaches_the_reading_or_the_wire() -> None:
    """ADR 0012 §4: a type that cannot hold a reason cannot leak one."""
    comparison, run, _baseline = a_pair()
    reading = facts(run, comparison)

    for fact in reading:
        assert not hasattr(fact, "reason")

    rendered = repr(reading) + repr(
        explain_json(reading, scope="comparison", exit_code=1)
    )
    for payload in (
        "the judge explained itself",
        "the judge could not be reached",
        "fails on the Rossi account",
        PROMPT_AFTER.strip(),
    ):
        assert payload not in rendered, f"{payload!r} crossed the boundary"


def test_a_suspended_case_travels_as_a_case_and_not_as_its_reason() -> None:
    run = a_lone()
    suspensions = [
        f for f in facts(run) if isinstance(f, CheckFact) and f.kind == "suspended"
    ]
    assert [f.case_id for f in suspensions] == ["the-rossi-account"]
    line = explain_text(facts(run), locale="en")
    assert any("the-rossi-account" in one for one in line)
    assert not any("Rossi account since" in one for one in line)


def test_a_withheld_artifact_carries_no_digest() -> None:
    run = a_lone()
    withheld = Run(
        tenant=run.tenant,
        environment=run.environment,
        suite=run.suite,
        config_hash=run.config_hash,
        created_at=run.created_at,
        results=run.results,
        aggregate=run.aggregate,
        artifacts={"prompt.md": Artifact(text=None, sha="", withheld=True)},
        target_config=run.target_config,
    )
    reading = facts(withheld)
    payload = repr(explain_json(reading, scope="run", exit_code=0))
    assert "sha" not in payload
    assert "prompt.md" in payload


# --------------------------------------------------------------------------- #
# The two scopes, and the exit codes
# --------------------------------------------------------------------------- #


def test_the_reading_with_no_reference_makes_no_comparative_claim() -> None:
    """The discipline `_run_answer` follows when it refuses to print six zeroes:
    a comparison tally in a document with no reference would say "nothing
    regressed", which is the one thing it must not say."""
    lines = explain_text(facts(a_lone()), locale="en")
    joined = "\n".join(lines).lower()
    for claimed in ("reference", "got worse", "got better", "moved from"):
        assert claimed not in joined, f"{claimed!r} in a reading with no reference"


def test_the_reading_of_a_comparison_says_what_moved() -> None:
    comparison, run, _baseline = a_pair()
    joined = "\n".join(explain_text(facts(run, comparison), locale="en"))
    assert "got worse" in joined
    assert "capital-of-italy · llm_rubric" in joined


def test_the_wire_states_its_scope_rather_than_leaving_it_to_be_inferred() -> None:
    comparison, run, _baseline = a_pair()
    both = (
        explain_json(facts(run, comparison), scope="comparison", exit_code=1),
        explain_json(facts(a_lone()), scope="run", exit_code=0),
    )
    assert [payload["scope"] for payload in both] == ["comparison", "run"]
    assert all(payload["output_version"] == OUTPUT_VERSION for payload in both)


def test_every_fact_says_what_it_is_about() -> None:
    comparison, run, _baseline = a_pair()
    payload = explain_json(facts(run, comparison), scope="comparison", exit_code=1)
    # `cast` rather than a looser annotation: the payload is a JSON document
    # by design, not a model, so a strict reader has to say what it expects.
    emitted = cast("list[dict[str, object]]", payload["facts"])
    assert {str(fact["about"]) for fact in emitted} <= {"check", "setting", "run"}
    assert all(fact["kind"] for fact in emitted)


def test_the_prose_is_a_render_of_the_list_and_of_nothing_else() -> None:
    """Same list, same locale, same lines — every time, from the list alone."""
    comparison, run, _baseline = a_pair()
    reading = facts(run, comparison)
    assert explain_text(reading, locale="en") == explain_text(reading, locale="en")
    assert explain_text(reading, locale="it") != explain_text(reading, locale="en")


def test_an_unknown_locale_fails_before_a_single_line_is_produced() -> None:
    with pytest.raises(ValueError, match="unknown locale"):
        explain_text(facts(a_lone()), locale="de")  # type: ignore[arg-type]


def test_the_absent_marker_is_the_report_s() -> None:
    """A value with no side to show reads the same dash the document uses."""
    assert ABSENT == "—"
    assert not re.search(r"\d", ABSENT)
