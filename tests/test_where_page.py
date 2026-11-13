"""The view of where the project is: each state laid out, and nothing more.

`tests/test_where.py` holds which state a store is in; this holds what the
page says of each: its sentence, the command for the next step shown and
never run, the page that says more, and the switch as a button only on a
server that writes. Served, the view is covered beside the recorder's in
`tests/test_view_recorder.py`: the policy on every response, nothing inline,
a GET that writes nothing, and a POST answered as an unknown path.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from digline.cli.recorder_pages import WHERE_DOCS, where_page
from digline.host.importing import Shape
from digline.host.where import RECORD_LINES, STATES, State, Where, record_lines
from digline.report.pages import (
    nav,
    recorder_address,
    where_address,
    with_screens,
    with_tenant_screens,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

#: What a served page's commands carry, as a server started with
#: `--suite suites/suite.py` from the store's directory gives them.
SUITE_ARG = "suites/suite.py"
SWITCH = ["--tenant", "acme"]

#: One value per state, with the numbers its sentence reads.
SAMPLES: dict[State, Where] = {
    "nothing_recorded": Where("nothing_recorded", "acme", suite="triage"),
    "recording_off": Where("recording_off", "acme", count=4, suite="triage"),
    "unassigned": Where("unassigned", "acme", count=3),
    "no_suite_yet": Where(
        "no_suite_yet",
        "acme",
        count=5,
        suite="triage",
        shapes=((Shape(episode=False, kind="text"), 5),),
    ),
    "to_import": Where("to_import", "acme", count=2, suite="triage"),
    "never_run": Where("never_run", "acme", count=6, suite="triage"),
    "cases_changed": Where(
        "cases_changed", "acme", count=2, suite="triage", run_key="k", exit_code=1
    ),
    "judge_disagrees": Where(
        "judge_disagrees", "acme", count=1, suite="triage", run_key="k", exit_code=1
    ),
    "green_without_red": Where(
        "green_without_red", "acme", count=7, suite="triage", run_key="k", exit_code=0
    ),
    "new_setup": Where(
        "new_setup", "acme", count=5, suite="triage", run_key="k", exit_code=0
    ),
    "nothing_to_do": Where(
        "nothing_to_do",
        "acme",
        count=8,
        suite="triage",
        run_key="k",
        exit_code=0,
        last_import="2026-11-03T08:02:00+00:00",
    ),
    "last_run_red": Where(
        "last_run_red", "acme", count=8, suite="triage", run_key="k", exit_code=2
    ),
}

#: The heading each state shows, in English, with the sample's numbers.
HEADINGS: dict[State, str] = {
    "nothing_recorded": "Nothing recorded yet",
    "recording_off": "Recording is off",
    "unassigned": "3 call(s) named no suite",
    "no_suite_yet": "5 recording(s) in triage, no suite yet",
    "to_import": "2 since the last import",
    "never_run": "The suite has never run",
    "cases_changed": "The newest run was made with other cases",
    "judge_disagrees": "The judge disagrees with a person on 1",
    "green_without_red": "Green without a red",
    "new_setup": "5 answer(s) from a new setup",
    "nothing_to_do": "Nothing to do",
    "last_run_red": "The newest run exits 2",
}

#: The command each state shows, or none where the next step is an edit.
COMMANDS: dict[State, str | None] = {
    "nothing_recorded": "digline record on --tenant acme",
    "recording_off": "digline record on --tenant acme",
    "unassigned": (
        "digline record import --tenant acme --suite suites/suite.py --from _unassigned"
    ),
    "no_suite_yet": None,
    "to_import": "digline record import --tenant acme --suite suites/suite.py",
    "never_run": "digline run --suite suites/suite.py",
    "cases_changed": "digline run --suite suites/suite.py",
    "judge_disagrees": "digline explain --suite suites/suite.py --run latest",
    "green_without_red": None,
    "new_setup": "digline record compare --tenant acme --suite suites/suite.py",
    "nothing_to_do": None,
    "last_run_red": "digline explain --suite suites/suite.py --run latest",
}


def page(state: State, *, writes: list[str] | None = None, locale: str = "en") -> str:
    return where_page(
        SAMPLES[state],
        suite="triage",
        suite_arg=SUITE_ARG,
        root=[],
        locale="it" if locale == "it" else "en",
        writes=writes,
    )


def test_every_state_has_a_sample_a_heading_and_a_command() -> None:
    assert set(SAMPLES) == set(HEADINGS) == set(COMMANDS) == set(STATES)
    assert set(WHERE_DOCS) == set(STATES)


@pytest.mark.parametrize("state", STATES)
def test_each_state_is_its_heading_its_command_and_its_page(state: State) -> None:
    shown = page(state)
    assert f"<h1>{HEADINGS[state]}</h1>" in shown.replace("&#x27;", "'"), shown
    command = COMMANDS[state]
    if command is None:
        assert '<pre class="snippet">digline' not in shown
    else:
        assert f'<pre class="snippet">{command}</pre>' in shown, shown
    for doc, anchor in WHERE_DOCS[state]:
        slug = doc.removesuffix(".md")
        href = f"https://digline.dev/product/{slug}/" + (f"#{anchor}" if anchor else "")
        assert f'href="{href}"' in shown, (state, href)


@pytest.mark.parametrize("state", STATES)
def test_no_state_offers_a_button_that_runs_anything(state: State) -> None:
    """The command is shown and never launched: no form on the page but the
    switch's, and that one only where the recorder's buttons are."""
    for writes in (None, SWITCH):
        shown = page(state, writes=writes)
        forms = re.findall(r'<form method="post" action="([^"]+)"', shown)
        if state == "recording_off" and writes is not None:
            assert forms == [recorder_address("acme")]
            assert '<input type="hidden" name="action" value="on">' in shown
            assert "digline record on --tenant acme" in shown
        else:
            assert forms == [], (state, writes)
            assert "<button" not in shown


def test_the_switch_is_a_button_only_on_a_server_that_writes() -> None:
    assert "<button" not in page("recording_off")
    assert "<button" in page("recording_off", writes=SWITCH)


def test_nothing_recorded_shows_each_language_s_three_lines() -> None:
    """The documentation's lines, with the page's tenant and suite in place of
    its example's: the sample is tenant acme, suite triage."""
    shown = page("nothing_recorded")
    for language, _page, lines in record_lines("acme", "triage"):
        assert f"<summary>{language}</summary>" in shown
        block = shown.split(f"<summary>{language}</summary>")[1].split("</details>")[0]
        for line in lines:
            assert line.replace('"', "&quot;") in block, (language, line)


