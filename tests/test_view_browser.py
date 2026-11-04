"""The page's writes as a real browser sends them. (ADR 0061 §4.3, §4.4)

`http.client` applies no `Referrer-Policy`: a test that sends `Origin` by hand
passes whatever policy the page carries, and that is how every form of
`digline view` stopped writing in a real browser without a test noticing. The
page carried `no-referrer`, and under it Chrome sends `Origin: null` on a
same-origin form POST, which the origin check refuses.

So the POSTs here are built the way the browser builds them: from the page
that carries the form, its address and the `Referrer-Policy` it was served
with, read off the response, through `AS_CHROME_156_SENDS`, the table measured
in Chrome. A policy the table does not hold fails the test rather than being
guessed. Putting `no-referrer` back makes these POSTs carry `Origin: null`,
and they are refused.

**Measured 2026-11-04, HeadlessChrome 156.0.0.0 on macOS**, by a page served
with each policy and a form posting to the same origin, the POST's headers
logged by the server:

| `Referrer-Policy` | `Origin` | `Referer` |
|---|---|---|
| `no-referrer` | `null` | absent |
| `same-origin` | the page's origin | the page's address |
| `strict-origin-when-cross-origin` | the page's origin | the page's address |
"""

from __future__ import annotations

import http.client
import json
import urllib.parse
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests._helpers import hand_over, run_key
from tests.test_view import baseline_of, launch_of, port_of, promoted, server
from tests.test_view_recorder import (
    HOURS,
    LONG_ANSWER,
    REFUND,
    SUITE,
    Served,
    opened,
    recorded,
    serving,
)

from digline.cli.view import HOST, REFERRER_POLICY
from digline.host import switch_on
from digline.host.importing import answer_id
from digline.report.pages import recorder_address, recordings_address

#: What Chrome 156 sends on a same-origin form POST, by the policy of the page
#: the form is on: `Origin` and whether `Referer` is the page's address. Read
#: from the measurement above; every other header below was in the same POST.
AS_CHROME_156_SENDS: Mapping[str, tuple[str, bool]] = {
    "no-referrer": ("null", False),
    "same-origin": ("origin", True),
    "strict-origin-when-cross-origin": ("origin", True),
}

#: The other headers of that POST, as Chrome 156 sent them. `Host`,
#: `Content-Length` and `Connection` are `http.client`'s to write.
CHROME_156_FORM_POST = {
    "Cache-Control": "max-age=0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) HeadlessChrome/156.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
}


@dataclass(frozen=True)
class Answer:
    status: int
    location: str
    body: str


def fetch(
    port: int, method: str, target: str, headers: Mapping[str, str], body: str = ""
) -> tuple[http.client.HTTPResponse, str]:
    connection = http.client.HTTPConnection(HOST, port, timeout=10)
    connection.request(method, target, body=body or None, headers=dict(headers))
    answer = connection.getresponse()
    text = answer.read().decode("utf-8")
    connection.close()
    return answer, text


def as_chrome(port: int, page: str, cookie: str, action: str, form: str) -> Answer:
    """Open `page` with `cookie`, then post `form` to `action` with the headers
    Chrome 156 sends from that page under the policy it was served with."""
    shown, _ = fetch(port, "GET", page, {"Cookie": cookie})
    assert shown.status == 200, page
    policy = shown.getheader("Referrer-Policy") or ""
    if policy not in AS_CHROME_156_SENDS:
        pytest.fail(f"Referrer-Policy {policy!r} was not measured in Chrome")
    origin, referer = AS_CHROME_156_SENDS[policy]
    address = f"http://{HOST}:{port}"
    headers = {**CHROME_156_FORM_POST, "Cookie": cookie}
    headers["Origin"] = address if origin == "origin" else origin
    if referer:
        headers["Referer"] = address + page
    answer, text = fetch(port, "POST", action, headers, form)
    return Answer(answer.status, answer.getheader("Location") or "", text)


