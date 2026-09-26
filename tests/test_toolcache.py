import json
import sys

import pytest

from toolhint.toolcache import configured_servers, refresh

FIXTURE_SERVER = '''
from mcp.server.mcpserver import MCPServer
server = MCPServer("fixture")

@server.tool(name="echo", description="Echo text back.")
def echo(text: str) -> str:
    return text

server.run()
'''


@pytest.mark.anyio
async def test_refresh_snapshots_stdio_server(tmp_path):
    script = tmp_path / "srv.py"
    script.write_text(FIXTURE_SERVER)
    servers = [{"name": "fixture", "plugin": None, "command": sys.executable, "args": [str(script)], "env": None}]
    snapshot = await refresh(servers, tmp_path / "cache.json")
    assert snapshot["servers"][0]["tools"] == [{"name": "echo", "description": "Echo text back."}]
    assert json.loads((tmp_path / "cache.json").read_text())["servers"][0]["name"] == "fixture"


@pytest.mark.anyio
async def test_refresh_skips_broken_server(tmp_path):
    servers = [{"name": "broken", "plugin": None, "command": "/nonexistent/bin", "args": [], "env": None}]
    assert (await refresh(servers, tmp_path / "cache.json"))["servers"] == []


def test_configured_servers_expands_plugin_root_and_skips_http_and_self(tmp_path):
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {
        "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "remote": {"type": "http", "url": "https://example.com/mcp"}}}))
    root, self_root = tmp_path / "cache" / "playwright" / "1", tmp_path / "cache" / "toolhint" / "1"
    root.mkdir(parents=True)
    self_root.mkdir(parents=True)
    (root / ".mcp.json").write_text(json.dumps({"playwright": {"command": "npx", "args": ["${CLAUDE_PLUGIN_ROOT}/x"]}}))
    (self_root / ".mcp.json").write_text(json.dumps({"mcpServers": {"router": {"command": "toolhint"}}}))
    (tmp_path / ".claude" / "plugins").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"playwright@official": True, "toolhint@toolhint": True}}))
    (tmp_path / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "playwright@official": [{"installPath": str(root)}], "toolhint@toolhint": [{"installPath": str(self_root)}]}}))
    servers = configured_servers(tmp_path)
    assert [(s["name"], s["plugin"]) for s in servers] == [("context7", None), ("playwright", "playwright")]
    assert servers[1]["args"] == [f"{root}/x"]
