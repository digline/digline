"""The proposal `digline suggest` wrote, shown read only at the page.
(ADR 0063, the read-only view ruled 2026-11-09; P-1598)

What is held here:

- the file is read as suggest writes it: each check in the file's order, why
  it is there, each value with its mark, the placeholders as placeholders and
  a value the assistant wrote as the assistant's, not measured; the
  counterexample and the calibration skeleton;
- the page renders it so, and under it the command that writes one, without
  and with `--model`, and that suggest does not overwrite it;
- with no file, where it looked and the two commands;
- no recorded word reaches the page: the page reads the file alone;
- a line it cannot place is shown as it stands, and a file that is no TOML is
  said, not a 500;
- `where` names the proposal in `no_suite_yet`, in its sentence, its `--json`
  and its page; and over the server started without a suite.

The policy, the locale, *a GET writes nothing* and *a POST is a 404* are held
for this view with every other one, in `tests/test_view_recorder.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.test_suggest import (
    EPISODES,
    SECRET_ANSWER,
    SECRET_INPUT,
    existing,
    main,
    write,
)
from tests.test_suggest_assistant import (  # noqa: F401 — a fixture, by its name
    MODEL,
    checks,
    fake_provider,  # pyright: ignore[reportUnusedImport]
    new,
    upstream,
)
from tests.test_view_tenant import get, record, viewing

from digline.cli.recorder_pages import proposal_page
from digline.host import UsageError, read_proposal, suggest_lines
from digline.host.proposal import found_proposal, proposal_places
from digline.host.toml_suite import PROPOSAL
from digline.report.pages import proposal_address


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def page(path: Path, *, suite: str = "triage", locale: str = "en") -> str:
    found = read_proposal(path)
    return proposal_page(
        found,
        suite=suite,
        places=[str(path)],
        lines=suggest_lines(found, suite_arg=None, suite=suite, tenant="acme", root=[]),
        shown_path=str(path),
        invalid=None,
        locale=locale,  # pyright: ignore[reportArgumentType]
    )


def marked_rows(html: str, mark: str) -> list[str]:
    """The keys of the rows whose last cell says `mark`."""
    keys: list[str] = []
    for chunk in html.split("<tr><td><code>")[1:]:
        key = chunk.split("</code>", 1)[0]
        if chunk.split("</tr>", 1)[0].endswith(f">{mark}</td>"):
            keys.append(key)
    return keys


# -- the file, as suggest writes it ------------------------------------------- #


def test_every_placeholder_the_file_marks_is_marked_on_the_page(here: Path) -> None:
    write(here, EPISODES)
    assert new("private") == 0
    text = (here / PROPOSAL).read_text(encoding="utf-8")
    found = read_proposal(here / PROPOSAL)
    marked = [
        param.key
        for block in found.checks
        for param in block.params
        if param.mark is not None and param.mark.kind == "placeholder"
    ]
    assert len(marked) == text.count("# placeholder: yours to write")
    assert [block.type for block in found.checks] == [c["type"] for c in checks(here)]
    assert all(block.why for block in found.checks)
    html = page(here / PROPOSAL)
    shown = marked_rows(html, "a placeholder: yours to write")
    assert sorted(shown) == sorted(marked)
    assert "inner.judge" in shown and "inner.rubric" in shown
    assert found.counterexample is not None and "counterexample-1" in html
    assert found.calibration is not None and "calibration-llm_rubric" in html
    assert found.unread == ()


def test_a_value_the_assistant_wrote_is_its_own_not_a_measure(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(here, EPISODES)
    upstream(monkeypatch, capsys, {})
    assert new("private") == 0
    numbered = {n: c["type"] for n, c in enumerate(checks(here), start=1)}
    (here / PROPOSAL).unlink()
    length = next(n for n, t in numbered.items() if t == "length")
    upstream(monkeypatch, capsys, {"limits": {f"check-{length}.maximum": 400}})
    assert new("private", "--model", MODEL) == 0
    html = page(here / PROPOSAL)
    assert "maximum" in marked_rows(html, "from the assistant, not measured")
    assert "maximum" not in marked_rows(html, "a placeholder: yours to write")
    italian = page(here / PROPOSAL, locale="it")
    assert "maximum" in marked_rows(italian, "dall&#x27;assistente, non misurato")


def test_under_it_the_command_without_and_with_a_model_and_no_button(
    here: Path,
) -> None:
    write(here, EPISODES)
    assert new("public") == 0
    html = page(here / PROPOSAL)
    plain = "digline suggest --suite triage --tenant acme --repository public"
    assert f'<pre class="snippet">{plain}</pre>' in html
    assert (
        f'<pre class="snippet">{plain} --model &#x27;&lt;provider/model&gt;&#x27;</pre>'
        in html
    )
    assert "does not overwrite a proposal: move or delete" in html
    assert "<form" not in html and "<button" not in html


@pytest.mark.usefixtures("fake_provider")
def test_no_recorded_word_reaches_the_page(here: Path) -> None:
    """The control: the markers are in what the store holds, which suggest
    read, and in the cases file beside the suite. The page reads the file
    alone, and none of them is there."""
    existing(here)
    assert main("suggest", "--suite", "suite.toml") == 0
    stored = "".join(
        path.read_text(encoding="utf-8")
        for path in here.rglob("*.json")
        if path.is_file()
    )
    assert SECRET_INPUT in stored and SECRET_ANSWER in stored
    html = page(here / PROPOSAL)
    assert SECRET_INPUT not in html and SECRET_ANSWER not in html


def test_a_line_it_cannot_place_is_shown_as_it_stands(here: Path) -> None:
    write(here, EPISODES)
    assert new("private") == 0
    with (here / PROPOSAL).open("a", encoding="utf-8") as handle:
        handle.write("\n# a note of mine, after the skeleton\n")
    found = read_proposal(here / PROPOSAL)
    assert found.unread == ("a note of mine, after the skeleton",)
    assert "a note of mine, after the skeleton" in page(here / PROPOSAL)


def test_a_file_that_is_no_toml_is_refused_where_it_is(here: Path) -> None:
    (here / PROPOSAL).write_text("[[assertions]\n", encoding="utf-8")
    with pytest.raises(UsageError, match="is not valid TOML"):
        read_proposal(here / PROPOSAL)


# -- where it is looked for ---------------------------------------------------- #


def test_it_is_looked_for_where_suggest_writes_it_and_nowhere_else(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "eval" / "suite.toml"
    assert proposal_places(suite_file, tmp_path, tmp_path / "x") == (
        tmp_path / "eval" / PROPOSAL,
    )
    assert proposal_places(None, tmp_path, tmp_path / "x") == (
        tmp_path / PROPOSAL,
        tmp_path / "x" / PROPOSAL,
    )
    assert proposal_places(None, tmp_path, tmp_path) == (tmp_path / PROPOSAL,)
    # Below the root is not looked in: no walk.
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / PROPOSAL).write_text(
        '# suite.proposed.toml, written by `digline suggest` for suite "t".\n',
        encoding="utf-8",
    )
    assert found_proposal(proposal_places(None, tmp_path, tmp_path), "t") is None


def test_a_proposal_for_another_suite_is_not_this_one(here: Path) -> None:
    write(here, EPISODES)
    assert new("private") == 0
    assert found_proposal((here / PROPOSAL,), "triage") == here / PROPOSAL
    assert found_proposal((here / PROPOSAL,), "other") is None


# -- over a server, and in where ---------------------------------------------- #


def test_without_a_suite_the_server_shows_it_and_where_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(tmp_path, "CV: Python", "CV: Java")
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            "suggest",
            "--suite",
            "screening",
            "--tenant",
            "dev",
            "--repository",
            "private",
        )  # fmt: skip
        == 0
    )
    with viewing(tmp_path) as (base, _line):
        status, front, _ = get(base)
        assert status == 200
        assert proposal_address("dev", "screening") in front
        assert "not adopted yet: suite.proposed.toml." in front
        status, html, policy = get(
            f"{base.rstrip('/')}{proposal_address('dev', 'screening')}"
        )
    assert status == 200 and "default-src &#x27;none&#x27;" not in html
    assert policy.startswith("default-src 'none'")
    assert "a placeholder: yours to write" in html
    assert "digline suggest --suite screening --tenant dev --repository private" in html


def test_without_a_file_the_page_says_where_it_looked_and_the_commands(
    tmp_path: Path,
) -> None:
    record(tmp_path, "CV: Python")
    with viewing(tmp_path) as (base, _line):
        status, html, _ = get(
            f"{base.rstrip('/')}{proposal_address('dev', 'screening')}"
        )
    assert status == 200
    assert "No proposal for screening where digline suggest writes one." in html
    assert f"<code>{tmp_path / PROPOSAL}</code>" in html or PROPOSAL in html
    assert "--repository &#x27;&lt;private|public&gt;&#x27;" in html
    assert "does not overwrite" not in html


def test_where_names_the_proposal_in_its_sentence_and_its_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record(tmp_path, "CV: Python")
    monkeypatch.chdir(tmp_path)
    assert main("where", "--tenant", "dev", "--json") == 0
    before = json.loads(capsys.readouterr().out)
    assert before["state"] == "no_suite_yet" and before["proposal"] is None
    assert (
        main(
            "suggest",
            "--suite",
            "screening",
            "--tenant",
            "dev",
            "--repository",
            "private",
        )  # fmt: skip
        == 0
    )
    capsys.readouterr()
    assert main("where", "--tenant", "dev", "--json") == 0
    after = json.loads(capsys.readouterr().out)
    assert after["proposal"] == PROPOSAL
    assert "not adopted yet: suite.proposed.toml." in after["next"]["say"]
    assert main("where", "--tenant", "dev") == 0
    assert "not adopted yet: suite.proposed.toml." in capsys.readouterr().out
