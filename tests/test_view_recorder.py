"""The recorder's three views of `digline view`: the recordings as the import
lists them, a suite's answers across setups, and a tenant's recorder.
(ADR 0061 §1, §3, §4, §6)

The store is written with the real writers, `RecordingWriter` and `switch_on`,
so what the pages read is what the recorder files. The suite lives in a
directory of its own and names its capture file relative to itself, which is
what makes the module the server is handed matter.

What is held here:

- each view renders the structure its command's host function returns, and
  the import's sentences are `listing_lines`' own, word for word;
- an answer is shown up to `SHOWN_CHARS` with a link to the whole of it, and
  the whole is one page away; nothing is ranked, scored, pre-selected or
  offered for many answers at once (ADR 0037 §6);
- across setups, a pair is chosen with a GET and shows the keys the two differ
  on, each value by its first line, never whole; the chart is a data block
  and two scripts from the server, for one case only;
- the recorder opens with its four figures, and *to import* is a number only
  for the suite whose draft was read;
- served: every response carries the policy and nothing inline, a GET writes
  nothing, a POST to any of the three is the 404 any unknown path gets, the
  host's refusals reach the page as the command prints them, and the menu of
  every screen links the three.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import shlex
import shutil
import subprocess
import sys
import threading
import urllib.parse
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from email.message import Message
from functools import partial
from html import unescape
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import pytest
from tests.test_view_policy import WANTED, inline_in

from digline.cli import EXIT_OK, recorder_pages
from digline.cli.main import build_parser, main
from digline.cli.recorder_pages import (
    SHOWN_CHARS,
    Field,
    command_line,
    import_fields,
    switch_fields,
)
from digline.cli.view import HOST, Launch, ViewHandler, self_netlocs
from digline.core.recording import Recording, setup_digest_of
from digline.core.run import RecordedResponse, RecordedStep
from digline.host import (
    import_listing,
    imported_since,
    load_suite,
    record_compare,
    recorder_status,
    switch_on,
)
from digline.host.importing import answer_id, closing_lines, group_line, setup_line
from digline.report import Locale
from digline.report.pages import (
    answer_address,
    recorder_address,
    recordings_address,
    setups_address,
    where_address,
)
from digline.run import Suite
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.wire.record_compare import (
    ComparedAnswer,
    ComparedCase,
    ComparedSetup,
    RecordComparison,
    SetupKey,
    SetupValue,
)

#: The flags every command under a button carries, on a server started from
#: the store's directory with `--suite suites/suite.py`.
WRITES = ["--tenant", "acme", "--suite", "suites/suite.py"]

#: And every `digline record on|off` under a button of the recorder's page.
SWITCH = ["--tenant", "acme"]

LONG_PROMPT = "Be brief and kind.\n" + "Never promise a refund. " * 20
SETUP_1: dict[str, object] = {"model": "m", "system": "Be brief.", "temperature": 0}
SETUP_2: dict[str, object] = {"model": "m", "system": LONG_PROMPT, "temperature": 0}
S1, S2 = setup_digest_of(SETUP_1), setup_digest_of(SETUP_2)


def case(text: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": text}]}


REFUND, HOURS, PARCEL = case("refund?"), case("hours?"), case("lost parcel")

#: An answer longer than the listing shows, and one that holds markup a page
#: must show as text.
LONG_ANSWER = "Refunds are issued in fourteen days. " * 12
MARKUP = 'open <p style="x">nine</p> to five'

SUITE = """\
from pathlib import Path
from digline.core import JudgeReply, LlmRubric
from digline.host import read_cases
from digline.run import Case, CaptureSource, Suite
HERE = Path(__file__).parent


def judge(prompt):
    return JudgeReply(score=1.0, reason="r")


suite = Suite(
    tenant='acme', environment='dev', name='triage',
    assertions=[LlmRubric(rubric='right?', judge=judge, threshold=0.7, tolerance=0.05)],
    cases=[Case(id='by-hand'), *read_cases(HERE / 'captured.json')],
    samples=2,
    min_agreement='2/2',
    capture=CaptureSource(
        cases_file='captured.json', repository='private', check='llm_rubric'
    ),
)
"""


def recording(
    vars: dict[str, object],  # noqa: A002 — `Recording.case`'s name
    setup: dict[str, object],
    output: str,
    minute: str,
    **changes: Any,
) -> Recording:
    # An episode's steps are its response's (ADR 0060 §6).
    steps = changes.pop("steps", None)
    fields: dict[str, Any] = {
        "source_tenant": "acme",
        "app": "support",
        "suite": "triage",
        "case": vars,
        "setup": setup,
        "setup_digest": setup_digest_of(setup),
        "response": RecordedResponse(
            output=output, kind="text", input="q", steps=steps
        ),
        "recorded_at": f"2026-11-03T08:{minute}:00+00:00",
    }
    fields.update(changes)
    return Recording(**fields)


def recorded(root: Path) -> None:
    """Two setups, an answer that repeats, one that changes, a long one, one
    with markup, an episode, and an orphan, which is counted and never a case.
    """
    writer = RecordingWriter(FileResultStore(root))
    for item in (
        recording(REFUND, SETUP_1, "refunds in 14 days", "01"),
        recording(REFUND, SETUP_1, "refunds in 14 days", "02"),
        recording(REFUND, SETUP_1, "refunds in 30 days", "03"),
        recording(HOURS, SETUP_1, MARKUP, "04"),
        recording(REFUND, SETUP_2, LONG_ANSWER, "10"),
        recording(HOURS, SETUP_2, "nine to five", "11"),
        recording(
            PARCEL,
            SETUP_2,
            "we have found it",
            "12",
            steps=(RecordedStep(index=0, actor="model"),),
            id="e" * 32,
        ),
        recording(case("orphan?"), SETUP_2, "alone", "13", orphan=True),
    ):
        writer.write(item)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    recorded(tmp_path)
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "suite.py").write_text(SUITE, encoding="utf-8")
    switch_on(tmp_path, "acme", production=False, sample=0.5)
    return tmp_path


@dataclass(frozen=True)
class Loaded:
    suite: Suite
    module: Any


def loaded(root: Path) -> Loaded:
    suite, found = load_suite(str(root / "suites" / "suite.py"), root=root)
    return Loaded(suite, found.module)


class Text(HTMLParser):
    """What a reader sees of a page: its text, not its markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def text_of(page: str) -> str:
    parser = Text()
    parser.feed(page)
    parser.close()
    return " ".join(parser.parts)


