"""The state of a suite, whole, in `digline view`. (ADR 0066 §1)

From a first use outside the project, on an application with a judged suite:
nothing showed the suite's state whole. The page puts side by side what each
command already says, and computes nothing of its own, so each fact here is
held against the command that says it, on the same store:

- the next step, the newest run and the checks no case is asked, against
  `digline where --json`;
- the recordings waiting, against `digline record status --suite --json`;
- the reviewed answers by yes and no, against the counts `digline suggest
  --assist` sends, which now read the same function;
- the reference in force and the cases excluded at its promotion, against
  the reference the store holds.

And the page as served, beside the views ADR 0061 §6 tests in
`tests/test_view_recorder.py`, where its address is one of `views()`: it
reads, it writes nothing, a POST is the 404 of an unknown path on either
server, and it answers only to the server's own name, on 127.0.0.1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli
from tests.test_exclude_at_promotion import KEPT, SAID_NO, promote, ran, write
from tests.test_view_rebinding import REBOUND, request
from tests.test_view_recorder import (
    loaded,
    serving,
    text_of,
)
from tests.test_view_recorder import (
    root as root,  # noqa: F401 — the fixture, by its name
)

from digline.cli import recorder_pages
from digline.cli.view import HOST
from digline.core.run import Exclusion
from digline.host import import_elect, import_listing, load_suite, suite_state
from digline.host.assistant import material
from digline.host.state import CaseChecks, SuiteState
from digline.report.pages import state_address
from digline.run.suite import ReviewedCounts, reviewed_counts
from digline.wire.where import Where

AT = "2026-11-13T09:00:00+00:00"


def _where(root: Path, suite: str) -> dict[str, object]:
    done = cli(root, "where", "--tenant", "acme", "--suite", suite, "--json")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _status(root: Path, suite: str) -> dict[str, object]:
    done = cli(root, "record", "status", "--suite", suite, "--json")
    assert done.returncode == 0, done.stderr
    [tenant] = json.loads(done.stdout)["tenants"]
    [entry] = [s for s in tenant["recordings"]["suites"] if s["suite"] == "triage"]
    return entry


def reviewed(root: Path) -> None:
    """Three answers reviewed through the import's own path: two good, one
    bad, so that a count that swapped the two would be seen."""
    found = loaded(root)
    listing = import_listing(root, found.suite, found.module, "acme")
    electable = [answer.id for answer in listing.answers if answer.electable]
    assert len(electable) >= 3, electable
    import_elect(listing, good=electable[:2], bad=[electable[2]], by="Ada")


# -- each fact, against the command that says it ----------------------------- #


def test_the_next_step_and_the_checks_no_case_is_asked_are_where_s(
    root: Path,
) -> None:
    found = loaded(root)
    state = suite_state(root, found.suite, found.module)
    said = _where(root, "suites/suite.py")
    assert state.where.state == said["state"]
    assert state.where.count == said["count"]
    assert list(state.idle_checks) == said["idle_checks"]


def test_the_recordings_waiting_are_record_status_s(root: Path) -> None:
    reviewed(root)
    found = loaded(root)
    state = suite_state(root, found.suite, found.module)
    said = _status(root, "suites/suite.py")
    assert state.recordings is not None
    assert state.recordings.imported == said["imported"]
    assert state.recordings.since_last_import == said["since_last_import"]
    assert state.recordings.under_earlier_setups == said["under_earlier_setups"]


def test_the_reviewed_answers_are_counted_as_suggest_counts_them(
    root: Path,
) -> None:
    reviewed(root)
    found = loaded(root)
    state = suite_state(root, found.suite, found.module)
    assert state.reviewed == ReviewedCounts(good=2, bad=1)
    answers = [c for c in found.suite.cases if c.reviewed_answer is not None]
    given = material(
        suite="triage",
        regime="public",
        eligible=(),
        reviewed=answers,
        checks=(),
        declared=(),
    )
    counts = json.loads(given.prompt)["counts"]
    assert (counts["reviewed_yes"], counts["reviewed_no"]) == (2, 1)


def test_a_case_of_another_kind_counts_in_neither() -> None:
    """The control for the count: a case that is not a reviewed answer."""
    from digline.run import Case

    assert reviewed_counts([Case(id="plain")]) == ReviewedCounts(good=0, bad=0)


def test_each_case_is_asked_the_checks_the_driver_asks(tmp_path: Path) -> None:
    """A plain case is asked every check; a reviewed answer the one it names
    (ADR 0059 §1), which is what `checks_asked` reads off the dispatch."""
    write(tmp_path, KEPT, SAID_NO)
    suite, found = load_suite(str(tmp_path / "suite.py"), root=tmp_path)
    state = suite_state(tmp_path, suite, found.module)
    assert state.cases == (
        CaseChecks("kept", ("llm_rubric", "agrees")),
        CaseChecks("said-no", ("llm_rubric",)),
    )


@pytest.fixture
def excluded(tmp_path: Path) -> tuple[Path, str]:
    """ADR 0065's story: a run, the reviewed no removed from the suite, and
    the reference promoted without it, by name."""
    write(tmp_path, KEPT, SAID_NO)
    key = ran(tmp_path)
    write(tmp_path, KEPT)
    done = promote(tmp_path, key, "--exclude", "said-no", "--by", "Ada")
    assert done.returncode == 0, done.stderr
    return tmp_path, key


def test_the_newest_run_and_the_reference_are_where_s_and_the_store_s(
    excluded: tuple[Path, str],
) -> None:
    root, key = excluded
    suite, found = load_suite(str(root / "suite.py"), root=root)
    state = suite_state(root, suite, found.module)
    said = _where(root, "suite.py")
    # The run's own code, which `where` reads: the judge contradicted the
    # person on the case the reference leaves out, so the run exits 1.
    assert state.newest is not None
    assert state.newest == (said["run_key"], said["run_exit_code"])
    assert state.newest[0] == key
    assert state.baseline_key is not None
    reference = json.loads(
        (root / ".digline" / "acme" / "baselines" / "support.json").read_text("utf-8")
    )
    assert state.promoted_at == reference["promoted_at"]
    [item] = state.excluded
    assert (item.case_id, item.by) == ("said-no", "Ada")


def test_the_page_says_the_exclusion_in_the_run_list_s_sentence(
    excluded: tuple[Path, str],
) -> None:
    root, _ = excluded
    suite, found = load_suite(str(root / "suite.py"), root=root)
    page = recorder_pages.state_page(
        suite_state(root, suite, found.module),
        suite="support",
        suite_arg="suite.py",
        root=[],
        locale="en",
    )
    assert (
        "1 case was excluded at promotion from the reference: said-no, by Ada."
        in text_of(page)
    )


# -- the page, a pure function ----------------------------------------------- #


def state(**changes: object) -> SuiteState:
    fields: dict[str, object] = {
        "where": Where("never_run", "acme", count=0, suite="triage"),
        "cases": (
            CaseChecks("by-hand", ("llm_rubric",)),
            CaseChecks("set-aside", ()),
        ),
        "reviewed": ReviewedCounts(good=3, bad=2),
        "idle_checks": ("contains",),
        "newest": None,
        "baseline_key": None,
        "baseline_refused": "",
        "promoted_at": None,
        "excluded": (),
        "recordings": None,
    }
    fields.update(changes)
    return SuiteState(**fields)  # pyright: ignore[reportArgumentType]


def page_of(found: SuiteState, locale: str = "en") -> str:
    return recorder_pages.state_page(
        found,
        suite="triage",
        suite_arg="suites/suite.py",
        root=[],
        locale=locale,  # pyright: ignore[reportArgumentType]
    )


def test_the_page_says_each_fact_in_order() -> None:
    said = text_of(page_of(state()))
    order = [
        "2 case(s), each with the checks a run asks of it.",
        "by-hand",
        "none: it is suspended",
        "Checks that judge no case: contains",
        "3 said good, 2 said bad.",
        "The suite has never run.",
        "No reference yet: no run has been promoted.",
        "Tenant acme holds no recording of this suite.",
        "The next step",
        "digline run --suite suites/suite.py",
    ]
    at = [said.index(item) for item in order]
    assert at == sorted(at), list(zip(order, at, strict=True))


def test_the_next_step_is_where_s_command_shown_and_never_a_form() -> None:
    page = page_of(state())
    assert "digline run --suite suites/suite.py" in text_of(page)
    assert "<form" not in page


def test_a_reference_and_the_newest_run_are_said_with_their_keys() -> None:
    said = text_of(
        page_of(
            state(
                newest=("run-b", 1),
                baseline_key="run-a",
                promoted_at=AT,
                excluded=(Exclusion("said-no", "Ada", AT),),
            )
        )
    )
    assert "run-b, exit code 1." in said
    assert f"run-a, promoted {AT}." in said
    assert "excluded at promotion from the reference: said-no, by Ada" in said


def test_a_name_from_the_suite_is_text() -> None:
    page = page_of(state(cases=(CaseChecks("<b>x</b>", ("llm_rubric",)),)))
    assert "<b>x</b>" not in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_the_page_speaks_italian() -> None:
    said = text_of(page_of(state(), "it"))
    assert "Lo stato della suite triage" in said
    assert "3 dette buone, 2 dette cattive." in said


# -- served: 127.0.0.1, reads, no POST --------------------------------------- #


def test_the_server_binds_127_0_0_1_and_nothing_else() -> None:
    assert HOST == "127.0.0.1"


def test_the_page_answers_its_own_name_and_refuses_a_rebound_one(
    root: Path,
) -> None:
    address = state_address("acme", "triage")
    with serving(root, allow_record=True) as (served, _launch):
        ok, page = request(served.port, "GET", address, host=f"127.0.0.1:{served.port}")
        assert ok == 200, page
        status, _ = request(
            served.port, "GET", address, host=f"{REBOUND}:{served.port}"
        )
        assert status != 200


def test_another_tenant_or_suite_is_no_page(root: Path) -> None:
    with serving(root, allow_record=False) as (served, _launch):
        assert served.ask("GET", state_address("globex", "triage")).status == 404
        assert served.ask("GET", state_address("acme", "other")).status == 404


def test_the_run_list_and_every_menu_link_the_state(root: Path) -> None:
    address = state_address("acme", "triage")
    with serving(root, allow_record=False) as (served, _launch):
        runs = served.ask("GET", "/").body
        assert runs.count(f'href="{address}?locale=') == 2  # the menu and the head
        assert ">The suite</a>" in runs
