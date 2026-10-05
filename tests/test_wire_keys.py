"""Every document `digline.wire` builds, held to the table in `contract.py`.

Until #312 one builder of twenty-three had its key set pinned, `compare --json`
through `COMPARE_KEYS`. Measured on 2026-10-02: 31 of the 297 literal keys in
the builders were quoted in no test, and of sixteen changes made to them —
eight renamed keys and eight keys added to eight builders — fifteen left the
whole suite green. A rename or a type change is what `OUTPUT_VERSION` exists to
announce, and nothing asked for it.

So the contract is a table a test reads (`_BASE`, `_ADDED`, `_SHAPES`), and this
module holds three things to it:

- **every document matches it**, at every level: no key it does not name, no
  required key missing, and no value of a type it does not allow, `bool` and
  `int` told apart;
- **every shape and every key in it was reached** by some fixture here, so a
  pin cannot go vacuous by belonging to a branch nobody builds;
- **`_BASE` has not moved under this `OUTPUT_VERSION`**, by its digest: an added
  key goes in `_ADDED`, a word added to a map's key vocabulary goes in
  `_ADDED_WORDS`, and anything else is a bump.

The fixtures are built from the dataclasses the builders read, directly, where
that reaches a branch more cheaply than a store would. Where a builder reads a
real comparison or a real reading, they are computed for real, because those
are what decide which branches a document takes.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from typing import Any, cast

import pytest

from digline.core import (
    Artifact,
    CalibrationBand,
    CaseResult,
    Disclosure,
    RegisterEntry,
    Run,
    RunUsage,
    Score,
    SystemConfig,
    Usage,
    Verdict,
    compare,
    diff,
    key_of,
)
from digline.core.register import RecordedOutcome
from digline.core.run import CallTotals
from digline.report import facts, headline
from digline.report.log import (
    SPREAD_ABSENCES,
    AggregateSpread,
    IdentityLog,
    IdentitySpan,
    Reference,
    Replay,
    Roll,
    Sighting,
)
from digline.run import CallPlan
from digline.store import Listing, RunRef
from digline.wire import (
    OUTPUT_VERSION,
    compare_json,
    diff_json,
    explain_json,
    log_json,
    run_document,
    run_json,
    runs_json,
)
from digline.wire.contract import (  # pyright: ignore[reportPrivateUsage]
    _ADDED,  # pyright: ignore[reportPrivateUsage]
    _ADDED_WORDS,  # pyright: ignore[reportPrivateUsage]
    _BASE,  # pyright: ignore[reportPrivateUsage]
    _BASE_DIGEST,  # pyright: ignore[reportPrivateUsage]
    _SHAPES,  # pyright: ignore[reportPrivateUsage]
    _Arr,  # pyright: ignore[reportPrivateUsage]
    _digest,  # pyright: ignore[reportPrivateUsage]
    _Key,  # pyright: ignore[reportPrivateUsage]
    _lines,  # pyright: ignore[reportPrivateUsage]
    _Map,  # pyright: ignore[reportPrivateUsage]
    _Obj,  # pyright: ignore[reportPrivateUsage]
    _OneOf,  # pyright: ignore[reportPrivateUsage]
    _Type,  # pyright: ignore[reportPrivateUsage]
)

CREATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-01-02T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# The walk
# --------------------------------------------------------------------------- #


def _kind(value: object) -> str:
    """The JSON type of a value as a parser reads it. `bool` first, because
    Python counts it as an `int`."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _fits(kind: str, allowed: _Type) -> bool:
    match allowed:
        case "any":
            return True
        case "number":
            return kind in ("number", "integer")
        case str():
            return kind == allowed
        case _Arr():
            return kind == "array"
        case _Obj() | _Map() | _OneOf():
            return kind == "object"


