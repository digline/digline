"""The four screens, and the route that writes where there is one.

The screens are pure functions, so they are tested as functions: no socket, no
port, no waiting. The server is tested end to end in a subprocess for the
things only a real server can show — that the routes are wired, that a POST
from another origin is refused, and that `POST /promote` is a 404 on the
default server that leaves the store where it was.

Two fixtures, because there are two servers and the default is the one that
ships: `served` is `digline view`, `served_promoting` is `digline view
--allow-promote`. A test that lands on the wrong one still passes for the
reading routes, which is why the promotion tests name the flagged fixture
explicitly rather than taking whatever the module hands them. (ADR 0032 §1)

The flagged fixture also hands over the **launch cookie** its server minted,
and every promotion test sends it unless the test is about its absence. A test
of the origin check that sent no cookie would be refused by the key instead,
and go on passing with the origin check deleted. (ADR 0033)
"""

from __future__ import annotations

import http.client
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from html import unescape
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, run_key, write_suite

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
        allow_promote=True,
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
        allow_promote=True,
    )
    assert "baseline" in html


def test_the_newest_run_is_first() -> None:
    html = runs_page(
        [("key-a", RUN_A), ("key-b", RUN_B)],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
        allow_promote=True,
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
        allow_promote=True,
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
        allow_promote=True,
    )
    assert "schema 5" in html and "migrate" in html


