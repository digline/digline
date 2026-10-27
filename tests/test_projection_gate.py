"""The gate ADR 0034 §16 promised: every string a projection lets cross is in
one of §4's three classes, or it is refused here. (#710)

§4 says *"every serialized field is classified"* and *"A field in none of the
three is refused, not passed"*, and §16 names a test that walks the serializer
as what holds it. Until #710 that test did not exist. `_check_projected` checks
by name, field by field, and lets through whatever it does not name: a string
field added to `CaseResult` and kept by `redact()` reached a projected document,
a person's name in it, and nothing refused it.

**Two halves, and each catches what the other cannot.**

- **The first walks the projected document** and fails **closed**: every
  string, value or map key, sits at a path, and a path that is not in
  `STRINGS` or `KEYS` below is red, named. `_check_projected` checks what it
  names and passes the rest. This refuses what it does not name. It catches a
  value that escapes.
- **The second walks the model**: every field of a string type on a dataclass
  reachable from `Run` must be in `FIELDS`, which says where the field goes in a
  projection or why it never gets there. It catches a field that exists, and
  it does so when the field is empty: the serializer writes a string only when
  it has one, so a new field with an empty default never reaches the document,
  and the first half alone could not see it by construction. A closed
  vocabulary, a `Literal` of strings whether a type alias names it or not, is a
  string type too: until #563 the walk read only `str`, so `Verdict.status` and
  three fields of a recorded answer were outside it, and a new word on a case
  would have been as well.

**What this does not cover, one exclusion with its reason**, so that nobody
reads the gate as §4's whole guarantee. §4 read literally stays wider than what
is held here.

1. **Numbers.** §4's correction of 2026-09-28 says that read literally the rule
   refuses every number, and that numbers are *"the one axis this enumeration
   does not yet decide"*. The walk skips them. Deciding them here, sideways, by
   writing a test would be deciding what §4 left open.

`Run.modules_unchecked` was a second, until #712: `redact()` keeps the names in
clear because they come from the perimeter artifact and pinned paths cross from
(ADR 0052), and in a projection those paths are tokens. Its names are tokens
there now, of the `module_name` kind, and the walk holds them to that.

**The keys of a verdict's metadata were a third, until schema 22** (#711). A
verdict records its `origin`, and the walk classifies a metadata key by the
origin of the verdict it sits on, which it reads beside it: a builtin
verdict's keys are written by digline's code, class (a); a foreign or
unrecorded one's are tokens, except the keys the driver writes. A
configuration key is a token or a word of digline's vocabulary, which it
records as `named` (#323). (ADR 0034 §17)
"""

from __future__ import annotations

import dataclasses
import json
import re
import typing
from collections.abc import Callable, Iterator
from dataclasses import replace

from digline.core import (
    DRIVER_METADATA_KEYS,
    NAMED_CONFIG_KEYS,
    Run,
    is_token,
    project,
    run_to_json,
    split_grouped_name,
)
from test_projection import Table, promoted

Check = Callable[[str], bool]

_DIGEST = re.compile(r"[0-9a-f]{16}")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9:.]+)?(?:Z|[+-][0-9:]+)?")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\S*")
_RUN_KEY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9-]*Z?)?-[0-9a-f]{16}")
_STATUS = frozenset({"pass", "fail", "error"})
_ERROR_KINDS = frozenset({"raised", "shape"})
_ORIGINS = frozenset({"builtin", "foreign"})


def _token_or_named(text: str) -> bool:
    """A configuration key: a token, or one of digline's words, which the
    projection lets cross only where the configuration recorded it."""
    return is_token(text) or text in NAMED_CONFIG_KEYS


def _token_or_driver(text: str) -> bool:
    """A metadata key on a verdict that is not builtin: a token, or a key the
    driver writes on every verdict."""
    return is_token(text) or text in DRIVER_METADATA_KEYS


def _form(pattern: re.Pattern[str]) -> Check:
    return lambda text: pattern.fullmatch(text) is not None


def _grouped_token(text: str) -> bool:
    family, group = split_grouped_name(text)
    return is_token(family) and (group is None or is_token(group))


def _anything(_: str) -> bool:
    return True