@dataclasses.dataclass
class Walk:
    """What one or more documents were found to be, against the table."""

    errors: list[str] = dataclasses.field(default_factory=list[str])
    reached: set[tuple[str, str]] = dataclasses.field(
        default_factory=set[tuple[str, str]]
    )
    shapes: set[str] = dataclasses.field(default_factory=set[str])

    def shape(self, document: object, name: str, at: str) -> None:
        if not isinstance(document, dict):
            self.errors.append(f"{at}: <{name}> is a {_kind(document)}, not an object")
            return
        found = cast(dict[str, object], document)
        table = _SHAPES[name]
        self.shapes.add(name)
        for key in sorted(set(found) - set(table)):
            self.errors.append(f"{at}.{key}: a key <{name}> does not name")
        for key, spec in sorted(table.items()):
            if key not in found:
                if not spec.optional:
                    self.errors.append(f"{at}.{key}: a key <{name}> requires")
                continue
            self.reached.add((name, key))
            self.value(found[key], spec.types, f"{at}.{key}")

    def value(self, value: object, types: frozenset[_Type], at: str) -> None:
        kind = _kind(value)
        matching = [t for t in types if _fits(kind, t)]
        if not matching:
            allowed = sorted(
                t if isinstance(t, str) else type(t).__name__ for t in types
            )
            self.errors.append(f"{at}: a {kind}, where the table allows {allowed}")
            return
        match matching[0]:
            case _Obj(shape):
                self.shape(value, shape, at)
            case _Arr(of):
                for index, item in enumerate(cast(list[object], value)):
                    self.value(item, of, f"{at}[{index}]")
            case _Map(of, keys):
                for key, item in cast(dict[str, object], value).items():
                    if keys is not None and key not in keys:
                        self.errors.append(f"{at}: {key!r} is not in its vocabulary")
                    self.value(item, of, f"{at}[{key!r}]")
            case _OneOf(shapes):
                self.one_of(cast(dict[str, object], value), shapes, at)
            case _:
                pass

    def one_of(
        self, found: dict[str, object], shapes: tuple[str, ...], at: str
    ) -> None:
        def admits(name: str) -> bool:
            table = _SHAPES[name]
            required = {k for k, spec in table.items() if not spec.optional}
            return required <= set(found) <= set(table)

        fitting = [name for name in shapes if admits(name)]
        if len(fitting) != 1:
            self.errors.append(
                f"{at}: keys {sorted(found)} fit {fitting or 'none'} of {list(shapes)}"
            )
            return
        self.shape(found, fitting[0], at)


# --------------------------------------------------------------------------- #
# The fixtures: every branch of every builder
# --------------------------------------------------------------------------- #


def _verdict(
    name: str,
    score: float | None,
    *,
    threshold: float = 0.5,
    tolerance: float = 0.05,
    samples: tuple[float, ...] = (),
    judged: bool = False,
    metadata: Mapping[str, object] | None = None,
) -> Verdict:
    status = "error" if score is None else ("pass" if score >= threshold else "fail")
    return Verdict(
        score=Score(
            name=name,
            score=score,
            metadata=metadata or {},
            samples=samples,
            sample_min=min(samples) if samples else None,
            sample_max=max(samples) if samples else None,
        ),
        threshold=threshold,
        status=status,
        reason="the reply names the account" if score is not None else "",
        tolerance=tolerance,
        judged=judged,
        assertion_id=f"id-{name}",
    )


