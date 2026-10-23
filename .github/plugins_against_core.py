"""The core this tag releases, against every plugin PyPI serves.

Ruled on 2026-10-18 (RELEASING.md, *What CI proves about each index*): between
the `testpypi` job and the `pypi` gate, the core as TestPyPI serves it — the
wheel the `pypi` job will publish — is installed in a clean environment beside
each plugin at the newest version PyPI serves, and each plugin is tried the way
its users try it. A user who installs or upgrades the core gets exactly that
pair, and nothing else tests it: `tests/test_plugin_floors.py` looks the other
way, from the plugin in the tree to the core it needs.

0.32.0 is why. It made an argument of `headline` mandatory, and both served
plugins that call the comparison broke on it: pytest-digline 0.2.4 stopped
every session that named a suite, and digline-mcp 0.5.0 answered `compare` with
*"Error executing tool compare"*. Each was found after the tag.

Each plugin ends in one of three words, and only one of them is red:

    works     in the range it declares, installed beside this core, and tried.
    excluded  its newest served version caps digline below this core, so a
              project that holds it keeps the previous core. Not a break: the
              cap is doing its job. It is a debt — this release owes that
              plugin a release (RELEASING.md, *Before the tag: moving the
              number*, "The plugins, after this release").
    broken    in its range, and it does not install or does not work beside
              this core. Red: `testpypi` fails and `pypi` does not start.

A plugin PyPI does not serve yet has no user to break, and is reported as such.

How each plugin is tried, and why from what it declares rather than a list:

- **digline-mcp, every tool**, over stdio as a client meets it. The tools are
  the ones the server lists, not a list written here: a tool this script has no
  arguments for is red, so a new tool cannot go untried by being new.
- **pytest-digline, a session that names a suite**, once comparing the stored
  run and once with `--digline-run`.
- **a provider, by building its entry point through the core**: a TOML suite
  whose target and both judges name it, loaded by `digline list` with no key in
  the environment and no network. The core resolves the plugin by name and
  calls its three factories with the keywords a suite file gives them, which is
  where a signature breaks. A provider is any plugin that registers a
  `digline.providers` entry point.

A plugin with none of the three is red too, for the same reason as the tool.

Subcommands:

    check     plugins_against_core.py check            (in the job, from the
              workspace root with `dist/` in it)
    exercise  <python> plugins_against_core.py exercise KIND NAME DIR
              (run by `check` with each plugin's own interpreter)

Exit codes: 0 every plugin works or is excluded, 1 one is broken, 2 not judged
(PyPI never answered: nothing was learned, and the remedy is a re-run).

`check` needs `packaging`, to read a range as pip reads it; the step installs it.
`exercise` runs in the plugin's environment and needs only what is there.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
PYPI = os.environ.get("PYPI", "https://pypi.org").rstrip("/")
TESTPYPI = os.environ.get("TESTPYPI", "https://test.pypi.org").rstrip("/")
CORE = "digline"

#: Where the debt an exclusion records is ruled.
OWED = (
    "RELEASING.md, *Before the tag: moving the number*, "
    '"The plugins, after this release"'
)

#: How each plugin that is not a provider is tried. A provider is recognised by
#: its entry point, so a new one needs no line here; any other new plugin does.
EXERCISES = {"digline-mcp": "mcp", "pytest-digline": "pytest"}

#: A model each provider builds with. Construction calls nothing, so the model
#: only has to be one the plugin accepts at build time.
MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "bedrock": "anthropic.claude-3-haiku-20240307-v1:0",
}

#: Each install is tried this many times, `PAUSE` seconds apart: the earlier
#: step installed this core from TestPyPI already, so a wait here is a CDN.
ATTEMPTS = int(os.environ.get("ATTEMPTS", "5"))
PAUSE = float(os.environ.get("PAUSE", "15"))


class Broken(Exception):
    """The plugin is in its range and does not work beside this core."""


class NotJudged(Exception):
    """A read PyPI never answered: nothing was learned about any plugin."""


# --- check ---------------------------------------------------------------------


@dataclass(frozen=True)
class Served:
    name: str
    version: str
    requires: str  # the plugin's range on digline, as declared; "" for none


@dataclass(frozen=True)
class Outcome:
    name: str
    word: str  # works | excluded | broken | not served
    version: str
    requires: str
    detail: str


def _wheel(path: pathlib.Path) -> tuple[str, str]:
    name, version = path.name.split("-")[:2]
    return name.replace("_", "-").lower(), version


def roster(dist: pathlib.Path) -> tuple[str, list[str]]:
    """The core's version this tag built, and every other package it built."""
    built = dict(_wheel(p) for p in dist.glob("*.whl"))
    if CORE not in built:
        raise SystemExit(
            f"::error title=No core in dist/::{dist} holds no {CORE} wheel, so "
            "there is no core to try the plugins against"
        )
    plugins = sorted(name for name in built if name != CORE)
    if not plugins:
        raise SystemExit(
            f"::error title=No plugins in dist/::{dist} holds no plugin, so this "
            "would pass by trying nothing"
        )
    return built[CORE], plugins