def test_an_empty_store_says_so_instead_of_an_empty_table() -> None:
    html = runs_page(
        [],
        baseline_key=None,
        config_hash="cfg",
        locale="en",
        suite="brief",
        allow_promote=True,
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


@contextmanager
def server(repo: Path, *flags: str) -> Generator[tuple[str, str]]:
    """A real `digline view` on an ephemeral port, over a real store.

    The bound URL is read off the startup line, which is why that line keeps
    the URL as its fourth word whichever server it is: the mode goes after it.
    What is yielded is the address without its query — on the flagged server
    the printed one carries the launch key, which `launch_of` reads.
    """
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
            *flags,
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
        yield line.split()[3].split("?")[0], line
    finally:
        process.terminate()
        process.wait(timeout=10)


def promoted(repo: Path) -> str:
    """One run promoted, and its key — the state every server test starts in."""
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    return key


@pytest.fixture
def served(repo: Path) -> Iterator[tuple[str, str]]:
    """The server a person gets by typing `digline view`: it promotes nothing.

    Every reading route is tested here rather than on the flagged server,
    because this is the one that ships as the default. (ADR 0032 §1)
    """
    key = promoted(repo)
    with server(repo) as (base, _line):
        yield base, key


def launch_of(line: str) -> str:
    """The launch key on a flagged server's startup line, or empty."""
    query = urllib.parse.urlparse(line.split()[3]).query
    return (urllib.parse.parse_qs(query).get("launch") or [""])[0]


def cookie_for(base: str, launch: str) -> str:
    """The `Cookie` header the browser sends after the hand-over."""
    port = urllib.parse.urlparse(base).port
    return f"digline-view-{port}={launch}"


@pytest.fixture
def served_promoting(repo: Path) -> Iterator[tuple[str, str, str]]:
    """`digline view --allow-promote`: the server that has the write route,
    with the `Cookie` header of the browser it was opened in."""
    key = promoted(repo)
    with server(repo, "--allow-promote") as (base, line):
        yield base, key, cookie_for(base, launch_of(line))


def baseline_of(repo: Path) -> dict[str, object]:
    path = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return document


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


def test_a_run_key_cannot_climb_out_of_the_store(
    served: tuple[str, str], repo: Path
) -> None:
    """The traversal that mattered was in the query string, not the path.

    The test above holds the *route*, and passed throughout: `/compare` is a
    real route, so the escape rode in as its argument. `?run=../../../../x`
    resolved under `.digline/<tenant>/runs/<suite>/` and, before 0.7.1, was read
    and rendered with a 200. The file planted here is a valid run document, so
    what is being tested is the boundary and not a parse failure.
    """
    base, key = served
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    (repo / "outside.json").write_text(stored.read_text(encoding="utf-8"), "utf-8")

    status, body = get(f"{base}compare?run=../../../../outside")
    assert status == 400
    assert "invalid run name" in body
    # The planted document is readable and really is a run: without this the
    # assertion above would also pass if the escape had merely failed to parse.
    assert stored.exists() and '"schema_version"' in (repo / "outside.json").read_text()


def test_a_run_that_links_out_of_the_store_is_refused_by_the_server(
    served: tuple[str, str], repo: Path
) -> None:
    """The second half of the same door. 0.7.1 checked the run *name*; a link
    planted under a legal name still reached out of the store, and this route
    rendered what it found with a 200. (0.7.2, from the adversarial pass.)"""
    base, key = served
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    outside = repo.parent / "linked.json"
    document = json.loads(stored.read_text(encoding="utf-8"))
    document["environment"] = "exfiltrated"
    outside.write_text(json.dumps(document), encoding="utf-8")
    (stored.parent / "planted-key.json").symlink_to(outside)

    status, body = get(f"{base}compare?run=planted-key")
    assert status == 400
    assert "outside" in body
    assert "exfiltrated" not in body
    # The control, in the same server: a real key still renders.
    assert get(f"{base}compare?run={key}")[0] == 200


def post(url: str, data: str, *, origin: str | None, cookie: str = "") -> int:
    return send(url, data, origin=origin, cookie=cookie)[0]


def send(
    url: str, data: str, *, origin: str | None, cookie: str = ""
) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=data.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if origin is not None:
        request.add_header("Origin", origin)
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_a_post_from_another_origin_is_refused(
    served_promoting: tuple[str, str, str],
) -> None:
    """Loopback is not a boundary: any page the developer has open can POST to
    localhost. The cookie is sent, as a browser would send it, so what refuses
    here is the origin check and not the missing key — the sentence says which.
    """
    base, key, cookie = served_promoting
    status, page = send(
        f"{base}promote", f"run={key}", origin="https://evil.example", cookie=cookie
    )
    assert status == 403
    assert "another origin" in page


def test_a_post_from_the_page_itself_is_accepted(
    served_promoting: tuple[str, str, str],
) -> None:
    base, key, cookie = served_promoting
    host = base.removeprefix("http://").rstrip("/")
    # `replacing` is the key the page was drawn against: the served baseline.
    assert (
        post(
            f"{base}promote",
            f"run={key}&replacing={key}",
            origin=f"http://{host}",
            cookie=cookie,
        )
        == 200
    )


def test_promotion_goes_through_the_same_refusals(
    repo: Path,
    served_promoting: tuple[str, str, str],
) -> None:
    """It is the same `promote_baseline`, so a run produced under another
    configuration is refused here exactly as it is on the command line."""
    base, key, cookie = served_promoting
    write_suite(repo, fr_score="0.2")
    other = run_key(repo)
    write_suite(repo)  # the configuration in force is the original one again

    host = base.removeprefix("http://").rstrip("/")
    assert (
        post(
            f"{base}promote",
            f"run={other}&replacing={key}",
            origin=f"http://{host}",
            cookie=cookie,
        )
        == 200
    )
    # The baseline did not move: the refusal is real, not cosmetic.
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    assert json.loads(baseline.read_text(encoding="utf-8"))["config_hash"] != ""


def post_page(base: str, data: str, *, cookie: str = "") -> tuple[int, str]:
    """A same-origin POST, answered with its status and page. A connection the
    server closed without answering is returned as status 0 rather than raised,
    because that is the outcome friction 59 is about."""
    host = base.removeprefix("http://").rstrip("/")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"http://{host}",
    }
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(
        f"{base}promote",
        data=data.encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except (ConnectionError, http.client.HTTPException):
        return 0, ""


def plant(repo: Path, key: str, name: str, **changes: object) -> None:
    """A run file beside the real one, differing only by `changes`."""
    runs = repo / ".digline" / "acme-bank" / "runs" / "qa"
    document = json.loads((runs / f"{key}.json").read_text(encoding="utf-8"))
    (runs / f"{name}.json").write_text(
        json.dumps({**document, **changes}), encoding="utf-8"
    )


def test_a_promotion_that_happened_says_so_when_the_list_cannot_be_drawn(
    repo: Path, served_promoting: tuple[str, str, str]
) -> None:
    """Friction 59's worst half. One unreadable run file anywhere in the store,
    and a promotion of a *good* run wrote the baseline and then answered with a
    closed connection: the list is re-read after the write, and that read raised.
    A promotion that looks failed and is not. The outcome must arrive whatever
    the list does."""
    base, key, cookie = served_promoting
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    before = json.loads(baseline.read_text(encoding="utf-8"))["promoted_at"]
    plant(repo, key, "zz-malformed", results=7)

    status, page = post_page(
        base, f"run={key}&replacing={key}&locale=en", cookie=cookie
    )

    assert status == 200
    assert f"Baseline set to {key}." in page
    assert "The list of runs could not be drawn" in page
    # And it did happen: the page is telling the truth about the write.
    assert json.loads(baseline.read_text(encoding="utf-8"))["promoted_at"] != before


def test_the_page_that_says_what_a_promotion_did_writes_no_control_character(
    repo: Path, served_promoting: tuple[str, str, str]
) -> None:
    """The fallback page — the outcome of a promotion when the list of runs
    cannot be drawn — escaped with `html.escape`, which leaves C0, C1 and the
    bidi overrides alone. A refusal quoting a committed baseline's
    `promoted_at` therefore wrote them raw: an RLO reverses the sentence that
    names which key was found. Every other page goes through `report.escape`.
    (0.20.0 delta-pass, F-2)"""
    base, key, cookie = served_promoting
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    document = json.loads(baseline.read_text(encoding="utf-8"))
    document["promoted_at"] = "\x1b[2K\r\u202eFORGED\x9bEND"
    baseline.write_text(json.dumps(document), encoding="utf-8")
    plant(repo, key, "zz-malformed", results=7)

    # `none` over a baseline that exists: refused, naming what it found.
    status, page = post_page(base, f"run={key}&replacing=none&locale=en", cookie=cookie)

    assert status == 200
    assert "The list of runs could not be drawn" in page
    assert "FORGED" in page
    for raw in ("\x1b", "\r", "\u202e", "\x9b"):
        assert raw not in page, f"{raw!r} reached the page raw"


def test_a_run_that_lies_about_its_suite_is_refused_in_words(
    repo: Path, served_promoting: tuple[str, str, str]
) -> None:
    """0.19.2 made the store refuse a document declaring another suite, and the
    route that writes never learned the refusal: the browser got a closed
    connection. v0.19.1 accepted the same POST, which is the defect 0.19.2 fixed
    — so the traceback was introduced by the fix. (friction 59)"""
    base, key, cookie = served_promoting
    plant(repo, key, "zz-other-suite", suite="another-suite")

    status, page = post_page(base, "run=zz-other-suite&replacing=" + key, cookie=cookie)

    assert status == 200
    assert "Refused:" in page
    assert "declares suite &#x27;another-suite&#x27;" in page


# --------------------------------------------------------------------------- #
# The wire half of the default refusal (ADR 0032 §§1-2)
# --------------------------------------------------------------------------- #


def test_the_default_server_has_no_promote_route_and_the_store_proves_it(
    repo: Path, served: tuple[str, str]
) -> None:
    """The half that carries the guarantee. A caller with a shell never renders
    the page, so absenting the button provides nothing on its own: the POST
    measured in ADR 0032 §*What was measured* carried no `Origin` and no
    credential of any kind, and moved the baseline.

    **The status alone would prove nothing**, which is why the baseline is read
    on both sides of it: a 404 in front of a write that happened is exactly the
    failure friction 59 was about, with the sign reversed.
    """
    base, key = served
    before = baseline_of(repo)
    write_suite(repo)
    other = run_key(repo)

    # No `Origin` — the door `_allowed_origin` deliberately leaves open for
    # curl, and the one this refusal has to hold without.
    assert post(f"{base}promote", f"run={other}&replacing={key}", origin=None) == 404
    assert baseline_of(repo) == before


def test_the_refusal_is_the_sentence_an_unknown_path_gets(
    served: tuple[str, str],
) -> None:
    """Not a 403 and not a 405. Both say *you may not*, which implies a someone
    who may, which is the policy ADR 0011 refused to create. On this server
    there is no promote, so it answers what it answers about any path it does
    not serve — in the same words, or the difference is a hint."""
    base, key = served
    host = base.removeprefix("http://").rstrip("/")
    status, page = post_page(base, f"run={key}&replacing={key}")
    assert status == 404
    assert "no such action: /promote" in page
    # The same sentence, from a path nobody ever claimed existed.
    nowhere = urllib.request.Request(
        f"{base}nowhere",
        data=b"",
        method="POST",
        headers={"Origin": f"http://{host}"},
    )
    try:
        urllib.request.urlopen(nowhere, timeout=10)
        raise AssertionError("a path this server does not serve answered 200")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
        assert "no such action: /nowhere" in exc.read().decode("utf-8")


def test_the_page_and_the_route_answer_from_one_fact(
    repo: Path, served: tuple[str, str]
) -> None:
    """A page that decided independently of the dispatcher is a page that will
    eventually show a button the route rejects. Read off one real server rather
    than from two functions, because that is where they could disagree.

    **The second run is what makes this test able to fail.** The fixture
    promotes the only run there is, so its one row is the baseline's and would
    carry a chip rather than a button on any server at all — a mutation removing
    the page's guard went green here before this line existed.
    """
    base, _key = served
    write_suite(repo)
    run_key(repo)  # a run that is not the baseline: the row a button would be on

    page = get(base)[1]
    assert 'action="/promote"' not in page
    assert "--allow-promote" in page


def test_the_flag_turns_both_halves_on_together(
    repo: Path, served_promoting: tuple[str, str, str]
) -> None:
    """The other side of the same fact, and the reason this test cannot stand
    in for the one above: it would pass unchanged on a server that promoted
    whatever it was told to."""
    base, key, cookie = served_promoting
    before = baseline_of(repo)
    write_suite(repo)
    other = run_key(repo)

    page = get(base)[1]
    assert 'action="/promote"' in page
    assert "--allow-promote" not in page

    assert (
        post(
            f"{base}promote", f"run={other}&replacing={key}", origin=None, cookie=cookie
        )
        == 200
    )
    assert baseline_of(repo) != before


def test_the_startup_line_names_the_flag_and_keeps_the_url_where_it_was(
    repo: Path,
) -> None:
    """Two places name `--allow-promote`, and this is the one a person reads
    before the page exists. The URL stays the fourth word: a caller reading the
    line for the bound port of `--port 0` should not have to parse a mood."""
    promoted(repo)
    with server(repo) as (base, line):
        assert "read-only" in line and "--allow-promote" in line
        assert line.split()[3] == base and base.startswith("http://")
    with server(repo, "--allow-promote") as (flagged, flagged_line):
        assert "read-only" not in flagged_line
        assert "promotion enabled" in flagged_line
        assert flagged_line.split()[3] == f"{flagged}?launch={launch_of(flagged_line)}"


# --------------------------------------------------------------------------- #
# The launch key: the flagged server promotes for one browser (ADR 0033)
# --------------------------------------------------------------------------- #


def test_a_shell_without_the_key_cannot_promote_on_a_flagged_server(
    repo: Path, served_promoting: tuple[str, str, str]
) -> None:
    """The measurement ADR 0033 exists for, as a test. A person starts
    `digline view --allow-promote`; any process of the same user then POSTs
    with no `Origin` — which `_allowed_origin` admits, on purpose, for `curl` —
    and before 0033 the baseline moved. The store is read on both sides, as in
    the default-server test, because a status in front of a write that happened
    is friction 59 with the sign reversed.

    And the control, in the same server: the same POST with the cookie moves
    it. Without that line a server that refused every POST would pass.
    """
    base, key, cookie = served_promoting
    before = baseline_of(repo)
    write_suite(repo)
    other = run_key(repo)

    status, page = send(f"{base}promote", f"run={other}&replacing={key}", origin=None)
    assert status == 403, "a POST with no key was not refused on the flagged server"
    assert "only from the browser" in page
    assert baseline_of(repo) == before

    forged = cookie.split("=")[0] + "=" + "x" * 43
    assert (
        post(
            f"{base}promote", f"run={other}&replacing={key}", origin=None, cookie=forged
        )
        == 403
    )
    assert baseline_of(repo) == before

    assert (
        post(
            f"{base}promote", f"run={other}&replacing={key}", origin=None, cookie=cookie
        )
        == 200
    )
    assert baseline_of(repo) != before


def test_the_refusal_on_the_flagged_server_is_a_403_not_the_404(
    served_promoting: tuple[str, str, str],
) -> None:
    """Same fact, two servers, two truthful answers. On the default server
    nobody may promote, so `/promote` is absent (404). Here somebody may — the
    person who started it — so a caller without the key is refused (403), and
    the sentence is not the unknown-path one."""
    base, key, _cookie = served_promoting
    status, page = post_page(base, f"run={key}&replacing={key}")
    assert status == 403
    assert "no such action" not in page


def test_the_printed_address_becomes_a_cookie_and_leaves_the_address(
    served_promoting: tuple[str, str, str],
) -> None:
    """The hand-over, as a browser meets it: a 303 to the same page without the
    key, and the key in an `HttpOnly`, `SameSite=Strict` cookie named for the
    port. Other parameters survive the redirect."""
    base, _key, cookie = served_promoting
    launch = cookie.split("=", 1)[1]
    parsed = urllib.parse.urlparse(base)
    connection = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=10)
    connection.request("GET", f"/?locale=it&launch={launch}")
    answer = connection.getresponse()
    answer.read()
    connection.close()

    assert answer.status == 303
    assert answer.getheader("Location") == "/?locale=it"
    set_cookie = answer.getheader("Set-Cookie") or ""
    assert set_cookie.startswith(f"{cookie};")
    assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie


