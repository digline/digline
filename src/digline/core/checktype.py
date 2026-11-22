"""The type a check was declared with, as a verdict records it.

A run records a check's name and its identity, and neither says what kind of
check it is: the identity is a digest, and two checks of different types may
carry one name. The comparison of a re-judge with the run it was made from
pairs verdicts by name, and must never pair two whose types differ, so the
type is recorded on each verdict from schema 25. (ADR 0067 §1 (d), as noted
2026-11-22)
"""

from __future__ import annotations

from collections.abc import Mapping

from digline.core.adapters import FromAutoevals
from digline.core.aggregate import F1, Accuracy, Precision, Recall
from digline.core.assertions import (
    Affix,
    Before,
    Contains,
    CostBudget,
    Equals,
    Faithfulness,
    IsJson,
    JsonSchema,
    LatencyBudget,
    Length,
    Levenshtein,
    LlmRubric,
    MaxSteps,
    Never,
    NotContains,
    PiiAbsent,
    Regex,
    Subsequence,
    ToolCalledWith,
    ToolsCalled,
)
from digline.core.sampling import Repeated
from digline.core.types import CheckType

__all__ = ["TYPE_OF_CLASS", "check_type"]

#: Class → the word a `suite.toml` builds it from. Exact classes: a subclass a
#: suite writes is the suite's check, not digline's, and has no word.
TYPE_OF_CLASS: Mapping[type, CheckType] = {
    Equals: "equals",
    Contains: "contains",
    NotContains: "not_contains",
    Affix: "affix",
    IsJson: "is_json",
    JsonSchema: "json_schema",
    Length: "length",
    Levenshtein: "levenshtein",
    Regex: "regex",
    ToolCalledWith: "tool_called_with",
    ToolsCalled: "tools_called",
    Subsequence: "subsequence",
    Before: "before",
    Never: "never",
    MaxSteps: "max_steps",
    LlmRubric: "llm_rubric",
    Faithfulness: "faithfulness",
    PiiAbsent: "pii_absent",
    CostBudget: "cost_budget",
    LatencyBudget: "latency_budget",
    FromAutoevals: "from_autoevals",
    Precision: "precision",
    Recall: "recall",
    Accuracy: "accuracy",
    F1: "f1",
}


def check_type(assertion: object) -> CheckType | None:
    """The word for `assertion`'s type, or `None` where digline has none.

    Read through `Repeated` to what it wraps, as `judged()` and `origin()`
    are: a check asked three times is the same kind of check asked once, and
    its verdicts are read as that check's. Nothing is guessed for a class
    digline did not write: `None` is *not recorded*, never a type.
    """
    current: object = assertion
    while isinstance(current, Repeated):
        current = current.inner
    return TYPE_OF_CLASS.get(type(current))
