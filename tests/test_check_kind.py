"""`KIND` says what a check is, and changes nothing about what it checks.

`KIND` is a `ClassVar`, so `dataclasses.fields()` does not see it, and
`identity` and `config_hash` are built from those fields. That is the argument;
these are the evidence, taken two ways:

- **Pinned values.** One instance of every exported check, with fixed
  parameters, and the `identity` each had — plus the `config_hash` of all of
  them together — computed on `origin/main` at 413f66b, before `KIND` existed.
- **The committed baselines.** Every example ships one, promoted by a digline
  that had no `KIND`. Each suite is loaded as `digline run` would load it, and
  its `config_hash` must be the one the baseline recorded — `promote` refuses a
  run whose hash differs — and every `assertion_id` the baseline holds must
  still be produced, or `compare` would stop pairing the verdicts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, get_args

import pytest

import digline.core as core
from digline.core import (
    F1,
    Accuracy,
    Affix,
    Assertion,
    CheckKind,
    ClaimReply,
    Contains,
    CostBudget,
    Equals,
    Faithfulness,
    FromAutoevals,
    IsJson,
    JsonSchema,
    JudgeReply,
    LatencyBudget,
    Length,
    Levenshtein,
    LlmRubric,
    NotContains,
    PiiAbsent,
    Precision,
    Recall,
    Regex,
    Repeated,
    RunAssertion,
    ToolCalledWith,
    ToolsCalled,
    config_hash,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINES = sorted(ROOT.glob("examples/*/.digline/*/baselines/*.json"))


def judge(prompt: str) -> JudgeReply:
    raise AssertionError("never called: only the identity is read")


def claims(prompt: str) -> ClaimReply:
    raise AssertionError("never called: only the identity is read")


def scorer(output: Any, expected: Any = None, **kwargs: Any) -> Any:
    raise AssertionError("never called: only the identity is read")


CONTAINS = Contains(needle="Northwind")

PER_CASE: list[Assertion] = [
    Equals(),
    CONTAINS,
    NotContains(needle="password"),
    Affix(affix="Dear"),
    Regex(pattern=r"\d+"),
    IsJson(),
    JsonSchema(schema={"type": "object"}),
    Length(maximum=280),
    Levenshtein(),
    PiiAbsent(),
    ToolsCalled(expected=["lookup"]),
    ToolCalledWith(tool="lookup", arguments={"id": 1}),
    LlmRubric(rubric="polite", judge=judge, threshold=0.7, tolerance=0.1),
    Faithfulness(judge=claims, threshold=0.8, tolerance=0.1),
    FromAutoevals(scorer=scorer, threshold=0.5, tolerance=0.1),
    CostBudget(max_usd=0.01, tolerance=0.05),
    LatencyBudget(max_ms=2000, tolerance=0.05),
    Repeated(inner=CONTAINS, samples=3, min_agreement="2/3"),
]

PER_RUN: list[RunAssertion] = [
    Precision(over="contains", threshold="3/4", tolerance="1/20"),
    Recall(over="contains", threshold="3/4", tolerance="1/20"),
    Accuracy(over="contains", threshold="3/4", tolerance="1/20"),
    F1(over="contains", threshold="3/4", tolerance="1/20"),
]

#: Computed before `KIND` existed. Never regenerate these to make a test pass:
#: a moved value here is every stored baseline refusing to promote.
PINNED_IDENTITY = {
    "Equals": "8949d4f38793e974",
    "Contains": "88a931f8f1842070",
    "NotContains": "3dfd6bc30055337a",
    "Affix": "53dc4220d6324c96",
    "Regex": "f51cb4113514ec2e",
    "IsJson": "22f70df7274e1fd7",
    "JsonSchema": "04e75688ee9ba056",
    "Length": "510e3d393aae974d",
    "Levenshtein": "9831ae8fdaf2e736",
    "PiiAbsent": "26aa28fe0511db05",
    "ToolsCalled": "3dd906e1af504b81",
    "ToolCalledWith": "c3858696255bd4c0",
    "LlmRubric": "8ee6f54f82a4159a",
    "Faithfulness": "50e57c1831bfeaed",
    "FromAutoevals": "514154c995907893",
    "CostBudget": "1ce7dd96f1671c89",
    "LatencyBudget": "8615e202964028ec",
    "Repeated": "cabbf7b8bcbc2d95",
    "Precision": "eb1dc4b65364eb3d",
    "Recall": "20c8a5a64464ceec",
    "Accuracy": "ddb968366023a5a1",
    "F1": "635076508520de16",
}
PINNED_CONFIG_HASH = "9dad4100423ffde4"


def exported() -> list[type]:
    bases = (core.AssertionBase, core.RunAssertionBase)
    return [
        obj
        for name in core.__all__
        if isinstance(obj := getattr(core, name), type)
        and issubclass(obj, bases)
        and obj not in bases
    ]


@pytest.mark.parametrize("cls", exported(), ids=lambda cls: cls.__name__)
def test_every_exported_check_declares_its_own_kind(cls: type) -> None:
    """On the class itself: a subclass inheriting its parent's kind would say
    nothing about what it was made into."""
    assert "KIND" in vars(cls), f"{cls.__name__} declares no KIND"
    assert vars(cls)["KIND"] in get_args(CheckKind.__value__)


def test_the_bases_declare_kind_without_a_value() -> None:
    for base in (core.AssertionBase, core.RunAssertionBase):
        assert "KIND" in base.__annotations__
        assert "KIND" not in vars(base)


def test_every_exported_check_has_a_pinned_identity() -> None:
    """A new export has no *before* to pin, but it gets one the day it lands,
    so that whatever comes after it is held to the same test."""
    assert {cls.__name__ for cls in exported()} == set(PINNED_IDENTITY)
    assert [type(a).__name__ for a in [*PER_CASE, *PER_RUN]] == list(PINNED_IDENTITY)


@pytest.mark.parametrize(
    "check", [*PER_CASE, *PER_RUN], ids=lambda check: type(check).__name__
)
def test_kind_leaves_the_identity_where_it_was(check: Assertion | RunAssertion) -> None:
    assert check.identity == PINNED_IDENTITY[type(check).__name__]


def test_kind_leaves_the_config_hash_where_it_was() -> None:
    assert config_hash(PER_CASE, run_assertions=PER_RUN) == PINNED_CONFIG_HASH


#: Run in the example's own directory and in a process of its own: four
#: examples import a module called `app`, and one interpreter can hold only one.
_READ_SUITE = """
import json, sys
from pathlib import Path
from digline.host.loader import load_suite, load_target
from digline.host.measure import price_digest_of

