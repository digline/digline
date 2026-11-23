"""The reviewed answer, as the document holds it: a check, a person's yes or
no, and whether the judge agreed. (ADR 0059 §1)

A reviewed answer is an answer the application gave and a person's yes or no
about it. Only the judged check it names runs on it, and the expected verdict
is the person's: for a yes the check passes, for a no it does not. A judge that
contradicts the person fails the case, in the gate. It is a failure of its own,
exit `1`, and not `scale_lost`: a calibration band sits strictly between 0 and
1, and a yes or a no asks for an extreme.

What lives here is the half that crosses into a run: which check, by identity
and by name, and the person's yes or no. The answer itself is payload, declared
in `digline.run.ReviewedAnswer`, and it is never written.

**Since schema 25 (ADR 0067 §1, §2, §4)** a reviewed answer may also be:

- **awaiting a verdict**: `good` is `None`. The judge judged it and the person
  has not yet, so it is in no gate: `contradicted` passes over it;
- **about the whole answer**: `check` is `None`, and every judged check of the
  suite ran on it, by identity in `judged`. `good` is the overall yes or no,
  and `failing` the identities of the checks the person expected to fail on a
  no; every other judged check is expected to pass;
- **revised**: `good` and `failing` are then the person's verdict after she
  read the disagreements, the one the gate holds, and `revised` says so. Her
  blind verdict is kept beside it: on an answer about one check it is the
  other answer, since a revision that says the same is refused; on the whole
  answer it is `blind_failing`, the checks she first expected to fail, empty
  for a blind yes;
- **held out**: `held_out` is the role the person chose for it when she chose
  it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from digline.core.refused import NameRef, Written

if TYPE_CHECKING:
    # Only for the annotation: `run.py` imports `Reviewed` from here, so a
    # runtime import the other way would be a cycle.
    from digline.core.run import Run
    from digline.core.stability import Instability, Stability

__all__ = [
    "Against",
    "AgreementReading",
    "AgreementTally",
    "CheckAgreement",
    "Composite",
    "CompositeMismatch",
    "Contradiction",
    "Disagreement",
    "Reviewed",
    "contradicted",
    "reviewed_agreement",
]

#: How a judge contradicted a person: it passed an answer the person said no
#: to, or failed one the person said yes to. The two are counted apart, because
#: a judge too lenient and a judge too strict are two different faults.
type Against = Literal["passed_no", "failed_yes"]


@dataclass(frozen=True, slots=True)
class Reviewed:
    """Which judged check a reviewed answer is for, and what the person said.

    **`assertion_id` is what binds, `check` is what is said**, for the reason
    `CalibrationBand` gives: a verdict's `score.name` is the assertion's
    choice, and binding on it could match nothing and read as *the judge
    agreed*. (ADR 0024 §4.7, amended 2026-09-26)

    `good` is the person's yes, `True`, or no, `False`, and nothing else; or
    `None`, an answer awaiting the person's verdict, which no gate reads
    (ADR 0067 §1 (a)). Where the person revised her verdict it is the revised
    one, the verdict the gate holds, and `revised` is `True` (ADR 0067 §2).

    **Two forms** (ADR 0067 §4). About one check: `check` and `assertion_id`
    name it, and `judged` and `failing` are empty. About the whole answer:
    `check` and `assertion_id` are `None`, `judged` holds the identity of
    every judged check that ran on it, and `failing`, a part of `judged`, the
    ones the person expected to fail. Only a no names any.
    """

    check: str | None
    assertion_id: str | None
    good: bool | None
    revised: bool = False
    held_out: bool = False
    judged: tuple[str, ...] = ()
    failing: tuple[str, ...] = ()
    #: On a revised verdict about the whole answer, the identities of the
    #: checks the blind verdict expected to fail: empty where it was a yes.
    #: The blind agreement is read against it. (ADR 0067 §2)
    blind_failing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        whole = self.check is None
        if whole != (self.assertion_id is None):
            raise ValueError(
                "a reviewed answer names a check and its identity together, or "
                "neither, for an answer reviewed as a whole"
            )
        if self.check is not None and not self.check:
            raise ValueError(
                "a reviewed answer names no check: the person's yes or no is "
                "about one judged assertion, or about the whole answer"
            )
        if self.assertion_id is not None and not self.assertion_id:
            raise ValueError(
                Written.said(
                    "the reviewed answer for ",
                    NameRef("calibration_check", self.check or ""),
                    " carries no assertion_id: it binds to its verdict by "
                    "identity, and one with none binds to nothing",
                )
            )
        # `bool` and nothing that is merely truthy: a person said yes or no,
        # or has not said yet.
        if self.good is not None and type(self.good) is not bool:  # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError(
                Written.said(
                    "the reviewed answer for ",
                    NameRef("calibration_check", self.check or ""),
                    f" carries good={self.good!r}: good is true or false, the "
                    "person's yes or no",
                )
            )
        object.__setattr__(self, "judged", tuple(self.judged))
        object.__setattr__(self, "failing", tuple(self.failing))
        object.__setattr__(self, "blind_failing", tuple(self.blind_failing))
        if self.blind_failing and not (whole and self.revised):
            raise ValueError(
                "a reviewed answer carries the blind verdict's failing checks "
                "beside a verdict that is not a revision about the whole answer"
            )
        if not set(self.blind_failing) <= set(self.judged):
            raise ValueError(
                "a reviewed answer's blind verdict expects a check to fail that "
                "did not run on it: `blind_failing` is a part of `judged`"
            )
        if not whole and (self.judged or self.failing):
            raise ValueError(
                "a reviewed answer about one check carries no `judged` and no "
                "`failing`: those are the whole answer's"
            )
        if whole and not self.judged:
            raise ValueError(
                "a reviewed answer about the whole answer names no judged "
                "check: every judged check of the suite runs on it"
            )
        if not set(self.failing) <= set(self.judged):
            raise ValueError(
                "a reviewed answer expects a check to fail that did not run on "
                "it: `failing` is a part of `judged`"
            )
        if self.failing and self.good is not False:
            raise ValueError(
                "a reviewed answer names checks expected to fail beside a "
                "verdict that is not a no"
            )
        if whole and self.good is False and not self.failing:
            raise ValueError(
                "a no about the whole answer names no check expected to fail: "
                "a no that does not say which part was wrong expects nothing "
                "of any check"
            )
        if self.good is None and self.revised:
            raise ValueError(
                "a reviewed answer awaiting a verdict cannot have been revised"
            )

    @property
    def awaiting(self) -> bool:
        """No verdict from the person yet: in no gate. (ADR 0067 §1 (a))"""
        return self.good is None

    @property
    def blind(self) -> tuple[bool | None, tuple[str, ...]]:
        """The person's blind verdict and the identities it expected to fail:
        the verdict itself where it was not revised. (ADR 0067 §2)"""
        if not self.revised:
            return self.good, self.failing
        if self.check is not None:
            return (None if self.good is None else not self.good), ()
        return not self.blind_failing, self.blind_failing

    def expects_pass(self, assertion_id: str) -> bool | None:
        """Whether the person expected the check with this identity to pass,
        or `None` where she said nothing about it: awaiting, or a check the
        reviewed answer did not ask."""
        if self.good is None:
            return None
        if self.assertion_id is not None:
            return self.good if assertion_id == self.assertion_id else None
        if assertion_id not in self.judged:
            return None
        return assertion_id not in self.failing

    def blind_expects_pass(self, assertion_id: str) -> bool | None:
        """`expects_pass`, read on the blind verdict: what the person expected
        of the check before she read any disagreement. The same where she did
        not revise. (ADR 0067 §2)"""
        good, failing = self.blind
        if good is None:
            return None
        if self.assertion_id is not None:
            return good if assertion_id == self.assertion_id else None
        if assertion_id not in self.judged:
            return None
        return assertion_id not in failing


@dataclass(frozen=True, slots=True)
class Contradiction:
    """One reviewed answer the judge disagreed with the person about.

    `score` is the judge's, the folded mean the verdict was judged on, and
    `None` where the check reported none.

    `on_the_steps` says who contradicted: the judge, through the check the
    answer was reviewed for, or a check on the steps beside it, which only an
    episode's answer is asked (ADR 0059 §1, amended 2026-11-05).
    `assertion_id` is that check's, so a reader finds its verdict.
    """

    case_id: str
    check: str
    good: bool
    score: float | None
    assertion_id: str = ""
    on_the_steps: bool = False

    @property
    def direction(self) -> Against:
        """`passed_no` where the person said no and the judge passed the
        answer; `failed_yes` where the person said yes and it did not."""
        return "failed_yes" if self.good else "passed_no"


def contradicted(run: Run) -> tuple[Contradiction, ...]:
    """Every reviewed answer in `run` whose verdict is not the person's.

    From the run alone, like `scale_lost`: it compares a verdict with what a
    person said rather than with a past, so a first run is stopped by it.

    **An errored verdict does not fire it.** That case is unjudged, which is
    already exit `2` and already said, and a judge that could not answer has
    neither agreed nor disagreed. A suspended case has no verdict and says
    nothing either.

    The verdict binds by `assertion_id`, and `Run` refuses a reviewed answer
    that binds none, so empty means *every judge agreed*, never *nothing was
    checked*.

    **An episode's answer is asked its trajectory checks too** (ADR 0059 §1,
    amended 2026-11-05), and they are the case's other verdicts. On a yes
    each of them must pass, as the check must: a person who said yes to the
    turn said yes to the steps it took. On a no they say nothing, because a
    no does not say which part of the turn was wrong.
    """
    found: list[Contradiction] = []
    for case in run.results:
        reviewed = case.reviewed
        if reviewed is None or reviewed.good is None:
            # Awaiting the person's verdict: the judge's stands alone, and no
            # gate reads it. (ADR 0067 §1 (a))
            continue
        for verdict in case.verdicts:
            if verdict.status == "error":
                continue
            expected = reviewed.expects_pass(verdict.assertion_id)
            if expected is None:
                # A trajectory check beside the ones reviewed: only a yes
                # binds it, and only a red one contradicts it.
                if not reviewed.good or verdict.status == "pass":
                    continue
                check, good, on_the_steps = verdict.score.name, True, True
            elif (verdict.status == "pass") == expected:
                continue
            else:
                check = (
                    reviewed.check if reviewed.check is not None else verdict.score.name
                )
                good, on_the_steps = expected, False
            found.append(
                Contradiction(
                    case_id=case.case_id,
                    check=check,
                    good=good,
                    score=verdict.score.score,
                    assertion_id=verdict.assertion_id,
                    on_the_steps=on_the_steps,
                )
            )
    return tuple(found)


# -- the agreement reading (ADR 0067 §1 (c), (e), §2, §5) -------------------- #


@dataclass(frozen=True, slots=True)
class AgreementTally:
    """How a judge's verdicts on one check stood against a person's: agreed,
    passed an answer she said no to, failed one she said yes to. The two ways
    of disagreeing are counted apart, as `Against` is."""

    agree: int = 0
    passed_no: int = 0
    failed_yes: int = 0

    @property
    def judged(self) -> int:
        """Every verdict counted here: the three figures summed."""
        return self.agree + self.passed_no + self.failed_yes


@dataclass(frozen=True, slots=True)
class CheckAgreement:
    """One judged check's agreement with the person, on the held-in answers
    or on the held-out ones, never both in one row. (ADR 0067 §1 (c), (e))

    `blind` is read against the verdict she gave before she read any
    disagreement, `after` against the verdict the gate holds, her revision
    where there is one (§2). `revised` counts the answers whose expectation
    of this check her revision moved: the gap between the two figures, and
    how often the judge persuaded her. `unjudged` counts the answers whose
    verdict on this check errored: in neither figure, because a judge that
    could not answer neither agreed nor disagreed.
    """

    check: str
    assertion_id: str
    held_out: bool
    blind: AgreementTally
    after: AgreementTally
    revised: int = 0
    unjudged: int = 0
    #: The answers whose verdict on this check is unstable (§3): in neither
    #: figure, as an unjudged one is, and named apart by the reading.
    unstable: int = 0


@dataclass(frozen=True, slots=True)
class Disagreement:
    """One reviewed answer whose stable verdict on one check is not the
    person's after review: what a reader names for a held-in answer, and
    counts for a held-out one unless asked to show it (§1 (e)). `reason` is
    the judge's, payload, `None` where the run kept none."""

    case_id: str
    check: str
    held_out: bool
    direction: Against
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Composite:
    """A composite check and the checks that are its criteria, by identity:
    what a suite's `criteria` declares, resolved. (ADR 0067 §5, P-1713)"""

    assertion_id: str
    criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompositeMismatch:
    """A reviewed answer about the whole answer on which a composite's verdict
    is not the conjunction of its criteria's: it passed where one of them
    failed, or failed where every one of them passed. `failed` names the
    criteria that failed, empty in the second case. (ADR 0067 §5)"""

    case_id: str
    composite: str
    held_out: bool
    composite_passed: bool
    failed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgreementReading:
    """The agreement between the judge and the person, read off one run.

    `held_in` and `held_out` count the reviewed answers with a verdict in
    each role, awaiting ones in neither. `mismatches` holds the composite's
    disagreements with its criteria in both roles: a reader names the
    held-in ones and counts the held-out ones (§1 (e)).

    `unstable` holds every answer and check whose verdict is unstable (§3),
    counted in no figure. `runs_read` is how many runs the stability was read
    across, this one included, and `stability_measured` is true from two:
    with one, only an answer whose samples split is set apart.
    `disagreements` holds every stable verdict that is not the person's after
    review, held in and held out: a reader names the first and counts the
    second unless asked to show it. (ADR 0067 §3, §1 (e), as noted 2026-11-22)
    """

    rows: tuple[CheckAgreement, ...]
    held_in: int
    held_out: int
    mismatches: tuple[CompositeMismatch, ...] = ()
    stability_measured: bool = False
    runs_read: int = 1
    unstable: tuple[Instability, ...] = ()
    disagreements: tuple[Disagreement, ...] = ()
    #: The suite's runs the scan passed over for their schema, said beside
    #: `runs_read`. (ADR 0067 §3, P-1719)
    runs_unread: int = 0

    def total(self, *, held_out: bool) -> AgreementTally:
        """The verdicts after review in one role, every check summed: what the
        line that says whether the suite can gate reads, held out (§1 (e))."""
        rows = [row.after for row in self.rows if row.held_out == held_out]
        return AgreementTally(
            agree=sum(t.agree for t in rows),
            passed_no=sum(t.passed_no for t in rows),
            failed_yes=sum(t.failed_yes for t in rows),
        )


