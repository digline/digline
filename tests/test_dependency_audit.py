"""The weekly audit of the locks — driven locally, never against osv.dev.

`.github/dependency_audit.py` runs in `.github/workflows/dependency-audit.yml`,
after osv-scanner has read the root `uv.lock` and every `examples/*/uv.lock`.
What is pinned here is the part that is ours:

- **what it reads** out of osv-scanner's JSON: one finding per advisory, per
  package, per lock, under any of the advisory's names;
- **what it subtracts**: a row of `.github/accepted_advisories.toml` accepts
  one advisory in one lock, and no other lock;
- **what it does not judge**: a scanner that failed, or a lock it never read;
- **what it does with the one issue**: rewrites it while it is open, closes it
  once nothing is left, and opens a second one never.

The JSON here has the shape osv-scanner 2.7.0 wrote on 2026-10-24 for this
repository's locks, cut down to the fields that are read.

**What no test here proves**: that osv-scanner reads every package of a
`uv.lock`. That is the scanner's, and the first scheduled run is its reading.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "dependency_audit.py"
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-audit.yml"

sys.path.insert(0, str(ROOT / ".github"))
from dependency_audit import (  # noqa: E402
    SCOPE,
    Accepted,
    decide,
    findings,
    read_accepted,
    report,
)

NLTK = "GHSA-8mgp-746c-j5xp"
SETUPTOOLS = "GHSA-xmj3-9gf7-h52w"
LOCKS = ("uv.lock", "examples/llamaindex/uv.lock", "examples/rag/uv.lock")


def _package(name: str, version: str, *advisories: tuple[str, list[str], str]) -> Any:
    """A package as osv-scanner lists it, with each advisory and its aliases."""
    return {
        "package": {"name": name, "version": version, "ecosystem": "PyPI"},
        "vulnerabilities": [
            {
                "id": vid,
                "aliases": aliases or None,
                "summary": f"{name}: something",
                "affected": [
                    {
                        "package": {"name": name, "ecosystem": "PyPI"},
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [{"introduced": "0"}]
                                + ([{"fixed": fixed}] if fixed else []),
                            }
                        ],
                    }
                ],
            }
            for vid, aliases, fixed in advisories
        ],
        "groups": [
            {"ids": [vid], "aliases": [vid, *aliases]} for vid, aliases, _ in advisories
        ],
    }


def _osv(root: Path, by_lock: dict[str, list[Any]]) -> Any:
    """osv-scanner's document: absolute paths, as it writes them."""
    return {
        "results": [
            {
                "source": {"path": str(root / lock), "type": "lockfile"},
                "packages": packages,
            }
            for lock, packages in by_lock.items()
        ]
    }


def _nltk() -> Any:
    return _package("nltk", "3.10.3", (NLTK, ["CVE-2026-81726", "PYSEC-2026-3740"], ""))


def _setuptools() -> Any:
    return _package("setuptools", "84.0.0", (SETUPTOOLS, [], "84.1.0"))


def _clean() -> Any:
    return _package("jsonschema", "4.26.0")


def _root(tmp_path: Path) -> Path:
    for lock in LOCKS:
        (tmp_path / lock).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / lock).write_text("version = 1\n", encoding="utf-8")
    return tmp_path


def _accepted(*manifests: str, ghsa: str = NLTK) -> tuple[Accepted, ...]:
    return tuple(
        Accepted(
            ghsa=ghsa,
            manifest=m,
            date=datetime.date(2026, 10, 8),
            reason="Not reached by anything we ship.",
        )
        for m in manifests
    )


# --- what it reads ----------------------------------------------------------


