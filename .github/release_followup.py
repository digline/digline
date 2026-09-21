"""The four things a machine can ask about a release once the tag is out.

`RELEASING.md` has a checklist headed *After the tag: what to watch, and what to
ignore*, and until this file existed **nothing in the repository knew whether
any of it had been done**. That is not a hypothesis. The example locks were last
regenerated for 0.15.0 and were found still naming it at 0.15.3 — two releases
in which the nine example legs exercised a version nobody had released — and the
*Status* block was two releases behind on the same day. Neither made anything
red, because the `<0.16` caps admitted both versions and the stale versions in
the prose were already registered as history.

The shape of the gap is worth naming, because it explains why the answer is a
separate workflow rather than another test: **before the tag the subject is the
tree, and a test can read it; after the tag the subject is the world** — an
index, a registry, a run's approval record — and the gates of this repository do
not look there. So these four run where the world can be asked, and they are the
four that have an answer a machine can check:

1. **the example locks** name the version that was released;
2. the `publish` run's **reviewer gate** recorded an `approved`;
3. the three **image tags** resolve to one digest;
4. the **Status block** names the release it is supposed to describe.

**What is deliberately not here.** The delta-pass, its report in `private/` and
the GHSA draft have no check and must not get one: a gate on a file's existence
is satisfied by a file with one line in it, so the cheap way past it is to write
the file, and the gate then certifies the opposite of what it was built for.
`RELEASING.md` says so at length beside them.

**Every check carries its own negative half**, and they run in the same job as
the positive one rather than in a selftest. A check that cannot fail has
verified nothing, and three of these four are the kind that fail open by
construction: a registry that answers nothing, an approvals list that is empty
because the endpoint moved, a comparison against a version nobody set. Each one
is therefore asked a second question whose answer must be *no*, and a `no` that
does not arrive fails the run as loudly as a broken check.

**No network and no clock.** Everything arrives as a file, so this is testable
against fixtures and cannot answer differently on a runner than on a laptop.
The fetching lives in `release-followup.yml`, which is also where the finding
becomes an issue.

Usage:

    python .github/release_followup.py --version 0.15.3 --root . \\
        --releasing RELEASING.md \\
        --approvals approvals.json --approvals-control no-gate.json \\
        --digests digests.json --out report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Finding",
    "approvals_finding",
    "digests_finding",
    "lock_versions",
    "locks_finding",
    "main",
    "report",
    "status_block",
    "status_finding",
]

#: The examples that pin an exact version, and therefore the ones post-tag step
#: 3 regenerates: whichever ones have a `uv.lock`, found by looking.
#:
#: This was a named tuple of five, on the reasoning that the others resolve at
#: install time and have no lock to be stale. That reasoning was true when it
#: was written and stopped being true when `mcp-tools` arrived with a lock: the
#: tuple did not name it, so step 3 read five files, found them all at the new
#: version, and reported green over a sixth that was a release behind. A list
#: of what exists cannot be kept by hand in a repository that grows examples —
#: and it does not have to be, since the thing it lists is on disk.

#: The heading of the block post-tag step 4 updates, and the one after it.
STATUS_HEADING = "### Status: what each path has proven"

#: A version no release will ever carry, used as the impossible expectation the
#: negative halves are measured against.
IMPOSSIBLE = "0.0.0"


@dataclass(frozen=True, slots=True)
class Finding:
    """One check, both halves of it, and the sentence an issue title would use.

    `held` is the negative half: whether the same check, asked something that
    must be false, said false. A `Finding` with `ok` true and `held` false is
    **not** a pass — it is a check that would have said yes to anything, which
    is the failure mode this file exists to refuse.
    """

    step: str
    ok: bool
    held: bool
    said: str
    control_said: str
    #: What an issue title reads when `ok` is false. A sentence, in the present
    #: tense, naming the step rather than the check: the reader is being told
    #: which part of the runbook has not been done.
    title: str

    #: Whether this question has a meaningful answer about the release being
    #: asked about. Two of the four are about **the current state of a moving
    #: thing** — the locks in the tree, and the `<minor>` and `latest` image
    #: tags — so asked about a superseded release they can only fail, and
    #: failing is the wrong word: the locks naming the newest release and
    #: `latest` pointing at it are correct, not undone. The other two are about
    #: a **record of what happened at that release** — the approvals of its
    #: publish run, and its paragraph in the Status block — and those keep their
    #: meaning for ever.
    #:
    #: The distinction is not a convenience. Without it the issue opened for a
    #: superseded release is immortal: two of its lines could never go green
    #: without making the current tree wrong, so no run could close it, and a
    #: red label open for ever is the signal people learn to ignore.
    applicable: bool = True

    @property
    def sound(self) -> bool:
        """Nothing to answer counts as nothing wrong — but only where the
        question genuinely does not apply, never where it was not asked."""
        return True if not self.applicable else (self.ok and self.held)


def pinned_examples(root: Path) -> tuple[str, ...]:
    """Every example that carries a `uv.lock`, in a fixed order.

    Sorted so that a report reads the same twice, and so that a new example
    joins the check by being committed rather than by somebody remembering."""
    return tuple(sorted(path.parent.name for path in root.glob("examples/*/uv.lock")))


def lock_versions(
    root: Path, examples: Sequence[str] | None = None
) -> dict[str, str | None]:
    """The digline version each example's `uv.lock` pins, or `None` where the
    lock has no digline entry at all — which is a different defect and is
    reported as one rather than as a mismatch.

    `examples` is for the tests, which build a tree of their own. Left out, the
    examples are the ones `root` actually has."""
    found: dict[str, str | None] = {}
    for name in pinned_examples(root) if examples is None else examples:
        path = root / "examples" / name / "uv.lock"
        if not path.is_file():
            found[name] = None
            continue
        match = re.search(
            r'^name = "digline"\nversion = "([^"]+)"',
            path.read_text(encoding="utf-8"),
            re.M,
        )
        found[name] = match.group(1) if match else None
    return found


def locks_finding(root: Path, version: str, *, current: bool = True) -> Finding:
    """Post-tag step 3: every example lock names the version that was released.

    Only about the newest release. Asked about a superseded one it would report
    that the locks name something else — which is what they are supposed to do,
    and calling that a skipped step would be a finding against the repair.
    """
    if not current:
        return Finding(
            step="the example locks",
            ok=True,
            held=True,
            applicable=False,
            said=(
                f"not applicable: the locks track the newest release, so what "
                f"they name is not a fact about {version}"
            ),
            control_said="not asked",
            title="",
        )
    pinned = lock_versions(root)
    stale = {name: got for name, got in pinned.items() if got != version}
    control = {name: got for name, got in pinned.items() if got != IMPOSSIBLE}
    listed = ", ".join(
        f"{name} {got or 'no digline entry'}" for name, got in stale.items()
    )
    return Finding(
        step="the example locks",
        ok=not stale,
        # Every lock must differ from a version nobody released. If this comes
        # back empty the comparison is not comparing.
        #
        # `pinned` itself must not be empty either, and that is new with the
        # glob: a named tuple could not find nothing, but a pattern can — an
        # examples/ that moved, a checkout without it — and "all 0 locks name
        # 0.17.1" is true of every version there has ever been.
        held=bool(pinned) and len(control) == len(pinned),
        said=(
            f"all {len(pinned)} locks name {version}"
            if not stale and pinned
            else "no example carries a uv.lock, so this step read nothing"
            if not pinned
            else f"{len(stale)} of {len(pinned)} do not name {version}: {listed}"
        ),
        control_said=(
            f"and none of them names {IMPOSSIBLE}"
            if len(control) == len(pinned)
            else f"but {len(pinned) - len(control)} of them read as {IMPOSSIBLE}, "
            "so this comparison is not reading the file"
        ),
        title=f"the example locks still name {_one_of(stale) or 'nothing'}",
    )


def _one_of(stale: Mapping[str, str | None]) -> str:
    """The version the stale locks name, for the title. The first one, and
    'several versions' where they disagree — a title says which step, not the
    whole finding."""
    versions = {got for got in stale.values() if got}
    if not versions:
        return ""
    return versions.pop() if len(versions) == 1 else "several versions"


def approvals_finding(approvals: object, control: object) -> Finding:
    """Post-tag step 1: the reviewer gate recorded an approval.

    Read from the record rather than from the run's green, for the reason
    `RELEASING.md` gives: a fast approval passes through `waiting` in seconds,
    so polling cannot see it, and **a gate that fails open looks exactly the
    same from the outside**. It has failed open once, on v0.5.0.

    The control is the approvals of a run with no gated environment, which the
    workflow fetches beside it. That list must be empty: if this reads an
    approval there, it is reading something other than an approval.
    """
    approved = _approved(approvals)
    control_approved = _approved(control)
    return Finding(
        step="the reviewer gate",
        ok=approved,
        held=not control_approved,
        said=(
            "the publish run records an approved"
            if approved
            else "the publish run records no approved: either the gate did not "
            "hold, or nobody has approved it yet"
        ),
        control_said=(
            "and a run with no gated environment records none"
            if not control_approved
            else "but a run with no gated environment also reads as approved, "
            "so this is not reading approvals"
        ),
        title="the reviewer gate recorded no approval",
    )


def _approved(payload: object) -> bool:
    if not isinstance(payload, list):
        return False
    entries = [entry for entry in payload if isinstance(entry, dict)]
    return any(entry.get("state") == "approved" for entry in entries)


def digests_finding(
    digests: Mapping[str, object], version: str, *, current: bool = True
) -> Finding:
    """Post-tag step 2, the half a log cannot show: the three tags are one image.

    `null` means the registry answered *not found*; the string `"error"` means
    it did not answer at all, and the two are kept apart on purpose. A registry
    that is down must not read as a release that shipped three different images
    — that is a weather report dressed as a defect, and a defect nobody can
    reproduce is one everybody learns to ignore.
    """
    if not current:
        return Finding(
            step="the image tags",
            ok=True,
            held=True,
            applicable=False,
            said=(
                f"not applicable: `<minor>` and `latest` follow the newest "
                f"release, so where they point is not a fact about {version}"
            ),
            control_said="not asked",
            title="",
        )
    minor = ".".join(version.split(".")[:2])
    wanted = (version, minor, "latest")
    unreachable = [tag for tag in wanted if digests.get(tag) == "error"]
    resolved = {tag: digests.get(tag) for tag in wanted}
    distinct = {
        value
        for value in resolved.values()
        if isinstance(value, str) and value != "error"
    }
    absent = [tag for tag, value in resolved.items() if value is None]
    impossible = f"{version}-does-not-exist"
    control_absent = digests.get(impossible) is None

    if unreachable:
        said = f"the registry did not answer for {', '.join(unreachable)} — not judged"
    elif absent:
        said = f"the registry has no {', '.join(absent)}"
    elif len(distinct) == 1:
        # `next(iter(...))` and not `.pop()`: popping empties the set, and the
        # line below counts it. The first cut read "are one digest" and reported
        # a failure in the same `Finding` — the exact shape of defect this file
        # exists to make visible, found by its own test.
        said = f"{', '.join(wanted)} are one digest ({next(iter(distinct))[:19]}…)"
    else:
        said = f"{', '.join(wanted)} resolve to {len(distinct)} different digests"

    return Finding(
        step="the image tags",
        ok=not unreachable and not absent and len(distinct) == 1,
        held=control_absent,
        said=said,
        control_said=(
            f"and {impossible} is not found"
            if control_absent
            else f"but {impossible} resolved to something, so this query answers "
            "for tags that do not exist"
        ),
        title=f"the three image tags are not one digest for {version}",
    )


def status_block(releasing: str) -> str:
    """The block post-tag step 4 updates, from its heading to the next one."""
    start = releasing.find(STATUS_HEADING)
    if start == -1:
        return ""
    rest = releasing[start + len(STATUS_HEADING) :]
    end = rest.find("\n### ")
    return rest if end == -1 else rest[:end]


def status_finding(releasing: str, version: str) -> Finding:
    """Post-tag step 4: the block names the release it is meant to describe.

    **This is the weakest of the four and is kept anyway.** It checks that the
    block *names* the version, not that what it says about it is true — no
    predicate can check a reading. What it does catch is the failure that
    actually happened: a block describing v0.15.0 and v0.15.1 while the tree was
    at 0.15.3, three releases of drift that nothing could see.
    """
    block = status_block(releasing)
    names = f"v{version}" in block
    return Finding(
        step="the Status block",
        ok=names,
        held=f"v{IMPOSSIBLE}" not in block,
        said=(
            f"the Status block names v{version}"
            if names
            else f"the Status block does not name v{version}; it names "
            + (
                ", ".join(sorted(set(re.findall(r"v\d+\.\d+\.\d+", block))))
                or "no release"
            )
        ),
        control_said=(
            f"and does not name v{IMPOSSIBLE}"
            if f"v{IMPOSSIBLE}" not in block
            else f"but it also names v{IMPOSSIBLE}, so this is not reading the block"
        ),
        title=f"the Status block does not mention v{version}",
    )


def report(findings: Sequence[Finding], version: str) -> dict[str, object]:
    """The issue an unsound run earns: a title naming the step, and a body that
    is the whole reading rather than a link to it."""
    unsound = [finding for finding in findings if not finding.sound]
    broken = [
        finding
        for finding in findings
        if finding.applicable and finding.ok and not finding.held
    ]
    lines = [
        f"The four checks `RELEASING.md` calls *After the tag* ran against "
        f"**v{version}**. Each is asked twice: once for the answer, and once for "
        f"something that must be false — a check that cannot fail has verified "
        f"nothing.",
        "",
    ]
    for finding in findings:
        if not finding.applicable:
            lines.append(f"- [~] **{finding.step}** — {finding.said}.")
            continue
        mark = "x" if finding.sound else " "
        lines.append(
            f"- [{mark}] **{finding.step}** — {finding.said}; {finding.control_said}."
        )
    lines += [
        "",
        "This issue is written and closed by `release-followup.yml`. It closes "
        "itself on the next push to `main` once every line above is ticked, so "
        "it needs no reply — only the step it names.",
    ]

    if broken:
        title = (
            f"Release follow-up for v{version}: "
            f"a check that cannot fail ({broken[0].step})"
        )
    elif unsound:
        first = unsound[0].title
        more = f", and {len(unsound) - 1} more" if len(unsound) > 1 else ""
        title = f"Release follow-up for v{version}: {first}{more}"
    else:
        title = (
            f"Release follow-up for v{version}: everything the runbook asks for is done"
        )

    return {
        "ok": not unsound,
        # The prefix every title for this release carries, and the only thing
        # that decides which open issue this run may touch. Owned here, where
        # the title is built, so the workflow greps for a string it was given
        # rather than one it reinvents — two spellings of a title is how an
        # issue about one release comes to be closed by a run about another.
        "scope": f"Release follow-up for v{version}:",
        "title": title,
        "body": "\n".join(lines),
        "steps": [
            {"step": f.step, "ok": f.ok, "held": f.held, "said": f.said}
            for f in findings
        ],
    }


def _load(path: str | None) -> object:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--newest",
        default=None,
        help=(
            "the newest released version, which decides whether the questions "
            "about moving things apply. Defaults to --version, so a caller who "
            "does not know asks about the present."
        ),
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--releasing", default="RELEASING.md")
    parser.add_argument("--approvals", required=True)
    parser.add_argument("--approvals-control", required=True)
    parser.add_argument("--digests", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.root)
    digests = _load(args.digests)
    current = args.newest is None or args.newest == args.version
    findings = [
        locks_finding(root, args.version, current=current),
        approvals_finding(_load(args.approvals), _load(args.approvals_control)),
        digests_finding(
            digests if isinstance(digests, dict) else {},
            args.version,
            current=current,
        ),
        status_finding(Path(args.releasing).read_text(encoding="utf-8"), args.version),
    ]
    written = report(findings, args.version)
    Path(args.out).write_text(json.dumps(written, indent=2), encoding="utf-8")

    for finding in findings:
        if not finding.applicable:
            print(f"n/a  {finding.step}: {finding.said}")
            continue
        mark = "ok  " if finding.sound else "FAIL"
        print(f"{mark} {finding.step}: {finding.said}; {finding.control_said}")
    return 0 if written["ok"] and all(f.held for f in findings if f.applicable) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
