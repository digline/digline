"""The MCP client `docs/walkthroughs/from-the-ide-over-mcp.md` made its calls with, in
place of an IDE.

It starts the one server the project's `.mcp.json` declares, over stdio, from
the project's root, with the server's `env` over the client's default
environment, as `.github/mcp_tools.py` starts one; then it calls one tool and
returns its answer: the structured content, or the refusal's text.

    python tests/_story_ide_mcp_client.py ROOT TOOL '{"arg": "value"}'
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.stdio import get_default_environment
from mcp.types import TextContent

__all__ = ["Answer", "call"]

#: `(refused, payload)`: the structured content, or the refusal's text.
type Answer = tuple[bool, Any]


async def _call(root: Path, tool: str, arguments: dict[str, Any]) -> Answer:
    declared = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    (server,) = declared["mcpServers"].values()
    env = {**get_default_environment(), **server.get("env", {})}
    params = StdioServerParameters(
        command=server["command"], args=server["args"], cwd=root, env=env
    )
    with (root.parent / f"{root.name}.mcp-stderr.log").open("a") as log:
        async with (
            stdio_client(params, errlog=log) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    if result.is_error:
        return True, "".join(
            b.text for b in result.content if isinstance(b, TextContent)
        )
    return False, result.structured_content


def call(root: Path, tool: str, arguments: dict[str, Any] | None = None) -> Answer:
    """One tool of the server `root/.mcp.json` declares, called once."""
    return asyncio.run(_call(root, tool, arguments or {}))


if __name__ == "__main__":
    refused, said = call(
        Path(sys.argv[1]),
        sys.argv[2],
        json.loads(sys.argv[3]) if len(sys.argv) > 3 else None,
    )
    if refused:
        print("refused:", said)
        raise SystemExit(1)
    print(json.dumps(said, indent=2, ensure_ascii=False))
