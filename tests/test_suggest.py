"""`digline suggest`: a first suite, proposed and never marked. (ADR 0063)

The recordings are written with the store's own writer, as the recorder files
them, and the command runs in this process, so a mutation of `src/` reaches
every test here.

What is held here, one test or more for each line of ADR 0063's test plan:

- it writes `suite.proposed.toml` and nothing else, and a second run refuses
  by name where the file is there;
- it marks nothing and no command reads the file: the suite loads to the same
  `config_hash`, and the cases file is byte for byte what it was;
- a check on the steps is proposed only where every recording holds it, and
  one contradicting recording takes it out;
- the counterexample is a reviewed no where there is one, and a constructed
  case marked as such otherwise; the suite, the proposal adopted whole, fails
  on the no;
- `_unassigned` calls are counted and never quoted;
- a suite that does not exist yet: with `--tenant` and `--repository` the
  proposal's `[capture]` carries the regime given, and without either the
  command refuses naming the flag; where the suite exists, `--repository` is
  refused;
- with no model declared, no provider is reached;
- no recorded text is in the file under `"public"`, and none on standard
  output or standard error under either regime.

And the rules beneath them: every check proposed can fail, a placeholder is
the strictest value its check accepts, a limit is read from the runs where
they measured it, a JSON shape proposes `is_json` and a draft schema of the
keys every answer carries, and answers of two kinds propose no shape.
"""

from __future__ import annotations

import importlib
import json
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from digline.core import EvaluatorInputs
from digline.core.recording import Recording, setup_digest_of
from digline.core.run import (
    CaseResult,
    RecordedResponse,
    RecordedStep,
    RecordedToolCall,
    Run,
)
from digline.core.suggest import PLACEHOLDER
from digline.core.types import OutputKind
from digline.host import PROPOSAL, load_suite, suggest_new
from digline.recorder import UNASSIGNED
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.store.protocol import PathRefusedError

#: Text only a recording holds: none of it may reach the file under
#: `"public"`, or a stream under either regime.
SECRET_INPUT = "SECRET-INPUT-where-is-order-A1"
SECRET_ANSWER = "SECRET-ANSWER-refunded-to-card"
SECRET_UNASSIGNED = "SECRET-UNASSIGNED-answer"
SECRET_UNASSIGNED_TOOL = "secret_unassigned_tool"

#: The tools the model is told about, by every call of every episode.
TOOLS = ("lookup_order", "send_email", "issue_refund", "delete_account")

SUITE_TOML = """\
[suite]
tenant = "acme"
environment = "dev"
name = "triage"
cases = ["captured.json"]
samples = 2
min_agreement = "2/2"

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


def main(*args: str) -> int:
    """The command in this process, so the code under test is the tree's."""
    return int(importlib.import_module("digline.cli.main").main(list(args)))


def step(index: int, tool: str | None = None) -> RecordedStep:
    if tool is None:
        return RecordedStep(index=index, actor="model", finish="end_turn")
    return RecordedStep(
        index=index, actor="tool", call=RecordedToolCall(tool=tool, arguments="{}")
    )


def trajectory(*tools: str | None) -> tuple[RecordedStep, ...]:
    steps = [step(0)]
    for tool in tools:
        steps.append(step(len(steps), tool) if tool else step(len(steps), None))
        if tool is None:
            steps[-1] = RecordedStep(
                index=len(steps) - 1,
                actor="tool",
                call=RecordedToolCall(tool=None, arguments="{}"),
            )
    steps.append(step(len(steps)))
    return tuple(steps)


