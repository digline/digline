"""`docs/record-node.md` says only what was run. (ADR 0062 §4, as amended
2026-11-06, and §5)

The page has two parts. The first quotes the lines of the recorder in the
process, which the CI job `recorder-node` runs: each of its JavaScript blocks,
in order, is one of `recorders/node/page.test.mjs`'s, between a `// page:`
line and an `// end` line. The second quotes the lines the CI job
`through-the-proxy` runs, so each of its lines of JavaScript is held to
`recorders/node/through-the-proxy.mjs`, and the variable the page sets is held
to the script that sets it. And what the page names of digline is held to
digline: each `digline` command and its flags to the parser, each
`X-Digline-*` header to what the proxy reads.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import cast

from digline.cli.main import build_parser

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "docs" / "record-node.md").read_text(encoding="utf-8")
SCRIPT = (ROOT / "recorders" / "node" / "through-the-proxy.mjs").read_text(
    encoding="utf-8"
)
PAGE_TEST = (ROOT / "recorders" / "node" / "page.test.mjs").read_text(encoding="utf-8")
#: Where the page's second part, the proxy's, begins.
PROXY_PART = "\n## Through the proxy\n"
JOB = (ROOT / "recorders" / "through-the-proxy.sh").read_text(encoding="utf-8")
PROXY = (ROOT / "src" / "digline" / "host" / "proxy.py").read_text(encoding="utf-8")


def blocks(language: str, part: str = PAGE) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", part, flags=re.S)


def _lines(block: str) -> list[str]:
    return [line.strip() for line in block.strip("\n").splitlines()]


def test_every_block_of_the_recorder_is_one_the_page_test_runs() -> None:
    """A line goes on the page only once it was run (ADR 0062 §5): each block
    of the first part, in order, is one of `page.test.mjs`'s, compared line by
    line, indentation aside, as `docs/record-java.md` is to `PageTest`."""
    first = PAGE.split(PROXY_PART, 1)[0]
    page = blocks("js", first)
    run = re.findall(r"// page:\n(.*?)\n[ ]*// end", PAGE_TEST, re.S)
    assert page, "the page quotes no JavaScript of the recorder"
    assert [_lines(block) for block in page] == [_lines(block) for block in run]


def test_every_line_of_javascript_on_the_page_is_a_line_the_job_runs() -> None:
    assert PROXY_PART in PAGE, "the page has no part for the proxy"
    second = PAGE.split(PROXY_PART, 1)[1]
    quoted = [
        line for block in blocks("js", second) for line in block.splitlines() if line
    ]
    assert quoted, "the page quotes no JavaScript: this would prove nothing"
    script = SCRIPT.splitlines()
    missing = [line for line in quoted if line not in script]
    assert not missing, f"not lines of recorders/node/through-the-proxy.mjs: {missing}"


def test_the_variable_the_page_sets_is_the_one_the_job_sets() -> None:
    [console] = [b for b in blocks("console") if "node " in b]
    assert "ANTHROPIC_BASE_URL=" in console
    assert 'env ANTHROPIC_BASE_URL="$DIGLINE_PROXY" node' in JOB
    # And the client the variable reaches is given no base URL of its own.
    anthropic = SCRIPT[SCRIPT.index("new Anthropic(") :]
    assert "baseURL" not in anthropic


def _record_parser() -> argparse.ArgumentParser:
    """`digline record`'s own parser, read off the command line's."""
    for action in build_parser()._actions:  # pyright: ignore[reportPrivateUsage]
        choices: object = getattr(action, "choices", None)
        if isinstance(choices, dict):
            # The subcommands' parsers, keyed by name: argparse types
            # `choices` loosely, and this is the action that holds parsers.
            return cast(dict[str, argparse.ArgumentParser], choices)["record"]
    raise AssertionError("the command line has no subcommands")


def test_every_digline_command_and_flag_on_the_page_exists() -> None:
    named = re.findall(r"digline (record [a-z]+(?: [^`\n]*)?)", PAGE)
    assert named, "the page names no command: this would prove nothing"
    record = _record_parser()
    options: set[str] = set()
    verbs: list[str] = []
    for action in record._actions:  # pyright: ignore[reportPrivateUsage]
        options.update(action.option_strings)
        if action.dest == "action":
            verbs = list(cast(list[str], action.choices))
    assert "proxy" in verbs, verbs
    for command in named:
        words = command.split()
        assert words[1] in verbs, command
        for flag in (word for word in words[2:] if word.startswith("--")):
            assert flag in options, f"{flag} in {command!r}"


def test_every_header_on_the_page_is_one_the_proxy_reads() -> None:
    headers = set(re.findall(r"X-Digline-([A-Za-z]+)", PAGE))
    assert headers >= {"Suite", "App", "Episode"}
    for name in headers:
        assert f'_OURS + "{name.lower()}"' in PROXY, f"X-Digline-{name}"


def test_the_versions_the_page_says_are_the_ones_the_job_installs() -> None:
    """ "Measured with" names the versions `recorders/node/package.json` pins:
    a Dependabot bump that moves them makes this red until the page says the
    new ones."""
    import json

    pinned = json.loads(
        (ROOT / "recorders" / "node" / "package.json").read_text(encoding="utf-8")
    )["dependencies"]
    said = " ".join(PAGE.split())
    for package in ("openai", "@anthropic-ai/sdk", "@aws-sdk/client-bedrock-runtime"):
        assert f"{package} {pinned[package]}" in said, package
