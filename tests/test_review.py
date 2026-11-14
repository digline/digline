"""The review, one answer at a time, in `digline view`. (ADR 0066 §2, §3)

From a first use outside the project, on an application with a judged suite:
27 recorded answers were reviewed in a file prepared apart, and the verdicts
passed through one command line with 27 flags typed by hand. Here each answer
has a page of its own, whole, with a yes and a no, and each press writes one
answer through the path `digline record import` takes.

What is held, each beside the mistake it prevents:

- the page shows the question and its context, the answer whole and an
  episode's steps with each call's arguments and result; nothing is chosen,
  and nothing writes more than the one answer the address names;
- a press and the command, on two copies of one store, leave the two stores
  identical (ADR 0061 §6), and one press adds one case to `captured.json`;
- the `303` leads to the next answer not yet reviewed, which reads back from
  the draft what the press wrote, and never says a text the address carries;
- an answer already reviewed is shown as such, with no button;
- the name is the one typed, kept for the session in the server's memory,
  shown on every answer after, and gone when the server starts again;
- the key, the cookie and the origin hold for the new route as for every
  write (ADR 0061 §4), and without `--allow-record` there is no form and a
  POST is the 404 of an unknown path. The pages are in `views()` of
  `tests/test_view_recorder.py`, where the policy and *a GET writes nothing*
  hold for them on both servers.
"""

from __future__ import annotations

import json
import urllib.parse
from html import unescape
from pathlib import Path

import pytest
from tests.test_view_recorder import (
    HOURS,
    LONG_ANSWER,
    REFUND,
    SETUP_2,
    WRITES,
    Served,
    by_command,
    copy_of,
    listing,
    opened,
    recording,
    serving,
    text_of,
    tree,
)
from tests.test_view_recorder import (
    root as root,  # noqa: F401 — the fixture, by its name
)

from digline.cli import recorder_pages
from digline.cli.recorder_pages import Field, command_line
from digline.core.run import RecordedStep, RecordedToolCall
from digline.host.importing import answer_id, review_order
from digline.report.pages import review_address
from digline.store.file_store import FileResultStore, RecordingWriter

CAPTURED = Path("suites") / "captured.json"
LONG_ID = answer_id(REFUND, LONG_ANSWER)
HOURS_ID = answer_id(HOURS, "nine to five")


def cases_in(root: Path) -> list[dict[str, object]]:
    path = root / CAPTURED
    return json.loads(path.read_text("utf-8")) if path.is_file() else []


def press(
    served: Served, answer: str, verdict: str, by: str, **extra: str
) -> tuple[int, str, str]:
    body = urllib.parse.urlencode(
        {"locale": "en", "verdict": verdict, "by": by, **extra}
    )
    done = served.ask("POST", review_address("acme", "triage", answer), body)
    return done.status, done.headers.get("Location", ""), done.body


@pytest.fixture
def writing(root: Path):  # noqa: F811 — the fixture `root`, by its name
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        yield opened(server, launch)


# -- the page ---------------------------------------------------------------- #


def test_the_page_shows_the_question_and_the_answer_whole(root: Path) -> None:
    found = listing(root)
    [answer] = [item for item in found.answers if item.id == LONG_ID]
    said = text_of(
        recorder_pages.review_page(found, answer, locale="en", writes=WRITES, by="")
    )
    assert LONG_ANSWER.strip() in said
    assert "refund?" in said
    assert "The question, and its context" in said


def test_an_episode_shows_its_steps_with_arguments_and_result(root: Path) -> None:
    """A document the answer cites reaches the page as the recording holds it:
    here, a tool's result inside a step."""
    RecordingWriter(FileResultStore(root)).write(
        recording(
            {"messages": [{"role": "user", "content": "policy?"}]},
            SETUP_2,
            "see section 4",
            "20",
            steps=(
                RecordedStep(
                    index=0,
                    actor="tool",
                    call=RecordedToolCall(
                        tool="search",
                        arguments='{"q": "refund policy"}',
                        result="Section 4: refunds within 14 days.",
                    ),
                ),
                RecordedStep(index=1, actor="model", finish="stop"),
            ),
            id="f" * 32,
        )
    )
    found = listing(root)
    [answer] = [item for item in found.answers if item.text == "see section 4"]
    said = text_of(
        recorder_pages.review_page(found, answer, locale="en", writes=WRITES, by="")
    )
    assert "0 · a tool · search" in said
    assert '{"q": "refund policy"}' in said
    assert "Section 4: refunds within 14 days." in said
    assert "1 · the model · stop" in said