def test_an_address_from_another_start_is_refused_by_name(
    served_promoting: tuple[str, str, str],
) -> None:
    """A tab left open across a restart carries the old key. It is refused in
    words that say what happened, and no cookie is set."""
    base, _key, _cookie = served_promoting
    status, page = get(f"{base}?launch=" + "y" * 43)
    assert status == 403
    assert "another start" in page


def test_no_page_the_flagged_server_renders_contains_the_key(
    repo: Path, served_promoting: tuple[str, str, str]
) -> None:
    """The half of the design that is easy to lose. Every reading route answers
    anybody with a shell, so a key written into a page — a hidden field, a link,
    a script — is handed to exactly the caller it exists to refuse. Walked over
    every route, after a promotion so the outcome page is included."""
    base, key, cookie = served_promoting
    launch = cookie.split("=", 1)[1]
    write_suite(repo)
    other = run_key(repo)
    for url in (
        base,
        f"{base}?locale=it",
        f"{base}compare?run={key}",
        f"{base}compare?run={other}&against={key}",
        f"{base}case/capital-it",
        f"{base}suspend/capital-it?reason=x",
    ):
        status, page = get(url)
        assert status == 200, url
        assert launch not in page, f"{url} rendered the launch key"
    _status, outcome = post_page(base, f"run={other}&replacing={key}", cookie=cookie)
    assert "Baseline set to" in outcome
    assert launch not in outcome


