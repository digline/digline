"""What a tag is about to publish, and whether its message says so.

`publish.yml` uploads **every workspace package whose version the index does
not serve**, whatever the tag is called. That is how a family ships in one run
— v0.15.0 carried digline, digline-anthropic, digline-openai and
digline-bedrock together, deliberately — and it is not going to change.

What has to change is that the run be **declared**. A tag is a signature, and
`v0.17.0`'s message said `digline 0.17.0` while the run published
`digline-anthropic 0.5.3` and `digline-openai 0.5.2` as well. Nothing was
wrong with the packages; what was wrong is that no ref and no message named
them, so the only place that record exists is PyPI's upload timestamps.

So: before the tag, compute what the index lacks and refuse a message that
does not name it. The same shape as the counts the runbook already asks for at
the `[GATE]` — a number somebody reads out loud rather than a memory somebody
trusts.

Everything here is pure but `served()` and `main()`. The index is the one fact
that cannot be derived from the tree, so it is fetched in one place and passed
in, which is what lets `tests/test_tag_names.py` cover the rest offline.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path

__all__ = [
    "declared_versions",
    "missing_from_message",
    "names",
    "to_publish",
]

ROOT = Path(__file__).resolve().parents[1]

#: How long to wait on the index before giving up. A pre-tag check that hangs
#: is a pre-tag check somebody skips.
TIMEOUT = 20


def declared_versions(root: Path) -> dict[str, str]:
    """Every workspace package and the version its `pyproject.toml` declares."""
    found: dict[str, str] = {}
    paths = [root / "pyproject.toml", *sorted(root.glob("packages/*/pyproject.toml"))]
    for path in paths:
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
        name, version = project.get("name"), project.get("version")
        if isinstance(name, str) and isinstance(version, str):
            found[name] = version
    return found


def to_publish(
    declared: Mapping[str, str], served: Mapping[str, Iterable[str]]
) -> dict[str, str]:
    """The packages this tag's run will upload: those the index does not serve.

    A package absent from `served` entirely is a first release and counts, which
    is the case that most needs naming — nobody is expecting it.
    """
    return {
        name: version
        for name, version in sorted(declared.items())
        if version not in set(served.get(name, ()))
    }


def names(message: str, package: str, version: str) -> bool:
    """Whether the tag message names this package **at this version**.

    Both, and adjacent: `digline-anthropic 0.5.3`. The version alone would let
    `digline 0.15.0, digline-anthropic 0.5.2` pass for a run publishing 0.5.3,
    and the name alone would let a stale line stand through a bump — which is
    the failure this exists to catch, one release later.

    Tolerant about the separator (space, `==`, `@`, `v`) and about case, because
    a check that argues with punctuation gets bypassed rather than satisfied.
    """
    pattern = (
        re.escape(package) + r"[\s]*(?:==|@|\s)[\s]*v?" + re.escape(version) + r"\b"
    )
    return re.search(pattern, message, flags=re.IGNORECASE) is not None


def missing_from_message(message: str, publishing: Mapping[str, str]) -> list[str]:
    """`package version` for everything the run publishes and the message omits."""
    return [
        f"{name} {version}"
        for name, version in sorted(publishing.items())
        if not names(message, name, version)
    ]


def served(package: str) -> set[str]:  # pragma: no cover - the one network call
    """The versions PyPI serves for a package, from the JSON API.

    The JSON API and not `/project/<name>/<version>/`, which answers 200 for any
    string somebody types and has confirmed a release that did not exist.
    """
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as reply:  # noqa: S310
            return set(json.load(reply).get("releases", {}))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return set()
        raise


def main(argv: list[str]) -> int:  # pragma: no cover - the command
    if len(argv) != 2:
        print("usage: tag_names.py '<the tag message>'", file=sys.stderr)
        return 2
    message = argv[1]
    declared = declared_versions(ROOT)
    publishing = to_publish(declared, {name: served(name) for name in declared})

    if not publishing:
        print("tag: the index already serves every version this tree declares")
        print("     nothing to publish — this tag would upload nothing")
        return 1

    print(f"tag: this run will publish {len(publishing)} package(s):")
    for name, version in sorted(publishing.items()):
        print(f"       {name} {version}")

    missing = missing_from_message(message, publishing)
    if missing:
        print(file=sys.stderr)
        print(
            "tag: the message does not name "
            f"{len(missing)} of them — {', '.join(missing)}.\n"
            "     A tag is a signature. publish.yml uploads every workspace\n"
            "     package the index lacks, so a message that names fewer than\n"
            "     the run publishes leaves the only record on PyPI's upload\n"
            "     timestamps. Name them, in the annotation, and tag again.",
            file=sys.stderr,
        )
        return 1

    print("tag: the message names every one of them")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
