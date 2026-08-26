"""What is declared: the cases, and the suite that judges them.

A `Suite` is a declaration, not an execution. It says who the results belong to,
where they were produced, what is checked and on what — and nothing about how to
produce them, which is the `Target`'s business.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from digline.core import (
    NOTHING_EXTRA,
    Assertion,
    Disclosure,
    Label,
    Output,
    RunAssertion,
    config_hash,
)
from digline.core.ratio import Ratio, as_agreement

__all__ = ["Case", "Suite"]


@dataclass(frozen=True, slots=True)
class Case:
    """One test case: data, never execution.

    `id` is the key `compare()` pairs on, so it deserves the same care as an
    assertion name: renaming it shows up in the diff as a `new` plus a
    `missing`. In world 1 the developer chooses it and answers for it — these
    are their own test data. On the production-to-repository bridge nobody
    chooses it: digline generates it, and there is no parameter through
    which an application identifier could be passed (ADR 0002 §5).

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

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Case.id must not be empty")
        if self.suspended is not None and not self.suspended:
            raise ValueError(
                f"case {self.id!r} is suspended without a stated reason: "
                "a suspension nobody can justify is a case quietly dropped"
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

        self._check_aggregates()

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
