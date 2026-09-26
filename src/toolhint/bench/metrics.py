"""One run's metrics from its stream-json events and the router's decision records."""
from __future__ import annotations

from collections import Counter

from ..catalog import connector_of

ROUTER = "plugin:toolhint:router"
TOKENS = (("input", "inputTokens"), ("output", "outputTokens"), ("cache_read", "cacheReadInputTokens"),
          ("cache_creation", "cacheCreationInputTokens"))
KIND = {"skills": "skill", "connectors": "connector", "tools": "tool"}


def summarize(arm: str, events: list[dict], decisions: list[dict]) -> dict:
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    session = init.get("session_id") or result.get("session_id", "")
    main, sub, skills = tool_uses(events)
    routed = next((d for d in decisions if d.get("session") == session), {})
    hinted = [{"id": c["id"], "kind": KIND[plural], "p": c["p"]} for plural in KIND for c in routed.get(plural, [])]
    models = (result.get("modelUsage") or {}).values()
    problem = arm_problem(arm, init, bool(routed)) or ("" if result else "no result event")
    return {
        "session_id": session, "valid": not problem, "invalid_reason": problem,
        "result_subtype": result.get("subtype"), "is_error": result.get("is_error"),
        "terminal_reason": result.get("terminal_reason"), "cost_usd": result.get("total_cost_usd"),
        "num_turns": result.get("num_turns"), "duration_ms": result.get("duration_ms"),
        "tokens": {name: sum(m.get(key, 0) for m in models) for name, key in TOKENS},
        "tools": dict(main), "subagent_tools": dict(sub), "skills": skills,
        "subagents": (result.get("subagent_stats") or {}).get("spawned", 0),
        "denials": [d.get("tool_name") for d in result.get("permission_denials") or []],
        "hints": hinted, "hint_uptake": uptake(hinted, main + sub, skills),
        "router_device": routed.get("device", ""), "router_ms": routed.get("latency_ms"),
        # the hook passes the session id; a record without one is the model calling `route` itself
        "model_route_calls": sum(1 for d in decisions if not d.get("session")),
    }


def arm_problem(arm: str, init: dict, routed: bool) -> str:
    """Empty when the session really ran as its arm says; otherwise what went wrong."""
    if not init:
        return "no init event"
    loaded = any(plugin.get("name") == "toolhint" for plugin in init.get("plugins", []))
    if arm == "off":
        return "toolhint loaded in the off arm" if loaded else ""
    connected = any(s.get("name") == ROUTER and s.get("status") == "connected" for s in init.get("mcp_servers", []))
    if not (loaded and connected):
        return "toolhint router not connected"
    return "" if routed else "the prompt was not routed (router still loading?)"


def tool_uses(events: list[dict]) -> tuple[Counter, Counter, list[str]]:
    """Tool calls by the main agent and by subagents, once per tool_use id, plus every skill invoked."""
    seen: set[str] = set()
    main: Counter = Counter()
    sub: Counter = Counter()
    skills: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use" or block.get("id") in seen:
                continue
            seen.add(block.get("id"))
            name = block.get("name", "")
            (sub if event.get("parent_tool_use_id") else main)[name] += 1
            if name == "Skill":
                skills.append(str((block.get("input") or {}).get("skill", "")))
    return main, sub, skills


def uptake(hinted: list[dict], tools: Counter, skills: list[str]) -> list[str]:
    """Hinted ids the run went on to use; a skill also matches by its name without the plugin prefix."""
    used = set(tools) | set(skills) | {connector_of(name) for name in tools} | {s.rsplit(":", 1)[-1] for s in skills}
    return [h["id"] for h in hinted if h["id"] in used or h["id"].rsplit(":", 1)[-1] in used]