def _read(url: str) -> dict[str, Any] | None:
    """PyPI's JSON page, `None` for a 404, `NotJudged` when it never answered."""
    import urllib.error
    import urllib.request

    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code < 500:
                raise NotJudged(f"{url} answered {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        if attempt < ATTEMPTS:
            time.sleep(PAUSE)
    raise NotJudged(f"{url} did not answer on {ATTEMPTS} reads")


def served(name: str) -> Served | None:
    """The newest version PyPI serves of `name`, and its range on digline."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    page = _read(f"{PYPI}/pypi/{name}/json")
    if page is None:
        return None
    info = page["info"]
    ranges = [
        str(requirement.specifier)
        for requirement in map(Requirement, info.get("requires_dist") or [])
        if canonicalize_name(requirement.name) == CORE
        and (requirement.marker is None or requirement.marker.evaluate({"extra": ""}))
    ]
    return Served(name=name, version=info["version"], requires=",".join(ranges))


def admits(requires: str, core: str) -> bool:
    """Whether a range admits this core, read as pip reads it."""
    from packaging.specifiers import SpecifierSet

    return SpecifierSet(requires).contains(core, prereleases=True)


def _pip(python: pathlib.Path, *args: str) -> None:
    """`pip install`, tried `ATTEMPTS` times; red with pip's own words."""
    said = ""
    for attempt in range(1, ATTEMPTS + 1):
        done = subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "--no-cache-dir", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode == 0:
            return
        said = done.stdout + done.stderr
        if attempt < ATTEMPTS:
            print(f"install did not resolve, try {attempt + 1} in {PAUSE:.0f}s")
            time.sleep(PAUSE)
    raise Broken(f"does not install beside this core:\n{said}")


def _installed(python: pathlib.Path, name: str) -> str:
    return subprocess.run(
        [
            str(python),
            "-c",
            f"import importlib.metadata as m; print(m.version({name!r}))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def kind_of(python: pathlib.Path, name: str) -> str:
    """How `name` is tried: by name, or as a provider by its entry point."""
    if name in EXERCISES:
        return EXERCISES[name]
    registered = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m, sys; "
            "print(' '.join(p.name for p in m.distribution(sys.argv[1]).entry_points "
            "if p.group == 'digline.providers'))",
            name,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if len(registered) == 1:
        return f"provider:{registered[0]}"
    raise Broken(
        f"no exercise is declared for {name}: it is not one of "
        f"{sorted(EXERCISES)} and registers {len(registered)} digline.providers "
        "entry points rather than one. Say in plugins_against_core.py how its "
        "users run it"
    )


def install(root: pathlib.Path, plugin: Served, core: str) -> pathlib.Path:
    """A clean environment: this core from TestPyPI, the plugin from PyPI."""
    venv = root / plugin.name / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / "bin" / "python"
    # The same indexes as the step before, which installed this core already:
    # TestPyPI for the core, PyPI for what TestPyPI does not have.
    _pip(
        python,
        "--index-url",
        f"{TESTPYPI}/simple/",
        "--extra-index-url",
        f"{PYPI}/simple/",
        f"{CORE}=={core}",
    )
    _pip(python, "--index-url", f"{PYPI}/simple/", f"{plugin.name}=={plugin.version}")
    # Held by name, because a lagging index resolves the previous release and
    # every command after would pass having proved nothing (RELEASING.md,
    # *What CI proves about each index*).
    for name, version in ((CORE, core), (plugin.name, plugin.version)):
        found = _installed(python, name)
        if found != version:
            raise Broken(
                f"asked for {name}=={version} and the environment holds {found}"
            )
    return python


def quickstart(sdist: pathlib.Path, into: pathlib.Path) -> pathlib.Path:
    """`examples/quickstart` from the sdist this tag built: the suite every
    plugin is tried on, offline, and the one the steps before already ran."""
    with tarfile.open(sdist) as archive:
        members = [m for m in archive.getmembers() if "/examples/quickstart/" in m.name]
        archive.extractall(into, members=members, filter="data")
    (found,) = into.glob("*/examples/quickstart")
    return found


def check(dist: pathlib.Path, work: pathlib.Path) -> list[Outcome]:
    core, plugins = roster(dist)
    (sdist,) = dist.glob(f"{CORE}-{core}.tar.gz")
    example = quickstart(sdist, work / "sdist")
    outcomes: list[Outcome] = []
    for name in plugins:
        plugin = served(name)
        if plugin is None:
            outcomes.append(
                Outcome(name, "not served", "", "", "no version on PyPI yet")
            )
            continue
        if not admits(plugin.requires, core):
            outcomes.append(
                Outcome(
                    name,
                    "excluded",
                    plugin.version,
                    plugin.requires,
                    f"excluded by its cap, so this release owes it a release ({OWED})",
                )
            )
            continue
        print(f"--- {name} {plugin.version}, which declares digline{plugin.requires}")
        try:
            python = install(work, plugin, core)
            kind = kind_of(python, name)
            app = work / name / "app"
            shutil.copytree(example, app)
            done = subprocess.run(
                [
                    str(python),
                    str(HERE / "plugins_against_core.py"),
                    "exercise",
                    kind,
                    name,
                    str(app),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            print(done.stdout + done.stderr, end="")
            if done.returncode != 0:
                raise Broken(f"failed its exercise ({kind}); its output is above")
            outcomes.append(
                Outcome(name, "works", plugin.version, plugin.requires, kind)
            )
        except Broken as exc:
            outcomes.append(
                Outcome(name, "broken", plugin.version, plugin.requires, str(exc))
            )
    return outcomes


def summary(core: str, outcomes: Sequence[Outcome]) -> str:
    lines = [
        f"### digline {core} against the plugins PyPI serves",
        "",
        "| Plugin | Newest on PyPI | Its range on digline | Outcome |",
        "|---|---|---|---|",
    ]
    for o in outcomes:
        detail = o.detail.splitlines()[0] if o.detail else ""
        lines.append(
            f"| `{o.name}` | {o.version or '—'} | `{o.requires or 'any'}` "
            f"| **{o.word}**: {detail} |"
        )
    return "\n".join(lines) + "\n"


def main_check() -> int:
    dist = pathlib.Path("dist")
    core, _ = roster(dist)
    with tempfile.TemporaryDirectory() as tmp:
        outcomes = check(dist, pathlib.Path(tmp))
    section = summary(core, outcomes)
    print(section)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(section + "\n")
    broken = [o for o in outcomes if o.word == "broken"]
    for o in broken:
        print(
            f"::error title={o.name} {o.version} breaks against digline {core}::"
            f"{o.detail.splitlines()[0]}",
            file=sys.stderr,
        )
    return 1 if broken else 0


# --- exercise: runs inside the plugin's own environment -------------------------


def _digline(app: pathlib.Path, *args: str) -> str:
    done = subprocess.run(
        [str(pathlib.Path(sys.executable).parent / "digline"), *args],
        cwd=app,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(
            f"digline {' '.join(args)} exited {done.returncode}:\n{done.stderr}"
        )
    return done.stdout


def _promoted(app: pathlib.Path) -> None:
    _digline(app, "run", "--suite", "suite.py")
    _digline(
        app, "promote", "--suite", "suite.py", "--run", "latest", "--replacing", "none"
    )


def exercise_pytest(app: pathlib.Path) -> None:
    """A session that names the suite, comparing the stored run and then
    running it first, as the two ways its users invoke it."""
    _promoted(app)
    tests = app / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("def test_app():\n    pass\n", encoding="utf-8")
    for extra in ([], ["--digline-run"]):
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--digline-suite",
                "suite.py",
                *extra,
                "tests",
            ],
            cwd=app,
            capture_output=True,
            text=True,
            check=False,
        )
        print(done.stdout + done.stderr, end="")
        said = f"pytest --digline-suite suite.py {' '.join(extra)}"
        if done.returncode != 0:
            raise SystemExit(f"{said} exited {done.returncode}")
        print(f"{said}: exit 0")


SUITE = {"suite": "suite.py"}


def tool_arguments(tool: str, keys: Sequence[str]) -> dict[str, Any]:
    """What each tool is called with; `run` is called apart, with its count.

    A tool the server lists and this does not know is red, not skipped: the
    roster is the server's, so a new tool is tried or says why it is not."""
    match tool:
        case "list_runs" | "get_run" | "get_baseline" | "log" | "compare" | "explain":
            return SUITE
        case "diff":
            return {**SUITE, "run1": keys[0], "run2": keys[1]}
        case _:
            raise SystemExit(
                f"the server lists a tool `{tool}` this script has no arguments "
                "for: say in plugins_against_core.py how to call it"
            )


def exercise_mcp(app: pathlib.Path) -> None:
    """Every tool the server lists, over stdio, with two runs and a baseline
    in the store so that each one has something to answer about."""
    import anyio
    from mcp import ClientSession, StdioServerParameters, stdio_client

    _promoted(app)
    _digline(app, "run", "--suite", "suite.py")
    suite = SUITE
    keys: list[str] = []

    def text(result: Any) -> str:
        return "".join(getattr(c, "text", "") for c in result.content)

    async def go() -> None:
        params = StdioServerParameters(
            command=str(pathlib.Path(sys.executable).parent / "digline-mcp"),
            args=["--root", str(app)],
            env=dict(os.environ),
        )
        with anyio.fail_after(120):
            async with (
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = sorted(t.name for t in (await session.list_tools()).tools)
                print(f"the server lists {len(tools)} tools: {', '.join(tools)}")
                if not tools:
                    raise SystemExit(
                        "the server lists no tools: this would pass by calling none"
                    )
                listed = await session.call_tool("list_runs", suite)
                if listed.is_error:
                    raise SystemExit(f"list_runs: {text(listed)}")
                keys.extend(re.findall(r'"key":\s*"([^"]+)"', text(listed)))
                if len(keys) < 2:
                    raise SystemExit(
                        f"list_runs named {len(keys)} runs, and two were written"
                    )
                for tool in tools:
                    if tool == "run":
                        # The refusal carries the count to type back (ADR 0011 §2),
                        # and then the call with it measures for real, offline.
                        asked = await session.call_tool("run", suite)
                        count = re.search(r"acknowledge_calls=(\d+)", text(asked))
                        if not asked.is_error or count is None:
                            raise SystemExit(f"run without a count: {text(asked)}")
                        result = await session.call_tool(
                            "run", {**suite, "acknowledge_calls": int(count.group(1))}
                        )
                    else:
                        result = await session.call_tool(
                            tool, tool_arguments(tool, keys)
                        )
                    if result.is_error:
                        raise SystemExit(f"{tool}: {text(result)}")
                    print(f"{tool}: answered")

    try:
        anyio.run(go)
    except BaseExceptionGroup as group:
        # The SDK's task group wraps what `go` raised; the sentence is the
        # first exit inside it, and anything else is shown whole.
        # The groups nest, one per task group the client opens.
        exits = group.subgroup(SystemExit)
        if exits is None:
            raise
        first: BaseException = exits
        while isinstance(first, BaseExceptionGroup):
            first = first.exceptions[0]
        raise first from None


def exercise_provider(app: pathlib.Path, provider: str) -> None:
    """The plugin's three factories, built by the core from a suite file, with
    no key in the environment and nothing reachable."""
    model = MODELS.get(provider)
    if model is None:
        raise SystemExit(
            f"no model is declared for the provider `{provider}`: add one to "
            "MODELS in plugins_against_core.py"
        )
    coordinate = f"{provider}/{model}"
    probe = app / "provider"
    probe.mkdir()
    (probe / "prompt.md").write_text("Answer: {{question}}\n", encoding="utf-8")
    (probe / "cases.json").write_text(
        json.dumps([{"id": "a", "vars": {"question": "hi"}, "context": "hi"}]),
        encoding="utf-8",
    )
    (probe / "suite.toml").write_text(
        f"""[suite]
tenant = "probe"
environment = "ci"
name = "probe"
cases = "cases.json"

[target]
type = "provider"
provider = "{coordinate}"
prompt_file = "prompt.md"
max_tokens = 64

[[assertions]]
type = "llm_rubric"
rubric = "Is it polite?"
judge = "{coordinate}"
threshold = 0.5
tolerance = 0.05

[[assertions]]
type = "faithfulness"
judge = "{coordinate}"
threshold = 0.5
tolerance = 0.05
""",
        encoding="utf-8",
    )
    # No key, and nothing to reach if a factory tried: building calls nothing.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and not k.startswith("AWS_")
    }
    env |= {
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    done = subprocess.run(
        [
            str(pathlib.Path(sys.executable).parent / "digline"),
            "list",
            "--suite",
            "suite.toml",
        ],
        cwd=probe,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    print(done.stdout + done.stderr, end="")
    if done.returncode != 0:
        raise SystemExit(
            f"digline list on a suite naming {coordinate} exited {done.returncode}"
        )
    print(f"{coordinate}: target, judge and claim judge built by the core")


def main_exercise(kind: str, name: str, app: pathlib.Path) -> int:
    print(f"exercise {name} as {kind}")
    if kind == "pytest":
        exercise_pytest(app)
    elif kind == "mcp":
        exercise_mcp(app)
    elif kind.startswith("provider:"):
        exercise_provider(app, kind.removeprefix("provider:"))
    else:
        raise SystemExit(f"no exercise called {kind!r}")
    return 0


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["check"]:
            try:
                sys.exit(main_check())
            except NotJudged as exc:
                print(
                    f"::error title=Plugins against the core not judged::{exc}",
                    file=sys.stderr,
                )
                sys.exit(2)
        case ["exercise", kind, name, app]:
            sys.exit(main_exercise(kind, name, pathlib.Path(app)))
        case _:
            sys.exit("usage: plugins_against_core.py check | exercise KIND NAME DIR")
