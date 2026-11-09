"""`docs/walkthroughs/from-the-ide-over-mcp.md`, held to what was run.

The page is replayed here, in its order, against the stand-in it ran against
(`tests/_story_ide_stand_in.py`) and with the client it made its tool calls
with (`tests/_story_ide_mcp_client.py`), which starts the server the page's
`.mcp.json` declares:

- the application, the page's Python block, answers the four tickets and the
  fifth with the categories the page says;
- every JSON block the page shows as an answer is held to the answer the tool
  gives now: whole where the page shows it whole, and where it shows an
  excerpt, each key it shows, with the value it shows. A run's key and an
  instant are the two values that differ on every run, and are held to their
  type;
- the refusals and the sentences the page quotes from an answer are held to
  the answer;
- the commands of the `console` blocks are run and print what the page says,
  but for `digline view`, which serves a page: the import under its button
  stands in for its form, as the page says it does. A run's key, which
  differs on every run, is the one value read rather than compared.

Its `console` blocks open with the command that printed them
(`tests/test_console_blocks.py`, which reads this page too).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests._docs import Session, console_sessions
from tests._story_ide_mcp_client import Answer, call
from tests._story_ide_stand_in import ANSWERS, serve

from doc_fences import BLOCK_RE

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "walkthroughs" / "from-the-ide-over-mcp.md"
TEXT = PAGE.read_text(encoding="utf-8")
MARK = "> **Arrives with digline 1.1.**"

#: A run's key, which differs on every run.
KEY = re.compile(r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-\d+-\d\d-\d\d-[0-9a-f]+")

#: The keys whose values differ on every run, held to their type.
VOLATILE = frozenset({"key", "examined_through"})

#: The tickets of day one, in the page's order, and day two's.
DAY_ONE = list(ANSWERS)[:4]
DAY_TWO = list(ANSWERS)[4]


def test_the_story_carries_the_mark_under_its_title() -> None:
    """Until digline 1.1.0 and a `digline-mcp` with the thirteen tools are on
    PyPI, the story's commands need both from this repository, and the mark
    says so under the title. The cut takes it out (RELEASING.md, *Owed to the
    next version*)."""
    title, rest = TEXT.split("\n", 1)
    assert title.startswith("# ")
    assert rest.lstrip("\n").startswith(MARK)


def _flat(text: str) -> str:
    return " ".join(text.split())


def holds(
    page: object, actual: object, where: str = "$", *, whole: bool = False
) -> None:
    """Every key the page shows is in the answer with the value it shows; a
    list the page shows is the answer's, item for item. `whole` where the page
    shows the answer whole: then the answer has no key the page leaves out."""
    if isinstance(page, dict):
        assert isinstance(actual, dict), (where, actual)
        shown: dict[str, object] = dict(page)  # pyright: ignore[reportUnknownArgumentType]
        given: dict[str, object] = dict(actual)  # pyright: ignore[reportUnknownArgumentType]
        if whole:
            assert sorted(shown) == sorted(given), (where, sorted(shown), sorted(given))
        for key, value in shown.items():
            assert key in given, (where, key, sorted(given))
            if key in VOLATILE:
                assert isinstance(given[key], str), (where, key)
                continue
            holds(value, given[key], f"{where}.{key}", whole=whole)
    elif isinstance(page, list):
        assert isinstance(actual, list), (where, actual)
        left: list[object] = list(page)  # pyright: ignore[reportUnknownArgumentType]
        right: list[object] = list(actual)  # pyright: ignore[reportUnknownArgumentType]
        assert len(left) == len(right), (where, left, right)
        for index, (one, other) in enumerate(zip(left, right, strict=True)):
            holds(one, other, f"{where}[{index}]", whole=whole)
    else:
        assert page == actual, (where, page, actual)


class Story:
    """The page's project, its stand-in, and the page's blocks in order."""

    def __init__(self, project: Path, port: int) -> None:
        self.project = project
        self.port = port
        self.env = {
            **os.environ,
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
            "ANTHROPIC_API_KEY": "fake",
        }
        self.sessions: list[Session] = console_sessions(TEXT)
        blocks: list[tuple[str, str]] = BLOCK_RE.findall(TEXT)
        self.json: list[Any] = [
            json.loads(body) for lang, body in blocks if lang == "json"
        ]
        self.python = [body for lang, body in blocks if lang == "python"]
        #: Every answer and refusal the agent received, in order.
        self.received: list[Answer] = []

    def session(self, command: str) -> Session:
        """The next `console` session, which must be `command`'s."""
        found = self.sessions.pop(0)
        assert found.command.startswith(command), (found.command, command)
        return found

    def shown(self) -> Any:
        """The next JSON block the page shows."""
        return self.json.pop(0)

    def printed(self, text: str) -> list[str]:
        """Output as the page shows it: the project's path shortened."""
        for path in (str(self.project.resolve()), str(self.project)):
            text = text.replace(path, "…/helpdesk")
        return [line.rstrip() for line in text.splitlines() if line.strip()]

    def command(self, session: Session, *, key: str | None = None) -> list[str]:
        """Run a `digline` or `diff` command of the page, and hold what it
        prints to the page's lines. `key` is the run key the command names in
        place of the page's."""
        words = shlex.split(session.command)
        if key is not None:
            words = [key if KEY.fullmatch(word) else word for word in words]
        argv = (
            [sys.executable, "-m", "digline.cli", *words[1:]]
            if words[0] == "digline"
            else words
        )
        done = subprocess.run(  # noqa: S603 - the page's own commands
            argv,
            cwd=self.project,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        printed = self.printed(done.stdout + done.stderr)
        expected = [line for line in session.expected if line.strip()]
        assert [KEY.sub("KEY", line) for line in printed] == [
            KEY.sub("KEY", line) for line in expected
        ], (session.command, printed)
        return printed

    def tool(self, tool: str, arguments: dict[str, Any]) -> Answer:
        answer = call(self.project, tool, arguments)
        self.received.append(answer)
        return answer

    def answer(self, ticket: str) -> str:
        """The application, the page's Python block, asked one ticket."""
        done = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-c",
                f"from app import category; print(category({ticket!r}))",
            ],
            cwd=self.project,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.strip()

    def recorded(self) -> None:
        """The application written, recording on, and day one's tickets."""
        (app,) = self.python
        (self.project / "app.py").write_text(app, encoding="utf-8")
        self.command(self.session("digline record on"))
        for ticket in DAY_ONE:
            answered = self.answer(ticket)
            assert answered == ANSWERS[ticket]
            assert f'*{answered}* to *"{ticket}"*' in _flat(TEXT), ticket

    def served(self) -> None:
        """`.mcp.json` as the page declares it, pointed at this stand-in."""
        declared = self.shown()
        declared["mcpServers"]["digline"]["env"]["ANTHROPIC_BASE_URL"] = (
            f"http://127.0.0.1:{self.port}"
        )
        (self.project / ".mcp.json").write_text(json.dumps(declared), encoding="utf-8")


