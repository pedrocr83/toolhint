"""Snapshot tools/list of the user's local stdio MCP servers for the catalog."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from .catalog import enabled_plugin_paths, load_json

log = logging.getLogger("toolhint.toolcache")
TIMEOUT_S = 30
SELF_PLUGIN = "toolhint"


def server_configs(data: dict) -> dict:
    """Server mapping from either the wrapped ({"mcpServers": ...}) or the flat .mcp.json layout."""
    wrapped = data.get("mcpServers")
    return wrapped if isinstance(wrapped, dict) else data


def configured_servers(home: Path) -> list[dict]:
    """Stdio servers from ~/.claude.json and enabled plugins' .mcp.json. A project's .mcp.json is left out:
    Claude Code runs those only after the user approves them, and a refresh must not bypass that."""
    sources: list[tuple[dict, str | None, Path | None]] = [
        (load_json(home / ".claude.json").get("mcpServers") or {}, None, None)]
    for plugin, root in enabled_plugin_paths(home).items():
        if plugin != SELF_PLUGIN:
            sources.append((server_configs(load_json(root / ".mcp.json")), plugin, root))
    entries = [stdio_entry(name, cfg, plugin, root) for configs, plugin, root in sources for name, cfg in configs.items()]
    return [entry for entry in entries if entry]


def stdio_entry(name: str, cfg: object, plugin: str | None, root: Path | None) -> dict | None:
    """Launch spec for a stdio server; None for http/sse servers (they need auth headers)."""
    if not isinstance(cfg, dict) or not cfg.get("command"):
        return None

    def expand(value: object) -> str:
        return os.path.expandvars(str(value).replace("${CLAUDE_PLUGIN_ROOT}", str(root or "")))

    env = {key: expand(value) for key, value in (cfg.get("env") or {}).items()}
    return {"name": name, "plugin": plugin, "command": expand(cfg["command"]),
            "args": [expand(arg) for arg in cfg.get("args") or []], "env": env or None}


async def list_tools(server: dict) -> list[dict]:
    """All tools a stdio server advertises, following pagination."""
    params = StdioServerParameters(command=server["command"], args=server["args"], env=server["env"])
    tools: list[dict] = []
    cursor: str | None = None
    async with Client(params) as client:
        while True:
            page = await client.list_tools(cursor=cursor)
            tools += [{"name": tool.name, "description": tool.description or ""} for tool in page.tools]
            cursor = page.next_cursor
            if not cursor:
                return tools


async def refresh(servers: list[dict], out: Path) -> dict:
    """Snapshot every reachable server into `out`; unreachable servers are skipped."""
    snapshot: dict = {"refreshed_at": time.time(), "servers": []}
    for server in servers:
        try:
            with anyio.fail_after(TIMEOUT_S):
                tools = await list_tools(server)
        except Exception as exc:  # a dead server must not abort the snapshot
            log.warning("skipping MCP server %s: %s", server["name"], exc)
            continue
        snapshot["servers"].append({"name": server["name"], "plugin": server["plugin"], "instructions": "", "tools": tools})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    return snapshot
