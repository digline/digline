"""Finding 2: `digline view`'s origin check against a rebound name.

`_allowed_origin(origin, host)` compares the `Origin` header against the `Host`
header **of the same request**. Under DNS rebinding both are chosen by the
attacker: their page is served from a name that resolves to 127.0.0.1, so it is
*same-origin with the server* and the comparison succeeds. `Host` is never
checked against loopback, which is the fact that turns the check into a
tautology.

No browser and no DNS server are needed to show it. What a rebound browser
sends is exactly a request carrying `Host: evil.example:PORT` and
`Origin: http://evil.example:PORT`, and `http.client` sends that where
`urllib.request` would overwrite `Host` with the address it dialled.

The route that writes is the one that matters, but the reading routes are the
larger loss: they hand a remote page the whole unredacted store, which is the
boundary ADR 0002 draws worlds 2 and 3 around.
"""

from __future__ import annotations

import http.client
import subprocess
import sys
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, run_key

# Private on purpose: `view.py` is transport only and its `__all__` is two
# names. The security predicate is still worth a direct test, so it is reached
# the way `test_calibration.py` and `test_journal.py` reach theirs.
from digline.cli.view import (
    _allowed_origin,  # pyright: ignore[reportPrivateUsage]
    _is_self,  # pyright: ignore[reportPrivateUsage]
    self_netlocs,
)

#: A name that is not the server's own. The port is filled in per run, because
#: `Host` has to carry the port for the comparison to be the interesting one:
#: `_allowed_origin` compares full netlocs, so a mismatch on the port would
#: refuse for a reason that has nothing to do with the name.
REBOUND = "evil.example"

#: What `view.py` says for each of the three refusals a POST can meet, in the
#: order it applies them. Asserted beside every 403 in this file, because all
#: three are 403s and a status cannot tell them apart.
HOST_REFUSED = "addressed to a name this server does not answer to"
ORIGIN_REFUSED = "this request came from another origin"
KEY_REFUSED = "promotes only from the browser that opened the address"


@pytest.fixture
def served(repo: Path) -> Iterator[tuple[int, str, str]]:
    """A real server over a real store, on an ephemeral port, with the `Cookie`
    header of the browser it was opened in.

    A subprocess rather than a handler built in-process: what is being tested is
    a header comparison made by `http.server`, and a `ViewHandler` constructed
    by hand would be a test of the function rather than of the door.

    **The cookie is sent on every POST here, and that is what keeps this file
    meaning anything.** Without it the launch key refuses first (ADR 0033), and
    each test below would go on passing with the guard it names deleted.
    """
    key = run_key(repo)
    promoted = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    assert promoted.returncode == 0, promoted.stderr

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
            # The server that *has* a write route, deliberately. This file is
            # about the `Host` and `Origin` guards on that route, and on the
            # default server the POST below would be a 404 before either guard
            # ran — including the control line that exists to prove the guard
            # can refuse. It would have passed, guarding nothing, and said so
            # nowhere: a test does not fail when it stops testing. It was moved
            # here by hand when the default changed, and that hand is the whole
            # of what caught it. That the default has no route at all is
            # `tests/test_view.py`; what this file is worth is ADR 0032 §6.
            "--allow-promote",
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
        address: str = line.split()[3]
        printed = urllib.parse.urlparse(address)
        port = printed.port
        assert port is not None, line
        launch = urllib.parse.parse_qs(printed.query)["launch"][0]
        yield port, key, f"digline-view-{port}={launch}"
    finally:
        process.terminate()
        process.wait(timeout=10)


