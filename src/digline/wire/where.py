"""Where a project is, for a program and for the two front ends that lay it
out: the states `digline.host.where` reads, the value it returns, the command
for each state's next step and the pages that say more. (ADR 0011 §6)

The value is built in the host, which reads the store; here it is only held
and rendered. `where_command` is the next step as a person types it, shown and
never run, and `where_json` the same reading for a program: `digline where
--json` prints it, and the MCP server returns it. The view lays the same value
out as a page.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from digline.wire.contract import OUTPUT_VERSION
from digline.wire.recordings import Shape, shape_json
from digline.wire.text import neutralised

__all__ = [
    "DOCS_SITE",
    "NO_SUITE_ARG",
    "STATES",
    "WHERE_DOCS",
    "State",
    "Where",
    "docs_url",
    "where_command",
    "where_json",
]

State = Literal[
    "nothing_recorded",
    "recording_off",
    "unassigned",
    "no_suite_yet",
    "to_import",
    "never_run",
    "judge_disagrees",
    "green_without_red",
    "new_setup",
    "nothing_to_do",
    "last_run_red",
]

#: Every state, in the order `where` asks them.
STATES: tuple[State, ...] = (
    "nothing_recorded",
    "recording_off",
    "unassigned",
    "no_suite_yet",
    "to_import",
    "never_run",
    "judge_disagrees",
    "green_without_red",
    "new_setup",
    "nothing_to_do",
    "last_run_red",
)


@dataclass(frozen=True, slots=True)
class Where:
    """One state and the facts that put the project in it.

    `count` is the number the state's sentence names: recordings, calls,
    reviewed answers, disagreements, answers or cases, by state. `suite` is
    the suite the state is about, `None` where it is about the tenant.
    `shapes` are the output shapes of `no_suite_yet`, each with its count.
    `run_key` and `exit_code` are the newest run's, where the state reads it;
    `last_import` the newest `examined_through` a case of the suite holds.
    """

    state: State
    tenant: str
    count: int = 0
    suite: str | None = None
    shapes: tuple[tuple[Shape, int], ...] = ()
    run_key: str | None = None
    exit_code: int | None = None
    last_import: str | None = None
    #: Whether the suite declares a capture source: `--from _unassigned` is
    #: refused without one. `None` where no suite was given.
    capture: bool | None = None


#: Where the documentation is read, on the site that publishes `docs/`.
DOCS_SITE = "https://digline.dev/product/"

#: The pages that say more about each state, by their path under `docs/`
#: and the anchor on the page; `tests/test_where_page.py` holds each to a
#: page that exists and an anchor it has.
WHERE_DOCS: dict[State, tuple[tuple[str, str], ...]] = {
    "nothing_recorded": (("record.md", ""),),
    "recording_off": (("record.md", "switching-it-on"),),
    "unassigned": (("record.md", "from-recordings-to-cases-digline-record-import"),),
    "no_suite_yet": (("proposing-a-suite.md", ""), ("declarative.md", "capture")),
    "to_import": (("record.md", "from-recordings-to-cases-digline-record-import"),),
    "never_run": (("guide.md", ""),),
    "judge_disagrees": (("calibration.md", ""), ("explain.md", "")),
    "green_without_red": (("proposing-a-suite.md", ""),),
    "new_setup": (("record.md", "comparing-setups-digline-record-compare"),),
    "nothing_to_do": (("view.md", ""),),
    "last_run_red": (("explain.md", ""),),
}


#: What a command for a suite says where the server was started without one.
NO_SUITE_ARG = "<suite file>"


def where_command(
    found: Where, suite_arg: str | None, root: Sequence[str]
) -> list[str]:
    """The command for the state's next step, as a person types it, or none
    where the step is an edit: a suite written, a counterexample added. It is
    shown and never run: no button on this page launches a run or a gate.
    Without a suite it names the suite's file as the person's to fill in."""
    tenant = ["--tenant", found.tenant]
    suite = ["--suite", suite_arg or NO_SUITE_ARG]
    words: dict[State, list[str]] = {
        "nothing_recorded": ["record", "on", *tenant],
        "recording_off": ["record", "on", *tenant],
        "unassigned": ["record", "import", *tenant, *suite, "--from", "_unassigned"],
        "to_import": ["record", "import", *tenant, *suite],
        "never_run": ["run", *suite],
        "judge_disagrees": ["explain", *suite, "--run", "latest"],
        "new_setup": ["record", "compare", *tenant, *suite],
        "last_run_red": ["explain", *suite, "--run", "latest"],
    }
    if found.state not in words:
        return []
    return ["digline", *words[found.state], *root]


def docs_url(page: str, anchor: str) -> str:
    """A page of `docs/` as the site publishes it, with its anchor."""
    slug = page.removesuffix(".md")
    return f"{DOCS_SITE}{slug}/" + (f"#{anchor}" if anchor else "")


def where_json(
    found: Where, *, suite_arg: str | None, root: Sequence[str]
) -> dict[str, object]:
    """Where the project is, for a program: the state, the counts that put it
    there, the next step's command where there is one, and the pages that say
    more. Counts, shapes, a run's key and an instant: no recorded word. No
    `exit_code` of its own: the reading is not a gate, and the newest run's
    is a field."""
    command = where_command(found, suite_arg, root)
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenant": found.tenant,
            "suite": found.suite,
            "state": found.state,
            "count": found.count,
            "shapes": [
                {**shape_json(shape), "recordings": count}
                for shape, count in found.shapes
            ],
            "run_key": found.run_key,
            "run_exit_code": found.exit_code,
            "last_import": found.last_import,
            "capture": found.capture,
            "next": {
                "command": shlex.join(command) if command else None,
                "docs": [
                    {"page": page, "anchor": anchor, "url": docs_url(page, anchor)}
                    for page, anchor in WHERE_DOCS[found.state]
                ],
            },
        }
    )
