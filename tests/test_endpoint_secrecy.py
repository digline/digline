"""What may be said about an endpoint, and by whom.

ADR 0005 §2 reduces a custom endpoint to its host, and 0.7.1 extended that to
`HttpTarget`, whose `url` had not been covered by it. The reduction was applied
to what **digline** says. It was not applied to what `urllib` says, and urllib
quotes the authority back: `https://svc:sk-live-…@gateway/answer` raised

    http.client.InvalidURL: nonnumeric port: 'sk-live-…@gateway'

as an **unhandled traceback** — `InvalidURL` is an `HTTPException`, not an
`OSError`, so `preflight`'s handler never saw it, and `__call__` had no handler
at all. Found by the adversarial pass over the 0.7.1 fixes, not by a report.

The four rows below are that pass's own table: the leak needed userinfo *and*
no explicit port, which is exactly the shape the docstring on `endpoint_host`
names as the one somebody really writes.
"""

from __future__ import annotations

import http.client

import pytest

from digline.run import Case
from digline.targets import HttpTarget, endpoint_host

SECRET = "sk-live-DEADBEEF"  # noqa: S105 — a fake key, and the point of the file


def a_target(url: str) -> HttpTarget:
    return HttpTarget(url=url, output_path="a", body={"q": "case.id"})


# --------------------------------------------------------------------------- #
# The four rows
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("row", "url"),
    [
        # The one that leaked: userinfo, no explicit port.
        ("user:pass@host", f"https://svc:{SECRET}@gw.invalid/answer"),
        # The same URL with a port took a different path through http.client
        # and did not leak. Pinned so the fix cannot be narrowed to the first.
        ("user:pass@host:port", f"https://svc:{SECRET}@gw.invalid:8443/answer"),
        ("user@host", "https://svc@gw.invalid/answer"),
        ("no userinfo", "https://gw.invalid/answer"),
    ],
)
@pytest.mark.parametrize("phase", ["preflight", "call"])
def test_no_endpoint_error_ever_carries_the_userinfo(
    row: str, url: str, phase: str
) -> None:
    """Both call sites, because both open a socket and both can be handed a URL
    urllib refuses to parse. `__call__` was the unguarded one."""
    target = a_target(url)
    with pytest.raises(ValueError) as caught:  # noqa: PT011 — message is the assertion
        if phase == "preflight":
            target.preflight([Case(id="c1")])
        else:
            target(Case(id="c1"))
    said = str(caught.value)
    assert SECRET not in said, f"{row} via {phase} leaked the credential: {said}"
    assert "svc" not in said or "***" in said
    # The host still gets said: the reduction is not silence.
    assert "gw.invalid" in said


def test_the_leak_row_is_the_one_urllib_raises_invalidurl_for() -> None:
    """The specific mechanism, pinned. If a future Python stops raising
    `InvalidURL` here the test above still holds, but this one says why the
    handler had to grow beyond `OSError`."""
    assert not issubclass(http.client.InvalidURL, OSError)
    assert issubclass(http.client.InvalidURL, http.client.HTTPException)


def test_the_diagnosis_survives_the_redaction() -> None:
    """ "connection refused" is the whole answer on the ordinary bad day, so the
    exception text is kept — only the known secrets are taken out of it."""
    target = a_target("http://127.0.0.1:9/answer")
    with pytest.raises(ValueError, match="nothing answered at 127.0.0.1:9"):
        target.preflight([Case(id="c1")])


# --------------------------------------------------------------------------- #
# `endpoint_host`: what is not a host has none
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "malformed",
    [
        f"not a url at all {SECRET}",
        f"http://svc:{SECRET}@",
        f"//svc:{SECRET}@",
        "http://",
        "",
    ],
)
def test_a_value_with_no_host_records_none_and_never_itself(malformed: str) -> None:
    """`urlsplit` will call anything before the first `/` a host, so this used
    to answer with the whole lowercased string — a "host" with spaces in it,
    written into every run's configuration and printed in every message."""
    assert endpoint_host(malformed) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://user:secret@gateway/v1", "gateway"),  # noqa: S105
        ("https://user:secret@gateway:8443/v1", "gateway:8443"),  # noqa: S105
        ("gateway.internal:9000", "gateway.internal:9000"),
        # Two `@` — the host is what follows the last one, per WHATWG, and the
        # first is userinfo however much it looks like a hostname.
        ("https://user:secret@evil.invalid@real.invalid/", "real.invalid"),  # noqa: S105
    ],
)
def test_the_host_is_still_reduced_correctly(url: str, expected: str) -> None:
    assert endpoint_host(url) == expected


def test_a_url_with_no_host_is_refused_rather_than_spoken() -> None:
    """The `or url` fallback is gone. It made the reduction conditional on the
    URL being well formed — the case where a mistyped secret is most likely."""
    with pytest.raises(ValueError, match="names no host") as caught:
        a_target(f"http://svc:{SECRET}@")
    assert SECRET not in str(caught.value)
