"""Local JSONL log of routing decisions: debugging aid and future fine-tuning data."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .items import Ranking, RouteContext

DEFAULT_LOG = Path.home() / ".local" / "state" / "laya-router" / "decisions.jsonl"
MAX_BYTES = 10 * 1024 * 1024
PROMPT_CHARS = 500


class DecisionLog:
    """Append one JSON line per routed prompt; rotate once past max_bytes. path=None disables."""

    def __init__(self, path: Path | None = DEFAULT_LOG, max_bytes: int = MAX_BYTES) -> None:
        self.path = path
        self.max_bytes = max_bytes

    def write(self, ctx: RouteContext, ranking: Ranking, catalog_size: int) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > self.max_bytes:
            self.path.replace(self.path.with_name(self.path.name + ".1"))
        record = {
            "ts": time.time(), "harness": ctx.harness, "session": ctx.session_id,
            "prompt": ctx.prompt[:PROMPT_CHARS], "skills": [asdict(c) for c in ranking.skills],
            "connectors": [asdict(c) for c in ranking.connectors], "tools": [asdict(c) for c in ranking.tools],
            "latency_ms": ranking.latency_ms, "model": ranking.model, "catalog_size": catalog_size,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