@pytest.mark.parametrize(
    ("language", "doc", "lines"), RECORD_LINES, ids=[r[0] for r in RECORD_LINES]
)
def test_each_line_is_quoted_from_its_page_as_it_stands(
    language: str, doc: str, lines: tuple[str, ...]
) -> None:
    """Taken as the page has it, never rewritten: a line that moved on its
    page fails here."""
    text = (DOCS / doc).read_text(encoding="utf-8")
    for line in lines:
        assert line in text, (language, doc, line)


def test_the_lines_record_where_the_page_reads() -> None:
    """The documentation's example records under tenant acme and suites
    category, triage and refunds; copied from a page about tenant dev and
    suite screening, those lines would record somewhere else. Every line
    shows the page's tenant and suite, and keeps the rest as it stands."""
    shown = where_page(
        Where("nothing_recorded", "dev", suite="screening"),
        suite="screening",
        suite_arg="suite.toml",
        root=[],
        locale="en",
        writes=None,
    )
    blocks = shown.split("<details>")[1:]
    assert len(blocks) == len(RECORD_LINES)
    for block in blocks:
        snippet = block.split('<pre class="snippet">')[1].split("</pre>")[0]
        assert "acme" not in snippet, snippet
        assert "dev" in snippet, snippet
        for example in ("category", "triage", "refunds"):
            assert example not in snippet, snippet
    assert "digline record on --tenant dev" in shown


def test_each_language_links_its_own_page() -> None:
    shown = page("nothing_recorded")
    for language, href in (
        ("Java", "https://digline.dev/product/record-java/"),
        ("Node", "https://digline.dev/product/record-node/"),
        ("Python", "https://digline.dev/product/record/#wrapping-the-client"),
    ):
        block = shown.split(f"<summary>{language}</summary>")[1].split("</details>")[0]
        assert f'href="{href}"' in block, (language, block)