def request(
    port: int,
    method: str,
    path: str,
    *,
    host: str,
    origin: str | None = None,
    body: str = "",
    cookie: str = "",
) -> tuple[int, str]:
    """One request with `Host` set by the caller.

    `http.client` is what makes this possible: it sends the `Host` we give it,
    where `urllib.request` derives it from the address it connected to and so
    cannot express the rebound case at all.
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    if cookie:
        headers["Cookie"] = cookie
    if body:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    connection.request(method, path, body=body, headers=headers)
    answer = connection.getresponse()
    read = answer.read().decode("utf-8")
    connection.close()
    return answer.status, read


def test_a_post_from_a_rebound_name_is_refused(
    served: tuple[int, str, str],
) -> None:
    """The write route, reached from a page the developer merely visited."""
    port, key, cookie = served
    rebound = f"{REBOUND}:{port}"

    # The control, and it is the point of the test: the check does work when the
    # attacker cannot also choose `Host`. Without this line a refusal for any
    # reason at all would read as success.
    refused, said = request(
        port,
        "POST",
        "/promote",
        host=f"127.0.0.1:{port}",
        origin=f"http://{REBOUND}",
        body=f"run={key}",
        cookie=cookie,
    )
    assert refused == 403, "the control failed: a plain cross-origin POST got through"
    assert ORIGIN_REFUSED in said, said

    status, body = request(
        port,
        "POST",
        "/promote",
        host=rebound,
        origin=f"http://{rebound}",
        body=f"run={key}",
        cookie=cookie,
    )
    assert status == 403, (
        f"a POST whose Origin and Host are both {rebound!r} was answered "
        f"{status}: the origin check compares two headers the same attacker "
        f"chose. Body: {body[:200]!r}"
    )
    # The status alone does not say which guard refused, and here that is the
    # whole question: with the `Host` check deleted this request is *still* a
    # 403, from the origin check behind it — measured, not supposed. Only the
    # sentence says the guard this test is named after is the one that held.
    assert HOST_REFUSED in body, (
        f"the rebound POST was refused, but not by the Host check: {body[:200]!r}"
    )


def test_the_same_post_from_the_server_s_own_name_is_accepted(
    served: tuple[int, str, str],
) -> None:
    """The positive control for the test above.

    Every refusal there is a 403, and so is the launch key's. Without a request
    that differs from the rebound one only in `Host` and `Origin`, and is
    accepted, a key that had stopped matching would refuse everything in that
    file and every test would stay green. Re-promoting the baseline over itself
    is a write that moves nothing, as in `test_view.py`.
    """
    port, key, cookie = served
    here = f"127.0.0.1:{port}"
    form = f"run={key}&replacing={key}&locale=en"

    status, body = request(
        port,
        "POST",
        "/promote",
        host=here,
        origin=f"http://{here}",
        body=form,
        cookie=cookie + "-not-the-key",
    )
    assert status == 403 and KEY_REFUSED in body, (
        f"the launch key's own refusal changed shape: {status} {body[:200]!r}"
    )

    status, body = request(
        port,
        "POST",
        "/promote",
        host=here,
        origin=f"http://{here}",
        body=form,
        cookie=cookie,
    )
    assert status == 200 and f"Baseline set to {key}." in body, (
        f"the legitimate POST was answered {status}: {body[:200]!r}"
    )


def test_a_get_from_a_rebound_name_does_not_serve_the_store(
    served: tuple[int, str, str],
) -> None:
    """The reading routes, which lose more than the writing one.

    A page that can read `/` has the run keys, the environments and the commit
    of every stored run — held by a party ADR 0002 exists to keep them from.
    """
    port, key, _cookie = served

    # The control: the server does answer this route, so a 403 below would mean
    # the check refused rather than that the route is missing.
    ok, page = request(port, "GET", "/", host=f"127.0.0.1:{port}")
    assert ok == 200 and key in page, "the control failed: / did not serve the store"

    status, body = request(port, "GET", "/", host=f"{REBOUND}:{port}")
    assert status != 200 or key not in body, (
        f"GET / answered {status} with the store in it for a request claiming "
        f"Host: {REBOUND}. Nothing checks Host against loopback, so a rebound "
        f"page reads {len(body)} bytes of another party's runs."
    )


# --------------------------------------------------------------------------- #
# The allowlist itself, as a function: what the fix decided, pinned
# --------------------------------------------------------------------------- #


def test_the_developer_can_type_localhost() -> None:
    """The names all reach the same socket on a loopback bind, and a browser
    sends whichever was typed. Refusing `localhost` would break the address
    most people use."""
    known = self_netlocs("127.0.0.1", 7373)
    for netloc in ("127.0.0.1:7373", "localhost:7373", "[::1]:7373"):
        assert _is_self(netloc, known, wildcard=False), netloc


def test_the_right_name_at_the_wrong_port_is_not_us() -> None:
    """A different server on the same machine. The port is in every entry of
    the set for this reason."""
    known = self_netlocs("127.0.0.1", 7373)
    assert not _is_self("localhost:9999", known, wildcard=False)
    assert not _is_self("localhost", known, wildcard=False)


def test_a_name_is_refused_even_when_bound_to_every_interface() -> None:
    """The wildcard exception admits address *literals*, which is what keeps it
    from being a hole: the attack needs a name pointed at the loopback address,
    and a literal does not resolve at all."""
    known = self_netlocs("0.0.0.0", 7373)  # noqa: S104
    assert _is_self("192.168.1.10:7373", known, wildcard=True)
    assert _is_self("127.0.0.1:7373", known, wildcard=True)
    assert not _is_self("evil.example:7373", known, wildcard=True)
    # And with a normal bind the literal of another interface is not us either.
    assert not _is_self(
        "192.168.1.10:7373", self_netlocs("127.0.0.1", 7373), wildcard=False
    )


def test_an_origin_is_checked_against_the_server_not_the_request() -> None:
    """The defect, as a unit. `_allowed_origin` no longer sees `Host` at all."""
    known = self_netlocs("127.0.0.1", 7373)
    assert _allowed_origin("", known, wildcard=False)  # curl: no Origin
    assert _allowed_origin("http://127.0.0.1:7373", known, wildcard=False)
    assert not _allowed_origin("http://evil.example:7373", known, wildcard=False)
    assert not _allowed_origin("https://evil.com", known, wildcard=False)
