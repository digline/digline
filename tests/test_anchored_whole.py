"""Three patterns held to the whole value: `^…$` with `match` lets a final
newline through, because `$` also matches before one. `\\A…\\Z` with
`fullmatch` does not. (The class #927 closed for a tenant's name.)

Measured before the change, for each: only the journal leg was reachable, a
file named `<key>.1\\n.jsonl` read as a leg of `<key>`. A date with a newline
was already refused by `strptime`, as not a calendar date, and `urlsplit`
drops a newline before the host reaches the pattern. Those two are held at
the pattern, which is where the next caller would meet it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.host import UsageError
from digline.host.reading import _DATE, instant  # pyright: ignore[reportPrivateUsage]
from digline.store.file_store import FileResultStore
from digline.targets.config import _HOST, endpoint_host  # pyright: ignore[reportPrivateUsage]


def test_a_date_with_a_newline_is_not_a_date() -> None:
    assert _DATE.match("2026-09-14\n") is None
    assert instant("2026-09-14", name="--since") == "2026-09-14"
    with pytest.raises(UsageError, match="neither a date"):
        instant("2026-09-14\n", name="--since")


def test_a_host_with_a_newline_is_no_host() -> None:
    assert _HOST.match("gw\n") is None
    assert endpoint_host("https://gw.example:8443/v1") == "gw.example:8443"


def test_a_journal_leg_whose_name_ends_in_a_newline_is_not_a_leg(
    tmp_path: Path,
) -> None:
    store = FileResultStore(tmp_path)
    directory = store.journal_dir("acme", "triage")
    directory.mkdir(parents=True)
    key = "2026-11-05T12-30-00-123456-00-00-0123456789abcdef"
    (directory / f"{key}.1\n.jsonl").write_text("{}\n", encoding="utf-8")
    [pending] = store.pending("acme", "triage")
    assert pending.key == f"{key}.1\n.jsonl"
    assert pending.refusal is not None
    assert "is not a journal leg" in pending.refusal
