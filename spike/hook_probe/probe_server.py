"""Throwaway: sentinel MCP server for checking mcp_tool UserPromptSubmit hooks."""
import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

LOG = Path(__file__).with_name("calls.jsonl")
server = MCPServer("probe")


@server.tool(name="route", description="Probe: records hook arguments and returns a sentinel.")
def route(prompt: str = "", cwd: str = "", transcript_path: str = "", session_id: str = "", format: str = "text") -> str:
    record = {"prompt": prompt, "cwd": cwd, "transcript_path": transcript_path, "session_id": session_id, "format": format}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    hint = "" if "EMPTY" in prompt else "LAYA_SENTINEL_42"
    if format != "hook" or not hint:
        return hint
    return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": hint}})


if __name__ == "__main__":
    server.run()
