"""Every place `digline.core` names a configuration key by its text is listed.

A projection turns configuration keys into tokens (ADR 0034 §4), and the core
names some of those keys by their literal text. **A check of that shape is born
broken against the projection**: on a projected document the key is not there
to find, so the check either fires on every projection or passes on every one
without looking. #263's sweep found four such checks after they were written;
this file is so the fifth is found when it is.

The keys are derived from the four sets that name them, so a key added to one
of those sets is watched from that moment. A use is a string literal equal to
one of those keys, or a reference to a set of them — check 1 of the sweep read
`SYSTEM_NAME_FIELDS`, not `"provider"`, and a guard on literals alone would
have missed the instance that motivated it.

**What this proves, and what it does not.** A green here means every such use
is on the list below with a reason somebody wrote beside it. It does not mean
the reason is right. Scope: `digline.core` only, which is where the checks a
document meets at construction live. The same keys are read by text in
`targets`, `host`, `report` and `wire`, and none of those is watched here.

Outside that scope, a sweep of `report`, `wire`, `host`, `cli` and `run` for
these keys and sets found three kinds of use, and none of them is watched here
either:

- **Sentences that came out false on a projected document**, repaired in #275.
  The report chose a verb or a headline by finding a key in `OBSERVED_FIELDS`,
  and a token is never there. The choice is now one that stays true when the
  lookup misses: `render.field_verb` says "recorded" for a token's key, and the
  headline counts the withheld fields rather than naming one. That was not ADR
  0034 §15's question, as this file used to say: §15 is an accepted rule, and
  a false sentence breaks it whatever a reader loses.
- **A qualification lost in silence**, left as it is. `render.echoed_model`
  finds `"resolved_model"` and `"model"` by text, so on a projection the
  "echoed" clause is dropped without a word. Nothing false is said: something
  is lost, and what a reader at the software house loses is §15's question.
- **A crash, repaired in #402.** `report.log.sighting` read
  `values["provider"]`, which raised on a projected baseline, and the
  membership tests after it had #275's shape. It now returns the absence
  `projected` before any key is read by text. The repair also found a lookup
  by **verdict name**, `report.log._aggregate`, which a sweep for
  configuration keys cannot find: a projected reference names its aggregates
  by tokens, so the flip check missed in silence. Neither is watched here.

The sweep was a search for the literal keys and the names of the sets. A key
read through a variable would not show up in it.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from collections import Counter
from pathlib import Path

import digline.core
from digline.core.run import (
    ENDPOINT_PERIMETER_FIELDS,
    OBSERVED_FIELDS,
    PERIMETER_FIELDS,
    SYSTEM_NAME_FIELDS,
)

KEYS: frozenset[str] = (
    SYSTEM_NAME_FIELDS | PERIMETER_FIELDS | ENDPOINT_PERIMETER_FIELDS | OBSERVED_FIELDS
)

#: A use: the module, the enclosing class and function, and the key, or the
#: name of the set of keys, prefixed with `@`. Keyed by where the use sits
#: rather than by line number, so an edit above it moves nothing here.
type Use = tuple[str, str, str]

#: Every known use, how many times it occurs, and why it holds on a projected
#: document. Somebody wrote each reason while looking at the check.
KNOWN: dict[Use, tuple[int, str]] = {
    ("digline.core.run", "SystemConfig.__post_init__", "@SYSTEM_NAME_FIELDS"): (
        1,
        "the presence check, skipped when `projected` (#263 check 1, relaxed "
        "together with check 2)",
    ),
    ("digline.core.run", "SystemConfig.__post_init__", "provider"): (
        1,
        "the identity check, after the return on `projected` (#263 check 2)",
    ),
    ("digline.core.run", "SystemConfig.__post_init__", "model"): (
        1,
        "the identity check, after the return on `projected` (#263 check 2)",
    ),
    ("digline.core.run", "SystemConfig._at_named_endpoint", "base_url"): (
        2,
        "reads false on a projected document; the widening it decides happens "
        "during redaction, which `project` runs first, while every key is text "
        "(#263, check 3's route and its correction)",
    ),
    ("digline.core.run", "SystemConfig.perimeter", "@PERIMETER_FIELDS"): (
        2,
        "called by redaction, which `project` runs before it tokenises: the "
        "perimeter keys are withheld while they are still text (#263 check 3)",
    ),
    ("digline.core.run", "SystemConfig.perimeter", "@ENDPOINT_PERIMETER_FIELDS"): (
        1,
        "as `PERIMETER_FIELDS` beside it (#263 check 3)",
    ),
    ("digline.core.run", "pricing_digest", "model"): (
        1,
        "a key the digest writes into its own input; it reads no configuration",
    ),
}


def _key_sets(module: object) -> frozenset[str]:
    """The module-level names bound to a set of configuration keys: the four
    sources, and any set they are built from (`DECLARED_PRICE_FIELDS`).
    Derived rather than listed, so a new one is a use from the moment it
    exists."""
    return frozenset(
        name
        for name, value in vars(module).items()
        if isinstance(value, frozenset)
        and value
        and all(isinstance(key, str) and key in KEYS for key in value)  # pyright: ignore[reportUnknownVariableType]
    )


def _uses(module_name: str) -> Counter[Use]:
    module = importlib.import_module(module_name)
    path = Path(str(module.__file__))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sets = _key_sets(module)
    found: Counter[Use] = Counter()

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            # A set's own definition is where the keys come from, not a use.
            if (
                not scope
                and isinstance(child, ast.Assign | ast.AnnAssign)
                and any(
                    isinstance(target, ast.Name) and target.id in sets
                    for target in (
                        child.targets
                        if isinstance(child, ast.Assign)
                        else [child.target]
                    )
                )
            ):
                continue
            inner = scope
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                inner = (*scope, child.name)
            where = ".".join(inner) or "<module>"
            if (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value in KEYS
            ):
                found[(module_name, where, child.value)] += 1
            elif isinstance(child, ast.Name) and child.id in sets:
                found[(module_name, where, f"@{child.id}")] += 1
            visit(child, inner)

    visit(tree, ())
    return found


def _core_uses() -> Counter[Use]:
    found: Counter[Use] = Counter()
    for info in pkgutil.walk_packages(digline.core.__path__, "digline.core."):
        found += _uses(info.name)
    return found + _uses("digline.core")


_WHAT_A_GREEN_PROVES = (
    "A green here proves that somebody looked at each place the core reads a "
    "configuration key by its text, and wrote down why it holds on a projected "
    "document. It does not prove that the reason is right."
)


def test_every_key_the_core_names_by_its_text_is_listed() -> None:
    found = _core_uses()
    new = sorted(
        f"{module} {where} {key!r} x{count - known}"
        for (module, where, key), count in found.items()
        if count > (known := KNOWN.get((module, where, key), (0, ""))[0])
    )
    assert not new, (
        "digline.core names a configuration key by its text in a place nobody "
        f"has looked at yet: {'; '.join(new)}. A projection turns these keys "
        "into tokens, so a check that reads one either fires on every "
        "projected document or passes on every one without looking (#263's "
        "sweep). Look at the check, and add it to KNOWN in this file with the "
        "reason it holds on a projected document. " + _WHAT_A_GREEN_PROVES
    )


def test_every_listed_use_still_exists() -> None:
    """The control on the test above. An entry whose use is gone is a reason
    nobody is reading any more, and a list that only grows stops being read."""
    found = _core_uses()
    stale = sorted(
        f"{module} {where} {key!r}"
        for (module, where, key), (count, _) in KNOWN.items()
        if found[(module, where, key)] < count
    )
    assert not stale, (
        f"KNOWN lists uses the core no longer has, or not that many times: "
        f"{'; '.join(stale)}. Remove or correct the entry: the reason beside "
        "it described a check that has changed. " + _WHAT_A_GREEN_PROVES
    )


def test_the_keys_are_the_four_sources() -> None:
    """A control on the derivation: an empty `KEYS` would make both tests
    above pass on a core that names every key there is."""
    assert {"provider", "model", "base_url", "fingerprint", "resolved_model"} <= KEYS
    assert "input_per_mtok" in KEYS
