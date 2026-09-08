"""A suite that is data (ADR 0007).

The whole of this module is dispatch. It decides **which class** and **with
what arguments**, and it decides nothing else: every rule about what a check
means stays in the class that implements it, every validation stays in the
`__post_init__` that already runs, and the objects that come out are the
objects `suite.py` would have built. That is ADR 0007 §9, and it is what lets a
suite be ported from one form to the other without re-baselining.

Three rules do the work, and they are all driven by the **declared type of the
constructor's field** rather than by a table of special keys:

- a field annotated `frozenset[...]` is written as an array and constructed as
  a frozenset, so the identity matches the Python form character for character;
- a field annotated `Assertion` holds a nested table, built by these same
  rules — which is how `Repeated` nests;
- a field annotated `Judge` or `ClaimJudge` holds a `provider/model`
  coordinate, resolved through the entry point registry;
- a field whose type only Python can supply is a boundary, and the error names
  the way out rather than saying "invalid".

The last one is why a new assertion needs no change here: whatever it declares,
it is either data, a nested assertion, an instrument with coordinates, or
something a TOML file cannot give — and the fourth case has a sentence ready.
"""

from __future__ import annotations

import inspect
import json
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, Field, fields
from pathlib import Path
from typing import Any, cast

from digline.cli.errors import UsageError
from digline.cli.toml_errors import (
    code_only,
    computed_body,
    listing,
    missing_parameters,
    not_a_coordinate,
    object_parameter,
    unknown_key,
    unknown_type,
)
from digline.core import (
    F1,
    Accuracy,
    Affix,
    Contains,
    CostBudget,
    Equals,
    Faithfulness,
    IsJson,
    JsonSchema,
    LatencyBudget,
    Length,
    Levenshtein,
    NotContains,
    PiiAbsent,
    Precision,
    Recall,
    Regex,
    Repeated,
)
from digline.core import (
    LlmRubric as LlmRubricAssertion,
)
from digline.run import Case, Suite, Target
from digline.targets import HttpTarget, ProviderNotFound, resolve, split_coordinate

__all__ = [
    "AGGREGATES",
    "ASSERTIONS",
    "PYTHON_ONLY",
    "SUITE_SUFFIX",
    "load_toml_suite",
]

#: What makes the CLI read a suite as data rather than import it.
SUITE_SUFFIX = ".toml"

#: Token → class, for a check about one case. The token is the name the check
#: already carries in every report and every baseline, so a reader who has seen
#: the output can write the file (ADR 0007 §1). The two whose name is derived
#: rather than declared — `Affix` becomes `starts_with` or `ends_with`, and
#: `Repeated` takes the name of what it wraps — are keyed by their class.
ASSERTIONS: Mapping[str, type] = {
    "equals": Equals,
    "contains": Contains,
    "not_contains": NotContains,
    "affix": Affix,
    "is_json": IsJson,
    "json_schema": JsonSchema,
    "length": Length,
    "levenshtein": Levenshtein,
    "regex": Regex,
    "llm_rubric": LlmRubricAssertion,
    "faithfulness": Faithfulness,
    "pii_absent": PiiAbsent,
    "cost_budget": CostBudget,
    "latency_budget": LatencyBudget,
    "repeated": Repeated,
}

#: Token → class, for a verdict about the whole run. Written in the same list
#: as the others and routed to `Suite.run_assertions` here, so the author never
#: has to know that the object model keeps them apart (ADR 0007 §2).
AGGREGATES: Mapping[str, type] = {
    "precision": Precision,
    "recall": Recall,
    "accuracy": Accuracy,
    "f1": F1,
}

#: Tokens that name a real check which no data file can build, and the sentence
#: each one gets. Recognised on purpose: "there is no check called
#: `from_autoevals`" would be a lie, and it would send a reader hunting for a
#: spelling when what they need to know is that the check is code.
PYTHON_ONLY: Mapping[str, str] = {
    "from_autoevals": "`from_autoevals` needs a scorer, which is a Python object",
}

#: A constructor field whose type no data file can supply, and the sentence
#: that says so. Keyed by the annotation exactly as the dataclass declares it.
CODE_ONLY: Mapping[str, str] = {
    "AutoevalsScorer": "a scorer, which is a Python object",
    "tuple[PiiPattern, ...]": "PII patterns, which carry a checksum function",
}