def test_the_default_server_ignores_a_launch_parameter(
    served: tuple[str, str],
) -> None:
    """On the server that does not promote there is nothing to hand over: the
    page is served and nothing is set."""
    base, _key = served
    parsed = urllib.parse.urlparse(base)
    connection = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=10)
    connection.request("GET", "/?launch=anything")
    answer = connection.getresponse()
    answer.read()
    connection.close()
    assert answer.status == 200
    assert answer.getheader("Set-Cookie") is None


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
    locale: str = "en",
    *,
    extra: Run | None = None,
    config_hash: str = "cfg",
    allow_promote: bool = True,
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
        allow_promote=allow_promote,
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
    assert ">older suite</span>" in cell
    assert "produced under an earlier version of the suite" in cell
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
        allow_promote=True,
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
        allow_promote=True,
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
        allow_promote=True,
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
        allow_promote=True,
    )
    assert '<span class="when">24 Aug 09:00:00</span>' in html


def test_minutes_are_enough_when_nothing_collides() -> None:
    html = runs_html()
    assert '<span class="when">21 Aug 10:00</span>' in html


def test_a_run_that_cannot_be_promoted_says_so_without_being_hovered() -> None:
    """A disabled radio alone was invisible in the screenshot."""
    assert "chip warn" in act_cell(runs_html(extra=ERRORED), "key-e")


