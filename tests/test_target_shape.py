"""A target of the wrong shape is refused before it is paid for, or named.

Measured at `e82dc2b` and again at `f8a88e5` (#423):

- `price_digest = 3` exited 0. The digest enters `config_hash` as it is, so
  `3`, `"3"` and `"anything"` were three different run keys, moved for a reason
  no reader could see. A baseline promoted under one matched nothing else. A
  falsy value that is not `""` vanished from the hash without a word.
- `preflight = 3` and `config = 'x'` exited 70, before any call, as a bare
  `TypeError` and a bare `ValueError`.
- A target that returned a `str`, `None` or a `dict` exited 70 after the first
  paid call: `response.usage` was read outside the target's `try`.

The members are refused with `TargetShapeError`, exit 64, by `check_target`,
which both entry points call: `execute()` for a library caller, `load_target`
for a command that loads a target and never runs it. The digest is refused
by `price_digest_of` too, wherever it is read, so it needs neither of them.
A return value exists only once the target is called, so it is an errored
case, the way a target that raises already is.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, run_key, write_suite

from digline.cli import EXIT_USAGE
from digline.core import Contains, pricing_digest
from digline.run import Case, Response, Suite, TargetShapeError, execute
from digline.run.driver import (
    _PRICING_DIGEST,  # pyright: ignore[reportPrivateUsage]
)
from digline.targets import ModelPrice

CREATED_AT = "2026-10-04T00:00:00+00:00"
DIGEST = "feedbeefcafe0000"


def suite() -> Suite:
    return Suite(
        tenant="t",
        environment="e",
        name="s",
        assertions=[Contains(needle="a")],
        cases=[Case(id="c1"), Case(id="c2")],
    )


class Counting:
    """A target that counts its calls and answers with `answer`."""

    def __init__(self, answer: object = None) -> None:
        self.calls = 0
        self.answer = Response(output="a") if answer is None else answer

    def __call__(self, case: Case) -> Response:
        self.calls += 1
        return self.answer  # pyright: ignore[reportReturnType]


class Answering(Counting):
    """`Counting`, but able to answer `None` as well."""

    def __init__(self, answer: object) -> None:
        super().__init__()
        self.answer = answer


# --------------------------------------------------------------------------- #
# price_digest: an identity that moved without a word
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "digest",
    [3, 0, None, False, b"feedbeefcafe0000"],
    ids=["int", "zero", "None", "False", "bytes"],
)
def test_a_digest_that_is_not_a_string_is_refused_before_the_first_call(
    digest: object,
) -> None:
    """`0`, `None` and `False` are the falsy values that used to vanish from the
    hash. `""` alone means *nothing declared*."""
    target = Counting()
    target.price_digest = digest  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(TargetShapeError) as refused:
        execute(suite(), target, created_at=CREATED_AT)

    assert f"`price_digest` is of type {type(digest).__name__}" in str(refused.value)
    assert "moves the run's key" in str(refused.value)
    assert target.calls == 0


@pytest.mark.parametrize(
    "digest",
    ["3", "anything", DIGEST.upper(), DIGEST + "0", DIGEST[:-1], " " + DIGEST],
)
def test_a_string_that_is_not_a_digest_is_refused_before_the_first_call(
    digest: str,
) -> None:
    target = Counting()
    target.price_digest = digest  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(TargetShapeError) as refused:
        execute(suite(), target, created_at=CREATED_AT)

    assert "is not the shape `pricing_digest` produces" in str(refused.value)
    assert "goes round ADR 0022" in str(refused.value)
    assert target.calls == 0


def test_a_long_string_is_shown_clipped() -> None:
    target = Counting()
    target.price_digest = "x" * 500  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(TargetShapeError) as refused:
        execute(suite(), target, created_at=CREATED_AT)

    assert "x" * 41 not in str(refused.value)


@pytest.mark.parametrize("digest", ["", DIGEST])
def test_no_digest_and_a_real_one_still_run(digest: str) -> None:
    """The control: what `ProviderTarget` produces, and the empty string it
    gives when nothing was declared."""
    target = Counting()
    target.price_digest = digest  # pyright: ignore[reportAttributeAccessIssue]

    run = execute(suite(), target, created_at=CREATED_AT)

    assert run.config_hash == suite().config_hash(pricing=digest)
    assert target.calls == 2


def test_the_shape_checked_is_the_shape_pricing_digest_produces() -> None:
    """The pattern is written beside the reader and the producer is in the
    core, so this is what holds them together."""
    for rates in (ModelPrice(1.10, 4.40), ModelPrice(0.0, 0.0), ModelPrice(3, 15)):
        assert _PRICING_DIGEST.fullmatch(pricing_digest("m", rates.rates()))


# --------------------------------------------------------------------------- #
# preflight and config: refusals that exited 70
# --------------------------------------------------------------------------- #


def test_a_preflight_that_cannot_be_called_is_refused() -> None:
    target = Counting()
    target.preflight = 3  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(TargetShapeError) as refused:
        execute(suite(), target, created_at=CREATED_AT)

    assert "`preflight` is of type int, which cannot be called" in str(refused.value)
    assert target.calls == 0


@pytest.mark.parametrize(
    ("config", "said"),
    [
        ("x", "`config` is of type str, not a mapping"),
        (["provider", "model"], "`config` is of type list, not a mapping"),
        ({"provider": "p", "model": "m", "nested": {"a": 1}}, "not a scalar"),
    ],
    ids=["str", "list", "nested"],
)
def test_a_config_of_the_wrong_shape_is_refused(config: object, said: str) -> None:
    """The third was a bare `ValueError` out of `SystemConfig`, which is not a
    refusal (ADR 0041 §4.2)."""
    target = Counting()
    target.config = config  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(TargetShapeError) as refused:
        execute(suite(), target, created_at=CREATED_AT)

    assert said in str(refused.value)
    assert target.calls == 0


# --------------------------------------------------------------------------- #
# The return value: an errored case, named as the target's code
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer", ["a", None, {"output": "a"}], ids=["str", "None", "dict"]
)
def test_a_target_returning_the_wrong_type_errors_the_case(answer: object) -> None:
    target = Answering(answer)

    run = execute(suite(), target, created_at=CREATED_AT)

    reasons = {v.reason for result in run.results for v in result.verdicts}
    assert reasons == {
        f"the target returned a value of type {type(answer).__name__}, not a "
        "Response: that is the target's code, not the endpoint. Wrap what it "
        "answers in Response(output=...)"
    }
    assert {v.status for result in run.results for v in result.verdicts} == {"error"}
    # Every case is attempted, and every call is on the bill, with no counts.
    assert target.calls == 2
    assert run.usage is not None
    assert (run.usage.target.calls, run.usage.target.counted) == (2, 0)


# --------------------------------------------------------------------------- #
# The second entry point: a command that never reaches execute()
# --------------------------------------------------------------------------- #


def shaped(name: str, member: str) -> str:
    """A second target in the suite file, the shared one with one `member`."""
    return f"""