def _run(
    *,
    created_at: str,
    score: float,
    threshold: float,
    temperature: float,
    judge_model: str,
    config_hash: str,
    groups: tuple[str, ...] = (),
) -> Run:
    """One side of a comparison that takes every branch `compare_json` has: a
    judged check with samples, a deterministic one, a canary, a calibration
    case, a run-level aggregate, and a configuration on both sides."""
    judged = _verdict(
        "llm_rubric",
        score,
        threshold=threshold,
        samples=(score, 1.0, 0.0),
        judged=True,
        metadata={"judge_min": 0.0},
    )
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash=config_hash,
        created_at=created_at,
        git_commit="abc1234",
        results=(
            CaseResult("c1", (judged, _verdict("contains", 1.0))),
            CaseResult("c2", (_verdict("contains", 0.0),), canary=True),
            CaseResult(
                "c3",
                # Sampled and the same on both sides, so it does not flip:
                # `diff` measures an interval only on a row that did not.
                (
                    _verdict(
                        "llm_rubric",
                        0.6,
                        threshold=threshold,
                        samples=(0.5, 0.6, 0.7),
                        judged=True,
                    ),
                ),
                calibration=CalibrationBand(
                    check="llm_rubric", low=0.4, high=0.8, assertion_id="id-llm_rubric"
                ),
            ),
            CaseResult("c4", (), suspended="parked"),
        ),
        aggregate=(
            _verdict("pass_rate", score),
            *(_verdict(f"pass_rate[group={group}]", score) for group in groups),
        ),
        metadata={"model": "m", "customer_balance": 1499.0},
        artifacts={
            "prompt.md": Artifact(sha="a" * 64, text="Answer briefly."),
        },
        pinned=("prompt.md",),
        target_config=SystemConfig(
            values={"provider": "acme", "model": "m-1", "temperature": temperature},
        ),
        judge_config=SystemConfig(
            values={"provider": "acme", "model": judge_model},
            identities=(f"acme/{judge_model}",),
        ),
        digline_version="0.27.0",
        promoted_at=LATER,
        rejudged_from="2025-12-31T00-00-00-00-00-0123456789abcdef",
        usage=RunUsage(
            target=CallTotals(
                calls=3,
                counted=2,
                tokens=Usage(input_tokens=10, output_tokens=5, thinking_tokens=2),
                spent_usd=0.01,
            ),
            judge=CallTotals(calls=1, counted=1, tokens=Usage(1, 1), spent_usd=0.002),
        ),
    )


def _pair() -> tuple[Run, Run]:
    before = _run(
        created_at=CREATED,
        score=0.9,
        threshold=0.5,
        temperature=0.3,
        judge_model="judge-1",
        config_hash="0" * 16,
    )
    now = _run(
        created_at=LATER,
        score=0.2,
        threshold=0.7,
        temperature=0.7,
        judge_model="judge-2",
        config_hash="1" * 16,
        # A gate per group where the reference had one whole: the rule fact
        # that says so carries an `expansion`. (ADR 0028 §6)
        groups=("eu",),
    )
    return now, before


def _sighting(provider: str) -> Sighting:
    return Sighting(
        provider=provider, sent=("m-1",), answered=None, absence="not_reported"
    )


def _register_entry() -> RegisterEntry:
    return RegisterEntry(
        recorded_at=LATER,
        digline_version="0.27.0",
        disposition="accepted",
        run_key="2026-01-02T00-00-00-00-00-1111111111111111",
        run_created_at=LATER,
        run_config_hash="1" * 16,
        run_environment="staging",
        run_digline_version="0.27.0",
        run_rejudged=False,
        baseline_key="2026-01-01T00-00-00-00-00-0000000000000000",
        baseline_config_hash="0" * 16,
        baseline_promoted_at="",
        outcome=RecordedOutcome(
            regressed=1,
            improved=0,
            unchanged=2,
            new=0,
            missing=0,
            errored=0,
            unjudged=0,
            suspended=1,
            within_noise=0,
            on_the_line=0,
            worse=True,
            canary_moved=False,
            config_changed=True,
            artifacts_changed=False,
            target_config_changed=True,
            judge_config_changed=False,
            rejudged=False,
        ),
        exit_code=1,
    )


