"""Grade a finished workspace: hidden tests or a regex checklist, the agent's own tests, and an isolated judge."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import Task
from .formats import html_checklist, render_cells, xlsx_cells, xlsx_checklist
from .session import clean_env

FLAGS = re.IGNORECASE | re.MULTILINE
COUNT = re.compile(r"(\d+) (passed|failed|errors?)\b")
JUDGE_TEMPLATE = Path(__file__).with_name("judge_prompt.md")
JUDGE_CHARS = 40_000
# -c /dev/null: neither this repo's pytest settings nor the agent's may change how grading tests run
PYTEST = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", os.devnull)


def grade(task: Task, workspace: Path, run_dir: Path, judge_model: str | None, claude_bin: str = "claude") -> dict:
    spec = task.grading
    if spec["kind"] == "tests":
        hidden = hidden_tests(task, workspace)
        total = hidden["passed"] + hidden["failed"] + hidden["errors"]
        score = hidden["passed"] / total if total else 0.0
        detail = {"hidden": hidden, "agent_tests": agent_tests(workspace, run_dir / "agent-tests")}
        output = collect(workspace, spec["judge_files"])
    else:
        path = workspace / spec["output"]
        wanted = json.loads((task.root / spec["checklist"]).read_text(encoding="utf-8"))
        if spec["kind"] == "xlsx":
            cells = xlsx_cells(path)
            checks, output, present = xlsx_checklist(cells, wanted), render_cells(cells), bool(cells)
        else:
            output = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            checks = (html_checklist if spec["kind"] == "html" else checklist)(output, wanted)
            present = bool(output.strip())
        score = checks["passed"] / checks["total"] if present else 0.0
        detail = {"output_exists": path.is_file(), "words": len(output.split()), **checks}
    verdict = judge(task, output, judge_model, run_dir / "judge", claude_bin) if judge_model else None
    return {"score": round(score, 3), "detail": detail, "judge": verdict}


def checklist(text: str, checks: list[dict]) -> dict:
    """A check passes on a regex hit, on hits for all of several patterns, on enough distinct hits, or under a word limit."""
    results = {}
    for check in checks:
        if "max_words" in check:
            ok = len(text.split()) <= check["max_words"]
        elif "distinct" in check:
            # with capture groups, the first one that matched is the key: "[01]" and "01-pilot.md" cite one source
            hits = {next((g for g in m.groups() if g), m.group(0)).lower()
                    for m in re.finditer(check["distinct"], text, FLAGS)}
            ok = len(hits) >= check["min"]
        else:
            ok = all(re.search(pattern, text, FLAGS) for pattern in check.get("patterns") or [check["pattern"]])
        results[check["id"]] = ok
    return {"passed": sum(results.values()), "total": len(results), "checks": results}


def pytest_counts(output: str) -> dict:
    last = next((line for line in reversed(output.splitlines()) if COUNT.search(line)), "")
    counts = {"passed": 0, "failed": 0, "errors": 0}
    for number, word in COUNT.findall(last):
        counts["errors" if word.startswith("error") else word] += int(number)
    return counts


def run_pytest(args: list[str], cwd: Path, env: dict | None = None, timeout: int = 300) -> dict:
    env = {**(env or os.environ), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run([*PYTEST, "--rootdir", str(cwd), *args], cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 0, "errors": 1, "exit_code": None}
    return {**pytest_counts(proc.stdout), "exit_code": proc.returncode}


def hidden_tests(task: Task, workspace: Path) -> dict:
    hidden = task.root / task.grading["hidden"]
    return run_pytest([hidden.name], hidden.parent, {**os.environ, "BENCH_WORKSPACE": str(workspace.resolve())})


def agent_tests(workspace: Path, copy: Path) -> dict:
    """The agent's own tests, run on a copy so grading never changes the workspace. Exit code 5: none collected."""
    shutil.copytree(workspace, copy, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
                    dirs_exist_ok=True)
    return run_pytest([], copy)


def collect(workspace: Path, patterns: list[str]) -> str:
    files = sorted({p for pattern in patterns for p in workspace.glob(pattern) if p.is_file() and ".git" not in p.parts})
    return "\n\n".join(f"### {p.relative_to(workspace)}\n{p.read_text(encoding='utf-8', errors='replace')}" for p in files)


def judge(task: Task, output: str, model: str, cwd: Path, claude_bin: str = "claude") -> dict:
    """A separate session without hooks, plugins, MCP servers or tools, so both arms get the same grader."""
    reference = (task.root / task.grading["judge_reference"]).read_text(encoding="utf-8")
    prompt = (JUDGE_TEMPLATE.read_text(encoding="utf-8").replace("{{task}}", task.prompt)
              .replace("{{reference}}", reference).replace("{{output}}", output[:JUDGE_CHARS] or "(no output)"))
    cwd.mkdir(parents=True, exist_ok=True)
    cmd = [claude_bin, "-p", "--model", model, "--setting-sources", "project", "--strict-mcp-config", "--tools", "",
           "--no-session-persistence", "--output-format", "json"]
    try:
        proc = subprocess.run(cmd, cwd=cwd, input=prompt, capture_output=True, text=True, timeout=300, check=False,
                              env=clean_env(os.environ, cwd / "unused.jsonl"))
    except subprocess.TimeoutExpired:
        return {"score": None, "reason": "judge timed out", "cost_usd": None}
    return judge_verdict(proc.stdout)


def judge_verdict(stdout: str) -> dict:
    try:
        reply = json.loads(stdout)
        verdict = json.loads(re.search(r"\{.*\}", reply.get("result", ""), re.DOTALL).group(0))
        score = int(verdict["score"])
    except (ValueError, TypeError, AttributeError, KeyError):
        return {"score": None, "reason": f"unparsed judge reply: {stdout[:200]}", "cost_usd": None}
    return {"score": max(1, min(10, score)), "reason": str(verdict.get("reason", "")),
            "cost_usd": reply.get("total_cost_usd")}
