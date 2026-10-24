"""The weekly scan of the published image — driven locally, never against GHCR.

`.github/workflows/image-scan.yml` resolves `ghcr.io/digline/digline:latest`
to a digest at the moment it runs, scans each platform of that digest with
trivy, and uploads the SARIF to Code scanning. `.github/image_scan.py` is the
part that is ours:

- **the digest**, read from what `docker buildx imagetools inspect` says the
  tag points at, and refused when it is not one;
- **the digest in the result**: every result's message, and the run itself,
  name the image by digest and platform. `latest` moves, and a finding read a
  week later has to say which image it was found in;
- **the image trivy scanned is the one asked for**: a SARIF or a JSON report
  whose image is another is refused, not relabelled;
- **the counts in the summary**: the SARIF carries only what has a fixed
  version (`--ignore-unfixed`), and the job's summary still says everything
  trivy found — the total, by severity, and how many have a fix — read from an
  unfiltered JSON report of the same digest. No threshold and no red.

The SARIF and the JSON here have the shape trivy 0.76.1 wrote on 2026-10-24
for `ghcr.io/digline/digline@sha256:555e97f8…` (linux/amd64), cut down to the
fields that are read.

**What no test here proves**: that trivy finds what is in the image. That is
the scanner's, and the first scheduled run is its reading.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "image_scan.py"
WORKFLOW = ROOT / ".github" / "workflows" / "image-scan.yml"

sys.path.insert(0, str(ROOT / ".github"))
from image_scan import counts, named, resolved, summary  # noqa: E402

IMAGE = "ghcr.io/digline/digline"
DIGEST = "sha256:555e97f892d68c0ddc9ea6b0d3e170e30fb10cebb909895656dd6fb1361a9795"
OTHER = "sha256:" + "0" * 64


def _sarif(digest: str = DIGEST, results: int = 2) -> Any:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "Trivy", "rules": list[Any]()}},
                "results": [
                    {
                        "ruleId": f"CVE-2011-{3374 + i}",
                        "level": "note",
                        "message": {
                            "text": "Package: apt\nInstalled Version: 3.0.3\n"
                            f"Vulnerability CVE-2011-{3374 + i}\nSeverity: LOW"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": "digline/digline",
                                        "uriBaseId": "ROOTPATH",
                                    }
                                },
                                "message": {"text": "digline/digline: apt@3.0.3"},
                            }
                        ],
                    }
                    for i in range(results)
                ],
                "properties": {
                    "imageName": f"{IMAGE}@{digest}",
                    "repoDigests": [f"{IMAGE}@{digest}"],
                    "repoTags": [],
                },
            }
        ],
    }


def _vuln(severity: str, fixed: str = "") -> Any:
    return {
        "VulnerabilityID": "CVE-2026-0001",
        "PkgName": "apt",
        "Severity": severity,
        **({"FixedVersion": fixed} if fixed else {}),
    }


#: Seven found: HIGH 3, MEDIUM 1, LOW 2, UNKNOWN 1; two with a fixed version.
FOUND = [
    [_vuln("HIGH", "1.2"), _vuln("HIGH"), _vuln("LOW")],
    [_vuln("HIGH"), _vuln("MEDIUM", "2.0"), _vuln("LOW"), _vuln("UNKNOWN")],
]


def _report(digest: str = DIGEST) -> Any:
    """trivy's JSON report, unfiltered, for one platform of the digest."""
    return {
        "SchemaVersion": 2,
        "Metadata": {
            "ImageID": "sha256:09b0c6a3",
            "RepoDigests": [f"{IMAGE}@{digest}"],
        },
        "Results": [
            {"Target": "debian", "Vulnerabilities": FOUND[0]},
            {"Target": "Python"},
            {"Target": "python-pkg", "Vulnerabilities": FOUND[1]},
        ],
    }


def _index(digest: str = DIGEST) -> Any:
    """`imagetools inspect --format '{{json .Manifest}}'`, for a multi-arch tag."""
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "digest": digest,
        "manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
        ],
    }


# --- the digest ---------------------------------------------------------------


def test_the_tag_resolves_to_its_index_digest() -> None:
    assert resolved(_index()) == DIGEST