# -- the recordings, as the import lists them --------------------------------- #


def listing(root: Path) -> Any:
    found = loaded(root)
    return import_listing(root, found.suite, found.module, "acme")


def test_the_recordings_page_says_the_listing_s_own_sentences(root: Path) -> None:
    """The declaration, the setup in force, each group's heading and the
    closing lines are the host's, the ones `digline record import` prints."""
    found = listing(root)
    page = recorder_pages.recordings_page(found, locale="en", writes=None)
    said = unescape(page)
    sentences = [
        found.declaration.line(),
        setup_line(found),
        *(group_line(n, g) for n, g in enumerate(found.groups, start=1)),
        *closing_lines(found),
    ]
    assert len(found.groups) == 2
    for sentence in sentences:
        assert sentence in said, sentence
    # The capture file is the suite's, beside its own file: the module said so.
    assert "writes to suites/captured.json ·" in said


def test_a_case_from_the_first_call_says_so_beside_the_id(root: Path) -> None:
    """An episode the proxy read with no case given takes its first call's
    case, and the row says so beside the id, as the command says it after the
    input (ADR 0062 §3). One answer of the listing is marked; the others are
    the control, and say nothing."""
    found = listing(root)
    group = found.groups[0]
    marked = replace(group.answers[0], case_from_first_call=True)
    found = replace(
        found,
        groups=(
            replace(group, answers=(marked, *group.answers[1:])),
            *found.groups[1:],
        ),
    )
    said_in: tuple[tuple[Locale, str], ...] = (
        ("en", "case from the first call"),
        ("it", "caso dalla prima chiamata"),
    )
    for locale, said in said_in:
        page = recorder_pages.recordings_page(found, locale=locale, writes=None)
        cell = page[page.index(f'<code class="key">{marked.id}</code>') :]
        cell = cell[: cell.index("</td>")]
        assert f'<div class="note">{said}</div>' in cell, cell
        assert page.count(said) == 1, locale


def _rule(selector: str) -> str:
    """The declarations of one rule of the sheet, by its exact selector."""
    from digline.report import SHEET

    start = SHEET.index(selector + " {")
    return SHEET[start : SHEET.index("}", start)]


def test_the_answers_table_fits_the_page_and_its_last_column_inside_it(
    root: Path,
) -> None:
    """Seen in a browser on the Java pass: the table of answers was wider than
    the page, because a wide page's cells never wrap, and the column that
    names an answer sat outside the box. The table is now in a box that
    scrolls rather than run off the page, and its cells wrap, the date
    excepted. What a browser lays out is measured in the scratch screenshots
    of the pull request; this holds the rules that do it."""
    page = recorder_pages.recordings_page(listing(root), locale="en", writes=WRITES)
    assert '<div class="fits"><table class="answers">' in page
    assert page.count('<table class="answers">') == page.count("<table")
    assert "overflow-x: auto" in _rule(".fits")
    assert "white-space: normal" in _rule("body.wide table.answers td")
    assert "white-space: nowrap" in _rule("body.wide table.answers td.when")
    assert "overflow-wrap: anywhere" in _rule("table.answers code.key")


def test_the_command_under_a_button_wraps_and_is_read_whole() -> None:
    """The line grows with each answer named, and was cut at the box's edge
    with no wrap; it wraps now, and a copy is still one line."""
    rule = _rule("pre.snippet.command")
    assert "white-space: pre-wrap" in rule
    assert "overflow-wrap: anywhere" in rule


def test_each_answer_is_a_row_with_its_id_date_setup_and_count(root: Path) -> None:
    found = listing(root)
    page = recorder_pages.recordings_page(found, locale="en", writes=None)
    repeated = answer_id(REFUND, "refunds in 14 days")
    assert f'<code class="key">{repeated}</code>' in page
    row = page[page.index(repeated) :]
    row = row[: row.index("</tr>")]
    assert "2026-11-03T08:01:00+00:00" in row
    assert f">{S1[:8]}</code>" in row
    assert ">×2</td>" in row
    # The orphan is counted, never a row.
    assert answer_id(case("orphan?"), "alone") not in page