def episode(
    number: int,
    *tools: str | None,
    suite: str = "triage",
    output: str = SECRET_ANSWER,
) -> list[Recording]:
    """An episode and one call inside it, whose setup declares `TOOLS`."""
    own = f"{number:032x}"
    child_setup: dict[str, object] = {
        "model": "m",
        "tools": [{"name": tool} for tool in TOOLS],
    }
    return [
        Recording(
            source_tenant="acme",
            app="support",
            suite=suite,
            case={"question": f"{SECRET_INPUT} {number}"},
            setup={"child_setups": [setup_digest_of(child_setup)]},
            setup_digest="e" * 16,
            response=RecordedResponse(
                output=f"{output} {number}",
                kind="text",
                input=f"{SECRET_INPUT} {number}",
                steps=trajectory(*tools),
            ),
            id=own,
            recorded_at=f"2026-11-06T08:{number:02d}:00+00:00",
        ),
        Recording(
            source_tenant="acme",
            app="support",
            suite=suite,
            case={"question": f"{SECRET_INPUT} {number}"},
            setup=child_setup,
            setup_digest=setup_digest_of(child_setup),
            response=RecordedResponse(output="calling", kind="text"),
            episode=own,
            recorded_at=f"2026-11-06T08:{number:02d}:01+00:00",
        ),
    ]


def single(
    number: int, output: str, *, kind: OutputKind = "text", suite: str = "triage"
) -> Recording:
    setup: dict[str, object] = {"model": "m"}
    return Recording(
        source_tenant="acme",
        app="support",
        suite=suite,
        case={"question": f"{SECRET_INPUT} {number}"},
        setup=setup,
        setup_digest=setup_digest_of(setup),
        response=RecordedResponse(
            output=output,
            kind=kind,
            input=f"{SECRET_INPUT} {number}",
        ),
        recorded_at=f"2026-11-06T09:{number:02d}:00+00:00",
    )


def unassigned() -> Recording:
    setup: dict[str, object] = {
        "model": "m",
        "tools": [{"name": SECRET_UNASSIGNED_TOOL}],
    }
    return Recording(
        source_tenant="acme",
        app="support",
        suite=UNASSIGNED,
        case={"question": SECRET_UNASSIGNED},
        setup=setup,
        setup_digest=setup_digest_of(setup),
        response=RecordedResponse(
            output=SECRET_UNASSIGNED,
            kind="text",
            input=SECRET_UNASSIGNED,
            steps=trajectory(SECRET_UNASSIGNED_TOOL),
        ),
        call_site="app:handler",
        recorded_at="2026-11-06T10:00:00+00:00",
    )


def write(root: Path, recordings: Sequence[Recording]) -> None:
    writer = RecordingWriter(FileResultStore(root))
    for recording in recordings:
        writer.write(recording)


#: Three episodes: every one looks the order up first, two refund after it,
#: one mails between, and none deletes an account.
EPISODES = [
    *episode(1, "lookup_order", "issue_refund"),
    *episode(2, "lookup_order", "send_email", "issue_refund"),
    *episode(3, "lookup_order"),
]


def reviewed(case_id: str, *, good: bool) -> dict[str, object]:
    return {
        "id": case_id,
        "reviewed_answer": {
            "output": f"{SECRET_ANSWER} {case_id}",
            "check": "llm_rubric",
            "good": good,
            "input": SECRET_INPUT,
        },
        "metadata": {"source": "recordings", "reviewed_by": "Ada"},
    }