#: (a) digline's own vocabulary, checked for its form; (b) the committing
#: party's own strings, which are the software house's by construction; (c) a
#: token. Every string value of a projected document sits at one of these
#: paths, or the first half below is red.
STRINGS: dict[str, tuple[str, Check]] = {
    "$.config_hash": ("a", _form(_DIGEST)),
    "$.created_at": ("a", _form(_TIME)),
    "$.promoted_at": ("a", _form(_TIME)),
    "$.resumed_at[]": ("a", _form(_TIME)),
    "$.digline_version": ("a", _form(_VERSION)),
    "$.rejudged_from": ("a", _form(_RUN_KEY)),
    "$.results[].verdicts[].assertion_id": ("a", _form(_DIGEST)),
    "$.results[].verdicts[].status": ("a", _STATUS.__contains__),
    "$.results[].calibration.assertion_id": ("a", _form(_DIGEST)),
    "$.results[].error_kind": ("a", _ERROR_KINDS.__contains__),
    "$.results[].verdicts[].origin": ("a", _ORIGINS.__contains__),
    "$.aggregate[].origin": ("a", _ORIGINS.__contains__),
    "$.target_config.named[]": ("a", NAMED_CONFIG_KEYS.__contains__),
    "$.judge_config.named[]": ("a", NAMED_CONFIG_KEYS.__contains__),
    "$.aggregate[].assertion_id": ("a", _form(_DIGEST)),
    "$.aggregate[].status": ("a", _STATUS.__contains__),
    "$.tenant": ("b", _anything),
    "$.suite": ("b", _anything),
    "$.environment": ("b", _anything),
    "$.git_commit": ("b", _anything),
    "$.results[].case_id": ("c", is_token),
    "$.results[].verdicts[].assertion": ("c", is_token),
    "$.results[].calibration.check": ("c", is_token),
    "$.aggregate[].assertion": ("c", _grouped_token),
    "$.pinned[]": ("c", is_token),
    "$.modules_unchecked[]": ("c", is_token),
    "$.target_config.values{}": ("c", is_token),
    "$.target_config.withheld[]": ("a|c", _token_or_named),
    "$.target_config.identities[]": ("c", is_token),
    "$.judge_config.values{}": ("c", is_token),
    "$.judge_config.withheld[]": ("a|c", _token_or_named),
    "$.judge_config.identities[]": ("c", is_token),
}

#: The objects whose keys are data rather than the serializer's own field
#: names, and what their keys are. A field name is the serializer's constant and
#: is not checked: a new field shows up as a value at a path `STRINGS` lacks.
KEYS: dict[str, tuple[str, Check]] = {
    "$.artifacts": ("c", is_token),
    "$.target_config.values": ("a|c", _token_or_named),
    "$.judge_config.values": ("a|c", _token_or_named),
    "$.metadata": ("refused", lambda _: False),
    # A verdict's metadata, by the origin of the verdict it sits on, which the
    # walk writes into the path. A builtin verdict's keys are written by
    # digline's code, an open vocabulary of its own: class (a), with no form
    # to check. (ADR 0034 §17.3)
    "$.results[].verdicts[].metadata<builtin>": ("a", _anything),
    "$.results[].verdicts[].metadata<foreign>": ("a|c", _token_or_driver),
    "$.results[].verdicts[].metadata<None>": ("a|c", _token_or_driver),
    "$.aggregate[].metadata<builtin>": ("a", _anything),
    "$.aggregate[].metadata<foreign>": ("a|c", _token_or_driver),
    "$.aggregate[].metadata<None>": ("a|c", _token_or_driver),
}

#: The objects a verdict sits in: the walk reads its `origin` there and writes
#: it into the path of its metadata.
_VERDICTS = frozenset({"$.results[].verdicts[]", "$.aggregate[]"})

