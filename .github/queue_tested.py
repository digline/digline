"""Say whether the merge queue already ran `ci` green on the commit `main` was
just pushed to.

The queue builds `main` plus the pull request on a `gh-readonly-queue/main/...`
ref, runs `ci` there, and then moves `main` to **that same commit**. So the
push that follows carries a SHA the queue has already tested, and the jobs
below would run a second time on the same tree. This answers whether they
did run there, green, so the push run can skip them:

    python3 .github/queue_tested.py <sha>

It asks the API for every `ci` run with `event=merge_group` and
`head_sha=<sha>`, reads the jobs of each one's latest attempt, and prints
`tested=true` only when one of those runs has every job named in `REPEATED`
concluded `success` and the image job `success` or `skipped`. Anything else
prints `tested=false`: no queue run on the SHA, which is what a commit that did
not come through the queue looks like; a queue run not finished; a job red,
cancelled or missing. The answer is read from the commit, never from who
pushed it or from the event, so a push that did not come from the queue finds
no run and is tested in full.

**It fails towards testing.** An error reading the API prints `tested=false`
and a warning, and exits 0: the price of a wrong `false` is one more run of
the suite, and the price of a wrong `true` is an untested commit.

`docs` is not in `REPEATED`, and that is not an omission. On a push to `main`
it runs the ordinary `--strict` build with the site's guard, where the queue
ran the preview: a different build, which `CONTRIBUTING.md` names as the one
that finds a page with no nav line. `examples-from-pypi` does not run on a
push either way.

Standard library only, like the other scripts here. Reads
`GITHUB_REPOSITORY`, `GH_TOKEN`, `API` (default https://api.github.com) and
`GITHUB_OUTPUT` (when set, the answer is appended to it as well).
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
            f"could not read the queue's runs ({error}); testing in full",
        )
        print(f"::warning::{reason}")
    print(reason)
    line = f"tested={'true' if tested else 'false'}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
