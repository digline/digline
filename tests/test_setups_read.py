"""Recordings under an earlier setup, said by `record status` and at the head
of `record import`.

Found in a first use outside the project, on a Java application with a judged
suite: a variable in the system prompt made a setup per value, and the import
listed most answers as not electable, one by one, with nothing at the head to
say why so many were. Both commands now say how many recordings sit under an
earlier setup, which setups those are, and which one is in force, from the
same reading the import makes (`setups_read`).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests._helpers import cli
from tests.test_where import SETUP_1, SETUP_2, TENANT, record, write_suite

from digline.core.recording import setup_digest_of

#: Two answers under the first setup, then one under the second, which is the
#: newest and so the setup in force.
EARLY = (
    ("refund?", "in 14 days", SETUP_1, "2026-11-03T08:01:00+00:00"),
    ("hours?", "nine to five", SETUP_1, "2026-11-03T08:02:00+00:00"),
)
LATE = (("refund?", "in 14 days, kindly", SETUP_2, "2026-11-04T08:00:00+00:00"),)

OLD = setup_digest_of(SETUP_1)[:8]
NEW = setup_digest_of(SETUP_2)[:8]
SAID = (
    f"2 recordings under an earlier setup {OLD}: an answer recorded only there "
    f"cannot be imported; in force: {NEW}"
)


def test_status_says_how_many_are_under_an_earlier_setup(tmp_path: Path) -> None:
    write_suite(tmp_path)
    record(tmp_path, *EARLY, *LATE)
    done = cli(tmp_path, "record", "status", "--tenant", TENANT)
    assert done.returncode == 0, done.stderr
    assert f"    {SAID}" in done.stdout.splitlines()

    as_json = cli(tmp_path, "record", "status", "--tenant", TENANT, "--json")
    [tenant] = json.loads(as_json.stdout)["tenants"]
    [suite] = tenant["recordings"]["suites"]
    assert suite["setups_in_force"] == {"single_calls": NEW, "episodes": None}
    assert (suite["under_earlier_setups"], suite["earlier_setups"]) == (2, [OLD])


def test_the_import_says_it_at_its_head_before_any_answer(tmp_path: Path) -> None:
    write_suite(tmp_path)
    record(tmp_path, *EARLY, *LATE)
    done = cli(
        tmp_path, "record", "import", "--tenant", TENANT, "--suite", "suites/suite.py"
    )
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    head = lines.index(f"  {SAID}")
    assert head < next(i for i, line in enumerate(lines) if "cap-" in line)

    as_json = cli(
        tmp_path,
        "record",
        "import",
        "--tenant",
        TENANT,
        "--suite",
        "suites/suite.py",
        "--json",
    )
    listing = json.loads(as_json.stdout)
    assert (listing["under_earlier_setups"], listing["earlier_setups"]) == (2, [OLD])


def test_nothing_is_said_where_every_recording_is_under_the_setup_in_force(
    tmp_path: Path,
) -> None:
    write_suite(tmp_path)
    record(tmp_path, *EARLY)
    status = cli(tmp_path, "record", "status", "--tenant", TENANT)
    listing = cli(
        tmp_path, "record", "import", "--tenant", TENANT, "--suite", "suites/suite.py"
    )
    for done in (status, listing):
        assert done.returncode == 0, done.stderr
        assert "under an earlier setup" not in done.stdout