#: Every string-typed field of the model, and where it goes in a projection:
#: a path the walk classifies, or why it never reaches one.
_REDACTED = "removed by redact(), so a projection never carries it"
FIELDS: dict[str, str] = {
    "Artifact.sha": _REDACTED + " (the digest goes with the text, ADR 0003 §4)",
    "Artifact.text": _REDACTED,
    "CalibrationBand.check": "$.results[].calibration.check",
    "CalibrationBand.assertion_id": "$.results[].calibration.assertion_id",
    "CaseResult.case_id": "$.results[].case_id",
    "CaseResult.suspended": _REDACTED + "; the fact travels as a boolean",
    "CaseResult.error_kind": "$.results[].error_kind",
    "RecordedResponse.output": _REDACTED + "; the count travels",
    "RecordedResponse.input": _REDACTED + "; the count travels",
    "RecordedResponse.kind": _REDACTED + "; a withheld answer carries no kind",
    "RecordedToolCall.status": _REDACTED + " with its response",
    "RecordedToolCall.result_absence": _REDACTED + " with its response",
    "RecordedToolCall.tool": _REDACTED + " with its response",
    "RecordedToolCall.arguments": _REDACTED + " with its response",
    "RecordedToolCall.result": _REDACTED + " with its response",
    "Run.tenant": "$.tenant",
    "Run.environment": "$.environment",
    "Run.suite": "$.suite",
    "Run.config_hash": "$.config_hash",
    "Run.created_at": "$.created_at",
    "Run.git_commit": "$.git_commit",
    "Run.metadata": "refused in a projection, which keeps none",
    "Run.artifacts": "$.artifacts",
    "Run.pinned": "$.pinned[]",
    "Run.digline_version": "$.digline_version",
    "Run.rejudged_from": "$.rejudged_from",
    "Run.promoted_at": "$.promoted_at",
    "Run.resumed_at": "$.resumed_at[]",
    "Run.modules_unchecked": "$.modules_unchecked[]",
    "Score.name": "$.results[].verdicts[].assertion",
    "Score.metadata": "$.results[].verdicts[].metadata",
    "SystemConfig.values": "$.target_config.values{}",
    "SystemConfig.withheld": "$.target_config.withheld[]",
    "SystemConfig.identities": "$.target_config.identities[]",
    "SystemConfig.named": "$.target_config.named[]",
    "Verdict.reason": _REDACTED + "; a redacted document omits it",
    "Verdict.assertion_id": "$.results[].verdicts[].assertion_id",
    "Verdict.status": "$.results[].verdicts[].status",
    "Verdict.origin": "$.results[].verdicts[].origin",
}


def _projected() -> dict[str, object]:
    """The projection of `test_projection`'s fixture, with the optional strings
    it leaves empty filled in, so their paths are walked too, and with each
    provenance schema 22 records: a foreign verdict with a key of its own, a
    builtin aggregate, and both configurations' `named`."""
    base = promoted()
    first = base.results[0]
    foreign = replace(
        first.verdicts[0],
        origin="foreign",
        score=replace(
            first.verdicts[0].score,
            metadata={**first.verdicts[0].score.metadata, "rossi_hits": 3},
        ),
    )
    aggregate = (
        replace(base.aggregate[0], origin="builtin"),
        *base.aggregate[1:],
    )
    run = replace(
        base,
        results=(
            replace(first, error_kind="raised", verdicts=(foreign,)),
            *base.results[1:],
        ),
        aggregate=aggregate,
        # A key the target's author chose, beside digline's words: a token.
        target_config=replace(
            base.target_config,
            values={**base.target_config.values, "rossi_tenant_flag": 1},
            named=frozenset(base.target_config.values) & NAMED_CONFIG_KEYS,
        ),
        judge_config=replace(
            base.judge_config,
            named=frozenset(base.judge_config.values) & NAMED_CONFIG_KEYS,
        ),
        digline_version="0.33.0",
        git_commit="0123456789abcdef0123456789abcdef01234567",
        resumed_at=("2026-09-30T11:00:00+00:00",),
    )
    return json.loads(run_to_json(project(run, Table())))


def _strings(value: object, path: str) -> Iterator[tuple[str, str, bool]]:
    """Every string in the document: (path, text, whether it is a map key)."""
    if isinstance(value, dict):
        fields = typing.cast(dict[str, object], value)
        data_keys = path in KEYS
        for key, inner in fields.items():
            if data_keys:
                yield path, key, True
                yield from _strings(inner, f"{path}{{}}")
            elif path in _VERDICTS and key == "metadata":
                yield from _strings(inner, f"{path}.metadata<{fields.get('origin')}>")
            else:
                yield from _strings(inner, f"{path}.{key}")
    elif isinstance(value, list):
        for inner in typing.cast(list[object], value):
            yield from _strings(inner, f"{path}[]")
    elif isinstance(value, str):
        yield path, value, False
    # Numbers, booleans and null: exclusion 1. Not decided here.


