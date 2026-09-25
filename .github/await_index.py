"""Wait until the index serves *these exact versions* — to this runner.

The failure this closes is a race our own ordering guarantees. `publish.yml`
uploads, and the consumers start the moment it completes: `ci.yml` on
`workflow_run: [publish] types: [completed]`, `docker-publish.yml` beside it on
the same `v*` tag. PyPI needs seconds to minutes to serve a new file at every
edge. So the first consumer to run is structurally early, and whether it goes
red is decided by scheduling rather than by anything in the tree.

**Why a wait-and-verify and not a retry**, which is the whole ruling and the
reason this file exists rather than a `--retries` on a `pip install`:

A bare retry cannot tell *not yet propagated* from *genuinely missing* — a
typo'd pin, a version that never uploaded, a project that does not exist. It
burns its budget and then fails the same way for both, so a real missing
package becomes a slow flake and the run says nothing about which it was. This
asks the one question that separates them — *is this exact file served?* — and
answers in two distinct shapes:

    /simple/digline/ lists 41 files, none at 0.13.0   → propagation, or a
                                                        version never uploaded
    /simple/digline-mcp/ answered 404 throughout      → a project that has
                                                        never been published,
                                                        or a misspelled name

The second is the shape a package **new to the index** fails in, and it is
worth naming separately: a brand-new project has no page at all, so an edge can
hold a cached 404 for the project URL — a longer-lived thing than a page that
merely has to gain a line.

**Asked of the simple index**, which is the file listing `pip` itself resolves
from, and not of `/pypi/<name>/<version>/json`. That endpoint answered 404 for
the three plugins for minutes after their upload had returned 200 and after the
simple index was already serving them; a wait built on it would have failed a
release whose packages were in fact there.

**And asked the same question `pip` asks, header for header.** On v0.15.0 this
wait, inside the build, printed `served digline==0.15.0 (after 0s)`, and `pip
install` in the same `RUN`, 1.2s later, found no such version. PyPI answers
`Vary: Accept-Encoding, Accept`, and the two requests differed in both: this
file sent no `Accept` and `identity`, `pip` sends the JSON simple API first and
`gzip, deflate`. So by protocol they were two different cached objects, and a
wait that reads one proves nothing about the other. See `PIP_HEADERS`.

**And asked from where the install will happen.** One runner's view of the
index does not prove another's: on v0.13.0 the publishing job verified its
pins and the image build, ~30s later and inside a container's own network
namespace, was still told `digline==0.13.0` did not exist. So this runs in each
consuming job, against that job's own edge, and not only in the job that
uploaded — and, for the image, **inside the Docker build itself**, beside the
`pip install` it protects. On 0.14.0 and 0.14.1 the wait on the runner passed and
`pip` inside the build was still served the previous version 16–20s later.
`docker/await_index.py` is this file, copied into the build context and held
identical by `tests/test_docker.py`.

**And it says which cache server answered, on every request.** After the
same-question fix above, v0.20.1 still printed `served digline==0.20.1 (after
0s)` and then, 1.0s later in the same `RUN`, handed `pip` a version list that
ended at 0.20.0. The variant is ruled out, so one hypothesis is left:
**per-server luck** — the two requests reaching different cache servers of the
same variant, one refreshed and one not. Deciding that needs the two requests
compared, so every request this file makes prints an `index-capture` line
naming the server, the cache state, the object and the time (see
`CAPTURE_FIELDS`), and the same line is printed for **`pip`'s own** request by
the second half of this file (see `install_pip_capture`).

It is printed on **every** observation and not only on a failure, and that is
the whole reason it costs anything. The observation that has to be compared is
the `served` one that *precedes* the failure, and at the moment it is made
nothing knows a failure is coming: a capture switched on by the failure can only
ever describe one of the two requests. So both halves are always on wherever
they run at all, and what they cost is lines.

**Measured.** The wait prints one line per pin per poll: four on a run where
the index is already ahead, forty-four on a wait like v0.20.0's (eleven polls,
four pins). `pip`'s half prints one line per project page it resolves, which for
the image's four pins is **33** — its own self-check and every transitive
dependency included, measured with pip 26.2.1 on 2026-09-25. No extra HTTP
request and no extra second of wall time on either side: both read headers off
a response that was going to be read anyway. Nothing parses these lines.

Usage:

    python .github/await_index.py digline==0.13.0 digline-anthropic==0.5.0
    python .github/await_index.py --manifest /tmp/manifest/pins.txt

    # the other half: `pip`'s request, from `pip`'s own process
    ln -s await_index.py /tmp/index_capture/sitecustomize.py
    INDEX_CAPTURE=1 PYTHONPATH=/tmp/index_capture pip install digline==0.20.1

Environment:

    INDEX           index root, default https://pypi.org (no /simple suffix)
    TIMEOUT         seconds to wait in total, default 300
    INTERVAL        seconds between polls, default 10
    INDEX_CAPTURE   set to anything non-empty to make this file, when imported
                    as `sitecustomize`, report the `/simple/` requests of the
                    process that imported it. Unset it and nothing is patched.
"""