@pytest.mark.parametrize(
    "digest", ["", "latest", "sha256:555e97f8", "sha512:" + "0" * 128, None]
)
def test_what_is_not_a_digest_is_refused(digest: str | None) -> None:
    with pytest.raises(ValueError, match="digest"):
        resolved(_index(digest))  # type: ignore[arg-type]


# --- the digest in the result -------------------------------------------------


def test_every_result_names_the_image_by_digest_and_platform() -> None:
    out = named(_sarif(), image=IMAGE, digest=DIGEST, platform="linux/amd64")
    results = out["runs"][0]["results"]
    assert len(results) == 2
    for result in results:
        first = result["message"]["text"].splitlines()[0]
        assert first == f"In {IMAGE}@{DIGEST} (linux/amd64)."
        assert "Package: apt" in result["message"]["text"]


def test_the_run_names_the_image_by_digest_and_platform() -> None:
    out = named(_sarif(), image=IMAGE, digest=DIGEST, platform="linux/arm64")
    props = out["runs"][0]["properties"]
    assert props["digline.image"] == f"{IMAGE}@{DIGEST}"
    assert props["digline.platform"] == "linux/arm64"


def test_the_input_is_left_as_it_was() -> None:
    sarif = _sarif()
    before = json.dumps(sarif, sort_keys=True)
    named(sarif, image=IMAGE, digest=DIGEST, platform="linux/amd64")
    assert json.dumps(sarif, sort_keys=True) == before


def test_a_scan_of_another_image_is_refused() -> None:
    with pytest.raises(ValueError, match=OTHER):
        named(_sarif(OTHER), image=IMAGE, digest=DIGEST, platform="linux/amd64")


# --- the counts in the summary ------------------------------------------------


def test_the_counts_are_of_everything_found_fixed_or_not() -> None:
    found = counts(_report(), image=IMAGE, digest=DIGEST)
    assert found.total == 7
    assert found.fixed == 2
    assert found.by_severity == {
        "CRITICAL": 0,
        "HIGH": 3,
        "MEDIUM": 1,
        "LOW": 2,
        "UNKNOWN": 1,
    }


def test_a_report_of_another_image_is_refused() -> None:
    with pytest.raises(ValueError, match=OTHER):
        counts(_report(OTHER), image=IMAGE, digest=DIGEST)


def test_the_summary_says_the_digest_the_total_each_severity_and_the_fixed() -> None:
    found = counts(_report(), image=IMAGE, digest=DIGEST)
    out = named(_sarif(results=2), image=IMAGE, digest=DIGEST, platform="linux/amd64")
    line = summary(found, out, ref=f"{IMAGE}@{DIGEST}", platform="linux/amd64")
    assert f"`{IMAGE}@{DIGEST}` (linux/amd64)" in line
    assert "7 found" in line
    assert "CRITICAL 0, HIGH 3, MEDIUM 1, LOW 2, UNKNOWN 1" in line
    assert "2 with a fixed version" in line
    assert "2 results in the SARIF" in line


def _run(
    *args: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )


def test_the_command_line_writes_the_sarif_and_the_summary(tmp_path: Path) -> None:
    (tmp_path / "in.sarif").write_text(json.dumps(_sarif(results=2)), encoding="utf-8")
    (tmp_path / "all.json").write_text(json.dumps(_report()), encoding="utf-8")
    written = tmp_path / "summary.md"
    done = _run(
        "name",
        "--sarif",
        "in.sarif",
        "--json",
        "all.json",
        "--out",
        "out.sarif",
        "--image",
        IMAGE,
        "--digest",
        DIGEST,
        "--platform",
        "linux/amd64",
        cwd=tmp_path,
        env={"GITHUB_STEP_SUMMARY": str(written)},
    )
    assert done.returncode == 0, done.stderr
    out = json.loads((tmp_path / "out.sarif").read_text(encoding="utf-8"))
    assert all(
        f"{IMAGE}@{DIGEST}" in r["message"]["text"] for r in out["runs"][0]["results"]
    )
    said = written.read_text(encoding="utf-8")
    assert f"{IMAGE}@{DIGEST}" in said
    assert "linux/amd64" in said
    assert "7 found" in said
    assert "CRITICAL 0, HIGH 3, MEDIUM 1, LOW 2, UNKNOWN 1" in said
    assert "2 with a fixed version" in said