def test_a_long_answer_is_cut_with_a_link_to_the_whole_of_it(root: Path) -> None:
    found = listing(root)
    page = recorder_pages.recordings_page(found, locale="en", writes=None)
    long_id = answer_id(REFUND, LONG_ANSWER)
    whole = answer_address("acme", "triage", long_id)
    assert unescape(LONG_ANSWER[:SHOWN_CHARS]) + "…" in unescape(page)
    assert LONG_ANSWER not in unescape(page)
    assert f'{whole}?locale=en">show all</a>' in page
    # A short answer is whole, and has no such link.
    short_id = answer_id(REFUND, "refunds in 30 days")
    row = page[page.index(f'<code class="key">{short_id}') :]
    assert "show all" not in row[: row.index("</tr>")]
    # The whole answer, one page away.
    [answer] = [a for a in found.answers if a.id == long_id]
    alone = recorder_pages.answer_page(found, answer, locale="en")
    assert LONG_ANSWER in unescape(alone)


def test_markup_in_an_answer_is_text(root: Path) -> None:
    page = recorder_pages.recordings_page(listing(root), locale="en", writes=None)
    assert inline_in(page) == []
    assert MARKUP in text_of(page)


#: Words that rank, propose or judge, as `tests/test_recorder_import.py` holds
#: them for the command's listing.
RANKING = ("better", "worse", "regress", "improve", "likely", "suggest", "recommend")


def test_nothing_is_ranked_pre_selected_or_offered_for_many(root: Path) -> None:
    """ADR 0037 §6 at the page: no word that ranks, no control chosen in
    advance, and nothing that acts on more than one answer."""
    found = listing(root)
    for locale in ("en", "it"):
        page = recorder_pages.recordings_page(found, locale=locale, writes=WRITES)
        seen = text_of(page).lower()
        for word in RANKING:
            assert word not in seen, (locale, word)
        assert "import all" not in seen and "--all" not in seen
        assert " checked" not in page and " selected" not in page
    assert "better" in "the better answer"  # the search finds a word that is there


def test_the_note_on_writes_is_there_without_the_flag(root: Path) -> None:
    found = listing(root)
    note = "served only by digline view --allow-record"
    assert note in recorder_pages.recordings_page(found, locale="en", writes=None)
    assert note not in recorder_pages.recordings_page(found, locale="en", writes=WRITES)


# -- across setups ------------------------------------------------------------- #


def compared(root: Path, **options: Any) -> Any:
    found = loaded(root)
    return record_compare(root, found.suite, "acme", **options)


#: The words of `tests/test_record_compare.py`: the view shows and judges
#: nothing.
JUDGING = ("better", "worse", "regress", "improve", "changed", "good", "bad")


def test_the_setups_page_is_the_comparison_by_case_and_setup(root: Path) -> None:
    found = compared(root)
    page = recorder_pages.setups_page(found, locale="en")
    for case_ in found.cases:
        assert f"Case {case_.id} · {case_.kind}" in unescape(page)
        for setup in case_.setups:
            for answer in setup.answers:
                assert f"<code>{answer.digest}</code>" in page
    # In the order they were recorded: 08:01 before 08:03 under S1.
    assert page.index("08:01:00") < page.index("08:03:00")
    # Equal answers one after the other: one row, counted, with when it ended.
    assert "×2" in page and "through 2026-11-03T08:02:00+00:00" in page
    seen = text_of(page).lower()
    for word in JUDGING:
        assert word not in seen, word
    assert "better" in "the better answer"


def test_two_setups_side_by_side_show_their_keys_never_a_prompt_whole(
    root: Path,
) -> None:
    found = compared(root, setups=[S1[:8], S2[:8]], show_setup=True)
    page = unescape(recorder_pages.setups_page(found, locale="en"))
    assert f"A {S1[:8]}, B {S2[:8]}" in page
    assert "Keys the two setups differ on (2 the same)" in page
    first = LONG_PROMPT.split("\n", 1)[0][:60]
    assert json.dumps(first) in page
    assert f"{len(LONG_PROMPT)} characters" in page
    assert LONG_PROMPT not in page and "Never promise a refund." not in page


def test_a_list_of_messages_is_its_first_text_and_a_count_never_json(
    root: Path,
) -> None:
    """A `system` the way Chat Completions carries it: each side its first
    message's text, quoted and not escaped, and how many messages there are."""
    found = compared(root, setups=[S1[:8], S2[:8]], show_setup=True)
    keys = (
        SetupKey(
            key="system",
            a=SetupValue(preview="Be brief.", chars=9, clipped=False, messages=1),
            b=SetupValue(
                preview='Say "no" kindly.', chars=80, clipped=True, messages=2
            ),
        ),
    )
    page = unescape(
        recorder_pages.setups_page(replace(found, setup_keys=keys), locale="en")
    )
    assert '"Be brief."' in page and "1 message" in page
    assert '"Say "no" kindly."…' in page and "2 messages" in page
    assert '\\"' not in page


def test_the_pair_is_chosen_with_a_get_and_nothing_chosen_before(
    root: Path,
) -> None:
    page = recorder_pages.setups_page(compared(root), locale="en")
    form = page[page.index('<form method="get"') :]
    form = form[: form.index("</form>")]
    assert form.count('<select name="setup">') == 2
    assert " selected" not in form
    assert 'method="post"' not in page


def test_the_chart_is_one_case_a_data_block_and_two_scripts(root: Path) -> None:
    every = recorder_pages.setups_page(compared(root), locale="en")
    assert 'id="series-data"' not in every and "<script" not in every

    refund = next(c.id for c in compared(root).cases if c.vars == REFUND)
    page = recorder_pages.setups_page(compared(root, case=refund), locale="en")
    assert inline_in(page) == []
    assert '<script src="/static/uPlot.iife.min.js"></script>' in page
    assert '<script src="/static/chart.js"></script>' in page
    block = page[page.index('id="series-data">') + len('id="series-data">') :]
    data = json.loads(block[: block.index("</script>")])
    assert data["setups"] == [S1[:8], S2[:8]]
    # The length of each answer, at its first instant and, for a run of equal
    # ones, its last: 14 days at 08:01 and 08:02, 30 days at 08:03, the long
    # answer at 08:10.
    lengths = [len("refunds in 14 days")] * 2 + [len("refunds in 30 days"), None]
    assert data["y"][0] == lengths
    assert data["y"][1] == [None, None, None, len(LONG_ANSWER)]
    assert len(data["x"]) == 4 and data["x"] == sorted(data["x"])


