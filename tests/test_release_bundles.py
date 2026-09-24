"""The release's signatures, driven against an index that answers like PyPI.

`.github/release_bundles.py` turns PyPI's PEP 740 attestations into the
`.sigstore.json` files attached to a GitHub release. What is pinned here is the
part that is ours: **which files it picks**, **when it refuses**, and that the
bundle is the one the reference library makes — **byte for byte the same on a
second run**, which is what makes `gh release upload --clobber` safe.

The attestations are real: PyPI's own, for `digline 0.19.1` (signed from
`refs/tags/v0.19.1`) and `digline-anthropic 0.5.3` (signed from
`refs/tags/v0.17.0`), saved under `tests/fixtures/provenance/`. The expected
bundle beside them is what `pypi_attestations.Attestation.to_bundle` produced
from the first, 0.0.30, on 2026-09-24.

**What no test here proves**: that a signature is valid. That is
`sigstore verify github --ref`, which the workflow runs on every bundle against
the served file — the script selects, the verifier proves. The served bytes
here are stand-ins with their own digests, so a signature check against them
would fail by construction and would not be a test of anything of ours.

The index is local, like `test_await_index.py`'s, for fixed decision 5 and
because the refusals cannot be produced on purpose against the real one.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "release_bundles.py"
FIXTURES = ROOT / "tests" / "fixtures" / "provenance"

CORE = "digline-0.19.1-py3-none-any.whl"
PLUGIN = "digline_anthropic-0.5.3-py3-none-any.whl"


def provenance(filename: str) -> bytes:
    return (FIXTURES / f"{filename}.provenance.json").read_bytes()


@contextmanager
def index(
    releases: dict[tuple[str, str], list[str]],
    attestations: dict[str, bytes],
    *,
    corrupt: frozenset[str] = frozenset(),
) -> Generator[str]:
    """An index serving `releases` — (name, version) to filenames — and their
    attestations by filename. A file in `corrupt` is served with bytes that do
    not match the digest its JSON page states."""

    def body(filename: str) -> bytes:
        return f"stand-in for {filename}".encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            parts = self.path.strip("/").split("/")
            if parts[0] == "pypi" and (parts[1], parts[2]) in releases:
                urls = [
                    {
                        "filename": filename,
                        "url": f"http://{self.headers['Host']}/files/{filename}",
                        "digests": {
                            "sha256": hashlib.sha256(body(filename)).hexdigest()
                        },
                    }
                    for filename in releases[(parts[1], parts[2])]
                ]
                self._send(json.dumps({"urls": urls}).encode())
            elif parts[0] == "integrity" and parts[3] in attestations:
                self._send(attestations[parts[3]])
            elif parts[0] == "files":
                data = body(parts[1])
                self._send(data + b"!" if parts[1] in corrupt else data)
            else:
                self.send_error(404)

        def _send(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def run(
    tmp_path: Path, url: str, tag: str, dist: list[str], out: str = "out"
) -> subprocess.CompletedProcess[str]:
    """The script as the workflow runs it: from a checkout with `dist/` in it."""
    (tmp_path / "dist").mkdir(exist_ok=True)
    for filename in dist:
        (tmp_path / "dist" / filename).write_bytes(b"built here, never read")
    return subprocess.run(
        [sys.executable, str(SCRIPT), tag, out],
        cwd=tmp_path,
        env={"INDEX": url, "PATH": ""},
        capture_output=True,
        text=True,
        timeout=60,
    )


BOTH = {("digline", "0.19.1"): [CORE], ("digline-anthropic", "0.5.3"): [PLUGIN]}
BOTH_SIGNED = {CORE: provenance(CORE), PLUGIN: provenance(PLUGIN)}


def test_the_tag_s_own_file_gets_the_bundle_the_reference_library_makes(
    tmp_path: Path,
) -> None:
    with index(BOTH, BOTH_SIGNED) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert result.returncode == 0, result.stderr
    written = json.loads((tmp_path / "out" / f"{CORE}.sigstore.json").read_text())
    expected = json.loads((FIXTURES / f"{CORE}.expected.sigstore.json").read_text())
    assert written == expected
    assert (
        tmp_path / "out" / "served" / CORE
    ).read_bytes() == f"stand-in for {CORE}".encode()


def test_a_file_an_earlier_tag_published_is_skipped_by_name(tmp_path: Path) -> None:
    """Every tag rebuilds every package, so `dist/` holds older plugin versions
    too. Their attestations name the tag that published them, and that is how
    they are told apart — not by a list a re-run would find empty."""
    with index(BOTH, BOTH_SIGNED) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert f"skip     {PLUGIN}  — published by refs/tags/v0.17.0" in result.stdout
    assert not (tmp_path / "out" / f"{PLUGIN}.sigstore.json").exists()
    assert sorted(p.name for p in (tmp_path / "out").glob("*.sigstore.json")) == [
        f"{CORE}.sigstore.json"
    ]


def test_the_same_input_twice_writes_the_same_bytes(tmp_path: Path) -> None:
    """What makes `--clobber` safe: a re-run replaces a bundle with itself."""
    with index(BOTH, BOTH_SIGNED) as url:
        first = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], out="first")
        second = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN], out="second")

    assert first.returncode == second.returncode == 0
    name = f"{CORE}.sigstore.json"
    assert (tmp_path / "first" / name).read_bytes() == (
        tmp_path / "second" / name
    ).read_bytes()


def test_an_empty_list_is_refused_rather_than_passed(tmp_path: Path) -> None:
    """A job that attaches nothing and passes is the check that cannot fail,
    and the release would go out unsigned with a green on it."""
    only_plugin = {("digline-anthropic", "0.5.3"): [PLUGIN]}
    with index(only_plugin, {PLUGIN: provenance(PLUGIN)}) as url:
        result = run(tmp_path, url, "v0.19.1", [PLUGIN])

    assert result.returncode == 1
    assert "no file on" in result.stderr
    assert "the check that cannot fail" in result.stderr
    assert not list((tmp_path / "out").glob("*.sigstore.json"))


def test_the_tag_s_own_version_signed_from_another_ref_is_refused(
    tmp_path: Path,
) -> None:
    """A file at the tag's own version is this tag's by construction: a foreign
    signature on it is a fault, not a skip."""
    with index({("digline", "0.19.1"): [CORE]}, {CORE: provenance(PLUGIN)}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE])

    assert result.returncode == 1
    assert (
        f"{CORE} is at the tag's own version and was signed from refs/tags/v0.17.0"
        in result.stderr
    )


def test_the_tag_s_own_version_without_an_attestation_is_refused(
    tmp_path: Path,
) -> None:
    with index({("digline", "0.19.1"): [CORE]}, {}) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE])

    assert result.returncode == 1
    assert (
        f"{CORE} is at the tag's own version and PyPI holds no attestation"
        in result.stderr
    )


def test_bytes_that_do_not_match_the_index_s_own_digest_are_refused(
    tmp_path: Path,
) -> None:
    with index(BOTH, BOTH_SIGNED, corrupt=frozenset({CORE})) as url:
        result = run(tmp_path, url, "v0.19.1", [CORE, PLUGIN])

    assert result.returncode == 1
    assert f"{CORE}: the bytes PyPI serves do not match" in result.stderr
    assert not (tmp_path / "out" / f"{CORE}.sigstore.json").exists()