# --------------------------------------------------------------------------- #
# The page half of the default refusal (ADR 0032 §§1-2)
# --------------------------------------------------------------------------- #


def test_without_the_flag_no_row_offers_to_promote() -> None:
    """The refusal is an absence: not a disabled button, not a button that
    fails on click. A control that is present and refuses teaches every reader
    that promotion is something this surface does, subject to a policy — and it
    teaches it every time the page is read."""
    html = runs_html(allow_promote=False)
    assert 'action="/promote"' not in html
    assert "<button" not in html.split("</table>")[0]
    # The control, in the same shape of page: with the flag the button is there,
    # so what the assertions above measure is the flag and not the fixture.
    assert 'action="/promote"' in runs_html(allow_promote=True)


def test_the_promotable_row_keeps_its_comparison_and_gains_nothing() -> None:
    """Nothing takes the button's place. The reason the row can do less is not
    about the row, so saying it there would be a lie about its own subject."""
    cell = act_cell(runs_html(allow_promote=False), "key-b")
    assert "Compare" in cell
    assert "chip" not in cell and "<button" not in cell


def test_the_per_run_markers_survive_a_server_that_promotes_nothing() -> None:
    """They answer *why not this run*, which goes on being true and useful when
    the server would refuse every run anyway."""
    html = runs_html(extra=ERRORED, allow_promote=False)
    assert "chip warn" in act_cell(html, "key-e")  # not judged
    assert "chip" in act_cell(html, "key-a")  # baseline


