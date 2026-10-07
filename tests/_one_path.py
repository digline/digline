"""#481's layout, shared by ADR 0045's tests in the root suite, digline-mcp and
pytest-digline, so the three front ends are measured on one layout.

A repository `R`, the perimeter, with a suite at `R/eval/suite.py` (or
`suite.toml`), and a directory `OUT` outside it. A prompt with its own text
sits in each of `R/eval`, `R` and `OUT`, so the file a target read and the file
a run recorded can be told apart by what they say.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests._helpers import git

SUITE = """\
import json
import os
from pathlib import Path

from digline.core import Contains
from digline.run import Case, Suite
from digline.targets import ModelPrice, Pricing, ProviderTarget, Usage

HERE = Path(__file__).parent
CALLS = HERE.parent.parent / "calls.jsonl"


class Stub(ProviderTarget):
    \"\"\"A provider that writes down every prompt it is sent.\"\"\"

    provider = "stub"

    def _complete(self, prompt, system):
        with CALLS.open("a", encoding="utf-8") as calls:
            calls.write(json.dumps(prompt) + "\\n")
        return "ok", Usage(input_tokens=1, output_tokens=1)


suite = Suite(
    tenant="acme",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="ok")],
    cases=[Case(id="one")],
    pinned=[%(pinned)s],
)
%(target)s
%(after)s
"""

BARE = '"prompt.txt"'
ANCHORED = 'HERE / "prompt.txt"'

#: The provider target, built from `prompt`.
STUB = (
    'target = Stub(%(prompt)s, "m1", '
    'pricing=Pricing({"m1": ModelPrice(1.0, 1.0, 0.1)}))'
)

#: A target that answers through `HasArtifacts` a path it did not resolve, so
#: ADR 0045 §5's refusal can be reached through a front end: `ProviderTarget`
#: never answers relative.
RELATIVE = """
class Naming:
    def artifacts(self):
        return [Path(%(prompt)s)]

    def __call__(self, case):
        from digline.run import Response
        return Response(output="ok", cost_usd=0.0)


target = Naming()
"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layout(
    tmp_path: Path,
    *,
    prompt: str = BARE,
    pinned: str = "",
    after: str = "",
    target: str = STUB,
) -> Path:
    """#481's layout under `tmp_path`, which holds `R`, `OUT` and `calls.jsonl`.
    Returns `R`."""
    root = tmp_path / "R"
    (root / "eval").mkdir(parents=True)
    (tmp_path / "OUT").mkdir()
    git(root, "init", "-q")
    for where in ("R/eval", "R", "OUT"):
        (tmp_path / where / "prompt.txt").write_text(f"text of {where}\n", "utf-8")
    (root / "eval" / "suite.py").write_text(
        SUITE
        % {"target": target % {"prompt": prompt}, "pinned": pinned, "after": after},
        "utf-8",
    )
    return root


def recorded(root: Path, key: str) -> dict[str, dict[str, str]]:
    (path,) = (root / ".digline").rglob(f"runs/*/{key}.json")
    return json.loads(path.read_text("utf-8"))["artifacts"]


def sent(tmp_path: Path) -> list[str]:
    calls = tmp_path / "calls.jsonl"
    if not calls.exists():
        return []
    return [json.loads(line) for line in calls.read_text("utf-8").splitlines()]


TOML = """
[suite]
tenant = "acme"
environment = "staging"
name = "qa"
cases = "cases.json"

[target]
type = "provider"
provider = "anthropic/claude-haiku-4-5"
prompt_file = "prompt.md"
max_tokens = 20

[[assertions]]
type = "contains"
needle = "ok"
"""


def toml_layout(tmp_path: Path) -> Path:
    root = tmp_path / "R"
    (root / "eval").mkdir(parents=True)
    (tmp_path / "OUT").mkdir()
    git(root, "init", "-q")
    for where in ("R/eval", "R", "OUT"):
        (tmp_path / where / "prompt.md").write_text(f"text of {where}\n", "utf-8")
    (root / "eval" / "cases.json").write_text('[{"id": "one"}]', "utf-8")
    (root / "eval" / "suite.toml").write_text(TOML, "utf-8")
    return root


@contextmanager
def fake_anthropic() -> Iterator[tuple[list[str], str]]:
    """A Messages endpoint on loopback that keeps every prompt it is sent, and
    its base URL. Whoever runs a command points the SDK at it through
    `ANTHROPIC_BASE_URL`."""
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["content-length"])
            body = json.loads(self.rfile.read(length))
            seen.append(body["messages"][0]["content"])
            reply = json.dumps(
                {
                    "id": "m",
                    "type": "message",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, format: str, *args: object) -> None: ...

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield seen, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