def _log() -> IdentityLog:
    """Built directly: every list holds one item, and every optional object is
    present, so each shape `log --json` can carry is reached once."""
    return IdentityLog(
        tenant="acme",
        suite="qa",
        since=CREATED,
        until="",
        runs=2,
        first=CREATED,
        last=LATER,
        spans=(
            IdentitySpan(
                side="target",
                provider="acme",
                sent=("m-1",),
                answered="m-1-0915",
                absence=None,
                first_seen=CREATED,
                last_seen=LATER,
                runs=2,
                environments=("staging",),
                unread_on_record=0,
            ),
        ),
        rolls=(
            Roll(
                side="judge",
                provider="acme",
                sent="judge-1",
                before="judge-1-a",
                after="judge-1-b",
                last_before=CREATED,
                first_after=LATER,
                silent_between=0,
                unread_on_record=1,
            ),
        ),
        replays=(Replay(key="k", created_at=LATER, source="k0"),),
        skipped={7: 2},
        unreadable=1,
        refused=1,
        reference=Reference(
            key="k0",
            created_at=CREATED,
            promoted_at="",
            target=_sighting("acme"),
            judge=_sighting("acme"),
        ),
        register=(_register_entry(),),
        register_torn=False,
        register_unreadable=False,
        spread=(
            AggregateSpread(
                name="pass_rate",
                latest=0.2,
                reference=0.9,
                low=0.2,
                high=0.9,
                runs=2,
                excluded={"unjudged": 1},
                unidentified=0,
                commits=2,
                versions=("0.27.0",),
                within_low=None,
                within_high=None,
            ),
        ),
        spread_absence={"scoreless": 1},
        on_record_not_read=(CREATED,),
    )


def documents() -> Iterator[tuple[str, str, dict[str, object]]]:
    """Every top-level document, with the shape it must be, by the builder that
    makes it. The nested builders are reached through these."""
    now, before = _pair()
    comparison = compare(now, before)
    head = headline(comparison, now, before, locale="en")
    yield (
        "compare_json",
        "compare",
        compare_json(comparison, head, baseline=before, full=False, run=now),
    )
    yield (
        "compare_json full",
        "compare.full",
        compare_json(comparison, head, baseline=before, full=True, run=now),
    )
    # A caller written before `run_key`, which passes no run: the optional key
    # absent, and nothing else missing. (#448)
    yield (
        "compare_json without a run",
        "compare",
        compare_json(comparison, head, baseline=before, full=False),
    )

    # A diff refuses two suites, so its right side is `before`'s suite with
    # `now`'s scores and configuration.
    other = _run(
        created_at=LATER,
        score=0.2,
        threshold=0.5,
        temperature=0.7,
        judge_model="judge-1",
        config_hash=before.config_hash,
    )
    difference = diff(before, other)
    keys = (
        key_of(before.created_at, before.config_hash),
        key_of(other.created_at, other.config_hash),
    )
    for full in (False, True):
        yield (
            f"diff_json full={full}",
            "diff.full" if full else "diff",
            diff_json(
                difference,
                before,
                other,
                keys=keys,
                labels=("baseline", "latest"),
                sentence="Two runs.",
                full=full,
            ),
        )

    yield (
        "explain_json comparison",
        "explain",
        explain_json(
            facts(now, comparison),
            scope="comparison",
            exit_code=1,
            run=now,
            baseline=before,
        ),
    )
    yield (
        "explain_json run",
        "explain",
        explain_json(facts(now), scope="run", exit_code=0, run=now),
    )
    yield (
        "explain_json without its documents",
        "explain",
        explain_json(facts(now), scope="run", exit_code=0),
    )

    yield "log_json", "log", log_json(_log())

    ref = RunRef(tenant="acme", suite="qa", key=keys[1])
    plan = CallPlan(cases=4, samples=1, tenant="acme", reused=1)
    yield "run_json", "run", run_json(ref, plan)
    yield (
        "run_json judged",
        "run",
        run_json(
            ref,
            plan,
            resumed=True,
            judge_reading="The judge ranged 0.0 to 1.0.",
            usage=now.usage,
        ),
    )

    yield (
        "runs_json",
        "runs",
        runs_json(
            [(keys[0], before), (keys[1], now)],
            tenant="acme",
            suite="qa",
            baseline_key=keys[0],
            listing=Listing(runs=(ref,), skipped={7: 1}, unreadable=("x.json",)),
            refused=1,
            baseline_unreadable=False,
        ),
    )

    yield "run_document", "run_document", run_document(now, Disclosure())
    # `get_run`'s: the optional key present, as a run resolved by name brings it.
    yield (
        "run_document resolved",
        "run_document",
        run_document(now, Disclosure(), note="ignored: 1 run(s) at schema 7"),
    )
    yield (
        "run_document disclosed",
        "run_document",
        run_document(
            dataclasses.replace(now, usage=None),
            Disclosure(
                score_metadata=frozenset({"judge_min"}),
                run_metadata=frozenset({"model"}),
                artifacts=True,
            ),
        ),
    )


