"""Whether merging a Dependabot pull request would close something on a tracker.

A closing keyword followed by an issue reference closes that issue when the
pull request is merged into the default branch, and GitHub reads it in two
places: *"in the pull request's description or in a commit message"* (Linking
a pull request to an issue). A Dependabot body quotes release notes written by
somebody else, and a release note that says `Fixes #6665` is a sentence about
another repository's tracker. Here it is read as ours: merging would close our
#6665 if one existed, and a `#N` in a pull request is a reference to this
repository (CLAUDE.md, *A `#N` in a pull request…*).

What GitHub recognises, from the same page:

- the nine keywords `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`,
  `resolve`, `resolves`, `resolved`, in any case, *"followed by colons or in
  uppercase"* (`Closes: #10`, `CLOSES #10`);
- `KEYWORD #ISSUE-NUMBER` for this repository, and
  `KEYWORD OWNER/REPOSITORY#ISSUE-NUMBER` for another;
- one keyword per reference: *"Use full syntax for each issue"*.

A keyword inside a longer word (`closely`, `enclosed`) is not a keyword, and a
keyword not followed by a reference (`the close`) closes nothing. A full URL
after a keyword is a form the page does not rule on, and it is not matched here.

**One form is matched although the page does not rule on it**: a keyword
followed by an HTML link whose text is the reference, `Fixes <a href=…>#6665</a>`.
That is how a Dependabot body quotes a release note, and #857 carried exactly
that on 2026-11-02. Whether GitHub closes on it is not known from the page; a
guard that has to choose between a false alarm and a closed issue reads it.

    python3 .github/closing_words.py check --repo OWNER/REPO --pr N --event PATH
    python3 .github/closing_words.py --selftest

`check` reads the body from the event payload at PATH and every commit message
of the pull request through `gh api`, with the workflow's read-only token. For
each reference it asks the tracker whether an issue or a pull request with that
number exists. It prints every reference it found and exits 1 when one exists,
naming it, and when the body is empty: a body nobody could read is not a body
with nothing in it. Standard library only, plus `gh`: this runs under the
runner's bare `python3`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

#: The nine words, longest first inside each family so a match takes the whole
#: word; `\b`-free on purpose, the boundaries are spelled out in `REFERENCE`.
KEYWORDS = r"(?:closes|closed|close|fixes|fixed|fix|resolves|resolved|resolve)"

#: A keyword that is a word of its own, then a colon or whitespace, then an
#: optional opening HTML link, then an optional `owner/repo`, then `#` and the
#: number.
REFERENCE = re.compile(
    rf"(?<![0-9A-Za-z_/.-])(?P<keyword>{KEYWORDS})(?::\s*|\s+)"
    r"(?:<a\s[^>]*>\s*)?"
    r"(?:(?P<repo>[0-9A-Za-z_.-]+/[0-9A-Za-z_.-]+))?#(?P<number>[0-9]+)(?![0-9A-Za-z_])",
    re.IGNORECASE,
)


USAGE = (
    "usage: closing_words.py check --repo OWNER/REPO --pr N --event PATH\n"
    "       closing_words.py --selftest"
)


@dataclass(frozen=True)
class Reference:
    keyword: str
    repo: str
    number: int
    where: str

    def __str__(self) -> str:
        return f"{self.keyword} {self.repo}#{self.number} (in {self.where})"


def references(text: str, *, repo: str, where: str) -> list[Reference]:
    """Every closing reference in `text`, in order."""
    return [
        Reference(
            keyword=match.group("keyword"),
            repo=match.group("repo") or repo,
            number=int(match.group("number")),
            where=where,
        )
        for match in REFERENCE.finditer(text)
    ]


def found(body: str, messages: Iterable[str], *, repo: str) -> list[Reference]:
    refs = references(body, repo=repo, where="the body")
    for index, message in enumerate(messages, start=1):
        refs += references(message, repo=repo, where=f"commit message {index}")
    return refs


def verdict(
    body: str,
    messages: Iterable[str],
    *,
    repo: str,
    exists: Callable[[str, int], bool],
) -> tuple[int, list[str]]:
    """The exit code and the lines to print."""
    if not body.strip():
        return 1, [
            "could not read the pull request's body from the event payload: it "
            "is empty, so whether it holds a closing word is not known"
        ]
    refs = found(body, messages, repo=repo)
    lines = [f"references found: {len(refs)}"] + [f"  {ref}" for ref in refs]
    existing = [ref for ref in refs if exists(ref.repo, ref.number)]
    if existing:
        lines += [
            f"merging would close {ref.repo}#{ref.number}, which exists ({ref})"
            for ref in existing
        ]
        return 1, lines
    lines.append("none of them names an issue or a pull request that exists")
    return 0, lines


def _gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def tracker_has(repo: str, number: int) -> bool:
    """Whether `repo` has an issue or a pull request numbered `number`.

    The issues endpoint answers for both. A 404 is *no*; any other failure is
    raised, because a tracker that could not be asked has not said no."""
    done = _gh("api", f"repos/{repo}/issues/{number}", "--jq", ".number")
    if done.returncode == 0:
        return True
    if "HTTP 404" in done.stderr:
        return False
    raise RuntimeError(f"could not ask {repo} about #{number}: {done.stderr.strip()}")


def commit_messages(repo: str, pr: int) -> list[str]:
    done = _gh(
        "api",
        "--paginate",
        f"repos/{repo}/pulls/{pr}/commits",
        "--jq",
        ".[].commit.message | @json",
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"could not read the commits of #{pr}: {done.stderr.strip()}"
        )
    return [json.loads(line) for line in done.stdout.splitlines() if line]


def check(repo: str, pr: int, event: str) -> int:
    with open(event, encoding="utf-8") as handle:
        payload = json.load(handle)
    body = (payload.get("pull_request") or {}).get("body") or ""
    code, lines = verdict(
        body, commit_messages(repo, pr), repo=repo, exists=tracker_has
    )
    print("\n".join(lines))
    return code


def selftest() -> int:
    repo = "digline/digline"
    tracker = {("digline/digline", 3), ("octo/repo", 9)}

    def exists(where: str, number: int) -> bool:
        return (where, number) in tracker

    cases: list[tuple[str, str, list[str], list[tuple[str, int]], int]] = [
        ("a keyword followed by #N", "Fixes #12", [], [(repo, 12)], 0),
        ("a keyword not followed by #N", "the close of the window", [], [], 0),
        ("a keyword inside a word", "closely #5 related, enclosed #6", [], [], 0),
        ("#N with no keyword", "see #7 and #8", [], [], 0),
        (
            "today's case: Fixes #6665, absent here",
            "Fixes #6665",
            [],
            [(repo, 6665)],
            0,
        ),
        (
            "today's case as #857 carried it: a link",
            '<li>Fixes <a href="https://example.org/issues/6665">#6665</a> x</li>',
            [],
            [(repo, 6665)],
            0,
        ),
        ("a colon and capitals", "CLOSES: #10", [], [(repo, 10)], 0),
        ("another repository", "fixes octo/repo#9", [], [("octo/repo", 9)], 1),
        ("a reference that exists", "Bump x\n\nresolves #3", [], [(repo, 3)], 1),
        ("in a commit message", "Bump x", ["Bump x\n\nCloses #3"], [(repo, 3)], 1),
        ("an empty body", "", [], [], 1),
    ]
    failed = 0
    for name, body, messages, want_refs, want_code in cases:
        got_refs = [(ref.repo, ref.number) for ref in found(body, messages, repo=repo)]
        code, _ = verdict(body, messages, repo=repo, exists=exists)
        ok = got_refs == want_refs and code == want_code
        print(f"{'ok  ' if ok else 'FAIL'} {name}: refs {got_refs}, exit {code}")
        failed += not ok
    print(f"selftest: {len(cases) - failed} of {len(cases)} passed")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if len(argv) == 7 and argv[0] == "check":
        options = {argv[i]: argv[i + 1] for i in range(1, len(argv), 2)}
        return check(options["--repo"], int(options["--pr"]), options["--event"])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