def existing(root: Path, *, noes: int = 1) -> Path:
    """A suite.toml that declares its capture, with one yes and `noes` noes
    a person gave, and the recordings of three episodes and an unassigned
    call."""
    (root / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    cases = [reviewed("cap-yes", good=True)]
    cases += [reviewed(f"cap-no-{n}", good=False) for n in range(noes)]
    (root / "captured.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    write(root, [*EPISODES, unassigned()])
    return root / "suite.toml"


def proposal(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / PROPOSAL).read_text(encoding="utf-8"))


def checks(root: Path) -> list[dict[str, Any]]:
    return list(proposal(root).get("assertions", []))


def types(root: Path) -> list[str]:
    return [check["type"] for check in checks(root)]


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# It writes the proposal and nothing else.


def test_it_writes_the_proposal_and_nothing_else(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    before = tree(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    after = tree(here)
    assert set(after) - set(before) == {PROPOSAL}
    assert {k: v for k, v in after.items() if k != PROPOSAL} == before


def test_a_second_run_refuses_by_name_and_keeps_the_file(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    (here / PROPOSAL).write_text("# mine now\n", encoding="utf-8")
    capsys.readouterr()
    assert main("suggest", "--suite", "suite.toml") == 64
    said = capsys.readouterr().err
    assert f"{PROPOSAL} is already there" in said
    assert "Move it or delete it" in said
    assert (here / PROPOSAL).read_text(encoding="utf-8") == "# mine now\n"


# It marks nothing, and no command reads the file.


def test_nothing_is_marked_and_the_suite_loads_as_before(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    suite, _ = load_suite("suite.toml", root=here)
    cases = (here / "captured.json").read_bytes()
    assert main("suggest", "--suite", "suite.toml") == 0
    again, _ = load_suite("suite.toml", root=here)
    assert again.config_hash() == suite.config_hash()
    assert [c.id for c in again.cases] == [c.id for c in suite.cases]
    assert (here / "captured.json").read_bytes() == cases
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    for mark in ('"good"', "reviewed_answer", "reviewed_by", '"label"'):
        assert mark not in written
    assert not list((here / ".digline" / "acme" / "baselines").rglob("*.json"))


# A check on the steps holds on every recording, or is not proposed.


def test_a_check_on_the_steps_is_proposed_where_every_recording_holds_it(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    found = checks(here)
    befores = {(c["first"], c["then"]) for c in found if c["type"] == "before"}
    assert ("lookup_order", "issue_refund") in befores
    assert ("lookup_order", "send_email") in befores
    assert ("send_email", "issue_refund") not in befores
    nevers = [c["tool"] for c in found if c["type"] == "never"]
    assert nevers == ["delete_account"]
    assert "tools_called" not in types(here)
    assert "subsequence" not in types(here)


def test_one_contradicting_recording_takes_the_check_out(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    write(here, episode(4, "issue_refund", "lookup_order"))
    assert main("suggest", "--suite", "suite.toml") == 0
    befores = {(c["first"], c["then"]) for c in checks(here) if c["type"] == "before"}
    assert ("lookup_order", "issue_refund") not in befores
    assert ("lookup_order", "send_email") in befores


def test_one_recording_that_calls_it_takes_never_out(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    write(here, episode(4, "lookup_order", "delete_account"))
    assert main("suggest", "--suite", "suite.toml") == 0
    assert [c["tool"] for c in checks(here) if c["type"] == "never"] == []


def test_the_same_tools_in_every_recording_are_tools_called(
    here: Path, fake_provider: None
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(here, [*episode(1, "lookup_order", "issue_refund")] * 1)
    write(here, episode(2, "lookup_order", "issue_refund"))
    assert main("suggest", "--suite", "suite.toml") == 0
    [called] = [c for c in checks(here) if c["type"] == "tools_called"]
    assert called["expected"] == ["lookup_order", "issue_refund"]
    # Said by the sequence, so not said again by a pair.
    assert "before" not in types(here)


def test_a_common_order_of_two_or_more_is_a_subsequence(
    here: Path, fake_provider: None
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(here, episode(1, "lookup_order", "issue_refund"))
    write(here, episode(2, "lookup_order", "send_email", "issue_refund"))
    assert main("suggest", "--suite", "suite.toml") == 0
    [common] = [c for c in checks(here) if c["type"] == "subsequence"]
    assert common["tools"] == ["lookup_order", "issue_refund"]


def test_a_tool_nobody_named_takes_out_every_check_that_names_tools(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    write(here, episode(4, "lookup_order", None))
    assert main("suggest", "--suite", "suite.toml") == 0
    assert not {"before", "never", "tools_called", "subsequence"} & set(types(here))
    assert "max_steps" in types(here)


# The counterexample.


def test_the_counterexample_is_the_reviewed_noes_and_the_suite_fails_on_them(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adopted whole: the proposal's lines appended to the suite. Its judge
    says yes to everything, so on the person's no the gate is red."""
    existing(here, noes=2)
    assert main("suggest", "--suite", "suite.toml") == 0
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    assert "#   cap-no-0" in written and "#   cap-no-1" in written
    assert "counterexample-1" not in written
    assert "2 reviewed noes for llm_rubric" in capsys.readouterr().err
    with (here / "suite.toml").open("a", encoding="utf-8") as suite:
        suite.write("\n" + written)
    load_suite("suite.toml", root=here)
    assert main("run", "--suite", "suite.toml") == 0
    out = str(here / "report.html")
    reported = main(
        "report", "--suite", "suite.toml", "--run", "latest", "--locale", "en",
        "--out", out,
    )  # fmt: skip
    assert reported == 1


def test_with_no_reviewed_no_the_counterexample_is_constructed_and_marked(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here, noes=0)
    assert main("suggest", "--suite", "suite.toml") == 0
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    [line] = [line for line in written.splitlines() if "counterexample-1" in line]
    case = json.loads(line.removeprefix("# "))
    assert case["id"] == "counterexample-1"
    assert case["vars"] == {"question": "WRITE"}
    assert "not recorded" in case["metadata"]["constructed"]
    assert "constructed and marked as constructed" in capsys.readouterr().err


# The calls no suite named.


def test_unassigned_calls_are_counted_and_never_quoted(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    said = capsys.readouterr()
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    for text in (SECRET_UNASSIGNED, SECRET_UNASSIGNED_TOOL):
        assert text not in written
        assert text not in said.out + said.err
    assert f"1 call of tenant 'acme' named no suite ({UNASSIGNED})" in said.err
    assert f"--from {UNASSIGNED}" in said.err


# A suite that does not exist yet.


@pytest.mark.parametrize("regime", ["private", "public"])
def test_a_suite_that_does_not_exist_is_proposed_with_the_regime_given(
    here: Path, regime: str
) -> None:
    write(here, EPISODES)
    code = main(
        "suggest", "--suite", "triage", "--tenant", "acme", "--repository", regime
    )
    assert code == 0
    found = proposal(here)
    assert found["capture"] == {
        "cases_file": "captured.json",
        "repository": regime,
        "check": "llm_rubric",
    }
    assert found["suite"]["tenant"] == "acme"
    assert found["suite"]["name"] == "triage"
    assert "environment" not in found["suite"]
    assert found["suite"]["cases"] == ["captured.json"]


@pytest.mark.parametrize(
    ("given", "named"),
    [
        (("--tenant", "acme"), "--repository"),
        (("--repository", "private"), "--tenant"),
        ((), "--tenant and --repository"),
    ],
)
def test_without_a_flag_a_suite_that_does_not_exist_is_refused_naming_it(
    here: Path, given: tuple[str, ...], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    assert main("suggest", "--suite", "triage", *given) == 64
    assert f"that needs {named}:" in capsys.readouterr().err
    assert not (here / PROPOSAL).exists()


def test_another_regime_is_refused_by_name(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    assert (
        main("suggest", "--suite", "triage", "--tenant", "acme", "--repository", "x")
        == 64
    )
    assert "--repository takes 'private' or 'public'" in capsys.readouterr().err


def test_where_the_suite_exists_repository_is_refused(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml", "--repository", "public") == 64
    said = capsys.readouterr().err
    assert "--repository is refused where the suite exists" in said
    assert not (here / PROPOSAL).exists()


def test_where_the_suite_exists_another_tenant_is_refused(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml", "--tenant", "other") == 64
    assert "--tenant 'other' does not match the suite" in capsys.readouterr().err


def test_a_new_suite_is_written_in_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    work = tmp_path / "work"
    work.mkdir()
    write(root, EPISODES)
    monkeypatch.chdir(work)
    code = main(
        "suggest", "--suite", "triage", "--root", str(root),
        "--tenant", "acme", "--repository", "private",
    )  # fmt: skip
    assert code == 0
    assert (work / PROPOSAL).is_file()
    assert not (root / PROPOSAL).exists()


def test_a_proposal_for_a_new_suite_does_not_load_as_it_is(
    here: Path, fake_provider: None
) -> None:
    """Its placeholders refuse rather than pass: the judge is no plugin's,
    and the environment has no line."""
    write(here, EPISODES)
    assert (
        main(
            "suggest",
            "--suite",
            "triage",
            "--tenant",
            "acme",
            "--repository",
            "private",
        )  # fmt: skip
        == 0
    )
    (here / PROPOSAL).rename(here / "suite.toml")
    with pytest.raises(Exception, match="no provider named 'provider'"):
        load_suite("suite.toml", root=here)


def test_nothing_recorded_proposes_nothing_and_says_where_a_suite_begins(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            "suggest",
            "--suite",
            "triage",
            "--tenant",
            "acme",
            "--repository",
            "private",
        )  # fmt: skip
        == 0
    )
    assert not (here / PROPOSAL).exists()
    assert "digline record on --tenant acme" in capsys.readouterr().err


# No model.


def test_with_no_model_declared_no_provider_is_reached(
    here: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reached() -> dict[str, object]:
        raise AssertionError("a provider plugin was looked up")

    monkeypatch.setattr("digline.targets.registry._entry_points", reached)
    write(here, EPISODES)
    found = suggest_new(here, "triage", tenant="acme", repository="private", here=here)
    assert found.path == here / PROPOSAL


# Recorded text.


@pytest.mark.parametrize("regime", ["private", "public"])
def test_no_recorded_text_in_the_file_or_on_either_stream(
    here: Path, regime: str, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [*EPISODES, single(1, SECRET_ANSWER, suite="other"), unassigned()])
    code = main(
        "suggest", "--suite", "triage", "--tenant", "acme", "--repository", regime
    )
    assert code == 0
    said = capsys.readouterr()
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    assert said.out == ""
    for text in (SECRET_INPUT, SECRET_ANSWER, SECRET_UNASSIGNED):
        assert text not in written
        assert text not in said.err
    # The rules read from the recordings are in the checks, and on no stream.
    assert "lookup_order" in written
    assert "lookup_order" not in said.err


def test_the_assumptions_are_said_in_the_skills_words(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    said = capsys.readouterr().err
    for words in (
        "  the form: ",
        "  the setup its target reproduces: ",
        "  the judge: ",
        "  each check: ",
        "  each starting number: ",
        "  the calibration band: ",
        "  the counterexample: ",
    ):
        assert words in said
    assert "not yet examined: group 1 · episodes, text · 1 answer of 1" in said


# The rules beneath.


def contrary(check: Any) -> EvaluatorInputs:
    """An answer the check must refuse, for each kind the proposal writes."""
    name = type(check).__name__
    if name == "Before":
        return EvaluatorInputs(
            output="o", metadata={"response": {"tools": [check.then]}}
        )
    if name == "Never":
        return EvaluatorInputs(
            output="o", metadata={"response": {"tools": [check.tool]}}
        )
    if name in ("ToolsCalled", "Subsequence"):
        return EvaluatorInputs(output="o", metadata={"response": {"tools": []}})
    if name == "MaxSteps":
        steps = [
            {"index": i, "actor": "model", "finish": "stop"}
            for i in range(check.limit + 1)
        ]
        return EvaluatorInputs(output="o", metadata={"response": {"steps": steps}})
    if name == "Length":
        return EvaluatorInputs(output="x" * ((check.maximum or 0) + 1))
    if name == "IsJson":
        return EvaluatorInputs(output="not json")
    if name == "JsonSchema":
        return EvaluatorInputs(output="[]")
    raise AssertionError(f"no contrary answer for {name}")


@pytest.mark.parametrize("shape", ["episodes", "json", "text"])
def test_every_check_proposed_can_fail(
    here: Path, fake_provider: None, shape: str
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(
        here,
        {
            "episodes": EPISODES,
            "json": [single(1, '{"a": 1}'), single(2, '{"a": 2, "b": "x"}')],
            "text": [single(1, "one"), single(2, "two")],
        }[shape],
    )
    assert main("suggest", "--suite", "suite.toml") == 0
    with (here / "suite.toml").open("a", encoding="utf-8") as suite:
        suite.write("\n" + (here / PROPOSAL).read_text(encoding="utf-8"))
    adopted, _ = load_suite("suite.toml", root=here)
    added = [a for a in adopted.assertions if type(a).__name__ != "LlmRubric"]
    assert added
    for check in added:
        assert check(contrary(check)).status == "fail", check


def test_a_placeholder_is_the_strictest_value_and_marked(
    here: Path, fake_provider: None
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    [steps] = [c for c in checks(here) if c["type"] == "max_steps"]
    assert steps["limit"] == PLACEHOLDER["max_steps.limit"]
    assert "limit = 1  # placeholder: yours to write" in written


def test_a_limit_is_read_from_the_runs_where_they_measured_it(
    here: Path, fake_provider: None
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(here, [single(1, "one"), single(2, "two")])
    store = FileResultStore(here)
    for n, answers in enumerate((("abcd",), ("abcdefgh", "ab"))):
        store.write_run(
            Run(
                tenant="acme",
                environment="dev",
                suite="triage",
                config_hash="0" * 16,
                created_at=f"2026-11-06T10:0{n}:00+00:00",
                results=[
                    CaseResult(
                        case_id=f"c{n}",
                        responses=tuple(
                            RecordedResponse(output=a, kind="text") for a in answers
                        ),
                    )
                ],
            )
        )
    assert main("suggest", "--suite", "suite.toml") == 0
    [length] = [c for c in checks(here) if c["type"] == "length"]
    assert length["maximum"] == 8
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    assert "maximum = 8\n" in written


def test_a_json_answer_proposes_is_json_and_the_keys_every_one_carries(
    here: Path, fake_provider: None
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(
        here,
        [
            single(1, '{"category": "refund", "urgent": true, "n": 1}'),
            single(2, '{"category": "other", "urgent": false, "n": 1.5, "x": 1}'),
        ],
    )
    assert main("suggest", "--suite", "suite.toml") == 0
    found = {c["type"]: c for c in checks(here)}
    assert found["is_json"]["top_level"] == "object"
    assert found["json_schema"]["schema"] == {
        "type": "object",
        "required": ["category", "urgent", "n"],
        "properties": {
            "category": {"type": "string"},
            "urgent": {"type": "boolean"},
            "n": {"type": "number"},
        },
    }
    assert "length" not in found


def test_answers_of_two_kinds_propose_no_shape(here: Path, fake_provider: None) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(here, [single(1, "text"), single(2, '{"a": 1}', kind="structured")])
    assert main("suggest", "--suite", "suite.toml") == 0
    assert not {"is_json", "json_schema", "length"} & set(types(here))


def test_a_check_the_suite_declares_is_not_proposed_again(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    assert "repeated" not in types(here)
    assert "the one suite 'triage' declares for llm_rubric" in capsys.readouterr().err


def test_a_suite_with_no_capture_is_refused_by_name(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    head, _, _ = SUITE_TOML.partition("[capture]")
    (here / "suite.toml").write_text(
        head.replace('cases = ["captured.json"]', 'cases = ["cases.json"]')
        + SUITE_TOML.partition("[[assertions]]")[1]
        + SUITE_TOML.partition("[[assertions]]")[2],
        encoding="utf-8",
    )
    (here / "cases.json").write_text(
        json.dumps([reviewed("cap-x", good=True)]), encoding="utf-8"
    )
    assert main("suggest", "--suite", "suite.toml") == 64
    assert "declares no capture source" in capsys.readouterr().err


def test_suggest_new_refuses_an_unsafe_name() -> None:
    with pytest.raises(PathRefusedError):
        suggest_new(
            Path("."), "../x", tenant="acme", repository="private", here=Path(".")
        )


def test_a_shape_check_the_suite_declares_is_not_proposed_again(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    (here / "suite.toml").write_text(
        SUITE_TOML + '\n[[assertions]]\ntype = "length"\nmaximum = 500\n',
        encoding="utf-8",
    )
    write(here, [single(1, "one"), single(2, "two")])
    assert main("suggest", "--suite", "suite.toml") == 0
    assert "length" not in types(here)
    assert "length is not proposed again" in capsys.readouterr().err
