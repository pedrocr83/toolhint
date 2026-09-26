"""Discover routable skills, connectors and tools for the calling harness.

Every source is best-effort: a missing or malformed file is skipped with a log
line and never breaks routing.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import yaml

from .bm25 import fold
from .items import Item, Kind, RouteContext

log = logging.getLogger("toolhint.catalog")
LABEL_CHARS = 80
TEXT_CHARS = 1500
COWORK_ROOT = Path(".config") / "Claude" / "local-agent-mode-sessions"
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


def one_line(text: str, limit: int = LABEL_CHARS) -> str:
    """First sentence of `text`, whitespace collapsed, cut to `limit` chars."""
    flat = " ".join(text.split())
    sentence = re.split(r"(?<=[.!?])\s", flat, maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def make_item(kind: Kind, item_id: str, description: str, source: str, connector: str | None = None) -> Item:
    flat = " ".join(description.split())
    return Item(kind, item_id, one_line(flat), flat[:TEXT_CHARS], connector, source)


def load_json(path: Path | None) -> dict:
    """Parsed JSON object at `path`, or {} when missing, unreadable or not an object."""
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_frontmatter(path: Path) -> dict:
    """YAML frontmatter of a markdown file, or {} when absent or unparseable."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):  # bad dates and tags raise ValueError
        log.warning("unparseable frontmatter in %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def markdown_item(path: Path, name: str | None, prefix: str, source: str) -> Item | None:
    """Skill/command item from frontmatter; None when not model-invocable or undescribed."""
    meta = read_frontmatter(path)
    name = meta.get("name", name)
    description = meta.get("description")
    if not isinstance(name, str) or not isinstance(description, str) or not description.strip():
        return None
    if meta.get("disable-model-invocation") in (True, "true"):
        return None
    return make_item("skill", f"{prefix}:{name}" if prefix else name, description, source)


def scan_skills(root: Path, prefix: str = "", source: str = "") -> list[Item]:
    """Items for every root/<dir>/SKILL.md (the frontmatter name is required)."""
    if not root.is_dir():
        return []
    found = (markdown_item(p, None, prefix, source or str(root)) for p in sorted(root.glob("*/SKILL.md")))
    return [item for item in found if item]


def scan_commands(root: Path, prefix: str = "", source: str = "") -> list[Item]:
    """Items for every root/<name>.md slash command that has a description."""
    if not root.is_dir():
        return []
    found = (markdown_item(p, p.stem, prefix, source or str(root)) for p in sorted(root.glob("*.md")))
    return [item for item in found if item]


def _first(entries: object) -> dict:
    return entries[0] if isinstance(entries, list) and entries and isinstance(entries[0], dict) else {}


def enabled_plugin_paths(home: Path) -> dict[str, Path]:
    """plugin name -> install path, for plugins enabled in ~/.claude/settings.json."""
    enabled = load_json(home / ".claude" / "settings.json").get("enabledPlugins") or {}
    installed = load_json(home / ".claude" / "plugins" / "installed_plugins.json").get("plugins") or {}
    paths: dict[str, Path] = {}
    for key, is_on in enabled.items():
        entry = _first(installed.get(key))
        if is_on is True and entry.get("installPath"):
            paths[key.split("@", 1)[0]] = Path(entry["installPath"])
    return paths


def claude_code_skills(home: Path, cwd: Path | None) -> list[Item]:
    """User, project, synced and enabled-plugin skills plus slash commands, as Claude Code lists them."""
    items: list[Item] = []
    for base in [home] + ([cwd] if cwd else []):
        items += scan_skills(base / ".claude" / "skills") + scan_skills(base / ".agents" / "skills")
        items += scan_commands(base / ".claude" / "commands")
    for synced in sorted((home / ".claude" / "skills" / "synced").glob("*/")):
        items += scan_skills(synced, prefix="anthropic-skills", source="synced")
    for plugin, root in enabled_plugin_paths(home).items():
        items += scan_skills(root / "skills", plugin, f"plugin:{plugin}")
        items += scan_commands(root / "commands", plugin, f"plugin:{plugin}")
    return items


def cowork_skills(home: Path, session: dict) -> list[Item]:
    """Anthropic-managed skills from the Cowork manifest plus the session's user plugins."""
    if str(session.get("skillsEnabled", True)).lower() == "false":
        return []
    items: list[Item] = []
    for manifest in sorted((home / COWORK_ROOT / "skills-plugin").glob("*/*/manifest.json")):
        for skill in load_json(manifest).get("skills") or []:
            if isinstance(skill, dict) and skill.get("enabled", True) and skill.get("name") and skill.get("description"):
                items.append(make_item("skill", f"anthropic-skills:{skill['name']}", str(skill["description"]), "cowork:manifest"))
    for raw in session.get("pluginInstallPaths") or []:
        root = Path(raw)
        name = load_json(root / ".claude-plugin" / "plugin.json").get("name") or root.name
        items += scan_skills(root / "skills", name, f"cowork-plugin:{name}")
    return items


TOOL_CACHE = Path(".cache") / "toolhint" / "mcp-tools.json"
TTL_S = 30.0
_CACHE: dict[tuple[str, ...], tuple[float, list[Item]]] = {}


TOOL_VERBS = frozenset({"get", "list", "create", "update", "delete", "set", "add", "remove", "fetch", "read",
                        "write", "tool", "by", "for", "the", "to", "of", "and", "or", "with",
                        "from", "in", "on", "all", "new", "me", "id"})


def tool_keywords(name: str, tools: list[dict], limit: int = 6) -> list[str]:
    """Most frequent words in a connector's tool names, minus CRUD verbs and the connector's own name."""
    own = set(re.findall(r"[a-z0-9]+", fold(name)))
    counts = Counter(word for tool in tools for word in dict.fromkeys(re.findall(r"[a-z0-9]+", fold(str(tool["name"]))))
                     if word not in TOOL_VERBS and word not in own)
    return [word for word, _ in counts.most_common(limit)]


def connector_items(name: str, instructions: str, tools: list, tool_prefix: str, source: str) -> list[Item]:
    """One connector item plus one tool item per tool; tool ids are tool_prefix + tool name. Without server
    instructions the label names what the tools do, since a raw tool list tells Laya little."""
    tool_list = [tool for tool in tools if isinstance(tool, dict) and tool.get("name")]
    names = ", ".join(tool["name"] for tool in tool_list)
    keywords = tool_keywords(name, tool_list)
    summary = instructions.strip() or (f"{name}: {', '.join(keywords)}." if keywords else "")
    items = [make_item("connector", name, f"{summary} {name} tools: {names}".strip(), source)]
    for tool in tool_list:
        description = str(tool.get("description") or tool["name"])
        items.append(make_item("tool", tool_prefix + tool["name"], f"{name} {tool['name']}: {description}", source, name))
    return items


def claude_ai_items(session: dict, cc_names: bool) -> list[Item]:
    """claude.ai connectors from a Cowork session JSON; Claude Code tool ids when cc_names,
    otherwise Cowork's own mcp__<connector uuid>__<tool> ids."""
    items: list[Item] = []
    for server in session.get("remoteMcpServersConfig") or []:
        if not isinstance(server, dict) or not server.get("name"):
            continue
        name, uuid = str(server["name"]), server.get("uuid")
        if cc_names:
            prefix = f"mcp__claude_ai_{name.replace(' ', '_')}__"
        else:
            prefix = f"mcp__{uuid}__" if uuid else ""
        items += connector_items(name, str(server.get("instructions") or ""), server.get("tools") or [], prefix, "claude.ai")
    return items


def local_server_items(home: Path) -> list[Item]:
    """Local MCP servers snapshotted by `toolhint catalog --refresh`."""
    items: list[Item] = []
    for server in load_json(home / TOOL_CACHE).get("servers") or []:
        if not isinstance(server, dict) or not server.get("name"):
            continue
        name, plugin = str(server["name"]), server.get("plugin")
        prefix = f"mcp__plugin_{plugin}_{name}__" if plugin else f"mcp__{name}__"
        items += connector_items(name, str(server.get("instructions") or ""), server.get("tools") or [], prefix, f"mcp:{name}")
    return items


def connector_of(tool_id: str) -> str | None:
    """Connector name, as this catalog names it, for an mcp__<server>__<tool> id."""
    parts = tool_id.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return None
    server = parts[1]
    if server.startswith("claude_ai_"):
        return server.removeprefix("claude_ai_").replace("_", " ")
    if server.startswith("plugin_"):
        return server.removeprefix("plugin_").partition("_")[2] or None
    return server


def session_json_for(transcript_path: str) -> Path | None:
    """Cowork session JSON beside the local_<id>/ dir that holds this transcript."""
    for parent in Path(transcript_path).parents:
        if parent.name.startswith("local_"):
            return parent.with_name(parent.name + ".json")
    return None


def newest_session_json(home: Path) -> Path | None:
    """Most recently modified Cowork session JSON, if any."""
    try:
        sessions = list((home / COWORK_ROOT).glob("*/*/local_*.json"))
        return max(sessions, key=lambda path: path.stat().st_mtime) if sessions else None
    except OSError:
        return None


def discover(ctx: RouteContext, home: Path | None = None, now: float | None = None) -> list[Item]:
    """Routable items for ctx's harness; rescans at most every TTL_S seconds."""
    home = home or Path.home()
    now = time.monotonic() if now is None else now
    key = (str(home), ctx.harness, ctx.cwd, ctx.transcript_path if ctx.harness == "cowork" else "")
    hit = _CACHE.get(key)
    if hit and now - hit[0] < TTL_S:
        return hit[1]
    items = dedupe(_collect(ctx, home))
    _CACHE[key] = (now, items)
    return items


def clear_cache() -> None:
    _CACHE.clear()


def _collect(ctx: RouteContext, home: Path) -> list[Item]:
    if ctx.harness == "cowork":
        session = load_json(session_json_for(ctx.transcript_path))
        return _safe(cowork_skills, home, session) + _safe(claude_ai_items, session, False)
    cwd = Path(ctx.cwd) if ctx.cwd else None
    session = load_json(newest_session_json(home))
    return (_safe(claude_code_skills, home, cwd) + _safe(local_server_items, home)
            + _safe(claude_ai_items, session, True))


def _safe(fn: Callable[..., list[Item]], *args: object) -> list[Item]:
    try:
        return fn(*args)
    except Exception:  # one broken source must never break routing
        log.exception("catalog source %s failed", fn.__name__)
        return []


def dedupe(items: list[Item]) -> list[Item]:
    seen: set[tuple[str, str]] = set()
    unique: list[Item] = []
    for item in items:
        if (item.kind, item.id) not in seen:
            seen.add((item.kind, item.id))
            unique.append(item)
    return unique


def harness_catalogs(home: Path | None = None) -> dict[str, list[Item]]:
    """Claude Code catalog plus, when Cowork exists, the newest Cowork session's catalog."""
    home = home or Path.home()
    catalogs = {"claude-code": discover(RouteContext(""), home=home)}
    newest = newest_session_json(home)
    if newest:
        transcript = newest.with_suffix("") / ".claude" / "projects" / "eval" / "eval.jsonl"
        catalogs["cowork"] = discover(RouteContext("", transcript_path=str(transcript)), home=home)
    return catalogs
