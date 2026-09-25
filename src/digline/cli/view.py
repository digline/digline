"""`digline view`: the four screens over `.digline/`, served locally.

Transport only. Every screen is a pure function in `digline.report.pages`,
so what is tested is the page and not the socket, and what is served can never
disagree with what `digline report` writes to a file.

Three properties are deliberate:

- **No state of its own.** It reads the store and holds nothing between
  requests — not a session, not a preference, not a cache. Restarting it loses
  nothing because there was nothing to lose.
- **Nothing here writes, unless `--allow-promote` was typed.** On the default
  server `/promote` is not a route: a POST to it gets the 404 any unknown path
  gets, and no row offers a button. With the flag it is the route it always
  was, writing exactly what `digline promote` writes, through the same
  `promote_baseline` with the same refusals.

  **The default is the refusing one, and the asymmetry is why.** Forgetting the
  flag costs a restart — the header names it. Forgetting a `--read-only` would
  cost an unreviewed baseline, silently, which is the whole of what the
  perimeter exists to prevent. (ADR 0032 §1)
- **The request does not get to say who this server is.** Binding to loopback is
  not enough: any page in the developer's browser can reach `localhost`, and the
  browser will attach no credential but the server needs none. So `Host` is
  checked against the address this server actually bound to, on **every** route,
  and `Origin` is checked against that same known value.

  **This used to read "`Origin` is checked on that route ... five lines close
  the category", and that sentence was wrong for the life of the project.**
  Those five lines compared `Origin` with the request's own `Host` header —
  two values describing one request. A page served from a hostname its author
  controls that resolves to the loopback address is same-origin with this
  server, so the comparison agreed and one request read the whole store or
  promoted a baseline. The claim is recorded here rather than deleted because a
  confident docstring is why nobody looked again: the code was one defect, and
  the sentence telling everyone it was handled was the other.
"""

from __future__ import annotations

import ipaddress
import sys
import urllib.parse

# `collections.abc.Set` is the read-only set protocol — the abstract one, not
# the builtin `set`. Aliased because the bare name reads as the builtin at every
# use site, and `serve()` deliberately passes a mutable set it fills after the
# bind while the handler only ever reads it.
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from digline.cli.output import say
from digline.host import REFUSALS, replacing
from digline.report import Locale, case_history, escape, pages
from digline.run import Suite
from digline.store import FileResultStore, RunRef, utc_now_iso

__all__ = ["ViewHandler", "serve"]

# `_ROUTES` used to stand here, a tuple commented *"everything this server
# answers"*, with zero readers anywhere in the tree and two routes missing —
# `do_GET` dispatches on literals and serves `/case/` and `/suspend/`, neither
# of which it listed. A list that describes the server incorrectly and is
# consulted by nothing is worse than no list: it is where a change lands that
# reads correctly in review and does nothing. ADR 0032 §2 gave it the choice of
# becoming the real dispatch table or going; it goes. The routes are the
# `if` chain in `do_GET`, which is the only thing that was ever true.


#: Bind addresses that name every interface rather than one. A server bound to
#: one of these cannot enumerate the names it will be reached by, which is the
#: one case `_is_self` has to answer differently.
_WILDCARDS = frozenset({"", "0.0.0.0", "::", "[::]"})  # noqa: S104


def self_netlocs(host: str, port: int) -> frozenset[str]:
    """The `Host` values that name this server, derived from where it bound.

    `localhost` and the loopback literals are in the set beside the configured
    address because a browser sends whichever the developer typed, and all of
    them reach the same socket when the bind is loopback.

    The port is part of every entry: `Host` carries it, and a set without it
    would accept the right name at the wrong port — which is a different server
    on the same machine.
    """
    names = {host, "localhost", "127.0.0.1", "[::1]"} - _WILDCARDS
    return frozenset(f"{name}:{port}" for name in names)


