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

Usage:

    python .github/await_index.py digline==0.13.0 digline-anthropic==0.5.0
    python .github/await_index.py --manifest /tmp/manifest/pins.txt

Environment:

    INDEX      index root, default https://pypi.org (no /simple suffix)
    TIMEOUT    seconds to wait in total, default 300
    INTERVAL   seconds between polls, default 10
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.error
import urllib.request

INDEX = os.environ.get("INDEX", "https://pypi.org").rstrip("/")
TIMEOUT = float(os.environ.get("TIMEOUT", "300"))
INTERVAL = float(os.environ.get("INTERVAL", "10"))

#: Per-request ceiling. Distinct from TIMEOUT, which bounds the whole wait: a
#: single edge hanging must not eat the budget meant for the next poll.
REQUEST_TIMEOUT = 15

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


class Absent(Exception):
    """The project page did not answer 200. Carried so the final message can
    say *which* absence this is — the distinction the whole file exists for."""


def served_versions(name: str) -> set[str]:
    """Every version the index currently serves a file for, at this edge.

    `Cache-Control: no-cache` is a request and not a guarantee — an
    intermediary may answer from cache anyway. That is precisely why this runs
    in the consuming job rather than only in the publishing one: the fix is to
    ask from where the install will happen, not to assume the answer travels.
    """
    url = f"{INDEX}/simple/{name}/"
    request = urllib.request.Request(  # noqa: S310 - http(s) index URL, by config
        url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Absent(f"{url} answered 404") from exc
        raise Absent(f"{url} answered {exc.code}") from exc
    except urllib.error.URLError as exc:
        # A DNS or TLS failure is not "the version is missing", and must not be
        # reported as one. It is still a reason to keep waiting: a runner's
        # network comes up late often enough to be worth riding out.
        raise Absent(f"{url} is unreachable ({exc.reason})") from exc

    found = set()
    for filename in ANCHOR.findall(body):
        parsed = name_and_version(filename.strip())
        if parsed and parsed[0] == name:
            found.add(parsed[1])
    return found


def main(argv: list[str]) -> int:
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
    print(f"the index at {INDEX} must serve, within {TIMEOUT:.0f}s:")
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
                available = served_versions(name)
            except Absent as absent:
                why[f"{name}=={version}"] = (
                    f"{absent} — a project that has never been published, or a "
                    "name that is misspelled"
                )
                still.append((name, version))
                continue
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
        if waited + INTERVAL > TIMEOUT:
            # The deadline, and the reason this is not a retry: the message
            # names the exact pin and which absence it is, in the job that is
            # about to consume it.
            unserved = ", ".join(f"{n}=={v}" for n, v in pending)
            detail = "; ".join(
                f"{pin}: {reason}" for pin, reason in sorted(why.items())
            )
            print(
                f"::error title=The index has not served {unserved} after "
                f"{TIMEOUT:.0f}s::{detail}. This is not a slow install to retry: "
                "the index was asked for these exact files and did not list "
                "them. If a version above was never uploaded, that is the "
                "defect — do not re-run. See RELEASING.md, 'The index race'.",
                file=sys.stderr,
            )
            return 1

        for pin, reason in sorted(why.items()):
            print(f"waiting {pin}  — {reason}")
        print(f"...{waited:.0f}s elapsed; checking again in {INTERVAL:.0f}s")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
