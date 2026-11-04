"""A view another package adds to `digline view` (ADR 0061 §5).

The package is real as far as `importlib.metadata` can tell: a `.dist-info`
directory with an `entry_points.txt`, and a module beside it, on `sys.path`.
Nothing is installed, and nothing digline ships is replaced to make it appear,
so what is read is what an installed package would give.
"""

from __future__ import annotations

import http.client
import importlib
import os
import subprocess
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from html import unescape
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from tests.test_view import promoted, server
from tests.test_view_policy import inline_in

from digline.cli import EXIT_USAGE
from digline.cli.view import ViewHandler, installed_extensions, self_netlocs
from digline.core import RefusedError
from digline.host import load_suite
from digline.store import FileResultStore

PACKAGE = "acme-digline-views"

#: The module the fake package's views live in. `{marker}` is a file each test
#: names, written when the module is imported, so a test can tell whether the
#: server imported it — the menu must not.
MODULE = """\
from pathlib import Path

from digline.report import escape

Path({marker!r}).write_text("imported", encoding="utf-8")


class Drift:
    def render(self, context):
        return (
            "<h1>Latency drift</h1>"
            f"<p class=\\"locale\\">{{escape(context.locale)}}</p>"
            f"<p class=\\"root\\">{{escape(context.root)}}</p>"
            f"<p class=\\"query\\">{{escape(','.join(context.query.get('n', [])))}}</p>"
        )


class Broken:
    def render(self, context):
        raise RuntimeError("the secret the view held")


class NoRender:
    pass


DRIFT = Drift()
BROKEN = Broken()
NO_RENDER = NoRender()
"""


def install(
    where: Path,
    module: str,
    views: dict[str, str],
    *,
    package: str = PACKAGE,
    marker: Path | None = None,
) -> None:
    """A package `package` declaring `views` (name to attribute of `module`)
    in `digline.views`, written under `where`."""
    dist = where / f"{package.replace('-', '_')}-1.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {package}\nVersion: 1.0\n", encoding="utf-8"
    )
    lines = "".join(f"{name} = {module}:{attr}\n" for name, attr in views.items())
    (dist / "entry_points.txt").write_text(
        f"[digline.views]\n{lines}", encoding="utf-8"
    )
    source = where / f"{module}.py"
    if not source.exists():
        marked = marker if marker is not None else where / f"{module}.imported"
        source.write_text(MODULE.format(marker=str(marked)), encoding="utf-8")


@pytest.fixture
def packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory on `sys.path` for fake packages, with a module name of its
    own per test, so no test reads another's module out of `sys.modules`."""
    where = tmp_path / "site"
    where.mkdir()
    monkeypatch.setattr(sys, "path", [str(where), *sys.path])
    importlib.invalidate_caches()
    return where


def module_name(tmp_path: Path) -> str:
    return f"acme_views_{abs(hash(tmp_path)) % 10**9}"


@contextmanager
def in_process(repo: Path) -> Generator[int]:
    """The server `serve()` builds, in this process, so a test reads its
    standard error and its imports."""
    suite, _loaded = load_suite(str(repo / "suite_qa.py"), root=repo)
    known: set[str] = set()
    handler = partial(
        ViewHandler,
        suite=suite,
        store=FileResultStore(repo),
        known=known,
        extensions=installed_extensions(),
        root=str(repo),
    )
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as httpd:  # pyright: ignore[reportArgumentType]
        port = int(httpd.server_address[1])
        known.update(self_netlocs("127.0.0.1", port))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield port
        finally:
            httpd.shutdown()
            thread.join(timeout=10)


def request(port: int, method: str, target: str) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Length": "0"} if method == "POST" else {}
    connection.request(
        method, target, body=b"" if method == "POST" else None, headers=headers
    )
    answer = connection.getresponse()
    body = answer.read().decode("utf-8")
    connection.close()
    return answer.status, body


# --------------------------------------------------------------------------- #
# What the server reads when it starts
# --------------------------------------------------------------------------- #


def test_a_declared_view_is_found_by_name_without_importing_it(
    packages: Path, tmp_path: Path
) -> None:
    module = module_name(tmp_path)
    marker = tmp_path / "imported"
    install(packages, module, {"latency-drift": "DRIFT"}, marker=marker)
    found = installed_extensions()
    assert found["latency-drift"].package == PACKAGE
    assert not marker.exists(), "reading the names imported the package"
    assert module not in sys.modules


def test_a_name_that_is_not_an_address_is_refused_by_name(
    packages: Path, tmp_path: Path
) -> None:
    install(packages, module_name(tmp_path), {"Latency_Drift": "DRIFT"})
    with pytest.raises(RefusedError) as refused:
        installed_extensions()
    assert "'Latency_Drift'" in str(refused.value)
    assert PACKAGE in str(refused.value)