def test_nothing_is_chosen_and_nothing_names_more_than_one_answer(
    root: Path,
) -> None:
    found = listing(root)
    [answer] = [item for item in found.answers if item.id == LONG_ID]
    page = recorder_pages.review_page(found, answer, locale="en", writes=WRITES, by="")
    assert " checked" not in page and "autofocus" not in page
    assert page.count('name="verdict"') == 2
    assert 'name="answer:' not in page
    for flag in ("--good", "--bad"):
        assert f"--tenant acme --suite suites/suite.py {flag} {LONG_ID}" in page


def test_the_first_page_is_the_first_answer_not_reviewed_in_the_listing_s_order(
    root: Path,
) -> None:
    found = listing(root)
    first = next(item for item in review_order(found) if item.electable)
    assert recorder_pages.next_to_review(found) == first


def test_without_the_flag_the_page_reads_and_has_no_form(root: Path) -> None:
    with serving(root, allow_record=False) as (served, _launch):
        page = served.ask("GET", review_address("acme", "triage", LONG_ID)).body
        assert "<form" not in page
        assert "--allow-record" in text_of(page)
        refused = served.ask(
            "POST",
            review_address("acme", "triage", LONG_ID),
            "verdict=good&by=Ada",
        )
        assert refused.status == 404
        assert "no such action" in refused.body
    assert cases_in(root) == []


# -- one press, one answer, the command's file -------------------------------- #


