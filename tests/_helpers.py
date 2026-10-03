"""Helpers shared by the tests that drive the CLI in a subprocess.

Plain functions, deliberately not fixtures and deliberately not a test module.
A test module that imports another test module makes collection order matter:
`conftest.py` is imported before any test, so a fixture reached through
`tests.test_cli` is a fixture that depends on a file pytest has not read yet.
Everything shared lives here, `conftest.py` builds the fixtures on top, and no
test module imports another.
"""

from __future__ import annotations

import http.client
import json
import secrets
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from digline.cli import EXIT_OK
from digline.core import NO_BASELINE, key_of, project
from digline.core.run import run_from_json, run_to_json
from digline.store import FileResultStore

__all__ = [
    "SUITE_SOURCE",
    "cli",
    "configured_repo",
    "git",
    "hand_over",
    "run_key",
    "stamp_journal_format",
    "suite_source",
    "write_suite",
]

SUITE_SOURCE = """\
from digline.core import Contains, CostBudget, Disclosure, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

%(preamble)s
QUALITY = {"capital-fr": %(fr)s}


def _judge(prompt):
    score = QUALITY.get(_judge.case, 1.0)
    return JudgeReply(score=score, reason="judged: " + prompt[:12])


_judge.case = "capital-it"

suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[
        Contains(needle="Rome"),
        CostBudget(max_usd=0.10, tolerance=0.02),
        LlmRubric(rubric="answers?", judge=_judge, threshold=0.7, tolerance=0.05),
    ],
    cases=[Case(id="capital-it"), Case(id="capital-fr")%(extra)s],
    disclosure=Disclosure(run_metadata=frozenset({"model"})),
)


def target(case):
    if case.id == "flaky":
        raise TimeoutError("provider did not answer")
    _judge.case = case.id
    return Response(
        output="The capital is Rome.",
        input="What is the capital?",
        cost_usd=0.01,
        latency_ms=100.0,
    )
"""


def suite_source(*, fr_score: str = "1.0", extra: str = "", preamble: str = "") -> str:
    """The shared suite as text, with every seam defaulted.

    The one place `SUITE_SOURCE` is interpolated. A test that formatted the
    template itself had to name every placeholder, so adding one broke it —
    which is how `preamble` arrived. `extra` adds cases; `preamble` adds
    statements that run when the module is imported, which is how a test
    observes how many times a loader executed it.
    """
    return SUITE_SOURCE % {"fr": fr_score, "extra": extra, "preamble": preamble}


def write_suite(
    root: Path, *, fr_score: str = "1.0", extra: str = "", preamble: str = ""
) -> Path:
    path = root / "suite_qa.py"
    path.write_text(
        suite_source(fr_score=fr_score, extra=extra, preamble=preamble),
        encoding="utf-8",
    )
    return path


def baseline_in(root: Path) -> str:
    """What `promote --replacing` names in a test repository: the key of the one
    baseline under `root/.digline/`, or `none` before the first promotion.

    The honest value for a test that has just compared against that baseline,
    which is what every caller of this is doing on its way to testing something
    else. The check itself is exercised where a wrong key is named on purpose.
    A repository holding two baselines has no "the" baseline, and is refused.
    """
    found = sorted((root / ".digline").glob("*/baselines/*.json"))
    if not found:
        return NO_BASELINE
    assert len(found) == 1, f"more than one baseline under {root}: {found}"
    document = json.loads(found[0].read_text(encoding="utf-8"))
    return key_of(document["created_at"], document["config_hash"])


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "digline.cli", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def run_key(root: Path, *extra: str) -> str:
    done = cli(root, "run", "--suite", "suite_qa.py", *extra)
    assert done.returncode == EXIT_OK, done.stderr
    return done.stdout.strip()


def stamp_journal_format(
    root: Path, tenant: str, suite: str, key: str, version: int
) -> None:
    """Rewrite every leg's header to claim journal format `version`.

    So a test can build the file an *older* digline wrote out of the one this
    digline writes — a format-1 journal, of which every 0.15.x one is an
    example. Only the header is edited: the case lines keep whatever they hold,
    which is what a reader that ignores unknown keys would have met anyway.

    It asserts that it found a leg. A rewrite that silently matched nothing
    would leave the test asserting the *current* format while claiming to assert
    the old one — a check that answers without having looked.
    """
    directory = FileResultStore(root).journal_dir(tenant, suite)
    legs = sorted(directory.glob(f"{key}.*.jsonl"))
    assert legs, f"no journal leg under {directory}: the stamp would do nothing"
    for leg in legs:
        lines = leg.read_text(encoding="utf-8").splitlines()
        header = json.loads(lines[0])
        header["journal_version"] = version
        leg.write_text(
            "\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8"
        )


def hand_over(port: int, launch: str) -> str:
    """Open the printed address the way a browser does, and return the `Cookie`
    header the browser will send from then on.

    A real hand-over rather than a cookie built from the key: since 0.21.1 the
    cookie carries a session minted here and the key is spent, so a test that
    built `digline-view-PORT=KEY` by hand would be sending the one value the
    server now refuses (ADR 0033 §11).
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", f"/?launch={launch}")
    answer = connection.getresponse()
    answer.read()
    connection.close()
    assert answer.status == 303, f"the hand-over answered {answer.status}"
    set_cookie = answer.getheader("Set-Cookie") or ""
    return set_cookie.split(";", 1)[0]


CONFIGURED_TARGET = """

_plain = target


class _Configured:
    config = {config!r}

    def __call__(self, case):
        return _plain(case)


target = _Configured()
"""


def configured_repo(
    root: Path, values: Mapping[str, object], *, projected: bool
) -> Path:
    """The shared suite with a target that declares `values`, run and promoted
    through the CLI. With `projected`, the baseline is then replaced by its
    projection, which is the file the software house commits: nothing in
    digline writes a projected reference into a store, it arrives. (#402)

    The minter is one random token per name, which is all a reading needs: the
    table that could resolve them is never on this side.
    """
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    suite = write_suite(root)
    with suite.open("a", encoding="utf-8") as handle:
        handle.write(CONFIGURED_TARGET.format(config=dict(values)))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    key = run_key(root)
    done = cli(
        root, "promote", "--suite", "suite_qa.py", "--run", key, "--replacing", "none"
    )
    assert done.returncode == EXIT_OK, done.stderr
    if projected:
        (path,) = (root / ".digline").glob("*/baselines/*.json")
        clear = run_from_json(path.read_text(encoding="utf-8"))
        rows: dict[tuple[str, str], str] = {}

        def mint(kind: str, text: str) -> str:
            return rows.setdefault((kind, text), secrets.token_urlsafe(16))

        path.write_text(run_to_json(project(clear, mint)), encoding="utf-8")
    return root