def reviewed_agreement(
    run: Run,
    composites: Sequence[Composite] = (),
    stability: Stability | None = None,
) -> AgreementReading | None:
    """The agreement reading of `run`, or `None` where no reviewed answer in
    it carries a person's verdict.

    Per judged check and per role, blind and after review. An answer awaiting
    a verdict is in no figure (§1 (a)); a check the answer did not ask is not
    counted for it, and nor is a check on an episode's steps, which the person
    gave no verdict about check by check. Pure, and from the run alone, like
    `contradicted`: the same verdicts, read against both of the person's.

    `stability` is `reviewed_stability(run, others)`, read across the suite's
    other runs by the front end; `None` reads it on this run alone, its
    samples. An unstable verdict is in no figure, and counted apart. (§3)
    """
    if stability is None:
        # Imported here and not at the top: `stability` imports `run`, which
        # imports this module, so a top-level import would be a cycle.
        from digline.core.stability import reviewed_stability

        stability = reviewed_stability(run)
    blind: dict[tuple[str, bool], list[int]] = {}
    after: dict[tuple[str, bool], list[int]] = {}
    moved: dict[tuple[str, bool], int] = {}
    errored: dict[tuple[str, bool], int] = {}
    unsteady: dict[tuple[str, bool], int] = {}
    disagreements: list[Disagreement] = []
    names: dict[str, str] = {}
    answers = {False: 0, True: 0}
    for case in run.results:
        reviewed = case.reviewed
        if reviewed is None or reviewed.good is None:
            continue
        answers[reviewed.held_out] += 1
        for verdict in case.verdicts:
            expected = reviewed.expects_pass(verdict.assertion_id)
            first = reviewed.blind_expects_pass(verdict.assertion_id)
            if expected is None or first is None:
                continue
            key = (verdict.assertion_id, reviewed.held_out)
            # The verdict's own name, on both forms: under a projection a
            # reviewed answer's `check` and a verdict's name are tokens of two
            # kinds, and one row must not carry whichever came first.
            names.setdefault(verdict.assertion_id, verdict.score.name)
            blind.setdefault(key, [0, 0, 0])
            after.setdefault(key, [0, 0, 0])
            if verdict.status == "error":
                moved[key] = moved.get(key, 0) + (first != expected)
                errored[key] = errored.get(key, 0) + 1
                continue
            if stability.is_unstable(case.case_id, verdict.assertion_id):
                unsteady[key] = unsteady.get(key, 0) + 1
                continue
            moved[key] = moved.get(key, 0) + (first != expected)
            passed = verdict.status == "pass"
            for table, said in ((blind, first), (after, expected)):
                table[key][_slot(passed, said)] += 1
            if passed != expected:
                disagreements.append(
                    Disagreement(
                        case_id=case.case_id,
                        check=verdict.score.name,
                        held_out=reviewed.held_out,
                        direction="passed_no" if passed else "failed_yes",
                        reason=verdict.reason,
                    )
                )
    if not answers[False] and not answers[True]:
        return None
    rows = tuple(
        CheckAgreement(
            check=names[identity],
            assertion_id=identity,
            held_out=role,
            blind=AgreementTally(*blind[(identity, role)]),
            after=AgreementTally(*after[(identity, role)]),
            revised=moved.get((identity, role), 0),
            unjudged=errored.get((identity, role), 0),
            unstable=unsteady.get((identity, role), 0),
        )
        for role in (False, True)
        for identity in names
        if (identity, role) in blind
    )
    return AgreementReading(
        rows=rows,
        held_in=answers[False],
        held_out=answers[True],
        mismatches=_mismatches(run, composites),
        stability_measured=stability.measured,
        runs_read=stability.runs_read,
        runs_unread=stability.runs_unread,
        unstable=stability.unstable,
        disagreements=tuple(disagreements),
    )


