"""One declared path, resolved once: ADR 0045's test plan, entries 1 to 8 and 10.

#481's layout throughout, built by `tests/_one_path.py`. Entries 6 and 9
reach the MCP server and pytest-digline in those packages' own tests.

Every test that runs a command sets its working directory: it is the variable
under test, and one inherited from the runner would decide the answer.
Windows is not in this plan (entry 12): no runner here has it, and that is
said so its absence is not read as a pass.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from tests._helpers import cli
from tests._one_path import (
    ANCHORED,
    BARE,
    RELATIVE,
    fake_anthropic,
    layout,
    recorded,
    sent,
    sha,
    toml_layout,
)

from digline.core import Contains
from digline.host import UsageError, read_artifacts
from digline.run import Case, Suite
from digline.wire.contract import EXIT_OK, EXIT_USAGE


def run(
    tmp_path: Path, cwd: str, suite: str | None = None
) -> subprocess.CompletedProcess[str]:
    """`digline run` from `tmp_path / cwd`, suite and root named absolute
    unless `suite` says otherwise."""
    root = tmp_path / "R"
    return cli(
        tmp_path / cwd,
        "run",
        "--suite",
        suite or str(root / "eval" / "suite.py"),
        "--root",
        str(root),
    )


# --------------------------------------------------------------------------- #
# 1, 2, 3: the divergent case and the agreed one
# --------------------------------------------------------------------------- #


def test_1_from_the_root_the_run_records_the_file_it_sent(tmp_path: Path) -> None:
    """Red on `main`, which sends `R/prompt.txt` and records `R/eval/prompt.txt`
    under `eval/prompt.txt`."""
    root = layout(tmp_path)
    done = run(tmp_path, "R")
    assert done.returncode == EXIT_OK, done.stderr
    assert sent(tmp_path) == ["text of R\n"]
    assert recorded(root, done.stdout.strip()) == {
        "prompt.txt": {"sha": sha(root / "prompt.txt"), "text": "text of R\n"}
    }


def test_2_from_outside_the_run_is_refused_and_nothing_is_sent(
    tmp_path: Path,
) -> None:
    """Red on `main`, which exits 0 and sends `OUT/prompt.txt`."""
    root = layout(tmp_path)
    done = run(tmp_path, "OUT")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "the target Stub of suite 'qa'" in done.stderr
    assert "outside the perimeter" in done.stderr
    assert "(ADR 0042 §2)" in done.stderr
    assert sent(tmp_path) == []
    assert not list((root / ".digline").rglob("runs/*/*.json"))


@pytest.mark.parametrize(
    ("cwd", "prompt"), [("R/eval", BARE), ("R", ANCHORED), ("OUT", ANCHORED)]
)
def test_3_where_the_two_resolutions_agreed_nothing_moves(
    tmp_path: Path, cwd: str, prompt: str
) -> None:
    """Green on `main` too, by construction: it guards that the repair moves
    nothing where the two resolutions agreed. The name and digest are those
    `main` records: `eval/prompt.txt`, the suite's own file."""
    root = layout(tmp_path, prompt=prompt)
    done = run(tmp_path, cwd)
    assert done.returncode == EXIT_OK, done.stderr
    assert sent(tmp_path) == ["text of R/eval\n"]
    assert recorded(root, done.stdout.strip()) == {
        "eval/prompt.txt": {
            "sha": sha(root / "eval" / "prompt.txt"),
            "text": "text of R/eval\n",
        }
    }


# --------------------------------------------------------------------------- #
# 4: what `HasArtifacts` requires
# --------------------------------------------------------------------------- #


def _suite() -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
    )


class Answering:
    """A target that answers through `HasArtifacts` whatever it is given."""

    def __init__(self, *paths: Path) -> None:
        self._paths = paths

    def artifacts(self) -> Sequence[Path]:
        return self._paths


