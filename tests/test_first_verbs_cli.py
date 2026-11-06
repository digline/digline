"""The command line of the first verbs: `digline where`, `digline record
import --json` and the shape of an episode in `digline record compare
--json`. (ADR 0011 §1 and ADR 0023 §9, as noted 2026-11-06)

The stores are written by the writers digline uses, through the helpers of
`tests/test_where.py`; the commands run in a subprocess, as a person runs
them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._helpers import cli
from tests.test_where import (
    EARLY,
    REFUND_ID,
    SETUP_1,
    TENANT,
    asked,
    elect,
    record,
    write_suite,
)

from digline.core.recording import Recording, setup_digest_of
from digline.core.run import RecordedResponse, RecordedStep
from digline.host.importing import _REFUSALS  # pyright: ignore[reportPrivateUsage]
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.wire import STATES, WHERE_DOCS, docs_url
from digline.wire.recordings import REFUSAL_REASONS

SUITE = "suites/suite.py"


def printed(root: Path, *args: str) -> dict[str, Any]:
    done = cli(root, *args)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write_suite(tmp_path)
    return tmp_path


# digline where


def test_where_says_the_state_the_command_and_the_page(root: Path) -> None:
    record(root, *EARLY)
    done = cli(root, "where", "--tenant", TENANT, "--suite", SUITE)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == "2 since the last import"
    assert (
        f"The command: digline record import --tenant {TENANT} --suite {SUITE}" in lines
    )
    page, anchor = WHERE_DOCS["to_import"][0]
    assert f"The page that says more: {docs_url(page, anchor)}" in lines


def test_where_in_italian(root: Path) -> None:
    done = cli(root, "where", "--tenant", TENANT, "--locale", "it")
    assert done.returncode == 0, done.stderr
    assert "Il comando: digline record on --tenant acme" in done.stdout


def test_where_names_the_root_it_read(
    root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    done = cli(elsewhere, "where", "--tenant", TENANT, "--root", str(root), "--json")
    assert done.returncode == 0, done.stderr
    found = json.loads(done.stdout)
    assert found["next"]["command"] == (
        f"digline record on --tenant {TENANT} --root {root}"
    )


def test_where_json_holds_the_state_and_its_counts(root: Path) -> None:
    record(root, *EARLY)
    found = printed(root, "where", "--tenant", TENANT, "--suite", SUITE, "--json")
    assert found["state"] in STATES
    assert (found["state"], found["count"], found["suite"]) == (
        "to_import",
        2,
        "triage",
    )
    assert found["next"]["command"] == (
        f"digline record import --tenant {TENANT} --suite {SUITE}"
    )
    assert "exit_code" not in found


def test_where_refuses_a_suite_of_another_tenant(root: Path) -> None:
    done = cli(root, "where", "--tenant", "other", "--suite", SUITE)
    assert done.returncode == 64
    assert "does not match the suite" in done.stderr


# digline record import --json


@pytest.mark.parametrize(
    "flags",
    [("--good", REFUND_ID), ("--bad", REFUND_ID), ("--by", "Ada")],
    ids=["good", "bad", "by"],
)
def test_the_listing_for_a_program_writes_nothing(
    root: Path, flags: tuple[str, str]
) -> None:
    record(root, *EARLY)
    done = cli(
        root, "record", "import", "--tenant", TENANT, "--suite", SUITE, "--json",
        *flags,
    )  # fmt: skip
    assert done.returncode == 64
    assert "a yes or a no about an answer is a person's" in done.stderr
    assert not (root / "suites" / "captured.json").exists()


def test_the_listing_for_a_program_holds_counts_and_no_answer(root: Path) -> None:
    record(root, *EARLY)
    elect(root, good=[REFUND_ID])
    record(root, ("parcel?", "found it", SETUP_1, "2026-11-03T09:00:00+00:00"))
    found = printed(
        root, "record", "import", "--tenant", TENANT, "--suite", SUITE, "--json"
    )
    [group] = found["groups"]
    assert (group["answers"], group["recordings"]) == (3, 3)
    assert (group["good"], group["bad"], group["waiting"]) == (1, 0, 2)
    assert group["refused"] == {
        "already_in_the_file": 1,
        "earlier_setups": 0,
        "no_input": 0,
        "conversation": 0,
    }
    assert group["shape"] == {
        "episode": False,
        "kind": "text",
        "actors": [],
        "finish": None,
    }
    assert found["declaration"]["check"] == "llm_rubric"
    said = json.dumps(found)
    for text in ("in 14 days", "nine to five", "found it", "refund?", "cap-"):
        assert text not in said
    assert found["review"]["command"] == f"digline view --suite {SUITE}"


def test_the_listing_counts_a_refusal_by_its_word() -> None:
    """Each sentence `record import` refuses an answer with has the word the
    listing for a program counts it under, and no other."""
    assert tuple(_REFUSALS) == REFUSAL_REASONS


def test_without_the_flag_the_person_reads_the_answers(root: Path) -> None:
    """The control: the answers the program's listing leaves out are in the
    store, and the terminal's listing shows them to the person."""
    record(root, *EARLY)
    done = cli(root, "record", "import", "--tenant", TENANT, "--suite", SUITE)
    assert done.returncode == 0, done.stderr
    assert "in 14 days" in done.stdout


# digline record compare --json, an episode's shape


def test_an_episode_s_calls_and_models_are_on_the_wire(root: Path) -> None:
    child: dict[str, object] = {"model": "child-model"}
    own = "b" * 32
    writer = RecordingWriter(FileResultStore(root))
    for recording in (
        Recording(
            source_tenant=TENANT,
            app="support",
            suite="triage",
            case=asked("refund?"),
            setup={"child_setups": [setup_digest_of(child)]},
            setup_digest="f" * 16,
            response=RecordedResponse(
                output="in 14 days",
                kind="text",
                input="q",
                steps=(RecordedStep(index=0, actor="model", finish="end_turn"),),
            ),
            id=own,
            recorded_at="2026-11-03T08:00:00+00:00",
        ),
        Recording(
            source_tenant=TENANT,
            app="support",
            suite="triage",
            case=asked("refund?"),
            setup=child,
            setup_digest=setup_digest_of(child),
            response=RecordedResponse(output="calling", kind="text"),
            episode=own,
            recorded_at="2026-11-03T08:00:01+00:00",
        ),
    ):
        writer.write(recording)
    found = printed(
        root, "record", "compare", "--tenant", TENANT, "--suite", SUITE, "--json"
    )
    [case] = found["cases"]
    [setup] = case["setups"]
    assert (setup["calls"], setup["models"]) == ([1], ["child-model"])
    assert "in 14 days" not in json.dumps(found)
