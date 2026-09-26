"""The gate on the release workflows' wiring: nothing ships before `on-main`.

`publish.yml` and `docker-publish.yml` start with a job, `on-main`, that runs
`.github/on_main.py` and refuses a commit `main` does not contain. A guard
nothing depends on guards nothing: GitHub starts every job without `needs:` at
once, so a publishing job that does not wait for `on-main` — directly or
through a chain of `needs:` — runs beside it and ships whatever the tag points
at. This reads the workflows and refuses:

- a release workflow with no `on-main` job, or one that does not run the
  script, does not fetch the whole history, or can be skipped or ignored
  (`if:`, `continue-on-error:`);
- a job that **builds or publishes** and does not reach `on-main` through
  `needs:`;
- a job on that chain whose `if:` runs it when a job it needs failed
  (`always()`, `failure()`, `cancelled()`), which is the one way past a
  failed `needs:`.

**Which jobs build or publish is decided by what they do, not by a list of
names**, so a job added next year is covered on the day it is written: an
artifact upload, an upload to an index, an image build or push, a registry
login, a release, a dispatch to another repository, any write permission or
OIDC token, a deployment environment. `JOBS_THAT_SHIP` in the test pins the
jobs this recognises today, so a marker that stops matching is noticed too.

YAML is read as text, the way `tools/actions.py` and `tests/test_docker.py`
read it: the shape a workflow is written in here is regular enough, and a
parser would be a dependency for the sake of one gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

GUARD = "on-main"
SCRIPT = ".github/on_main.py"
RELEASE_WORKFLOWS = ("publish.yml", "docker-publish.yml")

#: What a job does that makes it one that builds or publishes. Matched on the
#: job's lines with whole-line comments taken out, so a comment that mentions
#: `uv build` does not turn a job into a build.
SHIPS = tuple(
    re.compile(pattern, re.M)
    for pattern in (
        r"uses:\s*actions/upload-artifact@",
        r"uses:\s*pypa/gh-action-pypi-publish@",
        r"uses:\s*docker/build-push-action@",
        r"uses:\s*docker/login-action@",
        r"uses:\s*[\w.-]+/[\w.-]*release[\w.-]*@",
        r"\buv build\b",
        r"\bpython3? -m build\b",
        r"\btwine upload\b",
        r"\bdocker (?:buildx )?(?:build|push)\b",
        r"\bgh release (?:create|upload|edit)\b",
        r"/dispatches\b",
        r"\bgh workflow run\b",
        r"^\s+[\w-]+:\s*write\b",
        r"^    environment:",
    )
)

#: An `if:` that runs a job after a job it needs has failed.
PAST_A_FAILURE = re.compile(r"\b(?:always|failure|cancelled)\(\)")

_JOB = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$")
_KEY = re.compile(r"^    ([A-Za-z_][\w-]*):\s*(.*?)\s*$")
_ITEM = re.compile(r"^\s+-\s*(\S+)\s*$")


@dataclass
class Job:
    name: str
    body: str = ""
    needs: list[str] = field(default_factory=list[str])
    condition: str = ""


def jobs(text: str) -> dict[str, Job]:
    """The jobs of a workflow, with their `needs:`, their `if:` and their lines."""
    found: dict[str, Job] = {}
    inside = False
    current: Job | None = None
    collecting_needs = False
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        if line and not line[0].isspace():
            inside = line.rstrip() == "jobs:"
            current = None
            continue
        if not inside:
            continue
        header = _JOB.match(line)
        if header:
            current = found.setdefault(header.group(1), Job(header.group(1)))
            collecting_needs = False
            continue
        if current is None:
            continue
        current.body += line + "\n"
        key = _KEY.match(line)
        if key:
            collecting_needs = False
            name, value = key.groups()
            if name == "needs":
                value = value.strip("[]")
                current.needs += [n.strip() for n in value.split(",") if n.strip()]
                collecting_needs = not value
            elif name == "if":
                current.condition = value
            continue
        item = _ITEM.match(line)
        if collecting_needs and item:
            current.needs.append(item.group(1))
        elif line.strip():
            collecting_needs = False
    return found


def ships(job: Job) -> bool:
    return any(pattern.search(job.body) for pattern in SHIPS)


def chain(name: str, found: dict[str, Job]) -> set[str]:
    """Every job `name` waits for, directly or through a chain of `needs:`."""
    seen: set[str] = set()
    todo = list(found[name].needs) if name in found else []
    while todo:
        need = todo.pop()
        if need not in seen:
            seen.add(need)
            todo += found[need].needs if need in found else []
    return seen


def problems(workflow: str, text: str) -> list[str]:
    """What is wrong with one release workflow's wiring; [] is a pass."""
    found = jobs(text)
    guard = found.get(GUARD)
    if guard is None:
        return [
            f"{workflow}: no `{GUARD}` job, so nothing checks that the commit "
            "being released is on main"
        ]
    wrong: list[str] = []
    if SCRIPT not in guard.body:
        wrong.append(f"{workflow}: `{GUARD}` does not run {SCRIPT}")
    if not re.search(r"fetch-depth:\s*0\b", guard.body):
        wrong.append(
            f"{workflow}: `{GUARD}` checks out without `fetch-depth: 0`, and "
            "ancestry cannot be asked of a shallow clone"
        )
    if guard.condition:
        wrong.append(f"{workflow}: `{GUARD}` has an `if:`, so it can be skipped")
    if re.search(r"continue-on-error:\s*true", guard.body):
        wrong.append(
            f"{workflow}: `{GUARD}` has `continue-on-error`, so its refusal "
            "stops nothing"
        )
    for name, job in found.items():
        if name == GUARD or not ships(job):
            continue
        waits_for = chain(name, found)
        if GUARD not in waits_for:
            wrong.append(
                f"{workflow}: job `{name}` builds or publishes and does not "
                f"wait for `{GUARD}`, directly or through `needs:`"
            )
            continue
        for link in sorted((waits_for - {GUARD}) | {name}):
            if link in found and PAST_A_FAILURE.search(found[link].condition):
                wrong.append(
                    f"{workflow}: job `{link}`, on the way from `{GUARD}` to "
                    f"`{name}`, runs past a failed `needs:` "
                    f"(`if: {found[link].condition}`)"
                )
    return wrong
