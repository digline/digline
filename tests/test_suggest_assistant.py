"""`digline suggest`'s assistant: a model of its own, declared, asked once,
and merged into the proposal, never obeyed. (ADR 0063 §4, §6)

No real model is called. Each provider plugin's judge is built by its real
code from its coordinates, and its SDK client is replaced by a fake that
records the request and answers what the test says: the same seam the
plugins' own tests use, so the request each plugin builds is the real one.

What is held here, one test or more for each line of the test plan:

- with no model declared, no call, and the proposal and standard error are
  byte for byte the ones the command wrote without an assistant;
- `[suggest] model` is read from a suite.toml alone, enters neither the suite
  nor its `config_hash`, and any other key under it is refused by name;
  `--model` wins, and standard error says where the model came from;
- what it costs is said before the first call, `unpriced` with why where the
  plugin's list has no price;
- the calls no suite named are never in the material; under `"public"` no
  recorded text is, under `"private"` it is, whole, the newest first and
  within the bound;
- what the model writes outside what it may, a check of its own among it, is
  discarded and counted; a limit less strict than the runs measured too;
- the file loads as a suite once its judge is named, and the counterexample
  the model constructed makes it fail on a target that gives that answer;
- the path is the judge's on the three plugins.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from tests.test_suggest import (
    EPISODES,
    SECRET_ANSWER,
    SECRET_INPUT,
    SECRET_UNASSIGNED,
    SUITE_TOML,
    existing,
    main,
    single,
    unassigned,
    write,
)

from digline.core.recording import Recording, setup_digest_of
from digline.core.run import RecordedResponse
from digline.core.types import Usage
from digline.host import PROPOSAL, load_suite
from digline.host.assistant import MAX_RECORDINGS, MAX_TOKENS, SYSTEM
from digline.run import Case, Response, execute

FIXTURES = Path(__file__).parent / "fixtures" / "suggest"

#: The coordinates every test but the plugins' asks: a model the
#: Anthropic plugin's price list knows.
MODEL = "anthropic/claude-haiku-4-5"


# A fake upstream for each plugin, at the SDK client.


@dataclass
class _Block:
    text: str
    type: str = "text"
    name: str = ""


@dataclass
class _Usage:
    input_tokens: int = 1000
    output_tokens: int = 200
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    inference_geo: str | None = None


@dataclass
class _Reply:
    content: list[_Block]
    usage: _Usage = field(default_factory=_Usage)
    stop_reason: str | None = "end_turn"
    model: str = "claude-haiku-4-5-20251001"


class Upstream:
    """What the model is asked, and what it answers. `heard` is what had
    been said on standard error when each call arrived."""

    def __init__(self, reply: object, capsys: pytest.CaptureFixture[str]) -> None:
        self.text = reply if isinstance(reply, str) else json.dumps(reply)
        self.capsys = capsys
        self.requests: list[dict[str, Any]] = []
        self.heard: list[str] = []

    def arrived(self, request: dict[str, Any]) -> None:
        self.requests.append(request)
        said = self.capsys.readouterr()
        self.heard.append(said.err)
        # Put back, so the test reads the whole of standard error after.
        import sys

        sys.stderr.write(said.err)

    @property
    def prompt(self) -> str:
        [request] = self.requests
        if "messages" in request and isinstance(request["messages"][0], dict):
            for message in request["messages"]:
                if message["role"] == "user":
                    content = message["content"]
                    return content if isinstance(content, str) else content[0]["text"]
        raise AssertionError(f"no user message in {sorted(request)}")


class _Messages:
    def __init__(self, upstream: Upstream) -> None:
        self.upstream = upstream

    def create(self, **kwargs: Any) -> _Reply:
        self.upstream.arrived(kwargs)
        # The plugin wrote "{" in the assistant's mouth; the model goes on.
        return _Reply(content=[_Block(self.upstream.text.removeprefix("{"))])


class AnthropicClient:
    def __init__(self, upstream: Upstream) -> None:
        self.messages = _Messages(upstream)


@dataclass
class _Message:
    content: str | None
    refusal: str | None = None
    tool_calls: list[object] | None = None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str | None = "stop"


@dataclass
class _OpenAIUsage:
    prompt_tokens: int = 1000
    completion_tokens: int = 200
    prompt_tokens_details: object = None
    completion_tokens_details: object = None


@dataclass
class _OpenAIReply:
    choices: list[_Choice]
    usage: _OpenAIUsage = field(default_factory=_OpenAIUsage)
    model: str = "gpt-4o-mini-2024-07-18"
    system_fingerprint: str | None = None


class _Completions:
    def __init__(self, upstream: Upstream) -> None:
        self.upstream = upstream

    def create(self, **kwargs: Any) -> _OpenAIReply:
        self.upstream.arrived(kwargs)
        return _OpenAIReply(choices=[_Choice(_Message(self.upstream.text))])


class _Chat:
    def __init__(self, upstream: Upstream) -> None:
        self.completions = _Completions(upstream)


class OpenAIClient:
    def __init__(self, upstream: Upstream) -> None:
        self.chat = _Chat(upstream)


class _Meta:
    region_name = "eu-west-1"


class BedrockClient:
    """`converse(**request)` answering a dict, as botocore does."""

    meta = _Meta()

    def __init__(self, upstream: Upstream) -> None:
        self.upstream = upstream

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.upstream.arrived(
            {
                **kwargs,
                "messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in kwargs["messages"]
                ],
            }
        )
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": self.upstream.text}],
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1000, "outputTokens": 200, "totalTokens": 1200},
            "metrics": {"latencyMs": 42},
        }


def upstream(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reply: object,
    provider: str = "anthropic",
) -> Upstream:
    """The plugin's SDK client replaced by one that answers `reply`."""
    found = Upstream(reply, capsys)
    if provider == "anthropic":
        monkeypatch.setattr(
            "digline_anthropic.judge.build_client", lambda: AnthropicClient(found)
        )
    elif provider == "openai":
        monkeypatch.setattr(
            "digline_openai.client.build_client",
            lambda base_url, api_key: OpenAIClient(found),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        )
    else:
        monkeypatch.setattr(
            "digline_bedrock.client.build_client",
            lambda region: BedrockClient(found),  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        )
    return found


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `fake` provider beside the installed ones: a suite here names its
    judge `fake/m`, and its assistant is a real plugin's. Shadows the
    conftest fixture, which leaves `fake` alone."""
    from importlib.metadata import EntryPoint

    from tests._providers import REGISTERED

    from digline.targets import registry

    installed = dict(registry._entry_points())  # pyright: ignore[reportPrivateUsage]
    installed[REGISTERED.name] = EntryPoint(
        name=REGISTERED.name, value="tests._providers:REGISTERED", group=registry.GROUP
    )
    monkeypatch.setattr("digline.targets.registry._entry_points", lambda: installed)


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def new(regime: str = "private", *more: str) -> int:
    return main(
        "suggest", "--suite", "triage", "--tenant", "acme", "--repository", regime,
        *more,
    )  # fmt: skip


def written(root: Path) -> str:
    return (root / PROPOSAL).read_text(encoding="utf-8")


def checks(root: Path) -> list[dict[str, Any]]:
    return list(tomllib.loads(written(root)).get("assertions", []))


# With no model.


@pytest.mark.parametrize("fixture", ["existing", "new-public"])
def test_without_a_model_the_output_is_the_rules_alone_byte_for_byte(
    here: Path,
    fixture: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fixtures are what the command wrote at 4c1a4960, before the
    assistant, regenerated since only for the corrections to its lines that
    followed it: a model never declared changes nothing, on the file or on
    standard error."""
    from tests._providers import REGISTERED

    looked: list[str] = []

    def only_fake() -> dict[str, object]:
        from importlib.metadata import EntryPoint

        from digline.targets.registry import GROUP

        looked.append("registry")
        return {
            REGISTERED.name: EntryPoint(
                name=REGISTERED.name, value="tests._providers:REGISTERED", group=GROUP
            )
        }

    monkeypatch.setattr("digline.targets.registry._entry_points", only_fake)
    if fixture == "existing":
        existing(here)
        assert main("suggest", "--suite", "suite.toml") == 0
    else:
        write(here, EPISODES)
        assert new("public") == 0
    said = capsys.readouterr()
    assert said.out == ""
    assert written(here) == (FIXTURES / f"{fixture}.toml").read_text(encoding="utf-8")
    assert said.err.replace(str(here), "<here>") == (
        FIXTURES / f"{fixture}.err"
    ).read_text(encoding="utf-8")
    # No line of the assistant's: the regime's line names one only to say
    # there is none.
    assert "assistant:" not in said.err
    # Where a suite exists, its own judge is the provider looked up; where
    # none does, the judge's line lists the plugins installed, from their
    # metadata, and loads none.
    assert looked == ["registry"]


