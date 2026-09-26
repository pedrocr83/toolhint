"""One headless Claude Code session per run: workspace, command line, environment, and the stream-json loop."""
from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from . import Task

COMMON_TOOLS = ("Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS", "TodoWrite", "Skill", "Task", "Agent",
                "ToolSearch", "mcp__plugin_toolhint_router__route", "Bash(ls:*)", "Bash(cat:*)", "Bash(mkdir:*)",
                "Bash(wc:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(find:*)", "Bash(grep:*)", "Bash(git:*)")
# An install in one run would change the environment for every later run, in both arms
NO_INSTALLS = ("Bash(pip:*)", "Bash(pip3:*)", "Bash(python3 -m pip:*)", "Bash(python -m pip:*)", "Bash(uv pip:*)",
               "Bash(uv add:*)", "Bash(uv tool:*)", "Bash(npm install:*)", "Bash(npm i:*)", "Bash(npx:*)")
# Turning off only the local copy lets the synced Cowork upload load in its place
OFF_SETTINGS = {"enabledPlugins": {"toolhint@toolhint": False, "toolhint@synced": False}}
# A nested run must not inherit the launching session's identity, IDE link or effort level
PARENT_PREFIXES = ("CLAUDE", "VSCODE_")
PARENT_FLAGS = ("ENABLE_TOOL_SEARCH", "MCP_CONNECTION_NONBLOCKING", "DISABLE_NON_ESSENTIAL_MODEL_CALLS")


def command(task: Task, arm: str, model: str, claude_bin: str = "claude") -> list[str]:
    cmd = [claude_bin, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", model, "--permission-mode", "acceptEdits", "--no-session-persistence",
           "--max-budget-usd", f"{task.budget_usd:g}"]
    if arm == "off":
        cmd += ["--settings", json.dumps(OFF_SETTINGS)]
    return cmd + ["--disallowedTools", *NO_INSTALLS, "--allowedTools", *COMMON_TOOLS, *task.allowed_tools]


def clean_env(base: Mapping[str, str], decisions: Path) -> dict[str, str]:
    env = {key: value for key, value in base.items() if not key.startswith(PARENT_PREFIXES) and key not in PARENT_FLAGS}
    # the router inherits it and runs inside the workspace, so the path must be absolute
    env["TOOLHINT_LOG"] = str(decisions.resolve())
    return env


def prepare_workspace(task: Task, run_dir: Path) -> Path:
    """A fresh git repo holding only the task's starting files; graders and references stay outside."""
    workspace = run_dir / "workspace"
    if (task.root / "workspace").is_dir():
        shutil.copytree(task.root / "workspace", workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    return workspace


def run(cmd: Sequence[str], cwd: Path, env: Mapping[str, str] | None, prompt: str, warmup_s: float,
        timeout_s: float, stderr_path: Path, followup: Callable[[], str | None] | None = None) -> dict:
    """Start the session, give the router time to load, send the prompt, and read until a result. After each result,
    `followup` may return another message for the same session; the timeout covers all turns."""
    events: list[dict] = []
    signals: queue.Queue[str] = queue.Queue()
    with stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.Popen(list(cmd), cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr, text=True)

        def read() -> None:
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                events.append(event)
                if event.get("type") == "result":
                    signals.put("result")
            signals.put("eof")  # end of output: the session exited or crashed

        def send(text: str) -> None:
            try:
                proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
                proc.stdin.flush()
            except OSError:
                pass

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        started = time.monotonic()
        timed_out, followups = False, 0
        try:
            signals.get(timeout=warmup_s)  # only a crash signals before the prompt
        except queue.Empty:
            started = time.monotonic()
            deadline = started + timeout_s
            send(prompt)
            while True:
                try:
                    signal = signals.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    timed_out = True
                    break
                text = followup() if signal == "result" and followup else None
                if not text:
                    break
                followups += 1
                send(text)
        wall_s = time.monotonic() - started
        if timed_out:
            proc.kill()
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        reader.join(timeout=5)
    return {"events": events, "timed_out": timed_out, "exit_code": proc.returncode, "wall_s": round(wall_s, 1),
            "followups": followups}