def test_the_command_line_resolves_from_standard_input(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "resolve"],
        input=json.dumps(_index()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == DIGEST


def test_the_command_line_refuses_a_tag_it_cannot_resolve(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "resolve"],
        input=json.dumps(_index("latest")),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout == ""


# --- where it runs: image-scan.yml ------------------------------------------


def _workflow() -> Any:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict[str, Any]]:
    (job,) = _workflow()["jobs"].values()
    return list(job["steps"])


def _at(text: str) -> list[int]:
    return [
        i
        for i, s in enumerate(_steps())
        if text in str(s.get("run", "")) + str(s.get("uses", ""))
    ]


def test_it_runs_on_monday_at_twenty_past_eight_and_by_hand() -> None:
    on = _workflow()[True]
    assert on["schedule"] == [{"cron": "20 8 * * 1"}]
    assert "workflow_dispatch" in on
    assert "pull_request" not in on


def test_it_may_write_security_events_and_nothing_else() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    (job,) = workflow["jobs"].values()
    assert job["permissions"] == {"contents": "read", "security-events": "write"}


def test_the_scanner_is_a_fixed_release_checked_against_its_digest() -> None:
    (install,) = _at("Linux-64bit.tar.gz")
    step = _steps()[install]
    assert "sha256sum --check" in step["run"] or "sha256sum -c" in step["run"]
    assert step["env"]["TRIVY_VERSION"] == "0.76.1"
    assert len(step["env"]["TRIVY_SHA256"]) == 64


def test_latest_is_resolved_once_and_every_scan_is_by_that_digest() -> None:
    steps = _steps()
    (resolve,) = _at("image_scan.py resolve")
    assert "ghcr.io/digline/digline:latest" in steps[resolve]["run"]
    scans = _at("trivy image")
    assert scans and all(i > resolve for i in scans)
    for i in scans:
        run = steps[i]["run"]
        assert "@${DIGEST}" in run or '@"${DIGEST}"' in run
        assert ":latest" not in run


def _scans(fmt: str) -> list[int]:
    return [i for i in _at("trivy image") if f"--format {fmt}" in _steps()[i]["run"]]


def test_the_sarif_carries_only_what_has_a_fixed_version() -> None:
    steps = _steps()
    sarif = _scans("sarif")
    assert len(sarif) == 2
    assert all("--ignore-unfixed" in steps[i]["run"] for i in sarif)


def test_the_counts_are_read_from_a_report_nothing_filters() -> None:
    steps = _steps()
    report = _scans("json")
    assert len(report) == 2
    for i in report:
        run = steps[i]["run"]
        assert "--ignore-unfixed" not in run
        assert "--severity" not in run


def test_no_scan_turns_a_finding_into_a_red() -> None:
    for i in _at("trivy image"):
        assert "--exit-code" not in _steps()[i]["run"]


def test_both_platforms_are_scanned_named_and_uploaded_in_that_order() -> None:
    steps = _steps()
    reports, sarifs, names, uploads = (
        _scans("json"),
        _scans("sarif"),
        _at("image_scan.py name"),
        _at("github/codeql-action/upload-sarif@"),
    )
    assert len(reports) == len(sarifs) == len(names) == len(uploads) == 2
    for report, sarif, name, upload in zip(
        reports, sarifs, names, uploads, strict=True
    ):
        assert report < name and sarif < name < upload
        platform = "arm64" if "arm64" in steps[sarif]["run"] else "amd64"
        assert f"linux/{platform}" in steps[report]["run"]
        run = steps[name]["run"]
        assert f"linux/{platform}" in run
        assert f"trivy-{platform}.json" in run
        assert f"trivy-{platform}.json" in steps[report]["run"]
        assert f"trivy-{platform}.sarif" in run
        assert f"trivy-{platform}.sarif" in steps[sarif]["run"]
        assert platform in steps[upload]["with"]["category"]
        assert platform in steps[upload]["with"]["sarif_file"]
        assert "named" in steps[upload]["with"]["sarif_file"]