def test_each_advisory_is_one_finding_per_lock(tmp_path: Path) -> None:
    root = _root(tmp_path)
    osv = _osv(
        root,
        {
            "uv.lock": [_nltk(), _setuptools(), _clean()],
            "examples/llamaindex/uv.lock": [_nltk()],
            "examples/rag/uv.lock": [_clean()],
        },
    )
    found = findings(osv, root)
    assert sorted((f.manifest, f.package, f.advisory) for f in found) == [
        ("examples/llamaindex/uv.lock", "nltk", NLTK),
        ("uv.lock", "nltk", NLTK),
        ("uv.lock", "setuptools", SETUPTOOLS),
    ]
    (tools,) = [f for f in found if f.package == "setuptools"]
    assert tools.version == "84.0.0"
    assert tools.fixed == ("84.1.0",)
    (nltk,) = [f for f in found if f.manifest == "uv.lock" and f.package == "nltk"]
    assert nltk.fixed == ()
    assert {"CVE-2026-81726", "PYSEC-2026-3740", NLTK} <= nltk.names


def test_an_advisory_listed_under_another_id_is_named_by_its_ghsa(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    package = _package("nltk", "3.10.3", ("PYSEC-2026-3740", [NLTK], ""))
    found = findings(_osv(root, {"uv.lock": [package]}), root)
    assert [f.advisory for f in found] == [NLTK]


# --- what it subtracts --------------------------------------------------------


def _report(tmp_path: Path, accepted: tuple[Accepted, ...], **locks: Any) -> Any:
    root = _root(tmp_path)
    by_lock = {lock: [_clean()] for lock in LOCKS}
    by_lock.update({k.replace("__", "/"): v for k, v in locks.items()})
    return report(
        findings(_osv(root, by_lock), root),
        accepted,
        read=frozenset(by_lock),
        expected=frozenset(LOCKS),
        commit="b6d478d114030b81addab0c841a5b20c733b9aa7",
    )


def test_a_lock_with_nothing_found_is_a_pass(tmp_path: Path) -> None:
    done = _report(tmp_path, ())
    assert done["ok"] is True
    assert done["undecided"] is False
    assert done["title"].startswith(SCOPE)


def test_an_advisory_nobody_accepted_is_a_failure_that_names_it(
    tmp_path: Path,
) -> None:
    done = _report(tmp_path, (), **{"uv.lock": [_setuptools()]})
    assert done["ok"] is False
    assert done["undecided"] is False
    assert done["title"].startswith(SCOPE)
    assert SETUPTOOLS in done["body"]
    assert "setuptools 84.0.0" in done["body"]
    assert "84.1.0" in done["body"]
    assert "`uv.lock`" in done["body"]


def test_an_accepted_advisory_is_subtracted_and_still_shown(tmp_path: Path) -> None:
    done = _report(
        tmp_path,
        _accepted("uv.lock", "examples/llamaindex/uv.lock"),
        **{"uv.lock": [_nltk()], "examples__llamaindex__uv.lock": [_nltk()]},
    )
    assert done["ok"] is True
    assert NLTK in done["body"]
    assert "2026-10-08" in done["body"]
    assert "Not reached by anything we ship." in done["body"]


def test_an_acceptance_covers_its_own_lock_and_no_other(tmp_path: Path) -> None:
    done = _report(
        tmp_path,
        _accepted("uv.lock"),
        **{"uv.lock": [_nltk()], "examples__llamaindex__uv.lock": [_nltk()]},
    )
    assert done["ok"] is False
    assert "`examples/llamaindex/uv.lock`" in done["body"]


def test_an_acceptance_of_another_advisory_covers_nothing(tmp_path: Path) -> None:
    done = _report(
        tmp_path, _accepted("uv.lock", ghsa=SETUPTOOLS), **{"uv.lock": [_nltk()]}
    )
    assert done["ok"] is False


def test_an_acceptance_nothing_matches_any_more_is_said_and_not_a_failure(
    tmp_path: Path,
) -> None:
    done = _report(tmp_path, _accepted("uv.lock"))
    assert done["ok"] is True
    assert "no longer found" in done["body"]
    assert NLTK in done["body"]


# --- what it does not judge ---------------------------------------------------


def test_a_lock_the_scanner_did_not_list_is_not_judged(tmp_path: Path) -> None:
    root = _root(tmp_path)
    by_lock = {"uv.lock": [_clean()]}
    done = report(
        findings(_osv(root, by_lock), root),
        (),
        read=frozenset(by_lock),
        expected=frozenset(LOCKS),
        commit="b6d478d114030b81addab0c841a5b20c733b9aa7",
    )
    assert done["undecided"] is True
    assert "examples/rag/uv.lock" in done["body"]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _accepted_file(root: Path, text: str = "") -> Path:
    path = root / "accepted.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("code", ["2", "127", "128"])
def test_a_scanner_that_failed_is_not_judged(tmp_path: Path, code: str) -> None:
    """Even with a document that would read as clean: the exit code decides."""
    root = _root(tmp_path)
    clean = _osv(root, {lock: [_clean()] for lock in LOCKS})
    (root / "osv.json").write_text(json.dumps(clean), encoding="utf-8")
    done = _run(
        "report",
        "--osv",
        "osv.json",
        "--osv-exit",
        code,
        "--accepted",
        str(_accepted_file(root)),
        "--commit",
        "b6d478d114030b81addab0c841a5b20c733b9aa7",
        "--out",
        "report.json",
        cwd=root,
    )
    assert done.returncode == 0, done.stderr
    written = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert written["undecided"] is True
    assert written["ok"] is False
    assert code in written["body"]


def test_the_command_line_reads_osv_and_the_accepted_file(tmp_path: Path) -> None:
    root = _root(tmp_path)
    osv = _osv(root, {lock: [_nltk()] for lock in LOCKS})
    (root / "osv.json").write_text(json.dumps(osv), encoding="utf-8")
    rows = "".join(
        f'[[advisory]]\nghsa = "{NLTK}"\nmanifest = "{lock}"\n'
        'date = 2026-10-08\nreason = "Not reached by anything we ship."\n\n'
        for lock in LOCKS
    )
    done = _run(
        "report",
        "--osv",
        "osv.json",
        "--osv-exit",
        "1",
        "--accepted",
        str(_accepted_file(root, rows)),
        "--commit",
        "b6d478d114030b81addab0c841a5b20c733b9aa7",
        "--out",
        "report.json",
        cwd=root,
    )
    assert done.returncode == 0, done.stderr
    written = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert written["ok"] is True, written["body"]
    assert written["undecided"] is False
    assert "b6d478d114030b81addab0c841a5b20c733b9aa7" in written["body"]


# --- the accepted file --------------------------------------------------------


def test_a_row_is_read_with_its_four_fields() -> None:
    (row,) = read_accepted(
        f'[[advisory]]\nghsa = "{NLTK}"\nmanifest = "uv.lock"\n'
        'date = 2026-10-08\nreason = "Not reached by anything we ship."\n'
    )
    assert row == _accepted("uv.lock")[0]


@pytest.mark.parametrize(
    ("row", "said"),
    [
        (
            'ghsa = "GHSA-8mgp"\nmanifest = "uv.lock"\ndate = 2026-10-08\nreason = "r"',
            "ghsa",
        ),
        (
            f'ghsa = "{NLTK}"\nmanifest = "uv.lock"\ndate = "2026-10-08"\nreason = "r"',
            "date",
        ),
        (
            f'ghsa = "{NLTK}"\nmanifest = "uv.lock"\ndate = 2026-10-08\nreason = ""',
            "reason",
        ),
        (
            f'ghsa = "{NLTK}"\nmanifest = "/uv.lock"\ndate = 2026-10-08\nreason = "r"',
            "manifest",
        ),
        (f'ghsa = "{NLTK}"\nmanifest = "uv.lock"\nreason = "r"', "date"),
        (
            f'ghsa = "{NLTK}"\nmanifest = "uv.lock"\ndate = 2026-10-08\n'
            'reason = "r"\nuntil = 2027-01-01',
            "until",
        ),
    ],
)
def test_a_malformed_row_is_refused_and_says_which_field(row: str, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        read_accepted("[[advisory]]\n" + row + "\n")


def test_the_same_advisory_twice_in_one_lock_is_refused() -> None:
    row = (
        f'[[advisory]]\nghsa = "{NLTK}"\nmanifest = "uv.lock"\n'
        'date = 2026-10-08\nreason = "r"\n'
    )
    with pytest.raises(ValueError, match="twice"):
        read_accepted(row + row)


# --- the one issue ------------------------------------------------------------


def _issues(*titles: str) -> list[dict[str, Any]]:
    return [{"number": 700 + i, "title": t} for i, t in enumerate(titles)]


FAILING: dict[str, Any] = {"ok": False, "undecided": False}
PASSING: dict[str, Any] = {"ok": True, "undecided": False}
UNREAD: dict[str, Any] = {"ok": False, "undecided": True}


def test_a_failure_with_the_issue_open_rewrites_it() -> None:
    issues = _issues("release-followup: v0.33.0", f"{SCOPE}: 1 advisory")
    assert decide(issues, FAILING) == "edit 701"


def test_a_failure_with_no_issue_open_opens_one() -> None:
    assert decide(_issues("release-followup: v0.33.0"), FAILING) == "create"


def test_a_pass_with_the_issue_open_closes_it() -> None:
    assert decide(_issues(f"{SCOPE}: 1 advisory"), PASSING) == "close 700"


def test_a_pass_with_nothing_open_does_nothing() -> None:
    assert decide(_issues(), PASSING) == "nothing"


@pytest.mark.parametrize("titles", [(), (f"{SCOPE}: 1 advisory",)])
def test_a_reading_nobody_made_leaves_the_issue_as_it_is(
    titles: tuple[str, ...],
) -> None:
    assert decide(_issues(*titles), UNREAD) == "leave"


def test_the_command_line_says_the_action(tmp_path: Path) -> None:
    (tmp_path / "open.json").write_text(
        json.dumps(_issues(f"{SCOPE}: 2 advisories")), encoding="utf-8"
    )
    (tmp_path / "report.json").write_text(json.dumps(FAILING), encoding="utf-8")
    done = _run(
        "decide", "--issues", "open.json", "--report", "report.json", cwd=tmp_path
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "edit 700"


# --- where it runs: dependency-audit.yml ------------------------------------


def _workflow() -> Any:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict[str, Any]]:
    (job,) = _workflow()["jobs"].values()
    return list(job["steps"])


def _index(text: str) -> int:
    (found,) = [i for i, s in enumerate(_steps()) if text in str(s.get("run", ""))]
    return found


def test_it_runs_on_monday_at_eight_and_by_hand() -> None:
    # PyYAML reads the key `on` as the boolean True.
    on = _workflow()[True]
    assert on["schedule"] == [{"cron": "0 8 * * 1"}]
    assert "workflow_dispatch" in on
    assert "pull_request" not in on


def test_it_may_write_issues_and_nothing_else() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    (job,) = workflow["jobs"].values()
    assert job["permissions"] == {"contents": "read", "issues": "write"}


def test_the_checkout_leaves_no_credentials_behind() -> None:
    (checkout,) = [s for s in _steps() if "actions/checkout@" in str(s.get("uses"))]
    assert checkout["with"]["persist-credentials"] is False


def test_the_scanner_is_a_fixed_release_checked_against_its_digest() -> None:
    install = _steps()[_index("osv-scanner_linux_amd64")]
    run = install["run"]
    assert "sha256sum --check" in run or "sha256sum -c" in run
    env = install["env"]
    assert env["OSV_SCANNER_VERSION"] == "2.7.0"
    assert len(env["OSV_SCANNER_SHA256"]) == 64


def test_every_lock_is_scanned_with_every_package_listed() -> None:
    run = _steps()[_index("scan source")]["run"]
    assert "uv.lock" in run
    assert "examples/*/uv.lock" in run
    assert "--all-packages" in run
    assert "--format json" in run


def test_the_scan_feeds_the_report_and_the_report_the_one_issue() -> None:
    scan = _index("scan source")
    made = _index("dependency_audit.py report")
    decided = _index("dependency_audit.py decide")
    assert scan < made < decided
    run = _steps()[decided]["run"]
    assert "gh issue edit" in run
    assert "gh issue create" in run
    assert "gh issue close" in run
    assert "gh issue reopen" not in run
    assert f"--label {'dependency-audit'}" in run


def test_the_red_comes_last_after_the_issue() -> None:
    steps = _steps()
    assert "exit 1" in str(steps[-1].get("run", ""))
    assert _index("dependency_audit.py decide") == len(steps) - 2