@pytest.fixture
def browser(tmp_path: Path) -> Iterator[Served]:
    """`digline view --allow-record` over the recorder's tests' store, written
    with the real writers, its address opened in a browser."""
    recorded(tmp_path)
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "suite.py").write_text(SUITE, encoding="utf-8")
    switch_on(tmp_path, "acme", production=False, sample=0.5)
    with serving(tmp_path, allow_record=True) as (server_, launch):
        assert launch is not None
        yield opened(server_, launch)


def test_the_policy_is_the_measured_one() -> None:
    """The policy the server sends is one the table holds, and one under which
    Chrome sends the page's origin on a form it posts to itself."""
    assert REFERRER_POLICY == "same-origin"
    assert AS_CHROME_156_SENDS[REFERRER_POLICY][0] == "origin"


def test_the_import_writes_as_chrome_posts_it(browser: Served) -> None:
    page = recordings_address("acme", "triage") + "?locale=en"
    long_id = answer_id(REFUND, LONG_ANSWER)
    hours_id = answer_id(HOURS, "nine to five")
    form = urllib.parse.urlencode(
        {
            "locale": "en",
            f"answer:{long_id}": "good",
            f"answer:{hours_id}": "bad",
            "by": "Ada Lovelace",
        }
    )
    answer = as_chrome(
        browser.port, page, browser.cookie, recordings_address("acme", "triage"), form
    )
    assert answer.status == 303, answer.body
    assert answer.location == page
    written = json.loads(
        (browser.root / "suites" / "captured.json").read_text(encoding="utf-8")
    )
    assert [(case["id"], case["reviewed_answer"]["good"]) for case in written] == [
        (long_id, True),
        (hours_id, False),
    ]


def test_the_switch_goes_off_and_on_as_chrome_posts_it(browser: Served) -> None:
    page = recorder_address("acme") + "?locale=en"
    switch = browser.root / ".digline" / "acme" / "recorder.toml"
    for action, state in (("off", "on = false"), ("on", "on = true")):
        answer = as_chrome(
            browser.port,
            page,
            browser.cookie,
            recorder_address("acme"),
            f"locale=en&action={action}",
        )
        assert answer.status == 303, (action, answer.body)
        assert state in switch.read_text(encoding="utf-8"), action


def test_a_promotion_goes_through_as_chrome_posts_it(repo: Path) -> None:
    """Promotion predates the recorder's writes, and it stopped in a real
    browser too: the policy is every page's."""
    key = promoted(repo)
    newer = run_key(repo)
    before = baseline_of(repo)
    with server(repo, "--allow-promote") as (base, line):
        port = port_of(base)
        cookie = hand_over(port, launch_of(line))
        answer = as_chrome(
            port,
            "/?locale=en",
            cookie,
            "/promote",
            f"locale=en&run={newer}&replacing={key}",
        )
    assert answer.status == 200, answer.body
    assert "refused" not in answer.body
    assert baseline_of(repo) != before


def test_origin_null_is_refused_and_says_why(browser: Served) -> None:
    """`null` is what a page opened from a file, a sandboxed frame or an
    extension sends: none of them is this server's page."""
    before = (browser.root / ".digline" / "acme" / "recorder.toml").read_bytes()
    answer, text = fetch(
        browser.port,
        "POST",
        recorder_address("acme"),
        {**CHROME_156_FORM_POST, "Cookie": browser.cookie, "Origin": "null"},
        "action=off",
    )
    assert answer.status == 403
    assert "Origin is null" in text and "opened from a file" in text
    assert (browser.root / ".digline" / "acme" / "recorder.toml").read_bytes() == before


def test_another_origin_is_refused(browser: Served) -> None:
    before = (browser.root / ".digline" / "acme" / "recorder.toml").read_bytes()
    answer, text = fetch(
        browser.port,
        "POST",
        recorder_address("acme"),
        {
            **CHROME_156_FORM_POST,
            "Cookie": browser.cookie,
            "Origin": "http://evil.example",
            "Sec-Fetch-Site": "cross-site",
        },
        "action=off",
    )
    assert answer.status == 403
    assert "came from another origin" in text
    assert (browser.root / ".digline" / "acme" / "recorder.toml").read_bytes() == before
