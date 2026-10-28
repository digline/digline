"""Say whether `ci` may skip what it would only repeat, on a push to `main` and
on a merge-queue entry.

    python3 .github/queue_tested.py <sha>

The event is read from `GITHUB_EVENT_NAME`, and each has its own question.

**On a push to `main`.** The queue builds `main` plus the pull request on a
`gh-readonly-queue/main/...` ref, runs `ci` there, and then moves `main` to
**that same commit**. So the push carries a SHA the queue has already tested.
It asks the API for every `ci` run with `event=merge_group` and
`head_sha=<sha>`, reads the jobs of each one's latest attempt, and answers
`tested=true` only when one of those runs has every job named in `REPEATED`
concluded `success` and the image job `success` or `skipped`. A push that did
not come through the queue has no such run and is tested in full.

**On a merge-queue entry.** `<sha>` is the commit the queue built: a merge whose
first parent is what the entry is built on and whose second is the pull
request's head. It answers `tested=true` only when all three hold:

1. the commit's tree is the head's tree;
2. the first parent is an ancestor of the head (`compare` reads `behind_by`
   0), so `main` at the enqueue holds nothing the head lacks;
3. a `pull_request` run of `ci` on the head has the four required checks
   (`REQUIRED`) concluded `success` in its latest attempt.

A `pull_request` run does not check out the head: it checks out the head merged
into the base of that moment. Point 2 is what makes that the head's own tree:
`main` is never rewritten (the ruleset refuses a force push), so the base of
that moment is an ancestor of the first parent, and a merge with an ancestor
is the head's tree. So the tree the four checks passed on **is** the tree the
queue built, which is what point 1 then compares. Measured on the 40 pull
requests merged from #738 to #780: the three held on 15, and on all 15 the
tree the head run's checkout log names is the queue's tree. A group of more
than one entry fails point 2 for every entry after the first, whose first
parent is the entry before it, and is tested in full.

**It fails towards testing.** An error reading the API prints `tested=false`
and a warning, and exits 0: the price of a wrong `false` is one more run of
the suite, and the price of a wrong `true` is an untested commit.

On a queue entry the answer skips only the steps of the `gates` legs, which
are what repeats there: `readers`, `docs`, `glyphs` and the image read things
outside the tree (the tags, the site, PyPI) that may have moved since the head
ran, and they run. `gates` is skipped by its steps and not by its `if:`, so its
three legs still report under their own names: a matrix job skipped whole
reports one check, without the version, and the required `gates (3.12)` would
never arrive.

`docs` is not in `REPEATED`, and that is not an omission. On a push to `main`
it runs the ordinary `--strict` build with the site's guard, where the queue
ran the preview: a different build, which `CONTRIBUTING.md` names as the one
that finds a page with no nav line. `examples-from-pypi` does not run on a
push either way.

Standard library only, like the other scripts here. Reads
`GITHUB_REPOSITORY`, `GITHUB_EVENT_NAME`, `GH_TOKEN`, `API` (default
https://api.github.com) and `GITHUB_OUTPUT` (when set, the answer is appended
to it as well).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API = os.environ.get("API", "https://api.github.com").rstrip("/")
WORKFLOW = ".github/workflows/ci.yml"

# The versions of the `gates` matrix. `tests/test_queue_tested.py` holds this
# equal to the matrix in ci.yml, so a version added there cannot be skipped
# here without having been run in the queue.
PYTHONS = ("3.12", "3.13", "3.14")

REPEATED = (
    *(f"gates ({python})" for python in PYTHONS),
    "The old readers, built from their tags, where they may not skip",
    "The site's fonts set every character of these docs",
    "Does this change the image?",
)
IMAGE = "The image builds, and the quickstart runs inside it"

# The four checks the `main` ruleset requires. CLAUDE.md lists the same four.
REQUIRED = (
    *(f"gates ({python})" for python in PYTHONS),
    "The old readers, built from their tags, where they may not skip",
)


def verdict(
    sha: str, runs: list[dict[str, Any]], jobs: dict[int, list[dict[str, Any]]]
) -> tuple[bool, str]:
    """Pure: `runs` as the runs listing returns them, `jobs` each run's jobs
    of its latest attempt, by run id. True only when one queue run of `ci` on
    exactly `sha` ran every repeated job green."""
    queued = [
        run
        for run in runs
        if run.get("head_sha") == sha
        and run.get("event") == "merge_group"
        and run.get("path") == WORKFLOW
    ]
    if not queued:
        return (
            False,
            f"no merge_group run of ci on {sha}: not a commit the queue tested",
        )
    # **Why this rarely answers true once the queue-side skip below has fired.**
    # The queue merges as soon as the four required checks are green, not
    # when the whole run is. With the `gates` legs skipping their steps that
    # takes about forty seconds, so `glyphs` and `image`, which are not
    # required, are usually still running when `main` moves and this run is
    # read. Their conclusion is then `None`, which is not green, and the
    # answer is false: the push is tested in full. Measured on #772's own
    # entry on 2026-10-28: its queue run (40698232620) began at 13:38:06, the
    # four were green at 13:38:44, the queue merged at 13:38:55, and the push
    # run (40698365639) read `None` for both jobs and answered false. The
    # 30-in-30 measurement this cut was justified by, every job of the queue's
    # run finished before the push, held only because the `gates` legs were
    # the slowest jobs, and the queue-side skip removed exactly that. It fails
    # towards testing, so nothing goes untested; it only cuts less.
    reasons = []
    for run in queued:
        by_name = {
            job["name"]: job.get("conclusion") for job in jobs.get(run["id"], [])
        }
        short = [
            f"{name}: {by_name.get(name, 'missing')}"
            for name in REPEATED
            if by_name.get(name) != "success"
        ]
        if by_name.get(IMAGE) not in ("success", "skipped"):
            short.append(f"{IMAGE}: {by_name.get(IMAGE, 'missing')}")
        if not short:
            return (
                True,
                f"merge_group run {run['id']} ran every repeated job green on {sha}",
            )
        reasons.append(f"run {run['id']}: " + "; ".join(short))
    return (
        False,
        "the queue's run did not run every repeated job green — " + " | ".join(reasons),
    )


def tree_verdict(
    sha: str,
    commit: dict[str, Any],
    head: dict[str, Any],
    compare: dict[str, Any],
    runs: list[dict[str, Any]],
    jobs: dict[int, list[dict[str, Any]]],
) -> tuple[bool, str]:
    """Pure: `commit` and `head` as `git/commits/{sha}` returns them, `compare`
    as `compare/{first parent}...{head}` does, `runs` the `pull_request` runs
    of ci on the head and `jobs` each one's jobs of its latest attempt. True
    only when the queue's tree is the tree the four required checks passed on."""
    parents = [parent["sha"] for parent in commit.get("parents", [])]
    if len(parents) != 2:
        return False, f"{sha} has {len(parents)} parents: not a queue merge of one head"
    base, head_sha = parents
    if head.get("sha") != head_sha:
        return False, f"the head read is {head.get('sha')}, not {head_sha}"
    tree, head_tree = commit["tree"]["sha"], head["tree"]["sha"]
    if tree != head_tree:
        return False, f"the queue's tree {tree} is not the head's tree {head_tree}"
    if compare.get("behind_by") != 0:
        return False, (
            f"{base} is not an ancestor of the head {head_sha}"
            f" (behind_by {compare.get('behind_by')})"
        )
    for run in runs:
        if (
            run.get("head_sha") != head_sha
            or run.get("event") != "pull_request"
            or run.get("path") != WORKFLOW
        ):
            continue
        by_name = {
            job["name"]: job.get("conclusion") for job in jobs.get(run["id"], [])
        }
        if all(by_name.get(name) == "success" for name in REQUIRED):
            return True, (
                f"pull_request run {run['id']} passed the four required checks on"
                f" {head_sha}, whose tree {tree} is this commit's"
            )
    return (
        False,
        f"no pull_request run of ci on {head_sha} passed the four required checks",
    )