def _is_self(netloc: str, known: AbstractSet[str], *, wildcard: bool) -> bool:
    """Whether `netloc` names this server.

    **Why a wildcard bind is answered differently rather than refused.** Bound
    to every interface, the server cannot know the names it is reachable by —
    a LAN address, a container alias, whatever the operator arranged — and a
    set derived from configuration would refuse a deployment somebody chose on
    purpose. So an address *literal* is accepted there.

    That is not a hole, and the reason is worth stating where the exception is
    made: this check exists to stop a request whose `Host` is a **name** the
    attacker controls. Pointing a name at the loopback address is what makes
    their page same-origin with this server; an IP literal cannot be made to
    resolve anywhere, because it does not resolve at all.
    """
    if netloc in known:
        return True
    if not wildcard:
        return False
    hostname = netloc.rsplit(":", 1)[0] if ":" in netloc else netloc
    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return True


def _allowed_origin(origin: str, known: AbstractSet[str], *, wildcard: bool) -> bool:
    """Whether a request carrying this `Origin` may be acted on.

    A browser sends `Origin` on cross-site posts, so a page on any site the
    developer happens to have open could otherwise promote a baseline. The rule
    is the conservative one: no `Origin` at all is allowed — that is a curl or
    an old browser, neither of which is the attack — but an `Origin` that is
    not ours is refused rather than ignored.

    **It is compared with what this server knows itself to be**, never with the
    request's own `Host`. That comparison was the defect: both headers describe
    one request, so it asked the sender whether the sender was allowed.
    """
    if not origin:
        return True
    return _is_self(urllib.parse.urlparse(origin).netloc, known, wildcard=wildcard)


