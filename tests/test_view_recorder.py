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
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from email.message import Message
from functools import partial
from html import unescape
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests.test_view_policy import WANTED, inline_in

from digline.cli import recorder_pages
from digline.cli.recorder_pages import SHOWN_CHARS
from digline.cli.view import HOST, ViewHandler, self_netlocs
from digline.core.recording import RecordedStep, Recording, setup_digest_of
from digline.core.run import RecordedResponse
from digline.host import (
    import_listing,
    imported_since,
    load_suite,
    record_compare,
    recorder_status,
    switch_on,
)
from digline.host.importing import answer_id, closing_lines, group_line, setup_line
from digline.report.pages import (
    answer_address,
    recorder_address,
    recordings_address,
    setups_address,
)
from digline.run import Suite
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.wire.record_compare import (
    ComparedAnswer,
    ComparedCase,
    ComparedSetup,
    RecordComparison,
)

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
    fields: dict[str, Any] = {
        "source_tenant": "acme",
        "app": "support",
        "suite": "triage",
        "case": vars,
        "setup": setup,
        "setup_digest": setup_digest_of(setup),
        "response": RecordedResponse(output=output, kind="text", input="q"),
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
    page = recorder_pages.recordings_page(found, locale="en", allow_record=False)
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
    assert str(root / "suites" / "captured.json") in said


def test_each_answer_is_a_row_with_its_id_date_setup_and_count(root: Path) -> None:
    found = listing(root)
    page = recorder_pages.recordings_page(found, locale="en", allow_record=False)
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
    page = recorder_pages.recordings_page(found, locale="en", allow_record=False)
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
    page = recorder_pages.recordings_page(
        listing(root), locale="en", allow_record=False
    )
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
        page = recorder_pages.recordings_page(found, locale=locale, allow_record=True)
        seen = text_of(page).lower()
        for word in RANKING:
            assert word not in seen, (locale, word)
        assert "import all" not in seen and "--all" not in seen
        assert " checked" not in page and " selected" not in page
    assert "better" in "the better answer"  # the search finds a word that is there


def test_the_note_on_writes_is_there_without_the_flag(root: Path) -> None:
    found = listing(root)
    note = "served only by digline view --allow-record"
    assert note in recorder_pages.recordings_page(
        found, locale="en", allow_record=False
    )
    assert note not in recorder_pages.recordings_page(
        found, locale="en", allow_record=True
    )


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
        status, suite="triage", locale="en", allow_record=False
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
        status_of(root, read=False), suite="triage", locale="en", allow_record=False
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

    def ask(self, method: str, target: str, body: str = "") -> Answer:
        connection = http.client.HTTPConnection(HOST, self.port, timeout=10)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        connection.request(method, target, body=body or None, headers=headers)
        answer = connection.getresponse()
        text = answer.read().decode("utf-8")
        connection.close()
        return Answer(answer.status, answer.msg, text)


@pytest.fixture(params=[False, True], ids=["read-only", "allow-record"])
def served(root: Path, request: pytest.FixtureRequest) -> Iterator[Served]:
    """The server in this process, on loopback, in a thread, as `serve()`
    builds it: the suite and the module it was loaded from."""
    found = loaded(root)
    known: set[str] = set()
    handler = partial(
        ViewHandler,
        suite=found.suite,
        store=FileResultStore(root),
        known=known,
        allow_record=request.param,
        root=str(root),
        module=found.module,
    )
    httpd = ThreadingHTTPServer((HOST, 0), handler)  # pyright: ignore[reportArgumentType]
    port = int(httpd.server_address[1])
    known.update(self_netlocs(HOST, port))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Served(port, root)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def views(served: Served) -> list[str]:
    long_id = answer_id(REFUND, LONG_ANSWER)
    return [
        recordings_address("acme", "triage"),
        answer_address("acme", "triage", long_id),
        setups_address("acme", "triage"),
        setups_address("acme", "triage") + f"?setup={S1[:8]}&setup={S2[:8]}",
        recorder_address("acme"),
        recorder_address("acme") + "?locale=it",
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


def test_a_post_to_any_view_is_the_404_of_an_unknown_path(served: Served) -> None:
    """There is no write in this release, with the flag or without it: a POST
    is answered as any path the server does not have (ADR 0032 §2)."""
    before = tree(served.root)
    for target in views(served):
        answer = served.ask("POST", target, "good=x&by=Ada")
        assert answer.status == 404, target
        assert "no such action" in answer.body, target
    assert tree(served.root) == before


def test_every_screen_links_the_three_views(served: Served) -> None:
    for target in ("/", "/suspend/x?reason=r", *views(served)):
        page = served.ask("GET", target).body
        for href in (
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
        assert str(root / "suites" / "captured.json") in unescape(answer.body)
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