from __future__ import annotations

import gzip
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass

INDEX = os.environ.get("INDEX", "https://pypi.org").rstrip("/")

#: `TIMEOUT` and `INTERVAL` are read in `main` and not here, because this
#: module is now imported into `pip`'s own process as `sitecustomize`. A module
#: that raises at import time over an environment variable it is not going to
#: use would turn a mistyped `TIMEOUT` into a capture that is silently off.

#: Per-request ceiling. Distinct from TIMEOUT, which bounds the whole wait: a
#: single edge hanging must not eat the budget meant for the next poll.
REQUEST_TIMEOUT = 15

#: What `pip` sends for a project page, copied from pip 25.0.1, the version in
#: the image's base (`_get_simple_response` in `pip/_internal/index/collector.py`,
#: and `DEFAULT_ACCEPT_ENCODING` in its vendored `requests`), and confirmed on
#: the wire with `http.client`'s debug output.
#:
#: `Accept` and `Accept-Encoding` are what PyPI's `Vary` names, so they decide
#: *which* cached copy answers. **`Cache-Control` is aligned too, and not
#: because it is proven to matter.** The goal is to ask **the same question**
#: `pip` asks, not a better one. `no-cache` looks stronger, and it is exactly
#: how this file came to read a copy `pip` never reads. Do not "improve" it
#: back: a wait that asks something fresher than the install is a wait that can
#: pass while the install fails. (RELEASING.md, *The index race*, v0.15.0)
PIP_HEADERS = {
    "Accept": (
        "application/vnd.pypi.simple.v1+json, "
        "application/vnd.pypi.simple.v1+html; q=0.1, text/html; q=0.01"
    ),
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "max-age=0",
}

#: The content type of a PEP 691 JSON project page, which is what `PIP_HEADERS`
#: asks for first and what PyPI answers with.
JSON_PAGE = "application/vnd.pypi.simple.v1+json"

#: The two the other copy of the same URL can arrive as: PEP 691's HTML and
#: PEP 503's plain one. Named so the capture can say *which* variant answered,
#: since that is the difference v0.15.0 turned out to be.
HTML_PAGES = ("application/vnd.pypi.simple.v1+html", "text/html")

#: The filename of every anchor on a PEP 503 page. The page is a flat list of
#: `<a href="...">filename</a>`, and the filename is what carries the version —
#: which is why this reads the text and not the href, where PyPI appends a
#: fragment hash that has nothing to do with the question.
ANCHOR = re.compile(r"<a\b[^>]*>([^<]+)</a>", re.I)


def normalize(name: str) -> str:
    """PEP 503 normalisation: the one spelling the index answers to."""
    return re.sub(r"[-_.]+", "-", name).lower()


def name_and_version(filename: str) -> tuple[str, str] | None:
    """`digline_mcp-0.1.1-py3-none-any.whl` -> `("digline-mcp", "0.1.1")`.

    The same parse as `select_unpublished.py` and `dist_manifest.py`, so the
    three agree about what a distribution file is called. Anything that is
    neither a wheel nor an sdist is not what a pin resolves to, and is skipped
    rather than guessed at.
    """
    if filename.endswith(".whl"):
        parts = filename.split("-")
        if len(parts) < 2:
            return None
        name, version = parts[0], parts[1]
    elif filename.endswith(".tar.gz"):
        stem = filename.removesuffix(".tar.gz")
        if "-" not in stem:
            return None
        name, version = stem.rsplit("-", 1)
    else:
        return None
    return normalize(name), version