def _slot(passed: bool, said: bool) -> int:
    """Where one verdict goes in a `AgreementTally`'s three figures."""
    if passed == said:
        return 0
    return 1 if passed else 2


def _mismatches(
    run: Run, composites: Sequence[Composite]
) -> tuple[CompositeMismatch, ...]:
    """Each reviewed answer about the whole answer, with a verdict, on which a
    composite is not the conjunction of its criteria. An answer on which the
    composite or any of its criteria errored, or did not run, is passed over:
    there is no conjunction to read. (ADR 0067 §5)"""
    found: list[CompositeMismatch] = []
    for case in run.results:
        reviewed = case.reviewed
        if reviewed is None or reviewed.good is None or reviewed.check is not None:
            continue
        by_id = {verdict.assertion_id: verdict for verdict in case.verdicts}
        for composite in composites:
            involved = (composite.assertion_id, *composite.criteria)
            if any(
                identity not in by_id or by_id[identity].status == "error"
                for identity in involved
            ):
                continue
            passed = by_id[composite.assertion_id].status == "pass"
            failed = tuple(
                by_id[identity].score.name
                for identity in composite.criteria
                if by_id[identity].status != "pass"
            )
            if passed == (not failed):
                continue
            found.append(
                CompositeMismatch(
                    case_id=case.case_id,
                    composite=by_id[composite.assertion_id].score.name,
                    held_out=reviewed.held_out,
                    composite_passed=passed,
                    failed=failed,
                )
            )
    return tuple(found)
