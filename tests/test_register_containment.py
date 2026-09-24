"""Finding 1: `digline register` writes outside the store on the first write.

`append_register` reaches its containment check only inside `if joined:`, and
`joined` requires the register file to already exist and be non-empty. The call
is not there to check containment: it is there to decide whether the previous
line needs a newline. Containment is a side effect of a formatting question,
conditioned on the wrong thing.

So the check is skipped **exactly once per register, on the write that creates
the file** — the ordinary first use. It is not that a dangling symlink evades a
guard; on the creating path there is no guard to evade. Every later write is
checked correctly, which is why this is invisible to anyone testing an
established register.

`_inside()` is the 0.7.2 fix (GHSA-j878-2v6m-m4vx), and `SECURITY.md` draws the
line this sits on: *"a path that escapes without any race at all — a symlink
sitting in the store, checked once, read once, no timing involved"* is **not**
covered by the filesystem-race exemption. This is that, on the write side.

The capability assumed is landing a file under `.digline/<tenant>/`, with no code
execution anywhere: `register/` is committed — the generated `.gitignore`
excludes only `*/runs/` — so a pull request carries the link and the victim's
action is reviewing it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests._helpers import cli, git, run_key

from digline.store import FileResultStore

TENANT = "acme-bank"
SUITE = "qa"


def test_git_carries_a_planted_symlink(repo: Path, tmp_path: Path) -> None:
    """The premise of the two tests below, checked rather than asserted in prose.

    If git stored the link's target as ordinary file content, every finding here
    would need a local attacker instead of a pull request, which is a different
    severity and a different advisory.
    """
    key = run_key(repo)
    cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)

    store = FileResultStore(repo)
    register = store.register_path(TENANT, SUITE)
    register.parent.mkdir(parents=True, exist_ok=True)
    register.symlink_to(tmp_path / "outside" / "victim.jsonl")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "add a register")

    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-s", "--", ".digline"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "120000" in listed, (
        "git did not record the planted register as a symlink, so the "
        f"pull-request vector does not hold:\n{listed}"
    )
    # The control: the store is committed at all. `*/runs/` is ignored, the rest
    # is not, and a change to that gitignore would quietly end this vector.
    assert "baselines/qa.json" in listed, f"the baseline is not committed:\n{listed}"


def test_the_register_is_not_appended_outside_the_store(
    repo: Path, tmp_path: Path
) -> None:
    """Finding 1. `append_register` gates `_inside` on the file existing.

        joined = path.exists() and path.stat().st_size > 0
        if joined:
            joined = not self._inside(path, "register").read_bytes()...

    A **dangling** link makes `path.exists()` false, so the containment check
    never runs, and the `os.open` that follows has no `O_NOFOLLOW`.
    """
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    second = run_key(repo)

    store = FileResultStore(repo)
    register = store.register_path(TENANT, SUITE)
    register.parent.mkdir(parents=True, exist_ok=True)

    outside = tmp_path / "outside" / "victim.jsonl"
    outside.parent.mkdir(parents=True)
    assert not outside.exists(), "the target must not exist: that is the gap"
    register.symlink_to(outside)

    done = cli(
        repo,
        "register",
        "--suite",
        "suite_qa.py",
        "--run",
        second,
        "--disposition",
        "accepted",
    )

    assert not outside.exists(), (
        f"`digline register` created {outside}, outside the store, and exited "
        f"{done.returncode} without saying so. Content:\n"
        f"{outside.read_text()[:300] if outside.exists() else ''}"
    )
