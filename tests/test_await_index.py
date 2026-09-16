"""The index wait, driven against an index that does what PyPI does.

`.github/await_index.py` closes a race our own ordering guarantees: `publish`
uploads, and the consumers start the moment it completes, while PyPI needs
seconds to minutes to serve a new file at every edge.

**The ruling it implements is wait-and-verify, not retry**, and the reason is
the one thing a test can actually prove about it. A bare retry cannot tell *not
yet propagated* from *genuinely missing*: it burns its budget and fails the
same way for both, so a real missing package becomes a slow flake. So what is
pinned here is the failure path — a version that will never exist must fail
**by name**, **within the timeout**, and must say **which** of the two absences
it is. A wait that hangs, or that passes having found nothing, would be the bug
this file exists to prevent.

The index is a local `ThreadingHTTPServer` speaking PEP 503, for two reasons:
fixed decision 5 (no network call the user has not configured — CI runs these
with no index in reach), and because the failure path cannot be produced on
purpose against the real one.

**What no test here can prove**, and it is stated rather than implied: that
PyPI's own edges converge, and that the edge `pip` reaches from inside a Docker
build is the edge this wait polled from the runner. That gap is why the wait
runs in each consuming job instead of only in the publishing one, and closing
it further needs a real publish, not a test.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "await_index.py"

#: Short enough that the failure path is a test and not a wait. The script's
#: real deadlines are minutes; what is under test is the behaviour at the
#: deadline, which is the same at two seconds as at thirty minutes.
TIMEOUT = "2"
INTERVAL = "0.4"

#: A ceiling on the subprocess itself, well above TIMEOUT. If the script ever
#: hangs instead of failing at its deadline, this is what turns that into a
#: failed test rather than a stuck suite.
HARD_LIMIT = 60


def page(files: list[str]) -> bytes:
    """A PEP 503 project page: a flat list of anchors, filename as the text."""
    links = "".join(
        f'<a href="/files/{name}#sha256=00">{name}</a><br/>' for name in files
    )
    return f"<!DOCTYPE html><html><body>{links}</body></html>".encode()


@contextmanager
def index(
    pages: dict[str, list[str]], gains: dict[str, tuple[int, str]] | None = None
) -> Generator[str]:
    """An index serving `pages`, keyed by normalised project name.

    `gains` makes a project pick up a file after N requests, which is how the
    *wait* half is driven: a page that is missing the version and then has it
    is what propagation looks like from a consumer's side.
    """
    served = {name: list(files) for name, files in pages.items()}
    counts: dict[str, int] = {}
    gaining = gains or {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            if not self.path.startswith("/simple/"):
                self.send_error(404)
                return
            name = self.path.removeprefix("/simple/").strip("/")
            counts[name] = counts.get(name, 0) + 1
            if name in gaining:
                after, filename = gaining[name]
                if counts[name] >= after:
                    served.setdefault(name, []).append(filename)
                    del gaining[name]
            if name not in served:
                self.send_error(404)
                return
            body = page(served[name])
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Silent: the suite's output is not this server's log."""

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def await_index(
    *pins: str, url: str, timeout: str = TIMEOUT
) -> tuple[subprocess.CompletedProcess[str], float]:
    """Run the script as the workflows run it, and time it."""
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *pins],
        capture_output=True,
        text=True,
        timeout=HARD_LIMIT,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "INDEX": url,
            "TIMEOUT": timeout,
            "INTERVAL": INTERVAL,
        },
    )
    return result, time.monotonic() - started


# --------------------------------------------------------------------------- #
# The failure path, which is the one this file is for
# --------------------------------------------------------------------------- #


def test_a_version_that_will_never_exist_fails_by_name_within_the_timeout() -> None:
    """The finding's own criterion, driven.

    The project is served and healthy; the version asked for is not in it and
    never will be. That must fail — not hang, not pass — and the message must
    carry the exact pin, so a reader of the red knows what was asked for.
    """
    with index({"digline": ["digline-0.13.1-py3-none-any.whl"]}) as url:
        result, elapsed = await_index("digline==99.99.99", url=url)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "digline==99.99.99" in result.stderr, result.stderr
    # Not a hang: it gave up at its own deadline, not at the test's ceiling.
    assert elapsed < HARD_LIMIT / 2, f"took {elapsed:.1f}s; the deadline was {TIMEOUT}s"


def test_the_two_absences_are_told_apart() -> None:
    """The whole difference from a retry.

    A page that is served and lists other versions is a propagation delay or a
    version that never uploaded; a page that 404s is a project that has never
    been published at all — the shape a package *new to the index* fails in.
    A retry reports both as "could not resolve".
    """
    with index({"digline": ["digline-0.13.1-py3-none-any.whl"]}) as url:
        listed, _ = await_index("digline==99.99.99", url=url)
        missing, _ = await_index("digline-nonesuch==1.0.0", url=url)

    assert "none at 99.99.99" in listed.stderr, listed.stderr
    assert "404" not in listed.stderr, (
        "a served page reported as an absent project: the two absences have "
        "stopped being distinguishable, which is the retry behaviour this "
        "replaces"
    )
    assert "never been published" in missing.stderr, missing.stderr


