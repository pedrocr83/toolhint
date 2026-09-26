"""Turn Claude Code / Cowork transcripts into routing eval rows (local, private data)."""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator, Mapping
from pathlib import Path

from .catalog import COWORK_ROOT, connector_of, load_json, session_json_for

TAG_BLOCK = re.compile(r"<([a-zA-Z_-]+)>.*?</\1>", re.DOTALL)
MAX_PROMPT = 2000
TAIL_BYTES = 4 * 1024 * 1024  # tool results grow transcripts fast; the earlier prompt is often ~1 MB back
INTERRUPTED = "[Request interrupted by user"


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                yield entry


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def prompt_text(entry: dict) -> str | None:
    """Text of a real user prompt; None for tool results, meta, sidechain, slash-command, compaction-summary
    and interrupt-marker entries."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain") or entry.get("isCompactSummary"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content):
            return None
        content = " ".join(block.get("text", "") for block in content
                           if isinstance(block, dict) and block.get("type") == "text")
    if not isinstance(content, str) or "<command-name>" in content or content.startswith(INTERRUPTED):
        return None
    return TAG_BLOCK.sub(" ", content).strip()[:MAX_PROMPT] or None


def previous_prompt(transcript_path: str, current: str, tail_bytes: int = TAIL_BYTES) -> str:
    """Latest real user prompt in the transcript's tail other than `current`; "" when none or unreadable."""
    try:
        with open(transcript_path, "rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - tail_bytes))
            lines = handle.read().decode("utf-8", "replace").splitlines()[1 if size > tail_bytes else 0:]
    except OSError:
        return ""
    now = TAG_BLOCK.sub(" ", current).strip()[:MAX_PROMPT]
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        text = prompt_text(entry) if isinstance(entry, dict) else None
        if text and text != now:
            return text
    return ""


def tool_uses(entry: dict) -> list[dict]:
    if entry.get("type") != "assistant" or entry.get("isSidechain"):
        return []
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]


def label_turn(uses: list[dict], names: Mapping[str, str] | None = None) -> dict:
    """First Skill invocation and first MCP tool call of a turn; `names` maps Cowork connector uuids."""
    gold: dict[str, str] = {}
    for use in uses:
        name, data = use.get("name", ""), use.get("input") or {}
        if name == "Skill" and "skill" not in gold and isinstance(data, dict) and data.get("skill"):
            gold["skill"] = str(data["skill"])
        elif name.startswith("mcp__") and "tool" not in gold:
            gold["tool"] = name
            connector = connector_of(name)
            if connector:
                gold["connector"] = (names or {}).get(connector, connector)
    return gold


def cowork_connector_names(transcript: Path) -> dict[str, str]:
    """Connector uuid -> display name from the Cowork session JSON beside this transcript."""
    session = load_json(session_json_for(str(transcript)))
    servers = session.get("remoteMcpServersConfig") or []
    return {str(s["uuid"]): str(s["name"]) for s in servers if isinstance(s, dict) and s.get("uuid") and s.get("name")}


def rows_from_transcript(path: Path, harness: str) -> Iterator[dict]:
    names = cowork_connector_names(path) if harness == "cowork" else None
    prompt, uses = None, []
    for entry in read_jsonl(path):
        text = prompt_text(entry)
        if text is None:
            uses += tool_uses(entry)
            continue
        if prompt:
            yield make_row(prompt, label_turn(uses, names), harness, path)
        prompt, uses = text, []
    if prompt:
        yield make_row(prompt, label_turn(uses, names), harness, path)


def make_row(prompt: str, gold: dict, harness: str, path: Path) -> dict:
    return {"prompt": prompt, "harness": harness, "gold": gold,
            "source": "transcript" if gold else "transcript-none", "file": path.name}


def transcript_files(home: Path) -> Iterator[tuple[Path, str]]:
    for path in sorted((home / ".claude" / "projects").glob("*/*.jsonl")):
        yield path, "claude-code"
    for path in sorted((home / COWORK_ROOT).glob("*/*/local_*/.claude/projects/*/*.jsonl")):
        yield path, "cowork"


def build(home: Path, out_dir: Path) -> dict[str, int]:
    labeled, negatives, seen = [], [], set()
    for path, harness in transcript_files(home):
        for row in rows_from_transcript(path, harness):
            if row["prompt"] in seen:
                continue
            seen.add(row["prompt"])
            (labeled if row["gold"] else negatives).append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "transcripts.jsonl", labeled)
    write_jsonl(out_dir / "negatives.jsonl", negatives)
    return {"labeled": len(labeled), "negatives": len(negatives)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="toolhint eval build")
    parser.add_argument("--out", default="eval/data")
    args = parser.parse_args(argv)
    print(json.dumps(build(Path.home(), Path(args.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