# -- the recorder ---------------------------------------------------------------- #


def status_of(root: Path, *, read: bool) -> Any:
    found = loaded(root)
    imports = (
        {"triage": imported_since(root, found.suite, found.module, "acme")}
        if read
        else {}
    )
    [status] = recorder_status(root, "acme", imports)
    return status


def figures(page: str) -> list[str]:
    block = page[page.index('<div class="figures">') :]
    block = block[: block.index("</div>\n")]
    return [
        unescape(part.split("</span>", 1)[0])
        for part in block.split('<span class="value">')[1:]
    ]


def test_the_recorder_opens_with_its_four_figures(root: Path) -> None:
    status = status_of(root, read=True)
    page = recorder_pages.recorder_page(
        status, suite="triage", locale="en", writes=None
    )
    held = sum(s.calls + s.episodes for s in status.suites)
    [triage] = [s for s in status.suites if s.suite == "triage"]
    assert triage.since_last_import is not None
    assert figures(page) == [
        str(status.size),
        str(status.ceiling),
        str(held),
        str(triage.since_last_import),
    ]
    assert status.size > 0 and held == 8
    assert 'sample 0.5</code> <span class="note">declared' in page
    assert "interval" in page and "default" in page
    assert status.recordings_path in page and status.switch_path in page


def test_to_import_says_not_read_where_no_draft_was_read(root: Path) -> None:
    page = recorder_pages.recorder_page(
        status_of(root, read=False), suite="triage", locale="en", writes=None
    )
    assert figures(page)[3] == "not read"
    assert "0" not in figures(page)[3]


# -- served -------------------------------------------------------------------- #


@dataclass(frozen=True)
class Answer:
    status: int
    headers: Message
    body: str


@dataclass(frozen=True)
class Served:
    port: int
    root: Path
    #: The cookie of the browser that opened the address, on a server that
    #: writes; empty on one that does not.
    cookie: str = ""

    @property
    def writing(self) -> bool:
        return bool(self.cookie)

    def ask(
        self,
        method: str,
        target: str,
        body: str = "",
        *,
        cookie: bool = True,
        origin: str = "",
    ) -> Answer:
        connection = http.client.HTTPConnection(HOST, self.port, timeout=10)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        if origin:
            headers["Origin"] = origin
        connection.request(method, target, body=body or None, headers=headers)
        answer = connection.getresponse()
        text = answer.read().decode("utf-8")
        connection.close()
        return Answer(answer.status, answer.msg, text)


@contextmanager
def serving(
    root: Path, *, allow_record: bool, allow_promote: bool = False
) -> Generator[tuple[Served, Launch | None]]:
    """The server in this process, on loopback, in a thread, as `serve()`
    builds it: the suite, the module it was loaded from, `--suite` as typed,
    and a launch key where a flag asks for one. Its address not yet opened."""
    found = loaded(root)
    known: set[str] = set()
    launch = Launch.minted() if allow_record or allow_promote else None
    handler = partial(
        ViewHandler,
        suite=found.suite,
        store=FileResultStore(root),
        known=known,
        launch=launch,
        promote=allow_promote,
        allow_record=allow_record,
        root=str(root),
        module=found.module,
        suite_arg="suites/suite.py",
    )
    httpd = ThreadingHTTPServer((HOST, 0), handler)  # pyright: ignore[reportArgumentType]
    port = int(httpd.server_address[1])
    known.update(self_netlocs(HOST, port))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Served(port, root), launch
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def opened(served: Served, launch: Launch) -> Served:
    """The address opened in a browser: the key spent, the cookie kept."""
    handed = served.ask("GET", f"/?launch={launch.key}")
    assert handed.status == 303, handed.body
    cookie = handed.headers.get("Set-Cookie", "").split(";")[0]
    assert cookie, "the hand-over set no cookie"
    return Served(served.port, served.root, cookie)


@pytest.fixture(params=[False, True], ids=["read-only", "allow-record"])
def served(root: Path, request: pytest.FixtureRequest) -> Iterator[Served]:
    """The read-only server, and the one started with `--allow-record` whose
    address a browser has opened."""
    with serving(root, allow_record=request.param) as (server, launch):
        yield server if launch is None else opened(server, launch)


@pytest.fixture
def writing(root: Path) -> Iterator[Served]:
    """`digline view --allow-record`, its address opened."""
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        yield opened(server, launch)


def views(served: Served) -> list[str]:
    long_id = answer_id(REFUND, LONG_ANSWER)
    return [
        recordings_address("acme", "triage"),
        answer_address("acme", "triage", long_id),
        setups_address("acme", "triage"),
        setups_address("acme", "triage") + f"?setup={S1[:8]}&setup={S2[:8]}",
        recorder_address("acme"),
        recorder_address("acme") + "?locale=it",
        where_address("acme", "triage"),
        where_address("acme", "triage") + "?locale=it",
    ]


def tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_every_view_answers_with_the_policy_and_nothing_inline(
    served: Served,
) -> None:
    for target in views(served):
        answer = served.ask("GET", target)
        assert answer.status == 200, (target, answer.body)
        assert answer.headers.get("Content-Security-Policy") == WANTED, target
        assert inline_in(answer.body) == [], target


def test_a_get_writes_nothing(served: Served) -> None:
    before = tree(served.root)
    for target in views(served):
        assert served.ask("GET", target).status == 200, target
    assert tree(served.root) == before


def test_a_post_where_there_is_no_write_is_the_404_of_an_unknown_path(
    served: Served,
) -> None:
    """Without `--allow-record` no view takes a POST; with it, the two that
    write do, and the answer page and the setups still do not. Each is
    answered as any path the server does not have (ADR 0032 §2)."""
    writes = (recordings_address("acme", "triage"), recorder_address("acme"))
    before = tree(served.root)
    for target in views(served):
        if served.writing and target.split("?")[0] in writes:
            continue
        answer = served.ask("POST", target, "good=x&by=Ada")
        assert answer.status == 404, target
        assert "no such action" in answer.body, target
    assert tree(served.root) == before


def test_every_screen_links_the_three_views(served: Served) -> None:
    for target in ("/", "/suspend/x?reason=r", *views(served)):
        page = served.ask("GET", target).body
        for href in (
            where_address("acme", "triage"),
            recordings_address("acme", "triage"),
            setups_address("acme", "triage"),
            recorder_address("acme"),
        ):
            assert f'href="{href}?locale=' in page, (target, href)
    italian = served.ask("GET", "/?locale=it").body
    assert ">Registrazioni</a>" in italian and ">Registratore</a>" in italian


def test_the_host_s_refusals_reach_the_page_as_the_command_prints_them(
    served: Served,
) -> None:
    other = served.ask("GET", recordings_address("globex", "triage"))
    assert other.status == 400
    assert "the recordings of tenant 'globex' are not imported into suite" in (
        unescape(other.body)
    )
    one = served.ask("GET", setups_address("acme", "triage") + f"?setup={S1[:8]}")
    assert one.status == 400
    assert "--setup names two setups, and was given 1" in unescape(one.body)
    climbing = served.ask("GET", "/recorder/..%2Fglobex/")
    assert climbing.status == 400
    assert "invalid tenant name" in unescape(climbing.body)


def test_another_suite_or_a_longer_path_is_no_page(served: Served) -> None:
    for target in (
        recordings_address("acme", "other"),
        setups_address("acme", "other"),
        "/recordings/acme/triage",
        "/recordings/acme/triage/x/y",
        "/setups/acme/triage/x",
        "/recorder/acme/x",
        "/recorder/acme",
    ):
        assert served.ask("GET", target).status == 404, target
    missing = served.ask("GET", answer_address("acme", "triage", "nope"))
    assert missing.status == 404
    assert "nope is not an answer the recordings of suite triage hold" in missing.body


def test_the_command_hands_the_server_the_suite_s_module(root: Path) -> None:
    """`digline view` started as a person starts it: the capture file named
    relative to the suite's own file is found beside it, which only the module
    the suite was loaded from can say."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "digline.cli",
            "view",
            "--suite",
            "suites/suite.py",
            "--port",
            "0",
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        line = process.stdout.readline()
        assert "http://" in line, line
        port = int(line.split()[3].rstrip("/").rsplit(":", 1)[1])
        answer = Served(port, root).ask("GET", recordings_address("acme", "triage"))
        assert answer.status == 200, answer.body
        assert "writes to suites/captured.json ·" in unescape(answer.body)
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_two_setups_in_the_query_are_setup_and_show_setup(served: Served) -> None:
    """The pair the form sends is what `--setup A B --show-setup` names: the
    two side by side, and the keys they differ on."""
    target = setups_address("acme", "triage") + f"?setup={S1[:8]}&setup={S2[:8]}"
    page = unescape(served.ask("GET", target).body)
    assert f"A {S1[:8]}, B {S2[:8]}" in page
    assert "Keys the two setups differ on (2 the same)" in page


def test_the_served_recorder_reads_the_suite_s_import(served: Served) -> None:
    """The server's own suite, in its own tenant, is read; another tenant's
    page has no draft to read and says so."""
    read = figures(served.ask("GET", recorder_address("acme")).body)
    assert read[3] == "8"  # never imported: every recording of the suite
    other = figures(served.ask("GET", recorder_address("globex")).body)
    assert other[3] == "not read"


def test_the_data_block_cannot_be_closed_by_what_it_carries() -> None:
    """A setup's digest is read from a recording file, and the block carries
    its first eight characters: a `<` is written `\\u003c`, so nothing the
    files hold can end the block and start markup."""
    hostile = "</script><p>x"
    found = ComparedCase(
        id="c",
        vars={},
        kind="call",
        setups=(
            ComparedSetup(
                setup=hostile,
                answers=(
                    ComparedAnswer(
                        digest="d",
                        text="t",
                        first_at="2026-11-03T08:01:00+00:00",
                        last_at="2026-11-03T08:01:00+00:00",
                        times=1,
                    ),
                ),
            ),
        ),
    )
    comparison = compared_with(found)
    page = recorder_pages.setups_page(comparison, locale="en")
    block = page[page.index('id="series-data">') :]
    block = block[: block.index("</script>")]
    assert "<" not in block.removeprefix('id="series-data">')
    assert json.loads(block.removeprefix('id="series-data">'))["setups"] == [
        hostile[:8]
    ]


def compared_with(case_: ComparedCase) -> RecordComparison:
    return RecordComparison(
        tenant="acme",
        suite="triage",
        case=case_.id,
        since=None,
        setups=tuple(setup.setup for setup in case_.setups),
        pair=None,
        setup_keys=None,
        same_keys=None,
        cases=(case_,),
        recordings=1,
        orphans=0,
        detached=0,
        interrupted=0,
        oversize=0,
        unreadable=0,
        undated=0,
    )


# -- the two writes (ADR 0061 §2, §4, §6) ----------------------------------------- #


class Forms(HTMLParser):
    """The forms that write on a page: each field with its attributes, and the
    line under the button with the base the page's script starts from."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: list[dict[str, str | None]] = []
        self.bases: list[str] = []
        self.lines: list[str] = []
        self._in_line = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        named = dict(attrs)
        if tag in ("input", "select", "textarea"):
            self.fields.append({"tag": tag, **named})
        if tag == "pre" and "data-base" in named:
            self.bases.append(named["data-base"] or "")
            self.lines.append("")
            self._in_line = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self._in_line = False

    def handle_data(self, data: str) -> None:
        if self._in_line:
            self.lines[-1] += data