def test_a_genuine_absence_is_never_swallowed() -> None:
    """It fails, and it says not to re-run — the failure stays honest.

    A wait that told a reader to re-run on a real absence would be the slow
    flake the ruling refuses.
    """
    with index({"digline": ["digline-0.13.1-py3-none-any.whl"]}) as url:
        result, _ = await_index("digline==99.99.99", url=url)

    assert result.returncode == 1
    assert "do not re-run" in result.stderr.lower(), result.stderr


# --------------------------------------------------------------------------- #
# That it is a wait, and not a single look
# --------------------------------------------------------------------------- #


def test_a_served_version_passes_at_once() -> None:
    with index({"digline": ["digline-0.13.1-py3-none-any.whl"]}) as url:
        result, elapsed = await_index("digline==0.13.1", url=url)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "served" in result.stdout
    assert elapsed < float(TIMEOUT) + 5


def test_a_version_that_arrives_late_is_waited_for() -> None:
    """Propagation, from the consumer's side: absent, then there.

    This is the case the whole step exists to absorb, and the one a fail-fast
    check would turn into a red for no reason.
    """
    with index(
        {"digline": ["digline-0.13.0-py3-none-any.whl"]},
        gains={"digline": (3, "digline-0.13.1-py3-none-any.whl")},
    ) as url:
        result, elapsed = await_index("digline==0.13.1", url=url, timeout="10")

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed >= float(INTERVAL), "it cannot have polled more than once"
    assert "waiting" in result.stdout, result.stdout


def test_every_pin_must_be_served_not_merely_one() -> None:
    """The digline-openai-v0.5.0 red, as a test: the core was current and a
    plugin was not, and the wait that asked only about the core passed."""
    with index(
        {
            "digline": ["digline-0.13.1-py3-none-any.whl"],
            "digline-anthropic": ["digline_anthropic-0.4.0-py3-none-any.whl"],
        }
    ) as url:
        result, _ = await_index("digline==0.13.1", "digline-anthropic==0.5.0", url=url)

    assert result.returncode == 1
    assert "digline-anthropic==0.5.0" in result.stderr, result.stderr


# --------------------------------------------------------------------------- #
# What counts as the file being there
# --------------------------------------------------------------------------- #


def test_an_sdist_alone_counts_as_served() -> None:
    """`pip` can resolve a pin from an sdist, so the wait must not insist on a
    wheel and sit there while an installable version is already listed."""
    with index({"digline": ["digline-0.13.1.tar.gz"]}) as url:
        result, _ = await_index("digline==0.13.1", url=url)

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_underscored_wheel_name_is_matched_to_the_dashed_project() -> None:
    """A wheel writes `digline_mcp-0.1.3-…` for the project `digline-mcp`.
    Reading the filename literally would wait forever for a file that is
    already there."""
    with index({"digline-mcp": ["digline_mcp-0.1.3-py3-none-any.whl"]}) as url:
        result, _ = await_index("digline-mcp==0.1.3", url=url)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_longer_version_is_not_mistaken_for_the_one_asked_for() -> None:
    """`0.13.10` is not `0.13.1`, and a prefix match would call the wait done
    against a version nobody asked for."""
    with index({"digline": ["digline-0.13.10-py3-none-any.whl"]}) as url:
        result, _ = await_index("digline==0.13.1", url=url)

    assert result.returncode == 1, result.stdout


# --------------------------------------------------------------------------- #
# It cannot pass by finding nothing
# --------------------------------------------------------------------------- #


def test_no_pins_is_refused_rather_than_passed() -> None:
    """Decision 3, at the one place this check could go vacuously green: a
    caller whose pin list came out empty would otherwise hold the index to
    nothing and report success."""
    with index({}) as url:
        result, _ = await_index(url=url)

    assert result.returncode == 1
    assert "decision 3" in result.stderr, result.stderr


def test_a_pin_without_a_version_is_refused() -> None:
    """`digline` is not a pin. Waiting for "some version of digline" is the
    lagging-index trap that let six of eight legs install 0.7.0 and pass."""
    with index({"digline": ["digline-0.13.1-py3-none-any.whl"]}) as url:
        result, _ = await_index("digline", url=url)

    assert result.returncode == 1
    assert "not a pin" in result.stderr.lower(), result.stderr


def test_an_empty_manifest_is_refused() -> None:
    """The manifest form has the same floor as the argument form."""
    with index({}) as url:
        empty = ROOT / "tests" / "fixtures" / "empty-pins.txt"
        empty.write_text("", encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--manifest", str(empty)],
                capture_output=True,
                text=True,
                timeout=HARD_LIMIT,
                env={
                    "PATH": "/usr/bin:/bin",
                    "INDEX": url,
                    "TIMEOUT": TIMEOUT,
                    "INTERVAL": INTERVAL,
                },
            )
        finally:
            empty.unlink(missing_ok=True)

    assert result.returncode == 1
    assert "decision 3" in result.stderr, result.stderr
