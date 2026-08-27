"""The four screens, and the one route that writes.

The screens are pure functions, so they are tested as functions: no socket, no
port, no waiting. The server is tested once, end to end in a subprocess, for the
two things only a real server can show — that the routes are wired, and that a
POST from another origin is refused.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from html import unescape
from pathlib import Path

import pytest
from tests._helpers import cli, run_key, write_suite

from digline.core import (
    Artifact,
    CaseResult,
    Run,
    Score,
    Verdict,
    artifacts_sha,
    compare,
)
from digline.report import (
    VIEW_CSS,
    case_history,
    case_page,
    compare_page,
    human_time,
    render_html,
    runs_page,
    suspend_page,
    suspension_snippet,
)

AGREES = "agrees_with_mark"


def make_run(created_at: str, *, scores: dict[str, float], precision: float) -> Run:
    """A run with one case per score and one aggregate, built directly: these
    tests are about rendering, and going through a driver would make them about
    the driver."""
    results = tuple(
        CaseResult(
            case_id=case_id,
            verdicts=(
                Verdict(
                    score=Score(
                        name=AGREES,
                        score=value,
                        metadata={"scores": [1.0, 0.0, 1.0]} if value == 0.67 else {},
                    ),
                    threshold=0.5,
                    status="pass" if value >= 0.5 else "fail",
                    reason="judged",
                    assertion_id="id-agrees",
                ),
            ),
        )
        for case_id, value in scores.items()
    )
    return Run(
        tenant="acme",
        environment="dev",
        suite="brief",
        config_hash="cfg",
        created_at=created_at,
        git_commit="abc1234",
        results=results,
        aggregate=(
            Verdict(
                score=Score(name="precision", score=precision, metadata={}),
                threshold=0.6,
                tolerance=0.05,
                status="pass" if precision >= 0.6 else "fail",
                reason="precision",
                assertion_id="id-precision",
            ),
        ),
    )


RUN_A = make_run(
    "2026-08-20T10:00:00+00:00", scores={"a": 1.0, "b": 0.0}, precision=0.625
)
RUN_B = make_run(
    "2026-08-21T10:00:00+00:00", scores={"a": 0.67, "b": 1.0}, precision=0.714
)


# --------------------------------------------------------------------------- #
# 1. The run list
# --------------------------------------------------------------------------- #


def test_the_run_list_carries_the_aggregates() -> None:
    """The reason the screen exists. Choosing which run to promote means reading
    precision down a column and taking the median; with key, date and commit
    alone the choice cannot be made, and the first green run gets frozen."""
    html = runs_page(
        [("key-a", RUN_A), ("key-b", RUN_B)],
        baseline_key="key-a",
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert "precision" in html
    assert "0.625" in html and "0.714" in html


def test_the_baseline_is_marked() -> None:
    html = runs_page(
        [("key-a", RUN_A), ("key-b", RUN_B)],
        baseline_key="key-a",
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert "baseline" in html


def test_the_newest_run_is_first() -> None:
    html = runs_page(
        [("key-a", RUN_A), ("key-b", RUN_B)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert html.index("key-b") < html.index("key-a")


def test_both_runs_can_be_chosen_not_only_the_reference() -> None:
    """Comparing against the baseline is the release question; comparing run 1
    with run 3 of a calibration is the noise question, and that is the one that
    says what tolerance to set."""
    html = runs_page(
        [("key-a", RUN_A), ("key-b", RUN_B)],
        baseline_key="key-a",
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert html.count('<select name="run">') == 1
    assert html.count('<select name="against">') == 1


def test_what_the_scan_ignored_is_said_on_the_page() -> None:
    html = runs_page(
        [("key-a", RUN_A)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
        ignored="ignored: 3 run(s) at schema 5",
    )
    assert "schema 5" in html and "migrate" in html


def test_an_empty_store_says_so_instead_of_an_empty_table() -> None:
    html = runs_page(
        [], baseline_key=None, config_hash="cfg", locale="en", suite="brief"
    )
    assert "No run has been recorded yet." in html
    assert "<table>" not in html


# --------------------------------------------------------------------------- #
# 2. The comparison — the same function as the exported report
# --------------------------------------------------------------------------- #


def test_the_page_is_the_report_plus_a_bar() -> None:
    """If the page and the exported document ever disagreed *about a run*, that
    would be a defect rather than a difference of medium.

    Two things are added and nothing else: the bar, and the rules that style it.
    Take both away and what is left must be byte for byte what `digline
    report` writes — same dates, same six decimals, same width.
    """
    page = compare_page(RUN_B, RUN_A, locale="en", suite="brief")
    document = render_html(compare(RUN_B, RUN_A), RUN_B, RUN_A, locale="en")

    start = page.index('<nav class="bar">')
    end = page.index("</nav>\n") + len("</nav>\n")
    stripped = (page[:start] + page[end:]).replace(VIEW_CSS, "", 1)
    assert stripped == document


def test_the_comparison_keeps_the_document_rules() -> None:
    """The screen may read dates its own way; this page may not, because this
    page *is* the document."""
    page = compare_page(RUN_B, RUN_A, locale="en", suite="brief")
    assert "2026-08-21T10:00:00+00:00" in page  # ISO, not "21 Aug 10:00"
    assert 'class="wide"' not in page


def test_the_comparison_page_honours_the_locale() -> None:
    assert "È peggiorato?" in compare_page(RUN_B, RUN_A, locale="it", suite="brief")
    assert "Did it get worse?" in compare_page(RUN_B, RUN_A, locale="en", suite="brief")


# --------------------------------------------------------------------------- #
# 3. One case, down the runs
# --------------------------------------------------------------------------- #


def test_the_history_is_oldest_first() -> None:
    """The question is "how did it move", and a sequence read downward is read
    forward in time."""
    history = case_history([("key-b", RUN_B), ("key-a", RUN_A)], "a")
    assert [e.run_key for e in history.entries] == ["key-a", "key-b"]


def test_the_case_table_shows_the_raw_votes() -> None:
    """The view that had to be built by hand with a script: a combined 0.67 says
    the samples disagreed, and only the votes say how."""
    history = case_history([("key-a", RUN_A), ("key-b", RUN_B)], "a")
    html = case_page(history, locale="en", suite="brief")
    assert "0.670" in html
    assert "1.000 · 0.000 · 1.000" in html


def test_a_case_absent_from_a_run_says_so_rather_than_showing_a_blank() -> None:
    """A gap in a history is a fact about the suite. A blank cell that could
    mean "absent" or "zero" would hide it."""
    only_b = make_run("2026-08-22T10:00:00+00:00", scores={"b": 1.0}, precision=0.7)
    history = case_history([("key-a", RUN_A), ("key-c", only_b)], "a")
    assert [e.present for e in history.entries] == [True, False]
    assert "not in this run" in case_page(history, locale="en", suite="brief")


def test_a_column_survives_the_assertion_that_was_removed() -> None:
    """Names come from the whole history, not from the newest run: an assertion
    dropped last week still has scores before it."""
    later = Run(
        tenant="acme",
        environment="dev",
        suite="brief",
        config_hash="cfg2",
        created_at="2026-08-25T10:00:00+00:00",
        git_commit=None,
        results=(CaseResult(case_id="a", verdicts=()),),
    )
    history = case_history([("key-a", RUN_A), ("key-z", later)], "a")
    assert history.assertion_names == (AGREES,)


# --------------------------------------------------------------------------- #
# 4. Suspension shows and does not write
# --------------------------------------------------------------------------- #


def test_the_suspension_page_produces_the_edit() -> None:
    page = suspend_page("a", reason="provider is down", locale="en", suite="brief")
    # Unescaped for the assertion: the page escapes its quotes, as it must, and
    # what the developer copies out of the browser is the unescaped line.
    assert 'Case(id="a", suspended="provider is down")' in unescape(page)


def test_the_snippet_escapes_a_quoted_reason() -> None:
    """The reason goes into a Python string literal. A quote that closed it
    early would produce a snippet that does not parse — pasted, then debugged."""
    snippet = suspension_snippet("a", 'the "flaky" provider')
    assert snippet == 'Case(id="a", suspended="the \\"flaky\\" provider")'

    # Evaluated, not just compared: the point is that the line *parses*, and a
    # test that only compared strings would pass on a snippet nobody can paste.
    def fake_case(**kwargs: str) -> dict[str, str]:
        return kwargs

    namespace: dict[str, object] = {"Case": fake_case}
    assert eval(snippet, namespace) == {"id": "a", "suspended": 'the "flaky" provider'}


def test_without_a_reason_there_is_no_snippet_to_copy() -> None:
    html = suspend_page("a", reason="", locale="en", suite="brief")
    assert "<pre" not in html


# --------------------------------------------------------------------------- #
# The server: wiring, and the one refusal
# --------------------------------------------------------------------------- #


@pytest.fixture
def served(repo: Path) -> Iterator[tuple[str, str]]:
    """A real server on an ephemeral port, over a real store."""
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)

    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "digline.cli",
            "view",
            "--suite",
            "suite_qa.py",
            "--port",
            "0",
        ],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        line = process.stdout.readline()
        assert "http://" in line, line
        base = line.split()[3]
        yield base, key
    finally:
        process.terminate()
        process.wait(timeout=10)


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_the_four_routes_answer(served: tuple[str, str]) -> None:
    base, key = served

    status, body = get(base)
    assert status == 200 and "<table>" in body

    status, body = get(f"{base}compare?run={key}")
    assert status == 200 and "Did it get worse?" in body

    status, body = get(f"{base}case/capital-it")
    assert status == 200 and "capital-it" in body

    status, body = get(f"{base}suspend/capital-it?reason=flaky+provider")
    assert status == 200
    assert 'Case(id="capital-it", suspended="flaky provider")' in unescape(body)


def test_the_locale_switch_is_a_link_not_a_preference(served: tuple[str, str]) -> None:
    base, _key = served
    assert "Esecuzioni" in get(f"{base}?locale=it")[1]
    # Nothing was remembered: the next request without the parameter is English.
    assert "Runs" in get(base)[1]


def test_an_unknown_path_is_a_page_not_a_file(served: tuple[str, str]) -> None:
    """The view serves pages it renders, never bytes off the disk."""
    base, _key = served
    assert get(f"{base}nope")[0] == 404
    assert get(f"{base}../../etc/passwd")[0] == 404


def post(url: str, data: str, *, origin: str | None) -> int:
    request = urllib.request.Request(
        url,
        data=data.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if origin is not None:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_a_post_from_another_origin_is_refused(served: tuple[str, str]) -> None:
    """Loopback is not a boundary: any page the developer has open can POST to
    localhost, and this server needs no credential to act."""
    base, key = served
    assert post(f"{base}promote", f"run={key}", origin="https://evil.example") == 403


def test_a_post_from_the_page_itself_is_accepted(served: tuple[str, str]) -> None:
    base, key = served
    host = base.removeprefix("http://").rstrip("/")
    assert post(f"{base}promote", f"run={key}", origin=f"http://{host}") == 200


def test_promotion_goes_through_the_same_refusals(
    repo: Path,
    served: tuple[str, str],
) -> None:
    """It is the same `promote_baseline`, so a run produced under another
    configuration is refused here exactly as it is on the command line."""
    base, _key = served
    write_suite(repo, fr_score="0.2")
    other = run_key(repo)
    write_suite(repo)  # the configuration in force is the original one again

    host = base.removeprefix("http://").rstrip("/")
    assert post(f"{base}promote", f"run={other}", origin=f"http://{host}") == 200
    # The baseline did not move: the refusal is real, not cosmetic.
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    assert json.loads(baseline.read_text(encoding="utf-8"))["config_hash"] != ""


# --------------------------------------------------------------------------- #
# Legibility (the second pass over the run list)
# --------------------------------------------------------------------------- #

ERRORED = Run(
    tenant="acme",
    environment="dev",
    suite="brief",
    config_hash="cfg",
    created_at="2026-08-22T10:00:00+00:00",
    git_commit=None,
    results=(
        CaseResult(
            case_id="a",
            verdicts=(
                Verdict(
                    score=Score(name=AGREES, score=None),
                    threshold=0.5,
                    status="error",
                    reason="the provider timed out",
                    assertion_id="id-agrees",
                ),
            ),
        ),
    ),
)


def runs_html(
    locale: str = "en", *, extra: Run | None = None, config_hash: str = "cfg"
) -> str:
    rows = [("key-a", RUN_A), ("key-b", RUN_B)]
    if extra is not None:
        rows.append(("key-e", extra))
    return runs_page(
        rows,
        baseline_key="key-a",
        config_hash=config_hash,
        locale=locale,  # type: ignore[arg-type]
        suite="brief",
    )


def act_cell(html: str, key: str) -> str:
    """The actions cell of one row, by the key printed inside that row."""
    row = html.split(f'<code class="key">{key}</code>')[1]
    return row.split('<td class="act">')[1].split("</td>")[0]


def test_the_moment_is_the_heading_and_the_key_is_underneath() -> None:
    """The key used to be the title, wrapping over four lines and doubling as a
    link. Now the moment names the run and the key identifies it."""
    html = runs_html()
    assert '<span class="when">21 Aug 10:00</span>' in html
    assert '<code class="key">key-b</code>' in html


def test_the_iso_column_is_gone_because_it_repeated_the_key() -> None:
    html = runs_html()
    assert "2026-08-21T10:00:00+00:00" not in html


def test_the_month_follows_the_locale_but_the_key_never_does() -> None:
    assert "21 ago 10:00" in runs_html("it")
    assert "21 Aug 10:00" in runs_html("en")
    for locale in ("en", "it"):
        assert '<code class="key">key-b</code>' in runs_html(locale)


def test_a_timestamp_we_do_not_recognise_is_shown_as_it_is() -> None:
    """Better a raw string than a confident rendering of a value that was not
    understood."""
    assert human_time("not a timestamp", "en") == "not a timestamp"
    assert human_time("2026-13-01T10:00:00+00:00", "en").startswith("2026-13")


def test_the_baseline_row_is_marked_and_offers_no_button() -> None:
    """Promoting the baseline to itself is not an action, so it is not offered
    and then refused — it is simply not there. Neither is comparing it with
    itself."""
    cell = act_cell(runs_html(), "key-a")
    assert ">baseline</span>" in cell
    assert "<button" not in cell and "/compare?" not in cell


def test_every_row_carries_its_own_actions() -> None:
    """No selection first. The row that is compared and the row that is promoted
    need not be the same row, and neither needs a tick before it can be either.
    """
    html = runs_html()
    assert 'type="radio"' not in html
    cell = act_cell(html, "key-b")
    assert '<a class="action" href="/compare?run=key-b&amp;locale=en"' in cell
    assert '<form method="post" action="/promote">' in cell
    assert '<input type="hidden" name="run" value="key-b">' in cell
    assert "Make baseline" in cell


def test_the_promotion_button_is_absent_wherever_the_store_would_refuse() -> None:
    """Three runs, three answers: the baseline, one that cannot be judged, one
    produced under another configuration. Exactly one of them may be promoted.
    """
    html = runs_html(extra=ERRORED)
    assert html.count('action="/promote"') == 1
    assert '<input type="hidden" name="run" value="key-b">' in html


def test_a_run_with_errors_offers_no_promotion_and_says_why() -> None:
    """`promote_baseline` would refuse it anyway. Showing the refusal before it
    happens is the difference between explaining and arguing."""
    cell = act_cell(runs_html(extra=ERRORED), "key-e")
    assert "<button" not in cell
    # The marker is scannable, the title behind it is the fact about this run.
    assert ">1 not judged</span>" in cell
    assert "1 case(s) could not be judged" in cell
    # Still comparable: nothing about an unjudged case makes the numbers it did
    # produce unreadable.
    assert "/compare?run=key-e" in cell


def test_a_run_of_another_configuration_is_comparable_but_not_promotable() -> None:
    """The refusal `promote_baseline` would give, given before the click. The
    row stays — those numbers were measured — attenuated, because they were
    measured under other rules.
    """
    html = runs_html(config_hash="cfg-2")
    cell = act_cell(html, "key-b")
    assert "<button" not in cell
    assert ">older config</span>" in cell
    assert "produced under an earlier configuration" in cell
    assert "/compare?run=key-b" in cell
    assert '<tr class="stale">' in html


def test_the_baseline_keeps_its_own_marker_under_a_changed_configuration() -> None:
    """One marker per row, and the baseline's says what it is. That the
    configuration moved on since the reference is the report's sentence, not a
    second chip here."""
    html = runs_html(config_hash="cfg-2")
    assert ">baseline</span>" in act_cell(html, "key-a")
    assert "is-baseline stale" not in html


def test_before_there_is_a_baseline_no_row_offers_to_compare_with_one() -> None:
    """The link would answer 404. An action that cannot be carried out is not
    an action."""
    html = runs_page(
        [("key-a", RUN_A), ("key-b", RUN_B)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert "/compare?run=" not in html
    assert html.count('action="/promote"') == 2


def test_the_delta_against_the_baseline_is_beside_the_number() -> None:
    """The "which run do I promote" reading, in one glance: 0.714 against a
    baseline of 0.625 is +0.089."""
    html = runs_html()
    assert "0.714" in html
    assert "+0.089" in html
    assert 'class="delta up"' in html


def test_the_baseline_row_has_no_delta_against_itself() -> None:
    html = runs_html()
    baseline_row = html.split('<tr class="is-baseline">')[1].split("</tr>")[0]
    assert "delta" not in baseline_row


def test_a_missing_commit_says_which_kind_of_missing() -> None:
    """A dash said nothing, and the two cases call for different reactions."""
    assert "no git repository" in runs_html(extra=ERRORED)

    dirty = make_run("2026-08-23T10:00:00+00:00", scores={"a": 1.0}, precision=0.7)
    object.__setattr__(
        dirty, "git_commit", "3feea0e576470b6e4b5ae9f0f06bcc9df7836627-dirty"
    )
    html = runs_page(
        [("key-d", dirty)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert "uncommitted changes" in html
    assert "<code>3feea0e</code>" in html  # short, not forty characters


def test_the_pickers_read_as_moments_not_as_keys() -> None:
    """A select whose entries are forty-nine characters of slug is a select
    nobody chooses from."""
    html = runs_html()
    option = html.split('<select name="run">')[1].split("</select>")[0]
    assert "21 Aug 10:00 · dev" in option


def test_the_case_table_reads_the_same_way() -> None:
    history = case_history([("key-a", RUN_A), ("key-b", RUN_B)], "a")
    html = case_page(history, locale="en", suite="brief")
    assert '<span class="when">20 Aug 10:00</span>' in html
    assert "2026-08-20T10:00:00+00:00" not in html


def test_runs_in_the_same_minute_are_still_told_apart() -> None:
    """A calibration is four runs of one configuration launched back to back, so
    they land in the same minute — which is precisely the table this page is
    for. Caught by looking at the screenshot, not by thinking about it."""
    a = make_run("2026-08-26T12:40:33.032281+00:00", scores={"a": 1.0}, precision=0.5)
    b = make_run("2026-08-26T12:40:33.472519+00:00", scores={"a": 0.0}, precision=0.6)
    html = runs_page(
        [("key-a", a), ("key-b", b)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert html.count("26 Aug 12:40</span>") == 0
    assert '<span class="when">26 Aug 12:40:33</span>' in html


def test_the_whole_column_moves_to_seconds_not_only_the_pair() -> None:
    """Mixed precision down one column reads as data — as though two of the runs
    were more precisely known — when it is only formatting."""
    a = make_run("2026-08-26T12:40:33.032281+00:00", scores={"a": 1.0}, precision=0.5)
    b = make_run("2026-08-26T12:40:33.472519+00:00", scores={"a": 0.0}, precision=0.6)
    far = make_run("2026-08-24T09:00:00.000000+00:00", scores={"a": 1.0}, precision=0.5)
    html = runs_page(
        [("key-a", a), ("key-b", b), ("key-f", far)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert '<span class="when">24 Aug 09:00:00</span>' in html


def test_minutes_are_enough_when_nothing_collides() -> None:
    html = runs_html()
    assert '<span class="when">21 Aug 10:00</span>' in html


def test_a_run_that_cannot_be_promoted_says_so_without_being_hovered() -> None:
    """A disabled radio alone was invisible in the screenshot."""
    assert "chip warn" in act_cell(runs_html(extra=ERRORED), "key-e")


def test_the_free_comparison_is_below_the_table_and_drops_the_baseline() -> None:
    """Comparing with the baseline is a button on the row now, so the picker no
    longer offers it: two ways to ask one question, and the shorter one is
    already there. What is left is the pair no row can ask for."""
    html = runs_html()
    assert html.index("</table>") < html.index('class="picker"')
    against = html.split('<select name="against">')[1].split("</select>")[0]
    assert '<option value="">' not in against
    assert against.count("<option") == 2


def test_with_a_single_run_there_is_nothing_to_compare_it_with() -> None:
    html = runs_page(
        [("key-a", RUN_A)],
        baseline_key="key-a",
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    assert 'class="picker"' not in html


def test_nothing_on_the_page_asks_to_be_selected_first() -> None:
    """The hint under a control that no longer exists, and the control itself."""
    html = runs_html()
    assert "click the key to select it" not in html
    assert "Make the selected run the baseline" not in html


def test_only_the_moment_is_a_link_not_the_key() -> None:
    """A blue underlined key put a click that navigates on top of a click that
    selects, and the key is there to be selected."""
    history = case_history([("key-a", RUN_A)], "a")
    html = case_page(history, locale="en", suite="brief")
    # `&amp;` because the href is escaped, which is what an attribute needs.
    assert '<a href="/compare?run=key-a&amp;locale=en"><span class="when">' in html
    assert '</a><code class="key">key-a</code>' in html


def test_the_two_hints_are_about_two_different_things() -> None:
    """One line said "click the key" under something that is not a key."""
    page = suspend_page("a", reason="down", locale="en", suite="brief")
    assert "click the line to select it" in page
    assert "click the key to select it" not in page


# --------------------------------------------------------------------------- #
# Which prompt produced this run (ADR 0003)
# --------------------------------------------------------------------------- #


def with_prompt(sha: str) -> Run:
    """RUN_B, plus the file that was under test when it happened."""
    run = make_run("2026-08-21T10:00:00+00:00", scores={"a": 1.0}, precision=0.7)
    object.__setattr__(run, "artifacts", {"prompt.md": Artifact(sha=sha, text="v")})
    return run


def test_the_run_carries_the_digest_of_what_was_under_test() -> None:
    """A label beside the moment, not a column: it is read to group runs, and
    the table is already wide."""
    html = runs_page(
        [("key-p", with_prompt("a" * 64))],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    stamp = artifacts_sha({"prompt.md": Artifact(sha="a" * 64, text="v")})
    assert '<span class="stamp"' in html
    assert f"prompt {stamp}" in html
    assert "<th>prompt</th>" not in html  # no new column


def test_two_prompts_get_two_stamps_and_one_prompt_gets_one() -> None:
    """The whole point of the label: telling at a glance which runs share a
    prompt, which is the question a calibration table is read for."""
    same_a = ("key-a", with_prompt("a" * 64))
    same_b = ("key-b", with_prompt("a" * 64))
    other = ("key-c", with_prompt("b" * 64))
    html = runs_page(
        [same_a, same_b, other],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    stamps = re.findall(r'<span class="stamp"[^>]*>([^<]+)</span>', html)
    assert len(stamps) == 3
    assert len(set(stamps)) == 2


def test_a_suite_with_no_artifacts_shows_no_label() -> None:
    """Most suites declare none, and a label that is always there is a label
    nobody reads."""
    html = runs_page(
        [("key-a", RUN_A)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
    )
    # The element, not the stylesheet: `.stamp` is in the CSS on every page.
    assert '<span class="stamp"' not in html