def parse_pin(pin: str) -> tuple[str, str]:
    """`digline==0.13.0` -> `("digline", "0.13.0")`, or exit naming the pin."""
    name, sep, version = pin.partition("==")
    if not sep or not name.strip() or not version.strip():
        print(
            f"::error title=Not a pin::{pin!r} is not `name==version`, so there "
            "is no exact file to hold the index to.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return normalize(name.strip()), version.strip()


#: The prefix both halves of the capture print, so one `grep index-capture` on a
#: build log collects every request either of them made.
CAPTURE = "index-capture"

#: The fields, in order, and why each one is here. Written as one tuple so the
#: two halves cannot print two shapes: a reader compares two lines field by
#: field, and `tests/test_await_index.py` holds both to this order.
#:
#:   side      `wait` or `pip` — which of the two requests this is
#:   name      the project asked about
#:   t         wall clock, to the tenth of a second. Wall clock and not
#:             `monotonic`, because the two halves are two *processes* and the
#:             only thing they can both name is the time of day
#:   took      how long the round trip took, for reading `t` as a moment
#:   status    the response code, so a 404 is a record and not a silence
#:   variant   `json` or `html`: which copy of the URL answered, the thing
#:             `Vary` decides and the v0.15.0 cause
#:   serial    `X-PyPI-Last-Serial`, PyPI's own monotonic counter of the
#:             project's state. **This is the sharp one**: two responses with
#:             the same serial list the same files, and a lower serial is an
#:             older snapshot, whichever server it came from
#:   etag      the object's identity. Equal etags mean byte-identical pages, so
#:             the wait's version list *is* pip's list when they match
#:   age       `Age`, seconds the copy has been in cache. Absent from a chain
#:             that begins with a MISS, which is why a missing field is `-`
#:   cache     `X-Cache`, HIT/MISS per hop
#:   via       `X-Served-By`, the cache servers that answered, shield to edge.
#:             **This is what per-server luck is read from**: the same server
#:             with two answers refutes it, two servers confirm it
#:   versions  how many versions the page listed. `-` on pip's half: pip's body
#:             is not read (see `install_pip_capture`), and pip prints its own
#:             list when it fails
#:   asked     the pinned version this observation was about
#:   served    whether that version was in the list
CAPTURE_FIELDS = (
    "side",
    "name",
    "t",
    "took",
    "status",
    "variant",
    "serial",
    "etag",
    "age",
    "cache",
    "via",
    "versions",
    "asked",
    "served",
)


def as_field(raw: str | None) -> str:
    """One header, as a value that cannot break the line it goes on.

    Whitespace is removed rather than escaped: `X-Served-By` arrives as
    `cache-a-A, cache-b-B` and has to survive as one field. Quotes come off the
    etag for the same reason — the weak/strong distinction answers no question
    asked here. An absent or empty header is `-`, never an empty field, so that
    "the server said nothing" and "nobody looked" cannot read alike.
    """
    if raw is None:
        return "-"
    return "".join(raw.replace('"', "").split()) or "-"


def stamp(when: float) -> str:
    """A UTC timestamp to the tenth of a second, which is the resolution the
    two requests have to be told apart at: on v0.15.0 and v0.20.1 they were
    about a second apart."""
    tenth = int(when * 10) % 10
    return f"{time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(when))}.{tenth}Z"


def capture_line(**given: str) -> str:
    """One `index-capture` line. Any field not given is `-`."""
    unknown = sorted(set(given) - set(CAPTURE_FIELDS))
    if unknown:
        # Not a warning: a field nobody declared is a field nobody will read,
        # and a capture that silently drops it is worse than one that stops.
        raise ValueError(f"not a capture field: {', '.join(unknown)}")
    return f"{CAPTURE} " + " ".join(
        f"{name}={given.get(name, '-')}" for name in CAPTURE_FIELDS
    )


def variant_of(kind: str) -> str:
    """`json` or `html` — which copy of the one URL answered."""
    if kind.startswith(JSON_PAGE):
        return "json"
    if kind.startswith(HTML_PAGES):
        return "html"
    return as_field(kind)


@dataclass(frozen=True)
class Observation:
    """One request to one project page, and what answered it."""

    name: str
    at: float
    took: float
    status: int
    variant: str
    serial: str
    etag: str
    age: str
    cache: str
    via: str
    versions: frozenset[str]

    def capture(self, asked: str, *, served: bool) -> str:
        return capture_line(
            side="wait",
            name=self.name,
            t=stamp(self.at),
            took=f"{self.took:.3f}s",
            status=str(self.status),
            variant=self.variant,
            serial=self.serial,
            etag=self.etag,
            age=self.age,
            cache=self.cache,
            via=self.via,
            versions=str(len(self.versions)),
            asked=asked,
            served="yes" if served else "no",
        )


class Absent(Exception):
    """The project page did not answer 200. Carried so the final message can
    say *which* absence this is — the distinction the whole file exists for.

    It carries the `Observation` when there *was* a response, because a 404
    from a cache server is evidence about that server and throwing it away
    would lose the one shape a brand-new project fails in.
    """

    def __init__(self, message: str, observation: Observation | None = None) -> None:
        super().__init__(message)
        self.observation = observation


def observe(name: str) -> Observation:
    """Ask the index for one project page, and record what answered.

    `Cache-Control: max-age=0` is a request and not a guarantee — an
    intermediary may answer from cache anyway. That is precisely why this runs
    in the consuming job rather than only in the publishing one: the fix is to
    ask from where the install will happen, not to assume the answer travels.

    The headers are read off the response that was going to be read anyway, so
    the capture costs no request and no second of wall time — only the line it
    prints.
    """
    url = f"{INDEX}/simple/{name}/"
    request = urllib.request.Request(  # noqa: S310 - http(s) index URL, by config
        url, headers=PIP_HEADERS
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read()
            headers = response.headers
            status = int(response.status)
            encoding = (headers.get("Content-Encoding") or "").lower()
            kind = (headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        seen = seen_from(name, started, exc.headers, exc.code, frozenset())
        if exc.code == 404:
            raise Absent(f"{url} answered 404", seen) from exc
        raise Absent(f"{url} answered {exc.code}", seen) from exc
    except urllib.error.URLError as exc:
        # A DNS or TLS failure is not "the version is missing", and must not be
        # reported as one. It is still a reason to keep waiting: a runner's
        # network comes up late often enough to be worth riding out. There is
        # no response, so there is nothing to capture.
        raise Absent(f"{url} is unreachable ({exc.reason})") from exc

    versions = frozenset(
        parsed[1]
        for filename in filenames(decoded(raw, encoding), kind)
        if (parsed := name_and_version(filename)) and parsed[0] == name
    )
    return seen_from(name, started, headers, status, versions, kind=kind)


def seen_from(
    name: str,
    started: float,
    headers: http.client.HTTPMessage,
    status: int,
    versions: frozenset[str],
    *,
    kind: str = "",
) -> Observation:
    """An `Observation` from what the response carried.

    Both callers hand in an `HTTPMessage`: the response's own on a 200, and an
    `HTTPError`'s on a 404 — the error *is* the response, which is why a 404
    can be captured at all.
    """
    return Observation(
        name=name,
        at=started,
        took=time.time() - started,
        status=status,
        variant=variant_of(kind or (headers.get("Content-Type") or "").lower()),
        serial=as_field(headers.get("X-PyPI-Last-Serial")),
        etag=as_field(headers.get("ETag")),
        age=as_field(headers.get("Age")),
        cache=as_field(headers.get("X-Cache")),
        via=as_field(headers.get("X-Served-By")),
        versions=versions,
    )


def served_versions(name: str) -> set[str]:
    """Every version the index currently serves a file for, at this edge."""
    return set(observe(name).versions)


def decoded(raw: bytes, encoding: str) -> str:
    """The body, undone from the encoding `PIP_HEADERS` accepted.

    `urllib` does not decode for us, unlike `pip`'s `requests`. So asking with
    `gzip, deflate` means undoing both here. `deflate` is tried as zlib-wrapped
    first and raw second, since servers send either under that name.
    """
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.decode("utf-8", "replace")


def filenames(body: str, kind: str) -> list[str]:
    """Every distribution filename on the page, in either shape `pip` reads.

    The JSON page (PEP 691) is what PyPI answers `PIP_HEADERS` with. The HTML
    page (PEP 503) is what an index that does not speak JSON answers, and
    `pip` reads that too, so a custom `INDEX` still works.
    """
    if kind.startswith(JSON_PAGE):
        page = json.loads(body)
        return [
            str(entry["filename"])
            for entry in page.get("files", [])
            if isinstance(entry, dict) and "filename" in entry
        ]
    return [text.strip() for text in ANCHOR.findall(body)]


def main(argv: list[str]) -> int:
    timeout = float(os.environ.get("TIMEOUT", "300"))
    interval = float(os.environ.get("INTERVAL", "10"))
    pins: list[str] = []
    rest = argv[1:]
    while rest:
        argument = rest.pop(0)
        if argument == "--manifest":
            if not rest:
                print(
                    "::error title=--manifest needs a path::",
                    file=sys.stderr,
                )
                return 1
            path = rest.pop(0)
            try:
                with open(path, encoding="utf-8") as handle:
                    pins.extend(handle.read().split())
            except OSError as exc:
                print(
                    f"::error title=No manifest to read::{path}: {exc}",
                    file=sys.stderr,
                )
                return 1
        else:
            pins.append(argument)

    if not pins:
        # A check that can pass by finding nothing is the vacuously green
        # assertion `CLAUDE.md` decision 3 refuses. No pins means the caller is
        # not what it thinks it is, which is worth failing loudly for.
        print(
            "::error title=No versions to wait for::This was given no pins, so "
            "it would hold the index to nothing and pass. That is the vacuously "
            "green assertion decision 3 forbids.",
            file=sys.stderr,
        )
        return 1

    wanted = [parse_pin(pin) for pin in pins]
    print(f"the index at {INDEX} must serve, within {timeout:.0f}s:")
    for name, version in wanted:
        print(f"  {name}=={version}")

    started = time.monotonic()
    #: Why each outstanding pin is outstanding, kept so the deadline message
    #: can name the shape rather than shrug.
    why: dict[str, str] = {}
    pending = list(wanted)

    while True:
        still: list[tuple[str, str]] = []
        for name, version in pending:
            try:
                seen = observe(name)
            except Absent as absent:
                if absent.observation is not None:
                    # A 404 is an answer, and which server gave it is the whole
                    # of what the new-project shape has to be diagnosed from.
                    print(absent.observation.capture(version, served=False))
                why[f"{name}=={version}"] = (
                    f"{absent} — a project that has never been published, or a "
                    "name that is misspelled"
                )
                still.append((name, version))
                continue
            available = seen.versions
            print(seen.capture(version, served=version in available))
            if version in available:
                waited = time.monotonic() - started
                print(f"served  {name}=={version}  (after {waited:.0f}s)")
                why.pop(f"{name}=={version}", None)
            else:
                why[f"{name}=={version}"] = (
                    f"/simple/{name}/ is served and lists {len(available)} "
                    f"file version(s), none at {version}"
                )
                still.append((name, version))

        pending = still
        if not pending:
            waited = time.monotonic() - started
            print(f"\nevery version is served (after {waited:.0f}s)")
            return 0

        waited = time.monotonic() - started
        if waited + interval > timeout:
            # The deadline, and the reason this is not a retry: the message
            # names the exact pin and which absence it is, in the job that is
            # about to consume it.
            unserved = ", ".join(f"{n}=={v}" for n, v in pending)
            detail = "; ".join(
                f"{pin}: {reason}" for pin, reason in sorted(why.items())
            )
            print(
                f"::error title=The index has not served {unserved} after "
                f"{timeout:.0f}s::{detail}. This is not a slow install to retry: "
                "the index was asked for these exact files and did not list "
                "them. If a version above was never uploaded, that is the "
                "defect — do not re-run. See RELEASING.md, 'The index race'.",
                file=sys.stderr,
            )
            return 1

        for pin, reason in sorted(why.items()):
            print(f"waiting {pin}  — {reason}")
        print(f"...{waited:.0f}s elapsed; checking again in {interval:.0f}s")
        time.sleep(interval)


# --------------------------------------------------------------------------- #
# The other half of the capture: `pip`'s own request
# --------------------------------------------------------------------------- #
#
# The wait's half above can only ever describe the wait's request. The failure
# is a *disagreement* between two requests, so the second one has to be
# described too, and by the second one is meant `pip`'s own — not a replay of
# it. A replay is a third request, made after the fact, to whichever server
# happens to answer next; it cannot be either of the two under comparison.
#
# So this file is mounted a second time, as `sitecustomize.py` on `pip`'s
# `PYTHONPATH`, and `site` imports it before `pip`'s first line runs. Every
# `/simple/<name>/` page `pip` asks for then prints the same `index-capture`
# line, with `side=pip`. Nothing else about `pip` changes: no proxy, no index
# URL, no headers, no extra request — it is `pip`'s own connection, reported.
#
#: The path of a project page, in the one shape the capture is about. A file
#: download or an `/pypi/…/json` call is not the object in question and is not
#: reported: this must stay four or five lines, not one per artifact.
SIMPLE_PAGE = re.compile(r"/simple/([^/?#]+)/?$")

#: What the patch replaced, kept so it can be undone — `uninstall_pip_capture`
#: exists for the tests, which must not leave a patched `http.client` behind
#: for the rest of the suite.
_PATCHED: dict[str, object] = {}


def pip_capture_line(
    path: str, response: http.client.HTTPResponse, at: float
) -> str | None:
    """The line for one of `pip`'s requests, or `None` if it is not a page.

    **The body is not read.** Reading it would consume the stream `pip` is
    about to parse, and a diagnostic that can break an install is not one to
    put on the release path. `versions` is therefore `-` on this side, and the
    two fields that stand in for it are exact: equal `etag` means the two
    requests were handed byte-identical pages, and `serial` is PyPI's own
    counter, so a lower one on this side is an older snapshot. `pip` prints its
    own version list when it fails, which is the case that matters.
    """
    found = SIMPLE_PAGE.search(path)
    if found is None:
        return None
    headers = response.headers
    return capture_line(
        side="pip",
        name=normalize(found.group(1)),
        t=stamp(at),
        took=f"{time.time() - at:.3f}s",
        status=str(response.status),
        variant=variant_of((headers.get("Content-Type") or "").lower()),
        serial=as_field(headers.get("X-PyPI-Last-Serial")),
        etag=as_field(headers.get("ETag")),
        age=as_field(headers.get("Age")),
        cache=as_field(headers.get("X-Cache")),
        via=as_field(headers.get("X-Served-By")),
    )


def install_pip_capture() -> None:
    """Report every `/simple/` page the importing process asks for.

    `http.client.HTTPConnection` is the patch point because it is the one both
    of `pip`'s generations reach: pip 25's vendored urllib3 1.26 goes through
    the stdlib's own `request`, pip 26's urllib3 2.x calls `putrequest` and
    `getresponse` itself — and both inherit them from here. Measured against
    real `pip` and real PyPI on 2026-09-25, before this was written.

    Every capture is wrapped so that a failure inside it cannot fail an
    install. That is not defensive habit: this runs in the `RUN` that builds the
    image a release publishes, and the worst outcome available to a diagnostic
    is to become the outage it was meant to explain.
    """
    if _PATCHED:
        return
    original_putrequest = http.client.HTTPConnection.putrequest
    original_getresponse = http.client.HTTPConnection.getresponse
    _PATCHED["putrequest"] = original_putrequest
    _PATCHED["getresponse"] = original_getresponse

    def putrequest(self, method, url, *args, **rest):
        # The path and the moment, kept on the connection: `putrequest` is
        # where the URL is known and `getresponse` is where the answer is, and
        # between them a keep-alive connection serves several requests.
        try:
            self._capture_path = url
            self._capture_started = time.time()
        except Exception:
            pass
        return original_putrequest(self, method, url, *args, **rest)

    def getresponse(self):
        response = original_getresponse(self)
        try:
            path = getattr(self, "_capture_path", "")
            started = getattr(self, "_capture_started", None)
            line = pip_capture_line(
                path if isinstance(path, str) else "",
                response,
                started if isinstance(started, float) else time.time(),
            )
            if line is not None:
                print(line, flush=True)
        except Exception:
            # Never the reason an install failed.
            pass
        return response

    http.client.HTTPConnection.putrequest = putrequest
    http.client.HTTPConnection.getresponse = getresponse


def uninstall_pip_capture() -> None:
    """Put `http.client` back. For the tests, which run in one process."""
    if not _PATCHED:
        return
    http.client.HTTPConnection.putrequest = _PATCHED["putrequest"]
    http.client.HTTPConnection.getresponse = _PATCHED["getresponse"]
    _PATCHED.clear()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
# `sitecustomize` is the name `site` imports this file under when it is mounted
# as `sitecustomize.py` on `PYTHONPATH`. Checking the name rather than
# installing on every import is what keeps `tools/image_pins.py` and the tests —
# which import this module as `await_index` — from patching `http.client` behind
# their own backs.
#
# Gated on `INDEX_CAPTURE` so that a local `docker build docker/`, which waits
# for nothing, also reports nothing and behaves exactly as it did before. `site`
# catches whatever a `sitecustomize` raises and carries on with a warning, so
# the worst case here is a capture that is off — which is why
# `tests/test_docker.py` checks that the three release builds turn it on.
elif __name__ == "sitecustomize" and os.environ.get("INDEX_CAPTURE", ""):
    install_pip_capture()
