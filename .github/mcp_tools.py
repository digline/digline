"""Call every tool a digline-mcp server registers, as a client would, and fail
on any that does not answer.

The examples' CI leg runs this in `examples/operator`, against the digline and
digline-mcp it resolves from the index. That leg ran `digline run` and
`digline compare` on the command line, and nothing ever started the server
`.mcp.json` names: a digline-mcp that could not answer `compare` beside the
digline it resolves left the leg green (#719). Run here, the server is the
published one, started as the example's `.mcp.json` starts it.

No model and no credential: a tool call is JSON-RPC, not inference, and the
example answers and judges with `fake.py`. `run` refuses until it is told how
many calls it will make, and is asked again with that number, as an agent
must.

    python .github/mcp_tools.py --root examples/operator
    python .github/mcp_tools.py --root DIR -- python -m digline_mcp --root DIR ...

Exit 0 when every tool `docs/mcp.md` lists is registered and answered and no
other tool is registered; 1 otherwise, each tool on a line of its own.
`tests/test_mcp_tools.py` holds it against this tree's server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

#: The suite every call names, which is the example's.
SUITE = "suite.py"

#: The page that says which tools the server offers. **The one place the set
#: is written down**: the client reads it from the page's table rather than
#: keeping a list of its own, so the two cannot drift apart.
PAGE = Path(__file__).resolve().parents[1] / "docs" / "mcp.md"

#: How long the whole session may take. A server that never answers is a red,
#: not a hung job.
TIMEOUT = 300.0


def declared_server(root: Path) -> list[str]:
    """The command `.mcp.json` in `root` starts its one server with."""
    declared = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    servers = list(declared["mcpServers"].values())
    if len(servers) != 1:
        raise SystemExit(f"{root}/.mcp.json names {len(servers)} servers, not one")
    return [servers[0]["command"], *servers[0]["args"]]


def declared_tools(page: Path = PAGE) -> list[str]:
    """The tools `docs/mcp.md` lists: the first column of the table under its
    `## The … tools` heading."""
    text = page.read_text(encoding="utf-8")
    heading = re.search(r"^## The \w+ tools$", text, re.M)
    if heading is None:
        raise SystemExit(f"{page} has no `## The … tools` section to read")
    section = text[heading.end() :].split("\n## ", 1)[0]
    named = re.findall(r"^\| `([a-z_]+)` \|", section, re.M)
    if not named:
        raise SystemExit(f"{page}'s tools section lists no tool")
    return named


def _text(result: CallToolResult) -> str:
    return "".join(b.text for b in result.content if isinstance(b, TextContent))


def _answered(result: CallToolResult) -> str | None:
    """`None` when the tool answered, or what is wrong with the answer."""
    if result.is_error:
        return f"refused: {_text(result)}"
    if not isinstance(result.structured_content, Mapping):
        return "answered with no structured content"
    return None


async def drive(
    server: Sequence[str], root: Path, log: Any, declared: Sequence[str]
) -> list[tuple[str, str | None]]:
    """Each declared tool, called once, with what was wrong, if anything; and
    a line for each tool registered and not declared, or declared and not
    registered."""
    params = StdioServerParameters(command=server[0], args=list(server[1:]), cwd=root)
    said: list[tuple[str, str | None]] = []
    async with (
        stdio_client(params, errlog=log) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        registered = sorted(tool.name for tool in (await session.list_tools()).tools)
        # The set is the declared one, not the one found: a tool the page does
        # not list fails until the page lists it, and a tool it lists that the
        # server lacks fails by its name.
        for name in sorted(set(registered) - set(declared)):
            said.append((name, "registered, and docs/mcp.md does not list it"))
        for name in sorted(set(declared) - set(registered)):
            said.append(
                (name, "listed in docs/mcp.md, and the server does not register it")
            )
        registered = sorted(set(registered) & set(declared))

        async def call(name: str, arguments: dict[str, Any]) -> CallToolResult:
            return await session.call_tool(name, arguments)

        # `run` first, so the store holds the two runs `diff` names.
        if "run" in registered:
            first = await call("run", {"suite": SUITE})
            planned = re.search(r"acknowledge_calls=(\d+)", _text(first))
            if first.is_error and planned:
                first = await call(
                    "run",
                    {"suite": SUITE, "acknowledge_calls": int(planned.group(1))},
                )
            said.append(("run", _answered(first)))
        keys: list[str] = []
        if "list_runs" in registered:
            listed = await call("list_runs", {"suite": SUITE})
            said.append(("list_runs", _answered(listed)))
            content = listed.structured_content or {}
            keys = [str(r["key"]) for r in content.get("rows", []) if "key" in r]
        arguments: dict[str, dict[str, Any]] = {
            "get_run": {"suite": SUITE},
            "get_baseline": {"suite": SUITE},
            "log": {"suite": SUITE},
            "compare": {"suite": SUITE},
            "explain": {"suite": SUITE},
            "diff": {"suite": SUITE, "run1": keys[0], "run2": keys[-1]}
            if len(keys) >= 2
            else {},
        }
        for name in registered:
            if name in ("run", "list_runs"):
                continue
            if name not in arguments:
                # Fails closed: a tool added to the server is red here until
                # this client knows how to call it.
                said.append((name, "registered, and this client does not call it"))
                continue
            if name == "diff" and len(keys) < 2:
                said.append((name, f"needs two runs, and list_runs gave {len(keys)}"))
                continue
            said.append((name, _answered(await call(name, arguments[name]))))
    return said


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--show-server",
        action="store_true",
        help="print the command .mcp.json starts its server with, and stop",
    )
    parser.add_argument(
        "--show-declared",
        action="store_true",
        help="print the tools docs/mcp.md lists, and stop",
    )
    parser.add_argument("server", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    declared = declared_tools()
    if args.show_declared:
        print(json.dumps(declared))
        return 0
    server = [a for a in args.server if a != "--"] or declared_server(args.root)
    if args.show_server:
        print(json.dumps(server))
        return 0
    with tempfile.TemporaryFile("w+", encoding="utf-8") as log:
        try:
            said = asyncio.run(
                asyncio.wait_for(drive(server, args.root, log, declared), TIMEOUT)
            )
        except Exception as exc:  # noqa: BLE001 - no session at all is the finding
            log.seek(0)
            sys.stderr.write(log.read())
            print(f"FAILED the session: {type(exc).__name__}: {exc}")
            return 1
        failed = [(name, why) for name, why in said if why is not None]
        for name, why in said:
            print(f"ok {name}" if why is None else f"FAILED {name}: {why}")
        if failed:
            log.seek(0)
            sys.stderr.write(log.read())
        return 1 if failed or not said else 0


if __name__ == "__main__":
    raise SystemExit(main())