class ViewHandler(BaseHTTPRequestHandler):
    """One request, one page. Constructed per request by `http.server`."""

    server_version = "digline-view"
    sys_version = ""

    def __init__(
        self,
        *args: object,
        suite: Suite,
        store: FileResultStore,
        pricing: str = "",
        known: AbstractSet[str] = frozenset(),
        wildcard: bool = False,
        allow_promote: bool = False,
        **kwargs: object,
    ) -> None:
        self.suite = suite
        self.store = store
        #: Whether this server promotes at all — **one fact, read twice**: the
        #: page asks it to decide whether to draw a button, and `do_POST` asks
        #: it to decide whether `/promote` exists. Two decisions computed
        #: separately is a page that eventually offers a button the route
        #: rejects. Defaulting to `False` is the same asymmetry as the flag's:
        #: the cheap mistake is the one a default should make. (ADR 0032 §1-2)
        self.allow_promote = allow_promote
        #: The netlocs that name this server, from where it bound — not from
        #: anything the request says. `serve()` computes them once.
        self.known = known
        #: Bound to every interface, so the names cannot be enumerated and an
        #: address literal is accepted instead. See `_is_self`.
        self.wildcard = wildcard
        #: The declared-price digest of the target this view promotes for, so a
        #: promotion from the browser checks the same hash the CLI does.
        #: (ADR 0022 §5)
        self.pricing = pricing
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
        self._plain(status, message)

    def _plain(self, status: int, *paragraphs: str) -> None:
        # `escape`, the report's, and not `html.escape`: the second covers what
        # changes how a browser *parses* the page and leaves C0, C1 and the
        # bidi overrides alone, so a refusal quoting a committed baseline's
        # `promoted_at` wrote them raw — an RLO reversing the sentence that
        # names which key was found. Every other page already went through
        # this one; this was the page friction 59 added. (0.20.0 delta-pass,
        # F-2)
        body = "".join(f"<p>{escape(text)}</p>" for text in paragraphs)
        self._send(
            status,
            f"<!DOCTYPE html><html><body>{body}"
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

    def _addressed_to_us(self) -> bool:
        """Whether this request named this server, rather than a name that
        merely resolves to it.

        On **every** route and not only the one that writes: the reading routes
        serve the unredacted store, which is the larger of the two losses. A
        page that can read `/` has every run key, environment and commit in the
        project, held by a party ADR 0002 exists to keep them from.
        """
        if _is_self(self.headers.get("Host", ""), self.known, wildcard=self.wildcard):
            return True
        # 403 and not 404: the request reached the right server, and a reply
        # that pretended otherwise would be a different lie than the one being
        # refused.
        self._error(
            403,
            "refused: this request was addressed to a name this server does "
            "not answer to. digline view serves the address it bound to.",
        )
        return False

    def do_GET(self) -> None:  # noqa: N802 — the name http.server dispatches on
        if not self._addressed_to_us():
            return
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
        # Every refusal digline raises on purpose, derived rather than listed,
        # and bare `ValueError` beside it as the CLI keeps it. (friction 59)
        except (*REFUSALS, ValueError) as exc:
            self._error(400, str(exc))

    def _screen_runs(self, locale: Locale, message: str = "") -> None:
        runs, ignored = self._runs()
        self._send(
            200,
            pages.runs_page(
                runs,  # pyright: ignore[reportArgumentType]
                baseline_key=self._baseline_key(),
                config_hash=self.suite.config_hash(pricing=self.pricing),
                locale=locale,
                suite=self.suite.name,
                allow_promote=self.allow_promote,
                ignored=ignored,
                message=message,
            ),
        )

    def _screen_compare(
        self, locale: Locale, query: Mapping[str, Sequence[str]]
    ) -> None:
        """One route, two questions, and the reference is what tells them apart.

        Against the **baseline** — including when `against` is omitted, which is
        the default — this is a run held against an approved reference, which is
        `compare()`'s question, and the verdict document is the right answer.

        Against **any other run** neither side was approved by anybody, so the
        page is the diff report. Until ADR 0008 this route rendered the verdict
        for every pair, which put two candidates under a heading asking "Did it
        get worse?" beside a column called "Reference" — the diff's need served
        with the verdict's semantics. (ADR 0008 §6)
        """
        key = (query.get("run") or [""])[0]
        if not key:
            self._error(400, "compare needs a run")
            return
        run = self.store.read_run(
            RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=key)
        )

        baseline = self.store.read_baseline(self.suite.tenant, self.suite.name)
        baseline_key = None if baseline is None else self.store.key_for(baseline)

        other = (query.get("against") or [""])[0]
        if other and other != baseline_key:
            if other == key:
                self._error(400, pages.phrase(locale, "view.compare.same"))
                return
            against = self.store.read_run(
                RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=other)
            )
            # A refusal from ADR 0008 §3 is a `ValueError`, which `do_GET`
            # already turns into a 400 carrying `str(exc)` — so the screen shows
            # **the same sentence the CLI prints**, naming the same remedy. The
            # page around it is plain and may stay plain; the sentence is the
            # product, and a refusal worded twice would be two refusals.
            self._send(
                200,
                pages.diff_page(
                    run,
                    against,
                    locale=locale,
                    suite=self.suite.name,
                    keys=(key, other),
                ),
            )
            return

        if baseline is None:
            self._error(404, "this suite has no baseline yet")
            return
        self._send(
            200, pages.compare_page(run, baseline, locale=locale, suite=self.suite.name)
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

    # -- the route that writes, where there is one --------------------------- #

    def do_POST(self) -> None:  # noqa: N802 — the name http.server dispatches on
        """`/promote`, and only on a server started with `--allow-promote`.

        **Without the flag the refusal is a 404 and deliberately not a 403.** A
        403 says *you may not*, which implies a someone who may, which is a
        policy — and a policy is the kind of thing a future release relaxes
        "just for CI". ADR 0011 refused to create one when it declined to ship
        a `promote` tool that raises *not permitted*; the same argument governs
        the same act reached through a different word. On this server there is
        no promote, so the answer is the one every unknown path gets, in the
        same sentence. (ADR 0032 §2)
        """
        if not self._addressed_to_us():
            return
        path, _query = self._query()
        if path != "/promote" or not self.allow_promote:
            self._error(404, f"no such action: {path}")
            return
        if not _allowed_origin(
            self.headers.get("Origin", ""), self.known, wildcard=self.wildcard
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
        # The reference the page was drawn against. Absent is refused rather
        # than read as `none`: a form that lost the field is not a form that
        # said there was no baseline. (ADR 0031 §2)
        expected = (form.get("replacing") or [""])[0]
        if not expected:
            self._error(400, "promote needs the baseline it replaces")
            return

        ref = RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=key)
        try:
            self.store.promote_baseline(
                ref,
                self.suite.config_hash(pricing=self.pricing),
                expected_baseline=replacing(expected),
                promoted_at=utc_now_iso(),
            )
        except REFUSALS as exc:
            # Every refusal the call can raise, because the tuple is the
            # classification's rather than this file's: it used to be six
            # names written here, and 0.19.2 added two refusals this list never
            # learned, which reached the browser as a closed connection.
            # (friction 59)
            self._after_promotion(
                locale, pages.phrase(locale, "view.promote.refused", why=str(exc))
            )
            return
        self._after_promotion(
            locale, pages.phrase(locale, "view.promote.done", run_key=key)
        )

    def _after_promotion(self, locale: Locale, outcome: str) -> None:
        """Say what the promotion did, and draw the runs under it if they can
        be drawn.

        **The outcome is the part that must arrive.** The list is re-read from
        the store after the write, and one unreadable run file anywhere in it
        used to make that read raise — after the baseline had been written. The
        browser got a closed connection, and a person who had just promoted
        concluded that nothing happened. A promotion that looks failed and is
        not is worse than one that failed: the reference moved and nobody
        believes it did. So the list is optional here and the sentence is not.
        (friction 59)
        """
        try:
            self._screen_runs(locale, outcome)
        except (*REFUSALS, ValueError) as exc:
            self._plain(
                200,
                outcome,
                pages.phrase(locale, "view.list.unavailable", why=str(exc)),
            )


def serve(
    suite: Suite,
    store: FileResultStore,
    *,
    host: str = "127.0.0.1",
    port: int = 7373,
    pricing: str = "",
    allow_promote: bool = False,
) -> None:
    """Serve until interrupted. Loopback by default, and that is not a default
    anyone should change lightly: this server has no authentication because it
    has no user, only a developer at the same machine.

    `allow_promote` defaults to refusing, and the startup line says which server
    this is either way. The refusing one names the flag there as well as in the
    header, so the discovery path does not run through the documentation.
    """
    # Filled after the bind and shared with every handler by reference, because
    # the port may not be known until then: `--port 0` means the operating
    # system chooses, and the allowlist has to name the port actually taken.
    # Binding twice to learn it would race another process for the number.
    known: set[str] = set()
    handler = partial(
        ViewHandler,
        suite=suite,
        store=store,
        pricing=pricing,
        known=known,
        wildcard=host in _WILDCARDS,
        allow_promote=allow_promote,
    )
    with ThreadingHTTPServer((host, port), handler) as httpd:  # pyright: ignore[reportArgumentType]
        known.update(self_netlocs(host, int(httpd.server_address[1])))
        shown = f"http://{host}:{httpd.server_address[1]}/"
        # Flushed, and the *bound* port rather than the requested one: with
        # `--port 0` the operating system chooses, and a caller that cannot read
        # which one would have to guess. Through `say()` like every other line
        # the CLI prints, so no door to a terminal is left unguarded
        # (0.13.0 delta-pass).
        # The URL stays the fourth word whichever server this is: a caller
        # reading the line for the bound port should not have to parse a mood.
        mode = (
            "promotion enabled"
            if allow_promote
            else "read-only; --allow-promote to promote"
        )
        say(f"digline view on {shown} — {mode} — ctrl-c to stop")
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            say()


def project_root(root: str | Path) -> Path:
    return Path(root).resolve()
