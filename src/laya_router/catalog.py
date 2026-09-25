"""Discover routable skills, connectors and tools for the calling harness.

Every source is best-effort: a missing or malformed file is skipped with a log
line and never breaks routing.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import yaml

from .items import Item, Kind

log = logging.getLogger("laya_router.catalog")
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
    except yaml.YAMLError:
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