def test_4_a_relative_answer_is_refused_naming_the_target(tmp_path: Path) -> None:
    """Red on `main`, which joins the relative answer to the suite's directory
    and records it."""
    (tmp_path / "prompt.txt").write_text("x", "utf-8")
    with pytest.raises(UsageError) as caught:
        read_artifacts(_suite(), Answering(Path("prompt.txt")), tmp_path)
    message = str(caught.value)
    assert "the target Answering of suite 'qa'" in message
    assert "prompt.txt, a relative path" in message
    assert "(ADR 0045 §5)" in message


def test_4_the_same_target_answering_absolute_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "prompt.txt").write_text("x", "utf-8")
    found = read_artifacts(_suite(), Answering(tmp_path / "prompt.txt"), tmp_path)
    assert set(found) == {"prompt.txt"}


def test_4_the_refusal_comes_before_any_file_is_read(tmp_path: Path) -> None:
    """A suite artifact that is not a file would refuse too: the target's
    relative answer is what is named, because it is checked first."""
    suite = Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
        artifacts=[Path("absent.txt")],
    )
    with pytest.raises(UsageError, match="a relative path"):
        read_artifacts(suite, Answering(Path("prompt.txt")), tmp_path)


def test_4_through_the_command_line(tmp_path: Path) -> None:
    """Entry 9's command-line leg of entry 4: the refusal reaches the person
    who ran the command, before the run starts."""
    root = layout(tmp_path, target=RELATIVE)
    done = run(tmp_path, "R")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "the target Naming of suite 'qa'" in done.stderr
    assert "a relative path" in done.stderr
    assert not list((root / ".digline").rglob("runs/*/*.json"))


# --------------------------------------------------------------------------- #
# 5: resolved when it is read, not when it is asked
# --------------------------------------------------------------------------- #


def test_5_the_path_is_the_one_read_whatever_the_directory_becomes(
    tmp_path: Path,
) -> None:
    """The suite builds its target from `R`, then moves the process to `OUT`
    before the run asks. Red if the resolution is moved to `artifacts()`: the
    answer would then name `OUT/prompt.txt`, which is outside and refused."""
    root = layout(tmp_path, after=f"os.chdir({str(tmp_path / 'OUT')!r})")
    done = run(tmp_path, "R")
    assert done.returncode == EXIT_OK, done.stderr
    assert sent(tmp_path) == ["text of R\n"]
    assert set(recorded(root, done.stdout.strip())) == {"prompt.txt"}


# --------------------------------------------------------------------------- #
# 6: the TOML form
# --------------------------------------------------------------------------- #


@pytest.fixture
def anthropic(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """The prompts a fake Anthropic endpoint was sent; the command inherits the
    environment that points the SDK at it."""
    pytest.importorskip("digline_anthropic")
    with fake_anthropic() as (seen, url):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", url)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key")
        yield seen


