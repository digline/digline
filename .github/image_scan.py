"""The weekly scan of the published image: the digest, and the digest in the result.

`.github/workflows/image-scan.yml` scans `ghcr.io/digline/digline:latest`
with trivy every Monday, for each platform it is published for, and uploads
the SARIF to Code scanning, where *Before the tag: the alert list* reads it. A
base image ages between releases, which is why it is a schedule and not a step
of `docker-publish.yml`.

`latest` moves. So the tag is resolved to a digest once, at the start of the
run, every scan is of that digest, and every result says which image it was
found in. Without that, a finding read a week later names a tag that may by
then point at another image.

**Two reports of each platform, and only one is filtered.** The SARIF is made
with `--ignore-unfixed`: what reaches Code scanning is what somebody can act
on, a finding with a fixed version. The job's summary is read from an
unfiltered JSON report of the same digest and says everything trivy found: the
total, by severity, and how many have a fix. No threshold, and no severity
makes the job red.

    docker buildx imagetools inspect IMAGE:latest --format '{{json .Manifest}}' \\
        | python3 .github/image_scan.py resolve
    python3 .github/image_scan.py name --sarif trivy.sarif --json trivy.json \\
        --out named.sarif --image IMAGE --digest sha256:... --platform linux/amd64

`resolve` prints the digest, or refuses with exit 1. `name` writes the SARIF
with the image named by digest and platform in every result's message and in
the run's properties, refuses a SARIF or a JSON report of another image, and
writes the counts to `$GITHUB_STEP_SUMMARY` when it is set. Standard library
only: this runs under the runner's bare `python3`.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DIGEST = re.compile(r"\Asha256:[0-9a-f]{64}\Z")

#: trivy's severities, in the order the summary says them. Each is said, zero
#: included, so two weeks' summaries read line against line.
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


@dataclass(frozen=True)
class Counts:
    """Everything trivy found in one platform of the image, fixed or not."""

    total: int
    by_severity: dict[str, int]
    #: How many have a fixed version, which is what the SARIF carries.
    fixed: int


def resolved(manifest: Mapping[str, Any]) -> str:
    """The digest a tag points at, from `imagetools inspect`'s manifest."""
    digest = manifest.get("digest")
    if not isinstance(digest, str) or not DIGEST.match(digest):
        raise ValueError(f"the tag did not resolve to a sha256 digest: {digest!r}")
    return digest


def named(
    sarif: Mapping[str, Any], *, image: str, digest: str, platform: str
) -> dict[str, Any]:
    """A copy of trivy's SARIF that says, in every result, which image it is."""
    if not DIGEST.match(digest):
        raise ValueError(f"{digest!r} is not a sha256 digest")
    ref = f"{image}@{digest}"
    out: dict[str, Any] = copy.deepcopy(dict(sarif))
    for run in out.get("runs") or []:
        properties: dict[str, Any] = run.setdefault("properties", {})
        scanned = properties.get("imageName")
        if scanned != ref:
            raise ValueError(f"trivy scanned {scanned!r}, and {ref} was asked for")
        properties["digline.image"] = ref
        properties["digline.platform"] = platform
        for result in run.get("results") or []:
            message: dict[str, Any] = result.setdefault("message", {})
            message["text"] = f"In {ref} ({platform}).\n" + str(message.get("text", ""))
    return out


def counts(report: Mapping[str, Any], *, image: str, digest: str) -> Counts:
    """The counts of trivy's unfiltered JSON report, refused for another image."""
    ref = f"{image}@{digest}"
    scanned = (report.get("Metadata") or {}).get("RepoDigests") or []
    if ref not in scanned:
        raise ValueError(f"trivy's report is of {scanned!r}, and {ref} was asked for")
    by_severity = dict.fromkeys(SEVERITIES, 0)
    total = fixed = 0
    for result in report.get("Results") or []:
        for vulnerability in result.get("Vulnerabilities") or []:
            total += 1
            severity = str(vulnerability.get("Severity") or "UNKNOWN")
            by_severity[severity if severity in by_severity else "UNKNOWN"] += 1
            if vulnerability.get("FixedVersion"):
                fixed += 1
    return Counts(total=total, by_severity=by_severity, fixed=fixed)


def summary(found: Counts, sarif: Mapping[str, Any], *, ref: str, platform: str) -> str:
    """The run's summary for one platform: the digest, and the counts."""
    carried = sum(len(run.get("results") or []) for run in sarif.get("runs") or [])
    severities = ", ".join(f"{s} {found.by_severity[s]}" for s in SEVERITIES)
    return (
        f"- `{ref}` ({platform}): {found.total} found — {severities}; "
        f"{found.fixed} with a fixed version, and {carried} results in the SARIF "
        "for Code scanning\n"
    )


def _resolve_command() -> int:
    try:
        print(resolved(json.loads(sys.stdin.read())))
    except ValueError as exc:
        print(f"image_scan: {exc}", file=sys.stderr)
        return 1
    return 0


def _name_command(args: argparse.Namespace) -> int:
    sarif = json.loads(Path(args.sarif).read_text(encoding="utf-8"))
    report = json.loads(Path(args.json).read_text(encoding="utf-8"))
    try:
        out = named(sarif, image=args.image, digest=args.digest, platform=args.platform)
        found = counts(report, image=args.image, digest=args.digest)
    except ValueError as exc:
        print(f"image_scan: {exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(out) + "\n", encoding="utf-8")
    ref = f"{args.image}@{args.digest}"
    line = summary(found, out, ref=ref, platform=args.platform)
    print(line, end="")
    where = os.environ.get("GITHUB_STEP_SUMMARY")
    if where:
        with open(where, "a", encoding="utf-8") as handle:
            handle.write(line)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="image_scan.py")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("resolve")
    name = commands.add_parser("name")
    name.add_argument("--sarif", required=True)
    name.add_argument("--json", required=True)
    name.add_argument("--out", required=True)
    name.add_argument("--image", required=True)
    name.add_argument("--digest", required=True)
    name.add_argument("--platform", required=True)
    args = parser.parse_args(argv)
    if args.command == "resolve":
        return _resolve_command()
    return _name_command(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
