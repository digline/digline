"""`digline view`: the four screens over `.digline/`, served locally.

Transport only. Every screen is a pure function in `digline.report.pages`,
so what is tested is the page and not the socket, and what is served can never
disagree with what `digline report` writes to a file.

Four properties are deliberate:

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
  reading routes need no credential at all. So `Host` is
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
- **The server that promotes, promotes for one browser.** `--allow-promote`
  decides that this server may write; it cannot decide *who* is asking, and a
  person's `digline view --allow-promote` answered a `curl` from any shell on
  the machine — an agent's included — with no `Origin` and nothing else. So
  that server mints a **launch key** when it starts: random, held in memory,
  never written, never configurable. It reaches a browser once, on the address
  the startup line prints, and is **spent** there: the browser gets a second
  secret as a cookie, and `/promote` refuses a request without that. (ADR 0033
  §11: the address reaches the browser's history, and a key that still worked
  there would promote for whoever read the file.) The flag stays the only
  control a person operates — the key is how the flag's decision stays with
  the person who made it, not a second thing to set. (ADR 0033)
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import sys
import threading
import urllib.parse

# `collections.abc.Set` is the read-only set protocol — the abstract one, not
# the builtin `set`. Aliased because the bare name reads as the builtin at every
# use site, and `serve()` deliberately passes a mutable set it fills after the
# bind while the handler only ever reads it.
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from email.message import Message
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from digline.cli.output import say
from digline.core import key_of
from digline.host import (
    REFUSALS,
    SuiteRuns,
    left_out_parts,
    promote_priced,
    suite_runs,
    utc_now_iso,
)
from digline.report import Locale, case_history, escape, pages
from digline.run import Suite
from digline.store import ResultStore, RunRef

__all__ = ["Launch", "ViewHandler", "cookie_values", "serve"]

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

#: The query parameter that carries the launch key on the printed address, once.
LAUNCH = "launch"

#: The largest `POST /promote` body this server reads. The form is two run keys
#: and a locale, well under 200 bytes, so 4 KiB is twenty times what a real one
#: needs. `Content-Length` was read and then honoured with no ceiling: one
#: request that declared a gigabyte held a thread reading for as long as the
#: caller kept sending, and a caller that sent less held it forever. Refused
#: before a byte of the body is read.
MAX_FORM_BYTES = 4096

#: Seconds a connection may take to send its request, and to take its answer.
#: `ThreadingHTTPServer` starts a thread per connection and, with the
#: stdlib's default of no timeout, a connection that opened and then went quiet
#: held its thread for the life of the server: every such caller was one more
#: thread nobody would ever reclaim. A browser on loopback sends a request in
#: milliseconds; thirty seconds leaves room for anything slower that is still a
#: person.
REQUEST_TIMEOUT_S = 30.0


def launch_cookie(port: int) -> str:
    """The cookie's name, which carries the port.

    A browser keeps cookies by host and **not by port**, so two views on one
    machine — two suites, two terminals — would otherwise overwrite each other's
    key, and the first person would find their server refusing them after the
    second one started.
    """
    return f"digline-view-{port}"


@dataclass
class Launch:
    """One start's launch key, and the session it is traded for — once.

    **Spent on its first hand-over** (ADR 0033 §11). The printed address reaches
    the browser's history, a plaintext file every process of the user reads, and
    it gets there when the browser exits: measured, not on disk for the first
    sixty seconds the browser ran. The hand-over happens the moment the address
    is opened. So a key that works once has opened its browser before any file
    holds it, and a key that worked for the server's life opened a second one
    for whoever read the file.

    **The cookie carries the session, never the key.** Otherwise a spent key in
    the history would still be a valid cookie: skip the hand-over, send it, and
    promote. The two secrets come from the same generator and serve different
    things — the key names a start, the session names a browser.
    """

    # Out of the repr, both: a dataclass prints its fields by default, so the
    # object that holds the secrets would hand them to any exception log, `%r`
    # or debugger that ever formats it. The bare `str` this replaced had no
    # such default. (0.21.1 delta-pass, D-1)
    key: str = field(repr=False)
    session: str = field(default="", repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def minted(cls) -> Launch:
        return cls(key=secrets.token_urlsafe(32))

    def trade(self, offered: str) -> str:
        """`issued`, `spent` or `foreign` — and on `issued`, `session` is set.

        Under a lock, because `ThreadingHTTPServer` answers two hand-overs on two
        threads and only one of them may win the key.
        """
        with self._lock:
            if not hmac.compare_digest(
                offered.encode("utf-8"), self.key.encode("utf-8")
            ):
                return "foreign"
            if self.session:
                return "spent"
            self.session = secrets.token_urlsafe(32)
            return "issued"

    def admits(self, value: str) -> bool:
        """Whether `value` is the session this start issued. Before the hand-over
        there is none, and nothing is admitted."""
        session = self.session
        return bool(session) and hmac.compare_digest(
            value.encode("utf-8"), session.encode("utf-8")
        )


def cookie_values(headers: Message, name: str) -> list[str]:
    """Every value the request sends under the cookie `name`, read pair by pair.

    Not `http.cookies.SimpleCookie`: it stops at the first value it cannot
    parse — a JSON value, a space — so a cookie another app on the same host had
    set before ours hid ours, and the person who *had* opened the address was
    told they had not (ADR 0033 §11, K-3). A browser sends every cookie of the
    host, whoever set it, so what this reads has to survive other people's.
    """
    found: list[str] = []
    for header in headers.get_all("Cookie") or []:
        for pair in header.split(";"):
            key, sep, value = pair.strip().partition("=")
            if sep and key.strip() == name:
                found.append(value.strip())
    return found


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

    **That door is only safe because another one is shut behind it.** A caller
    with a shell *is* an attack on the flagged server — an agent's `curl`
    promoted a person's baseline through exactly this `return True` — and what
    refuses it is the launch key, which `curl` does not have. The origin check
    stops a page; the key stops a process. (ADR 0033 §2)

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
    #: Read by `StreamRequestHandler.setup()`, which puts it on the socket: every
    #: read and write on this connection then raises `TimeoutError` past it.
    #: While the request line and headers are read, the stdlib catches that and
    #: closes the connection; while the body is read, `do_POST` answers 408.
    timeout = REQUEST_TIMEOUT_S

    def __init__(
        self,
        *args: object,
        suite: Suite,
        store: ResultStore,
        pricing: str = "",
        known: AbstractSet[str] = frozenset(),
        wildcard: bool = False,
        launch: Launch | None = None,
        **kwargs: object,
    ) -> None:
        self.suite = suite
        self.store = store
        #: The key this start minted and the session it was traded for, or
        #: `None` on the server that does not promote. **There is no separate
        #: switch beside it**: a server that promotes without a key cannot be
        #: constructed, so the key cannot become the optional half of two
        #: controls. (ADR 0033)
        self.launch = launch
        #: Whether this server promotes at all — **one fact, read twice**: the
        #: page asks it to decide whether to draw a button, and `do_POST` asks
        #: it to decide whether `/promote` exists. Two decisions computed
        #: separately is a page that eventually offers a button the route
        #: rejects. Empty by default is the same asymmetry as the flag's: the
        #: cheap mistake is the one a default should make. (ADR 0032 §1-2)
        self.allow_promote = launch is not None
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

    # -- the launch key ------------------------------------------------------ #

    def _cookie(self) -> str:
        # The port the request arrived on, which is the one this server bound:
        # read off the socket because `server_address` is typed for every
        # address family, a Unix path included, and has no port to index.
        return launch_cookie(int(self.connection.getsockname()[1]))

    def _without_the_session(self) -> str:
        """Why this request may not promote, or empty when it may.

        **What the request carried, never what the browser did** (ADR 0033 §11,
        K-3). The server cannot see a browser; it sees a header. It used to say
        *"only from the browser that opened the address"* whenever the cookie
        did not match, and a foreign cookie that broke the parser made that
        sentence false for the one person it was addressed to.
        """
        assert self.launch is not None
        values = cookie_values(self.headers, self._cookie())
        if any(self.launch.admits(value) for value in values):
            return ""
        if not values:
            return (
                "refused: this request carries no cookie from this server. It "
                "promotes only for the browser that opened the address digline "
                "view printed when it started; a script or another browser has "
                "none."
            )
        return (
            "refused: this request's cookie was not issued by this start of "
            "digline view: it is from an earlier start, or not from this "
            "server. Open the address this start printed, or start it again."
        )

    def _hand_over(self, query: Mapping[str, Sequence[str]]) -> bool:
        """Turn the printed address into a cookie, and send the browser to `/`.

        True when the request was answered here. The key is checked, set as an
        `HttpOnly`, `SameSite=Strict` cookie, and the browser is sent to `/`
        **without** it — so the key does not sit in the address bar, and no
        page this server renders ever contains it. That last part is the whole
        of the design: every reading route answers anybody with a shell, so a
        key written into a page, a form or a link would be handed to exactly
        the caller it exists to refuse.

        **`Location` is the constant `/`, and that is the property, not a
        simplification: no header this server sends carries anything the
        request said.** It used to be the request's own path plus its
        re-encoded query, so `?locale=it` survived the hand-over. That was safe
        against response splitting, and the reasons were three facts about
        code this file does not own: `http.server` strips the request line's
        CR/LF and refuses a line whose CR splits it into extra words (400);
        `urlparse().path` does not decode `%0D%0A`; and `urlencode` re-encodes
        what `parse_qs` decoded. `send_header` itself checks nothing. And it
        was not safe against a *meaning*: `/\\evil.example` went out verbatim,
        and a browser reads that backslash as a slash — a redirect off the
        machine, reachable only with the key. A constant needs none of those
        facts to stay true. (ADR 0033 §2, CodeQL alert 89)

        On the server that does not promote there is nothing to hand over and
        the parameter is ignored: the header already says what that server is.
        """
        if LAUNCH not in query or self.launch is None:
            return False
        offered = query[LAUNCH][0] if query[LAUNCH] else ""
        outcome = self.launch.trade(offered)
        if outcome == "foreign":
            self._error(
                403,
                "refused: this address carries a launch key from another start "
                "of digline view. Open the address this start printed.",
            )
            return True
        if outcome == "spent":
            # The case §11 exists for: the address read back out of a browser's
            # history, or opened a second time. It opens one browser, once.
            self._error(
                403,
                "refused: this address has already been opened, and it opens "
                "one browser once. Promote from the browser that opened it, or "
                "stop digline view and start it again for a new address.",
            )
            return True
        self.send_response(303)
        self.send_header(
            "Set-Cookie",
            f"{self._cookie()}={self.launch.session}; "
            "Path=/; HttpOnly; SameSite=Strict",
        )
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return True

    # -- reading the store -------------------------------------------------- #

    def _runs(self) -> SuiteRuns:
        # In clear: this server serves the unredacted store to world 1. A run
        # the store refuses is left out and named, rather than answering 400
        # for the whole page. (#314)
        return suite_runs(self.store, self.suite.tenant, self.suite.name, mint=None)

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
        if self._hand_over(query):
            return
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
        # Every refusal digline raises on purpose, derived rather than listed.
        # A bare `ValueError` is no longer one: it is a failure nobody
        # anticipated, as on the command line. (friction 59, ADR 0041 §4.2)
        except REFUSALS as exc:
            self._error(400, str(exc))

    def _screen_runs(self, locale: Locale, message: str = "") -> None:
        listed = self._runs()
        self._send(
            200,
            pages.runs_page(
                listed.runs,
                baseline_key=listed.baseline_key,
                config_hash=self.suite.config_hash(pricing=self.pricing),
                locale=locale,
                suite=self.suite.name,
                allow_promote=self.allow_promote,
                ignored=left_out_parts(listed, locale=locale),
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

        With **no baseline yet** there is no reference to hold it against, so
        the page is the run on its own — `digline report`'s answer to the same
        state.

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
        baseline_key = (
            None
            if baseline is None
            else key_of(baseline.created_at, baseline.config_hash)
        )

        other = (query.get("against") or [""])[0]
        if other and other != baseline_key:
            if other == key:
                self._error(400, pages.phrase(locale, "view.compare.same"))
                return
            against = self.store.read_run(
                RunRef(tenant=self.suite.tenant, suite=self.suite.name, key=other)
            )
            # A refusal from ADR 0008 §3 is in `REFUSALS`, which `do_GET`
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
            # The run on its own, which is what `digline report` writes in the
            # same state — not a 404. The first baseline is promoted from this
            # server, and a refusal here left the aggregates as the only thing
            # to promote from.
            self._send(200, pages.run_page(run, locale=locale, suite=self.suite.name))
            return
        self._send(
            200, pages.compare_page(run, baseline, locale=locale, suite=self.suite.name)
        )

    def _screen_case(self, locale: Locale, case_id: str) -> None:
        listed = self._runs()
        history = case_history(listed.runs, case_id)
        self._send(
            200,
            pages.case_page(
                history,
                locale=locale,
                suite=self.suite.name,
                ignored=left_out_parts(listed, locale=locale),
            ),
        )

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
        """`/promote`, only on a server started with `--allow-promote`, and only
        from the browser that opened the address it printed.

        **Without the flag the refusal is a 404 and deliberately not a 403.** A
        403 says *you may not*, which implies a someone who may, which is a
        policy — and a policy is the kind of thing a future release relaxes
        "just for CI". ADR 0011 refused to create one when it declined to ship
        a `promote` tool that raises *not permitted*; the same argument governs
        the same act reached through a different word. On this server there is
        no promote, so the answer is the one every unknown path gets, in the
        same sentence. (ADR 0032 §2)

        **With the flag, a request without the launch key is a 403**, and that
        is the same reasoning giving the other answer. On this server somebody
        may promote — the person who started it — so a caller without the key
        is refused, not told there is nothing here. Same fact, two servers, two
        truthful answers. (ADR 0033 §3)
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
        refused = self._without_the_session()
        if refused:
            # After the origin check, so a cross-origin POST is still refused
            # in the words that say so; and before the form is read, so
            # nothing a refused caller sent is parsed at all.
            self._error(403, refused)
            return

        body = self._form_body()
        if body is None:
            return
        form = urllib.parse.parse_qs(body.decode("utf-8"))
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

        try:
            # The pricing was computed once, at launch, by the function
            # `digline.host.promote` uses: resolving the target on every
            # request would import the user's target module per promotion.
            promote_priced(
                self.store,
                self.suite,
                self.pricing,
                key,
                # What the page was drawn against. (ADR 0031 §1)
                replacing=expected,
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

    def _form_body(self) -> bytes | None:
        """The body `Content-Length` declares, or `None` once refused.

        **The length is judged before anything is read**, because reading is
        what an oversized or lying length makes expensive. A length that is
        not a non-negative integer is a 400 rather than the `ValueError` it used
        to raise, which reached the browser as a closed connection; a negative
        one would have read until the caller hung up. A body that stops arriving
        is a 408 with a sentence, so a caller learns the server gave up rather
        than meeting a connection that ended.
        """
        declared = self.headers.get("Content-Length") or "0"
        # ASCII first: `"²".isdigit()` is true, and `int("²")` raises.
        if not (declared.isascii() and declared.isdigit()):
            self._error(400, "refused: the request declared no usable length")
            return None
        length = int(declared)
        if length > MAX_FORM_BYTES:
            self._error(
                413,
                f"refused: a promotion form is at most {MAX_FORM_BYTES} bytes, "
                f"and this request declared {length}",
            )
            return None
        try:
            body = self.rfile.read(length)
        except TimeoutError:
            self._error(
                408,
                "refused: the request did not arrive in time, so none of it was read",
            )
            return None
        if len(body) < length:
            # The caller closed before sending what it declared: a form cut
            # short is not a form, and parsing half of it could read a run key
            # that is a prefix of the one intended.
            self._error(400, "refused: the request ended before its declared length")
            return None
        return body

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

        **So this catches every exception, and it answers a different
        requirement from the other handlers, not an exception to theirs.**
        They classify a failure that happens before anything has changed: a
        refusal is a 400, and a failure nobody anticipated is left to be one.
        Here the state has already changed, and a front end that has changed
        state must say so whatever fails afterwards. The catch classifies
        nothing. When ADR 0041 §4.2 took the bare `ValueError` out of the
        refusals, catching only `REFUSALS` here would have reopened friction 59
        for every failure that is not a refusal, and the test that injects a
        fault into the list caught exactly that.
        """
        try:
            self._screen_runs(locale, outcome)
        except Exception as exc:  # noqa: BLE001 — the outcome must arrive whatever the list does
            self._plain(
                200,
                outcome,
                pages.phrase(locale, "view.list.unavailable", why=str(exc)),
            )


def serve(
    suite: Suite,
    store: ResultStore,
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

    **The launch key is minted here, and there is no parameter to pass one in.**
    A key that could be supplied would have to come from somewhere — a file, a
    variable, an option — and every such place is readable by any process of
    the same user, which is the caller the key exists to refuse. Minted per
    start and held in memory, it has no home to read. (ADR 0033 §1)
    """
    # Filled after the bind and shared with every handler by reference, because
    # the port may not be known until then: `--port 0` means the operating
    # system chooses, and the allowlist has to name the port actually taken.
    # Binding twice to learn it would race another process for the number.
    known: set[str] = set()
    launch = Launch.minted() if allow_promote else None
    handler = partial(
        ViewHandler,
        suite=suite,
        store=store,
        pricing=pricing,
        known=known,
        wildcard=host in _WILDCARDS,
        launch=launch,
    )
    with ThreadingHTTPServer((host, port), handler) as httpd:  # pyright: ignore[reportArgumentType]
        known.update(self_netlocs(host, int(httpd.server_address[1])))
        shown = f"http://{host}:{httpd.server_address[1]}/"
        if launch is not None:
            # The one place the key is ever shown: the output of the process,
            # which goes wherever whoever started it pointed it — a person's
            # terminal, or an agent's pipe after the plugin's hook has asked.
            shown += f"?{LAUNCH}={launch.key}"
        # Flushed, and the *bound* port rather than the requested one: with
        # `--port 0` the operating system chooses, and a caller that cannot read
        # which one would have to guess. Through `say()` like every other line
        # the CLI prints, so no door to a terminal is left unguarded
        # (0.13.0 delta-pass).
        # The URL stays the fourth word whichever server this is: a caller
        # reading the line for the bound port should not have to parse a mood.
        mode = (
            "promotion enabled, for the first browser that opens this address"
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
