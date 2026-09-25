import json

from laya_router.catalog import (
    claude_ai_items, connector_items, connector_of, discover, harness_catalogs, local_server_items, session_json_for,
)
from laya_router.items import RouteContext

CAL = {"remoteMcpServersConfig": [{"name": "Google Calendar", "instructions": "", "tools": [
    {"name": "create_event", "description": "Creates an event on the given calendar."}]}]}


def test_claude_ai_items_use_claude_code_tool_ids():
    connector, tool = claude_ai_items(CAL, cc_names=True)
    assert (connector.kind, connector.id) == ("connector", "Google Calendar")
    assert (tool.kind, tool.id, tool.connector) == ("tool", "mcp__claude_ai_Google_Calendar__create_event", "Google Calendar")
    assert claude_ai_items(CAL, cc_names=False)[1].id == "create_event"


def test_local_server_items_from_tool_cache(tmp_path):
    cache = tmp_path / ".cache" / "laya-router" / "mcp-tools.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"servers": [
        {"name": "context7", "plugin": None, "instructions": "", "tools": [{"name": "query-docs", "description": "Query docs."}]},
        {"name": "playwright", "plugin": "playwright", "instructions": "", "tools": [{"name": "browser_click", "description": "Click."}]}]}))
    ids = {i.id for i in local_server_items(tmp_path) if i.kind == "tool"}
    assert ids == {"mcp__context7__query-docs", "mcp__plugin_playwright_playwright__browser_click"}


def test_local_server_items_missing_cache_is_empty(tmp_path):
    assert local_server_items(tmp_path) == []


def test_connector_of_inverts_tool_ids():
    assert connector_of("mcp__claude_ai_Google_Calendar__create_event") == "Google Calendar"
    assert connector_of("mcp__plugin_chrome-devtools-mcp_chrome-devtools__click") == "chrome-devtools"
    assert connector_of("mcp__context7__query-docs") == "context7"
    assert connector_of("Bash") is None


def test_session_json_for_cowork_transcript(tmp_path):
    transcript = tmp_path / "lams" / "acct" / "org" / "local_abc" / ".claude" / "projects" / "x" / "s.jsonl"
    assert session_json_for(str(transcript)) == tmp_path / "lams" / "acct" / "org" / "local_abc.json"
    assert session_json_for("/home/u/.claude/projects/x/s.jsonl") is None


def cowork_home(tmp_path):
    root = tmp_path / ".config" / "Claude" / "local-agent-mode-sessions" / "acct" / "org"
    (root / "local_1" / ".claude" / "projects" / "p").mkdir(parents=True)
    (root / "local_1.json").write_text(json.dumps({"skillsEnabled": False, "remoteMcpServersConfig": [
        {"name": "Gmail", "tools": [{"name": "search_threads", "description": "Search threads."}]}]}))
    return str(root / "local_1" / ".claude" / "projects" / "p" / "s.jsonl")


def test_discover_routes_by_harness(tmp_path, write_skill):
    write_skill(tmp_path / ".claude" / "skills", "mine")
    transcript = cowork_home(tmp_path)
    cc_ids = {i.id for i in discover(RouteContext("hi"), home=tmp_path, now=0.0)}
    assert {"mine", "Gmail", "mcp__claude_ai_Gmail__search_threads"} <= cc_ids
    cowork_ids = {i.id for i in discover(RouteContext("hi", transcript_path=transcript), home=tmp_path, now=0.0)}
    assert cowork_ids == {"Gmail", "search_threads"}


def test_discover_rescans_only_after_ttl(tmp_path, write_skill):
    write_skill(tmp_path / ".claude" / "skills", "mine")
    discover(RouteContext("hi"), home=tmp_path, now=0.0)
    write_skill(tmp_path / ".claude" / "skills", "late")
    assert "late" not in {i.id for i in discover(RouteContext("hi"), home=tmp_path, now=10.0)}
    assert "late" in {i.id for i in discover(RouteContext("hi"), home=tmp_path, now=31.0)}


def test_harness_catalogs_include_cowork_when_present(tmp_path, write_skill):
    write_skill(tmp_path / ".claude" / "skills", "mine")
    cowork_home(tmp_path)
    catalogs = harness_catalogs(tmp_path)
    assert set(catalogs) == {"claude-code", "cowork"}
    assert {i.id for i in catalogs["cowork"]} == {"Gmail", "search_threads"}


def test_claude_ai_items_use_cowork_uuid_tool_ids():
    session = {"remoteMcpServersConfig": [{"name": "Gmail", "uuid": "7729dcbf", "tools": [
        {"name": "search_threads", "description": "Search threads."}]}]}
    connector, tool = claude_ai_items(session, cc_names=False)
    assert (connector.id, tool.id, tool.connector) == ("Gmail", "mcp__7729dcbf__search_threads", "Gmail")


def test_connector_label_names_what_its_tools_do():
    tools = [{"name": "search_threads"}, {"name": "get_thread"}, {"name": "create_draft"}, {"name": "send_message"}]
    connector = connector_items("Gmail", "", tools, "mcp__x__", "claude.ai")[0]
    assert connector.label == "Gmail: search, threads, thread, draft, send, message."
    assert "search_threads" in connector.text


def test_connector_label_prefers_server_instructions():
    connector = connector_items("Docs", "Search the product documentation.", [{"name": "query"}], "mcp__d__", "mcp:d")[0]
    assert connector.label == "Search the product documentation."
