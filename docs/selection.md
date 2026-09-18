# Testing a selection

Some systems do not produce an answer, they produce a **choice**: which items,
from a set that was in the input. An assistant picking documents to cite, a
router picking a tool, a recommender picking products, a briefing picking the
morning's activities. For those the verdict is not in the text. It is in the
relation between what was chosen and what was offered.

The [Handbook's chapter on ground truth](https://digline.dev/handbook/03-ground-truth/)
explains why that relation can be checked only once the selection is data
rather than prose. This page assumes it is, and shows the two ways to check it
with what digline ships today. Every file on this page is written, and every
command run, by a test.

## Declare the offered set, and the rest follows

There are two checks, not four.

- **`within`** — every chosen id was offered. Nothing invented.
- **`includes`** — every id this case requires was chosen. The thing that
  must appear, appears.

The other two properties you want are not separate checks. They follow from
declaring the offered set:

- **Nothing from a set that was not offered** — another user's items, another
  tenant's, a document this user may not see — is `within`. An id from
  somewhere else is, by definition, not in this case's offered set. There is
  nothing extra to write, and nothing extra to keep in step.
- **An empty input yields an empty selection** is a *case*, not a check: offer
  nothing (`offered: []`), and `within` can only pass on an empty selection.

That is the strength of the approach: one declaration per case — what was
offered, what must appear — and two small checks cover all four properties.

Where you declare it decides the format. A set that is the **same for every
case** is written once, and works in a `suite.py` or a `suite.toml`
(recipe 1). A set **declared per case** needs a check of your own, and that
means a `suite.py`: no `suite.toml` can do it today (recipe 2).

## An empty selection passes `within`

**Read this before either recipe.** `within` asks "was anything chosen that
should not have been?", and a model that chooses nothing has chosen nothing
wrong. An empty selection passes it **on every case**. It is an absence check,
like `NotContains` and `PiiAbsent`: silence satisfies all three.

So a model that stops selecting anything — a prompt change that makes it
cautious, a failed call parsed as an empty list — keeps `within` green on the
whole suite. That is the vacuously green assertion digline refuses everywhere
else, arrived at from the data rather than from a default.

**Always pair `within` with `includes`.** `includes` is the check silence
fails: a case that requires an item cannot be satisfied by choosing nothing.
The second recipe enforces the pairing. `includes` reports `error` on a case
that offers items and requires none, because on that case it could not catch
a model that went silent.

## The selection has to be an object

A check reads the selection out of the target's output, and the output is one of
three shapes: text, a mapping, or a conversation. **A bare list is none of
them.** A target that returns `["inv-204", "task-88"]` has every check on the
case answer:

```text
output of type list is not a valid Output (expected str, Mapping or Sequence[Message])
```

Wrap it: `{"selected": [...]}`. If your model already answers with an object,
there is nothing to do. If it answers with a list, wrap it where you parse the
reply: `{"selected": json.loads(text)}`.

## Recipe 1: a fixed catalogue

When every case chooses from the **same** set — a help centre's articles, a
router's tools, a closed product catalogue — the shipped `JsonSchema` expresses
both checks, because the set can be written into the schema once.

```python
# helpdesk.py
"""Your model call. Canned, so this page needs no key."""

CITATIONS = {
    "refund-late": '{"selected": ["refund-policy", "shipping-times"]}',
    "refund-damaged": '{"selected": ["refund-policy", "refund-policy-2019"]}',
    "refund-gift": '{"selected": [], "note": "see internal-gift-exceptions"}',
}


def cite(case_id: str) -> str:
    return CITATIONS[case_id]
```

```python
# citations.py
"""The suite: refund questions, answered by citing the help centre."""

import helpdesk
from digline.core import JsonSchema, NotContains
from digline.run import Case, Response, Suite

CATALOGUE = ["refund-policy", "shipping-times", "warranty", "size-guide"]


def target(case: Case) -> Response:
    return Response(output=helpdesk.cite(case.id))


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="citations",
    assertions=[
        JsonSchema(
            name="cited_from_catalogue",
            schema={
                "type": "object",
                "required": ["selected"],
                "properties": {
                    "selected": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {"enum": CATALOGUE},
                    }
                },
            },
        ),
        JsonSchema(
            name="cited_refund_policy",
            schema={
                "required": ["selected"],
                "properties": {"selected": {"contains": {"const": "refund-policy"}}},
            },
        ),
        NotContains(name="no_internal_note", needle="internal-"),
    ],
    cases=[
        Case(id="refund-late"),
        Case(id="refund-damaged"),
        Case(id="refund-gift"),
    ],
)
```

```console
$ digline run --suite citations.py
2026-09-17T08-32-44-150771-00-00-0e5431e45b7809fb

$ digline explain --suite citations.py --run latest
What it found
refund-damaged · cited_from_catalogue is under its bar at 0.000000. The bar is 1.000000.
refund-gift · cited_refund_policy is under its bar at 0.000000. The bar is 1.000000.
refund-gift · no_internal_note is under its bar at 0.000000. The bar is 1.000000.
```

- `"items": {"enum": CATALOGUE}` is `within`. `refund-damaged` cited an article
  that does not exist.
- `"contains": {"const": ...}` is `includes`. `refund-gift` chose nothing, and
  **`cited_from_catalogue` passed it**: the warning above, on a real case. Only
  `cited_refund_policy` caught the silence.
- `NotContains` is not a selection check. It scans the **whole text**, so it
  catches an id that reached the answer outside `selected` — here, an internal
  note's name in a free-text field. Use it for a prefix that must never appear
  at all.

This recipe has one limit. The required item is written into the schema, so it
is the same for every case in the suite. When what must appear differs per case,
you are in recipe 2.

It is the one recipe on this page that also works as a
[`suite.toml`](declarative.md). `json_schema` and `not_contains` are both in the
format, with the schema written as nested tables. The `output_path` must point
at the reply's **text**: `not_contains` refuses a mapping.

## Recipe 2: a set that differs per case

A briefing chooses from *this user's* items today. A citation assistant
chooses from *the documents retrieved for this question*. The offered set is
different on every case, so it cannot live in a schema written once. It has to
be declared on the case, and read by a check of your own.

**This recipe is Python only.** It needs a `suite.py`: a `suite.toml` cannot
declare a custom assertion, so it cannot run the check below. The limits are
spelled out at the end of this page.

**Where the set is declared.** A check never sees `case.vars`: those fill the
prompt. What it does see is `case.metadata`, which arrives as
`inputs.metadata["case"]`. So the offered and required ids go in `metadata`.

The file you copy is the check:

```python
# selection.py
"""A selection checked against the set it was chosen from, declared per case."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal, cast

from digline.core import (
    STRUCTURED_ONLY,
    AssertionBase,
    CheckKind,
    EvaluatorInputs,
    OutputKind,
    Verdict,
)


@dataclass(frozen=True, slots=True)
class Selection(AssertionBase):
    """`within`: every chosen id was offered.

    `includes`: every id the case requires was chosen.
    """

    rule: Literal["within", "includes"]
    name: str = "selection"
    KIND: ClassVar[CheckKind] = "deterministic"
    threshold: float = 1.0
    tolerance: float = 0.0
    accepts: frozenset[OutputKind] = STRUCTURED_ONLY

    def __call__(self, inputs: EvaluatorInputs) -> Verdict:
        if (err := self._accept(inputs.output)) is not None:
            return err
        # `_accept` has just proved the output is a mapping; pyright cannot see it.
        output = cast(Mapping[str, object], inputs.output)
        case = cast(Mapping[str, object], inputs.metadata.get("case", {}))
        chosen = _ids(output, "selected")
        offered = _ids(case, "offered")
        required = _ids(case, "required")
        if chosen is None or offered is None or required is None:
            # Absent is not empty: a missing list is a question nobody can answer.
            return self._error(
                "'selected' in the output, or 'offered' or 'required' in the "
                "case metadata, is missing or is not a list of strings"
            )
        if self.rule == "within":
            stray = [i for i in chosen if i not in offered]
            why = f"{len(stray)} of {len(chosen)} chosen id(s) were not offered"
        elif offered and not required:
            return self._error(
                "the case offers items and requires none: an empty selection "
                "would pass it, so it cannot catch a model that went silent"
            )
        else:
            stray = [i for i in required if i not in chosen]
            why = f"{len(stray)} of {len(required)} required id(s) were not chosen"
        # Counts only, never the ids: they are the end company's data.
        return self._graded(
            0.0 if stray else 1.0,
            why,
            metadata={"chosen": len(chosen), "missing": len(stray)},
        )


def _ids(found: Mapping[str, object], key: str) -> Sequence[str] | None:
    value = found.get(key)
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    # No silent conversions: `3` is not the id `"3"`.
    if not all(isinstance(item, str) for item in items):
        return None
    return cast(list[str], items)
```

**The file is 74 lines, and the two comparisons are two of them** — the two
`stray = ...` lines. Almost everything else is a house rule, not decoration.
Each one is there because leaving it out produces a verdict that is wrong
without saying so. Copy them with the comparisons:

- **Absent is not empty.** A reply with no `selected`, or a case that declares
  no `offered`, is `error`: the question could not be asked. `[]` is an answer.
- **No silent conversions.** `_ids` refuses a list holding anything but
  strings, because `3` is not the id `"3"`, and a check that converts would
  pass or fail for reasons the author never wrote.
- **Silence cannot pass `includes`.** A case that offers items and requires
  none is `error`, not `pass`, for the reason in the warning above. This is the
  rule that makes the pairing hold even for a reader who never read the warning.
- **The ids never leave.** The reason and `Score.metadata` carry counts, never
  the ids themselves: an id is the end company's data, and a verdict crosses
  boundaries a payload does not.
- **One class with a parameter**, not two. The rules differ by one comparison,
  and everything around them would otherwise be written twice.

The suite:

```python
# planner.py
"""Your model call. Canned, so this page needs no key."""

BRIEFS = {
    "dana-monday": '{"selected": ["inv-204", "task-88"]}',
    "dana-tuesday": '{"selected": ["mtg-312", "inv-517"]}',
    "eli-monday": '{"selected": []}',
    "eli-holiday": '{"selected": []}',
}


def brief(case_id: str) -> str:
    return BRIEFS[case_id]
```

```python
# briefing.py
"""The suite: each user's morning, what was offered, and what must appear."""

import json

import planner
from digline.run import Case, Response, Suite
from selection import Selection


def case(case_id: str, offered: list[str], required: list[str]) -> Case:
    # One list, written once. `vars` is what the prompt shows the model;
    # `metadata` is what the check reads. Two copies typed by hand drift apart.
    return Case(
        id=case_id,
        vars={"items": offered},
        metadata={"offered": offered, "required": required},
    )


def target(case: Case) -> Response:
    # The model answers text; the check judges a shape. Parse it here.
    return Response(output=json.loads(planner.brief(case.id)))


suite = Suite(
    tenant="northwind",
    environment="staging",
    name="briefing",
    assertions=[
        Selection(rule="within", name="chosen_were_offered"),
        Selection(rule="includes", name="required_was_chosen"),
    ],
    cases=[
        case("dana-monday", ["inv-204", "mtg-311", "task-88"], ["inv-204"]),
        case("dana-tuesday", ["mtg-312", "task-90"], ["mtg-312"]),
        case("eli-monday", ["inv-517", "task-12"], ["inv-517"]),
        case("eli-holiday", [], []),
    ],
)
```

```console
$ digline run --suite briefing.py
2026-09-17T08-32-51-690217-00-00-03a15ef2396a5f1f

$ digline explain --suite briefing.py --run latest
What it found
dana-tuesday · chosen_were_offered is under its bar at 0.000000. The bar is 1.000000.
eli-monday · required_was_chosen is under its bar at 0.000000. The bar is 1.000000.
```

Case by case:

- **`dana-monday`** chose two of her own items, including the required one. Both
  pass.
- **`dana-tuesday`** chose `inv-517`, which is **Eli's**. No check was written
  for "another user's data": `within` caught it, because it was not offered to
  Dana. That is the property that follows from the declaration.
- **`eli-monday`** chose nothing. `chosen_were_offered` **passed** it, and only
  `required_was_chosen` failed. Without the pairing this case is green.
- **`eli-holiday`** was offered nothing and chose nothing: the empty-input case,
  written as a case. Had the model chosen anything, `within` would have failed.

`case()` builds `vars` and `metadata` from **one** list, and that is
deliberate. The model is shown the ids through `vars`, and the check reads them
from `metadata`. Typed twice, the two copies drift, and a check against a set
the model was never shown passes or fails for reasons that have nothing to do
with the model. When your cases come from a file rather than from code, build
both from the same field when you load them.

## Where this stops

- **Recipe 2 is Python only.** A [`suite.toml`](declarative.md) has no custom
  assertions, and its provider targets have no `parse`: the reply reaches the
  checks as text, and nothing can turn it into the object this check reads.
- **The shape is yours to hold.** Both recipes assume the selection is a list
  of string ids under one key. Ids inside objects (`{"id": ..., "reason": ...}`)
  mean changing `_ids` in your copy, and the schema in recipe 1.
- **Ordering is not here.** Whether the urgent item came first is a question for
  a judge ([`LlmRubric`](metrics.md)), or for a third rule you add yourself. The
  handbook explains why it is the one part that is not stable across days.
