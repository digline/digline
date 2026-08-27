"""`digline view`: the four screens over `.digline/`, served locally.

Transport only. Every screen is a pure function in `digline.report.pages`,
so what is tested is the page and not the socket, and what is served can never
disagree with what `digline report` writes to a file.

Three properties are deliberate:

- **No state of its own.** It reads the store and holds nothing between
  requests — not a session, not a preference, not a cache. Restarting it loses
  nothing because there was nothing to lose.
- **One route writes**, and it writes exactly what `digline promote` writes,
  through the same `promote_baseline` with the same three refusals.
- **`Origin` is checked on that route.** Binding to loopback is not enough: any
  page in the developer's browser can POST to `localhost`, and the browser will
  attach no credential but the server needs none. Five lines close the category.
"""

from __future__ import annotations

import html
import urllib.parse
from collections.abc import Mapping, Sequence
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from digline.report import Locale, case_history, pages
from digline.run import Suite
from digline.store import (
    ConfigMismatchError,
    ErroredRunError,
    FileResultStore,
    RunRef,
    TenantMismatchError,
)

__all__ = ["ViewHandler", "serve"]

#: Everything this server answers. A path outside it is a 404 and not a file:
#: the view serves pages it renders, never bytes off the disk.
_ROUTES = ("/", "/compare", "/promote")


def _allowed_origin(origin: str, host: str) -> bool:
    """Whether a POST may be acted on.

    A browser sends `Origin` on cross-site form posts, so a page on any site
    the developer happens to have open could otherwise promote a baseline. The
    rule is the conservative one: no `Origin` at all is allowed — that is a
    curl or an old browser, neither of which is the attack — but an `Origin`
    that is not ours is refused rather than ignored.
    """
    if not origin:
        return True
    parsed = urllib.parse.urlparse(origin)
    return parsed.netloc == host


