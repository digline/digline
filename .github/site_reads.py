"""Whether a push touched anything digline.dev reads out of this repository.

digline.dev builds its documentation from the tip of this repository's `main`,
and `tools/sync-docs.sh` over there copies five things out of it. A change to
any of them reaches the site only when the site rebuilds, and until #521
nothing told it to: `.github/workflows/site-docs.yml` now does, after each
push to `main` that touched one of them.

`SITE_READS` is that list, and `tests/test_site_docs.py` holds it equal to what
`sync-docs.sh` copies, read from the site's own checkout where this machine
has one. What the site reads at a release tag rather than at `main` — rule 1
of `AGENTS.md`, the facts of `examples/operator/` — is not here: a push to
`main` does not move it.

    git diff --name-only BEFORE HEAD | python3 .github/site_reads.py
    python3 .github/site_reads.py --no-base

Prints each path the site reads, then `dispatch=true` or `dispatch=false` on
its last line, for `$GITHUB_OUTPUT`. `--no-base` is a push with nothing to
compare it with: what moved is unknown, so the answer is `true`. Standard
library only: this runs under the runner's bare `python3`.
"""

from __future__ import annotations

import fnmatch
import sys
from collections.abc import Iterable

#: What `sync-docs.sh` copies, as it names each: a directory with a slash, a
#: file by its path, and the examples' READMEs by their glob.
SITE_READS = (
    "docs/",
    "CHANGELOG.md",
    "ROADMAP.md",
    "docker/README.md",
    "examples/*/README.md",
)


def _reads(path: str) -> bool:
    for read in SITE_READS:
        if read.endswith("/"):
            if path.startswith(read):
                return True
        elif "*" in read:
            # `*` is one directory: examples/operator/README.md, never a
            # README further down.
            if fnmatch.fnmatchcase(path, read) and path.count("/") == read.count("/"):
                return True
        elif path == read:
            return True
    return False


def touched(paths: Iterable[str]) -> list[str]:
    """The paths in `paths` that the site reads, in their order."""
    return [path for path in paths if _reads(path)]


def main(argv: list[str]) -> int:
    if argv == ["--no-base"]:
        print("no base commit to compare against; telling the site")
        print("dispatch=true")
        return 0
    if argv:
        print(__doc__.split("\n\n")[-3], file=sys.stderr)
        return 2
    found = touched(line.strip() for line in sys.stdin if line.strip())
    for path in found:
        print(path)
    if not found:
        print("nothing the site reads changed; not telling it")
    print(f"dispatch={'true' if found else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