spec = sys.argv[1]
suite, loaded = load_suite(spec, root=Path.cwd())
target = load_target(None, loaded, spec)
print(json.dumps({
    "config_hash": suite.config_hash(pricing=price_digest_of(target)),
    "identities": sorted(
        {a.identity for a in suite.assertions}
        | {a.identity for a in suite.run_assertions}
    ),
}))
"""


def test_every_example_ships_a_baseline() -> None:
    assert len(BASELINES) >= 10, BASELINES


@pytest.mark.parametrize(
    "baseline", BASELINES, ids=lambda path: path.relative_to(ROOT).parts[1]
)
def test_no_committed_baseline_needs_promoting_again(baseline: Path) -> None:
    example = baseline.parents[3]
    spec = "suite.toml" if (example / "suite.toml").is_file() else "suite.py"
    read = subprocess.run(
        [sys.executable, "-c", _READ_SUITE, spec],
        cwd=example,
        capture_output=True,
        text=True,
        check=False,
    )
    assert read.returncode == 0, read.stderr
    suite = json.loads(read.stdout)
    document = json.loads(baseline.read_text(encoding="utf-8"))

    assert suite["config_hash"] == document["config_hash"]
    stored = {v["assertion_id"] for r in document["results"] for v in r["verdicts"]}
    stored |= {a["assertion_id"] for a in document.get("aggregate", [])}
    assert stored <= set(suite["identities"]), stored - set(suite["identities"])
