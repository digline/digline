"""The question beside the answer: what the recorder writes as a recorded
response's `input`, read back by `digline record import` into a reviewed
answer. (ADR 0058 §3, §5; ADR 0059 §1)

Nothing here writes a recording by hand. Each way the recorder takes a call —
made, streamed, awaited, and an episode — records through a real SDK over a
fake transport, and the import then writes the answer a person named, so the
input in the cases file is the one the recorder wrote.

What is held here:

- a single call's input is its case's `messages` as JSON text, keys sorted
  and compact, the same made, streamed or awaited;
- the leading instructions an OpenAI map moves into the setup are not in it;
- an episode's input is its whole case, not one of its calls' messages;
- `record import --good ID --by NAME` writes that input into the reviewed
  answer, which it would refuse without one.

The SDKs are imported inside a test and taken out of `sys.modules` when the
module is done, for the reason `tests/test_recorder.py` gives.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.test_recorder_async import an_async_anthropic
from tests.test_recorder_episode import ANSWER, LOOKUP, REFUND
from tests.test_recorder_episode import an_anthropic as a_turn
from tests.test_recorder_import import argv, suite_file
from tests.test_recorder_streaming import QUESTION, an_anthropic, an_openai

from digline import recorder
from digline.cli.main import main
from digline.core.recording import input_of
from digline.host import answer_id
from digline.recorder import episode, wrap

SDKS = ("anthropic", "openai", "httpx2")

#: The input the recorder writes for `QUESTION`, spelled out once so the form
#: itself is held and not only its agreement with `input_of`.
ASKED = '[{"content":"Capital of France?","role":"user"}]'


@pytest.fixture(autouse=True, scope="module")
def the_sdks_leave_with_this_module() -> Iterator[None]:
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.split(".", 1)[0] in SDKS:
            del sys.modules[name]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(recorder.ENVIRONMENT_VARIABLE, "1")
    suite_file(tmp_path)
    return tmp_path


def recorded_input(root: Path) -> list[object]:
    return [
        json.loads(path.read_text(encoding="utf-8"))["response"].get("input")
        for path in sorted((root / ".digline").glob("*/recordings/*/*.json"))
    ]


def imported(root: Path, case: dict[str, object], text: str) -> dict[str, Any]:
    """The reviewed answer `record import` writes for the answer named."""
    assert main(argv(root, "--good", answer_id(case, text), "--by", "Ada")) == 0
    [written] = json.loads((root / "captured.json").read_text(encoding="utf-8"))
    return written["reviewed_answer"]


def ask(client: Any, **extra: Any) -> Any:
    return client.messages.create(
        model="claude-test", max_tokens=10, messages=QUESTION, suite="triage", **extra
    )


def test_a_call_made_records_its_messages_and_the_import_writes_them(
    root: Path,
) -> None:
    ask(wrap(an_anthropic(), app="support", tenant="acme", root=root))
    assert recorded_input(root) == [ASKED]
    assert input_of(QUESTION) == ASKED
    reviewed = imported(root, {"messages": QUESTION}, "Paris")
    assert reviewed == {
        "output": "Paris",
        "check": "llm_rubric",
        "good": True,
        "input": ASKED,
    }


def test_a_call_streamed_records_the_same_input(root: Path) -> None:
    client = wrap(an_anthropic(), app="support", tenant="acme", root=root)
    for _ in ask(client, stream=True):
        pass
    assert recorded_input(root) == [ASKED]
    assert imported(root, {"messages": QUESTION}, "Paris")["input"] == ASKED


def test_a_call_awaited_records_the_same_input(root: Path) -> None:
    client = wrap(an_async_anthropic(), app="support", tenant="acme", root=root)

    async def call() -> Any:
        return await ask(client)

    asyncio.run(call())
    assert recorded_input(root) == [ASKED]
    assert imported(root, {"messages": QUESTION}, "Paris")["input"] == ASKED


def test_the_instructions_moved_into_the_setup_are_not_in_the_input(
    root: Path,
) -> None:
    client = wrap(an_openai(), app="support", tenant="acme", root=root)
    system = {"role": "system", "content": "Answer in one word."}
    client.chat.completions.create(
        model="gpt-test",
        messages=[system, *QUESTION],  # pyright: ignore[reportArgumentType]
        suite="triage",
    )
    assert recorded_input(root) == [ASKED]


def test_an_episode_records_its_case_and_the_import_writes_it(root: Path) -> None:
    client = wrap(
        a_turn(LOOKUP, REFUND, ANSWER), app="support", tenant="acme", root=root
    )
    case: dict[str, object] = {"order": "A1", "ticket": "Où est mon remboursement ?"}
    with episode(client, suite="triage", case=case):
        for _ in range(3):
            client.messages.create(
                model="claude-test",
                max_tokens=50,
                messages=QUESTION,
                suite="triage-step",
            )
    # The calls' own recordings carry their messages; the episode's, its case.
    asked = '{"order":"A1","ticket":"Où est mon remboursement ?"}'
    assert sorted(map(str, recorded_input(root))) == sorted([ASKED] * 3 + [asked])
    reviewed = imported(root, case, "Your refund is on its way.")
    assert reviewed["input"] == asked
    assert reviewed["output"] == "Your refund is on its way."
