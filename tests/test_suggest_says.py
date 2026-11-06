"""`digline suggest`: what it says on standard error, and the sentences it is
refused with, as a person running it for the first time reads them.
(ADR 0063 §5, §6)

- beside the setup in force, every earlier setup of its form, and the
  command that says how two differ, which runs;
- a `suite.toml` that leaves out a mandatory `[suite]` key is refused in
  digline's words, naming the key;
- the judge's line names the provider plugins installed, and the file's
  judge points at the page that says how to write one;
- on a suite that exists, the placeholders adopted and still at their most
  severe value are counted, and a run with no case is not a run read;
- a name with runs under the tenant and no suite file stops, naming it;
- a proposal already there is refused with the suite it was written for;
- with the recorder on and no call naming the suite, `record on` is not
  proposed: the suites with recordings are named;
- a new suite's groups are counted in answers, as `record import` counts
  them;
- without an assistant, the regime's line says so.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from tests.test_suggest import EPISODES, SUITE_TOML, existing, main, single, write

from digline.core.recording import Recording, setup_digest_of
from digline.core.run import CaseResult, RecordedResponse, Run
from digline.host import PROPOSAL, load_suite
from digline.host.errors import UsageError
from digline.host.recording import switch_on
from digline.store.file_store import FileResultStore


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def new(*more: str) -> int:
    return main(
        "suggest", "--suite", "triage", "--tenant", "acme", "--repository", "private",
        *more,
    )  # fmt: skip


def under(recording: Recording, model: str) -> Recording:
    """The same call, made under a setup that names another model."""
    setup: dict[str, object] = {"model": model}
    return dataclasses.replace(
        recording, setup=setup, setup_digest=setup_digest_of(setup)
    )


def digest(model: str) -> str:
    return setup_digest_of({"model": model})[:8]


def a_run(root: Path, suite: str, *, cases: int) -> None:
    FileResultStore(root).write_run(
        Run(
            tenant="acme",
            environment="dev",
            suite=suite,
            config_hash="0" * 16,
            created_at="2026-11-06T10:00:00+00:00",
            results=[
                CaseResult(
                    case_id=f"c{n}",
                    responses=(RecordedResponse(output="abcd", kind="text"),),
                )
                for n in range(cases)
            ],
        )
    )


# The setups.


def test_every_setup_of_a_form_is_named_and_the_command_that_compares_two_runs(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    (here / "suite.toml").write_text(SUITE_TOML, encoding="utf-8")
    write(
        here,
        [
            under(single(1, "one"), "a"),
            under(single(2, "two"), "b"),
            under(single(3, "three"), "c"),
        ],
    )
    assert main("suggest", "--suite", "suite.toml") == 0
    said = capsys.readouterr().err
    assert (
        f"  the setup its target reproduces: {digest('c')} for single calls, "
        f"the newest of 3 recorded, after {digest('a')}, {digest('b')}\n"
    ) in said
    command = (
        "digline record compare --tenant acme --suite <your suite> "
        f"--setup {digest('b')} {digest('c')} --show-setup"
    )
    assert f"  to read how two setups differ: {command}\n" in said
    # The command it says is one digline runs, with the suite's path given.
    assert main(*command.replace("<your suite>", "suite.toml").split()[1:]) == 0
    assert "keys the two setups differ on" in capsys.readouterr().out


def test_one_setup_has_none_to_compare_it_with(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [single(1, "one"), single(2, "two")])
    assert new() == 0
    said = capsys.readouterr().err
    assert (
        f"  the setup its target reproduces: {digest('m')} for single calls\n" in said
    )
    assert "to read how two setups differ" not in said


def test_the_setups_in_force_of_both_forms_are_named_and_compared(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [*EPISODES, single(9, "one")])
    assert new() == 0
    said = capsys.readouterr().err
    assert (
        f"  the setup its target reproduces: {digest('m')} for single calls; "
        "eeeeeeee for episodes\n"
    ) in said
    assert (
        "  to read how two setups differ, once the proposal is your suite: "
        "digline record compare --tenant acme --suite <your suite> --setup "
        f"{digest('m')} eeeeeeee --show-setup\n"
    ) in said


# A mandatory key of [suite].


@pytest.mark.parametrize("key", ["environment", "tenant", "name"])
def test_a_mandatory_suite_key_left_out_is_named_in_digline_s_words(
    here: Path, fake_provider: None, key: str
) -> None:
    text = "\n".join(
        line for line in SUITE_TOML.splitlines() if not line.startswith(f"{key} =")
    )
    (here / "suite.toml").write_text(text, encoding="utf-8")
    (here / "captured.json").write_text("[]", encoding="utf-8")
    with pytest.raises(UsageError) as refused:
        load_suite("suite.toml", root=here)
    said = str(refused.value)
    assert f"suite.toml, [suite]: no `{key}`. It is mandatory, with no default" in said
    assert "__init__" not in said
    assert "positional" not in said


def test_two_mandatory_keys_left_out_are_both_named(
    here: Path, fake_provider: None
) -> None:
    text = SUITE_TOML.replace('environment = "dev"\n', "").replace(
        'name = "triage"\n', ""
    )
    (here / "suite.toml").write_text(text, encoding="utf-8")
    with pytest.raises(UsageError, match=r"no `environment` and no `name`\. Each is"):
        load_suite("suite.toml", root=here)


# The judge.


def test_the_judge_s_line_names_the_plugins_installed_and_the_file_its_page(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    assert new() == 0
    said = capsys.readouterr().err
    [line] = [x for x in said.splitlines() if x.startswith("  the judge: ")]
    assert line.endswith("; the provider plugins installed here: fake")
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    assert (
        'judge = "provider/model"  # placeholder: yours to write, '
        "docs/declarative.md#the-judge-by-coordinates\n"
    ) in written


def test_the_judge_s_line_says_where_no_plugin_is_installed(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def none() -> dict[str, object]:
        return {}

    monkeypatch.setattr("digline.targets.registry._entry_points", none)
    write(here, EPISODES)
    assert new() == 0
    assert "; no provider plugin is installed here\n" in capsys.readouterr().err


def test_the_page_the_file_points_at_has_the_heading() -> None:
    page = Path(__file__).parent.parent / "docs" / "declarative.md"
    assert "\n## The judge, by coordinates\n" in page.read_text(encoding="utf-8")


# The placeholders adopted, and the runs read.


ADOPTED = (
    SUITE_TOML
    + """