def get(path: str) -> Any:
    request = urllib.request.Request(f"{API}/{path}")
    request.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def read(sha: str) -> tuple[bool, str]:
    repo = os.environ["GITHUB_REPOSITORY"]
    if os.environ.get("GITHUB_EVENT_NAME") == "merge_group":
        commit = get(f"repos/{repo}/git/commits/{sha}")
        parents = [parent["sha"] for parent in commit["parents"]]
        if len(parents) != 2:
            return tree_verdict(sha, commit, {}, {}, [], {})
        head = get(f"repos/{repo}/git/commits/{parents[1]}")
        compare = get(f"repos/{repo}/compare/{parents[0]}...{parents[1]}")
        prs = get(
            f"repos/{repo}/actions/workflows/ci.yml/runs"
            f"?head_sha={parents[1]}&event=pull_request&per_page=100"
        )["workflow_runs"]
        pr_jobs = {
            run["id"]: get(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")[
                "jobs"
            ]
            for run in prs
        }
        return tree_verdict(sha, commit, head, compare, prs, pr_jobs)
    runs = get(
        f"repos/{repo}/actions/workflows/ci.yml/runs"
        f"?head_sha={sha}&event=merge_group&per_page=100"
    )["workflow_runs"]
    jobs = {
        run["id"]: get(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")[
            "jobs"
        ]
        for run in runs
    }
    return verdict(sha, runs, jobs)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: queue_tested.py <sha>", file=sys.stderr)
        return 2
    try:
        tested, reason = read(argv[0])
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as error:
        tested, reason = (
            False,
            f"could not read what was already tested ({error}); testing in full",
        )
        print(f"::warning::{reason}")
    print(reason)
    line = f"tested={'true' if tested else 'false'}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.write("reason=" + " ".join(reason.split()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
