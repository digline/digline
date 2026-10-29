"""`_STEPS` read as a family: each step declares its nature, and keeps it.

ADR 0055 §7 and ADR 0056 §6 owe this gate before the first step that renames
or transforms lands. Each entry of `_STEPS` declares one of four natures: it
writes nothing, it adds, it renames, or it transforms. What it touches is
declared as paths in the schema, never as names, because a name is written at
more than one position: `withheld` is a configuration's list and, in three
other places, a boolean meaning *kept back*.

**Two of the four natures have no instance.** No step in `_STEPS` renames and
none transforms, so a test that only walked `_STEPS` would never run the half of
this gate that matters most, and a check that cannot fail is the one this
repository forbids. They are exercised on steps built here: a renaming step and
a transforming step, with the documents that put each to the proof, and a
broken copy of each that the same checks must refuse. None of them is digline's
and none migrates anything outside this file.

How a path is written: keys separated by `.`, `[]` after a key for every
element of the list it holds, and `*` for every value of a map.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from digline.store import migrate
from digline.store.migrate import (
    _DECLARED_VIOLATIONS,  # pyright: ignore[reportPrivateUsage]
    _STEPS,  # pyright: ignore[reportPrivateUsage]
    Adds,
    NonAdditiveError,
    Renames,
    SchemaPath,
    Step,
    Transforms,
    WritesNothing,
    migrate_file,
)

ADR_0056 = (
    Path(__file__).parent.parent
    / "docs"
    / "adr"
    / "0056-a-migration-step-that-transforms.md"
)

Document = dict[str, Any]
#: One concrete position in a document: keys and list indices.
Position = tuple[str | int, ...]


# -- reading a document by position --------------------------------------------


def _matches(document: Any, path: SchemaPath) -> list[Position]:
    """Every concrete position in `document` that `path` names."""
    found: list[tuple[Position, Any]] = [((), document)]
    for segment in path.segments:
        reached: list[tuple[Position, Any]] = []
        for at, node in found:
            if segment == "[]":
                if isinstance(node, list):
                    items = cast(list[Any], node)
                    reached.extend((at + (i,), item) for i, item in enumerate(items))
            elif segment == "*":
                if isinstance(node, dict):
                    entries = cast(dict[str, Any], node)
                    reached.extend(
                        (at + (key,), value) for key, value in entries.items()
                    )
            elif isinstance(node, dict) and segment in node:
                reached.append((at + (segment,), cast(dict[str, Any], node)[segment]))
        found = reached
    return [at for at, _ in found]


def _at(document: Any, position: Position) -> Any:
    node = document
    for key in position:
        node = node[key]
    return node


def _delete(document: Document, positions: list[Position]) -> Document:
    """A copy of `document` without `positions`, deepest first so that an index
    deleted from a list does not move the next one."""
    out = copy.deepcopy(document)
    for position in sorted(positions, key=lambda p: (len(p), p), reverse=True):
        del _at(out, position[:-1])[position[-1]]
    return out


def _without(document: Document, paths: tuple[SchemaPath, ...]) -> Document:
    return _delete(document, [at for path in paths for at in _matches(document, path)])


def _keyed(document: Any, at: Position = ()) -> Iterator[Position]:
    """Every position in `document` that is a key of a map, at any depth."""
    if isinstance(document, dict):
        for key, value in cast(dict[str, Any], document).items():
            yield at + (key,)
            yield from _keyed(value, at + (key,))
    elif isinstance(document, list):
        for i, item in enumerate(cast(list[Any], document)):
            yield from _keyed(item, at + (i,))


def _same(a: Document, b: Document) -> bool:
    """Equal but for `schema_version`, by their JSON: `True == 1` in Python,
    and a step that turned one into the other has changed the document."""

    def text(d: Document) -> str:
        return json.dumps(
            {k: v for k, v in d.items() if k != "schema_version"}, sort_keys=True
        )

    return text(a) == text(b)


def _apply(step: Step, before: Document) -> Document:
    return step.apply(copy.deepcopy(before))


# -- the declarations ----------------------------------------------------------


def _faults(step: object) -> list[str]:
    """What is wrong with a declaration before any document is read."""
    if not isinstance(step, Step):
        return [f"{step!r} is not a Step: it declares no nature"]
    nature = cast(object, step.nature)
    faults: list[str] = []

    def paths(*declared: object) -> None:
        for each in declared:
            if not isinstance(each, SchemaPath):
                faults.append(f"{each!r} is declared as a name, not as a SchemaPath")

    if isinstance(nature, WritesNothing):
        pass
    elif isinstance(nature, Adds):
        paths(*nature.writes)
        if not nature.writes:
            faults.append("a step that adds declares no path it writes")
    elif isinstance(nature, Renames):
        if not nature.pairs:
            faults.append("a step that renames declares no pair")
        for old, new in nature.pairs:
            paths(old, new)
            # Declared as names, the pair has no position to compare.
            if not all(isinstance(cast(object, p), SchemaPath) for p in (old, new)):
                continue
            if old.segments[:-1] != new.segments[:-1] or old == new:
                faults.append(
                    f"{old} -> {new} is not a rename: a rename changes the last "
                    "key alone, at the same position (ADR 0055 §2)"
                )
    elif isinstance(nature, Transforms):
        paths(*nature.reads, nature.writes, *nature.removes, nature.domain)
        if nature.writes not in nature.reads:
            faults.append(
                f"{nature.writes} is not a path the step reads: a transformation that "
                "also names something new is two steps (ADR 0056 §4)"
            )
        if set(nature.removes) != set(nature.reads) - {nature.writes}:
            faults.append(
                "the removed paths are not the read paths it does not write "
                "(ADR 0056 §1)"
            )
        for read in nature.reads:
            if read.segments[: len(nature.domain.segments)] != nature.domain.segments:
                faults.append(f"{read} is outside the declared domain {nature.domain}")
        if not nature.refusals:
            faults.append(
                "a step that transforms declares no sentence to refuse with "
                "(ADR 0056 §3)"
            )
    else:
        faults.append(f"{nature!r} is none of the four natures")
    return faults


# -- holding a step to its nature ------------------------------------------------


def _holds_writes_nothing(before: Document, after: Document) -> None:
    assert _same(after, before), "declared to write nothing, and the document changed"


def _holds_adds(nature: Adds, before: Document, after: Document) -> None:
    added = [
        at
        for path in nature.writes
        for at in _matches(after, path)
        if at not in _matches(before, path)
    ]
    assert _same(_delete(after, added), before), (
        "declared to add only at " + ", ".join(map(str, nature.writes)) + ", and once "
        "what it added there is taken away, the document is not the one it was given"
    )


def _renamed(nature: Renames, before: Document) -> Document:
    """What a rename leaves, computed from the declaration alone."""
    expected = copy.deepcopy(before)
    for old, new in nature.pairs:
        for at in _matches(before, old):
            parent = _at(expected, at[:-1])
            parent[new.segments[-1]] = parent.pop(at[-1])
    return expected


def _holds_renames(nature: Renames, before: Document, after: Document) -> None:
    for old, _new in nature.pairs:
        assert not _matches(after, old), f"{old} is still in the document (ADR 0055 §5)"
    assert _same(after, _renamed(nature, before)), (
        "on the declared paths the value is not carried unchanged, or a path that "
        "was not declared changed (ADR 0055 §1, §7)"
    )
    declared = {at for old, _ in nature.pairs for at in _matches(before, old)}
    for old, _new in nature.pairs:
        for at in _keyed(before):
            if at[-1] == old.segments[-1] and at not in declared:
                assert at in set(_keyed(after)) and _at(after, at) == _at(before, at), (
                    f"{at} carried {old.segments[-1]!r} and was not declared, and it "
                    "does not carry it any more (ADR 0055 §1)"
                )


def _holds_transforms(nature: Transforms, before: Document, after: Document) -> None:
    for removed in nature.removes:
        assert not _matches(after, removed), (
            f"{removed} is declared removed and is still there"
        )
    domain = _matches(before, nature.domain)
    written = _matches(after, nature.writes)
    for at in domain:
        assert any(w[: len(at)] == at for w in written), (
            f"{at} is inside the domain and holds nothing at {nature.writes}"
        )
    read = [at for path in nature.reads for at in _matches(before, path)]
    assert _same(_delete(after, written), _delete(before, read)), (
        "a path the step does not declare changed (ADR 0056 §6)"
    )


def _holds(step: Step, before: Document) -> str:
    """Apply `step` to `before` and hold it to its declared nature.

    Returns the outcome, so a test can say which one it expected: `"same"`,
    `"added"`, `"renamed"`, `"transformed"` or `"refused"`. A refusal by a step
    that transforms must carry one of its declared sentences; any other step
    that refuses is reported as refused, and the caller decides.
    """
    nature = step.nature
    try:
        after = _apply(step, before)
    except NonAdditiveError as refusal:
        if isinstance(nature, Transforms):
            assert any(s in str(refusal) for s in nature.refusals), (
                f"refused with a sentence the step did not declare: {refusal}"
            )
        return "refused"
    if isinstance(nature, WritesNothing):
        _holds_writes_nothing(before, after)
        return "same"
    if isinstance(nature, Adds):
        _holds_adds(nature, before, after)
        return "added"
    if isinstance(nature, Renames):
        _holds_renames(nature, before, after)
        return "same" if _same(after, before) else "renamed"
    if not _matches(before, nature.domain):
        assert _same(after, before), (
            "outside its domain, and the document changed (ADR 0056 §1)"
        )
        return "same"
    _holds_transforms(nature, before, after)
    return "transformed"


# -- the documents ---------------------------------------------------------------


def _document(version: int) -> Document:
    """A document that carries every path a step in this file can touch.

    It is not parsed by any reader: a step reads keys, and this holds the keys
    each step reads and writes. `withheld` is at every position the stored
    document writes it, and two of them are positions no rename may touch: a
    configuration's list, and a third-party verdict's own metadata in a
    document that is not a projection (ADR 0055, *Context*).
    """
    return {
        "schema_version": version,
        "tenant": "acme",
        "environment": "staging",
        "redacted": False,
        "projected": False,
        "results": [
            {
                "case_id": "c1",
                "suspended": False,
                "verdicts": [
                    {
                        "assertion": "judge",
                        "assertion_id": "a1",
                        "score": 0.8,
                        "metadata": {"scores": [0.7, 0.9], "withheld": True},
                        "samples": [0.7, 0.9],
                        "sample_min": 0.7,
                        "sample_max": 0.9,
                    }
                ],
                "calibration": {
                    "check": "judge",
                    "assertion_id": "a1",
                    "low": 0.2,
                    "high": 0.9,
                },
                "responses": [{"withheld": True}, {"output": "an answer"}],
            },
            {"case_id": "c2", "suspended": False, "verdicts": []},
        ],
        "aggregate": [
            {
                "assertion": "mean",
                "assertion_id": "g1",
                "metadata": {"scores": [0.5, 0.6]},
                "samples": [0.5, 0.6],
                "sample_min": 0.5,
                "sample_max": 0.6,
            }
        ],
        "artifacts": {
            "prompt.txt": {"sha256": "ab", "withheld": True},
            "rules.md": {"sha256": "cd"},
        },
        "target_config": {"model": "m", "withheld": ["api_key"]},
        "judge_config": {"model": "j"},
    }


def _bare(version: int) -> Document:
    """A document that carries none of the paths a step can touch."""
    return {
        "schema_version": version,
        "tenant": "acme",
        "environment": "staging",
        "redacted": False,
        "results": [],
    }


def _before(version: int, step: Step) -> Document:
    """The full document of `version`, without what `step` declares it adds, so
    that a step that adds has something to add."""
    nature = step.nature
    if isinstance(nature, Adds):
        return _without(_document(version), nature.writes)
    return _document(version)


# -- the family ------------------------------------------------------------------


def test_every_entry_declares_a_nature_and_the_counts_are_fixed() -> None:
    """18 entries, 7 that add and 11 that write nothing. A new entry moves a
    count, so it cannot join without saying what it is; and the day the first
    rename or transformation lands, this is the line that says so."""
    faults = {version: _faults(step) for version, step in _STEPS.items()}
    assert {v: f for v, f in faults.items() if f} == {}
    natures = Counter(type(step.nature).__name__ for step in _STEPS.values())
    assert natures == {"Adds": 7, "WritesNothing": 11}


@pytest.mark.parametrize("version", sorted(_STEPS))
def test_each_step_keeps_its_declared_nature(version: int) -> None:
    """Applied to a document that carries every path it can touch, and to one
    that carries none, each step does what it declares and nothing else."""
    step = _STEPS[version]
    full = _before(version, step)
    outcome = _holds(step, full)
    expected = "added" if isinstance(step.nature, Adds) else "same"
    assert outcome == expected
    if isinstance(step.nature, Adds):
        after = _apply(step, full)
        missing = [str(p) for p in step.nature.writes if not _matches(after, p)]
        assert missing == [], f"declared to add {missing}, and added nothing there"
    assert _holds(step, _bare(version)) in {"same", "added"}


def _violations_in_the_adr() -> dict[int, str]:
    text = ADR_0056.read_text(encoding="utf-8")
    table = text.split("**The declared violations", 1)[1].split(
        "**Why `_add_artifacts`", 1
    )[0]
    rows = re.findall(r"^\| `(\d+) -> \d+`, `(_\w+)` \|", table, flags=re.MULTILINE)
    return {int(version): name for version, name in rows}


def _passes_in_the_adr() -> dict[int, str]:
    text = ADR_0056.read_text(encoding="utf-8")
    table = text.split("**The five steps that write a fixed value", 1)[1]
    table = table.split("**The declared violations", 1)[0]
    rows = re.findall(r"^\| `(\d+) -> \d+`, `(_\w+)` \|", table, flags=re.MULTILINE)
    return {int(version): name for version, name in rows}


def test_the_declared_violations_are_exactly_the_two_adr_0056_names() -> None:
    """ADR 0056 §2 declares two steps whose default states what was not true of
    the run, and fixes the count at two. The code's list and the ADR's table are
    read against each other and against the two names, so neither can grow or
    shrink without the other, and in silence."""
    in_code = {
        version: _STEPS[version].apply.__name__ for version in _DECLARED_VIOLATIONS
    }
    assert in_code == {6: "_add_artifacts", 7: "_add_configs"}
    assert _violations_in_the_adr() == in_code
    # The control: the same reading finds the three that pass, so an ADR whose
    # table moved would read as no rows here, not as agreement.
    assert _passes_in_the_adr() == {
        4: "_add_suspended",
        5: "_add_aggregate",
        17: "_add_schema_eighteen",
    }
    for version in (*in_code, *_passes_in_the_adr()):
        assert isinstance(_STEPS[version].nature, Adds)
        assert _STEPS[version].apply.__name__ == _passes_in_the_adr().get(
            version, in_code.get(version)
        )


# -- a renaming step, built here ---------------------------------------------------


_RENAMES = Renames(
    pairs=(
        (SchemaPath.of("artifacts.*.withheld"), SchemaPath.of("artifacts.*.redacted")),
        (
            SchemaPath.of("results[].responses[].withheld"),
            SchemaPath.of("results[].responses[].redacted"),
        ),
    )
)


def _rename_by_position(nature: Renames) -> Callable[[Document], Document]:
    def apply(raw: Document) -> Document:
        for old, new in nature.pairs:
            for at in _matches(raw, old):
                parent = _at(raw, at[:-1])
                if new.segments[-1] in parent:
                    raise NonAdditiveError(
                        f"{at} carries both {old.segments[-1]!r} and "
                        f"{new.segments[-1]!r}, and neither is chosen (ADR 0055 §4)"
                    )
                parent[new.segments[-1]] = parent.pop(old.segments[-1])
        return raw

    return apply


def _rename_by_spelling(raw: Any) -> Any:
    """The rename ADR 0055 §1 forbids: every key spelt `withheld`, wherever."""
    if isinstance(raw, dict):
        entries = cast(dict[str, Any], raw)
        return {
            ("redacted" if key == "withheld" else key): _rename_by_spelling(value)
            for key, value in entries.items()
        }
    if isinstance(raw, list):
        return [_rename_by_spelling(item) for item in cast(list[Any], raw)]
    return raw


RENAMING = Step(_rename_by_position(_RENAMES), _RENAMES)


def test_a_renaming_step_carries_the_value_and_touches_nothing_undeclared() -> None:
    before = _document(22)
    assert all(_matches(before, old) for old, _ in _RENAMES.pairs)
    assert _faults(RENAMING) == []
    assert _holds(RENAMING, before) == "renamed"
    after = _apply(RENAMING, before)
    assert after["artifacts"]["prompt.txt"] == {"sha256": "ab", "redacted": True}
    assert after["results"][0]["responses"][0] == {"redacted": True}
    # The two positions no rename may touch, by name.
    assert after["target_config"]["withheld"] == ["api_key"]
    assert after["results"][0]["verdicts"][0]["metadata"]["withheld"] is True


def test_a_renaming_step_leaves_an_absent_key_absent() -> None:
    before = _without(_document(22), tuple(old for old, _ in _RENAMES.pairs))
    assert _holds(RENAMING, before) == "same"


def test_a_renaming_step_refuses_both_names_and_the_file_is_left_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _document(22)
    before["artifacts"]["prompt.txt"]["redacted"] = False
    assert _holds(RENAMING, before) == "refused"
    _left_as_it_was(tmp_path, monkeypatch, RENAMING, before)


def test_a_rename_by_spelling_is_caught_on_the_undeclared_positions() -> None:
    """The broken copy: declared by paths, applied by name. The configuration's
    list and the foreign metadata are renamed too, and only a check on the
    undeclared positions can see it, since the declared ones are right."""
    broken = Step(_rename_by_spelling, _RENAMES)
    with pytest.raises(
        AssertionError, match="was not declared changed|carried 'withheld'"
    ):
        _holds(broken, _document(22))


def test_a_rename_declared_by_name_is_refused_before_any_document() -> None:
    by_name = Step(
        _rename_by_position(_RENAMES),
        Renames(pairs=cast(Any, (("withheld", "redacted"),))),
    )
    assert _faults(by_name) == [
        "'withheld' is declared as a name, not as a SchemaPath",
        "'redacted' is declared as a name, not as a SchemaPath",
    ]


# -- a transforming step, built here -----------------------------------------------


_TRANSFORMS = Transforms(
    domain=SchemaPath.of("results[].calibration"),
    reads=(
        SchemaPath.of("results[].calibration.low"),
        SchemaPath.of("results[].calibration.high"),
    ),
    writes=SchemaPath.of("results[].calibration.low"),
    removes=(SchemaPath.of("results[].calibration.high"),),
    refusals=("has no", "does not determine"),
)


def _transform(default: float | None) -> Callable[[Document], Document]:
    """`low` and `high` become one `low` holding both, ordered. With `default`,
    the broken copy: a missing `high` is filled instead of refused."""

    def apply(raw: Document) -> Document:
        for at in _matches(raw, _TRANSFORMS.domain):
            band = _at(raw, at)
            if default is not None:
                band.setdefault("high", default)
            for key in ("low", "high"):
                if key not in band:
                    raise NonAdditiveError(
                        f"the calibration band at {at} has no {key!r}, and its new "
                        "shape cannot be computed without it"
                    )
            if band["low"] > band["high"]:
                raise NonAdditiveError(
                    f"the calibration band at {at} is inverted, and it does not "
                    "determine which bound is which"
                )
            band["low"] = [band["low"], band.pop("high")]
        return raw

    return apply


TRANSFORMING = Step(_transform(None), _TRANSFORMS)


def test_a_transforming_step_writes_the_new_shape_and_removes_what_it_declared() -> (
    None
):
    assert _faults(TRANSFORMING) == []
    assert _holds(TRANSFORMING, _document(22)) == "transformed"
    band = _apply(TRANSFORMING, _document(22))["results"][0]["calibration"]
    assert band == {"check": "judge", "assertion_id": "a1", "low": [0.2, 0.9]}


@pytest.mark.parametrize("read", _TRANSFORMS.reads, ids=str)
def test_a_transforming_step_refuses_an_input_absent_inside_its_domain(
    read: SchemaPath, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _delete(_document(22), _matches(_document(22), read)[:1])
    assert _matches(before, _TRANSFORMS.domain), (
        "the position must stay inside the domain"
    )
    assert _holds(TRANSFORMING, before) == "refused"
    _left_as_it_was(tmp_path, monkeypatch, TRANSFORMING, before)


def test_a_transforming_step_refuses_inputs_that_do_not_determine_the_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _document(22)
    before["results"][0]["calibration"].update(low=0.9, high=0.2)
    assert _holds(TRANSFORMING, before) == "refused"
    _left_as_it_was(tmp_path, monkeypatch, TRANSFORMING, before)


def test_a_transforming_step_touches_nothing_outside_its_domain() -> None:
    before = _without(_document(22), (_TRANSFORMS.domain,))
    assert _holds(TRANSFORMING, before) == "same"


def test_a_transforming_step_that_writes_a_default_is_caught() -> None:
    """The broken copy: a missing `high` becomes `1.0` instead of a refusal.
    The check sees a document transformed where it expected a refusal, which
    is the default ADR 0056 §2 forbids."""
    broken = Step(_transform(1.0), _TRANSFORMS)
    before = _delete(_document(22), _matches(_document(22), _TRANSFORMS.reads[1]))
    assert _holds(broken, before) == "transformed"
    assert _holds(TRANSFORMING, before) == "refused"


def test_a_transformation_that_writes_a_path_it_did_not_read_is_two_steps() -> None:
    renaming_too = Step(
        _transform(None),
        Transforms(
            domain=_TRANSFORMS.domain,
            reads=_TRANSFORMS.reads,
            writes=SchemaPath.of("results[].calibration.bounds"),
            removes=_TRANSFORMS.reads,
            refusals=_TRANSFORMS.refusals,
        ),
    )
    assert _faults(renaming_too) == [
        "results[].calibration.bounds is not a path the step reads: a transformation "
        "that also names something new is two steps (ADR 0056 §4)"
    ]


def _left_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: Step, document: Document
) -> None:
    """Through `migrate_file`, with the step installed as `22 -> 23`: refused,
    and the file byte-identical."""
    monkeypatch.setattr(migrate, "SCHEMA_VERSION", 23)
    monkeypatch.setattr(migrate, "_STEPS", {**_STEPS, 22: step})
    path = tmp_path / "run.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    written = path.read_bytes()
    with pytest.raises(NonAdditiveError):
        migrate_file(path)
    assert path.read_bytes() == written