# The declaration.


def test_suggest_in_the_suite_toml_enters_neither_the_suite_nor_its_hash(
    here: Path, fake_provider: None
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    (here / "captured.json").write_text("[]", encoding="utf-8")
    before, _ = load_suite("suite.toml", root=here)
    (here / "suite.toml").write_text(
        SUITE_TOML + f'\n[suggest]\nmodel = "{MODEL}"\n', encoding="utf-8"
    )
    after, _ = load_suite("suite.toml", root=here)
    assert after.config_hash() == before.config_hash()
    # Nowhere in the suite, not only out of its hash.
    assert "claude-haiku-4-5" not in repr(after)


@pytest.mark.parametrize(
    ("table", "said"),
    [
        (f'model = "{MODEL}"\njudge = "x/y"', "judge"),
        ("model = 3", "needs `model = "),
        ('model = "claude"', "claude"),
    ],
)
def test_suggest_takes_a_model_by_coordinates_and_nothing_else(
    here: Path, fake_provider: None, table: str, said: str
) -> None:
    (here / "suite.toml").write_text(
        SUITE_TOML + f"\n[suggest]\n{table}\n", encoding="utf-8"
    )
    (here / "captured.json").write_text("[]", encoding="utf-8")
    with pytest.raises(Exception, match="suggest") as refused:
        load_suite("suite.toml", root=here)
    assert said in str(refused.value)


def test_the_model_in_the_suite_toml_is_asked_and_said_where_from(
    here: Path,
    fake_provider: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    existing(here)
    with (here / "suite.toml").open("a", encoding="utf-8") as suite:
        suite.write(f'\n[suggest]\nmodel = "{MODEL}"\n')
    asked = upstream(monkeypatch, capsys, {})
    assert main("suggest", "--suite", "suite.toml") == 0
    [request] = asked.requests
    assert request["model"] == "claude-haiku-4-5"
    assert (
        f"assistant: {MODEL}, from [suggest] in suite.toml" in capsys.readouterr().err
    )


def test_model_wins_over_the_suite_toml_and_says_so(
    here: Path,
    fake_provider: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    existing(here)
    with (here / "suite.toml").open("a", encoding="utf-8") as suite:
        suite.write('\n[suggest]\nmodel = "anthropic/claude-opus-5"\n')
    asked = upstream(monkeypatch, capsys, {})
    assert main("suggest", "--suite", "suite.toml", "--model", MODEL) == 0
    [request] = asked.requests
    assert request["model"] == "claude-haiku-4-5"
    said = capsys.readouterr().err
    assert (
        f"assistant: {MODEL}, from --model, which wins over [suggest] in suite.toml"
        in said
    )


# What it costs, said first.


def test_the_cost_is_said_before_the_first_call(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    [before] = asked.heard
    [line] = [
        line for line in before.splitlines() if line.startswith("assistant: 1 call")
    ]
    assert line.startswith(
        f"assistant: 1 call to {MODEL}, 3 recordings and 0 reviewed answers, about "
    )
    assert f"and at most {MAX_TOKENS:,} output; at most $" in line
    # Nothing of the proposal was said before the call: the command waits.
    assert "wrote" not in before


def test_a_model_the_price_list_does_not_know_is_refused_before_the_call(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measured: the judge's call prices every reply and raises, once paid,
    on a model its list does not know. So the refusal comes first."""
    write(here, EPISODES)
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", "anthropic/claude-nobody-1") == 64
    assert asked.requests == []
    said = capsys.readouterr().err
    assert "anthropic's price list has no price for 'claude-nobody-1'" in said
    assert "No call was made" in said
    assert not (here / PROPOSAL).exists()


def test_the_tokens_are_estimated_at_the_ratio_the_recordings_report(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a count on any recording, the convention is said as one; with
    counts, the ratio is theirs."""
    write(here, [single(1, "one"), single(2, "two")])
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    assert "at 4 characters a token, a convention" in asked.heard[0]

    other = here / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    counted = [
        replace(
            r,
            response=replace(r.response, usage=Usage(input_tokens=1, output_tokens=1)),
        )
        for r in (single(1, "one"), single(2, "two"))
    ]
    write(other, counted)
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    assert "at the ratio the suite's recordings report" in asked.heard[0]


# What it is given.


def test_the_calls_no_suite_named_are_never_given(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [*EPISODES, unassigned()])
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    assert SECRET_INPUT in asked.prompt
    assert SECRET_UNASSIGNED not in asked.prompt


@pytest.mark.parametrize("regime", ["private", "public"])
def test_under_public_the_shape_and_under_private_the_text(
    here: Path,
    regime: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write(here, EPISODES)
    asked = upstream(monkeypatch, capsys, {})
    assert new(regime, "--model", MODEL) == 0
    for text in (SECRET_INPUT, SECRET_ANSWER):
        assert (text in asked.prompt) == (regime == "private"), text
    said = capsys.readouterr().err
    if regime == "public":
        assert "under public the assistant read the shape, not the text" in said
        assert json.loads(asked.prompt)["shape"]["tools_called"] == [
            "issue_refund",
            "lookup_order",
            "send_email",
        ]
    else:
        assert "under private the assistant read the text: 3 recordings" in said
    assert SECRET_INPUT not in said and SECRET_ANSWER not in said


def test_the_material_is_the_newest_recordings_within_the_bound(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    many = [single(n, f"answer {n}") for n in range(MAX_RECORDINGS + 10)]
    many = [
        replace(r, recorded_at=f"2026-11-06T{8 + n // 60:02d}:{n % 60:02d}:00+00:00")
        for n, r in enumerate(many)
    ]
    write(here, many)
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    given = json.loads(asked.prompt)["recordings"]
    assert len(given) == MAX_RECORDINGS
    assert given[0]["answer"] == f"answer {MAX_RECORDINGS + 9}"
    assert all(entry["answer"] != "answer 0" for entry in given)
    assert (
        "; left out: 0 under earlier setups; 10 at the bound of 50 recordings "
        "and 200,000 characters" in capsys.readouterr().err
    )


def test_a_setup_no_longer_in_force_is_not_given(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    setup: dict[str, object] = {"model": "older"}
    old = Recording(
        source_tenant="acme",
        app="support",
        suite="triage",
        case={"question": "q"},
        setup=setup,
        setup_digest=setup_digest_of(setup),
        response=RecordedResponse(output="OLD-SETUP-ANSWER", kind="text", input="q"),
        recorded_at="2026-11-06T07:00:00+00:00",
    )
    write(here, [old, single(1, "one"), single(2, "two")])
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    assert "OLD-SETUP-ANSWER" not in asked.prompt
    assert "one" in asked.prompt


def test_an_earlier_setup_is_counted_apart_from_the_bound(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Six recordings on two setups, three each: the three under the earlier
    one are left out because of their setup, and the bound leaves out none.
    The line said *3 more left out at the bound*. (P-1588)"""
    setup: dict[str, object] = {"model": "older"}
    older = [
        Recording(
            source_tenant="acme",
            app="support",
            suite="triage",
            case={"question": f"q{n}"},
            setup=setup,
            setup_digest=setup_digest_of(setup),
            response=RecordedResponse(output=f"old {n}", kind="text", input=f"q{n}"),
            recorded_at=f"2026-11-06T07:0{n}:00+00:00",
        )
        for n in range(3)
    ]
    write(here, [*older, *(single(n, f"new {n}") for n in range(1, 4))])
    asked = upstream(monkeypatch, capsys, {})
    assert new("private", "--model", MODEL) == 0
    assert len(json.loads(asked.prompt)["recordings"]) == 3
    said = capsys.readouterr().err
    assert (
        "the assistant read the text: 3 recordings and 0 reviewed answers, the "
        "newest of the setups in force, each whole; left out: 3 under earlier "
        "setups; 0 at the bound of 50 recordings and 200,000 characters"
    ) in said
    assert "more left out at the bound" not in said


# What it writes, and what is discarded.


def test_a_check_the_model_adds_is_discarded_and_said(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {})
    assert new("private") == 0
    alone = [c["type"] for c in checks(here)]
    (here / PROPOSAL).unlink()
    capsys.readouterr()

    upstream(
        monkeypatch,
        capsys,
        {
            "assertions": [{"type": "contains", "value": "x"}],
            "capture": {"repository": "public"},
            "why": {"check-99": "a check of my own"},
            "limits": {"check-99.maximum": 3},
            "rubric": {"check-99": "Is it mine?"},
        },
    )
    assert new("private", "--model", MODEL) == 0
    assert [c["type"] for c in checks(here)] == alone
    assert tomllib.loads(written(here))["capture"]["repository"] == "private"
    said = capsys.readouterr().err
    assert "discarded: 3 × a check the proposal does not hold" in said
    assert "discarded: 2 × a part outside the reply's form" in said
    assert "a check of my own" not in written(here)


def test_a_limit_is_kept_stricter_and_discarded_laxer_than_the_runs(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`length` with no run is a placeholder, which any accepted number
    replaces, marked as the assistant's. `max_steps` measured at 2 by a run
    takes 1 and refuses 9."""
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {})
    assert new("private") == 0
    numbered = {n: c["type"] for n, c in enumerate(checks(here), start=1)}
    (here / PROPOSAL).unlink()
    length = next(n for n, t in numbered.items() if t == "length")
    steps = next(n for n, t in numbered.items() if t == "max_steps")

    upstream(
        monkeypatch,
        capsys,
        {"limits": {f"check-{length}.maximum": 400, f"check-{steps}.limit": 0}},
    )
    assert new("private", "--model", MODEL) == 0
    found = {c["type"]: c for c in checks(here)}
    assert found["length"]["maximum"] == 400
    assert "maximum = 400  # from the assistant, not measured" in written(here)
    assert found["max_steps"]["limit"] == 1
    assert "discarded: 1 × a limit its check does not accept" in capsys.readouterr().err


def test_a_limit_laxer_than_a_run_measured_is_discarded(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from digline.core.suggest import Proposed, merged

    measured_steps = Proposed(
        type="max_steps", params={"limit": 4, "count": "model"}, why="measured"
    )
    placeholder = Proposed(
        type="max_steps",
        params={"limit": 1, "count": "model"},
        why="placeholder",
        placeholders=("limit",),
    )
    judged = Proposed(
        type="repeated",
        params={"inner": {"type": "llm_rubric", "threshold": 0.8, "rubric": "R"}},
        why="judged",
    )
    done = merged(
        [measured_steps, placeholder, judged],
        {
            "limits": {
                "check-1.limit": 9,
                "check-2.limit": 9,
                "check-3.inner.threshold": 0.5,
            }
        },
    )
    assert done.checks[0].params["limit"] == 4
    assert done.checks[1].params["limit"] == 9
    assert done.checks[1].assisted == ("limit",)
    assert done.checks[2].params["inner"] == {
        "type": "llm_rubric",
        "threshold": 0.8,
        "rubric": "R",
    }
    assert done.discarded == {"a limit less strict than the runs measured": 2}
    stricter = merged(
        [measured_steps, judged],
        {"limits": {"check-1.limit": 3, "check-2.inner.threshold": 0.9}},
    )
    assert stricter.checks[0].params["limit"] == 3
    assert stricter.checks[1].params["inner"]["threshold"] == 0.9  # type: ignore[index]
    assert not stricter.discarded


def test_a_rubric_and_a_reason_are_written_marked_as_the_assistants(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {})
    assert new("private") == 0
    numbered = [c["type"] for c in checks(here)]
    (here / PROPOSAL).unlink()
    judged = numbered.index("repeated") + 1
    length = numbered.index("length") + 1
    upstream(
        monkeypatch,
        capsys,
        {
            "rubric": {
                f"check-{judged}": "Does it say when the refund was sent?",
                f"check-{length}": "Not a judged check",
            },
            "why": {f"check-{length}": "A reply this long\nis a reply nobody reads."},
        },
    )
    assert new("private", "--model", MODEL) == 0
    text = written(here)
    [judged_check] = [c for c in checks(here) if c["type"] == "repeated"]
    assert judged_check["inner"]["rubric"] == "Does it say when the refund was sent?"
    assert (
        'rubric = "Does it say when the refund was sent?"  # from the assistant: '
        "a draft, yours to read"
    ) in text
    assert "# the assistant: A reply this long is a reply nobody reads." in text
    said = capsys.readouterr().err
    assert "what it wrote: 1 rubric, 1 sentence of why, 0 limits" in said
    assert "discarded: 1 × a rubric for a check that is not judged" in said
    assert "Does it say" not in said


def test_a_reply_that_is_no_json_object_is_not_used(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {})
    assert new("private") == 0
    alone = written(here)
    (here / PROPOSAL).unlink()
    upstream(monkeypatch, capsys, "I would rather write prose.")
    assert new("private", "--model", MODEL) == 0
    assert written(here) == alone
    assert (
        "its reply was no JSON object: none of it was used" in capsys.readouterr().err
    )


# The counterexample, and the file as a suite.

JSON_SUITE = """\
[suite]
tenant = "acme"
environment = "dev"
name = "triage"
cases = ["captured.json"]

[capture]
cases_file = "captured.json"
repository = "private"
check = "llm_rubric"

[[assertions]]
type = "llm_rubric"
rubric = "Does it answer?"
judge = "fake/m"
threshold = 0.7
tolerance = 0.05
"""


def json_suite(root: Path) -> None:
    (root / "suite.toml").write_text(JSON_SUITE, encoding="utf-8")
    (root / "captured.json").write_text("[]", encoding="utf-8")
    write(root, [single(1, '{"status": "sent"}'), single(2, '{"status": "held"}')])


def adopted(root: Path) -> Any:
    """The suite with the proposal's lines appended, its judge named."""
    text = written(root).replace('"provider/model"', '"fake/m"')
    with (root / "suite.toml").open("a", encoding="utf-8") as suite:
        suite.write("\n" + text)
    suite, _ = load_suite("suite.toml", root=root)
    return suite


def counterexample(root: Path) -> dict[str, Any]:
    [line] = [x for x in written(root).splitlines() if "counterexample-1" in x]
    return json.loads(line.removeprefix("# "))


def test_the_file_loads_and_the_models_counterexample_makes_it_fail(
    here: Path,
    fake_provider: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_suite(here)
    upstream(
        monkeypatch,
        capsys,
        {"counterexample": {"vars": {"question": "Where is it?"}, "answer": "Sent."}},
    )
    assert main("suggest", "--suite", "suite.toml", "--model", MODEL) == 0
    said = capsys.readouterr().err
    # `json_schema` errors on an answer that is not JSON, and is not counted.
    assert "its counterexample: refused without a judge by is_json\n" in said
    built = counterexample(here)
    assert built["metadata"]["answer"] == "Sent."
    assert "constructed" in built["metadata"]
    suite = adopted(here)

    def target(case: Case) -> Response:
        """A target that gives the answer the assistant constructed."""
        return Response(output=built["metadata"]["answer"])

    run = execute(
        replace(suite, cases=[Case(id=built["id"], vars=built["vars"])]),
        target,
        created_at="2026-11-06T12:00:00+00:00",
    )
    statuses = {v.score.name: v.status for r in run.results for v in r.verdicts}
    assert statuses["is_json"] == "fail"


def test_a_counterexample_no_check_refuses_is_said_to_be_the_judges(
    here: Path,
    fake_provider: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_suite(here)
    upstream(
        monkeypatch,
        capsys,
        {"counterexample": {"vars": {"q": "x"}, "answer": '{"status": "sent"}'}},
    )
    assert main("suggest", "--suite", "suite.toml", "--model", MODEL) == 0
    assert (
        "its counterexample: refused by no check without a judge: only the judge "
        "can refuse it"
    ) in capsys.readouterr().err


@pytest.mark.parametrize(
    "given",
    [
        {"answer": "no input"},
        {"vars": {"question": "q"}, "answer": 3},
        {"vars": {}, "answer": "an empty input"},
        {"vars": "q", "answer": "an input that is no table"},
    ],
)
def test_a_counterexample_out_of_form_is_discarded(
    here: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    given: dict[str, object],
) -> None:
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {"counterexample": given})
    assert new("private", "--model", MODEL) == 0
    assert '"WRITE"' in written(here)
    said = capsys.readouterr().err
    assert "discarded: 1 × a counterexample not of the form vars and answer" in said


# The judge's path, on the three plugins.


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("anthropic", "claude-haiku-4-5"),
        ("openai", "gpt-4o-mini"),
        ("bedrock", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
    ],
)
def test_each_plugin_is_asked_through_its_own_judge(
    here: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    provider: str,
    model: str,
) -> None:
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {})
    assert new("private") == 0
    judged = [c["type"] for c in checks(here)].index("repeated") + 1
    (here / PROPOSAL).unlink()

    asked = upstream(
        monkeypatch,
        capsys,
        {"rubric": {f"check-{judged}": "Is the refund's date said?"}},
        provider,
    )
    assert new("private", "--model", f"{provider}/{model}") == 0
    [request] = asked.requests
    if provider == "anthropic":
        assert request["system"] == SYSTEM
        assert request["max_tokens"] == MAX_TOKENS
    elif provider == "openai":
        assert request["messages"][0] == {"role": "system", "content": SYSTEM}
        assert MAX_TOKENS in (
            request.get("max_tokens"),
            request.get("max_completion_tokens"),
        )
    else:
        assert request["system"] == [{"text": SYSTEM}]
        assert request["inferenceConfig"]["maxTokens"] == MAX_TOKENS
    assert SECRET_INPUT in asked.prompt
    assert 'rubric = "Is the refund\'s date said?"' in written(here)
    said = capsys.readouterr().err
    assert f"assistant: 1 call to {provider}/{model}" in said
    assert "what it cost: $" in said