DOCUMENTS = list(documents())


@pytest.mark.parametrize(
    ("builder", "shape", "document"), DOCUMENTS, ids=[d[0] for d in DOCUMENTS]
)
def test_every_document_is_the_shape_the_table_names(
    builder: str, shape: str, document: dict[str, object]
) -> None:
    walk = Walk()
    walk.shape(document, shape, builder)
    assert not walk.errors, (
        "The document is not the shape `digline.wire.contract` names. An added "
        "key is an entry in `_ADDED`; a renamed or removed key, or a value of "
        "another type, is a bump of `OUTPUT_VERSION`.\n" + "\n".join(walk.errors)
    )


def test_every_shape_and_every_key_in_the_table_is_reached() -> None:
    """A pin no fixture reaches is a pin that can never fail. Each shape, and
    each key including the optional ones, has to be produced by a builder here
    at least once."""
    walk = Walk()
    for builder, shape, document in DOCUMENTS:
        walk.shape(document, shape, builder)
    unreached_shapes = sorted(set(_SHAPES) - walk.shapes)
    unreached_keys = sorted(
        f"{name}.{key}"
        for name, table in _SHAPES.items()
        if name in walk.shapes
        for key in table
        if (name, key) not in walk.reached
    )
    assert not unreached_shapes, unreached_shapes
    assert not unreached_keys, unreached_keys


def test_the_base_has_not_moved_under_this_output_version() -> None:
    """`_BASE` is the shape every consumer of this `OUTPUT_VERSION` parses. It
    changes by a bump and by nothing else: an added key goes in `_ADDED`."""
    version, pinned = _BASE_DIGEST
    found = _digest(_BASE)
    assert version == OUTPUT_VERSION, (
        f"`_BASE_DIGEST` belongs to OUTPUT_VERSION {version}, and it is "
        f"{OUTPUT_VERSION}. After a bump, fold `_ADDED` into `_BASE`, empty "
        "`_ADDED`, and pin the new version and digest together."
    )
    assert found == pinned, (
        "`_BASE` moved under the same `OUTPUT_VERSION`. If a key was added, "
        "take it out of `_BASE` and put it in `_ADDED`. If a key was renamed or "
        "removed, or a value may now take another type, a consumer parsing the "
        "old shape breaks: bump `OUTPUT_VERSION`, record why in `contract.py`, "
        f"and pin ({OUTPUT_VERSION + 1}, {found!r}).\n" + "\n".join(_lines(_BASE))
    )


def test_an_added_key_is_new_and_named_once() -> None:
    """An `_ADDED` entry over a key `_BASE` already has would be a change
    wearing an addition's name, which is the one thing the split exists to
    tell apart."""
    seen: set[tuple[str, str]] = set()
    for entry in _ADDED:
        where = (entry.shape, entry.key)
        assert entry.key not in _BASE.get(entry.shape, {}), where
        assert where not in seen, where
        assert entry.ref, where
        seen.add(where)


