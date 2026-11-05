"""The Java recorder's contract, held from the Python side. (ADR 0062 §2, §4)

`recorders/java/DiglineRecorder.java` is held to files that digline's own
code writes, in `recorders/fixtures/`: the Java tests read them, and these
hold each one equal to what `recorders/fixtures/make.py` makes of digline
now. A change here that moves a digest, a float's text, a switch's sentence
or a recorded call's bytes turns this red until the fixtures are made again,
and then the Java side is held to the new answer.

The last test reads what the Java recorder wrote in the CI job
`recorder-java` and imports it with digline alone, no plugin installed.
"""

from __future__ import annotations

import importlib.util
import os
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from digline.cli.main import main
from digline.core.recording import setup_digest_of
from digline.host.importing import import_listing
from digline.host.loader import load_suite
from digline.host.recording import recorder_status

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "recorders" / "fixtures"

#: Where the CI job's Java run left its recordings, and whether this run must
#: find them: set together by the job, so a run of the job never skips.
RECORDINGS = "DIGLINE_JAVA_RECORDINGS"
REQUIRED = "DIGLINE_JAVA_REQUIRED"


def _expected() -> dict[str, str]:
    made = runpy.run_path(str(FIXTURES / "make.py"))
    return cast(Callable[[], dict[str, str]], made["expected"])()


def test_every_fixture_is_what_diglines_python_makes_of_it() -> None:
    expected = _expected()
    on_disk = sorted(
        str(path.relative_to(FIXTURES))
        for path in FIXTURES.rglob("*")
        if path.is_file() and path.name != "make.py"
    )
    assert on_disk == sorted(expected)
    for name, text in expected.items():
        assert (FIXTURES / name).read_text(encoding="utf-8") == text, (
            f"recorders/fixtures/{name} is not what digline makes of it now: run "
            "`uv run python recorders/fixtures/make.py`, and the Java tests are held "
            "to the new answer"
        )


def test_the_digest_measured_across_the_two_languages_is_fixed() -> None:
    # Measured in Java and in Python on 2026-11-04 (ADR 0062, *What was
    # measured*); the Java test asserts the same value.
    assert (
        setup_digest_of({"max_tokens": 64, "model": "claude-haiku-4-5"})
        == "81869b20f0d8875a"
    )


SUITE = """\
[suite]
tenant = "t"
environment = "dev"
name = "s"
cases = ["cases.json", "captured.json"]

[capture]
cases_file = "captured.json"
repository = "private"

[[assertions]]
type = "contains"
needle = "Monday"
name = "contains"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "data"

  [target.body]
  question = "case.vars.messages"
"""


def test_what_the_java_recorder_wrote_is_imported_by_digline_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    given = os.environ.get(RECORDINGS)
    if not given:
        assert not os.environ.get(REQUIRED), (
            f"{REQUIRED} is set and {RECORDINGS} is not"
        )
        pytest.skip(f"run by the CI job recorder-java, which sets {RECORDINGS}")
    root = Path(given)
    if os.environ.get(REQUIRED):
        # The job measures the import with digline alone (P-1501).
        for plugin in ("digline_openai", "digline_anthropic", "digline_bedrock"):
            assert importlib.util.find_spec(plugin) is None, f"{plugin} is installed"
    (root / "cases.json").write_text('[{"id": "by-hand"}]', encoding="utf-8")
    (root / "suite.toml").write_text(SUITE, encoding="utf-8")

    suite, loaded = load_suite(str(root / "suite.toml"), root=root)
    listing = import_listing(root, suite, loaded.module, "t")
    answers = {answer.text: answer for answer in listing.answers}
    assert sorted(answers) == [
        "A1 left the warehouse on Monday.",
        "Dans votre espace client.",
        "It was sent on Monday.",
    ]
    assert listing.unreadable == 0
    for text in ("It was sent on Monday.", "Dans votre espace client."):
        assert answers[text].electable, answers[text].refusal
        assert answers[text].input is not None
    # The episode came first, under another setup: listed, and not electable.
    episode = answers["A1 left the warehouse on Monday."]
    assert episode.refusal is not None
    assert episode.refusal.startswith("recorded only under earlier setups")
    assert episode.attached == 1

    assert (
        main(
            [
                "record",
                "import",
                "--tenant",
                "t",
                "--suite",
                str(root / "suite.toml"),
                "--root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    (status,) = recorder_status(root, "t")
    assert status.uncounted == 1
    assert main(["record", "status", "--tenant", "t", "--root", str(root)]) == 0
    out, _ = capsys.readouterr()
    assert (
        "not counted: 1 process keeps recordings and no counts, so what was not "
        "recorded there is not known"
    ) in out
