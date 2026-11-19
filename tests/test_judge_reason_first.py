"""The judge is asked for its reason before its score, in the same object.

A short reason written first is the sentence the score is then given against,
where a reason written after the score can only explain a number already
chosen. So `SCORE_SYSTEM` asks for `{"reason", "score"}` and `CLAIM_SYSTEM`
for `{"reason", "supported", "total"}`, in that order. The parser reads either
order, because a JSON object's keys have none and a model that answers
score-first has still answered. The words moved, so `score_prompt_digest` and
`claim_prompt_digest` moved with them (ADR 0005 §4, ADR 0068 §3).
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest
from tests.test_judge import FakeClaimJudge, FakeScoreJudge
from tests.test_judge_prompt_digest import Graded, a_run, outcome

from digline.core import SystemConfig, compare
from digline.targets import CLAIM_SYSTEM, SCORE_SYSTEM
from digline.targets.judge import prompt_digest

#: The digests of the two instructions as 1.3.0 shipped them, read from
#: `digline.targets.judge` at v1.3.0, unchanged at 6af7f2da.
SCORE_DIGEST_1_3_0 = "d7e18626f0c14266"
CLAIM_DIGEST_1_3_0 = "9ea822615848af92"


def keys_asked(system: str, first_key: str) -> list[str]:
    """The keys of the object the instruction spells out, in the order it
    spells them: the first template line that holds `first_key`."""
    for line in system.splitlines():
        if line.startswith("{") and f'"{first_key}"' in line:
            return re.findall(r'"([a-z]+)":', line)
    raise AssertionError(f"no template holding {first_key!r} in the instruction")


def test_the_score_instruction_asks_for_the_reason_first() -> None:
    assert keys_asked(SCORE_SYSTEM, "score") == ["reason", "score"]


def test_the_claim_instruction_asks_for_the_reason_first() -> None:
    assert keys_asked(CLAIM_SYSTEM, "supported") == ["reason", "supported", "total"]


def test_the_abstention_is_unchanged() -> None:
    """ADR 0004 §7.3: the declared form is one key and a reason, and it is
    not what moved."""
    assert keys_asked(SCORE_SYSTEM, "abstain") == ["abstain", "reason"]
    assert keys_asked(CLAIM_SYSTEM, "abstain") == ["abstain", "reason"]


def test_the_reason_is_asked_short() -> None:
    assert "short" in SCORE_SYSTEM and "short" in CLAIM_SYSTEM


SCORE = {"reason": "it names the capital", "score": 0.75}
CLAIM = {"reason": "one claim is not in the text", "supported": 1, "total": 2}


@pytest.mark.parametrize(
    "reply",
    [json.dumps(SCORE), json.dumps(dict(reversed(SCORE.items())))],
    ids=["reason-first", "score-first"],
)
def test_a_score_is_read_in_either_order(reply: str) -> None:
    got = FakeScoreJudge(reply)("prompt")
    assert (got.score, got.reason) == (0.75, "it names the capital")


@pytest.mark.parametrize(
    "reply",
    [
        json.dumps(CLAIM),
        json.dumps({"supported": 1, "total": 2, "reason": CLAIM["reason"]}),
        json.dumps({"total": 2, "reason": CLAIM["reason"], "supported": 1}),
    ],
    ids=["reason-first", "counts-first", "mixed"],
)
def test_counts_are_read_in_any_order(reply: str) -> None:
    got = FakeClaimJudge(reply)("prompt")
    assert (got.supported, got.total, got.reason) == (1, 2, CLAIM["reason"])


def test_the_new_words_moved_both_digests() -> None:
    """What makes `compare` say the judge changed, against a reference
    judged under 1.3.0's words."""
    assert prompt_digest(SCORE_SYSTEM) != SCORE_DIGEST_1_3_0
    assert prompt_digest(CLAIM_SYSTEM) != CLAIM_DIGEST_1_3_0


def test_the_first_compare_against_a_1_3_0_reference_says_the_judge_changed() -> None:
    """What the CHANGELOG says: against a reference that recorded 1.3.0's
    digest, the run says the judge changed; promoted, the next is quiet."""
    now = a_run(Graded('{"reason": "it names the capital", "score": 1}'))
    recorded = now.judge_config
    older = replace(
        now,
        judge_config=SystemConfig(
            values={**recorded.values, "score_prompt_digest": SCORE_DIGEST_1_3_0},
            identities=recorded.identities,
            named=recorded.named,
        ),
    )
    assert outcome(now, older) == "changed"
    assert compare(now, older).judge_config_changed
    assert not compare(a_run(Graded(json.dumps(SCORE))), now).judge_config_changed