class {name.title()}:
    {member}

    def __call__(self, case):
        return target(case)


{name} = {name.title()}()
"""


def promoted_with(repo: Path, name: str) -> str:
    """Run with the suite's own target, then promote naming `name`'s."""
    key = run_key(repo)
    done = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--target",
        f"suite_qa.py:{name}",
        "--run",
        key,
    )
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "Traceback" not in done.stderr
    return done.stderr


def test_promote_refuses_a_target_whose_shape_only_load_target_reads(
    repo: Path,
) -> None:
    """`promote --target` loads a target and never calls `execute()` or
    `preflight`, so this refusal is `load_target`'s alone: without its call,
    the promotion goes ahead."""
    write_suite(repo, preamble=shaped("unflighted", "preflight = 3"))

    said = promoted_with(repo, "unflighted")

    assert "TargetShapeError: the target's `preflight` is of type int" in said


def test_promote_refuses_a_digest_of_the_wrong_shape(repo: Path) -> None:
    """Refused by `price_digest_of`, the one place every command reads the
    digest, so a baseline cannot be promoted under a key nobody can explain."""
    write_suite(repo, preamble=shaped("undeclared", "price_digest = 3"))

    said = promoted_with(repo, "undeclared")

    assert "TargetShapeError: the target's `price_digest` is of type int" in said