@pytest.fixture
def story(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Story]:
    # The server `.mcp.json` names is this environment's `digline-mcp`.
    monkeypatch.setenv(
        "PATH", f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
    )
    server = serve()
    project = tmp_path / "helpdesk"
    project.mkdir()
    try:
        yield Story(project, server.server_port)
    finally:
        server.shutdown()


def test_the_story_runs_as_the_page_says(story: Story) -> None:
    text = _flat(TEXT)
    story.recorded()
    story.served()

    # where, for a suite that does not exist, and with the tenant alone.
    refused, said = story.tool("where", story.shown())
    assert refused
    assert "names no file inside" in said
    assert _flat(said.split(")", 1)[1]) in text
    refused, said = story.tool("where", {"tenant": "acme"})
    assert not refused
    holds(story.shown(), said, whole=True)
    story.command(story.session("digline where"))

    # suggest, which writes nothing; the command, run by hand, which does.
    before = sorted(p.name for p in story.project.iterdir())
    refused, said = story.tool(
        "suggest", {"name": "category", "tenant": "acme", "repository": "private"}
    )
    assert not refused
    holds(story.shown(), said)
    assert sorted(p.name for p in story.project.iterdir()) == before
    story.command(story.session("digline suggest"))

    # Adopting it: the lines the page's diff changes, changed, and `diff`
    # prints the page's diff.
    adopt = story.session("diff suite.proposed.toml suite.toml")
    proposed = (story.project / "suite.proposed.toml").read_text(encoding="utf-8")
    olds = [line[2:] for line in adopt.expected if line.startswith("< ")]
    news = [line[2:] for line in adopt.expected if line.startswith("> ")]
    for old, new in zip(olds, news, strict=True):
        assert proposed.count(old) == 1, old
        proposed = proposed.replace(old, new)
    (story.project / "suite.toml").write_text(proposed, encoding="utf-8")
    story.command(adopt)

    # What there is to review; then the yes and the no, written by the import
    # under the button of the page `digline view` serves.
    refused, said = story.tool("record_listing", {"suite": "suite.toml"})
    assert not refused
    holds(story.shown(), said, whole=True)
    story.session("digline view --suite suite.toml --allow-record")
    story.command(story.session("digline record import"))

    # The run: refused until the count is said back, then the verdicts.
    refused, said = story.tool("run", {"suite": "suite.toml"})
    assert refused
    assert _flat(said.split("Error executing tool run: ", 1)[1]) in text
    refused, ran = story.tool("run", {"suite": "suite.toml", "acknowledge_calls": 0})
    assert not refused
    assert (ran["usage"]["judge"]["calls"], ran["usage"]["target"]["calls"]) == (36, 0)
    refused, read = story.tool("get_run", {"suite": "suite.toml"})
    assert not refused
    page_result = story.shown()
    (result,) = [r for r in read["results"] if r["case_id"] == page_result["case_id"]]
    holds(page_result, result)
    assert sorted(
        (r["reviewed"]["good"], v["status"], v["score"])
        for r in read["results"]
        for v in r["verdicts"]
    ) == [
        (False, "fail", 0.0),
        (True, "pass", 1.0),
        (True, "pass", 1.0),
        (True, "pass", 1.0),
    ]

    # The reference, by hand; a second run, and compare.
    promoted = story.command(story.session("digline promote"))
    baseline = KEY.search(promoted[0])
    assert baseline is not None
    assert not story.tool("run", {"suite": "suite.toml", "acknowledge_calls": 0})[0]
    refused, compared = story.tool("compare", {"suite": "suite.toml"})
    assert not refused
    assert f'*"{compared["sentence"]}"*' in text
    assert compared["exit_code"] == 0

    # Day two.
    assert story.answer(DAY_TWO) == ANSWERS[DAY_TWO]
    assert f'*"{DAY_TWO}"*, with *{ANSWERS[DAY_TWO]}*' in text
    refused, where = story.tool("where", {"tenant": "acme", "suite": "suite.toml"})
    assert not refused
    assert (where["state"], where["count"]) == ("to_import", 1)
    assert f'`"{where["next"]["command"]}"`' in text
    story.command(story.session("digline record import"))
    refused, said = story.tool("run", {"suite": "suite.toml"})
    assert refused
    assert "5 reviewed answers judged 45 times" in said
    refused, ran = story.tool("run", {"suite": "suite.toml", "acknowledge_calls": 0})
    assert not refused
    holds(story.shown(), ran)
    refused, compared = story.tool("compare", {"suite": "suite.toml"})
    assert not refused
    holds(story.shown(), compared)
    refused, explained = story.tool("explain", {"suite": "suite.toml"})
    assert not refused
    page_explain = story.shown()
    holds(page_explain["exit_code"], explained["exit_code"])
    holds(
        page_explain["facts"],
        [fact for fact in explained["facts"] if fact.get("kind") == "reviewed"],
    )
    story.command(story.session("digline explain"))
    story.command(story.session("digline promote"), key=baseline.group(0))

    # Nothing of the page was left out of the replay.
    assert story.sessions == []
    assert story.json == []

    # The page's last section: eleven answers and three refusals, and none of
    # them holds a word of a ticket or of a category.
    refusals = [said for refused, said in story.received if refused]
    answers = [said for refused, said in story.received if not refused]
    assert (len(answers), len(refusals)) == (11, 3)
    assert "the eleven answers and three refusals the agent received" in text
    words = ("refund", "delivery", "password", "shoes", "parcel", "gift", "receipt")
    for said in [*answers, *refusals]:
        dumped = json.dumps(said).lower()
        assert not [word for word in words if word in dumped], said


def test_no_answer_holds_a_ticket_and_the_recordings_do(story: Story) -> None:
    """The page's last section: the words of the tickets and of their
    categories are in no answer the agent receives, and are in what was
    recorded. Asked of `where` and `suggest`, the two answers about the
    recordings themselves."""
    story.recorded()
    story.served()
    words = ("refund", "delivery", "password", "shoes", "parcel")
    for tool, arguments in (
        ("where", {"tenant": "acme"}),
        ("suggest", {"name": "category", "tenant": "acme", "repository": "private"}),
    ):
        refused, said = story.tool(tool, arguments)
        assert not refused
        dumped = json.dumps(said).lower()
        assert not [word for word in words if word in dumped], (tool, said)
    # The control: the recordings hold them.
    recorded = " ".join(
        p.read_text(encoding="utf-8").lower()
        for p in (story.project / ".digline").rglob("*.json")
    )
    assert all(word in recorded for word in words)