def test_the_marker_is_said_once_about_the_server_not_once_per_run() -> None:
    """Three rows, one marker. Repeated down the column it would read as three
    per-run refusals rather than one property of what the person started — and
    the header is where a fact about the server belongs."""
    body = runs_html(extra=ERRORED, allow_promote=False).split("</head>")[1]
    assert body.count('<td class="act">') == 3  # three rows really are drawn
    assert body.count('class="readonly"') == 1
    # And it is in the header, beside the suite name, not in the table.
    header, table = body.split("</nav>", 1)
    assert "readonly" in header
    assert "--allow-promote" not in table


def test_the_marker_names_the_flag_in_the_open_not_in_a_tooltip() -> None:
    """This is the whole discovery path for somebody who did not know the flag
    existed, and a hint that needs hovering was already the bug once."""
    html = runs_html(allow_promote=False)
    visible = html.split('class="readonly"')[1].split(">", 1)[1].split("</span>")[0]
    assert "--allow-promote" in visible


def test_the_flag_is_not_translated_but_the_sentence_is() -> None:
    """A flag is not localised, for the reason an ISO date is not: the sentence
    around it is the document, the eight characters are the thing to type."""
    italian = runs_html("it", allow_promote=False)
    assert "sola lettura" in italian
    assert "--allow-promote" in italian


def test_a_server_that_promotes_says_nothing_about_being_one() -> None:
    """The marker is the refusal's, and a page that carried it either way would
    be telling nobody anything."""
    body = runs_html(allow_promote=True).split("</head>")[1]
    assert "readonly" not in body and "--allow-promote" not in body
    # The stylesheet carries the rule either way, which is why the assertions
    # above read the body: a page-wide search would pass on the wrong evidence.
    assert "nav.bar .readonly" in runs_html(allow_promote=True)


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
        allow_promote=True,
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
        allow_promote=True,
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
        allow_promote=True,
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
        allow_promote=True,
    )
    # The element, not the stylesheet: `.stamp` is in the CSS on every page.
    assert '<span class="stamp"' not in html
