"""digline-mcp's entry on the official MCP registry, published by the tag.

Until this file the entry was a person's step after the release, and nothing
noticed when it was skipped: `server.json` would say 0.6.0 and the registry
would go on serving 0.5.0. The `mcp-registry` job in `publish.yml` runs it in
three steps, each a subcommand:

    plan        does the registry already hold this version? If so, nothing to
                do: a tag that does not release digline-mcp, or a re-run, ends
                green here. Before asking, `server.json` is held to `dist/`.
    await-pypi  wait until PyPI serves the version on the page the registry
                reads, `/pypi/digline-mcp/<version>/json`, with the `mcp-name`
                line in its description.
    publish     `mcp-publisher publish`, retried only on the registry's own 404
                from PyPI, recognised by its exact text (see `RETRYABLE`).

**Why a wait and then a retry, both.** The registry validates an entry by one
GET on that JSON page, with no retry of its own, and refuses on a 404. That page
answered 404 behind `/simple/` on v0.22.0 and v0.23.0, so the `pypi` job's wait
(`await_index.py`, on `/simple/`) does not cover it. The wait here proves the
version exists, read from this runner. It cannot prove what the registry reads
from its own network — the lesson `await_index.py` records for the image build
— so the publish may still meet a 404, and only that 404 earns another try:
after the wait it can only be propagation. Any other refusal is red at once.

Exit codes: 0 done, 1 refused, 2 not judged (the registry or PyPI never
answered: nothing was learned, and the remedy is a re-run).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from release_bundles import INDEX, Index, NotJudged, Refused, name_and_version

MANIFEST = pathlib.Path("packages/digline-mcp/server.json")
REGISTRY = os.environ.get(
    "REGISTRY", "https://registry.modelcontextprotocol.io"
).rstrip("/")

#: The `mcp-publisher` release whose error texts `RETRYABLE` quotes.
#: `publish.yml` installs this version by name and digest, and
#: `tests/test_mcp_registry.py` fails if the two differ: moving the pin moves
#: this line, and moving this line means re-reading the texts below.
PUBLISHER_VERSION = "1.8.1"


def retryable(identifier: str, version: str) -> tuple[str, ...]:
    """The registry's errors for a version PyPI did not serve it, and no other.

    Quoted from `internal/validators/registries/pypi.go`, `pypiVersion404Error`,
    at v1.8.1 — read from the source, not inferred from an observed failure.
    **On any change of `PUBLISHER_VERSION`, re-read that function at the new
    tag and update these.** A text that drifts is not recognised, and an
    unrecognised error is red: the drift fails loudly, never as a silent retry.
    The registry serves the error and the CLI prints it, so strictly it is the
    registry's deployment that has to match; the pin is the version we can name.

    Two of the function's four texts. Left out on purpose: *package not found*,
    which says digline-mcp does not exist on PyPI, and the fallback *version
    not found* that it reaches when PyPI's package page answered something it
    could not classify. Both are worth a person reading them.
    """
    return (
        f"PyPI package '{identifier}' exists, but version '{version}' "
        "was not found (status: 404)",
        f"PyPI could not confirm package '{identifier}' version '{version}' "
        "(version status: 404, package check inconclusive)",
    )


def manifest() -> tuple[str, str, str]:
    """`server.json`'s name, version and PyPI identifier, held to each other."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    (package,) = data["packages"]
    if package["registryType"] != "pypi":
        raise Refused(f"{MANIFEST} names a {package['registryType']} package, not pypi")
    if package["version"] != data["version"]:
        raise Refused(
            f"{MANIFEST} says {data['version']} and its package says "
            f"{package['version']}"
        )
    return data["name"], data["version"], package["identifier"]


def built(identifier: str) -> set[str]:
    """The versions of `identifier` this tag built."""
    return {
        version
        for name, version in (
            name_and_version(p)
            for p in pathlib.Path("dist").iterdir()
            if p.suffix in {".whl", ".gz"}
        )
        if name == identifier
    }