def test_two_packages_with_one_name_are_both_named(
    packages: Path, tmp_path: Path
) -> None:
    module = module_name(tmp_path)
    install(packages, module, {"latency-drift": "DRIFT"})
    install(packages, module, {"latency-drift": "DRIFT"}, package="other-views")
    with pytest.raises(RefusedError) as refused:
        installed_extensions()
    assert PACKAGE in str(refused.value) and "other-views" in str(refused.value)


def test_the_server_does_not_start_over_a_view_it_cannot_serve(
    repo: Path, packages: Path, tmp_path: Path
) -> None:
    """Refused when the server starts, not on the page later: the command exits
    with the refusal, and no address is printed."""
    install(packages, module_name(tmp_path), {"Bad Name": "DRIFT"})
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "digline.cli",
            "view",
            "--suite",
            "suite_qa.py",
            "--port",
            "0",
        ],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(packages)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "'Bad Name'" in done.stderr
    assert "http://" not in done.stdout


# --------------------------------------------------------------------------- #
# The menu and the route
# --------------------------------------------------------------------------- #


def test_the_menu_names_the_view_and_its_package(
    repo: Path, packages: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the command a person types, so `serve()` is what reads it."""
    promoted(repo)
    install(packages, module_name(tmp_path), {"latency-drift": "DRIFT"})
    monkeypatch.setenv("PYTHONPATH", str(packages))
    with server(repo) as (base, _line):
        port = int(base.rsplit(":", 1)[1].strip("/"))
        status, page = request(port, "GET", "/")
    assert status == 200
    assert (
        '<a class="ext" href="/x/latency-drift/">latency-drift'
        f"<small>{PACKAGE}</small></a>"
    ) in page


def test_the_view_is_served_at_its_address_in_digline_s_document(
    repo: Path, packages: Path, tmp_path: Path
) -> None:
    module = module_name(tmp_path)
    marker = tmp_path / "imported"
    install(packages, module, {"latency-drift": "DRIFT"}, marker=marker)
    promoted(repo)
    with in_process(repo) as port:
        status, _page = request(port, "GET", "/")
        assert status == 200
        assert not marker.exists(), "the menu imported the package"
        status, page = request(port, "GET", "/x/latency-drift/?locale=it&n=7")
    assert status == 200
    assert marker.exists()
    assert "<h1>Latency drift</h1>" in page
    assert '<p class="locale">it</p>' in page
    assert f'<p class="root">{repo}</p>' in page
    assert '<p class="query">7</p>' in page
    # In digline's document: the sheet linked, the bar, the view marked in it.
    assert '<link rel="stylesheet" href="/static/digline.css">' in page
    assert '<nav class="bar">' in page
    assert 'class="ext here" href="/x/latency-drift/"' in page
    assert inline_in(page) == []


def test_a_view_answers_get_and_nothing_else(
    repo: Path, packages: Path, tmp_path: Path
) -> None:
    install(packages, module_name(tmp_path), {"latency-drift": "DRIFT"})
    promoted(repo)
    with in_process(repo) as port:
        assert request(port, "GET", "/x/latency-drift/")[0] == 200
        status, body = request(port, "POST", "/x/latency-drift/")
        assert status == 404 and "no such action" in body
        # Its address, exactly: not without the slash, not a path under it,
        # and not a name nobody declared.
        assert request(port, "GET", "/x/latency-drift")[0] == 404
        assert request(port, "GET", "/x/latency-drift/deeper")[0] == 404
        assert request(port, "GET", "/x/nobody/")[0] == 404


def test_a_view_that_fails_names_itself_and_keeps_its_message_off_the_page(
    repo: Path, packages: Path, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """The page names the entry point and the package; what the package's
    code raised reaches the standard error of whoever started the server, and
    the server keeps answering (ADR 0043)."""
    install(
        packages,
        module_name(tmp_path),
        {"broken": "BROKEN", "no-render": "NO_RENDER", "latency-drift": "DRIFT"},
    )
    promoted(repo)
    with in_process(repo) as port:
        status, page = request(port, "GET", "/x/broken/")
        page = unescape(page)
        assert status == 500
        assert "'broken'" in page and PACKAGE in page and "digline.views" in page
        assert "the secret the view held" not in page
        status, page = request(port, "GET", "/x/no-render/")
        page = unescape(page)
        assert status == 500 and "'no-render'" in page
        assert request(port, "GET", "/x/latency-drift/")[0] == 200
        assert request(port, "GET", "/")[0] == 200
    err = capfd.readouterr().err
    assert "the secret the view held" in err
    assert "NoRender has no render(context)" in err
