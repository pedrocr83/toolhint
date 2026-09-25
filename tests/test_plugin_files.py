import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_hook_targets_the_bundled_router_server():
    hook = load("plugin/hooks/hooks.json")["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    server_name = next(iter(load("plugin/.mcp.json")["mcpServers"]))
    plugin = load("plugin/.claude-plugin/plugin.json")["name"]
    assert hook["type"] == "mcp_tool" and hook["server"] == f"plugin:{plugin}:{server_name}"
    assert hook["tool"] == "route" and hook["input"]["prompt"] == "${prompt}" and hook["timeout"] == 5


def test_hook_asks_for_hook_json_output():
    hook = load("plugin/hooks/hooks.json")["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert hook["input"]["format"] == "hook"


def test_plugin_has_no_top_level_bin():
    assert not (ROOT / "plugin" / "bin").exists()


def test_marketplace_points_at_plugin():
    [entry] = load(".claude-plugin/marketplace.json")["plugins"]
    assert (entry["name"], entry["source"]) == ("laya-router", "./plugin")
