"""What every response of `digline view` says a browser may run, and the files
it serves for that (ADR 0061 §4, §7).

The server carries a policy that forbids every inline style and script, so the
rule that no page carries one is held here by parsing what the server actually
sends, page by page, and not by searching text: an answer a model gave can hold
the characters `style=`, and the page shows it escaped.

The sheet, uPlot and digline's one script are served from the server's own
files. uPlot is vendored, so what is held here is what an upgrade must keep
equal: the version the sheet's absorbed rules name and the one the script's
header names, and the bytes of those rules against the file npm ships.
"""

from __future__ import annotations

import hashlib
import http.client
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from email.message import Message
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path

import pytest
from tests._helpers import cli
from tests.test_view import RUN_A, RUN_B, launch_of, port_of, promoted, server

from digline.cli import EXIT_USAGE
from digline.cli.view import POLICY
from digline.core import compare
from digline.report import SHEET, compare_page, render_html, render_run_html
from digline.report.pages import SHEET_ADDRESS
from digline.report.sheet import UPLOT_CSS

#: The policy of ADR 0061 §4.4, written out here rather than read from the
#: module, so a change to the module's constant is a red until this follows.
WANTED = (
    "default-src 'none'; style-src 'self'; script-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)

#: The SHA-256 of `package/dist/uPlot.min.css` in `uplot-1.6.31.tgz`, whose
#: sha512 matched the registry's `dist.integrity` when it was vendored.
UPLOT_CSS_SHA256 = "df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04"

#: And of `package/dist/uPlot.iife.min.js` in the same tarball.
UPLOT_JS_SHA256 = "2d27e8ad3d228164525ce213f9dc716f39b4e3aee0cc773fb3491c96cf4921a2"


class Inline(HTMLParser):
    """What a page carries inline: a `style` attribute, a `<style>`, or a
    `<script>` that has no `src` and is not a data block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        named = dict(attrs)
        if "style" in named:
            self.found.append(f"<{tag} style=...>")
        if tag == "style":
            self.found.append("<style>")
        data_block = named.get("type") == "application/json"
        if tag == "script" and "src" not in named and not data_block:
            self.found.append("<script> with a body")


def inline_in(page: str) -> list[str]:
    parser = Inline()
    parser.feed(page)
    parser.close()
    return parser.found


def test_the_inline_check_finds_what_it_is_for() -> None:
    """The control: each of the three is found, and what a page may carry is
    not. Without it a parser that found nothing would pass every page below."""
    assert inline_in('<p style="color:red">x</p>') == ["<p style=...>"]
    assert inline_in("<style>p{}</style>") == ["<style>"]
    assert inline_in("<script>alert(1)</script>") == ["<script> with a body"]
    assert inline_in('<script type="module">x()</script>') == ["<script> with a body"]
    assert inline_in('<script src="/static/chart.js"></script>') == []
    assert inline_in('<script type="application/json" id="d">{}</script>') == []
    # Text is text: the characters of an attribute, escaped into a cell.
    assert inline_in("<td>&lt;p style=&quot;x&quot;&gt;</td>") == []


@dataclass(frozen=True)
class Answer:
    status: int
    headers: Message
    body: str

    def header(self, name: str) -> str:
        return self.headers.get(name, "")


def response(port: int, target: str, cookie: str = "") -> Answer:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", target, headers={"Cookie": cookie} if cookie else {})
    answer = connection.getresponse()
    body = answer.read().decode("utf-8")
    connection.close()
    return Answer(answer.status, answer.msg, body)


@pytest.fixture
def flagged(repo: Path) -> Iterator[tuple[int, str, str, str]]:
    """The server with every page it can draw: flagged, opened, two runs, a
    baseline. The port, the baseline key, a newer run's key, and the launch key
    still unspent, so a test can read the hand-over's own response."""
    key = promoted(repo)
    done = cli(repo, "run", "--suite", "suite_qa.py")
    newer = done.stdout.strip()
    with server(repo, "--allow-promote") as (base, line):
        yield port_of(base), key, newer, launch_of(line)


def every_response(
    port: int, key: str, newer: str, launch: str
) -> list[tuple[str, Answer]]:
    """Every kind of answer the server gives: the hand-over, each screen, a
    refusal, an unknown path, and the three files."""
    handed = response(port, f"/?launch={launch}")
    cookie = handed.header("Set-Cookie").split(";")[0]
    assert cookie, "the hand-over set no cookie"
    targets = [
        "/",
        "/?locale=it",
        f"/compare?run={newer}",
        f"/compare?run={newer}&against={key}",
        f"/compare?run={key}&against={newer}",
        "/case/capital-it",
        "/suspend/capital-it?reason=a+%3Cp+style%3Dx%3E+reason",
        f"/compare?run={key}",
        # The recorder's views. This suite declares no capture source, so the
        # recordings answer the import's refusal; the other two read.
        "/recordings/acme-bank/qa/",
        "/setups/acme-bank/qa/",
        "/recorder/acme-bank/",
        "/no-such-page",
        "/x/no-such-view/",
        SHEET_ADDRESS,
        "/static/uPlot.iife.min.js",
        "/static/chart.js",
        "/static/no-such-file.js",
    ]
    answers = [("hand-over", handed)]
    answers += [(target, response(port, target, cookie)) for target in targets]
    return answers


def test_every_response_carries_the_policy(
    flagged: tuple[int, str, str, str],
) -> None:
    port, key, newer, launch = flagged
    assert POLICY == WANTED
    for target, answer in every_response(port, key, newer, launch):
        assert answer.header("Content-Security-Policy") == WANTED, target
        assert answer.header("X-Content-Type-Options") == "nosniff", target
        assert answer.header("Referrer-Policy") == "no-referrer", target


def test_no_page_the_server_sends_carries_anything_inline(
    flagged: tuple[int, str, str, str],
) -> None:
    """Parsed, every HTML response, the refusals and the 404 included."""
    port, key, newer, launch = flagged
    pages = [
        (target, answer)
        for target, answer in every_response(port, key, newer, launch)
        if answer.header("Content-Type").startswith("text/html")
    ]
    # The screens are among them, so a server that answered every page with a
    # bare error would not pass on an empty list.
    assert sum(1 for _target, answer in pages if answer.status == 200) >= 9
    for target, answer in pages:
        assert inline_in(answer.body) == [], target


def test_the_suspension_page_shows_a_style_attribute_as_text(
    flagged: tuple[int, str, str, str],
) -> None:
    """The reason a page is parsed and not searched: a reason that holds the
    characters of an attribute reaches the page as text, and a grep for
    `style=` would call that page inline."""
    port, _key, _newer, _launch = flagged
    page = response(port, "/suspend/capital-it?reason=a+%3Cp+style%3Dx%3E").body
    assert "style=x" in page
    assert inline_in(page) == []


def test_the_sheet_is_served_from_the_one_string(
    flagged: tuple[int, str, str, str],
) -> None:
    port, _key, _newer, _launch = flagged
    answer = response(port, SHEET_ADDRESS)
    assert answer.status == 200
    assert answer.header("Content-Type").startswith("text/css")
    assert answer.body == SHEET
    page = response(port, "/").body
    assert f'<link rel="stylesheet" href="{SHEET_ADDRESS}">' in page


def test_the_scripts_are_served_as_they_are_shipped(
    flagged: tuple[int, str, str, str],
) -> None:
    port, _key, _newer, _launch = flagged
    static = files("digline.report").joinpath("static")
    for name in ("uPlot.iife.min.js", "chart.js"):
        answer = response(port, f"/static/{name}")
        assert answer.status == 200, name
        assert answer.header("Content-Type").startswith("text/javascript")
        assert answer.body == static.joinpath(name).read_text(encoding="utf-8")
    assert response(port, "/static/uPlot.LICENSE").status == 404
    assert response(port, "/static/../sheet.py").status == 404


def test_the_vendored_script_is_npm_s_and_its_licence_is_beside_it() -> None:
    static = files("digline.report").joinpath("static")
    script = static.joinpath("uPlot.iife.min.js").read_bytes()
    assert hashlib.sha256(script).hexdigest() == UPLOT_JS_SHA256
    licence = static.joinpath("uPlot.LICENSE").read_text(encoding="utf-8")
    assert "MIT" in licence and "Leon Sorokin" in licence


def test_the_absorbed_rules_are_npm_s_byte_for_byte() -> None:
    """An edit inside the absorbed rules is a red here: the sheet's own rules
    go after them, and the theme is digline's to change there."""
    digest = hashlib.sha256(UPLOT_CSS.encode("utf-8")).hexdigest()
    assert digest == UPLOT_CSS_SHA256
    assert UPLOT_CSS in SHEET


def test_the_sheet_and_the_script_name_one_uplot_release() -> None:
    """Upgrading uPlot is two edits, the script and the rules, and this is
    the red until both are made (ADR 0061 §7)."""
    script = (
        files("digline.report")
        .joinpath("static", "uPlot.iife.min.js")
        .read_text(encoding="utf-8")
    )
    shipped = re.match(
        r"/\*! https://github\.com/leeoniya/uPlot \(v([0-9.]+)\) \*/", script
    )
    absorbed = re.search(r"uPlot ([0-9.]+), dist/uPlot\.min\.css, absorbed", SHEET)
    assert shipped and absorbed
    assert shipped.group(1) == absorbed.group(1)
    assert "Copyright (c) 2022 Leon Sorokin" in SHEET


def test_view_takes_no_host(repo: Path) -> None:
    """The option is gone, not ignored: argparse refuses it by name, with the
    usage exit code, before anything is served.

    The first line of standard output is read rather than waited for. A server
    that started prints its address there and keeps running, and a test that
    only waited would fail on a timeout that says nothing about what it saw.
    Refused, the process ends, and the line is empty.
    """
    process = subprocess.Popen(
        [sys.executable, "-m", "digline.cli", "view", "--suite", "suite_qa.py"]
        + ["--host", "0.0.0.0", "--port", "0"],  # noqa: S104
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None and process.stderr is not None
        first = process.stdout.readline()
        assert first == "", f"a server started on --host: {first!r}"
        err = process.stderr.read()
        assert process.wait(timeout=30) == EXIT_USAGE
    finally:
        process.kill()
        process.wait(timeout=10)
    # argparse's own sentence for an option the parser does not have.
    assert err.rstrip().splitlines()[-1] == (
        "digline: error: unrecognized arguments: --host 0.0.0.0"
    )


def test_allow_record_is_accepted_and_opens_no_route(repo: Path) -> None:
    """The flag exists before the writes it will serve, and serves none yet:
    the server starts, reads, and answers a POST with the 404 any unknown path
    gets (ADR 0061 §4)."""
    promoted(repo)
    with server(repo, "--allow-record") as (base, _line):
        port = port_of(base)
        assert response(port, "/").status == 200
        for path in ("/record", "/record/on", "/import", "/promote"):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.request("POST", path, body=b"", headers={"Content-Length": "0"})
            answer = connection.getresponse()
            answer.read()
            connection.close()
            assert answer.status == 404, path


def test_the_report_on_file_carries_the_sheet_inline_and_nothing_else() -> None:
    """The report is opened from disk, where no server answers a link: it
    carries the one sheet inline, once, and still no script (ADR 0061 §7). A
    served page links the same sheet instead, and is otherwise the report."""
    for document in (
        render_html(compare(RUN_B, RUN_A), RUN_B, RUN_A, locale="en", declared=None),
        render_run_html(RUN_A, locale="it"),
    ):
        assert document.count(f"<style>\n{SHEET}</style>\n") == 1
        assert "<link" not in document and "<script" not in document
    served = compare_page(RUN_B, RUN_A, locale="en", suite="brief", declared=None)
    assert "<style" not in served and SHEET_ADDRESS in served
    assert inline_in(served) == []


def test_the_sizes_docs_view_md_gives_are_the_files_shipped() -> None:
    """The table of weights is a measurement, and a figure that stopped being
    one is a red here rather than a sentence nobody re-reads."""
    page = (Path(__file__).resolve().parents[1] / "docs" / "view.md").read_text(
        encoding="utf-8"
    )
    static = files("digline.report").joinpath("static")
    rows = {
        "uPlot.iife.min.js": (
            r"\| `/static/uPlot\.iife\.min\.js`, uPlot [0-9.]+ \| ([0-9 ]+) \|"
        ),
        "chart.js": r"\| `/static/chart\.js`, digline's \| ([0-9 ]+) \|",
    }
    for name, pattern in rows.items():
        found = re.search(pattern, page)
        assert found, name
        size = len(static.joinpath(name).read_bytes())
        assert int(found.group(1).replace(" ", "")) == size, name
    absorbed = re.search(r"uPlot's own stylesheet, ([0-9 ]+) bytes", page)
    assert absorbed and int(absorbed.group(1).replace(" ", "")) == len(UPLOT_CSS)
