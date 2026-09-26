"""Benchmark Claude Code with and without toolhint on coding and research tasks (design in plan.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[3] / "bench" / "tasks"


@dataclass(frozen=True)
class Task:
    name: str
    root: Path
    prompt: str
    budget_usd: float
    timeout_s: int
    allowed_tools: tuple[str, ...]
    grading: dict

    @classmethod
    def load(cls, root: Path) -> Task:
        spec = json.loads((root / "task.json").read_text(encoding="utf-8"))
        prompt = (root / spec["prompt"]).read_text(encoding="utf-8").strip()
        return cls(root.name, root, prompt, float(spec["budget_usd"]), int(spec["timeout_s"]),
                   tuple(spec.get("allowed_tools", [])), spec["grading"])


def load_tasks(names: str, tasks_dir: Path = TASKS_DIR) -> list[Task]:
    """Comma-separated task names, or "all"."""
    available = sorted(path.parent.name for path in tasks_dir.glob("*/task.json"))
    chosen = available if names == "all" else [name.strip() for name in names.split(",") if name.strip()]
    unknown = sorted(set(chosen) - set(available))
    if unknown:
        raise SystemExit(f"unknown tasks {unknown}; available: {available}")
    return [Task.load(tasks_dir / name) for name in chosen]