[[assertions]]
type = "length"
maximum = 0  # placeholder: yours to write
unit = "characters"

[[assertions]]
type = "max_steps"
limit = 1  # placeholder: yours to write
count = "model"

[[assertions]]
type = "cost_budget"
max_usd = 0.25  # placeholder: yours to write
tolerance = 0.0

[[assertions]]
type = "latency_budget"
max_ms = 0.000001
tolerance = 0.0
"""
)


def test_the_placeholders_adopted_and_still_at_their_most_severe_are_counted(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    (here / "suite.toml").write_text(ADOPTED, encoding="utf-8")
    assert main("suggest", "--suite", "suite.toml") == 0
    said = capsys.readouterr().err
    lines = ADOPTED.splitlines()
    at = [
        n
        for n, line in enumerate(lines, start=1)
        if line.startswith(("maximum = 0", "limit = 1"))
    ]
    # A value replaced is the person's, and so is a mark taken off.
    assert (
        "  each starting number: 2 placeholders you adopted are still at their "
        f"most severe value, in suite.toml at lines {at[0]}, {at[1]}: each "
        "fails until a measured number replaces it\n"
    ) in said


def test_one_placeholder_adopted_is_said_in_the_singular(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    text = SUITE_TOML + (
        '\n[[assertions]]\ntype = "max_steps"\nlimit = 1  # placeholder\n'
        'count = "model"\n'
    )
    (here / "suite.toml").write_text(text, encoding="utf-8")
    assert main("suggest", "--suite", "suite.toml") == 0
    line = text.splitlines().index("limit = 1  # placeholder") + 1
    assert (
        "1 placeholder you adopted is still at its most severe value, in "
        f"suite.toml at line {line}:"
    ) in capsys.readouterr().err


def test_no_placeholder_adopted_says_nothing_of_them(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    assert "you adopted" not in capsys.readouterr().err


def test_a_run_with_no_case_is_not_a_run_read(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    a_run(here, "triage", cases=0)
    assert main("suggest", "--suite", "suite.toml") == 0
    said = capsys.readouterr().err
    assert "1 run read" not in said
    assert (
        "  each starting number: 0 runs read, 1 run with no case, not counted;" in said
    )


def test_a_run_with_a_case_is_a_run_read(
    here: Path, fake_provider: None, capsys: pytest.CaptureFixture[str]
) -> None:
    existing(here)
    a_run(here, "triage", cases=1)
    assert main("suggest", "--suite", "suite.toml") == 0
    assert "  each starting number: 1 run read;" in capsys.readouterr().err


# A name that already has runs.


@pytest.mark.parametrize("given", [("--repository", "private"), ()])
def test_a_name_with_runs_and_no_suite_file_stops(
    here: Path, given: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [single(1, "one", suite="screening")])
    a_run(here, "screening", cases=1)
    assert main("suggest", "--suite", "screening", "--tenant", "acme", *given) == 64
    said = capsys.readouterr().err
    assert (
        "'screening' has runs under this tenant but no suite file here: give the path"
    ) in said
    assert not (here / PROPOSAL).exists()


def test_a_name_with_runs_under_another_tenant_is_proposed(here: Path) -> None:
    write(here, [single(1, "one", suite="screening")])
    FileResultStore(here).write_run(
        Run(
            tenant="other",
            environment="dev",
            suite="screening",
            config_hash="0" * 16,
            created_at="2026-11-06T10:00:00+00:00",
        )
    )
    assert (
        main(
            "suggest",
            "--suite",
            "screening",
            "--tenant",
            "acme",
            "--repository",
            "private",
        )  # fmt: skip
        == 0
    )
    assert (here / PROPOSAL).exists()


# A proposal already there.


def test_a_proposal_already_there_is_refused_with_the_suite_it_is_for(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [single(1, "one", suite="pluto-step")])
    args = ("--tenant", "acme", "--repository", "private")
    assert main("suggest", "--suite", "pluto-step", *args) == 0
    capsys.readouterr()
    write(here, [single(1, "one", suite="triage")])
    assert main("suggest", "--suite", "triage", *args) == 64
    said = capsys.readouterr().err
    assert f"{PROPOSAL} here is the proposal for 'pluto-step'" in said


def test_a_file_of_that_name_digline_did_not_write_names_no_suite(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (here / PROPOSAL).write_text("# mine\n", encoding="utf-8")
    write(here, EPISODES)
    assert new() == 64
    said = capsys.readouterr().err
    assert f"{PROPOSAL} is already there. digline suggest does not overwrite" in said
    assert "is the proposal for" not in said


# The recorder on, and no call that named the suite.


def test_with_the_recorder_on_the_suites_recorded_are_named_not_record_on(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    switch_on(here, "acme", production=False)
    write(here, [single(1, "one", suite="screening"), single(2, "two", suite="b")])
    assert new() == 0
    said = capsys.readouterr().err
    assert (
        "The recorder of tenant 'acme' is on, and no call it recorded named "
        "'triage': the suites with recordings are 'b', 'screening'"
    ) in said
    assert "record on" not in said
    assert not (here / PROPOSAL).exists()


def test_with_the_recorder_off_record_on_is_proposed(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, [single(1, "one", suite="screening")])
    assert new() == 0
    said = capsys.readouterr().err
    assert "digline record on --tenant acme, which is yours to run" in said
    assert "is on" not in said


# Answers, as record import counts them.


def test_a_new_suite_s_groups_are_counted_in_answers(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same input answered the same way twice is one answer.
    write(here, [single(1, "same"), single(1, "same"), single(2, "other")])
    assert new() == 0
    said = capsys.readouterr().err
    assert (
        "not yet examined: group 1 · single calls, text · 2 answers from 3 recordings\n"
    ) in said


# The regime.


def test_without_an_assistant_the_regime_s_line_says_so(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    assert new() == 0
    said = capsys.readouterr().err
    assert (
        "  the regime: repository = 'private': without an assistant, the file "
        "quotes no recorded input or answer; "
    ) in said
    assert "under either regime" not in said


# The file's comments.


def test_the_file_says_where_its_cases_come_from_and_what_answers_its_counterexample(
    here: Path,
) -> None:
    write(here, EPISODES)
    assert new() == 0
    written = (here / PROPOSAL).read_text(encoding="utf-8")
    assert (
        "# captured.json is written by digline record import; until\n"
        "# then the suite has no case.\n"
        'cases = ["captured.json"]\n'
    ) in written
    assert (
        "# refuse. It is answered by the target, so the suite needs a\n# [target]:"
        in (written)
    )
    # The comments are comments: the file still parses, and its line is JSON.
    [line] = [x for x in written.splitlines() if '"counterexample-1"' in x]
    assert json.loads(line[2:])["id"] == "counterexample-1"
