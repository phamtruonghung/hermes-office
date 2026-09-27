#!/usr/bin/env python3
"""Tiny real MCP stdio client used by make-report.sh and verify.sh.

This is NOT a shortcut around the MCP protocol: it performs a genuine
stdio JSON-RPC handshake (initialize -> list_tools / call_tool) against the
hermes-office-mcp server, using the official `mcp` Python SDK's
ClientSession, exactly like Hermes/Claude Code would.

Usage:
  mcp_client.py list-tools
  mcp_client.py call <tool_name> '<json args>'
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_COMMAND = "/opt/office/venvs/hermes-office-mcp/bin/python"
SERVER_ARGS = ["-m", "hermes_office_mcp.server"]


async def _list_tools() -> dict:
    params = StdioServerParameters(command=SERVER_COMMAND, args=SERVER_ARGS)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return {
                "tools": [
                    {"name": t.name, "description": t.description} for t in tools.tools
                ]
            }


async def _call_tool(tool: str, args: dict) -> dict:
    params = StdioServerParameters(command=SERVER_COMMAND, args=SERVER_ARGS)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(tool, args)
            text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
            return {"isError": res.isError, "result": text}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: mcp_client.py list-tools | call <tool> <json-args>", file=sys.stderr)
        sys.exit(2)

    mode = sys.argv[1]
    if mode == "list-tools":
        out = asyncio.run(_list_tools())
        print(json.dumps(out, indent=2))
        return

    if mode == "call":
        if len(sys.argv) < 3:
            print("usage: mcp_client.py call <tool> '<json-args>'", file=sys.stderr)
            sys.exit(2)
        tool = sys.argv[2]
        args_json = sys.argv[3] if len(sys.argv) > 3 else "{}"
        args = json.loads(args_json)
        out = asyncio.run(_call_tool(tool, args))
        print(out["result"])
        sys.exit(1 if out["isError"] else 0)

    print(f"unknown mode: {mode}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
