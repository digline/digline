"""The weekly audit of the locks: osv-scanner's findings, less what we accepted.

Dependabot's version updates move only what a manifest declares, and its
security updates are off here, so a transitive package moves only when
somebody reads its alert. This reads what the locks resolve to, every Monday,
without waiting for an alert: the root `uv.lock` and every `examples/*/uv.lock`,
through osv-scanner, in `.github/workflows/dependency-audit.yml`.

**What is subtracted.** A row of `.github/accepted_advisories.toml` accepts one
advisory in one lock, with the date it was accepted and why. The same advisory
in another lock is still a finding. Each row is declared in `SECURITY.md`'s
*Advisories against a dependency*, and `tests/test_accepted_advisories.py`
holds the two to each other.

**Where a finding goes.** Into one issue, labelled `dependency-audit`, on the
precedent of `release_followup.py`: a failing run rewrites it while it is open
and opens it when it is not, a passing run closes it, and a run that could not
read something leaves it as it is. The job is red as well, last.

    python3 .github/dependency_audit.py report --osv osv.json --osv-exit 1 \\
        --accepted .github/accepted_advisories.toml --commit SHA --out report.json
    python3 .github/dependency_audit.py decide --issues open.json --report report.json

`report` writes `{ok, undecided, scope, title, body}`. `decide` prints one of
`leave`, `nothing`, `close N`, `edit N` or `create`. Standard library only:
this runs under the runner's bare `python3`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

#: The prefix of the one issue's title, which is how a run finds it.
SCOPE = "Dependency audit"
LABEL = "dependency-audit"
ACCEPTED = ".github/accepted_advisories.toml"

GHSA = re.compile(r"\AGHSA(?:-[23456789cfghjmpqrvwx]{4}){3}\Z")
FIELDS = ("ghsa", "manifest", "date", "reason")

#: What osv-scanner's exit code means. 0 is no advisory, 1 is at least one;
#: anything else (127, 128 and the rest) is a scan that did not happen.
READ = (0, 1)


@dataclass(frozen=True)
class Accepted:
    """One advisory, accepted in one lock."""

    ghsa: str
    manifest: str
    date: datetime.date
    reason: str


@dataclass(frozen=True)
class Found:
    """One advisory against one package in one lock."""

    manifest: str
    package: str
    version: str
    #: The GHSA identifier when the advisory has one, its first id otherwise.
    advisory: str
    #: Every name the advisory goes by: its ids and their aliases.
    names: frozenset[str]
    summary: str
    #: The versions osv lists as fixing it, for this package; () is none.
    fixed: tuple[str, ...]


def read_accepted(text: str) -> tuple[Accepted, ...]:
    """The rows of the accepted file. A malformed one is refused, by field."""
    rows: list[Accepted] = []
    seen: set[tuple[str, str]] = set()
    for number, raw in enumerate(tomllib.loads(text).get("advisory", []), start=1):
        row = cast(dict[str, Any], raw)
        where = f"{ACCEPTED}, row {number}"
        extra = sorted(set(row) - set(FIELDS))
        if extra:
            raise ValueError(f"{where}: {', '.join(extra)} is not a field of a row")
        for field in FIELDS:
            if field not in row:
                raise ValueError(f"{where}: {field} is missing")
        ghsa, manifest, date, reason = (row[f] for f in FIELDS)
        if not isinstance(ghsa, str) or not GHSA.match(ghsa):
            raise ValueError(f"{where}: ghsa {ghsa!r} is not a GHSA identifier")
        if (
            not isinstance(manifest, str)
            or not manifest.endswith("uv.lock")
            or manifest.startswith("/")
            or ".." in Path(manifest).parts
        ):
            raise ValueError(
                f"{where}: manifest {manifest!r} is not a lock's path from the root"
            )
        if not isinstance(date, datetime.date) or isinstance(date, datetime.datetime):
            raise ValueError(f"{where}: date {date!r} is not a TOML date")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{where}: reason is empty")
        if (ghsa, manifest) in seen:
            raise ValueError(f"{where}: {ghsa} is accepted twice in {manifest}")
        seen.add((ghsa, manifest))
        rows.append(Accepted(ghsa, manifest, date, reason))
    return tuple(rows)


def _relative(path: str, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path


def _fixed(vulnerability: Mapping[str, Any], package: str) -> tuple[str, ...]:
    versions: list[str] = []
    for affected in vulnerability.get("affected") or []:
        if (affected.get("package") or {}).get("name") != package:
            continue
        for span in affected.get("ranges") or []:
            for event in span.get("events") or []:
                if "fixed" in event:
                    versions.append(str(event["fixed"]))
    return tuple(versions)


def findings(osv: Mapping[str, Any], root: Path) -> tuple[Found, ...]:
    """One finding per advisory, per package, per lock."""
    found: list[Found] = []
    for result in osv.get("results") or []:
        manifest = _relative(str(result["source"]["path"]), root)
        for listed in result.get("packages") or []:
            package = listed["package"]
            by_id = {v["id"]: v for v in listed.get("vulnerabilities") or []}
            for group in listed.get("groups") or []:
                ids = [str(i) for i in group.get("ids") or []]
                names = frozenset(ids) | frozenset(
                    str(a) for a in group.get("aliases") or []
                )
                for vid in ids:
                    names |= frozenset(by_id.get(vid, {}).get("aliases") or [])
                ghsas = sorted(n for n in names if GHSA.match(n))
                first = by_id.get(ids[0], {}) if ids else {}
                found.append(
                    Found(
                        manifest=manifest,
                        package=str(package["name"]),
                        version=str(package["version"]),
                        advisory=ghsas[0] if ghsas else ids[0],
                        names=names,
                        summary=str(first.get("summary") or "").strip(),
                        fixed=_fixed(first, str(package["name"])),
                    )
                )
    return tuple(found)


def read_locks(osv: Mapping[str, Any], root: Path) -> frozenset[str]:
    """The locks osv-scanner listed. With `--all-packages`, every one it read."""
    return frozenset(
        _relative(str(r["source"]["path"]), root) for r in osv.get("results") or []
    )


def expected_locks(root: Path) -> frozenset[str]:
    """The locks the workflow hands the scanner, found the way it finds them."""
    locks = [root / "uv.lock", *sorted((root / "examples").glob("*/uv.lock"))]
    return frozenset(p.relative_to(root).as_posix() for p in locks if p.is_file())


def _match(found: Found, accepted: Sequence[Accepted]) -> Accepted | None:
    for row in accepted:
        if row.manifest == found.manifest and row.ghsa in found.names:
            return row
    return None


def _link(advisory: str) -> str:
    return f"[{advisory}](https://osv.dev/{advisory})"


def _count(n: int) -> str:
    return f"{n} advisor{'y' if n == 1 else 'ies'}"


def report(
    found: Sequence[Found],
    accepted: Sequence[Accepted],
    *,
    read: frozenset[str],
    expected: frozenset[str],
    commit: str,
) -> dict[str, Any]:
    """What the run says: the open findings, the accepted ones, the stale rows."""
    unread = sorted(expected - read)
    if unread:
        return not_judged(
            commit,
            "osv-scanner did not list "
            + ", ".join(f"`{u}`" for u in unread)
            + ", so it was not read",
        )
    open_: list[Found] = []
    kept: list[tuple[Found, Accepted]] = []
    for item in sorted(found, key=lambda f: (f.manifest, f.package, f.advisory)):
        row = _match(item, accepted)
        if row is None:
            open_.append(item)
        else:
            kept.append((item, row))
    used = {row for _, row in kept}
    stale = [row for row in accepted if row not in used]

    lines: list[str] = []
    if open_:
        lines += [
            f"**{_count(len(open_))} in the locks, and nobody accepted "
            f"{'it' if len(open_) == 1 else 'them'}.**",
            "",
            "| Advisory | Package | Lock | Fixed in |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {_link(f.advisory)} | {f.package} {f.version} | `{f.manifest}` | "
            f"{', '.join(f.fixed) if f.fixed else 'no fixed version'} |"
            for f in open_
        ]
        lines += [
            "",
            "A finding with a fixed version is owed a `uv lock --upgrade-package` "
            "that names it, in every lock it is listed in. One that is accepted "
            f"instead takes a row in `{ACCEPTED}` and a line in `SECURITY.md`'s "
            "*Advisories against a dependency*, which a test holds to each other.",
        ]
    else:
        lines.append("**Every advisory osv-scanner lists in the locks is accepted.**")
    if kept:
        lines += [
            "",
            "Accepted, and still found:",
            "",
            "| Advisory | Package | Lock | Accepted | Why |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {_link(row.ghsa)} | {f.package} {f.version} | `{f.manifest}` | "
            f"{row.date.isoformat()} | {row.reason} |"
            for f, row in kept
        ]
    if stale:
        lines += [
            "",
            f"Accepted, and no longer found, so the row can go from `{ACCEPTED}`:",
            "",
        ]
        lines += [
            f"- {_link(row.ghsa)} in `{row.manifest}`, accepted {row.date.isoformat()}"
            for row in stale
        ]
    lines += ["", f"Read on `{commit}`: {', '.join(f'`{r}`' for r in sorted(read))}."]
    title = (
        f"{SCOPE}: {_count(len(open_))} in the locks not accepted"
        if open_
        else f"{SCOPE}: nothing in the locks that is not accepted"
    )
    return {
        "ok": not open_,
        "undecided": False,
        "scope": SCOPE,
        "title": title,
        "body": "\n".join(lines) + "\n",
    }


def not_judged(commit: str, why: str) -> dict[str, Any]:
    """A run that read nothing it could judge, and says so."""
    return {
        "ok": False,
        "undecided": True,
        "scope": SCOPE,
        "title": f"{SCOPE}: not judged",
        "body": f"**Not judged:** {why}. Read on `{commit}`.\n",
    }


def decide(issues: Sequence[Mapping[str, Any]], done: Mapping[str, Any]) -> str:
    """What to do with the one issue, given the open ones and the report."""
    mine = next(
        (int(i["number"]) for i in issues if str(i["title"]).startswith(SCOPE)), None
    )
    if done["undecided"]:
        return "leave"
    if done["ok"]:
        return "nothing" if mine is None else f"close {mine}"
    return "create" if mine is None else f"edit {mine}"


def _report_command(args: argparse.Namespace) -> int:
    root = Path(args.root)
    accepted = read_accepted(Path(args.accepted).read_text(encoding="utf-8"))
    if args.osv_exit not in READ:
        done = not_judged(
            args.commit, f"osv-scanner exited {args.osv_exit}, so it read nothing"
        )
    else:
        try:
            osv = json.loads(Path(args.osv).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            done = not_judged(
                args.commit, f"osv-scanner's output could not be read ({exc})"
            )
        else:
            done = report(
                findings(osv, root),
                accepted,
                read=read_locks(osv, root),
                expected=expected_locks(root),
                commit=args.commit,
            )
    Path(args.out).write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
    print(done["title"])
    return 0


def _decide_command(args: argparse.Namespace) -> int:
    issues = json.loads(Path(args.issues).read_text(encoding="utf-8"))
    done = json.loads(Path(args.report).read_text(encoding="utf-8"))
    print(decide(issues, done))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dependency_audit.py")
    commands = parser.add_subparsers(dest="command", required=True)
    made = commands.add_parser("report")
    made.add_argument("--osv", required=True)
    made.add_argument("--osv-exit", type=int, required=True)
    made.add_argument("--accepted", default=ACCEPTED)
    made.add_argument("--commit", required=True)
    made.add_argument("--root", default=".")
    made.add_argument("--out", required=True)
    decided = commands.add_parser("decide")
    decided.add_argument("--issues", required=True)
    decided.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    if args.command == "report":
        return _report_command(args)
    return _decide_command(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
