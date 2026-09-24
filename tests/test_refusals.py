"""Every exception class digline defines is classified.

`digline.host.refusals` sorts them into refusals — shown to a reader, exited on
— and everything else. The list only helps if nobody can add a class without
touching it, and that is what this file is for: a refusal type added to the
store and left out of a front end's tuple reached the user as a closed
connection in 0.19.2 (friction 59), and the fix for the next one is to make it
impossible to add silently.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import threading
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import digline
from digline.cli import EXIT_USAGE
from digline.cli.view import ViewHandler, self_netlocs
from digline.core import Run
from digline.host import load_suite
from digline.host.refusals import NOT_REFUSALS, REFUSALS
from digline.store import FileResultStore

# By module path: `digline.cli` exports the `main` function under the same name
# as the module, so `import digline.cli.main as ...` hands back the function.
cli_main = importlib.import_module("digline.cli.main")


def _qualified(kind: type[BaseException]) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def _defined_exceptions() -> dict[str, type[BaseException]]:
    """Every exception class defined in a module under `digline`, by the name of
    the module that defines it — a re-export is the same class, counted once.

    `__main__` modules are skipped: importing one runs the command line.
    """
    found: dict[str, type[BaseException]] = {}
    for info in pkgutil.walk_packages(digline.__path__, "digline."):
        if info.name.rsplit(".", 1)[-1] == "__main__":
            continue
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseException)
                and value.__module__ == info.name
            ):
                found[_qualified(value)] = value
    return found


def test_every_exception_digline_defines_is_classified() -> None:
    unclassified = sorted(
        set(_defined_exceptions())
        - {_qualified(kind) for kind in REFUSALS}
        - set(NOT_REFUSALS)
    )
    assert not unclassified, (
        f"{', '.join(unclassified)} is defined in digline and classified nowhere. "
        "If a reader should see its message, add it to REFUSALS in "
        "digline/host/refusals.py; if it never reaches a front end, add it to "
        "NOT_REFUSALS with the reason. Every front end that catches refusals "
        "catches what that list says, so a class left out of both is one that "
        "reaches somebody as a traceback."
    )


def test_the_walk_sees_every_listed_class() -> None:
    """The control on the test above, which would pass on a walk that found
    nothing. Every class either table names must be one the walk reached —
    and so a name left behind by a class that was renamed or removed fails here
    rather than sitting in the table as a reason about nothing."""
    walked = set(_defined_exceptions())
    listed = {_qualified(kind) for kind in REFUSALS} | set(NOT_REFUSALS)
    assert listed <= walked, sorted(listed - walked)


def test_no_class_is_classified_twice() -> None:
    names = [_qualified(kind) for kind in REFUSALS]
    assert len(names) == len(set(names)), "a refusal is listed twice"
    assert not set(names) & set(NOT_REFUSALS), (
        "a class cannot be both a refusal and not one"
    )


# --------------------------------------------------------------------------- #
# Every front end says every refusal (friction 59)
# --------------------------------------------------------------------------- #

#: What a refusal carries, and what each front end must hand to a person intact.
SENTENCE = "the sentence a reader was written"


@pytest.mark.parametrize("kind", REFUSALS, ids=lambda kind: kind.__name__)
def test_the_command_line_says_every_refusal(
    kind: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 64 and the sentence, never a traceback. A refusal type added to
    digline arrives here through the classification, so this passes for it
    without the handler in `main` being touched — which is the claim."""

    def refuse(_args: object) -> int:
        raise kind(SENTENCE)

    monkeypatch.setattr(cli_main, "cmd_list", refuse)
    assert cli_main.main(["list", "--suite", "unused.py"]) == EXIT_USAGE
    assert SENTENCE in capsys.readouterr().err


class _Refusing(FileResultStore):
    """A store whose every promotion is refused with the one type under test."""

    def __init__(self, root: Path, kind: type[Exception]) -> None:
        super().__init__(root)
        self.kind = kind

    def promote_baseline(self, *args: object, **kwargs: object) -> Run:
        raise self.kind(SENTENCE)


@pytest.mark.parametrize("kind", REFUSALS, ids=lambda kind: kind.__name__)
def test_the_view_says_every_refusal(kind: type[Exception], repo: Path) -> None:
    """The route that writes answers with the sentence. Before friction 59 it
    listed six types by hand, and two refusals 0.19.2 added reached the browser
    as a closed connection.

    `allow_promote=True`, because the route only exists there: this is about
    what a refusal looks like on the server a person chose to promote from, and
    the default server has nothing to refuse *with* — it refuses the route
    itself. That half is `tests/test_view.py`. (ADR 0032 §6)

    **It was moved here deliberately, and that is the only reason it still
    means anything.** Left on the default server this walk would have gone on
    passing — sixteen refusal types, each POST answered `404` before
    `promote_baseline` was ever called, a green with nothing behind it. Nothing
    would have said so: a test does not fail when it stops testing. That is a
    third instance of the family ADR 0032 is about — the MCP, the hook and the
    skill each stayed correct about a word while the act moved past it; here a
    test stays correct about a request while the *default under it* moves. A
    test whose meaning depends on a default is a test to re-read whenever that
    default changes, and the changing of it is the only notice you get.
    """
    suite, _loaded = load_suite(str(repo / "suite_qa.py"), root=repo)
    known: set[str] = set()
    handler = partial(
        ViewHandler,
        suite=suite,
        store=_Refusing(repo, kind),
        known=known,
        allow_promote=True,
    )
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as httpd:  # pyright: ignore[reportArgumentType]
        port = int(httpd.server_address[1])
        known.update(self_netlocs("127.0.0.1", port))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/promote",
                data=b"run=any&replacing=none&locale=en",
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": f"http://127.0.0.1:{port}",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                status, body = response.status, response.read().decode("utf-8")
        finally:
            httpd.shutdown()
            thread.join(timeout=10)
    assert status == 200
    assert SENTENCE in body