def test_every_string_a_projection_carries_is_classified() -> None:
    """The first half: fails closed on a path nothing classifies."""
    unclassified: set[str] = set()
    malformed: list[str] = []
    for path, text, is_key in _strings(_projected(), "$"):
        table = KEYS if is_key else STRINGS
        if path not in table:
            unclassified.add(f"{path} ({'key' if is_key else 'value'})")
            continue
        kind, check = table[path]
        if not check(text):
            malformed.append(f"{path}: {text!r} is not class ({kind})")
    assert not unclassified, (
        "strings at paths in none of ADR 0034 §4's three classes: "
        f"{sorted(unclassified)}"
    )
    assert not malformed, malformed


def _string_fields(root: type) -> set[str]:
    def has_str(t: object) -> bool:
        if isinstance(t, typing.TypeAliasType):
            return has_str(t.__value__)
        if typing.get_origin(t) is typing.Literal:
            return any(isinstance(a, str) for a in typing.get_args(t))
        return t is str or any(has_str(a) for a in typing.get_args(t))

    found: set[str] = set()
    seen: set[type] = set()

    def visit(t: object) -> None:
        if isinstance(t, typing.TypeAliasType):
            visit(t.__value__)
            return
        if isinstance(t, type) and dataclasses.is_dataclass(t) and t not in seen:
            seen.add(t)
            hints = typing.get_type_hints(t)
            for field in dataclasses.fields(t):
                if has_str(hints[field.name]):
                    found.add(f"{t.__name__}.{field.name}")
                visit(hints[field.name])
        for argument in typing.get_args(t):
            visit(argument)

    visit(root)
    return found


def test_every_string_field_of_the_model_has_a_place_in_a_projection() -> None:
    """The second half: a field that exists, caught even when it is empty."""
    fields = _string_fields(Run)
    unplaced = fields - set(FIELDS)
    assert not unplaced, (
        "string fields that FIELDS does not place in a projection, or say why "
        f"they never reach one: {sorted(unplaced)}"
    )
    stale = set(FIELDS) - fields
    assert not stale, f"FIELDS names fields the model no longer has: {sorted(stale)}"


def test_every_place_a_field_names_is_classified_or_excluded() -> None:
    """A field placed at a path must be placed somewhere the walk classifies,
    so the two halves cannot drift apart."""
    places = {p for p in FIELDS.values() if p.startswith("$")}
    known = set(STRINGS) | set(KEYS) | {p.split("<")[0] for p in KEYS}
    assert places <= known, sorted(places - known)


def test_the_walk_reaches_every_class() -> None:
    """A guard on the guard: a walk that found no string would pass the first
    half on any document, so it must meet each class at least once."""
    met = {
        STRINGS[path][0]
        for path, _, is_key in _strings(_projected(), "$")
        if not is_key and path in STRINGS
    }
    assert {"a", "b", "c"} <= met <= {"a", "b", "c", "a|c"}, met


def test_the_walk_meets_each_provenance_schema_22_classifies() -> None:
    """The same guard for ADR 0034 §17: a fixture that carried no builtin
    verdict, no foreign key or no named key would pass the first half without
    looking at the rule it is for."""
    keys = [
        (path, text) for path, text, is_key in _strings(_projected(), "$") if is_key
    ]
    by_path = {path for path, _ in keys}
    assert "$.aggregate[].metadata<builtin>" in by_path
    foreign = [text for path, text in keys if path.endswith("metadata<foreign>")]
    assert any(is_token(text) for text in foreign), foreign
    assert any(text in DRIVER_METADATA_KEYS for text in foreign), foreign
    configured = [text for path, text in keys if path == "$.target_config.values"]
    assert "temperature" in configured
    assert any(is_token(text) for text in configured), configured