def test_calls_that_named_no_suite_say_capture_first_where_none_is_declared() -> None:
    """`--from _unassigned` is refused for a suite with no capture source: the
    page says to declare one first, and links where it is said how, before
    the command. Where the suite declares one, the command alone."""
    without = where_page(
        Where("unassigned", "dev", count=4, capture=False),
        suite="screening",
        suite_arg="suite.toml",
        root=[],
        locale="en",
        writes=None,
    )
    declare = without.index("First declare where the suite")
    assert declare < without.index("--from _unassigned</pre>")
    assert 'href="https://digline.dev/product/declarative/#capture"' in without
    declared = where_page(
        Where("unassigned", "dev", count=4, capture=True),
        suite="screening",
        suite_arg="suite.toml",
        root=[],
        locale="en",
        writes=None,
    )
    assert "First declare where the suite" not in declared
    assert "--from _unassigned</pre>" in declared


def test_no_suite_yet_shows_the_shapes_it_counted() -> None:
    assert "<li>a single call, text · ×5</li>" in page("no_suite_yet")


def test_to_import_and_new_setup_open_the_view_that_does_it() -> None:
    assert 'href="/recordings/acme/triage/?locale=en"' in page("to_import")
    assert 'href="/setups/acme/triage/?locale=en"' in page("new_setup")


def test_nothing_to_do_says_the_last_import() -> None:
    assert "up to 2026-11-03T08:02:00+00:00" in page("nothing_to_do")


@pytest.mark.parametrize("state", STATES)
def test_each_state_reads_in_italian_too(state: State) -> None:
    shown = page(state, locale="it")
    heading = re.search(r"<h1>(.*?)</h1>", shown)
    assert heading is not None and heading.group(1) != HEADINGS[state]


def slugs(doc: str) -> set[str]:
    """The anchors a page's headings get on the site: lower case, the
    punctuation dropped, spaces as hyphens."""
    text = (DOCS / doc).read_text(encoding="utf-8")
    return {
        re.sub(r"[^\w\- ]", "", heading.lower()).strip().replace(" ", "-")
        for heading in re.findall(r"^#{1,4} (.+)$", text, re.MULTILINE)
    }


@pytest.mark.parametrize("state", STATES)
def test_each_page_named_exists_and_has_its_anchor(state: State) -> None:
    for doc, anchor in WHERE_DOCS[state]:
        assert (DOCS / doc).is_file(), doc
        if anchor:
            assert anchor in slugs(doc), (doc, anchor)


def test_where_you_are_opens_the_bar() -> None:
    """The first entry of every screen's bar, before the runs, and the runs
    stay at `/`."""
    bar = with_screens(
        nav("en", here="runs", suite="triage"),
        tenant="acme",
        suite="triage",
        locale="en",
    )
    links = re.findall(r'<a href="([^"?]+)', bar)
    assert links[:2] == [where_address("acme", "triage"), "/"]
    assert ">Where you are</a>" in bar
    italian = with_screens(
        nav("it", here="runs", suite="triage"),
        tenant="acme",
        suite="triage",
        locale="it",
    )
    assert ">Dove sei</a>" in italian


def test_the_runs_link_is_found_in_linear_time_before_many_lookalikes() -> None:
    """The bar of a server started without a suite finds the runs' link with
    a pattern that cannot cross a `<`. The one before it could, so from each
    `<a href="/?locale=a"` its `[^>]*` ran on to the next `>`: on 20,000 of
    them, 400,000 characters, it took 2.1 seconds on the machine this was
    measured on, and four times as long for twice the input. The new one took
    half a millisecond, so half a second is a ceiling, not a race."""
    lookalikes = '<a href="/?locale=a"' * 20_000
    document = lookalikes + nav("en", here="runs", suite="triage")
    start = time.perf_counter()
    bar = with_tenant_screens(document, tenant="acme", locale="en")
    took = time.perf_counter() - start
    assert took < 0.5, f"{took:.2f}s"
    assert bar.startswith(lookalikes)
    assert ">Where you are</a>" in bar