def forms_of(page: str) -> Forms:
    parser = Forms()
    parser.feed(page)
    parser.close()
    return parser


def switch_page(root: Path, writes: list[str] | None) -> str:
    return recorder_pages.recorder_page(
        status_of(root, read=True), suite="triage", locale="en", writes=writes
    )


def test_without_the_flag_there_is_no_form(root: Path) -> None:
    for page in (
        recorder_pages.recordings_page(listing(root), locale="en", writes=None),
        switch_page(root, None),
    ):
        assert 'method="post"' not in page
        assert forms_of(page).lines == []


def test_the_import_form_is_served_with_nothing_chosen(root: Path) -> None:
    """Every answer that can be named has a yes and a no, neither chosen, and
    the line under the button is the command for the form as served: the
    listing, which names nothing."""
    found = listing(root)
    page = recorder_pages.recordings_page(found, locale="en", writes=WRITES)
    forms = forms_of(page)
    radios = [f for f in forms.fields if f.get("type") == "radio"]
    electable = [a for a in found.answers if a.electable]
    assert len(electable) == 3 and len(radios) == 2 * len(electable)
    assert all("checked" not in radio for radio in radios)
    assert forms.lines == [
        "digline record import --tenant acme --suite suites/suite.py"
    ]
    assert forms.bases == forms.lines
    # An answer that cannot be named has no choice beside it.
    held = {f["data-value"] for f in radios}
    assert held == {a.id for a in electable}


def test_the_switch_form_is_served_with_the_file_s_values(root: Path) -> None:
    """`sample` is declared in the file, so it is in its field and in the line;
    the rest are defaults, empty, as flags not given."""
    forms = forms_of(switch_page(root, SWITCH))
    assert forms.lines == [
        "digline record on --tenant acme --sample 0.5",
        "digline record off --tenant acme",
    ]
    sample = next(f for f in forms.fields if f.get("name") == "sample")
    assert sample["value"] == "0.5" and sample["data-flag"] == "--sample"
    production = next(f for f in forms.fields if f.get("name") == "production")
    assert "checked" not in production


def test_every_line_served_is_parsed_by_digline_s_own_parser(root: Path) -> None:
    """A renamed flag turns the page red here, not in a person's terminal
    (ADR 0061 §6)."""
    lines = [
        *forms_of(
            recorder_pages.recordings_page(listing(root), locale="en", writes=WRITES)
        ).lines,
        *forms_of(switch_page(root, SWITCH)).lines,
    ]
    parsed = [build_parser().parse_args(shlex.split(line)[1:]) for line in lines]
    assert [(p.command, p.action, p.tenant) for p in parsed] == [
        ("record", "import", "acme"),
        ("record", "on", "acme"),
        ("record", "off", "acme"),
    ]
    assert parsed[0].suite == "suites/suite.py" and parsed[1].sample == 0.5


def test_every_field_the_script_reads_names_a_flag_the_command_takes(
    root: Path,
) -> None:
    """The page's script joins what each field names and holds no flag of its
    own, so every field a person fills carries one, and each is an option of
    `digline record` (ADR 0061 §7)."""
    pages = (
        recorder_pages.recordings_page(listing(root), locale="en", writes=WRITES),
        switch_page(root, SWITCH),
    )
    flags: set[str] = set()
    for page in pages:
        for field in forms_of(page).fields:
            if field.get("type") == "hidden":
                assert "data-flag" not in field, field
                continue
            assert field.get("data-flag"), field
            flags.add(cast(str, field["data-flag"]))
    assert flags == {
        "--good",
        "--bad",
        "--by",
        "--production",
        "--sample",
        "--redact",
        "--ceiling",
        "--interval",
    }
    for flag in flags:
        words = ["record", "on", "--tenant", "a", flag]
        if flag != "--production":
            words.append("1")
        build_parser().parse_args(words)