#: Parameters a plugin exposes that are credentials. A suite file is a file
#: that gets committed, and ADR 0004 §5 resolves keys through the SDK's own
#: environment lookup precisely so that no digline object holds one — so the
#: format has no way to write this, and says so rather than passing it along.
CREDENTIALS = frozenset({"api_key"})

#: The two instrument protocols, and which factory on a `Provider` builds one.
#: ADR 0004 §1 makes every plugin ship both, so one coordinate answers for
#: either — `LlmRubric` wants the first, `Faithfulness` the second.
INSTRUMENTS = {"Judge": "judge", "ClaimJudge": "claim_judge"}


def load_toml_suite(path: Path) -> tuple[Suite, Target]:
    """The suite and its target, from a file that is data.

    Returns both because a TOML suite has no module for `--target` to look in:
    the target is declared in `[target]`, and that is the only one there is.
    """
    document = _parse(path)
    where = path.name

    _refuse_unknown(
        document, {"suite", "target", "assertions"}, f"{where}, top level", "table"
    )
    table = _table(document, "suite", where)
    assertions, aggregates = _assertions(document, where)

    suite_keys = _init_fields(Suite)
    _refuse_unknown(
        table,
        set(suite_keys) - {"assertions", "run_assertions"},
        f"{where}, [suite]",
        "key",
    )
    if "disclosure" in table:
        raise UsageError(
            f"{where}, [suite]: `disclosure` is not settable from a data file. "
            "What a Disclosure widens is what leaves the perimeter, and a "
            "suite that is data cannot widen it — that is ADR 0007 §7, and in "
            "world 3 it is a security property. A suite that genuinely needs "
            "to disclose more is a suite.py."
        )
    if "cases" not in table:
        raise UsageError(
            f"{where}, [suite]: no `cases`. Cases are always a file — "
            '`cases = "cases.json"` — because a suite is rules and cases are '
            "data, and a diff has to say which one moved (ADR 0007 §4)"
        )

    declared = dict(table)
    declared["cases"] = _cases(path.parent / str(declared.pop("cases")), where)
    if "artifacts" in declared:
        declared["artifacts"] = [
            Path(str(entry))
            for entry in _sequence(declared["artifacts"], "artifacts", where)
        ]

    try:
        # `cast` because a parsed document is `object` all the way down and
        # the constructor is what checks it — which is the point: the same
        # `__post_init__` the Python form runs, running here (ADR 0007 §6).
        suite = Suite(
            assertions=assertions,
            run_assertions=aggregates,
            **cast("Any", declared),
        )
    except TypeError as exc:
        raise UsageError(f"{where}, [suite]: {exc}") from exc
    except ValueError as exc:
        # The suite's own load-time refusals, unchanged and unduplicated: a
        # TOML suite that samples without min_agreement fails with the sentence
        # the Python form already fails with (ADR 0007 §6).
        raise UsageError(f"{where}: {exc}") from exc

    return suite, _target(document, path)


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #


def _parse(path: Path) -> Mapping[str, object]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path} is not valid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise UsageError(f"{path} is not UTF-8: {exc}") from exc


def _table(
    document: Mapping[str, object], key: str, where: str
) -> Mapping[str, object]:
    found = document.get(key)
    if found is None:
        raise UsageError(f"{where}: no [{key}] table, and every suite needs one")
    if not isinstance(found, Mapping):
        raise UsageError(f"{where}: [{key}] is a {type(found).__name__}, not a table")
    return cast("Mapping[str, object]", found)


