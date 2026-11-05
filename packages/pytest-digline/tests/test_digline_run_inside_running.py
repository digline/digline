"""`--digline-run` measures as `digline run` does: inside `running()`, and with
`around_target`. (ADR 0060 §3)

A suite whose target and judge both call a client `digline.recorder.wrap`
returned, with the recorder switched on. Under pytest:
- `MaxSteps` passes, which it can only where the target's response has steps,
  and a function target reports none: `around_target` read the call the target
  made;
- nothing is written, though the judge's calls are outside the target, where
  only `running()` keeps them from being the application's traffic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SUITE = """
import importlib

from digline.core import JudgeReply, LlmRubric, MaxSteps
from digline.recorder import wrap
from digline.run import Case, Response, Suite

httpx2 = importlib.import_module("httpx2")
anthropic = importlib.import_module("anthropic")


def answer(request):
    return httpx2.Response(
        200,
        json={
            "id": "m",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [{"type": "text", "text": "Acme, fine"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    )


client = wrap(
    anthropic.Anthropic(
        api_key="k",
        http_client=httpx2.Client(transport=httpx2.MockTransport(answer)),
        max_retries=0,
    ),
    app="support",
    tenant="acme",
)



def ask():
    return client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=[{"role": "user", "content": "Hi"}],
        suite="wrapped",
    )


def judge(prompt):
    ask()
    return JudgeReply(score=1.0, reason="asked the client")


def target(case: Case) -> Response:
    return Response(output=ask().content[0].text, latency_ms=1.0)

suite = Suite(
    tenant="acme",
    environment="staging",
    name="wrapped",
    assertions=[
        MaxSteps(limit=1, count="model"),
        LlmRubric(rubric="ok?", judge=judge, threshold=0.5, tolerance=0.05),
    ],
    cases=[Case(id="alpha")],
)
"""


def test_a_run_under_pytest_records_nothing_and_reads_the_targets_calls(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGLINE_RECORD", "1")
    path = pytester.path / "suite.py"
    path.write_text(SUITE, encoding="utf-8")
    pytester.runpytest_subprocess("--digline-suite", str(path), "--digline-run")

    recordings = [
        p
        for p in (pytester.path / ".digline").rglob("recordings/*/*.json")
        if not p.name.startswith(".")
    ]
    assert recordings == []
    [run] = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in (pytester.path / ".digline" / "acme" / "runs").rglob("*.json")
    ]
    [case] = run["results"]
    steps = next(v for v in case["verdicts"] if v["assertion"] == "max_steps")
    # The call the target made through the wrapped client, read into its
    # response as one model step: a function target reports no steps, and
    # `MaxSteps` errors on a response without them.
    assert steps["status"] == "pass", steps
    assert steps["metadata"]["steps"] == 1


def test_the_control_without_running_the_wrapped_client_records(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same target called outside a run, with the recorder on: it writes,
    so the absence above is `running()`'s, not a recorder that was off."""
    monkeypatch.setenv("DIGLINE_RECORD", "1")
    path = pytester.path / "suite.py"
    path.write_text(SUITE + "\nask()\n", encoding="utf-8")
    # The interpreter running this test, never the first `python` on PATH,
    # which may be another checkout's without the plugins.
    pytester.run(sys.executable, str(path))
    recordings = [
        p
        for p in (pytester.path / ".digline").rglob("recordings/*/*.json")
        if not p.name.startswith(".")
    ]
    assert len(recordings) == 1, sorted(Path(p).name for p in recordings)
