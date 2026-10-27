"""ADR 0004 §8.9's criteria for this plugin, end to end through `execute`, on
the target and on the judge, with the client replaced and no key.

A cache write at a TTL this list cannot price (#368) was refused, and the case
or the judged check errored over a call that had answered. It is now an
unpriced call: judged, counted with its tokens, its cost not known, and the
sentence handed to the person who ran the command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _bedrock_fakes import FakeClient, converse_reply

from digline.core import Contains, LlmRubric, Run, RunUsage
from digline.run import Case, Response, Suite, execute
from digline.targets import Usage
from digline_bedrock import BedrockJudge, BedrockTarget

CREATED = "2026-01-01T00:00:00+00:00"
SONNET = "eu.anthropic.claude-sonnet-4-20250514-v1:0"
HAIKU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def a_reply(text: str, ttl: str) -> dict[str, Any]:
    reply = converse_reply(text, input_tokens=1000, output_tokens=100, cache_write=400)
    reply["usage"]["cacheDetails"] = [{"ttl": ttl, "inputTokens": 400}]
    return reply


def replying(text: str, ttl: str) -> FakeClient:
    client = FakeClient()
    client.reply = a_reply(text, ttl)
    return client


class Answering:
    """A target priced at zero, so the judge's line is alone in what varies."""

    config = {"provider": "fake", "model": "m-1"}

    def __call__(self, case: Case) -> Response:
        return Response(output="Rome.", cost_usd=0.0, usage=Usage(0, 0))


def suite(*assertions: object) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=list(assertions),  # pyright: ignore[reportArgumentType]
        cases=[Case(id="c1", vars={"country": "Italy"})],
    )


def usage_of(run: Run) -> RunUsage:
    assert run.usage is not None
    return run.usage


def statuses(run: Run) -> list[str]:
    return [v.status for case in run.results for v in case.verdicts]


def judge(ttl: str) -> BedrockJudge:
    return BedrockJudge(
        model=HAIKU, client=replying('{"score": 1, "reason": "fine"}', ttl)
    )


def rubric(ttl: str) -> LlmRubric:
    return LlmRubric(rubric="Polite?", judge=judge(ttl), threshold=0.5, tolerance=0.0)


def test_an_unpriced_target_reply_is_judged_and_its_cost_not_known(
    prompt: Path,
) -> None:
    said: list[str] = []
    target = BedrockTarget(prompt, SONNET, 64, client=replying("Rome.", "1h"))
    run = execute(
        suite(Contains(needle="Rome", threshold=1.0)),
        target,
        created_at=CREATED,
        on_unpriced=said.append,
    )
    assert statuses(run) == ["pass"]
    assert run.results[0].error_kind is None
    line = usage_of(run).target
    assert (line.calls, line.counted, line.spent_usd) == (1, 1, 0.0)
    assert line.tokens.cache_write_tokens == 400
    assert line.every_cost_known is False
    (sentence,) = said
    assert "#368" in sentence


def test_an_unpriced_judge_reply_is_judged_and_its_cost_not_known() -> None:
    said: list[str] = []
    run = execute(
        suite(rubric("1h")), Answering(), created_at=CREATED, on_unpriced=said.append
    )
    assert statuses(run) == ["pass"]
    line = usage_of(run).judge
    assert (line.calls, line.counted, line.spent_usd) == (1, 1, 0.0)
    assert line.tokens.cache_write_tokens == 400
    assert line.every_cost_known is False
    (sentence,) = said
    assert "#368" in sentence


@pytest.mark.parametrize("side", ["target", "judge"])
def test_a_five_minute_write_has_its_figure_and_no_sentence(
    prompt: Path, side: str
) -> None:
    """The control: the sentence appears only where its fact holds."""
    said: list[str] = []
    if side == "target":
        target = BedrockTarget(prompt, SONNET, 64, client=replying("Rome.", "5m"))
        run = execute(
            suite(Contains(needle="Rome", threshold=1.0)),
            target,
            created_at=CREATED,
            on_unpriced=said.append,
        )
        line = usage_of(run).target
    else:
        run = execute(
            suite(rubric("5m")),
            Answering(),
            created_at=CREATED,
            on_unpriced=said.append,
        )
        line = usage_of(run).judge
    assert line.spent_usd > 0
    assert line.every_cost_known is True
    assert said == []
