"""Refuse to release a commit that `main` does not contain.

`main` is protected: nothing lands there without the two `gates` checks having
passed on the ref. A tag is not: anybody who can push can put `v0.21.0` on a
commit of an unmerged branch, and `publish.yml` would build it, upload it and
spend the version number — the one thing in the release that cannot be undone.
So both release workflows start with this, and every job that builds or
publishes waits for it (`tests/test_release_from_main.py` holds the wiring).

    python3 .github/on_main.py <commit> <label>

`<commit>` is anything `git rev-parse` resolves — the workflow passes the
checked-out `HEAD` — and `<label>` is what the messages call it, the tag name.
It runs in a full clone (`fetch-depth: 0`), fetches `main` itself and asks
`git merge-base --is-ancestor`.

**It must not refuse a legitimate release over a race**, because the first
false red is the moment somebody switches it off. So a commit that is not on
`main` yet is not refused at once:

1. it fetches again, `ATTEMPTS` times, `INTERVAL` seconds apart — a merge
   takes a moment to show on a fresh fetch;
2. then it asks the API which pull requests carry the commit
   (`GET /repos/{repo}/commits/{sha}/pulls`);
3. and refuses with the one of three messages that says what to do:

   - *not on main* — no pull request into `main` carries it, or only closed,
     unmerged ones: tag the merge commit instead;
   - *head of open PR #N* — merge it, then tag the merge commit or re-run;
   - *on merged PR #N but main does not show it yet* — re-run.

Exit 0 on `main`, 1 refused. Standard library only: like the other scripts
here it runs under the runner's bare `python3`. Reads `GITHUB_REPOSITORY`,
`GH_TOKEN` (optional on a public repository), `API` (default
https://api.github.com), `BRANCH` (default `main`), `ATTEMPTS` (default 3) and
`INTERVAL` (default 20).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

API = os.environ.get("API", "https://api.github.com").rstrip("/")
BRANCH = os.environ.get("BRANCH", "main")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def on_branch(sha: str) -> bool:
    """Fetch the branch afresh and ask whether it contains `sha`.

    The refspec is written out: whether a bare `git fetch origin main` moves
    `origin/main` depends on how the clone was configured, and a stale
    `origin/main` is exactly the false red this is careful about.
    """
    fetched = git(
        "fetch",
        "--quiet",
        "origin",
        f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}",
    )
    if fetched.returncode != 0:
        print(f"fetching {BRANCH} failed: {fetched.stderr.strip()}", file=sys.stderr)
        return False
    return git("merge-base", "--is-ancestor", sha, f"origin/{BRANCH}").returncode == 0


def pulls(sha: str) -> list[dict[str, Any]] | str:
    """The pull requests GitHub associates with `sha`, or why it could not say."""
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{API}/repos/{repository}/commits/{sha}/pulls", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            found: list[dict[str, Any]] = json.loads(response.read())
            return found
    except urllib.error.HTTPError as exc:
        # 422 is GitHub's answer for a commit it has never been pushed: no pull
        # request can carry it, which is an answer and not a failure.
        if exc.code == 422:
            return []
        return f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return str(exc)


def verdict(label: str, sha: str, found: list[dict[str, Any]] | str) -> tuple[str, str]:
    """(title, message) for a commit that is not on the branch.

    Pure, so every message is tested without a network: the three are what a
    person reads at the worst moment of a release, and each has to say what to
    do next.
    """
    carrying = (
        []
        if isinstance(found, str)
        else [pull for pull in found if pull.get("base", {}).get("ref") == BRANCH]
    )
    merged = [pull for pull in carrying if pull.get("merged_at")]
    if merged:
        number = merged[0]["number"]
        return (
            f"on merged PR #{number} but {BRANCH} does not show it yet: re-run",
            f"{label} ({sha}) is on merged PR #{number}, but {BRANCH} does not "
            f"show it yet. Re-run this workflow in a minute; nothing needs re-tagging.",
        )
    open_ = [pull for pull in carrying if pull.get("state") == "open"]
    if open_:
        pull = open_[0]
        number = pull["number"]
        where = (
            "the head of" if pull.get("head", {}).get("sha") == sha else "a commit of"
        )
        return (
            f"head of open PR #{number}: merge it, then tag the merge commit or re-run",
            f"{label} ({sha}) is {where} open PR #{number}, which is not merged. "
            f"Merge it, then tag the merge commit, or re-run this workflow once "
            f"{BRANCH} contains it.",
        )
    because = (
        f" (could not ask which pull request carries it: {found};"
        " if one was merged, re-run)"
        if isinstance(found, str)
        else ""
    )
    return (
        f"not on {BRANCH}",
        f"{label} ({sha}) is not on {BRANCH}, and no pull request into {BRANCH} "
        f"is carrying it{because}. A release is tagged on its merge commit, "
        f"after the pull request has merged: delete this tag and tag that "
        f"commit (RELEASING.md, 'Re-doing a tag').",
    )


def main(commit: str, label: str) -> int:
    resolved = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    if resolved.returncode != 0:
        print(f"::error title=not on {BRANCH}::{label}: {commit} is not a commit here")
        return 1
    sha = resolved.stdout.strip()
    attempts = max(1, int(os.environ.get("ATTEMPTS", "3")))
    interval = float(os.environ.get("INTERVAL", "20"))
    for attempt in range(1, attempts + 1):
        if on_branch(sha):
            print(f"{label} ({sha}) is on {BRANCH}.")
            return 0
        if attempt < attempts:
            print(
                f"{sha} is not on origin/{BRANCH} yet, fetching again in {interval:g}s"
            )
            time.sleep(interval)
    title, message = verdict(label, sha, pulls(sha))
    print(f"::error title={title}::{message}")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: on_main.py <commit> <label>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