def test_the_script_quotes_as_the_server_does() -> None:
    """The line the script writes and the line the server writes quote a word
    the same way: the pattern of words left bare is read out of `chart.js`
    and held equal to `shlex.quote`'s."""
    script = (
        files("digline.report")
        .joinpath("static", "chart.js")
        .read_text(encoding="utf-8")
    )
    found = re.search(r"if \(/(\^\[.+?\]\+\$)/\.test\(word\)\) return word;", script)
    assert found is not None, "the script's quoting is not where this test reads it"
    bare = re.compile(found.group(1).replace("\\/", "/"))

    def quoted(word: str) -> str:
        if word == "":
            return "''"
        if bare.fullmatch(word):
            return word
        return "'" + word.replace("'", "'\"'\"'") + "'"

    for word in (
        "",
        "acme",
        "Ada Lovelace",
        "it's",
        "a/b.c-d_e",
        "ada@example.org+x%",
        "x=1,2:3",
        "é",
        "$HOME",
    ):
        assert quoted(word) == shlex.quote(word), word


def chosen(fields: list[Field], picks: dict[str, str]) -> list[Field]:
    """The fields as a person leaves them: `picks` maps a field's name to the
    value they chose or typed."""
    out: list[Field] = []
    for field in fields:
        if field.name not in picks:
            out.append(replace(field, set=False) if field.kind == "radio" else field)
            continue
        pick = picks[field.name]
        if field.kind == "radio":
            out.append(replace(field, set=field.value == pick))
        elif field.kind == "checkbox":
            out.append(replace(field, set=bool(pick)))
        else:
            out.append(replace(field, value=pick, word=pick, set=bool(pick)))
    return out


def form_body(fields: list[Field], extra: dict[str, str]) -> str:
    """What a browser posts for these fields: the set ones, by name."""
    pairs = list(extra.items())
    pairs += [(f.name, f.value) for f in fields if f.set]
    return urllib.parse.urlencode(pairs)