def _vocabulary(
    shapes: Mapping[str, Mapping[str, _Key]], shape: str, key: str
) -> frozenset[str]:
    (found,) = [t for t in shapes[shape][key].types if isinstance(t, _Map)]
    assert found.keys is not None, f"{shape}.{key} has an open vocabulary"
    return found.keys


def test_an_added_word_is_new_and_named_once() -> None:
    """`_ADDED_WORDS`' counterpart of the test above. A word `_BASE` already
    had would be a change wearing an addition's name. A word the derived table
    lacks would be an entry that added nothing. (#402)"""
    seen: set[tuple[str, str, str]] = set()
    for entry in _ADDED_WORDS:
        where = (entry.shape, entry.key, entry.word)
        assert entry.word not in _vocabulary(_BASE, entry.shape, entry.key), where
        assert entry.word in _vocabulary(_SHAPES, entry.shape, entry.key), where
        assert where not in seen, where
        assert entry.ref, where
        seen.add(where)


def test_an_added_word_is_a_word_its_owner_has() -> None:
    """`_BASE` reads the vocabulary from the module that owns it, minus the
    added words, and `_derive` puts them back. So the derived vocabulary is the
    owner's, exactly. An entry naming a word the owner never had would put it
    on the wire's table and in no document."""
    assert _vocabulary(_SHAPES, "log", "spread_absence") == frozenset(SPREAD_ABSENCES)


def test_no_value_may_be_two_kinds_of_object() -> None:
    """The walk picks the one alternative a value's JSON type fits. Two object
    alternatives in one set, or two list ones, would have it pick by order, and
    a document of the wrong one would be checked against the right one."""
    for line, spec in _all_specs():
        objects = [t for t in spec.types if isinstance(t, _Obj | _Map | _OneOf)]
        arrays = [t for t in spec.types if isinstance(t, _Arr)]
        assert len(objects) <= 1 and len(arrays) <= 1, line


def _all_specs() -> Iterator[tuple[str, _Key]]:
    for name, table in _SHAPES.items():
        for key, spec in table.items():
            yield f"{name}.{key}", spec


# --------------------------------------------------------------------------- #
# The walk can fail: one document, three edits a consumer would see
# --------------------------------------------------------------------------- #


def _errors(document: dict[str, object], shape: str) -> list[str]:
    walk = Walk()
    walk.shape(document, shape, "doc")
    return walk.errors


def _runs() -> dict[str, Any]:
    [(_, shape, document)] = [d for d in DOCUMENTS if d[0] == "runs_json"]
    assert not _errors(document, shape)
    return dict(document)


def test_a_key_added_without_an_entry_fails() -> None:
    document = _runs()
    document["zz_added"] = 0
    assert _errors(document, "runs") == ["doc.zz_added: a key <runs> does not name"]


def test_a_renamed_key_fails_twice() -> None:
    document = _runs()
    document["refused_runs"] = document.pop("refused")
    assert _errors(document, "runs") == [
        "doc.refused_runs: a key <runs> does not name",
        "doc.refused: a key <runs> requires",
    ]


def test_a_boolean_where_an_integer_was_fails() -> None:
    """`False == 0` in Python, so an assertion written `== 0` passes this
    change. The walk does not."""
    document = _runs()
    document["refused"] = False
    [error] = _errors(document, "runs")
    assert error.startswith("doc.refused: a boolean")


def test_an_integer_where_a_boolean_was_fails() -> None:
    document = _runs()
    document["baseline_unreadable"] = 0
    [error] = _errors(document, "runs")
    assert error.startswith("doc.baseline_unreadable: a integer")


def test_a_nested_key_fails_where_it_is() -> None:
    document = _runs()
    rows = [dict(row) for row in document["runs"]]
    rows[0]["aggregate"] = [dict(rows[0]["aggregate"][0], status=1)]
    document["runs"] = rows
    [error] = _errors(document, "runs")
    assert error.startswith("doc.runs[0].aggregate[0].status: a integer")
