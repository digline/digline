"""What PyPI serves as each package's description, read after the upload for
a wording already found false and corrected. (#553)

PyPI renders a package's README as its description, and a description is fixed
with the version: a sentence corrected in the tree reaches PyPI only with the
next release of that package. On 2026-10-13 one false claim, that pytest's exit
code cannot tell digline's `1` from its `2`, was corrected in five files, and
https://pypi.org/project/pytest-digline/ went on serving it until the next
pytest-digline release. Nothing would have said so if a release had shipped an
old copy.

So after the upload, for each package `dist/` holds, at the version it holds,
this reads `info.description` from `/pypi/<name>/<version>/json` and refuses
the release if it contains any of `WORDINGS`. Every package in `dist/` and not
only those this run uploaded: a re-run of the `pypi` job uploads nothing, and a
check that read only the uploads would pass by reading nothing. A package the
tag did not upload is at a version PyPI already serves, so reading it costs one
request and proves the same thing.

**It matches the exact wordings, nothing wider.** A check that flagged every
sentence pairing pytest with an exit code was measured and discarded on
2026-10-13: 58 sentences to triage before the first green, at least 54 of them
true. This catches an old copy left served, not a new paraphrase; a new false
sentence is a person's to find. Line breaks are folded before matching, because
a README wraps its sentences and a wording split across two lines is still
served.

**Red only after a release.** It runs in the `pypi` job, which runs on every
tag, after the upload: a version that serves a listed wording is already spent,
and the remedy is the next release of that package with the README fixed.
Nothing re-reads PyPI between releases, and that limit is accepted (#553).

**It waits, and keeps a third word.** The JSON page answered 404 behind
`/simple/` on v0.22.0 and v0.23.0, so the `pypi` job's wait does not cover it;
this waits on the page itself, as `mcp_registry.py await-pypi` does. Exit codes:
0 every description is clean, 1 refused, 2 not judged (PyPI never answered:
nothing was learned, and the remedy is a re-run).

Standard library only: it runs under the runner's bare `python3`.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from release_bundles import INDEX, Index, NotJudged, Refused, name_and_version

#: Each found and removed on 2026-10-13, and readable in the history: the place
#: it was in, and the change that took it out.
WORDINGS = (
    # docs/pytest.md before a215b93, packages/pytest-digline/README.md before 79ceceb
    "What pytest cannot carry",
    # docs/pytest.md before a215b93
    "not something a plugin can change",
    # packages/pytest-digline/tests/test_contract.py before #552
    "pytest cannot carry that distinction",
    # packages/pytest-digline/tests/test_contract.py before #552
    "pytest erases",
    # digline.dev tools/hooks/seo.py before digline.dev#179
    "what pytest's exit code cannot carry",
    # digline.dev tools/hooks/llms.py before digline.dev#180
    "what pytest's single exit code cannot tell apart",
    # ADR 0013 §7, kept there with its dated note
    "the runner erases",
)


def served_wordings(description: str) -> list[str]:
    """The listed wordings a description contains, with its line breaks folded."""
    folded = " ".join(description.split())
    return [wording for wording in WORDINGS if wording in folded]


def roster(dist: pathlib.Path) -> list[tuple[str, str]]:
    found = sorted({name_and_version(p) for p in dist.glob("*.whl")})
    if not found:
        raise Refused(f"{dist} holds no wheel, so this would pass by reading nothing")
    return found


def main() -> int:
    index = Index(
        timeout=float(os.environ.get("TIMEOUT", "600")),
        interval=float(os.environ.get("INTERVAL", "10")),
    )
    refused: list[str] = []
    for name, version in roster(pathlib.Path("dist")):
        page = index.answer(f"{INDEX}/pypi/{name}/{version}/json")
        if page is None:
            raise Refused(
                f"{INDEX} answered 404 for {name} {version} until the last read, "
                f"{index.timeout:.0f}s after the first: this runs after the "
                "upload, so the version is not there"
            )
        description = json.loads(page)["info"]["description"] or ""
        found = served_wordings(description)
        if found:
            refused.append(f"{name} {version}: " + "; ".join(repr(w) for w in found))
            print(
                f"refused  {name} {version}: serves {len(found)} corrected wording(s)"
            )
        else:
            print(f"clean    {name} {version}")
    if refused:
        raise Refused(
            "PyPI serves a wording already found false and corrected — "
            + " | ".join(refused)
            + ". The version is spent: fix the README and release the package again"
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        print(f"::error title=A corrected wording is served::{exc}", file=sys.stderr)
        sys.exit(1)
    except NotJudged as exc:
        print(f"::error title=Served descriptions not judged::{exc}", file=sys.stderr)
        sys.exit(2)
