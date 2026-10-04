"""A file that is not UTF-8 is refused where it is read.

An implicit `UnicodeDecodeError` is a `ValueError`. While `main()` took every
`ValueError` for a refusal, each of these exited 64 by accident, with the
codec's sentence. ADR 0041 §4.2 made a bare `ValueError` a failure nobody
anticipated, exit 70. So each read of a file the user owns names the bytes
itself, at the read. It is not done by a rule in `main()`, which would also
catch a decode error inside digline itself, the confusion §4.2 removes.

There are five reads: a Python suite, a TOML suite's cases file, a run, a
baseline, and a declared artifact. The TOML suite file and the register already
refused it in words.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests._helpers import NO_BASELINE, cli, git, run_key, suite_source

from digline.cli import EXIT_OK, EXIT_USAGE
from digline.host import UsageError, load_suite

SUITE = ("--suite", "suite_qa.py")
NOT_UTF8 = b'{"a": "\xff"}'


def committed(root: Path, source: bytes) -> Path:
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "suite_qa.py").write_bytes(source)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def test_a_suite_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    root = committed(tmp_path, b"# \xff\n" + suite_source().encode("utf-8"))
    done = cli(root, "run", *SUITE)
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "suite_qa.py is not UTF-8 at byte 2" in done.stderr
    assert "Traceback" not in done.stderr


def test_a_baseline_that_is_not_utf8_is_refused(repo: Path) -> None:
    key = run_key(repo)
    done = cli(repo, "promote", *SUITE, "--run", key, "--replacing", NO_BASELINE)
    assert done.returncode == EXIT_OK, done.stderr
    baseline = next((repo / ".digline").glob("*/baselines/*.json"))
    baseline.write_bytes(NOT_UTF8)

    done = cli(repo, "compare", *SUITE, "--run", key)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "DocumentRefusedError:" in done.stderr
    assert "is not UTF-8 at byte 7" in done.stderr


def test_a_run_that_is_not_utf8_is_refused(repo: Path) -> None:
    key = run_key(repo)
    stored = next((repo / ".digline").rglob(f"runs/qa/{key}.json"))
    stored.write_bytes(NOT_UTF8)

    done = cli(repo, "explain", *SUITE, "--run", key)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "DocumentRefusedError:" in done.stderr
    assert "is not UTF-8 at byte 7" in done.stderr


def test_an_artifact_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_bytes(b"You are \xff helpful.\n")
    source = suite_source() + (
        "\nimport dataclasses\n"
        "suite = dataclasses.replace(suite, artifacts=['prompt.md'])\n"
    )
    root = committed(tmp_path, source.encode("utf-8"))

    done = cli(root, "run", *SUITE)

    assert done.returncode == EXIT_USAGE, done.stderr
    assert "declares the artifact prompt.md, which is not UTF-8 at byte 8" in (
        done.stderr
    )


TOML_SUITE = """
[suite]
tenant = "northwind"
environment = "staging"
name = "support"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"

[[assertions]]
type = "contains"
needle = "Northwind Support"
"""


def test_a_cases_file_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    (tmp_path / "suite.toml").write_text(TOML_SUITE, encoding="utf-8")
    (tmp_path / "cases.json").write_bytes(b"[\xff]")
    with pytest.raises(UsageError, match=r"cases\.json is not UTF-8"):
        load_suite(str(tmp_path / "suite.toml"))
