"""The body of one version's entry in CHANGELOG.md, for its GitHub Release.

    python .github/changelog_entry.py 0.13.3 [CHANGELOG.md]

Prints what sits under `## 0.13.3 — <date>` and above the next `## ` heading,
without the heading and without the blank lines around it. That is the text a
GitHub Release carries: `CHANGELOG.md` says the notes under each release title
are the file, verbatim, and until 0.13.3 they were typed in by hand — which is
why v0.12.1 was backfilled days late and v0.13.1 and v0.13.2 had none at all.

Refuses, with exit 1 and a sentence, when the version has no entry or the entry
is empty. A release published with empty notes is the vacuously green check
`CLAUDE.md` decision 3 forbids, arriving at the one step nobody re-reads.

The heading is matched as `## <version> ` — the version followed by a space —
so `0.13.3` never matches `0.13.30`, and `Unreleased` never matches at all.
"""

import pathlib
import sys


def entry(changelog: str, version: str) -> str:
    """The body of `version`'s entry, stripped of surrounding blank lines."""
    heading = f"## {version} "
    lines = changelog.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(heading)]
    if len(starts) != 1:
        raise ValueError(
            f"CHANGELOG.md has {len(starts)} entries headed '## {version} ', "
            "expected exactly one"
        )
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    text = "\n".join(body).strip("\n")
    if not text.strip():
        raise ValueError(f"the CHANGELOG.md entry for {version} is empty")
    return text + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: changelog_entry.py VERSION [CHANGELOG.md]", file=sys.stderr)
        return 2
    path = pathlib.Path(argv[2] if len(argv) == 3 else "CHANGELOG.md")
    try:
        sys.stdout.write(entry(path.read_text(encoding="utf-8"), argv[1]))
    except ValueError as exc:
        print(f"changelog_entry: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