def has_mcp_name(description: str, server: str) -> bool:
    """The registry's own test for the ownership line, `containsMCPNameToken`
    in `mcpname.go` at v1.8.1: the token, then the end, a character that
    cannot continue a server name, or an HTML comment's close."""
    token = f"mcp-name: {server}"
    start = 0
    while (at := description.find(token, start)) >= 0:
        rest = description[at + len(token) :]
        if (
            not rest
            or not (rest[0].isascii() and (rest[0].isalnum() or rest[0] in "._-/"))
            or rest.startswith(("-->", "--!>"))
        ):
            return True
        start = at + 1
    return False


def output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in values.items())


def plan() -> int:
    server, version, identifier = manifest()
    versions = built(identifier)
    if versions != {version}:
        raise Refused(
            f"{MANIFEST} says {version} and dist/ holds {identifier} at "
            f"{sorted(versions) or 'no version'}: the manifest would describe "
            "a release this tag did not make"
        )
    url = (
        f"{REGISTRY}/v0.1/servers/{urllib.parse.quote(server, safe='')}"
        f"/versions/{urllib.parse.quote(version, safe='')}"
    )
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            held = json.loads(response.read())["server"]["version"]
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise NotJudged(f"{url} answered {exc.code}") from exc
        print(f"publish  {server} {version}: the registry does not hold it")
        output(publish="true", version=version)
        return 0
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise NotJudged(f"{url} did not answer: {exc}") from exc
    if held != version:
        raise Refused(f"{url} answered with version {held}")
    print(f"skip     {server} {version}: the registry already holds it")
    output(publish="false", version=version)
    return 0


def await_pypi() -> int:
    server, version, identifier = manifest()
    index = Index(
        timeout=float(os.environ.get("TIMEOUT", "600")),
        interval=float(os.environ.get("INTERVAL", "10")),
    )
    page = index.answer(f"{INDEX}/pypi/{identifier}/{version}/json")
    if page is None:
        raise Refused(
            f"{INDEX} answered 404 for {identifier} {version} until the last "
            f"read, {index.timeout:.0f}s after the first: this runs after the "
            "upload, so the version is not there"
        )
    if not has_mcp_name(json.loads(page)["info"]["description"] or "", server):
        raise Refused(
            f"{identifier} {version} is on {INDEX} without 'mcp-name: {server}' "
            "in its description, and the registry would refuse it. The version "
            "is spent: the fix is in the README, released as the next version"
        )
    print(f"served   {identifier} {version}, with its mcp-name line")
    return 0


def publish(publisher: str) -> int:
    _, version, identifier = manifest()
    attempts = int(os.environ.get("ATTEMPTS", "3"))
    pause = float(os.environ.get("PAUSE", "30"))
    texts = retryable(identifier, version)
    for attempt in range(1, attempts + 1):
        done = subprocess.run(
            [publisher, "publish"],
            cwd=MANIFEST.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        print(done.stdout, end="")
        if done.returncode == 0:
            return 0
        if not any(text in done.stdout for text in texts):
            raise Refused(
                "mcp-publisher refused, and not with the registry's 404 from "
                "PyPI, which is the one error retried here. Read the output "
                "above"
            )
        if attempt < attempts:
            print(
                f"the registry read a 404 from PyPI; try {attempt + 1} in {pause:.0f}s"
            )
            time.sleep(pause)
    raise Refused(
        f"the registry read a 404 from PyPI on all {attempts} tries, after this "
        "runner had read the same page served. Nothing is lost: re-run the job"
    )


if __name__ == "__main__":
    try:
        match sys.argv[1:]:
            case ["plan"]:
                code = plan()
            case ["await-pypi"]:
                code = await_pypi()
            case ["publish", publisher]:
                code = publish(publisher)
            case _:
                sys.exit("usage: mcp_registry.py plan | await-pypi | publish PUBLISHER")
        sys.exit(code)
    except Refused as exc:
        print(
            f"::error title=digline-mcp not published to the MCP registry::{exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except NotJudged as exc:
        print(f"::error title=MCP registry step not judged::{exc}", file=sys.stderr)
        sys.exit(2)