def _sequence(value: object, key: str, where: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise UsageError(
            f"{where}: `{key}` is a {type(value).__name__}, and it has to be an array"
        )
    return cast("Sequence[object]", value)


# --------------------------------------------------------------------------- #
# Assertions, in one ordered list
# --------------------------------------------------------------------------- #


def _assertions(
    document: Mapping[str, object], where: str
) -> tuple[list[Any], list[Any]]:
    entries = document.get("assertions")
    if entries is None:
        raise UsageError(
            f"{where}: no [[assertions]]. A run that checks nothing passes "
            "vacuously, which is what fixed decision 3 forbids"
        )
    per_case: list[Any] = []
    per_run: list[Any] = []
    for index, entry in enumerate(_sequence(entries, "assertions", where), start=1):
        spot = f"{where}, [[assertions]] #{index}"
        if not isinstance(entry, Mapping):
            raise UsageError(f"{spot}: this entry is not a table")
        built, is_aggregate = _one(cast("Mapping[str, object]", entry), spot)
        (per_run if is_aggregate else per_case).append(built)
    return per_case, per_run


def _one(entry: Mapping[str, object], where: str) -> tuple[Any, bool]:
    """One `[[assertions]]` entry: the type selects the class, everything else
    is a constructor argument."""
    token = entry.get("type")
    if token is None:
        raise UsageError(
            f"{where}: no `type`, so nothing says which check this is.\n"
            f"  per case: {listing(ASSERTIONS)}\n"
            f"  per run:  {listing(AGGREGATES)}"
        )
    if not isinstance(token, str):
        raise UsageError(f"{where}: `type` is a {type(token).__name__}, not a name")

    if (cause := PYTHON_ONLY.get(token)) is not None:
        raise code_only(cause, where=where)

    aggregate = token in AGGREGATES
    cls = AGGREGATES.get(token) or ASSERTIONS.get(token)
    if cls is None:
        raise unknown_type(token, where=where, per_case=ASSERTIONS, per_run=AGGREGATES)

    arguments = {key: value for key, value in entry.items() if key != "type"}
    return _construct(cls, arguments, where, token), aggregate


def _construct(
    cls: type, arguments: Mapping[str, object], where: str, token: str
) -> Any:
    """Build one object: coerce what the field's type asks for, refuse what it
    cannot be given, and let the class do the rest."""
    declared = _init_fields(cls)
    _refuse_unknown(arguments, set(declared), where, "parameter", token=token)

    prepared: dict[str, object] = {}
    for key, value in arguments.items():
        prepared[key] = _value(declared[key], value, where, key, token)

    missing = [
        name
        for name, field in declared.items()
        if name not in prepared
        and field.default is MISSING
        and field.default_factory is MISSING
    ]
    if missing:
        raise missing_parameters(missing, where=where, token=token)
    try:
        return cls(**prepared)
    except (TypeError, ValueError) as exc:
        raise UsageError(f"{where}, `{token}`: {exc}") from exc


def _value(
    field: Field[Any], value: object, where: str, key: str, token: str
) -> object:
    """One argument, converted to what the field declares — and nothing more."""
    annotation = _annotation(field)

    if (reason := CODE_ONLY.get(annotation)) is not None:
        raise code_only(f"`{token}` takes `{key}` as {reason}", where=where)

    if annotation.startswith("frozenset"):
        # An array in, a frozenset out. Not cosmetic: `config_hash` fingerprints
        # field values, and a list where the Python form holds a frozenset is a
        # different fingerprint for the same suite (ADR 0007 §1, §9).
        if not isinstance(value, list):
            raise UsageError(
                f"{where}: `{key}` is a {type(value).__name__}, and it has to "
                "be an array"
            )
        return frozenset(cast("list[object]", value))

    if annotation == "Assertion":
        # `Repeated.inner`. The same rules, applied again: the loader still
        # interprets nothing, it dispatches recursively (ADR 0007 §1).
        if not isinstance(value, Mapping):
            raise UsageError(
                f"{where}: `{key}` is a {type(value).__name__}, and it has to "
                f"be a table — the check to wrap, written as one:\n\n"
                f'  [assertions.{key}]\n  type = "llm_rubric"\n  ...'
            )
        inner, is_aggregate = _one(
            cast("Mapping[str, object]", value), f"{where}, [{key}]"
        )
        if is_aggregate:
            raise UsageError(
                f"{where}: `{key}` is an aggregate, which is a verdict about "
                "the whole run and cannot be wrapped in a per-case check"
            )
        return inner

    if (factory := INSTRUMENTS.get(annotation)) is not None:
        return _instrument(value, factory, where, key)

    return value


def _instrument(value: object, factory: str, where: str, key: str) -> object:
    """A judge, from its coordinates (ADR 0007 §3)."""
    if isinstance(value, Mapping):
        # A table is how somebody asks for a judge with settings — a
        # max_tokens, a temperature. The coordinate carries the instrument's
        # identity and nothing else (ADR 0007 §3), so this is a boundary rather
        # than a typo, and it gets a boundary's sentence.
        raise code_only(
            f"`{key}` is a table, and a judge named in data is its coordinate "
            "alone: it grades with the plugin's own defaults, and a judge set "
            "up differently is an object",
            where=where,
            kind="judges",
        )
    if not isinstance(value, str):
        raise UsageError(
            f"{where}: `{key}` is a {type(value).__name__}. A judge is named "
            'by coordinates — provider/model, as in "anthropic/'
            'claude-haiku-4-5".'
        )
    if "/" not in value:
        raise not_a_coordinate(value, where=where, key=key)
    try:
        provider_name, model = split_coordinate(value, field=f"{where}: `{key}`")
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    try:
        provider = resolve(provider_name)
    except ProviderNotFound as exc:
        raise UsageError(f"{where}: {exc}") from exc
    build = getattr(provider, factory)
    try:
        # By keyword, always: a plugin's factory is a class whose positional
        # order is its own business — every published target takes
        # `prompt_file` first — and `model` is the one name the contract fixes.
        return build(model=model)
    except (TypeError, ValueError) as exc:
        raise UsageError(
            f"{where}: {provider_name} could not be set up as a judge for "
            f"{model!r}: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# Cases, always a file
# --------------------------------------------------------------------------- #


def _cases(path: Path, where: str) -> list[Case]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(
            f"{where}, [suite]: the cases file {path.name} could not be read "
            f"at {path}: {exc}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise UsageError(
            f"{path.name} holds a {type(payload).__name__}; the cases file is "
            "an array of case objects"
        )

    declared = _init_fields(Case)
    built: list[Case] = []
    for index, entry in enumerate(cast("list[object]", payload), start=1):
        spot = f"{path.name} #{index}"
        if not isinstance(entry, Mapping):
            raise UsageError(f"{spot}: this entry is not an object")
        arguments = cast("Mapping[str, object]", entry)
        _refuse_unknown(arguments, set(declared), spot, "field")
        try:
            built.append(Case(**cast("Any", arguments)))
        except (TypeError, ValueError) as exc:
            raise UsageError(f"{spot}: {exc}") from exc
    return built


# --------------------------------------------------------------------------- #
# The target: two forms, and there is no third
# --------------------------------------------------------------------------- #


def _target(document: Mapping[str, object], path: Path) -> Target:
    where = f"{path.name}, [target]"
    table = _table(document, "target", path.name)
    kind = table.get("type")
    if kind is None:
        raise UsageError(
            f'{where}: no `type`. It is either "http" — an endpoint digline '
            'posts to — or "provider", a model named by coordinates'
        )
    arguments = {key: value for key, value in table.items() if key != "type"}
    if kind == "http":
        return _http(arguments, where, path.parent)
    if kind == "provider":
        return _provider(arguments, where, path.parent)
    raise UsageError(
        f'{where}: `type` is {kind!r}, and there are two forms — "http" and '
        '"provider". A target that is a function is a suite.py: there is no '
        "third form, deliberately (ADR 0007 §5)."
    )


def _http(arguments: Mapping[str, object], where: str, base: Path) -> Target:
    if "request" in arguments:
        raise computed_body(where)
    _refuse_credentials(arguments, where)
    # Checked here rather than left to the constructor: a `TypeError` about an
    # unexpected keyword argument is the bare Python error every other position
    # in this format is careful not to show.
    _refuse_unknown(
        arguments, _accepted(HttpTarget) - {"request"}, where, "parameter", "http"
    )
    try:
        return HttpTarget(**cast("Any", _resolve_paths(arguments, HttpTarget, base)))
    except (TypeError, ValueError) as exc:
        raise UsageError(f"{where}: {exc}") from exc


def _provider(arguments: Mapping[str, object], where: str, base: Path) -> Target:
    coordinate = arguments.get("provider")
    if not isinstance(coordinate, str):
        raise UsageError(
            f'{where}: a provider target needs `provider = "anthropic/'
            'claude-haiku-4-5"` — the provider, a slash, and the model'
        )
    try:
        provider_name, model = split_coordinate(
            coordinate, field=f"{where}: `provider`"
        )
        provider = resolve(provider_name)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    except ProviderNotFound as exc:
        raise UsageError(f"{where}: {exc}") from exc

    rest = {key: value for key, value in arguments.items() if key != "provider"}
    if "model" in rest:
        raise UsageError(
            f"{where}: `model` is the second half of `provider`, so writing it "
            "again would be two sources for one fact. It is "
            f'"{provider_name}/<model>" and nothing else.'
        )
    _refuse_credentials(rest, where)
    for injected in ("client", "pricing"):
        if injected in rest:
            raise object_parameter(injected, where=where, provider=provider_name)
    # Against what the plugin *names*, so a plugin with a `**kwargs` bucket
    # does not quietly swallow a misspelling. ADR 0007 §5 admits "only the
    # parameters the plugin already exposes as declarative configuration", and
    # a bucket exposes nothing.
    _refuse_unknown(
        rest,
        _accepted(provider.target) - {"model", "client", "pricing", *CREDENTIALS},
        where,
        "parameter",
        provider_name,
    )
    try:
        settled = _resolve_paths(rest, provider.target, base)
        return provider.target(model=model, **cast("Any", settled))
    except (TypeError, ValueError) as exc:
        raise UsageError(
            f"{where}: {provider_name} refused this set-up: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# Shared
# --------------------------------------------------------------------------- #


def _resolve_paths(
    arguments: Mapping[str, object], factory: object, base: Path
) -> dict[str, object]:
    """A relative path in a suite file is relative to **the suite file**.

    `cases` already works this way and so do `Suite.artifacts`: the CLI resolves
    them against the suite's own directory, because that is where a prompt sits
    next to the suite that names it. Resolving against the working directory
    instead would make a suite runnable from one place only — and CI, the
    container and a colleague's checkout are all somewhere else.

    Driven by the parameter's declared type, like every other conversion here: a
    `str | Path` is a path, and a plugin that adds one gets this for free.
    """
    try:
        signature = inspect.signature(cast("Any", factory))
    except (TypeError, ValueError):  # pragma: no cover - a C-level callable
        return dict(arguments)
    resolved = dict(arguments)
    for name, parameter in signature.parameters.items():
        annotation = parameter.annotation
        declared = (
            annotation
            if isinstance(annotation, str)
            else getattr(annotation, "__name__", "")
        )
        given = resolved.get(name)
        if "Path" in declared and isinstance(given, str):
            candidate = Path(given)
            if not candidate.is_absolute():
                resolved[name] = base / candidate
    return resolved


def _accepted(factory: object) -> set[str]:
    """The parameter names a callable names, `self` and `**kwargs` aside.

    A `**kwargs` bucket is deliberately not treated as "anything goes": what it
    would buy is a plugin quietly accepting `temperture`, and what it would
    cost is the guarantee that a key in a suite file reaches the model.
    """
    try:
        signature = inspect.signature(cast("Any", factory))
    except (TypeError, ValueError):  # pragma: no cover - a C-level callable
        return set()
    return {
        name
        for name, parameter in signature.parameters.items()
        if name != "self" and parameter.kind is not parameter.VAR_KEYWORD
    }


def _refuse_credentials(arguments: Mapping[str, object], where: str) -> None:
    """A key never appears in a suite file, and this is the one place that
    could have let one in."""
    for key in arguments:
        if key in CREDENTIALS:
            raise UsageError(
                f"{where}: `{key}` is a credential, and a suite file is a file "
                "that gets committed. Leave it out: the provider's own SDK "
                "reads it from the environment, which is why no digline object "
                "holds one (ADR 0004 §5). A key is the one payload no "
                "Disclosure can release."
            )


def _init_fields(cls: type) -> dict[str, Field[Any]]:
    """The constructor's own parameters.

    `init=False` fields are excluded, which is what makes `threshold` on a
    `repeated` entry an unknown parameter rather than a silent no-op: `Repeated`
    copies its threshold from what it wraps, and a file that set one would be
    stating something that cannot be true.
    """
    return {f.name: f for f in fields(cast("Any", cls)) if f.init}


def _annotation(field: Field[Any]) -> str:
    """The field's declared type, as written.

    A string, because every module here uses `from __future__ import
    annotations` — which is the reason this reads the annotation rather than
    resolving it: resolution would need every name in scope at runtime, to
    answer a question the text already answers.
    """
    return (
        field.type
        if isinstance(field.type, str)
        else getattr(field.type, "__name__", "")
    )


def _refuse_unknown(
    given: Mapping[str, object],
    allowed: set[str],
    where: str,
    noun: str,
    token: str | None = None,
) -> None:
    """An unknown key is a load error, never a warning and never ignored.

    A silently dropped `treshold` is a check running on its default — and for a
    threshold, the default a typo falls back to is the one that passes. That is
    fixed decision 3's vacuously green assertion in configuration form.

    The message is built in `toml_errors`; what is decided here is only that
    there is no third option beside "known" and "refused".
    """
    if error := unknown_key(given, allowed, where=where, noun=noun, owner=token):
        raise error
