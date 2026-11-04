"""What another package gives `digline view` to add a page, and what it gets.

A package adds a view by declaring an entry point in the group `digline.views`
(ADR 0061 §5). The contract lives here, in `digline.report`, and not beside the
server: nothing under `packages/` may import `digline.cli`.

- **The name is the address and the label.** Lowercase letters, digits and
  hyphens, `NAME`; the view is served at `/x/<name>/`, a prefix no screen of
  digline's uses, so two packages can collide with each other and never with
  digline. The menu shows the name, with the package that declared it beside
  it. The names are read from the installed metadata, without importing any
  package.
- **The value is loaded on first access**, and is an object with one method,
  `render(context) -> str`, which returns the body of the page. digline wraps
  that body in its own document: the shared sheet, the navigation and the
  server's headers. The body escapes what it puts in it, with
  `digline.report.escape`, and carries no `style` attribute, no `<style>` and no
  `<script>` that runs: the server's policy refuses them (ADR 0061 §4.4).
- **Read only.** A view answers GET and nothing else, and the context carries
  values and no capability: the store's root, the locale and the query. A view
  that needs the store reads it through the read functions of `digline.host`,
  as any package may.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from digline.report.text import Locale

__all__ = ["GROUP", "NAME", "MenuEntry", "View", "ViewContext", "address"]

#: The entry point group a package declares its views in.
GROUP = "digline.views"

#: What a view's name may be. Refused by name otherwise, when the server starts.
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class ViewContext:
    """What a view is handed: values, and nothing it could write through.

    `root` is the directory that holds `.digline/`, as a string because this
    package does no I/O. `query` is the request's query string, parsed.
    """

    root: str
    locale: Locale
    query: Mapping[str, Sequence[str]]


@runtime_checkable
class View(Protocol):
    """The value an entry point in `digline.views` loads to."""

    def render(self, context: ViewContext) -> str:
        """The body of the page: markup, escaped by the view."""
        ...


@dataclass(frozen=True, slots=True)
class MenuEntry:
    """One view another package added, as the menu shows it: its name, and the
    distribution that declared it."""

    name: str
    package: str


def address(name: str) -> str:
    """Where the view named `name` is served."""
    return f"/x/{name}/"
