"""What `digline record proxy` wrote for the SDKs of other languages, in the CI
job `through-the-proxy`. (ADR 0062 §3, §5)

`recorders/through-the-proxy.sh` sends one request,
`recorders/through-the-proxy.json`, from Node's SDKs, from LangChain4j's
OpenAI model in Java and from Python's SDKs, each a single call and a stream,
through the proxy, to the fake upstream of `tests/test_record_proxy.py`.
Python is the control. What is held here, on what the proxy wrote:

- each language's calls are recorded, under the suite its header named and
  the app it named;
- the same request gives the same case and the same setup digest from every
  language: the proof that what the proxy records does not depend on the
  language that sent it;
- `digline record import` lists them, electable.

Skipped where the job has not run, and never in the job, which sets
`DIGLINE_PROXY_REQUIRED` beside the directory.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from digline.cli.main import main
from digline.host.importing import import_listing
from digline.host.loader import load_suite

REPO = Path(__file__).resolve().parent.parent
ASKED = json.loads((REPO / "recorders" / "through-the-proxy.json").read_text())

RECORDINGS = "DIGLINE_PROXY_RECORDINGS"
REQUIRED = "DIGLINE_PROXY_REQUIRED"

SUITE = """\
[suite]
tenant = "t"
environment = "dev"
name = "triage"
cases = ["cases.json", "captured.json"]

[capture]
cases_file = "captured.json"
repository = "private"

[[assertions]]
type = "contains"
needle = "Paris"
name = "contains"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "data"

  [target.body]
  question = "case.vars.messages"
"""


@pytest.fixture
def root() -> Path:
    given = os.environ.get(RECORDINGS)
    if not given:
        assert not os.environ.get(REQUIRED), (
            f"{REQUIRED} is set and {RECORDINGS} is not"
        )
        pytest.skip(f"run by the CI job through-the-proxy, which sets {RECORDINGS}")
    return Path(given)


def written(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / ".digline" / "t" / "recordings").glob("*/*.json"))
        if not path.name.startswith(".")
    ]


def kind(recording: dict[str, Any]) -> str:
    if "id" in recording:
        return "episode"
    return "in an episode" if "episode" in recording else "call"


def test_every_language_is_recorded_and_the_same_request_digests_alike(
    root: Path,
) -> None:
    found = written(root)
    by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recording in found:
        assert recording["suite"] == ASKED["suite"]
        assert recording["response"]["output"] == "Paris"
        by_app[recording["app"]].append(recording)
    print()
    for app in sorted(by_app):
        for recording in by_app[app]:
            print(
                f"  {app:7} {kind(recording):14} "
                f"{recording['setup'].get('model', '-'):12} {recording['setup_digest']}"
            )
    assert sorted(by_app) == ["java", "node", "python"]

    def calls(app: str, model: str) -> list[dict[str, Any]]:
        return [
            r
            for r in by_app[app]
            if kind(r) == "call" and r["setup"].get("model") == model
        ]

    for route, model in (("openai", "gpt-test"), ("anthropic", "claude-test")):
        apps = ("node", "python", "java") if route == "openai" else ("node", "python")
        seen = {
            (app, r["setup_digest"], json.dumps(r["case"], sort_keys=True))
            for app in apps
            for r in calls(app, model)
        }
        # A single call and a stream from each language: one case, one
        # setup, whatever sent it.
        assert {(digest, case) for _, digest, case in seen} == {
            (
                next(iter(seen))[1],
                json.dumps({"messages": ASKED[route]["messages"]}, sort_keys=True),
            )
        }
        assert all(len(calls(app, model)) == 2 for app in apps)
    # An episode from Node and one from Python, of two calls each.
    episodes = {app: [r for r in by_app[app] if kind(r) == "episode"] for app in by_app}
    assert [len(episodes[app]) for app in ("node", "python")] == [1, 1]
    assert episodes["node"][0]["setup_digest"] == episodes["python"][0]["setup_digest"]


def test_digline_record_import_lists_them_electable(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / "cases.json").write_text('[{"id": "by-hand"}]', encoding="utf-8")
    (root / "suite.toml").write_text(SUITE, encoding="utf-8")
    suite, loaded = load_suite(str(root / "suite.toml"), root=root)
    listing = import_listing(root, suite, loaded.module, "t")
    assert listing.unreadable == 0
    assert listing.answers
    for answer in listing.answers:
        assert answer.text == "Paris"
        assert answer.input is not None
    assert [a for a in listing.answers if a.electable], [
        a.refusal for a in listing.answers
    ]
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
    print(capsys.readouterr().out)