def by_command(root: Path, line: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The line run as a person runs it, from the store's directory."""
    words = shlex.split(line)
    assert words[0] == "digline"
    with monkeypatch.context() as patched:
        patched.chdir(root)
        assert main(words[1:]) == EXIT_OK, line


def copy_of(root: Path, factory: pytest.TempPathFactory) -> Path:
    where = factory.mktemp("by-command")
    shutil.copytree(root, where, dirs_exist_ok=True)
    return where


def test_the_import_form_writes_what_its_command_writes(
    writing: Served,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A test runs the form and the command on two copies of one store, and
    the two stores come out identical (ADR 0061 §6). The mark has a space, so
    the line quotes it."""
    other = copy_of(writing.root, tmp_path_factory)
    long_id = answer_id(REFUND, LONG_ANSWER)
    hours_id = answer_id(HOURS, "nine to five")
    fields = chosen(
        import_fields(listing(writing.root)),
        {
            f"answer:{long_id}": "good",
            f"answer:{hours_id}": "bad",
            "by": "Ada Lovelace",
        },
    )
    line = command_line(["digline", "record", "import", *WRITES], fields)
    assert line == (
        "digline record import --tenant acme --suite suites/suite.py "
        f"--good {long_id} --bad {hours_id} --by 'Ada Lovelace'"
    )
    by_command(other, line, monkeypatch)
    answer = writing.ask(
        "POST",
        recordings_address("acme", "triage"),
        form_body(fields, {"locale": "en"}),
    )
    assert answer.status == 303, answer.body
    assert tree(writing.root) == tree(other)
    assert (writing.root / "suites" / "captured.json").is_file()


def test_the_switch_forms_write_what_their_commands_write(
    writing: Served,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = copy_of(writing.root, tmp_path_factory)
    fields = chosen(
        switch_fields(status_of(writing.root, read=False)),
        {"production": "1", "sample": "0.25", "redact": "none", "ceiling": "4096"},
    )
    on = command_line(["digline", "record", "on", "--tenant", "acme"], fields)
    assert on == (
        "digline record on --tenant acme --production --sample 0.25 --redact none "
        "--ceiling 4096"
    )
    by_command(other, on, monkeypatch)
    answer = writing.ask(
        "POST", recorder_address("acme"), form_body(fields, {"action": "on"})
    )
    assert answer.status == 303, answer.body
    assert tree(writing.root) == tree(other)

    by_command(other, "digline record off --tenant acme", monkeypatch)
    answer = writing.ask("POST", recorder_address("acme"), "action=off&locale=it")
    assert answer.status == 303, answer.body
    assert tree(writing.root) == tree(other)
    assert "on = false" in (writing.root / ".digline/acme/recorder.toml").read_text(
        encoding="utf-8"
    )


def test_a_write_is_a_303_to_the_page_that_reads_it(writing: Served) -> None:
    long_id = answer_id(REFUND, LONG_ANSWER)
    body = urllib.parse.urlencode(
        {"locale": "it", f"answer:{long_id}": "good", "by": "Ada"}
    )
    answer = writing.ask("POST", recordings_address("acme", "triage"), body)
    assert answer.status == 303
    assert answer.headers.get("Location") == (
        recordings_address("acme", "triage") + "?locale=it"
    )
    assert answer.headers.get("Content-Security-Policy") == WANTED
    before = tree(writing.root)
    page = writing.ask("GET", answer.headers["Location"]).body
    assert "already in the file, --good" in page
    assert tree(writing.root) == before  # the reload reads, and writes nothing


def test_a_post_without_the_cookie_is_refused_and_writes_nothing(
    writing: Served,
) -> None:
    before = tree(writing.root)
    for target, body in (
        (recorder_address("acme"), "action=off"),
        (recordings_address("acme", "triage"), "by=Ada"),
    ):
        bare = writing.ask("POST", target, body, cookie=False)
        assert bare.status == 403, target
        assert "writes the recorder's switch and a suite's cases only for" in (
            unescape(bare.body)
        )
        foreign = writing.ask("POST", target, body, origin="http://evil.example")
        assert foreign.status == 403, target
    assert tree(writing.root) == before


def test_the_address_opens_one_browser(root: Path) -> None:
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        first = opened(server, launch)
        second = server.ask("GET", f"/?launch={launch.key}")
        assert second.status == 403
        assert "already been opened" in second.body
        assert first.ask("POST", recorder_address("acme"), "action=off").status == 303


def test_promotion_alone_serves_no_write_of_the_recorder(root: Path) -> None:
    """`--allow-promote` without `--allow-record`: the key is there, and the
    recorder's routes are still absent, a 404, with no form drawn."""
    with serving(root, allow_record=False, allow_promote=True) as (server, launch):
        assert launch is not None
        browser = opened(server, launch)
        before = tree(root)
        for target in (recorder_address("acme"), recordings_address("acme", "triage")):
            assert browser.ask("POST", target, "action=off").status == 404, target
            assert 'method="post"' not in browser.ask("GET", target).body, target
        assert tree(root) == before


def test_another_suite_s_recordings_take_no_write(writing: Served) -> None:
    """The server writes the cases of the suite it was started with, at that
    suite's address; another suite's address is no route."""
    before = tree(writing.root)
    long_id = answer_id(REFUND, LONG_ANSWER)
    body = urllib.parse.urlencode({f"answer:{long_id}": "good", "by": "Ada"})
    answer = writing.ask("POST", recordings_address("acme", "other"), body)
    assert answer.status == 404
    assert tree(writing.root) == before


def test_the_recorder_s_flag_alone_does_not_promote(writing: Served) -> None:
    assert writing.ask("POST", "/promote", "run=x&replacing=none").status == 404
    assert 'action="/promote"' not in writing.ask("GET", "/").body


def test_a_refusal_is_the_command_s_sentence_and_writes_nothing(
    writing: Served,
) -> None:
    before = tree(writing.root)
    long_id = answer_id(REFUND, LONG_ANSWER)
    cases = (
        (
            recordings_address("acme", "triage"),
            urllib.parse.urlencode({f"answer:{long_id}": "good"}),
            "--by NAME is missing",
        ),
        (
            recordings_address("acme", "triage"),
            "by=Ada",
            "no answer named: --good ID or --bad ID",
        ),
        (
            recorder_address("acme"),
            "action=on&sample=x",
            "argument --sample: invalid float value: 'x'",
        ),
        (recorder_address("acme"), "action=on&production=1", "redact"),
    )
    for target, body, sentence in cases:
        answer = writing.ask("POST", target, body)
        assert answer.status == 400, (body, answer.body)
        assert "Nothing was written." in answer.body, body
        assert sentence in unescape(answer.body), (body, answer.body)
    assert tree(writing.root) == before


def test_the_command_serves_the_writes_behind_its_flag(root: Path) -> None:
    """`digline view --allow-record` as a person starts it: the line says so,
    the key is printed once, and the opened browser switches the recorder
    off."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "digline.cli",
            "view",
            "--suite",
            "suites/suite.py",
            "--port",
            "0",
            "--allow-record",
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        line: str = process.stdout.readline()
        assert "the recorder's writes enabled, for the first browser" in line, line
        address = urllib.parse.urlparse(line.split()[3])
        assert address.port is not None
        key = urllib.parse.parse_qs(address.query)["launch"][0]
        browser = opened(Served(address.port, root), Launch(key=key))
        page = browser.ask("GET", recordings_address("acme", "triage")).body
        assert "--suite suites/suite.py" in forms_of(page).lines[0]
        answer = browser.ask("POST", recorder_address("acme"), "action=off")
        assert answer.status == 303, answer.body
        assert "on = false" in (root / ".digline/acme/recorder.toml").read_text(
            encoding="utf-8"
        )
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_the_recorder_says_what_it_could_not_count(root: Path) -> None:
    """A process that keeps recordings and no counts file is said, beside the
    files that are not recordings: what it did not record is not known, which
    is not nothing (ADR 0062 §2). The store here is written by the writer
    alone, as a writer outside the recorder writes it, so it keeps no counts.
    """
    status = status_of(root, read=False)
    assert status.uncounted == 1
    said = "Not counted: 1 process(es) keep recordings and no counts"
    page = recorder_pages.recorder_page(
        status, suite="triage", locale="en", writes=None
    )
    assert said in unescape(page)
    counted = recorder_pages.recorder_page(
        replace(status, uncounted=0), suite="triage", locale="en", writes=None
    )
    assert "Not counted" not in counted


def test_the_case_link_keeps_the_pair_chosen(root: Path) -> None:
    """From two setups side by side, a case alone stays side by side."""
    found = compared(root, setups=[S1[:8], S2[:8]], show_setup=True)
    page = unescape(recorder_pages.setups_page(found, locale="en"))
    refund = next(c.id for c in found.cases if c.vars == REFUND)
    assert f"?case={refund}&setup={S1[:8]}&setup={S2[:8]}&locale=en" in page


def test_a_setup_shown_by_eight_characters_carries_its_whole_digest(
    root: Path,
) -> None:
    """The listing and the comparison name a setup by eight characters, as
    `digline record compare` prints it; the cases file holds the whole digest,
    and the page says it in a title a browser shows without a script."""
    page = recorder_pages.setups_page(compared(root), locale="en")
    assert f'title="setup {S1}: shown by its first 8 characters' in page
    assert len(S1) > 8
    page = recorder_pages.recordings_page(listing(root), locale="en", writes=None)
    assert f'title="setup {S2}: shown by its first 8 characters' in page