@pytest.mark.parametrize(
    ("cwd", "spec"),
    [
        ("R", "eval/suite.toml"),
        ("OUT", "../R/eval/suite.toml"),
        ("R/eval", "suite.toml"),
        ("OUT", None),
    ],
)
def test_6_a_toml_target_sends_and_records_the_suite_s_prompt(
    tmp_path: Path, anthropic: list[str], cwd: str, spec: str | None
) -> None:
    """Red on `main` for the first two: exit 64 on `R/eval/eval/prompt.md`, the
    suite's directory joined to a path that already held it. The MCP server's
    half of this entry is in digline-mcp's tests."""
    root = toml_layout(tmp_path)
    done = cli(
        tmp_path / cwd,
        "run",
        "--suite",
        spec or str(root / "eval" / "suite.toml"),
        "--root",
        str(root),
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert anthropic == ["text of R/eval\n"]
    assert recorded(root, done.stdout.strip()) == {
        "eval/prompt.md": {
            "sha": sha(root / "eval" / "prompt.md"),
            "text": "text of R/eval\n",
        }
    }


# --------------------------------------------------------------------------- #
# 7: a pin on a target's prompt
# --------------------------------------------------------------------------- #


def test_7_an_anchored_target_prompt_is_pinned_from_the_root(tmp_path: Path) -> None:
    root = layout(tmp_path, prompt=ANCHORED, pinned='Path("prompt.txt")')
    done = run(tmp_path, "R")
    assert done.returncode == EXIT_OK, done.stderr
    (path,) = (root / ".digline").rglob(f"runs/*/{done.stdout.strip()}.json")
    assert json.loads(path.read_text("utf-8"))["pinned"] == ["eval/prompt.txt"]


def test_7_a_bare_target_prompt_is_refused_by_read_pinned_from_the_root(
    tmp_path: Path,
) -> None:
    """ADR 0045 §7, measured: inside the perimeter, with a file of that name,
    `read_pinned` refuses it, and nothing is sent. Red on `main`, which keyed
    the target's prompt from the suite's directory, matched the pin, and ran,
    sending `R/prompt.txt`."""
    root = layout(tmp_path, pinned='Path("prompt.txt")')
    done = run(tmp_path, "R")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert (
        "pins prompt.txt (as eval/prompt.txt), which this run records no "
        "artifact for" in done.stderr
    )
    assert sent(tmp_path) == []
    assert not list((root / ".digline").rglob("runs/*/*.json"))


# --------------------------------------------------------------------------- #
# 8: one normalization
# --------------------------------------------------------------------------- #


def test_8_a_link_inside_is_recorded_under_the_file_it_names(tmp_path: Path) -> None:
    """The boundary checks the file the link points at, and the name is that
    file's. Green on `main`, which normalized the same path twice. The mutation
    bites: compute the name from the path before normalization and this reads
    `link.txt`."""
    (tmp_path / "real.txt").write_text("real", "utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    found = read_artifacts(_suite(), Answering(tmp_path / "link.txt"), tmp_path)
    assert set(found) == {"real.txt"}


def test_8_a_link_pointing_outward_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "R"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("TOKEN=abc123", "utf-8")
    (root / "link.txt").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(UsageError) as caught:
        read_artifacts(_suite(), Answering(root / "link.txt"), root)
    assert f"which resolves to {(tmp_path / 'outside.txt').resolve()}" in str(
        caught.value
    )


def test_the_resolved_path_is_named_only_where_it_differs(tmp_path: Path) -> None:
    """An absolute answer that is its own resolution is said once."""
    root = tmp_path / "R"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("x", "utf-8")
    outside = (tmp_path / "outside.txt").resolve()
    with pytest.raises(UsageError) as caught:
        read_artifacts(_suite(), Answering(outside), root)
    assert "which resolves to" not in str(caught.value)
    assert str(caught.value).count(str(outside)) == 1


# --------------------------------------------------------------------------- #
# 10: a reference promoted where the two resolutions agreed
# --------------------------------------------------------------------------- #


def test_10_a_reference_from_the_agreed_case_compares_clean(tmp_path: Path) -> None:
    """A guard, green on `main` by construction. The half that needs `main` —
    promoted there, compared here — cannot run inside one tree; it was
    measured by hand with #481 and is reported there."""
    root = layout(tmp_path)
    first = run(tmp_path, "R/eval")
    assert first.returncode == EXIT_OK, first.stderr
    suite = str(root / "eval" / "suite.py")
    promoted = cli(
        root,
        "promote",
        "--suite",
        suite,
        "--run",
        first.stdout.strip(),
        "--replacing",
        "none",
    )
    assert promoted.returncode == EXIT_OK, promoted.stderr
    later = run(tmp_path, "R/eval")
    compared = cli(
        root, "compare", "--suite", suite, "--run", later.stdout.strip(), "--json"
    )
    assert compared.returncode == EXIT_OK, compared.stderr
    assert json.loads(compared.stdout)["artifacts_changed"] is False
