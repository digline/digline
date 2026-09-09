"""`python -m digline_mcp`, the same entry point as the `digline-mcp` script.

Both exist because a client's MCP config may name either: a console script is
tidier, and `python -m` is what somebody reaches for when the script is not on
the PATH of whatever launched the process.
"""

from digline_mcp.server import main

if __name__ == "__main__":
    raise SystemExit(main())