def test_a_press_writes_what_the_command_writes(
    writing: Served,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two presses and the two commands under their buttons, on two copies of
    one store: the stores come out identical (ADR 0061 §6)."""
    other = copy_of(writing.root, tmp_path_factory)
    by = Field("by", "Ada Lovelace", "--by", "Ada Lovelace", True)
    for answer, flag, verdict in (
        (LONG_ID, "--good", "good"),
        (HOURS_ID, "--bad", "bad"),
    ):
        line = command_line(
            ["digline", "record", "import", *WRITES, flag, answer], [by]
        )
        assert line.endswith(f"{flag} {answer} --by 'Ada Lovelace'")
        by_command(other, line, monkeypatch)
        status, _, body = press(writing, answer, verdict, "Ada Lovelace")
        assert status == 303, body
    assert tree(writing.root) == tree(other)


def test_one_press_adds_one_case_whatever_else_the_form_carries(
    writing: Served,
) -> None:
    before = len(cases_in(writing.root))
    status, _, body = press(
        writing, LONG_ID, "good", "Ada", **{f"answer:{HOURS_ID}": "bad"}
    )
    assert status == 303, body
    after = cases_in(writing.root)
    assert len(after) == before + 1
    assert after[-1]["id"] == LONG_ID


def test_the_303_reads_back_what_was_written_on_the_next_answer(
    writing: Served,
) -> None:
    status, location, _ = press(writing, LONG_ID, "good", "Ada")
    assert status == 303
    found = listing(writing.root)
    following = recorder_pages.next_to_review(found, LONG_ID)
    assert following is not None
    assert location.startswith(review_address("acme", "triage", following.id))
    assert f"after={LONG_ID}" in location
    said = text_of(writing.ask("GET", location).body)
    assert f"Written: {LONG_ID}, --good, by Ada." in said


def test_an_address_cannot_make_the_page_say_a_text_of_its_own(
    writing: Served,
) -> None:
    crafted = "<b>approved by legal</b>"
    page = writing.ask(
        "GET",
        review_address("acme", "triage")
        + "?"
        + urllib.parse.urlencode({"after": crafted}),
    ).body
    assert "approved by legal" not in unescape(page)
    assert "The answer the address names is not in the file." in text_of(page)


def test_an_answer_already_reviewed_is_shown_as_such_and_offered_no_button(
    writing: Served,
) -> None:
    assert press(writing, LONG_ID, "bad", "Ada")[0] == 303
    page = writing.ask("GET", review_address("acme", "triage", LONG_ID)).body
    assert 'name="verdict"' not in page
    assert "already in the file, --bad, by Ada" in text_of(page)
    # Pressed again, it is the import's refusal, and nothing more is written.
    before = tree(writing.root)
    status, _, _ = press(writing, LONG_ID, "good", "Ada")
    assert status == 400
    assert tree(writing.root) == before


def test_next_writes_nothing_and_skips_what_is_reviewed(writing: Served) -> None:
    """The second answer waiting is reviewed; the first's *next* goes to the
    third, past it, and following it writes nothing."""
    waiting = [a for a in review_order(listing(writing.root)) if a.electable]
    assert len(waiting) >= 3, [a.id for a in waiting]
    first, second, third = waiting[:3]
    assert press(writing, second.id, "good", "Ada")[0] == 303
    before = tree(writing.root)
    page = writing.ask("GET", review_address("acme", "triage", first.id)).body
    following = review_address("acme", "triage", third.id)
    assert f'href="{following}?locale=' in page
    assert writing.ask("GET", following).status == 200
    assert tree(writing.root) == before


# -- the name, once per session ----------------------------------------------- #


def test_the_name_stays_for_the_session_and_is_gone_at_a_new_start(
    root: Path,
) -> None:
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        served = opened(server, launch)
        page = served.ask("GET", review_address("acme", "triage")).body
        assert 'name="by"' in page and 'value=""' in page
        assert press(served, LONG_ID, "good", "Ada Lovelace")[0] == 303
        page = served.ask("GET", review_address("acme", "triage")).body
        assert 'value="Ada Lovelace"' in page
        assert "Reviewing as Ada Lovelace." in text_of(page)
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        served = opened(server, launch)
        page = served.ask("GET", review_address("acme", "triage")).body
        assert "Ada Lovelace" not in page


def test_the_name_is_the_one_typed_never_the_machine_s(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0059 §1: never read from git or the environment. A press with the
    field empty is the import's refusal, even after a name was kept."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Someone Else")
    monkeypatch.setenv("USER", "someone")
    with serving(root, allow_record=True) as (server, launch):
        assert launch is not None
        served = opened(server, launch)
        page = served.ask("GET", review_address("acme", "triage")).body
        assert "Someone Else" not in page and 'value="someone"' not in page
        assert press(served, LONG_ID, "good", "Ada")[0] == 303
        before = tree(root)
        status, _, body = press(served, HOURS_ID, "good", "")
        assert status == 400, body
        assert "--by" in text_of(body)
        assert tree(root) == before


# -- the key, the cookie and the origin (ADR 0061 §4) -------------------------- #


def test_a_press_without_the_cookie_or_from_another_origin_writes_nothing(
    writing: Served,
) -> None:
    before = tree(writing.root)
    target = review_address("acme", "triage", LONG_ID)
    body = "verdict=good&by=Ada"
    assert writing.ask("POST", target, body, cookie=False).status == 403
    assert writing.ask("POST", target, body, origin="http://evil.example").status == 403
    assert writing.ask("POST", target, body, origin="null").status == 403
    assert tree(writing.root) == before


def test_a_press_with_no_verdict_writes_nothing(writing: Served) -> None:
    before = tree(writing.root)
    status, _, body = press(writing, LONG_ID, "", "Ada")
    assert status == 400, body
    assert tree(writing.root) == before


def test_the_review_index_takes_no_post(writing: Served) -> None:
    answer = writing.ask("POST", review_address("acme", "triage"), "verdict=good&by=A")
    assert answer.status == 404


def test_the_state_links_the_review_with_how_many_are_waiting(
    writing: Served,
) -> None:
    from digline.report.pages import state_address

    waiting = sum(1 for item in listing(writing.root).answers if item.electable)
    page = writing.ask("GET", state_address("acme", "triage")).body
    assert f"{waiting} not yet reviewed" in text_of(page)
    assert f'href="{review_address("acme", "triage")}?locale=' in page
    assert press(writing, LONG_ID, "good", "Ada")[0] == 303
    page = writing.ask("GET", state_address("acme", "triage")).body
    assert f"{waiting - 1} not yet reviewed" in text_of(page)


def test_the_state_and_the_review_link_each_other_in_both_locales(
    writing: Served,
) -> None:
    """The menu carries both pages on every screen, so a link found anywhere
    on the page would pass for the one in the body: each is held here by its
    own words, and the menu by its two labels, in English and in Italian."""
    from digline.report.pages import state_address

    state = state_address("acme", "triage")
    review = review_address("acme", "triage")
    waiting = sum(1 for item in listing(writing.root).answers if item.electable)
    said = {
        "en": (
            f"Review them one at a time: {waiting} not yet reviewed",
            "The state of the suite",
            ("The suite", "Review"),
            "Review — triage",
        ),
        "it": (
            f"Rivedile una alla volta: {waiting} non ancora riviste",
            "Lo stato della suite",
            ("La suite", "Revisione"),
            "Revisione — triage",
        ),
    }
    for locale, (to_review, to_state, menu, title) in said.items():
        on_state = writing.ask("GET", f"{state}?locale={locale}").body
        assert f'<a href="{review}?locale={locale}">{to_review}</a>' in on_state
        on_review = writing.ask("GET", f"{review}?locale={locale}").body
        assert f'<a href="{state}?locale={locale}">{to_state}</a>' in on_review
        assert f"<h1>{title}</h1>" in on_review
        for page in (on_state, on_review):
            for label in menu:
                assert f">{label}</a>" in page, (locale, label)
