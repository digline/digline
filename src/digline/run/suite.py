"""What is declared: the cases, and the suite that judges them.

A `Suite` is a declaration, not an execution. It says who the results belong to,
where they were produced, what is checked and on what — and nothing about how to
produce them, which is the `Target`'s business.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import cast

from digline.core import (
    GROUP_MARKER,
    NOTHING_EXTRA,
    Assertion,
    Disclosure,
    Label,
    Output,
    Repeated,
    RunAssertion,
    config_hash,
    expand_by_group,
)
from digline.core.ratio import Ratio, as_agreement

__all__ = ["CallPlan", "Case", "Suite", "planned_calls"]


@dataclass(frozen=True, slots=True)
class Case:
    """One test case: data, never execution.

    `id` is the key `compare()` pairs on, so it deserves the same care as an
    assertion name: renaming it shows up in the diff as a `new` plus a
    `missing`. In world 1 the developer chooses it and answers for it — these
    are their own test data. On the production-to-repository bridge nobody
    chooses it: digline generates it, and there is no parameter through
    which an application identifier could be passed (ADR 0002 §5).

    `expected` is the value the output is compared against, and it is either
    absent or a real expectation: `None` says the case has nothing to compare
    against, while `""` claims an expectation that every empty output meets.
    The empty one is refused — absence is not emptiness.

    `metadata` is payload unless the suite's `Disclosure` says otherwise, and it
    never reaches a `Score`: an assertion writes its own metadata from what it
    measured.

    `suspended` sets the case aside with a stated reason. The driver does not
    invoke the assertions on it — the skip belongs to the driver, per ADR 0001 —
    but the run records it, so the suspension travels through the store and
    reaches the report instead of showing up as coverage that quietly shrank.

    The reason is mandatory: an empty one is refused for the same cause as an
    empty `Verdict.reason`. And it is payload — a developer writes things like
    "fails on the Rossi account" — so it is redacted at a boundary.
    """

    id: str
    vars: Mapping[str, object] = field(default_factory=dict[str, object])
    expected: Output | None = None
    context: Sequence[str] = ()
    metadata: Mapping[str, object] = field(default_factory=dict[str, object])
    suspended: str | None = None
    #: The human mark, when the suite has ground truth. Required on every case
    #: as soon as a `RunAssertion` counts a confusion matrix.
    label: Label | None = None
    #: Which class this case belongs to — an expense category, a language, a
    #: customer segment. **Descriptive, never behavioural**: nothing about
    #: execution changes, no target and no assertion is given it, and a suite
    #: that sets `by_group` nowhere behaves as if the field did not exist. It is
    #: read in one place, `Suite.__post_init__`, and read there as a label.
    #:
    #: `None` means the case belongs to no group, and is counted only in the
    #: whole-run aggregate: there is no implicit "ungrouped" bucket, which would
    #: be a gate nobody declared, appearing and vanishing as cases were
    #: labelled. (ADR 0010 §1, §2)
    group: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Case.id must not be empty")
        if self.suspended is not None and not self.suspended:
            raise ValueError(
                f"case {self.id!r} is suspended without a stated reason: "
                "a suspension nobody can justify is a case quietly dropped"
            )
        if self.expected is not None and not self.expected:
            # `None` says "this case has no expected value"; `""` claims there
            # *is* one and that it is nothing. The second is the vacuously
            # green assertion by another route: `levenshtein` scores an empty
            # expected against an empty output as a perfect 1.0 — both
            # behaviours defensible on their own, composing into a check that
            # cannot fail. Refused here rather than in the assertions, because
            # it is the case that is malformed. (fixed decision 3)
            raise ValueError(
                f"case {self.id!r} declares an empty expected: an empty "
                "expectation is a perfect match against an empty output. "
                "Leave it unset if the case has nothing to compare against — "
                "absence is not emptiness"
            )
        if self.group is not None and not self.group:
            # `None` and `""` would otherwise be two spellings of "no group"
            # with different consequences: the empty one names a group, so it
            # would expand into `precision[group=]`, a gate nobody can read.
            raise ValueError(
                f"case {self.id!r} declares an empty group: leave it unset to "
                "put the case in no group"
            )


@dataclass(frozen=True, slots=True)
class Suite:
    """The declared suite: whose results these are, where they were produced,
    what is checked and on what.

    `tenant` and `environment` live here rather than on `execute()` because they
    are properties of *what is being evaluated and for whom*, not of a single
    launch. Passing them per call would make it possible to run one declared
    suite under two different perimeters by a slip of the hand, which is exactly
    the boundary ADR 0002 exists to make uncrossable by accident.

    `disclosure` lives here for the same reason, and literally: the ADR says it
    must be declared in the suite's code and never read from data.

    `samples` asks the target more than once per case and folds the verdicts,
    which is how *system* noise — the same input answered differently — becomes
    a measurement instead of a surprise. For *judge* noise, wrap the assertion
    in `Repeated`: that is the same output graded repeatedly, a different
    question.

    `min_agreement` is mandatory as soon as `samples > 1`, for the same reason
    `LlmRubric.tolerance` is: a threshold on a noisy value that nobody chose is
    a green light nobody gave.
    """

    tenant: str
    environment: str
    name: str
    assertions: Sequence[Assertion]
    cases: Sequence[Case]
    disclosure: Disclosure = NOTHING_EXTRA
    samples: int = 1
    #: A count of samples, so `"2/3"` and `Fraction(2, 3)` are accepted and a
    #: float that no `k/samples` can produce is refused at construction.
    min_agreement: Ratio | None = None
    #: Verdicts about the run rather than about a case — precision, recall.
    #: Each one names, in `over`, the per-case check whose verdict it counts.
    run_assertions: Sequence[RunAssertion] = ()
    #: The files that *are* the thing under test — the prompt above all.
    #: Declared, never discovered: a file that counts as evidence is a file
    #: someone named. Nothing here opens them; the CLI reads them and hands the
    #: contents to `execute()`, as it already does for the clock and for git.
    #: They do not enter `config_hash`: changing a prompt must stay comparable,
    #: because that comparison is the experiment. (ADR 0003)
    #:
    #: A `str` is accepted where a `Path` is meant and coerced on construction,
    #: as the TOML loader already coerces by declared type; anything else is
    #: refused here, by field name, rather than at read time.
    artifacts: Sequence[Path] = ()

    def __post_init__(self) -> None:
        if not self.tenant:
            raise ValueError("Suite.tenant must not be empty")
        if not self.environment:
            raise ValueError("Suite.environment must not be empty")
        if not self.name:
            raise ValueError("Suite.name must not be empty")
        if not self.assertions:
            raise ValueError(
                f"suite {self.name!r} declares no assertions: a run that checks "
                "nothing passes vacuously, which is what fixed decision 3 forbids"
            )
        if not self.cases:
            raise ValueError(f"suite {self.name!r} declares no cases")
        # Before the duplicate check below, so `"prompt.md"` and
        # `Path("prompt.md")` are one artifact declared twice rather than two.
        object.__setattr__(
            self, "artifacts", _as_paths(self.artifacts, suite=self.name)
        )
        if len({str(p) for p in self.artifacts}) != len(self.artifacts):
            raise ValueError(
                f"suite {self.name!r} declares the same artifact twice: the "
                "path is the key a run files it under"
            )
        if self.samples < 1:
            raise ValueError(
                f"suite {self.name!r} asks for {self.samples} samples: at least "
                "one call per case is needed to judge anything"
            )
        if self.samples > 1 and self.min_agreement is None:
            raise ValueError(
                f"suite {self.name!r} samples {self.samples} times without "
                "declaring min_agreement. Sampling measures how much the system "
                "wobbles; without a stated floor nobody has said how much wobble "
                "is acceptable, and the answer would default to 'any'"
            )
        if self.min_agreement is not None:
            object.__setattr__(
                self,
                "min_agreement",
                as_agreement(
                    self.min_agreement,
                    samples=self.samples,
                    field=f"suite {self.name!r} min_agreement",
                ),
            )

        # Two cases sharing an id collide in the key `compare()` pairs on, and
        # the second would silently replace the first. It is the family of
        # positional mistakes already closed on the assertion side, reopened
        # from the case side.
        seen: set[str] = set()
        for case in self.cases:
            if case.id in seen:
                raise ValueError(
                    f"suite {self.name!r} declares case id {case.id!r} twice: "
                    "ids are how a result finds its counterpart in the baseline"
                )
            seen.add(case.id)

        # Validated on the *declared* set, so a refusal names what the author
        # wrote rather than a copy the expansion made.
        self._check_aggregates()
        # And expanded after, into the field the rest of the product reads:
        # `config_hash()` below, and the driver. So a data suite gets §2 with
        # no line in the loader, and `run_assertions` is longer than what was
        # written — deterministically, whole-run instance first. (ADR 0010 §6)
        object.__setattr__(
            self,
            "run_assertions",
            expand_by_group(self.run_assertions, self.groups()),
        )

    def groups(self) -> tuple[str, ...]:
        """The groups the cases declare, sorted and without repetition.

        Sorted here rather than in `expand_by_group`, which takes the order it
        is given: the core is not the layer that decides a group set exists at
        all. Sorted at all because it fixes the expansion's order, and with it
        the identity set, the `config_hash` and the report's columns.
        """
        return tuple(sorted({c.group for c in self.cases if c.group is not None}))

    def _check_aggregates(self) -> None:
        """`over` must name exactly one declared assertion, and labels must be
        there when something counts them.

        Absent and ambiguous are the same mistake seen from two sides. A name
        that matches nothing aggregates over an empty set; a name that matches
        two — and two `contains` in one suite is the ordinary case, which is why
        `compare()` pairs on identity rather than on names — aggregates over
        whichever came first. Both produce a number that looks like an answer.
        """
        for aggregate in self.run_assertions:
            if GROUP_MARKER in aggregate.name:
                raise ValueError(
                    f"aggregate {aggregate.name!r} writes {GROUP_MARKER!r} in "
                    "its own name, which is the form an expanded aggregate "
                    "takes. Two checks could then arrive under one name, which "
                    "is what identity exists to prevent and what the run grid "
                    "would silently merge. Set by_group=True and let the "
                    "expansion name them"
                )
            matches = [a for a in self.assertions if a.name == aggregate.over]
            if not matches:
                available = ", ".join(sorted({a.name for a in self.assertions}))
                raise ValueError(
                    f"{aggregate.name!r} aggregates over {aggregate.over!r}, "
                    f"which no assertion in suite {self.name!r} is called. "
                    f"Declared: {available}"
                )
            if len(matches) > 1:
                raise ValueError(
                    f"{aggregate.name!r} aggregates over {aggregate.over!r}, "
                    f"which {len(matches)} assertions in suite {self.name!r} "
                    "share. Give the one you mean a distinct `name`: an "
                    "aggregate cannot choose between them, and picking the "
                    "first would be a number that looks like an answer"
                )

        if not any(a.requires_label for a in self.run_assertions):
            return
        unlabelled = sorted(c.id for c in self.cases if c.label is None)
        if unlabelled:
            raise ValueError(
                f"suite {self.name!r} declares an aggregate that counts a "
                f"confusion matrix, so every case needs a label. Missing on: "
                f"{', '.join(unlabelled)}"
            )

    def config_hash(self) -> str:
        """Fingerprint of the configuration — assertions, aggregates,
        thresholds, tolerances, and how many times each case is sampled. Not the
        cases: they change on their own schedule."""
        return config_hash(
            self.assertions,
            samples=self.samples,
            min_agreement=(
                None if self.min_agreement is None else float(self.min_agreement)
            ),
            run_assertions=self.run_assertions,
        )


def _as_paths(values: object, *, suite: str) -> tuple[Path, ...]:
    """`artifacts=["prompt.md"]` is what a reader writes; `Sequence[Path]` is
    what the field declares.

    The same rule the TOML loader applies — a field that declares a `Path`
    accepts a `str` — extended from the data form to the Python constructor
    rather than written a second time. Without it the `str` travels: nothing
    here refuses it, and it surfaces later and elsewhere as `AttributeError:
    'str' object has no attribute 'is_absolute'`, raised inside
    `read_artifacts` at run time, naming neither the suite nor the field.

    What cannot be coerced is refused **by field name**, which is the fallback
    the loader's own errors model: a locator, a cause, a way out.
    """
    if not isinstance(values, Iterable) or isinstance(values, str | bytes):
        # A `str` is itself a `Sequence` — of characters — so `artifacts="p.md"`
        # would iterate into five one-letter paths instead of failing. It is the
        # one wrong value this rule would otherwise accept enthusiastically,
        # and it is grouped here with what cannot be iterated at all so that
        # neither escapes as a bare `TypeError` from the loop below.
        raise ValueError(
            f"suite {suite!r} declares `artifacts` as `{type(values).__name__}`"
            ": it is a list of the files under test, one str or Path each — "
            'write ["p.md"]'
        )
    coerced: list[Path] = []
    for entry in cast("Sequence[object]", values):
        if isinstance(entry, str):
            coerced.append(Path(entry))
        elif isinstance(entry, Path):
            coerced.append(entry)
        else:
            raise ValueError(
                f"suite {suite!r} declares `artifacts` entry {len(coerced)} "
                f"as `{type(entry).__name__}`: an artifact is the file that is "
                "the thing under test, and it is named by a str or a Path"
            )
    return tuple(coerced)


@dataclass(frozen=True, slots=True)
class CallPlan:
    """What a run is about to cost in calls, before the first one is made.

    Arithmetic over the declared suite — no provider, no price list, no protocol
    change — and it is the figure that surprises people: twenty cases at
    `samples=5` is a hundred calls, not twenty. (ADR 0006 §8)

    A **money** estimate is deliberately not here. `Pricing.cost` needs a
    `Usage`, which does not exist before the call, so an estimate would have to
    come from the target — an optional `estimate_usd(...)` alongside
    `preflight()` — and that is a change to the `digline.run` protocols and
    therefore a release of every plugin. Deferred to an ADR of its own, not
    refused. What was *actually* spent is already recorded and the report shows
    it.
    """

    #: Cases that will actually be called: a suspended one is never asked.
    cases: int
    samples: int
    #: `(assertion name, how many times it repeats)` for every `Repeated` in the
    #: suite, sorted. Named rather than summed into one multiplier, because
    #: "each answer is judged 3 times" is only true of the assertion that says
    #: so — and nothing here claims to know which of the others call a model.
    repeats: tuple[tuple[str, int], ...] = ()

    @property
    def target_calls(self) -> int:
        return self.cases * self.samples

    def sentence(self) -> str:
        """One line for a terminal, in English like every other runtime string.

        The report is the declared exception to that rule because it is a
        document with a recipient; this is a diagnostic on the way to a run.
        """
        text = (
            f"{_count(self.cases, 'case')} × {_count(self.samples, 'sample')} = "
            f"{_count(self.target_calls, 'call')} to the target"
        )
        for name, count in self.repeats:
            text += f"; each answer is judged {count} times by {name}"
        return text


def _count(number: int, noun: str) -> str:
    """`1 case`, `20 cases`. A line printed on every run is worth the three
    lines it takes not to say "1 cases"."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _repeats(assertions: Sequence[Assertion]) -> tuple[tuple[str, int], ...]:
    """Every `Repeated` in the suite, wrappers followed through.

    The same walk `judge_config` performs, and for the same reason: a `Repeated`
    may sit inside another wrapper, and a count that only looked at the top level
    would announce a bill smaller than the one that arrives.
    """
    found: list[tuple[str, int]] = []
    seen: set[int] = set()
    stack: list[object] = list(assertions)
    while stack:
        current = stack.pop()
        if (
            id(current) in seen
            or not is_dataclass(current)
            or isinstance(current, type)
        ):
            continue
        seen.add(id(current))
        if isinstance(current, Repeated):
            found.append((current.name, current.samples))
        for declared in fields(current):
            value = getattr(current, declared.name, None)
            if is_dataclass(value) and not isinstance(value, type):
                stack.append(value)
    return tuple(sorted(found))


def planned_calls(suite: Suite) -> CallPlan:
    """How many calls `suite` is about to make. Pure, and declared-only.

    A suspended case is not counted because it is not called — the driver
    returns its `CaseResult` without touching the target — and announcing a
    number that includes it would be an announcement nobody could reconcile with
    the invoice.
    """
    return CallPlan(
        cases=sum(1 for case in suite.cases if case.suspended is None),
        samples=suite.samples,
        repeats=_repeats(suite.assertions),
    )