class ViewHandler(BaseHTTPRequestHandler):
    """One request, one page. Constructed per request by `http.server`."""

    server_version = "digline-view"
    sys_version = ""

    def __init__(
        self,
        *args: object,
        suite: Suite,
        store: FileResultStore,
        **kwargs: object,
    ) -> None:
        self.suite = suite
        self.store = store
        # `BaseHTTPRequestHandler.__init__` handles the request, so every
        # attribute this class needs must be set before calling it.
        super().__init__(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    # -- plumbing ----------------------------------------------------------- #

    def log_message(self, format: str, *args: object) -> None:
        """Silent by default. A view left open all afternoon should not fill a
        terminal the developer is also using for the CLI."""

    def _send(self, status: int, body: str, *, content_type: str = "text/html") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # Nothing here is cacheable: the store changes under the page whenever
        # the developer runs the suite in the terminal next door.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        self._send(
            status,
            f"<!DOCTYPE html><html><body><p>{html.escape(message)}</p>"
            '<p><a href="/">back</a></p></body></html>\n',
        )

    def _query(self) -> tuple[str, Mapping[str, Sequence[str]]]:
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    # -- reading the store -------------------------------------------------- #

    def _runs(self) -> tuple[list[tuple[str, object]], str]:
        listing = self.store.scan_runs(self.suite.tenant, self.suite.name)
        rows = [(ref.key, self.store.read_run(ref)) for ref in listing.runs]
        return list(rows), listing.note()

    def _baseline_key(self) -> str | None:
        baseline = self.store.read_baseline(self.suite.tenant, self.suite.name)
        return None if baseline is None else self.store.key_for(baseline)

    # -- the screens -------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802 — the name http.server dispatches on
        path, query = self._query()
        locale: Locale = pages.locale_of(query)
        try:
            if path == "/":
                self._screen_runs(locale)
            elif path == "/compare":
                self._screen_compare(locale, query)
            elif path.startswith("/case/"):
                self._screen_case(locale, urllib.parse.unquote(path[len("/case/") :]))
            elif path.startswith("/suspend/"):
                self._screen_suspend(
                    locale, urllib.parse.unquote(path[len("/suspend/") :]), query
                )
            else:
                self._error(404, f"no such page: {path}")
        except FileNotFoundError as exc:
            self._error(404, str(exc))
        except (ValueError, TenantMismatchError) as exc:
            self._error(400, str(exc))

    def _screen_runs(self, locale: Locale, message: str = "") -> None:
        runs, ignored = self._runs()
        self._send(
            200,
            pages.runs_page(
                runs,  # pyright: ignore[reportArgumentType]
                baseline_key=self._baseline_key(),
                config_hash=self.suite.config_hash(),
                locale=locale,
                suite=self.suite.name,
                ignored=ignored,
                message=message,
            ),
        )

    def _screen_compare(
        self, locale: Locale, query: Mapping[str, Sequence[str]]
    ) -> None:
        key = (query.get("run") or [""])[0]
        if not key:
            self._error(400, "compare needs a run")
            return
        run = self.store.read_run(
            RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=key)
        )

        other = (query.get("against") or [""])[0]
        if other:
            against = self.store.read_run(
                RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=other)
            )
        else:
            baseline = self.store.read_baseline(self.suite.tenant, self.suite.name)
            if baseline is None:
                self._error(404, "this suite has no baseline yet")
                return
            against = baseline

        self._send(
            200, pages.compare_page(run, against, locale=locale, suite=self.suite.name)
        )

    def _screen_case(self, locale: Locale, case_id: str) -> None:
        runs, _ignored = self._runs()
        history = case_history(runs, case_id)  # pyright: ignore[reportArgumentType]
        self._send(200, pages.case_page(history, locale=locale, suite=self.suite.name))

    def _screen_suspend(
        self, locale: Locale, case_id: str, query: Mapping[str, Sequence[str]]
    ) -> None:
        reason = (query.get("reason") or [""])[0]
        self._send(
            200,
            pages.suspend_page(
                case_id, reason=reason, locale=locale, suite=self.suite.name
            ),
        )

    # -- the one route that writes ------------------------------------------ #

    def do_POST(self) -> None:  # noqa: N802 — the name http.server dispatches on
        path, _query = self._query()
        if path != "/promote":
            self._error(404, f"no such action: {path}")
            return
        if not _allowed_origin(
            self.headers.get("Origin", ""), self.headers.get("Host", "")
        ):
            # 403 and not a redirect: a refusal that looked like a page would be
            # indistinguishable from a promotion that happened.
            self._error(403, "refused: this request came from another origin")
            return

        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        locale: Locale = pages.locale_of(form)
        key = (form.get("run") or [""])[0]
        if not key:
            self._error(400, "promote needs a run")
            return

        ref = RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=key)
        try:
            self.store.promote_baseline(ref, self.suite.config_hash())
        except (
            ConfigMismatchError,
            ErroredRunError,
            TenantMismatchError,
            FileNotFoundError,
        ) as exc:
            # The same three refusals as the CLI, because it is the same call.
            self._screen_runs(
                locale, pages.phrase(locale, "view.promote.refused", why=str(exc))
            )
            return
        self._screen_runs(
            locale, pages.phrase(locale, "view.promote.done", run_key=key)
        )


def serve(
    suite: Suite,
    store: FileResultStore,
    *,
    host: str = "127.0.0.1",
    port: int = 7373,
) -> None:
    """Serve until interrupted. Loopback by default, and that is not a default
    anyone should change lightly: this server has no authentication because it
    has no user, only a developer at the same machine."""
    handler = partial(ViewHandler, suite=suite, store=store)
    with ThreadingHTTPServer((host, port), handler) as httpd:  # pyright: ignore[reportArgumentType]
        shown = f"http://{host}:{httpd.server_address[1]}/"
        # Flushed, and the *bound* port rather than the requested one: with
        # `--port 0` the operating system chooses, and a caller that cannot read
        # which one would have to guess.
        print(f"digline view on {shown} — ctrl-c to stop", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def project_root(root: str | Path) -> Path:
    return Path(root).resolve()
