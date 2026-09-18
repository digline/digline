"""Capture what the home of digline.dev shows, by running digline.

    uv run python tools/home_capture.py            # writes docs/assets/home/home.json
    uv run python tools/home_capture.py --check    # fails if that file is stale

The home used to carry a console block typed into the page, printed by a version
three minors old and reproducible by nobody. This replaces it with a file that
came out of the CLI: every command's stdout and stderr exactly as they were
written, its exit code, and the run keys it produced. `sync-docs.sh` copies
`docs/` to the site, so the file arrives there with everything else.

Two scenarios, each in its own temporary directory, initialised as a git
repository so that the run records a commit:

- **quickstart** — the three files of the guide's first chapter, read out of
  its fences by the same reader the guide's test uses, then run, promote,
  compare. The guide is not copied here: when it changes, this changes.
- **prompt_regression** — the same files, derived so that the canned model
  follows one line of a `prompt.md` the suite declares as an artifact. Run,
  promote, change that line, run, compare. It must end red, with at least one
  case worse, or this script fails: a capture that stayed green would put a
  claim on the home that the tool did not make.

Nothing here reaches the network, and it is run with the provider credentials
removed from the environment and the proxies pointed at a closed port, so an
accidental call fails rather than spends.

A tool, not part of the package: it lives outside `src/` and is never shipped.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import metadata, requires
from pathlib import Path
from typing import Any, cast, get_args

from packaging.requirements import Requirement

from doc_fences import python_files

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "guide.md"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
OUTPUT = ROOT / "docs" / "assets" / "home" / "home.json"
METRICS = ROOT / "docs" / "metrics.md"

#: Removed from the environment of every command. Names, never values.
STRIPPED = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
STRIPPED_PREFIXES = ("AWS_",)
#: Port 9 is discard, and nothing listens on it locally: a client that honours
#: the proxy variables fails at once instead of reaching a provider.
CLOSED_PROXY = "http://127.0.0.1:9"

TENANT = "northwind"
SUITE = "support"

SIGNATURE_LINE = 'Sign every reply as "— Northwind Support".'
CHANGED_LINE = 'Sign every reply as "— the Northwind team".'

PROMPT = f"""\
You are the support assistant for Northwind.
Answer the customer's question in one sentence.
{SIGNATURE_LINE}
"""

#: The steady scenario's prompt: the signature line the quickstart's answers are
#: signed with, and a line of guidance that costs tokens and changes nothing
#: else. The second is the one that moves between its two runs.
GUIDANCE_LINE = "Keep the answer to one sentence."
CHANGED_GUIDANCE = (
    "Keep the answer to one sentence, say what the customer can do next, name "
    "the policy it comes from, avoid jargon and internal codes, never promise a "
    "date the order page does not already show, and do not repeat the question "
    "back."
)

STEADY_PROMPT = f"""\
You are the support assistant for Northwind.
{GUIDANCE_LINE}
{SIGNATURE_LINE}
"""

#: What one call costs, per sample, in the steady fixture: a canned model that
#: bills the prompt it was sent and never the same twice to the last cent. Five
#: numbers, cycled, so a run measures a band and two runs of the same prompt
#: measure the same one. They add up to zero, so the mean is the prompt's own
#: cost, and they are wider than the suite's declared tolerance — a band
#: narrower than the tolerance can never absorb anything, because `compare`
#: asks the tolerance first (ADR 0009).
JITTER = (0.0, 0.004, -0.004, 0.003, -0.003)

MODEL_STEADY = (
    "The model and the judge are canned: no provider is called. The reply is "
    "billed for the prompt it was sent, plus a jitter that cycles through five "
    "values, so five samples of a case measure a band; the only edit between "
    "the two runs is one line of prompt.md, which the suite declares."
)

MODEL = (
    "The model and the judge are canned: no provider is called. The reply "
    "depends on the prompt by construction — each canned answer is signed with "
    "whatever the signature line of prompt.md asks for — and that line is the "
    "only edit made between the two runs."
)


class CaptureError(Exception):
    """The capture did not show what the home needs it to show."""


# ── the fixtures ──────────────────────────────────────────────────────────────


def chapter_one_files(guide: str) -> dict[str, str]:
    """The files as the guide has them when chapter 1 runs.

    Later chapters rewrite `app.py`, and `python_files` keeps the last version
    of a name, so the text is cut before chapter 2.
    """
    found = re.search(r"^## 2\. ", guide, re.MULTILINE)
    if found is None:
        raise CaptureError("docs/guide.md has no chapter 2 heading to stop at")
    files = python_files(guide[: found.start()])
    expected = {"app.py", "rules.py", "support.py"}
    if set(files) != expected:
        raise CaptureError(
            f"chapter 1 of docs/guide.md carries {sorted(files)}, "
            f"expected {sorted(expected)}"
        )
    return files


def _replace_once(text: str, old: str, new: str, *, where: str) -> str:
    if text.count(old) != 1:
        raise CaptureError(
            f"{where}: expected exactly one {old!r} to derive the prompt fixture "
            "from; the guide changed, so this derivation has to follow it"
        )
    return text.replace(old, new)


def steady_fixture(files: dict[str, str]) -> dict[str, str]:
    """The quickstart, with a prompt that is paid for and a case set aside.

    Three differences from the quickstart, and each is a thing the home's
    sentence has to be able to say:

      * the reply is billed for the prompt it was sent — its cost is the
        prompt's length plus a jitter that cycles through JITTER — so five
        samples of a case measure a band rather than one number;
      * `prompt.md` is declared as an artifact, so a change to it is a file
        under test that changed;
      * one case is suspended, with its reason, so nothing runs it.

    The same rule as the other fixtures: every edit must match exactly once.
    """
    app = _replace_once(
        files["app.py"],
        '"""The system under test, and the judge. Both would be yours."""\n',
        '"""The system under test, and the judge. Both would be yours."""\n\n'
        "import itertools\n\n"
        f"JITTER = {JITTER!r}\n"
        "_SAMPLE = itertools.count()\n",
        where="app.py",
    )
    app = _replace_once(
        app,
        "def reply(question_id: str) -> tuple[str, float]:\n"
        '    """Your model call. Canned, so this page needs no key."""\n'
        "    text = ANSWERS[question_id]\n"
        "    return text, 0.004 + 0.001 * len(text) / 100\n",
        "def reply(question_id: str, prompt: str) -> tuple[str, float]:\n"
        '    """Your model call. Canned, and billed for the prompt it was sent."""\n'
        "    text = ANSWERS[question_id]\n"
        "    cost = 0.004 + 0.001 * (len(text) + len(prompt)) / 100\n"
        "    return text, cost + JITTER[next(_SAMPLE) % len(JITTER)]\n",
        where="app.py",
    )
    support = _replace_once(
        files["support.py"],
        "import app\n",
        "from pathlib import Path\n\nimport app\n",
        where="support.py",
    )
    support = _replace_once(
        support,
        "app.reply(case.id)",
        'app.reply(case.id, Path("prompt.md").read_text(encoding="utf-8"))',
        where="support.py",
    )
    support = _replace_once(
        support,
        f'    name="{SUITE}",\n',
        f'    name="{SUITE}",\n'
        '    artifacts=[Path("prompt.md")],\n'
        "    samples=5,\n"
        '    min_agreement="3/5",\n',
        where="support.py",
    )
    support = _replace_once(
        support,
        '        Case(id="is-it-waterproof"),\n',
        '        Case(id="is-it-waterproof"),\n'
        '        Case(id="refund-status", '
        'suspended="the refund API is down, ticket 412"),\n',
        where="support.py",
    )
    return {**files, "app.py": app, "support.py": support, "prompt.md": STEADY_PROMPT}


def prompt_fixture(files: dict[str, str]) -> dict[str, str]:
    """The quickstart, with the reply made to depend on a prompt line.

    Every edit is a replacement that must match exactly once, so a guide that
    moves under it stops the capture instead of producing a different fixture.
    """
    app = _replace_once(
        files["app.py"],
        '"""The system under test, and the judge. Both would be yours."""\n',
        '"""The system under test, and the judge. Both would be yours."""\n\n'
        "import re\n",
        where="app.py",
    )
    app = _replace_once(
        app,
        "def reply(question_id: str) -> tuple[str, float]:\n"
        '    """Your model call. Canned, so this page needs no key."""\n'
        "    text = ANSWERS[question_id]\n",
        "def reply(question_id: str, prompt: str) -> tuple[str, float]:\n"
        '    """Your model call. Canned, and signed as the prompt says."""\n'
        '    text = ANSWERS[question_id].removesuffix(" — Northwind Support")\n'
        "    signature = re.search(r'^Sign every reply as \"(.+)\"\\.$', prompt, "
        "re.MULTILINE)\n"
        "    if signature is not None:\n"
        '        text = f"{text} {signature.group(1)}"\n',
        where="app.py",
    )
    support = _replace_once(
        files["support.py"],
        "import app\n",
        "from pathlib import Path\n\nimport app\n",
        where="support.py",
    )
    support = _replace_once(
        support,
        "app.reply(case.id)",
        'app.reply(case.id, Path("prompt.md").read_text(encoding="utf-8"))',
        where="support.py",
    )
    support = _replace_once(
        support,
        f'    name="{SUITE}",\n',
        f'    name="{SUITE}",\n    artifacts=[Path("prompt.md")],\n',
        where="support.py",
    )
    return {**files, "app.py": app, "support.py": support, "prompt.md": PROMPT}


# ── running ───────────────────────────────────────────────────────────────────


def clean_environment() -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in STRIPPED and not name.startswith(STRIPPED_PREFIXES)
    }
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env[name] = env[name.lower()] = CLOSED_PROXY
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)
    # The temporary repository must not inherit a signing key, a hook path or
    # an identity from whoever runs this.
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    for role in ("AUTHOR", "COMMITTER"):
        env[f"GIT_{role}_NAME"] = "digline capture"
        env[f"GIT_{role}_EMAIL"] = "capture@digline.invalid"
    return env


@dataclass
class Workspace:
    path: Path
    env: dict[str, str]
    commands: list[dict[str, Any]]

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        )

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def digline(self, *args: str) -> dict[str, Any]:
        """One command, recorded as it came out. Nothing is stripped or joined."""
        done = subprocess.run(
            [sys.executable, "-m", "digline.cli", *args],
            cwd=self.path,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        entry: dict[str, Any] = {
            "cmd": " ".join(("digline", *args)),
            "stdout": done.stdout,
            "stderr": done.stderr,
            "exit": done.returncode,
        }
        self.commands.append(entry)
        return entry

    def run(self) -> str:
        entry = self.digline("run", "--suite", "support.py")
        if entry["exit"] != 0:
            raise CaptureError(f"`{entry['cmd']}` exited {entry['exit']}")
        return entry["stdout"].strip()

    def run_document(self, key: str) -> dict[str, Any]:
        path = self.path / ".digline" / TENANT / "runs" / SUITE / f"{key}.json"
        document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return document


def workspace(root: Path, files: dict[str, str]) -> Workspace:
    root.mkdir(parents=True)
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    space = Workspace(path=root, env=clean_environment(), commands=[])
    space.git("init", "-q")
    space.commit("The suite")
    return space


def band(documents: list[dict[str, Any]]) -> str:
    """What the run files say about the interval each check measured.

    Read from the documents, never assumed: a verdict that was sampled carries
    `sample_min` and `sample_max`, and one that was not carries neither.
    """
    found: set[str] = set()
    for document in documents:
        verdicts = [v for r in document["results"] for v in r["verdicts"]]
        samples = max(
            (int(v.get("metadata", {}).get("samples", 1)) for v in verdicts),
            default=1,
        )
        widths = [
            v["sample_max"] - v["sample_min"]
            for v in verdicts
            if v.get("sample_min") is not None and v.get("sample_max") is not None
        ]
        if not widths:
            found.add(f"absent: samples={samples}")
        elif all(w == 0 for w in widths):
            found.add(f"zero-width: samples={samples}, every sample agreed")
        else:
            found.add(f"measured: samples={samples}")
    return "; ".join(sorted(found))


def _succeeded(entry: dict[str, Any]) -> None:
    if entry["exit"] != 0:
        raise CaptureError(
            f"`{entry['cmd']}` exited {entry['exit']}\n{entry['stdout']}"
            f"{entry['stderr']}"
        )


def quickstart(root: Path, guide: str) -> dict[str, Any]:
    space = workspace(root, chapter_one_files(guide))
    key = space.run()
    _succeeded(space.digline("promote", "--suite", "support.py", "--run", "latest"))
    space.commit("Promote the baseline")
    compared = space.digline("compare", "--suite", "support.py", "--run", "latest")
    if compared["exit"] != 0:
        raise CaptureError(
            f"the quickstart compare exited {compared['exit']}, not 0:\n"
            f"{compared['stdout']}{compared['stderr']}"
        )
    return {
        "run_ids": [key],
        "change": None,
        "band": band([space.run_document(key)]),
        "commands": space.commands,
    }


def steady(root: Path, guide: str) -> dict[str, Any]:
    """A green comparison with something in it.

    The quickstart's compare says four things and three of them are "nothing".
    This one moves what can move without anything getting worse: the prompt is
    declared and paid for, so a line of it changing is a file under test that
    changed and a cost that moves — and, five samples in, moves no further than
    the band the reference measured. One case is suspended throughout.

    It must end green, with a check inside the noise, a suspended case and a
    changed artifact, or this script fails: a capture that lost any of the three
    would put on /start/ a sentence the tool did not print.
    """
    space = workspace(root, steady_fixture(chapter_one_files(guide)))
    before = space.run()
    _succeeded(space.digline("promote", "--suite", "support.py", "--run", "latest"))
    space.commit("Promote the baseline")

    prompt = root / "prompt.md"
    prompt.write_text(
        _replace_once(
            prompt.read_text(encoding="utf-8"),
            GUIDANCE_LINE,
            CHANGED_GUIDANCE,
            where="prompt.md",
        ),
        encoding="utf-8",
    )
    space.commit("Reword the guidance line of the prompt")

    after = space.run()
    compared = space.digline("compare", "--suite", "support.py", "--run", "latest")
    as_json = space.digline(
        "compare", "--suite", "support.py", "--run", "latest", "--json", "full"
    )
    facts: dict[str, Any] = json.loads(as_json.pop("stdout"))
    if compared["exit"] != 0 or as_json["exit"] != 0:
        raise CaptureError(
            f"the steady scenario did not stay green: exits {compared['exit']} "
            f"and {as_json['exit']}\n{compared['stdout']}{compared['stderr']}"
        )
    for name, wrong in steady_problems(facts):
        raise CaptureError(f"the steady scenario has no {name}: {wrong}")

    return {
        "run_ids": [before, after],
        "model": MODEL_STEADY,
        "change": {
            "description": "One line of prompt.md, the guidance line, reworded.",
            "files": prompt_diff(root, after),
        },
        "band": band([space.run_document(before), space.run_document(after)]),
        "commands": space.commands,
        "compare_json": {
            "source": (
                f"The stdout of `{as_json['cmd']}` above, decoded with "
                "json.loads and otherwise unchanged: every key but this one "
                "is digline's."
            ),
            **facts,
        },
    }


def steady_problems(facts: dict[str, Any]) -> list[tuple[str, Any]]:
    """What the steady scenario must show, read out of `compare --json full`.

    Returned rather than raised so that both the capture and `--check` hold the
    file to the same four claims: green, a check inside the noise, a case set
    aside, and a file under test that changed under rules that did not.
    """
    counts = cast(dict[str, int], facts.get("counts") or {})
    deltas = cast(list[dict[str, Any]], facts.get("deltas") or [])
    within = [d for d in deltas if d.get("within_noise") and not d.get("calibration")]
    problems: list[tuple[str, Any]] = []
    if counts.get("regressed"):
        problems.append(
            ("green comparison", f"{counts['regressed']} check(s) regressed")
        )
    if not within:
        problems.append(("check that moved within the noise", "none of the deltas did"))
    if not facts.get("suspended"):
        problems.append(("suspended case", f"suspended is {facts.get('suspended')!r}"))
    if not facts.get("artifacts_changed"):
        problems.append(("changed file under test", "artifacts_changed is false"))
    if facts.get("config_changed"):
        problems.append(("unchanged suite", "config_changed is true"))
    return problems


def prompt_diff(workdir: Path, key: str) -> list[dict[str, Any]]:
    """The diff of each changed file under test, as digline produces it.

    `compare` prints only the tally (`prompt.md · +1 −1 lines`); the lines
    themselves are what the report renders, from `digline.report.diff_lines`
    over the comparison `digline.core.compare` builds from the stored run and
    baseline. The same two functions, called here, so nothing is reconstructed.
    """
    from digline.core import compare
    from digline.report import diff_lines
    from digline.store import FileResultStore, RunRef

    store = FileResultStore(workdir)
    run = store.read_run(RunRef(tenant=TENANT, suite=SUITE, key=key))
    baseline = store.read_baseline(TENANT, SUITE)
    if baseline is None:
        raise CaptureError("the prompt scenario has no baseline to diff against")
    return [
        {"path": delta.path, "outcome": delta.outcome, "diff": diff_lines(delta)}
        for delta in compare(run, baseline).artifact_deltas
        if delta.outcome not in ("same", "unknown")
    ]


def prompt_regression(root: Path, guide: str) -> dict[str, Any]:
    space = workspace(root, prompt_fixture(chapter_one_files(guide)))
    before = space.run()
    _succeeded(space.digline("promote", "--suite", "support.py", "--run", "latest"))
    space.commit("Promote the baseline")

    prompt = root / "prompt.md"
    prompt.write_text(
        _replace_once(
            prompt.read_text(encoding="utf-8"),
            SIGNATURE_LINE,
            CHANGED_LINE,
            where="prompt.md",
        ),
        encoding="utf-8",
    )
    space.commit("Change the signature line of the prompt")

    after = space.run()
    compared = space.digline("compare", "--suite", "support.py", "--run", "latest")
    as_json = space.digline(
        "compare", "--suite", "support.py", "--run", "latest", "--json", "full"
    )
    # The stdout is kept once, decoded, in `compare_json`: carrying it again as
    # a string beside the object it decodes to doubled the file for nothing.
    stdout = as_json.pop("stdout")
    facts: dict[str, Any] = json.loads(stdout)
    if "source" in facts:
        raise CaptureError(
            "compare --json now emits a `source` field of its own, which the "
            "capture would overwrite: rename the capture's field"
        )

    if compared["exit"] == 0 or as_json["exit"] == 0:
        raise CaptureError(
            "the prompt change did not make compare fail: exits "
            f"{compared['exit']} and {as_json['exit']}"
        )
    worse_cases = sorted(
        {d["case_id"] for d in facts["deltas"] if d["outcome"] == "regressed"}
    )
    if not worse_cases:
        raise CaptureError("compare failed, but no case is reported as worse")

    return {
        "run_ids": [before, after],
        "model": MODEL,
        "change": {
            "description": "One line of prompt.md, the signature line, changed.",
            "files": prompt_diff(root, after),
        },
        "band": band([space.run_document(before), space.run_document(after)]),
        "commands": space.commands,
        "compare_json": {
            "source": (
                f"The stdout of `{as_json['cmd']}` above, decoded with "
                "json.loads and otherwise unchanged: every key but this one "
                "is digline's."
            ),
            **facts,
        },
    }


RUNTIME_DEPENDENCIES_SOURCE = (
    "importlib.metadata.requires('digline') in the interpreter that ran every "
    "command above: the requirements the installed digline declares, keeping "
    "those whose marker holds in that interpreter. Extras are never active, so "
    "a requirement that exists only for an extra is not counted."
)


def runtime_dependencies(declared: Iterable[str] | None = None) -> dict[str, Any]:
    """The direct dependencies digline declares, as the installed metadata says.

    `declared` is for the tests; left out, it is read from the distribution. A
    marker is evaluated with `extra` set to the empty string, which is how an
    install that asked for no extra sees it.
    """
    lines = list(requires("digline") or ()) if declared is None else list(declared)
    names = sorted(
        {
            requirement.name
            for requirement in map(Requirement, lines)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""})
        }
    )
    return {
        "count": len(names),
        "names": names,
        "source": RUNTIME_DEPENDENCIES_SOURCE,
    }


REQUIRES_PYTHON_SOURCE = (
    "importlib.metadata.metadata('digline')['Requires-Python'] in the "
    "interpreter that ran every command above: the interpreter range the "
    "installed digline declares, as its own metadata carries it, not as the "
    "interpreter that happened to run this script satisfies it."
)


def requires_python(declared: str | None = None) -> dict[str, Any]:
    """The interpreter range digline declares, as the installed metadata says.

    `declared` is for the tests; left out, it is read from the distribution.
    A distribution that declares no range stops the capture rather than
    writing an empty promise onto the home.
    """
    specifier = metadata("digline")["Requires-Python"] if declared is None else declared
    if not specifier:
        raise CaptureError(
            "the installed digline declares no Requires-Python: the home has no "
            "interpreter range to show"
        )
    return {
        "specifier": specifier,
        "source": REQUIRES_PYTHON_SOURCE,
    }


CLI_COMMANDS_SOURCE = (
    "digline.cli.build_parser(), the parser `digline` itself runs: every "
    "subcommand in the order it is declared, with the one-line help `digline "
    "--help` prints beside it. Read from argparse's own list of subcommands, "
    "not from a list kept for the home."
)


def cli_commands(parser: argparse.ArgumentParser | None = None) -> dict[str, Any]:
    """Every public subcommand of `digline`, with its help line.

    `parser` is for the tests; left out, it is the CLI's own. `_choices_actions`
    is private to argparse, and it is the only place a subcommand's name and its
    help line are held together — so a Python that renames it stops the capture
    here instead of writing an empty list onto the home.
    """
    from digline.cli import build_parser

    parser = build_parser() if parser is None else parser
    found: list[argparse.Action] = [
        action
        for action in parser._actions  # pyright: ignore[reportPrivateUsage]
        if isinstance(action, argparse._SubParsersAction)  # pyright: ignore[reportPrivateUsage]
    ]
    if len(found) != 1:
        raise CaptureError(
            f"the digline parser has {len(found)} groups of subcommands, "
            "expected exactly one"
        )
    # `getattr` rather than the attribute: a Python that drops it must reach
    # the refusal below, not an AttributeError nobody reads as "the home broke".
    subcommands: object = getattr(found[0], "_choices_actions", None)
    if not isinstance(subcommands, list) or not subcommands:
        raise CaptureError(
            "argparse no longer lists the subcommands in `_choices_actions`, or "
            "the list is empty: the home has no commands to show"
        )
    items: list[dict[str, str]] = []
    for action in cast(list[argparse.Action], subcommands):
        # A subcommand declared without `help=` is left out of `--help` by
        # argparse too: it is not public, so it is not on the home.
        if action.help is None or action.help == argparse.SUPPRESS:
            continue
        items.append({"name": action.dest, "help": action.help})
    if not items:
        raise CaptureError("every subcommand of digline is hidden or has no help")
    return {"items": items, "source": CLI_COMMANDS_SOURCE}


CHECKS_SOURCE = (
    "Every class in digline.core.__all__ that subclasses AssertionBase or "
    "RunAssertionBase, in the order of __all__, with the `KIND` the class "
    "declares and the anchor of its card in docs/metrics.md, derived from the "
    "card's heading the way the site's Markdown derives a heading id."
)
HEADING = re.compile(r"^#{1,6} +(.+?) *$", re.MULTILINE)


def exported_checks() -> list[type]:
    """Every check digline.core exports: the rule `tests/test_metrics.py` uses."""
    import digline.core as core

    bases = (core.AssertionBase, core.RunAssertionBase)
    return [
        obj
        for name in core.__all__
        if isinstance(obj := getattr(core, name), type)
        and issubclass(obj, bases)
        and obj not in bases
    ]


def heading_id(title: str) -> str:
    """The id Python-Markdown's `toc` gives a heading, with its default slugify.

    The site sets no `slugify` of its own. A code span is rendered before the
    id is taken, so its backticks are not part of the text.
    """
    text = unicodedata.normalize("NFKD", title.replace("`", ""))
    text = re.sub(r"[^\w\s-]", "", text.encode("ascii", "ignore").decode()).strip()
    return re.sub(r"[-\s]+", "-", text.lower())


def checks(
    metrics: str | None = None, classes: Iterable[type] | None = None
) -> dict[str, Any]:
    """Every exported check, its kind and the anchor of its card.

    Both arguments are for the tests. A check with no `KIND`, a `KIND` outside
    `CheckKind`, or no card in `docs/metrics.md` stops the capture: a list with
    a hole in it is the hand-kept list this replaces.
    """
    from digline.core import CheckKind

    text = METRICS.read_text(encoding="utf-8") if metrics is None else metrics
    # `CheckKind` is a PEP 695 alias: `__value__` is the `Literal` behind it,
    # and `get_args` spells out its five strings.
    allowed: tuple[str, ...] = get_args(CheckKind.__value__)
    # A `#` line inside a fence is a comment in the code shown, not a heading.
    prose = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    titles: list[str] = HEADING.findall(prose)
    ids = [heading_id(title) for title in titles]
    items: list[dict[str, str]] = []
    for cls in exported_checks() if classes is None else classes:
        name = cls.__name__
        kind: object = getattr(cls, "KIND", None)
        if kind is None:
            raise CaptureError(f"{name} is exported and declares no KIND")
        if kind not in allowed:
            raise CaptureError(
                f"{name}.KIND is {kind!r}, not one of {', '.join(allowed)}"
            )
        if f"### `{name}`" not in text.splitlines():
            raise CaptureError(f"{name} is exported and has no card in docs/metrics.md")
        anchor = heading_id(f"`{name}`")
        if ids.count(anchor) != 1:
            # `toc` would suffix the later heading, and the link would land on
            # whichever came first.
            raise CaptureError(f"the id {anchor!r} names more than one heading")
        items.append({"name": name, "kind": str(kind), "anchor": anchor})
    if not items:
        raise CaptureError("digline.core exports no check: the derivation broke")
    return {"items": items, "source": CHECKS_SOURCE}


def package_version(pyproject: Path = PYPROJECT) -> str:
    with pyproject.open("rb") as handle:
        version: str = tomllib.load(handle)["project"]["version"]
    return version


def capture(scratch: Path, guide: Path = GUIDE) -> dict[str, Any]:
    text = guide.read_text(encoding="utf-8")
    scenarios = {
        "quickstart": quickstart(scratch / "quickstart", text),
        "steady": steady(scratch / "steady", text),
        "prompt_regression": prompt_regression(scratch / "prompt_regression", text),
    }
    # The version that actually ran, as the run file records it — not the one
    # this script believes it imported.
    recorded = {
        json.loads(path.read_text(encoding="utf-8"))["digline_version"]
        for path in scratch.glob(f"*/.digline/{TENANT}/runs/{SUITE}/*.json")
    }
    if len(recorded) != 1:
        raise CaptureError(f"the runs record more than one version: {recorded}")
    return {
        "digline_version": recorded.pop(),
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {
            "network": "none: no provider is configured, proxies point at "
            + CLOSED_PROXY,
            "stripped": [*STRIPPED, *(f"{p}*" for p in STRIPPED_PREFIXES)],
        },
        "runtime_dependencies": runtime_dependencies(),
        "requires_python": requires_python(),
        "cli_commands": cli_commands(),
        "checks": checks(),
        "scenarios": scenarios,
    }


# ── the check ─────────────────────────────────────────────────────────────────


#: A core release heading, exactly as digline.dev's `tools/hooks/home.py` reads
#: one: `## 0.13.3 — 2026-09-16`. Not `## Unreleased`, not `## 0.14.0 —
#: unreleased`, not a plugin's `## digline-openai 0.5.0 — …`.
_RELEASED = re.compile(r"^## (\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$")


def released_version(changelog: Path = CHANGELOG) -> str | None:
    """The newest core release the changelog dates, or `None`."""
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if match := _RELEASED.match(line):
            return match.group(1)
    return None


def check(path: Path = OUTPUT, changelog: Path = CHANGELOG) -> list[str]:
    """Everything wrong with the committed capture. Empty means current.

    **Held to the newest dated release in the changelog, not to
    `pyproject.toml`**, and the difference is deliberate — do not "fix" it back.
    The home of digline.dev is a public claim about what is *released*, so it
    must never show the output of a version that is not tagged. The site's own
    hook holds the file to the newest `## X.Y.Z — YYYY-MM-DD` heading; this
    check used to hold it to `pyproject.toml`, so the two tools had disagreed
    about what "the current version" means all along. It only became visible
    when a version was set on a branch ahead of its tag — schema 12's open
    train, `## 0.14.0 — unreleased` — and each gate then demanded a different
    capture. The tag PR dates the heading, this check then refuses the old
    capture, and the regeneration follows: the right order, and a required one
    rather than a remembered one (`RELEASING.md`, the home capture).
    """
    if not path.is_file():
        return [f"{path} does not exist: run tools/home_capture.py"]
    document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    captured = document.get("digline_version")
    released = released_version(changelog)
    if released is None:
        return [
            f"{changelog.name} has no heading of the form `## X.Y.Z — YYYY-MM-DD`, "
            f"so there is no released version to hold {path.name} to"
        ]
    if captured != released:
        return [
            f"{path.name} was captured with digline {captured} and the newest "
            f"dated release in {changelog.name} is {released}: run `uv run "
            "python tools/home_capture.py` and commit the result"
        ]
    return steady_check(document, path)


def steady_check(document: dict[str, Any], path: Path) -> list[str]:
    """The steady scenario in a committed capture, held to what it promises.

    digline.dev reads its sentence on /start/, and a sentence that lost the
    noise, the suspended case or the changed file would be a claim the page
    makes and the tool did not: the same four conditions the capture refuses to
    write are refused here when the file is read back.
    """
    scenarios = cast(dict[str, Any], document.get("scenarios") or {})
    scenario = scenarios.get("steady")
    if not isinstance(scenario, dict):
        return [
            f"{path.name} has no `steady` scenario: run `uv run python "
            "tools/home_capture.py` and commit the result"
        ]
    scenario = cast(dict[str, Any], scenario)
    problems = [
        f"{path.name}: steady: `{command.get('cmd')}` exited "
        f"{command.get('exit')!r}, not 0, and the scenario is the green one"
        for command in cast(list[dict[str, Any]], scenario.get("commands") or [])
        if command.get("exit") != 0
    ]
    facts = scenario.get("compare_json")
    if not isinstance(facts, dict):
        return [*problems, f"{path.name}: steady has no `compare_json`"]
    return problems + [
        f"{path.name}: steady shows no {name}: {wrong}"
        for name, wrong in steady_problems(cast(dict[str, Any], facts))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    if args.check:
        problems = check(args.out)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0

    with tempfile.TemporaryDirectory(prefix="digline-home-") as scratch:
        try:
            result = capture(Path(scratch))
        except CaptureError as exc:
            print(f"capture failed: {exc}", file=sys.stderr)
            return 1
    if result["digline_version"] != package_version():
        print(
            f"the runs recorded digline {result['digline_version']} and the "
            f"package is {package_version()}: run `uv sync --all-packages` first",
            file=sys.stderr,
        )
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
