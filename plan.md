# Laya Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local routing layer. A stdio MCP server keeps a Laya model warm and suggests relevant skills, connectors and tools for each prompt. A Claude Code/Cowork plugin hook calls it on every `UserPromptSubmit`. The build is gated by a Phase 0 evaluation.

**Architecture:** There are three layers.
- **Catalog.** Reads files on disk to find routable items for the calling harness (Claude Code or Cowork).
- **Engine.** Shortlists items with BM25 over each item's name, connector and description, then runs one Laya `choice` per kind, with a `none` option so it can abstain. The original design used encoder cosine similarity; the gate amendment in Task 12 replaced it.
- **Server.** An MCP server that exposes a single `route` tool, loads the model in the background, and fails open.

The plugin's hook uses `type: mcp_tool` to call `route`. Other harnesses reach the same server through a single MCP config entry.

**Tech Stack:** Python 3.12, uv, `laya==0.3.20` (torch, transformers), official `mcp==2.2.0` SDK (`MCPServer`, `Client`), PyYAML, pytest with the anyio plugin (bundled with anyio).

**Spec:** `docs/superpowers/specs/2026-09-25-laya-router-design.md`

**Spec amendments (surfaced for review):**
1. The Claude Code catalog also indexes slash commands (`~/.claude/commands/*.md`, `<cwd>/.claude/commands/*.md`, plugin `commands/*.md`) and synced account skills (`~/.claude/skills/synced/*/<name>/SKILL.md`, id `anthropic-skills:<name>`). Both already appear in Claude's skill list and can be invoked through the Skill tool.
2. There is no Copilot CLI snippet, because its `mcp-config.json` schema wasn't verified. Gemini, Cursor and VS Code snippets use keys that were confirmed.
3. The hook checks for VS Code (2.1.282) and Cowork use the real plugin in Task 15, not the throwaway probe. The gate needs only the CLI result from Task 2.

## Global Constraints

- Python `>=3.12`. Every command runs through `uv run ...` from the repo root. There is no docker-compose here, so commands run on the host.
- Dependencies are limited to `laya==0.3.20`, `mcp==2.2.0`, `pyyaml>=6` and dev `pytest>=8`, all approved at plan approval. Nothing else gets installed without asking the user.
- Default Laya checkpoint is `typed-decisions`, called as `router.predict(state, questions, model=...)`. The environment variable `LAYA_MODEL` does not exist.
- Choice options render as `key: value` inside a 192-token head budget (`head_max_len`). Use compact option keys. A `ValueError` mentioning `head_max_len` halves the option lists (at most 3 attempts).
- MCP: stdio only. No network listener. A static tool list with the single tool `route`. Never proxy or execute other tools.
- Fail-open: `route` never raises to the client. It returns `""` when the model isn't loaded yet, on errors, and for skipped prompts. A hook timeout of 5 s never blocks the prompt.
- Hint: a single line of at most 400 characters, prefixed `[laya-router] advisory, ignore if irrelevant — `, or `""`.
- Skip rules: the prompt starts with `/`, the stripped prompt is shorter than 12 characters, or it repeats the previous prompt.
- Prompts are cut to 2000 characters before embedding or choice.
- Defaults:
  - K: skill 10, connector 15, tool 10.
  - τ: 0.35 for every kind.
  - Caps: skill 3, connector 2, tool 3.
  - Catalog TTL: 30 s.
  - Environment overrides: `LAYA_ROUTER_MODEL`, `LAYA_ROUTER_DEVICE`, `LAYA_ROUTER_K_SKILL`, `LAYA_ROUTER_K_TOOL`, `LAYA_ROUTER_TAU`, `LAYA_ROUTER_LOG`.
- Paths:
  - caches in `~/.cache/laya-router/` (`mcp-tools.json`);
  - decision log at `~/.local/state/laya-router/decisions.jsonl`, rotated past 10 MB.
- Plugin rules:
  - no top-level `bin/` (Cowork rejects it);
  - hook server name `plugin:laya-router:router`;
  - hook `timeout: 5`.
- Phase 0 gate:
  - top-3 skill recall ≥ 0.70 on the transcript-derived test set;
  - at least 0.10 above BM25;
  - p95 ≤ 250 ms on GPU;
  - the `mcp_tool` hook injects context in the Claude Code CLI.
- Privacy: `eval/data/` and `eval/results/` are gitignored and hold transcript-derived text. Nothing leaves the machine.
- Do not touch `DYNAMIC-ROUTING.md`, `LAYA-ONTOLOGY-TRAINING.md`, or anything under `~/.claude` or `~/.config/Claude`. The exception is the plugin install in Task 15, and only after the user says yes.
- Style, from the user's CLAUDE.md:
  - functions under 40 lines;
  - type hints on public functions;
  - descriptive names and early returns;
  - `logging`, never `print`, in library code (the CLI prints output);
  - conventional commits ending with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Stop condition: if the same check fails twice in a row, stop changing code and report what was tried.

## Review Focus

1. **A huge pasted prompt** (for example 50k characters of logs). Latency must stay bounded, because the prompt is cut to 2000 characters before the BM25 shortlist and the choice. BM25 on a 2000-character prompt over the real catalog costs about 11 ms. Tested in Task 7: `test_giant_prompt_is_truncated`.
2. **A kind with no catalog items** (no Cowork, so no connectors; tool cache never refreshed). That question is omitted, the other kinds are still ranked, and nothing crashes. Tested in Task 7 (`test_empty_kind_pool_omits_question`, `test_no_items_returns_empty_without_model_calls`) and Task 5 (`test_local_server_items_missing_cache_is_empty`).
3. **A broken SKILL.md** (invalid YAML, missing description, non-UTF-8 bytes, or a folded block scalar that should still parse). Broken ones are skipped silently and valid neighbors still load. Tested in Task 4: `test_scan_skills_skips_malformed_and_disabled`.
4. **A catalog item edited mid-session** (a skill description rewritten, or a plugin updated). The cached BM25 index must not go stale. Tested by the Task 12 amendment: `test_edited_item_text_refreshes_shortlist`. This replaces the embedding-cache item, which the gate amendment removed.
5. **Portuguese or other non-English prompts.** They pass through unchanged, and eval reports their accuracy as a separate split. With the BM25 shortlist, a prompt that shares no terms with any description gets the first K items in catalog order. Laya can still answer `none`. Tested in Task 7 (`test_unicode_prompt_passes_through`) and Tasks 10–11 (at least 10 `synthetic-pt` prompts, reported as `dev_pt`).

---

## Phase 0: foundation, spikes and gate

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `pyproject.toml`, `src/laya_router/__init__.py`, `src/laya_router/items.py`, `tests/conftest.py`, `tests/test_items.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `laya_router.items`, with:
  - `Kind = Literal["skill","connector","tool"]`, `KINDS`, `Harness`, `COWORK_MARKER`;
  - `Item(kind, id, label, text, connector=None, source="")`;
  - `RouteContext(prompt, cwd="", transcript_path="", session_id="")` with the property `.harness -> "claude-code" | "cowork"`;
  - `Candidate(id, label, p, connector=None)`;
  - `Ranking(skills, connectors, tools, latency_ms=0.0, model="")` with `.is_empty()`.

- [ ] **Step 1: Write `pyproject.toml`, `src/laya_router/__init__.py`, `tests/conftest.py`**

```toml
[project]
name = "laya-router"
version = "0.1.0"
description = "Local Laya classifier that suggests relevant skills, connectors and tools for each prompt"
requires-python = ">=3.12"
dependencies = [
    "laya==0.3.20",
    "mcp==2.2.0",
    "pyyaml>=6",
]

[project.scripts]
laya-router = "laya_router.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/laya_router"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
markers = ["slow: loads the real Laya checkpoint (~850 MB download on first run)"]
addopts = "-m 'not slow'"
```

```python
# src/laya_router/__init__.py
"""Laya router: local skill/connector/tool routing hints for agent harnesses."""

__version__ = "0.1.0"
```

```python
# tests/conftest.py
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

- [ ] **Step 2: Install and check the GPU works**

Run: `uv sync && uv run python -c "import torch, laya, mcp, yaml; print(torch.__version__, torch.cuda.is_available())"`
Expected: prints the torch version and `True`. The driver is 580.178.04 with CUDA 13.0. If it prints `False`, stop and report the output; do not try other torch indexes without asking.

- [ ] **Step 3: Write the failing test**

```python
# tests/test_items.py
from laya_router.items import Ranking, RouteContext

COWORK_TRANSCRIPT = "/home/u/.config/Claude/local-agent-mode-sessions/a/b/local_1/.claude/projects/x/s.jsonl"


def test_harness_detected_from_transcript_path():
    assert RouteContext("hi", transcript_path=COWORK_TRANSCRIPT).harness == "cowork"
    assert RouteContext("hi", transcript_path="/home/u/.claude/projects/x/s.jsonl").harness == "claude-code"
    assert RouteContext("hi").harness == "claude-code"


def test_empty_ranking_reports_empty():
    assert Ranking().is_empty()
```

- [ ] **Step 4: Run it and confirm it fails**

Run: `uv run pytest tests/test_items.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.items'`

- [ ] **Step 5: Write `src/laya_router/items.py`**

```python
"""Value types shared by catalog, engine and server."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["skill", "connector", "tool"]
KINDS: tuple[Kind, ...] = ("skill", "connector", "tool")
Harness = Literal["claude-code", "cowork"]
COWORK_MARKER = "/local-agent-mode-sessions/"


@dataclass(frozen=True)
class Item:
    """One routable thing, named exactly as the harness knows it."""

    kind: Kind
    id: str
    label: str
    text: str
    connector: str | None = None
    source: str = ""


@dataclass(frozen=True)
class RouteContext:
    """What the hook (or the model) tells us about the current turn."""

    prompt: str
    cwd: str = ""
    transcript_path: str = ""
    session_id: str = ""

    @property
    def harness(self) -> Harness:
        return "cowork" if COWORK_MARKER in self.transcript_path else "claude-code"


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    p: float
    connector: str | None = None


@dataclass
class Ranking:
    skills: list[Candidate] = field(default_factory=list)
    connectors: list[Candidate] = field(default_factory=list)
    tools: list[Candidate] = field(default_factory=list)
    latency_ms: float = 0.0
    model: str = ""

    def is_empty(self) -> bool:
        return not (self.skills or self.connectors or self.tools)
```

- [ ] **Step 6: Run and confirm it passes**

Run: `uv run pytest -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src tests
git commit -m "feat: scaffold laya-router package and shared types

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 2: Spike — does the `mcp_tool` UserPromptSubmit hook inject context?

Throwaway probe. It answers spec §11 items 1, 2 and 5, and the hook criterion of the gate. It makes 2 small `claude -p` calls on the user's account.

**Files:**
- Create: `spike/hook_probe/.claude-plugin/plugin.json`, `spike/hook_probe/.mcp.json`, `spike/hook_probe/hooks/hooks.json`, `spike/hook_probe/probe_server.py`, `spike/FINDINGS.md`
- Modify: `.gitignore` (append the spike artifacts)

**Interfaces:**
- Consumes: the `.venv` from Task 1 (`mcp` installed).
- Produces: `spike/FINDINGS.md` § Hook probe. Task 15 reads it to choose the hook template field and the `.mcp.json` command form.

- [ ] **Step 1: Write the probe plugin**

```json
{"name": "laya-probe", "version": "0.0.1", "description": "Throwaway probe for mcp_tool UserPromptSubmit hooks"}
```
(file: `spike/hook_probe/.claude-plugin/plugin.json`)

```json
{"mcpServers": {"probe": {"command": "${CLAUDE_PLUGIN_ROOT}/../../.venv/bin/python", "args": ["${CLAUDE_PLUGIN_ROOT}/probe_server.py"]}}}
```
(file: `spike/hook_probe/.mcp.json`)

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "mcp_tool", "server": "plugin:laya-probe:probe", "tool": "route",
  "input": {"prompt": "${prompt}", "cwd": "${cwd}", "transcript_path": "${transcript_path}", "session_id": "${session_id}"},
  "timeout": 5}]}]}}
```
(file: `spike/hook_probe/hooks/hooks.json`)

```python
# spike/hook_probe/probe_server.py
"""Throwaway: sentinel MCP server for checking mcp_tool UserPromptSubmit hooks."""
import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

LOG = Path(__file__).with_name("calls.jsonl")
server = MCPServer("probe")


@server.tool(name="route", description="Probe: records hook arguments and returns a sentinel.")
def route(prompt: str = "", cwd: str = "", transcript_path: str = "", session_id: str = "") -> str:
    record = {"prompt": prompt, "cwd": cwd, "transcript_path": transcript_path, "session_id": session_id}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return "" if "EMPTY" in prompt else "LAYA_SENTINEL_42"


if __name__ == "__main__":
    server.run()
```

Append to `.gitignore`:

```
# spike run artifacts
spike/hook_probe/calls.jsonl
spike/hook_probe/*.log
spike/hook_probe/out*.txt
```

- [ ] **Step 2: Run the sentinel check**

```bash
rm -f spike/hook_probe/calls.jsonl
claude -p --plugin-dir spike/hook_probe --debug \
  "If your context contains a token starting with LAYA_SENTINEL, reply with that exact token and nothing else; otherwise reply NONE." \
  > spike/hook_probe/out1.txt 2> spike/hook_probe/debug1.log
cat spike/hook_probe/out1.txt; cat spike/hook_probe/calls.jsonl; grep -n "mcp_tool" spike/hook_probe/debug1.log | head
```

Expected: `out1.txt` contains `LAYA_SENTINEL_42`. `calls.jsonl` has 1 line whose `prompt` equals the question and whose `cwd`, `transcript_path` and `session_id` are all non-empty. The debug log shows `Hooks: mcp_tool calling plugin:laya-probe:probe/route`.
If the log says `MCP server ... not connected`, the server wasn't ready when the hook ran in `-p` mode. Rerun once. If it still fails, record that and ask the user to type the same question into an interactive `claude --plugin-dir spike/hook_probe` session.

- [ ] **Step 3: Run the empty-result check**

```bash
claude -p --plugin-dir spike/hook_probe \
  "EMPTY check: if your context contains any text injected by a UserPromptSubmit hook, quote it verbatim; otherwise reply NONE." \
  > spike/hook_probe/out2.txt 2> spike/hook_probe/debug2.log
cat spike/hook_probe/out2.txt
```

Expected: `NONE`, meaning an empty tool result injects nothing.

- [ ] **Step 4: Record the findings** in `spike/FINDINGS.md`

```markdown
# Phase 0 spike findings

## Hook probe (Task 2) — Claude Code CLI `claude --version` output here
- Sentinel reached the model: <yes/no> — out1.txt: "<verbatim>"
- Hook args received (calls.jsonl): prompt <ok/missing>, cwd <ok/missing>, transcript_path <ok/missing>, session_id <ok/missing>
- `${CLAUDE_PLUGIN_ROOT}` expanded in .mcp.json command/args: <yes/no>
- Empty result injects nothing: <yes/no> — out2.txt: "<verbatim>"
- Debug lines mentioning mcp_tool: <paste up to 5 lines>
- Decision for Task 15: hook input field `${prompt}` <confirmed / replace with ...>; gate hook criterion <PASS/FAIL>
```

Every `<...>` gets the observed value. If the sentinel never arrives after the interactive retry, **stop and report to the user**, because approach A's automatic hint depends on it (spec §7, fallback C).

- [ ] **Step 5: Commit**

```bash
git add .gitignore spike/hook_probe spike/FINDINGS.md
git commit -m "test: probe mcp_tool UserPromptSubmit hook in Claude Code CLI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 3: Spike — Laya load time, latency, VRAM and head budget on this machine

**Files:**
- Create: `spike/laya_probe.py`, `spike/results/laya_probe.json` (generated)
- Modify: `spike/FINDINGS.md` (append a section)

**Interfaces:**
- Consumes: `laya.Router`, `Router.preload`, `Router.load`, `Router.predict(..., model=, head_max_len=)`, `laya.shortlist.embed_fn_from_agent` (all confirmed in the laya 0.3.20 source).
- Produces: measured numbers. Task 7 uses the head-budget result: if 10 options at 80 characters overflow, lower `LABEL_CHARS` in `catalog.py` and note it.

- [ ] **Step 1: Write the probe**

```python
# spike/laya_probe.py
"""Throwaway: measure Laya load/latency/VRAM and the choice head budget on this machine."""
import json
import statistics
import sys
import time
from pathlib import Path

import torch
from laya import Router
from laya.shortlist import embed_fn_from_agent

MODEL = "typed-decisions"
STATE = {"request": "my pytest suite fails with a KeyError after the refactor, help me find why"}
LABEL = "Use when encountering any bug, test failure or unexpected behavior"


def timed(fn, runs: int) -> dict:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {"p50_ms": round(statistics.median(samples), 1), "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 1)}


def questions(n: int) -> dict:
    criteria = {**{f"skill-name-{i}": LABEL for i in range(n)}, "none": "no specialized skill or tool needed"}
    return {kind: {"type": "choice", "instructions": f"Which {kind} fits?", "criteria": criteria}
            for kind in ("skill", "connector", "tool")}


def head_budget(router: Router) -> dict:
    out = {}
    for n in (5, 10, 15, 20):
        for head in (None, 256, 384):
            try:
                router.predict(STATE, {"skill": questions(n)["skill"]}, model=MODEL, head_max_len=head)
                out[f"n{n}_head{head}"] = "ok"
            except ValueError as exc:
                out[f"n{n}_head{head}"] = f"ValueError: {exc}"
    return out


def probe(device: str) -> dict:
    start = time.perf_counter()
    router = Router(device=None if device == "auto" else device)
    router.preload([MODEL])
    agent = router.load(MODEL)
    load_s = round(time.perf_counter() - start, 2)
    embed = embed_fn_from_agent(agent)
    result = {"device": device, "actual_device": str(agent.device), "load_s": load_s,
              "embed_1": timed(lambda: embed([STATE["request"]]), 20),
              "embed_100": timed(lambda: embed([f"item text {i} about things" for i in range(100)]), 3),
              "predict_3q_k5": timed(lambda: router.predict(STATE, questions(5), model=MODEL), 20),
              "head_budget": head_budget(router)}
    if torch.cuda.is_available():
        result["vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
    return result


if __name__ == "__main__":
    report = [probe(device) for device in (sys.argv[1:] or ["auto", "cpu"])]
    Path("spike/results").mkdir(parents=True, exist_ok=True)
    Path("spike/results/laya_probe.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
```

- [ ] **Step 2: Run it** (the first run downloads about 850 MB)

Run: `uv run python spike/laya_probe.py`
Expected: JSON for `auto` and `cpu`. `auto` should report `actual_device` `cuda...`. Record the `head_budget` map; overflowing entries show `ValueError: ... head_max_len=...`.

- [ ] **Step 3: Append findings** to `spike/FINDINGS.md`

```markdown
## Laya probe (Task 3)
- auto → actual device: <cuda:0/cpu>; load: <s> (auto), <s> (cpu); VRAM: <MB>
- predict 3 questions × (5 options + none): p50/p95 <ms>/<ms> (auto), <ms>/<ms> (cpu)
- embed 1 text: p50 <ms> (auto); embed 100 texts: p50 <ms>
- head budget (default head): n5 <ok/overflow>, n10 <...>, n15 <...>, n20 <...>
- Decision: LABEL_CHARS stays 80 / lowered to <n> because <reason>; LayaScorer device=None (auto) <works/needs explicit cuda>
```

- [ ] **Step 4: Commit**

```bash
git add spike/laya_probe.py spike/results/laya_probe.json spike/FINDINGS.md
git commit -m "test: measure laya latency, VRAM and head budget locally

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 4: Catalog — skills and slash commands

**Files:**
- Create: `src/laya_router/catalog.py`, `tests/test_catalog_skills.py`
- Modify: `tests/conftest.py` (add the `write_skill` fixture)

**Interfaces:**
- Consumes: `laya_router.items.Item`, `Kind`.
- Produces, in `laya_router.catalog`:
  - constants `LABEL_CHARS=80`, `TEXT_CHARS=1500`, `COWORK_ROOT`;
  - `one_line(text, limit=80) -> str`;
  - `make_item(kind, item_id, description, source, connector=None) -> Item`;
  - `load_json(path | None) -> dict`;
  - `read_frontmatter(path) -> dict`;
  - `markdown_item(path, name, prefix, source) -> Item | None`;
  - `scan_skills(root, prefix="", source="") -> list[Item]`;
  - `scan_commands(root, prefix="", source="") -> list[Item]`;
  - `enabled_plugin_paths(home) -> dict[str, Path]`;
  - `claude_code_skills(home, cwd: Path | None) -> list[Item]`;
  - `cowork_skills(home, session: dict) -> list[Item]`.

- [ ] **Step 1: Add the fixture to `tests/conftest.py`** (append)

```python
from collections.abc import Callable
from pathlib import Path


def skill_md(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n"


@pytest.fixture
def write_skill() -> Callable[..., Path]:
    def write(root: Path, name: str, body: str | None = None) -> Path:
        path = root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body if body is not None else skill_md(name, f"{name} skill."), encoding="utf-8")
        return path

    return write
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_catalog_skills.py
import json

from laya_router.catalog import claude_code_skills, cowork_skills, one_line, scan_commands, scan_skills


def test_one_line_takes_first_sentence_and_truncates():
    assert one_line("Fix bugs. Then more.") == "Fix bugs."
    assert len(one_line("x" * 200)) == 80


def test_scan_skills_reads_name_and_description(tmp_path, write_skill):
    write_skill(tmp_path, "graphify", '---\nname: graphify\ndescription: "any input to knowledge graph. Use when asked."\n---\n')
    [item] = scan_skills(tmp_path)
    assert (item.kind, item.id, item.label) == ("skill", "graphify", "any input to knowledge graph.")


def test_scan_skills_skips_malformed_and_disabled(tmp_path, write_skill):
    write_skill(tmp_path, "bad-yaml", "---\nname: [unclosed\ndescription: x\n---\n")
    write_skill(tmp_path, "no-desc", "---\nname: no-desc\n---\n")
    write_skill(tmp_path, "no-frontmatter", "# just a heading\n")
    write_skill(tmp_path, "hidden", "---\nname: hidden\ndescription: secret\ndisable-model-invocation: true\n---\n")
    (tmp_path / "binary").mkdir()
    (tmp_path / "binary" / "SKILL.md").write_bytes(b"\xff\xfe---\x00")
    write_skill(tmp_path, "good", "---\nname: good\ndescription: >\n  Folded block\n  description.\n---\n")
    items = scan_skills(tmp_path)
    assert [i.id for i in items] == ["good"]
    assert items[0].label == "Folded block description."


def test_scan_commands_uses_file_stem(tmp_path):
    (tmp_path / "explore.md").write_text("---\ndescription: Delegate read-only exploration\n---\nbody\n")
    (tmp_path / "nodesc.md").write_text("no frontmatter\n")
    assert [i.id for i in scan_commands(tmp_path, prefix="p")] == ["p:explore"]


def test_claude_code_skills_include_synced_commands_and_enabled_plugins(tmp_path, write_skill):
    home = tmp_path
    write_skill(home / ".claude" / "skills", "mine")
    write_skill(home / ".claude" / "skills" / "synced" / "org_acct", "pdf")
    (home / ".claude" / "commands").mkdir(parents=True)
    (home / ".claude" / "commands" / "fix.md").write_text("---\ndescription: Small scoped fix\n---\n")
    plugin_root, off_root = home / "cache" / "superpowers" / "6.4.1", home / "cache" / "off" / "1"
    write_skill(plugin_root / "skills", "brainstorming")
    write_skill(off_root / "skills", "nope")
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"superpowers@official": True, "off@official": False}}))
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "superpowers@official": [{"installPath": str(plugin_root)}],
        "off@official": [{"installPath": str(off_root)}]}}))
    ids = sorted(i.id for i in claude_code_skills(home, cwd=None))
    assert ids == ["anthropic-skills:pdf", "fix", "mine", "superpowers:brainstorming"]


def test_cowork_skills_from_manifest_and_session_plugins(tmp_path, write_skill):
    manifest = tmp_path / ".config/Claude/local-agent-mode-sessions/skills-plugin/org/acct/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"skills": [
        {"name": "pdf", "description": "Work with PDF files.", "enabled": True},
        {"name": "off", "description": "Disabled.", "enabled": False}]}))
    plugin = tmp_path / "userplugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "mytools"}))
    write_skill(plugin / "skills", "deploy")
    session = {"skillsEnabled": "true", "pluginInstallPaths": [str(plugin)]}
    assert sorted(i.id for i in cowork_skills(tmp_path, session)) == ["anthropic-skills:pdf", "mytools:deploy"]
    assert cowork_skills(tmp_path, {"skillsEnabled": False}) == []
```

- [ ] **Step 3: Run and confirm they fail**

Run: `uv run pytest tests/test_catalog_skills.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.catalog'`

- [ ] **Step 4: Write `src/laya_router/catalog.py`**

```python
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
```

- [ ] **Step 5: Run and confirm they pass**

Run: `uv run pytest tests/test_catalog_skills.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/laya_router/catalog.py tests/test_catalog_skills.py tests/conftest.py
git commit -m "feat: discover skills and slash commands for Claude Code and Cowork

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 5: Catalog — connectors, tools, `discover()` with TTL

**Files:**
- Modify: `src/laya_router/catalog.py` (append), `tests/conftest.py` (append an autouse cache reset)
- Create: `tests/test_catalog_discover.py`

**Interfaces:**
- Consumes: everything from Task 4; `RouteContext` from `items`.
- Produces:
  - constants `TOOL_CACHE`, `TTL_S=30.0`;
  - `connector_items(name, instructions, tools, tool_prefix, source) -> list[Item]`;
  - `claude_ai_items(session, cc_names: bool) -> list[Item]`;
  - `local_server_items(home) -> list[Item]`;
  - `connector_of(tool_id) -> str | None`;
  - `session_json_for(transcript_path) -> Path | None`;
  - `newest_session_json(home) -> Path | None`;
  - `discover(ctx, home=None, now=None) -> list[Item]`;
  - `clear_cache()`;
  - `dedupe(items) -> list[Item]`;
  - `harness_catalogs(home=None) -> dict[str, list[Item]]`.

  Tool id forms:
  - `mcp__<server>__<tool>`;
  - `mcp__plugin_<plugin>_<server>__<tool>`;
  - `mcp__claude_ai_<Name with spaces→_>__<tool>` for Claude Code;
  - the plain `<tool>` for Cowork.

- [ ] **Step 1: Append the autouse reset to `tests/conftest.py`**

```python
@pytest.fixture(autouse=True)
def _fresh_catalog_cache():
    from laya_router import catalog

    catalog.clear_cache()
    yield
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_catalog_discover.py
import json

from laya_router.catalog import (
    claude_ai_items, connector_of, discover, harness_catalogs, local_server_items, session_json_for,
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
```

- [ ] **Step 3: Run and confirm they fail**

Run: `uv run pytest tests/test_catalog_discover.py -v`
Expected: FAIL with `ImportError: cannot import name 'claude_ai_items'`

- [ ] **Step 4: Append to `src/laya_router/catalog.py`**

Add `import time` and `from collections.abc import Callable` to the imports, and change the items import to `from .items import Item, Kind, RouteContext`. Then append:

```python
TOOL_CACHE = Path(".cache") / "laya-router" / "mcp-tools.json"
TTL_S = 30.0
_CACHE: dict[tuple[str, ...], tuple[float, list[Item]]] = {}


def connector_items(name: str, instructions: str, tools: list, tool_prefix: str, source: str) -> list[Item]:
    """One connector item plus one tool item per tool; tool ids are tool_prefix + tool name."""
    tool_list = [tool for tool in tools if isinstance(tool, dict) and tool.get("name")]
    names = ", ".join(tool["name"] for tool in tool_list)
    items = [make_item("connector", name, f"{instructions.strip()} {name} tools: {names}".strip(), source)]
    for tool in tool_list:
        description = str(tool.get("description") or tool["name"])
        items.append(make_item("tool", tool_prefix + tool["name"], f"{name} {tool['name']}: {description}", source, name))
    return items


def claude_ai_items(session: dict, cc_names: bool) -> list[Item]:
    """claude.ai connectors from a Cowork session JSON; Claude Code tool ids when cc_names."""
    items: list[Item] = []
    for server in session.get("remoteMcpServersConfig") or []:
        if not isinstance(server, dict) or not server.get("name"):
            continue
        name = str(server["name"])
        prefix = f"mcp__claude_ai_{name.replace(' ', '_')}__" if cc_names else ""
        items += connector_items(name, str(server.get("instructions") or ""), server.get("tools") or [], prefix, "claude.ai")
    return items


def local_server_items(home: Path) -> list[Item]:
    """Local MCP servers snapshotted by `laya-router catalog --refresh`."""
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
```

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: all tests pass, including 8 new ones.

- [ ] **Step 6: Smoke-test against the real machine** (read-only)

Run: `uv run python -c "from collections import Counter; from laya_router.catalog import harness_catalogs; print({h: Counter(i.kind for i in items) for h, items in harness_catalogs().items()})"`
Expected: `claude-code` has about 80 or more skills and 7 or more connectors, taken from the newest Cowork session. `cowork` has skills and connectors. Local tools are still 0 because the tool cache comes in Task 6.

- [ ] **Step 7: Commit**

```bash
git add src/laya_router/catalog.py tests/test_catalog_discover.py tests/conftest.py
git commit -m "feat: discover connectors and tools per harness with TTL cache

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 6: Tool cache — snapshot local stdio MCP servers

**Files:**
- Create: `src/laya_router/toolcache.py`, `tests/test_toolcache.py`

**Interfaces:**
- Consumes: `catalog.TOOL_CACHE`, `catalog.enabled_plugin_paths`, `catalog.load_json`; `mcp.Client`, `mcp.StdioServerParameters` (verified: `Client(StdioServerParameters(...))`, `await client.list_tools(cursor=...)` returns `.tools[].name/.description` and `.next_cursor`).
- Produces:
  - `server_configs(data) -> dict`;
  - `configured_servers(home, cwd) -> list[dict]`, where each dict has the keys `name`, `plugin`, `command`, `args`, `env`;
  - `stdio_entry(name, cfg, plugin, root) -> dict | None`;
  - `async list_tools(server) -> list[dict]`;
  - `async refresh(servers, out) -> dict`, which writes `{"refreshed_at", "servers": [{"name","plugin","instructions","tools":[{"name","description"}]}]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_toolcache.py
import json
import sys

import pytest

from laya_router.toolcache import configured_servers, refresh

FIXTURE_SERVER = '''
from mcp.server.mcpserver import MCPServer
server = MCPServer("fixture")

@server.tool(name="echo", description="Echo text back.")
def echo(text: str) -> str:
    return text

server.run()
'''


@pytest.mark.anyio
async def test_refresh_snapshots_stdio_server(tmp_path):
    script = tmp_path / "srv.py"
    script.write_text(FIXTURE_SERVER)
    servers = [{"name": "fixture", "plugin": None, "command": sys.executable, "args": [str(script)], "env": None}]
    snapshot = await refresh(servers, tmp_path / "cache.json")
    assert snapshot["servers"][0]["tools"] == [{"name": "echo", "description": "Echo text back."}]
    assert json.loads((tmp_path / "cache.json").read_text())["servers"][0]["name"] == "fixture"


@pytest.mark.anyio
async def test_refresh_skips_broken_server(tmp_path):
    servers = [{"name": "broken", "plugin": None, "command": "/nonexistent/bin", "args": [], "env": None}]
    assert (await refresh(servers, tmp_path / "cache.json"))["servers"] == []


def test_configured_servers_expands_plugin_root_and_skips_http_and_self(tmp_path):
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {
        "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
        "remote": {"type": "http", "url": "https://example.com/mcp"}}}))
    root, self_root = tmp_path / "cache" / "playwright" / "1", tmp_path / "cache" / "laya-router" / "1"
    root.mkdir(parents=True)
    self_root.mkdir(parents=True)
    (root / ".mcp.json").write_text(json.dumps({"playwright": {"command": "npx", "args": ["${CLAUDE_PLUGIN_ROOT}/x"]}}))
    (self_root / ".mcp.json").write_text(json.dumps({"mcpServers": {"router": {"command": "laya-router"}}}))
    (tmp_path / ".claude" / "plugins").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"playwright@official": True, "laya-router@layla": True}}))
    (tmp_path / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "playwright@official": [{"installPath": str(root)}], "laya-router@layla": [{"installPath": str(self_root)}]}}))
    servers = configured_servers(tmp_path, cwd=None)
    assert [(s["name"], s["plugin"]) for s in servers] == [("context7", None), ("playwright", "playwright")]
    assert servers[1]["args"] == [f"{root}/x"]
```

- [ ] **Step 2: Run and confirm they fail**

Run: `uv run pytest tests/test_toolcache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.toolcache'`

- [ ] **Step 3: Write `src/laya_router/toolcache.py`**

```python
"""Snapshot tools/list of the user's local stdio MCP servers for the catalog."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from .catalog import enabled_plugin_paths, load_json

log = logging.getLogger("laya_router.toolcache")
TIMEOUT_S = 30
SELF_PLUGIN = "laya-router"


def server_configs(data: dict) -> dict:
    """Server mapping from either the wrapped ({"mcpServers": ...}) or the flat .mcp.json layout."""
    wrapped = data.get("mcpServers")
    return wrapped if isinstance(wrapped, dict) else data


def configured_servers(home: Path, cwd: Path | None) -> list[dict]:
    """Stdio servers from ~/.claude.json, <cwd>/.mcp.json and enabled plugins' .mcp.json."""
    sources: list[tuple[dict, str | None, Path | None]] = [
        (load_json(home / ".claude.json").get("mcpServers") or {}, None, None)]
    if cwd:
        sources.append((server_configs(load_json(cwd / ".mcp.json")), None, None))
    for plugin, root in enabled_plugin_paths(home).items():
        if plugin != SELF_PLUGIN:
            sources.append((server_configs(load_json(root / ".mcp.json")), plugin, root))
    entries = [stdio_entry(name, cfg, plugin, root) for configs, plugin, root in sources for name, cfg in configs.items()]
    return [entry for entry in entries if entry]


def stdio_entry(name: str, cfg: object, plugin: str | None, root: Path | None) -> dict | None:
    """Launch spec for a stdio server; None for http/sse servers (they need auth headers)."""
    if not isinstance(cfg, dict) or not cfg.get("command"):
        return None

    def expand(value: object) -> str:
        return os.path.expandvars(str(value).replace("${CLAUDE_PLUGIN_ROOT}", str(root or "")))

    env = {key: expand(value) for key, value in (cfg.get("env") or {}).items()}
    return {"name": name, "plugin": plugin, "command": expand(cfg["command"]),
            "args": [expand(arg) for arg in cfg.get("args") or []], "env": env or None}


async def list_tools(server: dict) -> list[dict]:
    """All tools a stdio server advertises, following pagination."""
    params = StdioServerParameters(command=server["command"], args=server["args"], env=server["env"])
    tools: list[dict] = []
    cursor: str | None = None
    async with Client(params) as client:
        while True:
            page = await client.list_tools(cursor=cursor)
            tools += [{"name": tool.name, "description": tool.description or ""} for tool in page.tools]
            cursor = page.next_cursor
            if not cursor:
                return tools


async def refresh(servers: list[dict], out: Path) -> dict:
    """Snapshot every reachable server into `out`; unreachable servers are skipped."""
    snapshot: dict = {"refreshed_at": time.time(), "servers": []}
    for server in servers:
        try:
            with anyio.fail_after(TIMEOUT_S):
                tools = await list_tools(server)
        except Exception as exc:  # a dead server must not abort the snapshot
            log.warning("skipping MCP server %s: %s", server["name"], exc)
            continue
        snapshot["servers"].append({"name": server["name"], "plugin": server["plugin"], "instructions": "", "tools": tools})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    return snapshot
```

- [ ] **Step 4: Run and confirm they pass**

Run: `uv run pytest -v`
Expected: all pass, 3 new.

- [ ] **Step 5: Commit**

```bash
git add src/laya_router/toolcache.py tests/test_toolcache.py
git commit -m "feat: snapshot local stdio MCP tool lists into the catalog cache

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 7: Engine — shortlist, choice, thresholds, caches

**Files:**
- Create: `src/laya_router/engine.py`, `tests/fakes.py`, `tests/test_engine.py`

**Interfaces:**
- Consumes: `items.KINDS`, `Item`, `Candidate`, `Ranking`.
- Produces, in `laya_router.engine`:
  - constants `NONE_ID="none"`, `NONE_LABEL`, `MAX_PROMPT_CHARS=2000`, `QUESTIONS`, `PLURAL`, `Scores = dict[str, list[tuple[str, float]]]`;
  - `Scorer` protocol: `.model: str`, `.embed(texts) -> np.ndarray`, `.choose(state: dict, questions: dict) -> dict`, the last returning Laya's `answers` shape `{qid: {"choice": key, "probabilities": {key: p}}}`;
  - `EngineConfig(k, tau, cap, min_prompt_chars=12)` with `.from_env(env)`;
  - `EmbeddingCache(path=None)` with `.vectors(items, embed) -> np.ndarray`;
  - `digest(text)`, `cosine(query, matrix)`, `should_skip(prompt, previous, min_chars)`, `short_key(item)`, `option_keys(pool)`, `build_questions(keyed)`, `translate(answer, keyed)`;
  - `Engine(scorer, cfg=None, cache=None)` with `.scores(prompt, items) -> Scores`, `.rank(prompt, items) -> Ranking`, `.overflows: int`.

- [ ] **Step 1: Write the fake scorer**

```python
# tests/fakes.py
"""Deterministic stand-in for LayaScorer."""
from __future__ import annotations

import numpy as np

VOCAB = ("debug", "test", "email", "calendar", "slides", "browser", "deploy", "docs")


class FakeScorer:
    model = "fake"

    def __init__(self, answers: dict[str, dict[str, float]] | None = None, max_options: int | None = None) -> None:
        self.answers = answers or {}
        self.max_options = max_options
        self.embed_calls: list[list[str]] = []
        self.choose_calls: list[tuple[dict, dict]] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return np.array([[text.lower().count(word) for word in VOCAB] + [0.01] for text in texts], dtype=np.float32)

    def choose(self, state, questions):
        self.choose_calls.append((state, questions))
        for qid, question in questions.items():
            if self.max_options and len(question["criteria"]) > self.max_options:
                raise ValueError(f"question {qid!r} options exceed head_max_len=192")
        out = {}
        for qid, question in questions.items():
            probs = self._probs(qid, question["criteria"])
            out[qid] = {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs}
        return out

    def _probs(self, qid: str, criteria: dict) -> dict[str, float]:
        preset = {key: p for key, p in self.answers.get(qid, {}).items() if key in criteria}
        rest = [key for key in criteria if key not in preset]
        share = max(0.0, 1.0 - sum(preset.values())) / len(rest) if rest else 0.0
        return {**preset, **dict.fromkeys(rest, share)}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_engine.py
import numpy as np
from fakes import FakeScorer

from laya_router.engine import (
    NONE_ID, EmbeddingCache, Engine, EngineConfig, digest, option_keys, should_skip,
)
from laya_router.items import Item

K2 = EngineConfig(k={"skill": 2, "connector": 15, "tool": 10})
PROMPT = "please debug the failing test"


def skill(item_id: str, text: str) -> Item:
    return Item("skill", item_id, text[:80], text)


SKILLS = [skill("debugging", "debug failing test errors"), skill("slides", "make slides decks"),
          skill("email-writer", "write email drafts"), skill("calendar-helper", "calendar scheduling"),
          skill("browser-bot", "drive the browser"), skill("deployer", "deploy services"),
          skill("doc-writer", "write docs pages"), skill("tester", "write test suites")]


def test_skip_rules():
    assert should_skip("/brainstorm build x", "", 12)
    assert should_skip("ok thanks", "", 12)
    assert should_skip("same prompt here!", "same prompt here!", 12)
    assert not should_skip(PROMPT, "", 12)


def test_rank_skips_without_calling_scorer():
    scorer = FakeScorer()
    assert Engine(scorer).rank("/compact now please", SKILLS).is_empty()
    assert not scorer.embed_calls and not scorer.choose_calls


def test_shortlist_keeps_top_k_by_cosine():
    scorer = FakeScorer()
    Engine(scorer, K2).scores("debug this failing test", SKILLS)
    assert set(scorer.choose_calls[0][1]["skill"]["criteria"]) == {"debugging", "tester", NONE_ID}


def test_none_winning_empties_kind():
    scorer = FakeScorer({"skill": {NONE_ID: 0.7, "debugging": 0.2}})
    assert Engine(scorer).rank(PROMPT, SKILLS).skills == []


def test_threshold_and_cap():
    scorer = FakeScorer({"skill": {"debugging": 0.5, "tester": 0.36, "slides": 0.1}})
    cfg = EngineConfig(cap={"skill": 1, "connector": 2, "tool": 3})
    ranking = Engine(scorer, cfg).rank(PROMPT, SKILLS)
    assert [(c.id, c.p) for c in ranking.skills] == [("debugging", 0.5)]


def test_option_keys_are_short_and_unique():
    pool = [Item("tool", "mcp__a__search", "a", "a"), Item("tool", "mcp__b__search", "b", "b"),
            Item("skill", "x:none", "n", "n")]
    assert list(option_keys(pool)) == ["search", "search-2", "none-2"]


def test_scores_translate_option_keys_back_to_item_ids():
    items = [Item("tool", "mcp__claude_ai_Gmail__search_threads", "Gmail: search", "gmail search email", "Gmail")]
    scores = Engine(FakeScorer({"tool": {"search_threads": 0.8}})).scores("find the email from Ana", items)
    assert scores["tool"][0] == ("mcp__claude_ai_Gmail__search_threads", 0.8)


def test_empty_kind_pool_omits_question():
    scorer = FakeScorer()
    Engine(scorer).scores(PROMPT, SKILLS)
    assert set(scorer.choose_calls[0][1]) == {"skill"}


def test_no_items_returns_empty_without_model_calls():
    scorer = FakeScorer()
    assert Engine(scorer).scores(PROMPT, []) == {}
    assert not scorer.embed_calls


def test_giant_prompt_is_truncated():
    scorer = FakeScorer()
    Engine(scorer).scores("debug " * 20000, SKILLS)
    assert len(scorer.choose_calls[0][0]["request"]) == 2000


def test_unicode_prompt_passes_through():
    scorer = FakeScorer()
    Engine(scorer).scores("depura o teste que está a falhar, por favor", SKILLS)
    assert scorer.choose_calls[0][0]["request"] == "depura o teste que está a falhar, por favor"


def test_head_budget_overflow_halves_shortlists():
    scorer = FakeScorer(max_options=5)
    engine = Engine(scorer)
    scores = engine.scores(PROMPT, SKILLS)
    assert len(scorer.choose_calls) == 2 and engine.overflows == 1
    assert len(scorer.choose_calls[1][1]["skill"]["criteria"]) == 5
    assert scores["skill"]


def test_embedding_cache_persists_and_skips_known_texts(tmp_path):
    path = tmp_path / "emb.npz"
    Engine(FakeScorer(), K2, EmbeddingCache(path)).scores(PROMPT, SKILLS)
    second = FakeScorer()
    Engine(second, K2, EmbeddingCache(path)).scores(PROMPT, SKILLS)
    assert path.exists()
    assert second.embed_calls == [[PROMPT]]


def test_corrupt_cache_file_is_ignored(tmp_path):
    path = tmp_path / "emb.npz"
    path.write_bytes(b"not a zip")
    scorer = FakeScorer()
    Engine(scorer, K2, EmbeddingCache(path)).scores(PROMPT, SKILLS)
    assert len(scorer.embed_calls) == 2


def test_mixed_dimension_cache_rebuilds(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.npz")
    cache._vecs[digest(SKILLS[0].text)] = np.zeros(3, dtype=np.float32)
    scores = Engine(FakeScorer(), K2, cache).scores(PROMPT, SKILLS)
    assert scores["skill"]


def test_config_from_env():
    cfg = EngineConfig.from_env({"LAYA_ROUTER_K_SKILL": "5", "LAYA_ROUTER_TAU": "0.5"})
    assert cfg.k == {"skill": 5, "connector": 15, "tool": 10}
    assert cfg.tau == {"skill": 0.5, "connector": 0.5, "tool": 0.5}
```

- [ ] **Step 3: Run and confirm they fail**

Run: `uv run pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.engine'`

- [ ] **Step 4: Write `src/laya_router/engine.py`**

```python
"""Rank catalog items for a prompt: embedding shortlist, then one Laya choice per kind."""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from .items import KINDS, Candidate, Item, Ranking

log = logging.getLogger("laya_router.engine")
NONE_ID = "none"
NONE_LABEL = "no specialized skill or tool needed; general request"
MAX_PROMPT_CHARS = 2000
QUESTIONS = {
    "skill": "Which skill should handle this request?",
    "connector": "Which connected app or MCP server does this request need?",
    "tool": "Which tool should be called first for this request?",
}
PLURAL = {"skill": "skills", "connector": "connectors", "tool": "tools"}
DEFAULT_K = {"skill": 10, "connector": 15, "tool": 10}
DEFAULT_TAU = {"skill": 0.35, "connector": 0.35, "tool": 0.35}
DEFAULT_CAP = {"skill": 3, "connector": 2, "tool": 3}
Scores = dict[str, list[tuple[str, float]]]


class Scorer(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...

    def choose(self, state: dict, questions: dict) -> dict: ...


@dataclass(frozen=True)
class EngineConfig:
    k: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_K))
    tau: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TAU))
    cap: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CAP))
    min_prompt_chars: int = 12

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> EngineConfig:
        k, tau = dict(DEFAULT_K), dict(DEFAULT_TAU)
        if env.get("LAYA_ROUTER_K_SKILL"):
            k["skill"] = int(env["LAYA_ROUTER_K_SKILL"])
        if env.get("LAYA_ROUTER_K_TOOL"):
            k["tool"] = int(env["LAYA_ROUTER_K_TOOL"])
        if env.get("LAYA_ROUTER_TAU"):
            tau = dict.fromkeys(tau, float(env["LAYA_ROUTER_TAU"]))
        return cls(k=k, tau=tau)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """sha256(text) -> vector, persisted to an .npz so sessions share the work."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._vecs: dict[str, np.ndarray] = self._load(path)

    @staticmethod
    def _load(path: Path | None) -> dict[str, np.ndarray]:
        if not path or not path.exists():
            return {}
        try:
            with np.load(path) as data:
                return {key: data[key] for key in data.files}
        except Exception:  # corrupt or partial file: rebuild rather than fail
            log.warning("ignoring unreadable embedding cache %s", path)
            return {}

    def vectors(self, items: Sequence[Item], embed: Callable[[Sequence[str]], np.ndarray]) -> np.ndarray:
        keys = [digest(item.text) for item in items]
        missing = {key: item.text for key, item in zip(keys, items) if key not in self._vecs}
        if missing:
            fresh = np.asarray(embed(list(missing.values())), dtype=np.float32)
            self._vecs.update(zip(missing.keys(), fresh))
            self._save()
        try:
            return np.stack([self._vecs[key] for key in keys])
        except ValueError:  # mixed dimensions: stale vectors from another encoder
            self._vecs = {}
            return self.vectors(items, embed)

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp.npz")
        np.savez(tmp, **self._vecs)
        tmp.replace(self.path)


def cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    return (matrix @ query) / np.where(norms == 0, 1.0, norms)


def should_skip(prompt: str, previous: str, min_chars: int) -> bool:
    text = prompt.strip()
    return len(text) < min_chars or text.startswith("/") or text == previous.strip()


def short_key(item: Item) -> str:
    """Compact option key (Laya renders 'key: label' in a small head budget)."""
    return item.id.rsplit("__", 1)[-1].rsplit(":", 1)[-1] or item.id


def option_keys(pool: Sequence[Item]) -> dict[str, Item]:
    """Unique short keys for one question's options; NONE_ID stays reserved."""
    keyed: dict[str, Item] = {}
    for item in pool:
        base = key = short_key(item)
        suffix = 2
        while key in keyed or key == NONE_ID:
            key, suffix = f"{base}-{suffix}", suffix + 1
        keyed[key] = item
    return keyed


def build_questions(keyed: Mapping[str, Mapping[str, Item]]) -> dict:
    return {kind: {"type": "choice", "instructions": QUESTIONS[kind],
                   "criteria": {**{key: item.label for key, item in options.items()}, NONE_ID: NONE_LABEL}}
            for kind, options in keyed.items()}


def translate(answer: Mapping, keyed: Mapping[str, Item]) -> list[tuple[str, float]]:
    """Option-key probabilities -> (item id or NONE_ID, p), best first."""
    probs = answer.get("probabilities", {})
    pairs = [(keyed[key].id if key in keyed else NONE_ID, float(p))
             for key, p in probs.items() if key in keyed or key == NONE_ID]
    return sorted(pairs, key=lambda pair: -pair[1])


class Engine:
    """Stateless apart from the embedding cache and the last prompt (for repeat-skipping)."""

    def __init__(self, scorer: Scorer, cfg: EngineConfig | None = None, cache: EmbeddingCache | None = None) -> None:
        self.scorer = scorer
        self.cfg = cfg or EngineConfig()
        self.cache = cache or EmbeddingCache()
        self.overflows = 0
        self._previous = ""

    def rank(self, prompt: str, items: Sequence[Item]) -> Ranking:
        """Thresholded, capped candidates; empty when skipped or nothing clears tau."""
        started = time.perf_counter()
        ranking = Ranking(model=self.scorer.model)
        if should_skip(prompt, self._previous, self.cfg.min_prompt_chars):
            return ranking
        self._previous = prompt
        for kind, scored in self.scores(prompt, items).items():
            by_id = {item.id: item for item in items if item.kind == kind}
            setattr(ranking, PLURAL[kind], self._select(kind, scored, by_id))
        ranking.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return ranking

    def scores(self, prompt: str, items: Sequence[Item]) -> Scores:
        """Per kind: (item id or NONE_ID, probability), best first. No thresholds, no skipping."""
        text = prompt.strip()[:MAX_PROMPT_CHARS]
        pools = {kind: [item for item in items if item.kind == kind] for kind in KINDS}
        pools = {kind: pool for kind, pool in pools.items() if pool}
        if not pools:
            return {}
        query = np.asarray(self.scorer.embed([text]), dtype=np.float32)[0]
        keyed = {kind: option_keys(self._shortlist(query, pool, self.cfg.k[kind])) for kind, pool in pools.items()}
        answers, keyed = self._choose(text, keyed)
        return {kind: translate(answers[kind], keyed[kind]) for kind in keyed if kind in answers}

    def _shortlist(self, query: np.ndarray, pool: list[Item], k: int) -> list[Item]:
        if len(pool) <= k:
            return pool
        sims = cosine(query, self.cache.vectors(pool, self.scorer.embed))
        return [pool[int(i)] for i in np.argsort(-sims, kind="stable")[:k]]

    def _choose(self, text: str, keyed: dict[str, dict[str, Item]]) -> tuple[dict, dict[str, dict[str, Item]]]:
        """One predict call; halve option lists while they overflow Laya's head budget."""
        for _ in range(3):
            try:
                return self.scorer.choose({"request": text}, build_questions(keyed)), keyed
            except ValueError as exc:
                if "head_max_len" not in str(exc):
                    raise
                self.overflows += 1
                log.info("choice options exceed head budget; halving shortlists")
                keyed = {kind: dict(list(opts.items())[: max(1, len(opts) // 2)]) for kind, opts in keyed.items()}
        return {}, keyed

    def _select(self, kind: str, scored: list[tuple[str, float]], by_id: Mapping[str, Item]) -> list[Candidate]:
        if not scored or scored[0][0] == NONE_ID:
            return []
        keep = [(item_id, p) for item_id, p in scored if item_id in by_id and p >= self.cfg.tau[kind]]
        return [Candidate(item_id, by_id[item_id].label, round(p, 2), by_id[item_id].connector)
                for item_id, p in keep[: self.cfg.cap[kind]]]
```

- [ ] **Step 5: Run and confirm they pass**

Run: `uv run pytest -v`
Expected: all pass, 16 new.

- [ ] **Step 6: Commit**

```bash
git add src/laya_router/engine.py tests/fakes.py tests/test_engine.py
git commit -m "feat: add ranking engine with shortlist, abstain option and caches

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 8: Hint formatting and the Laya scorer

**Files:**
- Modify: `src/laya_router/engine.py` (append `PREFIX`, `MAX_HINT_CHARS`, `format_hint`)
- Create: `src/laya_router/scorer.py`, `tests/test_hint.py`, `tests/test_scorer_slow.py`

**Interfaces:**
- Consumes: `Ranking`, `Candidate`; `laya.Router`, `laya.shortlist.embed_fn_from_agent`.
- Produces:
  - `engine.PREFIX = "[laya-router] advisory, ignore if irrelevant — "`;
  - `engine.format_hint(ranking, max_chars=400) -> str`;
  - `scorer.LayaScorer(model="typed-decisions", device=None)`, which implements `Scorer`. This is the only module that imports torch or laya.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hint.py
from laya_router.engine import PREFIX, format_hint
from laya_router.items import Candidate, Ranking


def test_empty_ranking_formats_to_empty_string():
    assert format_hint(Ranking()) == ""


def test_hint_groups_tools_under_connectors():
    ranking = Ranking(
        skills=[Candidate("superpowers:systematic-debugging", "Use when...", 0.62)],
        connectors=[Candidate("Gmail", "Gmail tools", 0.71)],
        tools=[Candidate("mcp__claude_ai_Gmail__search_threads", "Gmail: Search", 0.55, "Gmail"),
               Candidate("mcp__context7__query-docs", "context7: Query", 0.4, "context7")])
    assert format_hint(ranking) == (
        PREFIX + "skills: superpowers:systematic-debugging (0.62) · "
        "connectors: Gmail (0.71) → mcp__claude_ai_Gmail__search_threads · "
        "tools: mcp__context7__query-docs (0.40)")


def test_hint_is_capped():
    hint = format_hint(Ranking(skills=[Candidate("s" * 300, "x", 0.9), Candidate("t" * 300, "y", 0.5)]))
    assert len(hint) == 400 and hint.endswith("…")
```

```python
# tests/test_scorer_slow.py
import pytest

from laya_router.engine import NONE_ID, Engine
from laya_router.items import Item

pytestmark = pytest.mark.slow

ITEMS = [
    Item("skill", "superpowers:systematic-debugging", "Use when encountering any bug or test failure",
         "Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes"),
    Item("skill", "anthropic-skills:pptx", "Create or edit PowerPoint slide decks",
         "Use this skill any time a .pptx file is involved: decks, slides, presentations"),
    Item("skill", "anthropic-skills:xlsx", "Work with spreadsheet files",
         "Use this skill any time a spreadsheet file is the primary input or output"),
]


def test_laya_scorer_returns_a_distribution_over_options():
    from laya_router.scorer import LayaScorer

    scores = Engine(LayaScorer()).scores("my pytest suite fails with a KeyError after the refactor", ITEMS)
    assert {item_id for item_id, _ in scores["skill"]} == {i.id for i in ITEMS} | {NONE_ID}
    assert abs(sum(p for _, p in scores["skill"]) - 1.0) < 0.02
```

- [ ] **Step 2: Run and confirm they fail**

Run: `uv run pytest tests/test_hint.py -v`
Expected: FAIL with `ImportError: cannot import name 'PREFIX'`

- [ ] **Step 3: Append to `src/laya_router/engine.py`**

```python
PREFIX = "[laya-router] advisory, ignore if irrelevant — "
MAX_HINT_CHARS = 400


def format_hint(ranking: Ranking, max_chars: int = MAX_HINT_CHARS) -> str:
    """One advisory line; tools are grouped under their connector when it was also picked."""
    if ranking.is_empty():
        return ""
    parts = []
    if ranking.skills:
        parts.append("skills: " + ", ".join(f"{c.id} ({c.p:.2f})" for c in ranking.skills))
    grouped: dict[str, list[Candidate]] = {c.id: [] for c in ranking.connectors}
    loose = []
    for tool in ranking.tools:
        (grouped[tool.connector] if tool.connector in grouped else loose).append(tool)
    if ranking.connectors:
        parts.append("connectors: " + ", ".join(_connector_text(c, grouped[c.id]) for c in ranking.connectors))
    if loose:
        parts.append("tools: " + ", ".join(f"{t.id} ({t.p:.2f})" for t in loose))
    line = PREFIX + " · ".join(parts)
    return line if len(line) <= max_chars else line[: max_chars - 1] + "…"


def _connector_text(connector: Candidate, tools: list[Candidate]) -> str:
    base = f"{connector.id} ({connector.p:.2f})"
    return base + (" → " + ", ".join(tool.id for tool in tools) if tools else "")
```

- [ ] **Step 4: Write `src/laya_router/scorer.py`**

```python
"""Laya adapter: the only module that imports laya (and so torch)."""
from __future__ import annotations

import threading
from collections.abc import Sequence

import numpy as np


class LayaScorer:
    """Warm Laya checkpoint: encoder embeddings for shortlisting plus typed choice answers."""

    def __init__(self, model: str = "typed-decisions", device: str | None = None) -> None:
        from laya import Router
        from laya.shortlist import embed_fn_from_agent

        self.model = model
        self._router = Router(device=device)
        self._router.preload([model])
        self._embed = embed_fn_from_agent(self._router.load(model))
        self._lock = threading.Lock()  # one forward pass at a time, as laya.serve does

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        with self._lock:
            return self._embed(list(texts))

    def choose(self, state: dict, questions: dict) -> dict:
        with self._lock:
            return self._router.predict(state, questions, model=self.model)["answers"]
```

If Task 3 found that `device=None` does **not** pick CUDA, add `import torch` at the top of `__init__` and change the line to `self._router = Router(device=device or ("cuda" if torch.cuda.is_available() else "cpu"))`. Note the change in FINDINGS.

- [ ] **Step 5: Run the fast suite, then the slow test**

Run: `uv run pytest -v && uv run pytest -m slow -v`
Expected: all fast tests pass. The slow test passes (the checkpoint is already cached from Task 3).

- [ ] **Step 6: Commit**

```bash
git add src/laya_router/engine.py src/laya_router/scorer.py tests/test_hint.py tests/test_scorer_slow.py
git commit -m "feat: format advisory hints and add warm Laya scorer

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 9: Eval dataset from transcripts

**Files:**
- Create: `src/laya_router/dataset.py`, `tests/test_dataset.py`

**Interfaces:**
- Consumes: `catalog.connector_of`.
- Produces:
  - `read_jsonl(path) -> Iterator[dict]`, which skips bad lines;
  - `write_jsonl(path, rows)`;
  - `prompt_text(entry) -> str | None`;
  - `tool_uses(entry) -> list[dict]`;
  - `label_turn(uses) -> dict`;
  - `rows_from_transcript(path, harness) -> Iterator[dict]`;
  - `transcript_files(home) -> Iterator[tuple[Path, str]]`;
  - `build(home, out_dir) -> {"labeled": int, "negatives": int}`;
  - `main(argv) -> int`.

  Rows have the form `{"prompt", "harness", "gold": {"skill"?, "tool"?, "connector"?}, "source": "transcript" | "transcript-none", "file"}`. The outputs are `eval/data/transcripts.jsonl` and `eval/data/negatives.jsonl`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dataset.py
import json

from laya_router.dataset import build, prompt_text, rows_from_transcript


def user(content, **extra):
    return {"type": "user", "message": {"role": "user", "content": content}, **extra}


def tool_result():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}


def assistant(*uses, **extra):
    blocks = [{"type": "tool_use", "name": name, "input": data} for name, data in uses]
    return {"type": "assistant", "message": {"content": blocks}, **extra}


def write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\nnot json\n", encoding="utf-8")


def test_prompt_text_filters_non_prompts():
    assert prompt_text(user("hello there")) == "hello there"
    assert prompt_text(tool_result()) is None
    assert prompt_text(user("x", isMeta=True)) is None
    assert prompt_text(user("x", isSidechain=True)) is None
    assert prompt_text(user("<command-name>/compact</command-name>")) is None
    assert prompt_text(user("<ide_opened_file>a.py</ide_opened_file> fix the bug")) == "fix the bug"
    assert prompt_text(user([{"type": "text", "text": "list form"}])) == "list form"


def test_rows_label_first_skill_and_mcp_tool(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, [
        user("plan the new feature"),
        assistant(("Skill", {"skill": "superpowers:brainstorming"}), ("Skill", {"skill": "other"})),
        tool_result(),
        assistant(("mcp__claude_ai_Gmail__search_threads", {"q": "x"})),
        assistant(("mcp__context7__query-docs", {}), isSidechain=True),
        user("thanks, now explain it"),
    ])
    rows = list(rows_from_transcript(path, "claude-code"))
    assert rows[0]["gold"] == {"skill": "superpowers:brainstorming",
                               "tool": "mcp__claude_ai_Gmail__search_threads", "connector": "Gmail"}
    assert rows[1]["gold"] == {} and rows[1]["source"] == "transcript-none"


def test_build_dedupes_and_splits(tmp_path):
    entries = [user("plan the new feature"), assistant(("Skill", {"skill": "superpowers:brainstorming"})),
               user("small talk only")]
    write(tmp_path / ".claude" / "projects" / "-p1" / "a.jsonl", entries)
    write(tmp_path / ".claude" / "projects" / "-p2" / "b.jsonl", entries)
    assert build(tmp_path, tmp_path / "out") == {"labeled": 1, "negatives": 1}
    rows = [json.loads(line) for line in (tmp_path / "out" / "transcripts.jsonl").read_text().splitlines()]
    assert rows[0]["harness"] == "claude-code"
```

- [ ] **Step 2: Run and confirm they fail**

Run: `uv run pytest tests/test_dataset.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.dataset'`

- [ ] **Step 3: Write `src/laya_router/dataset.py`**

```python
"""Turn Claude Code / Cowork transcripts into routing eval rows (local, private data)."""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path

from .catalog import COWORK_ROOT, connector_of

TAG_BLOCK = re.compile(r"<([a-zA-Z_-]+)>.*?</\1>", re.DOTALL)
MAX_PROMPT = 2000


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
    """Text of a real user prompt; None for tool results, meta, sidechain and slash-command entries."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content):
            return None
        content = " ".join(block.get("text", "") for block in content
                           if isinstance(block, dict) and block.get("type") == "text")
    if not isinstance(content, str) or "<command-name>" in content:
        return None
    return TAG_BLOCK.sub(" ", content).strip()[:MAX_PROMPT] or None


def tool_uses(entry: dict) -> list[dict]:
    if entry.get("type") != "assistant" or entry.get("isSidechain"):
        return []
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]


def label_turn(uses: list[dict]) -> dict:
    """First Skill invocation and first MCP tool call of a turn."""
    gold: dict[str, str] = {}
    for use in uses:
        name, data = use.get("name", ""), use.get("input") or {}
        if name == "Skill" and "skill" not in gold and isinstance(data, dict) and data.get("skill"):
            gold["skill"] = str(data["skill"])
        elif name.startswith("mcp__") and "tool" not in gold:
            gold["tool"] = name
            connector = connector_of(name)
            if connector:
                gold["connector"] = connector
    return gold


def rows_from_transcript(path: Path, harness: str) -> Iterator[dict]:
    prompt, uses = None, []
    for entry in read_jsonl(path):
        text = prompt_text(entry)
        if text is None:
            uses += tool_uses(entry)
            continue
        if prompt:
            yield make_row(prompt, uses, harness, path)
        prompt, uses = text, []
    if prompt:
        yield make_row(prompt, uses, harness, path)


def make_row(prompt: str, uses: list[dict], harness: str, path: Path) -> dict:
    gold = label_turn(uses)
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
    parser = argparse.ArgumentParser(prog="laya-router eval build")
    parser.add_argument("--out", default="eval/data")
    args = parser.parse_args(argv)
    print(json.dumps(build(Path.home(), Path(args.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run and confirm they pass**

Run: `uv run pytest -v`
Expected: all pass, 3 new.

- [ ] **Step 5: Build the real dataset** (private and local; `eval/data/` is gitignored)

Run: `uv run python -m laya_router.dataset && wc -l eval/data/*.jsonl`
Expected: JSON counts. Earlier sampling suggests about 40 or more skill labels and several hundred MCP-labeled turns, mostly Playwright. Note the counts for the gate report.

- [ ] **Step 6: Commit**

```bash
git add src/laya_router/dataset.py tests/test_dataset.py
git commit -m "feat: build routing eval rows from local transcripts

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 10: Synthetic dev prompts (content task)

**Files:**
- Create: `eval/synthetic.jsonl` (tracked; it holds no private data), `eval/check_synthetic.py`
- Side effects: writes `~/.cache/laya-router/mcp-tools.json` (Step 1) and `eval/data/catalog-summary.json` (gitignored)

**Interfaces:**
- Consumes: `catalog.harness_catalogs()`, `toolcache.configured_servers`, `toolcache.refresh`.
- Produces: `eval/synthetic.jsonl` rows `{"prompt", "harness", "gold", "source": "synthetic" | "synthetic-pt"}`, which are the dev set for Task 11.

- [ ] **Step 1: Snapshot local MCP tools.** This briefly starts each of the user's configured stdio servers, with a 30 s timeout each. Servers that need auth are skipped.

Run: `uv run python -c "import anyio; from pathlib import Path; from laya_router import toolcache, catalog; s = anyio.run(toolcache.refresh, toolcache.configured_servers(Path.home(), None), Path.home() / catalog.TOOL_CACHE); print([x['name'] for x in s['servers']])"`
Expected: a list of the reachable server names, for example `context7`, `playwright`, `chrome-devtools`, `serena`.

- [ ] **Step 2: Dump the catalog summary to write from**

Run: `uv run python -c "import json; from laya_router.catalog import harness_catalogs; print(json.dumps({h: [[i.kind, i.id, i.label] for i in items if i.kind != 'tool'] for h, items in harness_catalogs().items()}, indent=0))" > eval/data/catalog-summary.json && wc -c eval/data/catalog-summary.json`

- [ ] **Step 3: Write `eval/synthetic.jsonl`**, one JSON object per line.
  - **Claude Code skills and commands:** for every one in `catalog-summary.json["claude-code"]`, write 2 prompts in the user's voice (a developer, terse). Each gets `gold: {"skill": "<id>"}`.
  - **Claude Code connectors:** 2 prompts each, with `gold: {"connector": "<name>"}`. Add `"tool": "<exact tool id>"` when one tool is obviously the first call.
  - **Cowork:** 1 prompt for each skill and connector, with `"harness": "cowork"` and the Cowork ids.
  - **Portuguese:** at least 10 prompts across common skills and connectors, with `"source": "synthetic-pt"`. All other rows use `"source": "synthetic"`.
  - Paraphrase: use concrete situations, not the description's wording.

  Example lines:

```json
{"prompt": "my pytest suite started failing with a KeyError after yesterday's refactor, figure out why", "harness": "claude-code", "gold": {"skill": "superpowers:systematic-debugging"}, "source": "synthetic"}
{"prompt": "find the thread where Ana sent the signed contract last week", "harness": "claude-code", "gold": {"connector": "Gmail", "tool": "mcp__claude_ai_Gmail__search_threads"}, "source": "synthetic"}
{"prompt": "faz-me uma apresentação de 5 slides sobre os resultados do trimestre", "harness": "claude-code", "gold": {"skill": "anthropic-skills:pptx"}, "source": "synthetic-pt"}
```

- [ ] **Step 4: Write and run the validator**

```python
# eval/check_synthetic.py
"""Validate eval/synthetic.jsonl against the live catalog (Phase 0 helper)."""
import collections
import json
import sys
from pathlib import Path

from laya_router.catalog import harness_catalogs

rows = [json.loads(line) for line in Path("eval/synthetic.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
catalogs = harness_catalogs()
known = {h: {(i.kind, i.id) for i in items} for h, items in catalogs.items()}
unknown = [r for r in rows for kind, value in r["gold"].items() if (kind, value) not in known.get(r["harness"], set())]
counts = collections.Counter((r["harness"], kind, value) for r in rows for kind, value in r["gold"].items() if kind != "tool")
needed = {("claude-code", i.kind, i.id) for i in catalogs["claude-code"] if i.kind != "tool"}
thin = sorted(key for key in needed if counts[key] < 2)
portuguese = sum(1 for r in rows if r["source"] == "synthetic-pt")
print(f"rows={len(rows)} unknown_gold={len(unknown)} under_2={len(thin)} portuguese={portuguese}")
for row in unknown[:10]:
    print("unknown:", row["gold"])
for key in thin[:10]:
    print("thin:", key)
sys.exit(1 if unknown or thin or portuguese < 10 else 0)
```

Run: `uv run python eval/check_synthetic.py`
Expected: `unknown_gold=0 under_2=0 portuguese>=10`, exit code 0. Fix the rows it reports and rerun.

- [ ] **Step 5: Commit**

```bash
git add eval/synthetic.jsonl eval/check_synthetic.py
git commit -m "test: add synthetic routing dev set incl. Portuguese prompts

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 11: Eval runner (BM25 vs cosine vs Laya), with calibration and gate lines

**Files:**
- Create: `src/laya_router/evaluate.py`, `tests/test_evaluate.py`

**Interfaces:**
- Consumes:
  - `catalog.harness_catalogs`;
  - `dataset.read_jsonl`;
  - `engine.NONE_ID`, `EmbeddingCache`, `Engine`, `EngineConfig`, `cosine`;
  - `scorer.LayaScorer`, imported lazily;
  - `items.KINDS`, `Item`.
- Produces:
  - `BM25(docs).scores(query) -> list[float]`;
  - `evaluate(rows, known, rankers) -> {"kinds": {kind: {n, top1, top3, unknown, none_first}}, "p50_ms", "p95_ms"}`;
  - `calibrate(rows, kind, scored, taus) -> list[{tau, precision, recall}]`;
  - `pick_tau(table, min_precision=0.75) -> float`;
  - `none_rate(rows, rankers) -> float`;
  - `gate_lines(results, device) -> list[str]`;
  - `main(argv) -> int`, which writes `eval/results/report-<device>.md` and `raw-<device>.json`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evaluate.py
from laya_router.engine import NONE_ID
from laya_router.evaluate import BM25, calibrate, evaluate, gate_lines, none_rate, pick_tau

KNOWN = {"claude-code": {"skill": {"x", "y", "z", "w"}, "connector": set(), "tool": set()}}


def test_bm25_prefers_matching_doc():
    scores = BM25(["send email drafts", "debug failing tests", "make slides"]).scores("my tests are failing")
    assert scores.index(max(scores)) == 1


def test_evaluate_counts_top1_top3_and_skips_unknown_gold():
    rows = [{"prompt": p, "harness": "claude-code", "gold": {"skill": g}} for p, g in (("a", "x"), ("b", "y"), ("c", "gone"))]
    ranked = {"a": {"skill": ["x", "y", "z"]}, "b": {"skill": [NONE_ID, "z", "w", "y"]}, "c": {"skill": ["x"]}}
    result = evaluate(rows, KNOWN, {"claude-code": lambda prompt: ranked[prompt]})
    assert result["kinds"]["skill"] == {"n": 2, "top1": 0.5, "top3": 1.0, "unknown": 1, "none_first": 1}


def test_calibrate_treats_none_first_as_abstain():
    rows = [{"prompt": p, "harness": "claude-code", "gold": {"skill": "x"}} for p in ("a", "b", "c")]
    scored = {"a": {"skill": [("x", 0.8)]}, "b": {"skill": [("y", 0.6)]}, "c": {"skill": [(NONE_ID, 0.9)]}}
    assert calibrate(rows, "skill", scored, taus=(0.5, 0.7)) == [
        {"tau": 0.5, "precision": 0.5, "recall": 0.333}, {"tau": 0.7, "precision": 1.0, "recall": 0.333}]


def test_pick_tau_prefers_smallest_tau_meeting_precision_else_best_f1():
    table = [{"tau": 0.2, "precision": 0.6, "recall": 0.9}, {"tau": 0.3, "precision": 0.8, "recall": 0.7}]
    assert pick_tau(table, 0.75) == 0.3
    assert pick_tau([{"tau": 0.2, "precision": 0.5, "recall": 0.9}, {"tau": 0.3, "precision": 0.6, "recall": 0.2}], 0.75) == 0.2


def test_none_rate_counts_turns_where_every_kind_abstains():
    rows = [{"prompt": "a", "harness": "claude-code"}, {"prompt": "b", "harness": "claude-code"}]
    ranked = {"a": {"skill": [NONE_ID, "x"], "tool": [NONE_ID]}, "b": {"skill": ["x", NONE_ID]}}
    assert none_rate(rows, {"claude-code": lambda prompt: ranked[prompt]}) == 0.5


def test_gate_lines_compare_best_laya_with_bm25():
    def result(top3: float, p95: float) -> dict:
        return {"test": {"kinds": {"skill": {"top3": top3}}, "p95_ms": p95}}

    lines = gate_lines({"bm25": result(0.5, 1.0), "laya-typed-decisions-k10": result(0.75, 120.0)}, "cuda")
    assert "top-3 skill recall 0.75 >= 0.70: PASS" in lines[3]
    assert "PASS" in lines[4] and "PASS" in lines[5]
```

- [ ] **Step 2: Run and confirm they fail**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.evaluate'`

- [ ] **Step 3: Write `src/laya_router/evaluate.py`**

```python
"""Phase 0: compare routing methods on eval rows and write a markdown report."""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .catalog import harness_catalogs
from .dataset import read_jsonl
from .engine import NONE_ID, EmbeddingCache, Engine, EngineConfig, cosine
from .items import KINDS, Item

TOKEN = re.compile(r"[a-z0-9]+")
TAUS = (0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7)
CACHE_DIR = Path.home() / ".cache" / "laya-router"
RankFn = Callable[[str], dict[str, list[str]]]
Scored = dict[str, dict[str, list[tuple[str, float]]]]


@dataclass
class Inputs:
    catalogs: dict[str, list[Item]]
    known: dict[str, dict[str, set[str]]]
    test: list[dict]
    dev: list[dict]
    negatives: list[dict]


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class BM25:
    """Plain Okapi BM25 over item texts: the no-model baseline."""

    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = [Counter(tokens(doc)) for doc in docs]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths) if self.lengths else 1.0
        df = Counter(term for doc in self.docs for term in doc)
        self.idf = {term: math.log(1 + (len(self.docs) - f + 0.5) / (f + 0.5)) for term, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        terms = tokens(query)
        return [sum(self._term(doc, length, term) for term in terms) for doc, length in zip(self.docs, self.lengths)]

    def _term(self, doc: Counter, length: int, term: str) -> float:
        freq = doc.get(term, 0)
        if not freq:
            return 0.0
        norm = freq + self.k1 * (1 - self.b + self.b * length / (self.avg or 1.0))
        return self.idf[term] * freq * (self.k1 + 1) / norm


def pools(items: Sequence[Item]) -> dict[str, list[Item]]:
    grouped = {kind: [item for item in items if item.kind == kind] for kind in KINDS}
    return {kind: pool for kind, pool in grouped.items() if pool}


def order(pool: list[Item], scores: Sequence[float]) -> list[str]:
    return [pool[int(i)].id for i in np.argsort(-np.asarray(scores, dtype=np.float64), kind="stable")]


def bm25_method(items: Sequence[Item]) -> RankFn:
    grouped = pools(items)
    indexes = {kind: BM25([item.text for item in pool]) for kind, pool in grouped.items()}
    return lambda prompt: {kind: order(grouped[kind], index.scores(prompt)) for kind, index in indexes.items()}


def cosine_method(engine: Engine, items: Sequence[Item]) -> RankFn:
    grouped = pools(items)
    matrices = {kind: engine.cache.vectors(pool, engine.scorer.embed) for kind, pool in grouped.items()}

    def rank(prompt: str) -> dict[str, list[str]]:
        query = np.asarray(engine.scorer.embed([prompt]), dtype=np.float32)[0]
        return {kind: order(grouped[kind], cosine(query, matrix)) for kind, matrix in matrices.items()}

    return rank


def laya_method(engine: Engine, items: Sequence[Item], store: Scored) -> RankFn:
    def rank(prompt: str) -> dict[str, list[str]]:
        store[prompt] = engine.scores(prompt, items)
        return {kind: [item_id for item_id, _ in ranked] for kind, ranked in store[prompt].items()}

    return rank


def evaluate(rows: list[dict], known: dict[str, dict[str, set[str]]], rankers: dict[str, RankFn]) -> dict:
    """top-1/top-3 per kind (ignoring 'none'), none-first counts and latency percentiles."""
    tally = {kind: Counter() for kind in KINDS}
    latencies: list[float] = []
    for row in rows:
        rank_fn = rankers.get(row["harness"])
        if rank_fn is None:
            continue
        started = time.perf_counter()
        ranked = rank_fn(row["prompt"])
        latencies.append((time.perf_counter() - started) * 1000)
        for kind, gold in row["gold"].items():
            score_row(tally[kind], gold, ranked.get(kind, []), known[row["harness"]].get(kind, set()))
    return {"kinds": {kind: summarize(counts) for kind, counts in tally.items()}, **percentiles(latencies)}


def score_row(counts: Counter, gold: str, ranked: list[str], known: set[str]) -> None:
    if gold not in known:
        counts["unknown"] += 1
        return
    ids = [item_id for item_id in ranked if item_id != NONE_ID]
    counts["n"] += 1
    counts["top1"] += ids[:1] == [gold]
    counts["top3"] += gold in ids[:3]
    counts["none_first"] += bool(ranked) and ranked[0] == NONE_ID


def summarize(counts: Counter) -> dict:
    n = counts["n"]
    return {"n": n, "top1": round(counts["top1"] / n, 3) if n else 0.0, "top3": round(counts["top3"] / n, 3) if n else 0.0,
            "unknown": counts["unknown"], "none_first": counts["none_first"]}


def percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50_ms": 0.0, "p95_ms": 0.0}
    ordered = sorted(samples)
    return {"p50_ms": round(statistics.median(ordered), 1), "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 1)}


def none_rate(rows: list[dict], rankers: dict[str, RankFn]) -> float:
    """Share of unlabeled turns where every kind ranks 'none' first (the router stays silent)."""
    silent = total = 0
    for row in rows:
        rank_fn = rankers.get(row["harness"])
        if rank_fn is None:
            continue
        ranked = rank_fn(row["prompt"])
        total += 1
        silent += all(ids and ids[0] == NONE_ID for ids in ranked.values())
    return round(silent / total, 3) if total else 0.0


def calibrate(rows: list[dict], kind: str, scored: Scored, taus: Sequence[float] = TAUS) -> list[dict]:
    """Precision/recall of 'top candidate is gold and p >= tau'; 'none' first means abstain."""
    labeled = [row for row in rows if row["gold"].get(kind) and row["prompt"] in scored]
    table = []
    for tau in taus:
        predicted = correct = 0
        for row in labeled:
            ranked = scored[row["prompt"]].get(kind, [])
            if not ranked or ranked[0][0] == NONE_ID or ranked[0][1] < tau:
                continue
            predicted += 1
            correct += ranked[0][0] == row["gold"][kind]
        table.append({"tau": tau, "precision": round(correct / predicted, 3) if predicted else 0.0,
                      "recall": round(correct / len(labeled), 3) if labeled else 0.0})
    return table


def pick_tau(table: list[dict], min_precision: float = 0.75) -> float:
    """Smallest tau reaching min_precision; otherwise the tau with the best F1."""
    for row in table:
        if row["precision"] >= min_precision:
            return row["tau"]

    def f1(row: dict) -> float:
        total = row["precision"] + row["recall"]
        return 2 * row["precision"] * row["recall"] / total if total else 0.0

    return max(table, key=f1)["tau"]


def vram_mb() -> int:
    import torch

    return round(torch.cuda.max_memory_allocated() / 2**20) if torch.cuda.is_available() else 0


def run_model(model: str, device: str, ks: Sequence[int], data: Inputs) -> dict:
    """cosine-only plus shortlist→choice at each K, for one checkpoint."""
    from .scorer import LayaScorer

    scorer = LayaScorer(model=model, device=None if device == "auto" else device)
    cache = EmbeddingCache(CACHE_DIR / f"emb-{model}.npz")
    base = Engine(scorer, EngineConfig(), cache)
    out = {f"cosine-{model}": {"test": evaluate(data.test, data.known,
                                                {h: cosine_method(base, i) for h, i in data.catalogs.items()})}}
    for k in ks:
        engine = Engine(scorer, EngineConfig(k={"skill": k, "connector": 15, "tool": k}), cache)
        store: Scored = {}
        rankers = {h: laya_method(engine, i, store) for h, i in data.catalogs.items()}
        pt_rows = [row for row in data.dev if row.get("source") == "synthetic-pt"]
        out[f"laya-{model}-k{k}"] = {
            "test": evaluate(data.test, data.known, rankers), "dev": evaluate(data.dev, data.known, rankers),
            "dev_pt": evaluate(pt_rows, data.known, rankers), "silent_on_unlabeled": none_rate(data.negatives, rankers),
            "calibration": {kind: calibrate(data.dev, kind, store) for kind in KINDS},
            "overflows": engine.overflows, "vram_mb": vram_mb()}
    return out


def table_rows(split: str, result: dict) -> list[str]:
    return [f"| {split} | {kind} | {m['n']} | {m['top1']} | {m['top3']} | {m['none_first']} | {m['unknown']} "
            f"| {result['p50_ms']} | {result['p95_ms']} |" for kind, m in result["kinds"].items()]


def extra_lines(sets: dict) -> list[str]:
    lines = [""]
    if "silent_on_unlabeled" in sets:
        lines.append(f"Silent on unlabeled turns: {sets['silent_on_unlabeled']} · head overflows: "
                     f"{sets['overflows']} · VRAM MB: {sets['vram_mb']}")
    for kind, table in sets.get("calibration", {}).items():
        cells = ", ".join(f"τ={row['tau']} P={row['precision']} R={row['recall']}" for row in table)
        lines.append(f"Calibration {kind}: {cells} → pick τ={pick_tau(table)}")
    return lines + [""]


def gate_lines(results: dict, device: str) -> list[str]:
    laya = {name: r for name, r in results.items() if name.startswith("laya-")}
    if not laya:
        return ["## Gate", "", "No Laya results."]
    bm25 = results["bm25"]["test"]["kinds"]["skill"]["top3"]
    name, best = max(laya.items(), key=lambda kv: kv[1]["test"]["kinds"]["skill"]["top3"])
    top3, p95 = best["test"]["kinds"]["skill"]["top3"], best["test"]["p95_ms"]
    latency = "n/a on CPU" if device == "cpu" else ("PASS" if p95 <= 250 else "FAIL")
    return ["## Gate", "", f"Best: {name}",
            f"- top-3 skill recall {top3} >= 0.70: {'PASS' if top3 >= 0.70 else 'FAIL'}",
            f"- beats BM25 ({bm25}) by >= 0.10: {'PASS' if top3 - bm25 >= 0.10 else 'FAIL'}",
            f"- p95 {p95} ms <= 250 on GPU: {latency}",
            "- hook injects context in Claude Code CLI: see spike/FINDINGS.md"]


def render(results: dict, device: str) -> str:
    lines = [f"# Phase 0 routing eval ({device})", ""]
    for method, sets in results.items():
        lines += [f"## {method}", "", "| split | kind | n | top1 | top3 | none_first | unknown | p50 ms | p95 ms |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for split in ("test", "dev", "dev_pt"):
            if split in sets:
                lines += table_rows(split, sets[split])
        lines += extra_lines(sets)
    return "\n".join(lines + gate_lines(results, device))


def load_inputs(args: argparse.Namespace) -> Inputs:
    limit = args.limit or None
    catalogs = harness_catalogs()
    known = {h: {kind: {i.id for i in items if i.kind == kind} for kind in KINDS} for h, items in catalogs.items()}
    data_dir = Path(args.data)
    return Inputs(catalogs, known, list(read_jsonl(data_dir / "transcripts.jsonl"))[:limit],
                  list(read_jsonl(Path(args.synthetic)))[:limit],
                  list(read_jsonl(data_dir / "negatives.jsonl"))[: args.negatives])


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="laya-router eval run")
    parser.add_argument("--data", default="eval/data")
    parser.add_argument("--synthetic", default="eval/synthetic.jsonl")
    parser.add_argument("--out", default="eval/results")
    parser.add_argument("--device", default="auto", help="auto | cuda | cpu")
    parser.add_argument("--models", nargs="+", default=["typed-decisions", "english"])
    parser.add_argument("--ks", nargs="+", type=int, default=[5, 10, 15])
    parser.add_argument("--negatives", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0, help="cap test/dev rows (0 = all), for quick CPU runs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    data = load_inputs(args)
    bm25 = {h: bm25_method(items) for h, items in data.catalogs.items()}
    results = {"bm25": {"test": evaluate(data.test, data.known, bm25), "dev": evaluate(data.dev, data.known, bm25)}}
    for model in args.models:
        results.update(run_model(model, args.device, args.ks, data))
    report = render(results, args.device)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"report-{args.device}.md").write_text(report, encoding="utf-8")
    (out / f"raw-{args.device}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run and confirm they pass**

Run: `uv run pytest -v`
Expected: all pass, 6 new.

- [ ] **Step 5: Commit**

```bash
git add src/laya_router/evaluate.py tests/test_evaluate.py
git commit -m "feat: add phase 0 eval runner with baselines, calibration and gate

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 12: GATE — run the eval and stop for the user's go/no-go

**Files:**
- Modify: `tasks/todo.md` (§ Review), `spike/FINDINGS.md` (add a gate summary)

- [ ] **Step 1: Full GPU run** (the first run also downloads the `english` checkpoint, about 846 MB)

Run: `uv run python -m laya_router.evaluate --device cuda`
Expected: `eval/results/report-cuda.md` exists and ends with a `## Gate` section of PASS/FAIL lines.

- [ ] **Step 2: CPU latency sample**

Run: `uv run python -m laya_router.evaluate --device cpu --models typed-decisions --ks 10 --limit 60`
Expected: `eval/results/report-cpu.md` exists. Record p50/p95. Latency is informational only (the gate uses the GPU numbers).

- [ ] **Step 3: Write the gate summary** into `spike/FINDINGS.md` and the `tasks/todo.md` Review section. Include:
  - best method and K;
  - top-3 and top-1 per kind on the test set against BM25;
  - `dev_pt` accuracy;
  - picked τ per kind;
  - silent rate on unlabeled turns;
  - GPU and CPU p95;
  - VRAM;
  - head overflows;
  - the hook verdict from Task 2.

- [ ] **Step 4: STOP.** Show the user the gate lines and summary, and ask:
  - **all PASS:** "proceed to Phase 1 with τ=<picked> and K=<best>?"
  - **any FAIL:** list the options (fine-tune Laya on eval data, cosine only, or switch the hook to approach C) and do not start Task 13.

  If the user proceeds, set `DEFAULT_K` and `DEFAULT_TAU` in `engine.py` to the chosen values (`from_env` reads them, so it needs no change). Update the expected dicts in `tests/test_engine.py::test_config_from_env` to match, then run `uv run pytest` and commit `feat: set routing defaults from phase 0 calibration`.

#### Gate amendment: user decision on 2026-09-25 (hybrid, approach A)

The gate failed as planned; see `spike/FINDINGS.md` § Gate. The user chose the fix that was measured there:
- A BM25 shortlist over each item's short name, connector and description replaces the encoder-cosine shortlist. Laya `typed-decisions` still makes the choice.
- The embedding cache goes away.
- The skill criterion is measured on the synthetic dev set. Most real skill labels are workflow continuations that no prompt-only router can see.

Steps 5–10 run before Step 4's defaults commit.

**Files (amendment):**
- Create: `src/laya_router/bm25.py`, `tests/test_bm25.py`
- Modify: `src/laya_router/engine.py`, `src/laya_router/scorer.py`, `src/laya_router/evaluate.py`, `tests/fakes.py`, `tests/test_engine.py`, `tests/test_evaluate.py`

**Interfaces (amendment):**
- Produces:
  - `bm25.tokens(text) -> list[str]` and `bm25.BM25(docs, k1=1.5, b=0.75).scores(query) -> list[float]`, moved unchanged from `evaluate.py`;
  - `engine.doc_text(item) -> str`, which returns `f"{short_key(item)} {item.connector or ''} {item.text}"` and is used by both the shortlist and the BM25 baseline;
  - the `engine.Scorer` protocol, reduced to `.model` and `.choose(state, questions)`;
  - `engine.Engine(scorer, cfg=None)`, which no longer takes a `cache` argument.
- Removed: `EmbeddingCache`, `digest`, `cosine`, `Scorer.embed`, `LayaScorer.embed`, `evaluate.cosine_method`, `evaluate.CACHE_DIR` and `~/.cache/laya-router/emb-<model>.npz`.
- Later tasks (their text below is already updated):
  - Task 13 `default_engine` returns `Engine(scorer, EngineConfig.from_env(env))`.
  - Task 14 `warmup` loads the model and prints catalog counts; it no longer pre-embeds.

- [ ] **Step 5: Write the failing tests**
  - `tests/test_bm25.py`: `test_tokens_split_on_non_alphanumerics`, `test_bm25_prefers_matching_doc` (moved from `test_evaluate.py`), and `test_bm25_scores_zero_without_overlap`.
  - `tests/test_engine.py`:
    - `test_shortlist_ranks_by_bm25_over_name_and_description`: for "turn this csv into an xlsx workbook", the K=2 criteria are `{"xlsx", "reports", "none"}`;
    - `test_tool_shortlist_matches_connector_name`: for "anything new in my gmail inbox", the K=1 tool criteria are `{"search_threads", "none"}`;
    - `test_scorer_needs_only_choose`: a scorer with only `.choose` works;
    - `test_edited_item_text_refreshes_shortlist`: a characterization test, because the old digest-keyed cache already had this property.
  - `tests/test_evaluate.py`:
    - `test_bm25_baseline_indexes_item_names`;
    - `test_gate_lines_rate_best_laya_on_dev_skills`, which replaces `test_gate_lines_compare_best_laya_with_bm25`. The best method is picked by dev skill top-3, and the lines check dev skill top-3 ≥ 0.70, beating BM25 on dev skill top-3 by ≥ 0.10, and GPU p95 ≤ 250 ms.

- [ ] **Step 6: Run and confirm they fail**

Run: `uv run pytest -q`
Expected:
- `test_bm25.py` fails with `ModuleNotFoundError: No module named 'laya_router.bm25'`.
- The shortlist, connector-name and baseline-name tests fail on the wrong items.
- `test_scorer_needs_only_choose` fails with an `AttributeError` for `embed`.
- The gate test fails with `KeyError: 'kinds'`.

- [ ] **Step 7: Implement**
  - `bm25.py` holds `TOKEN`, `tokens` and `BM25`, moved from `evaluate.py`.
  - `engine.py`:
    - add `doc_text`;
    - an `lru_cache(maxsize=16)` builds the BM25 index for a `tuple` of pool items; the items are frozen and hashable, so an edited description keys a fresh index;
    - `Engine._shortlist(text, pool, k)` returns the whole pool when `len(pool) <= k`, otherwise the top-k by BM25 score using a stable argsort;
    - `Engine.scores` no longer embeds;
    - delete the embedding code.
  - `scorer.py`: `LayaScorer` keeps `preload` and `choose`, and drops `embed_fn_from_agent`.
  - `evaluate.py`:
    - `bm25_method` indexes `doc_text`;
    - `run_model` builds `Engine(scorer, EngineConfig(k=...))` for each K;
    - `gate_lines` is re-based on dev;
    - delete the cosine method and the embedding cache.
  - `tests/fakes.py`: drop `embed` and `VOCAB`.
  - `tests/test_engine.py`: drop the three `EmbeddingCache` tests, and assert on `choose_calls` wherever `embed_calls` was used.

- [ ] **Step 8: Run the suite**

Run: `uv run pytest -q` and then `uv run pytest -m slow -q`
Expected: all pass, and the slow test passes (1).

- [ ] **Step 9: Commit** `feat: shortlist with BM25 instead of encoder cosine`

- [ ] **Step 10: Re-run the GPU eval and record it**

Run: `uv run python -m laya_router.evaluate --device cuda`
Expected: `report-cuda.md` ends with the re-based gate lines.
Then:
- Add a "Re-run" block to `spike/FINDINGS.md` § Gate and a line to `tasks/todo.md` § Review.
- Do Step 4's defaults commit with the calibrated τ (typed-decisions, K=10).

---

## Phase 1: build (only after the user passes the gate)

### Task 13: Decision log and MCP server

**Files:**
- Create: `src/laya_router/decisions.py`, `src/laya_router/server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes:
  - `catalog.discover`;
  - `engine.Engine`, `EngineConfig`, `format_hint`;
  - `scorer.LayaScorer` (lazy);
  - `items.RouteContext`, `Ranking`;
  - `mcp.server.mcpserver.MCPServer(name, instructions=, version=, lifespan=)`, `@server.tool(name=, description=)`, `server.run()`. These are verified in mcp 2.2.0, where `stdio_server` points fd 1 at stderr while serving, before the lifespan runs.
- Produces:
  - `decisions.DEFAULT_LOG`;
  - `decisions.DecisionLog(path=DEFAULT_LOG, max_bytes=10 MiB).write(ctx, ranking, catalog_size)`;
  - `server.INSTRUCTIONS`;
  - `server.RouterService(engine_factory, discover=catalog.discover, decisions=None)` with `.load()`, `.start()`, `.route(ctx) -> str`, `.ready: threading.Event`;
  - `server.build_server(service) -> MCPServer`;
  - `server.default_engine(env=os.environ) -> Engine`;
  - `server.decision_log(env=os.environ) -> DecisionLog`;
  - `server.serve()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
import json
import threading

import pytest
from fakes import FakeScorer
from mcp import Client

from laya_router.decisions import DecisionLog
from laya_router.engine import Engine
from laya_router.items import Item, Ranking, RouteContext
from laya_router.server import INSTRUCTIONS, RouterService, build_server, decision_log

ITEMS = [Item("skill", "debugging", "debug failing tests", "debug failing tests"),
         Item("skill", "slides", "make slides", "make slides")]
PROMPT = {"prompt": "please debug the failing test", "session_id": "s1"}


def text_of(result) -> str:
    return "".join(getattr(block, "text", "") for block in result.content)


def service(factory, log_path=None) -> RouterService:
    return RouterService(factory, discover=lambda ctx: ITEMS, decisions=DecisionLog(log_path))


@pytest.mark.anyio
async def test_route_tool_returns_hint_and_logs(tmp_path):
    svc = service(lambda: Engine(FakeScorer({"skill": {"debugging": 0.9}})), tmp_path / "d.jsonl")
    svc.load()
    async with Client(build_server(svc)) as client:
        result = await client.call_tool("route", PROMPT)
    assert text_of(result) == "[laya-router] advisory, ignore if irrelevant — skills: debugging (0.90)"
    record = json.loads((tmp_path / "d.jsonl").read_text().splitlines()[0])
    assert record["session"] == "s1" and record["skills"][0]["id"] == "debugging"


@pytest.mark.anyio
async def test_route_is_empty_while_model_loads():
    gate = threading.Event()

    def slow_factory():
        gate.wait(5)
        return Engine(FakeScorer())

    async with Client(build_server(service(slow_factory))) as client:
        result = await client.call_tool("route", PROMPT)
    gate.set()
    assert text_of(result) == ""


@pytest.mark.anyio
async def test_failed_load_and_route_errors_stay_silent():
    def broken():
        raise RuntimeError("no checkpoint")

    svc = service(broken)
    svc.load()
    assert svc.ready.is_set()
    async with Client(build_server(svc)) as client:
        assert text_of(await client.call_tool("route", PROMPT)) == ""
    failing = RouterService(lambda: Engine(FakeScorer()), discover=lambda ctx: 1 / 0)
    failing.load()
    assert failing.route(RouteContext("please debug the failing test")) == ""


def test_decision_log_rotates_and_can_be_disabled(tmp_path):
    path = tmp_path / "d.jsonl"
    log = DecisionLog(path, max_bytes=10)
    log.write(RouteContext("x" * 50), Ranking(), 0)
    log.write(RouteContext("x" * 50), Ranking(), 0)
    assert (tmp_path / "d.jsonl.1").exists() and len(path.read_text().splitlines()) == 1
    DecisionLog(None).write(RouteContext("x"), Ranking(), 0)
    assert decision_log({"LAYA_ROUTER_LOG": "off"}).path is None
    assert decision_log({"LAYA_ROUTER_LOG": str(path)}).path == path


def test_instructions_fit_the_2kb_cap():
    assert len(INSTRUCTIONS) < 300 and "route" in INSTRUCTIONS
```

- [ ] **Step 2: Run and confirm they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.decisions'`

- [ ] **Step 3: Write `src/laya_router/decisions.py`**

```python
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
```

- [ ] **Step 4: Write `src/laya_router/server.py`**

```python
"""MCP stdio server exposing one `route` tool backed by a warm Laya engine."""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import __version__, catalog
from .decisions import DEFAULT_LOG, DecisionLog
from .engine import Engine, EngineConfig, format_hint
from .items import Item, RouteContext

log = logging.getLogger("laya_router.server")
INSTRUCTIONS = ("If a user request arrives without a [laya-router] line in context, you may call `route` "
                "with the request text to get ranked skill/connector/tool candidates. Treat them as advisory.")
ROUTE_DESCRIPTION = ("Rank the skills, connectors and tools most relevant to a user request. "
                     "Returns one advisory line, or an empty string when nothing stands out.")


class RouterService:
    """Holds the engine, loads it off the request path, and never raises from route()."""

    def __init__(self, engine_factory: Callable[[], Engine],
                 discover: Callable[[RouteContext], list[Item]] = catalog.discover,
                 decisions: DecisionLog | None = None) -> None:
        self._factory = engine_factory
        self._discover = discover
        self._decisions = decisions or DecisionLog(None)
        self._engine: Engine | None = None
        self._started = False
        self.ready = threading.Event()

    def load(self) -> None:
        try:
            self._engine = self._factory()
        except Exception:
            log.exception("engine load failed; routing stays silent this session")
        finally:
            self.ready.set()

    def start(self) -> None:
        if self._started or self.ready.is_set():
            return
        self._started = True
        threading.Thread(target=self.load, name="laya-load", daemon=True).start()

    def route(self, ctx: RouteContext) -> str:
        engine = self._engine
        if engine is None:
            return ""
        try:
            items = self._discover(ctx)
            ranking = engine.rank(ctx.prompt, items)
            self._decisions.write(ctx, ranking, len(items))
            return format_hint(ranking)
        except Exception:
            log.exception("route failed")
            return ""


def build_server(service: RouterService) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict]:
        service.start()  # stdio_server already points fd 1 at stderr, so stray model prints miss the wire
        yield {}

    server = MCPServer("laya-router", instructions=INSTRUCTIONS, version=__version__, lifespan=lifespan)

    @server.tool(name="route", description=ROUTE_DESCRIPTION)
    def route(prompt: str, cwd: str = "", transcript_path: str = "", session_id: str = "") -> str:
        return service.route(RouteContext(prompt, cwd, transcript_path, session_id))

    return server


def default_engine(env: Mapping[str, str] = os.environ) -> Engine:
    from .scorer import LayaScorer

    model = env.get("LAYA_ROUTER_MODEL", "typed-decisions")
    scorer = LayaScorer(model=model, device=env.get("LAYA_ROUTER_DEVICE") or None)
    return Engine(scorer, EngineConfig.from_env(env))


def decision_log(env: Mapping[str, str] = os.environ) -> DecisionLog:
    raw = env.get("LAYA_ROUTER_LOG", "")
    if raw.lower() in ("0", "off", "false"):
        return DecisionLog(None)
    return DecisionLog(Path(raw) if raw else DEFAULT_LOG)


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_server(RouterService(default_engine, decisions=decision_log())).run()
```

- [ ] **Step 5: Run and confirm they pass**

Run: `uv run pytest -v`
Expected: all pass, 5 new. If `yield {}` in the lifespan raises a type or runtime error, switch it to `yield None` and rerun (the lowlevel lifespan contract accepts any context).

- [ ] **Step 6: Commit**

```bash
git add src/laya_router/decisions.py src/laya_router/server.py tests/test_server.py
git commit -m "feat: add fail-open MCP route server and decision log

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 14: CLI

**Files:**
- Create: `src/laya_router/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `server.serve`, `server.default_engine` (looked up at call time so tests can patch it);
  - `catalog.discover`, `catalog.harness_catalogs`, `catalog.TOOL_CACHE`;
  - `toolcache.configured_servers`, `toolcache.refresh`;
  - `dataset.main`, `evaluate.main`;
  - `engine.format_hint`.
- Produces: `cli.main(argv) -> int`, the entry point for `laya-router`, with the subcommands `serve`, `route <prompt>`, `catalog [--refresh]`, `warmup`, and `eval {build,run} ...`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
from fakes import FakeScorer

from laya_router import cli
from laya_router.engine import Engine


def test_catalog_prints_counts(tmp_path, monkeypatch, capsys, write_skill):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    write_skill(tmp_path / ".claude" / "skills", "mine")
    assert cli.main(["catalog"]) == 0
    assert "skill" in capsys.readouterr().out


def test_route_prints_hint(tmp_path, monkeypatch, capsys, write_skill):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    write_skill(tmp_path / ".claude" / "skills", "debugging")
    monkeypatch.setattr("laya_router.server.default_engine",
                        lambda env=None: Engine(FakeScorer({"skill": {"debugging": 0.9}})))
    assert cli.main(["route", "please debug the failing test"]) == 0
    assert capsys.readouterr().out.startswith("[laya-router] advisory")


def test_eval_build_runs_on_empty_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["eval", "build", "--out", str(tmp_path / "out")]) == 0
    assert '"labeled": 0' in capsys.readouterr().out
```

- [ ] **Step 2: Run and confirm they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'laya_router.cli'`

- [ ] **Step 3: Write `src/laya_router/cli.py`**

```python
"""laya-router command line: serve | route | catalog | warmup | eval."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import anyio

from . import catalog, server
from .engine import format_hint
from .items import RouteContext


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laya-router", description="Local Laya routing hints for agent harnesses")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("serve", help="run the MCP stdio server").set_defaults(func=cmd_serve)
    route = sub.add_parser("route", help="rank one prompt and print the hint")
    route.add_argument("prompt")
    route.add_argument("--transcript-path", default="")
    route.set_defaults(func=cmd_route)
    cat = sub.add_parser("catalog", help="count discovered items; --refresh snapshots local MCP tools first")
    cat.add_argument("--refresh", action="store_true")
    cat.add_argument("--transcript-path", default="")
    cat.set_defaults(func=cmd_catalog)
    sub.add_parser("warmup", help="download the model, refresh tools, count catalogs").set_defaults(func=cmd_warmup)
    ev = sub.add_parser("eval", help="build the eval set or run the Phase 0 comparison")
    ev.add_argument("action", choices=["build", "run"])
    ev.add_argument("rest", nargs=argparse.REMAINDER)
    ev.set_defaults(func=cmd_eval)
    return parser


def cmd_serve(_args: argparse.Namespace) -> int:
    server.serve()
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    ctx = RouteContext(args.prompt, cwd=os.getcwd(), transcript_path=args.transcript_path)
    ranking = server.default_engine().rank(ctx.prompt, catalog.discover(ctx))
    print(format_hint(ranking) or "(no hint)")
    print(json.dumps(asdict(ranking), indent=1))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    home, cwd = Path.home(), Path.cwd()
    if args.refresh:
        from . import toolcache

        snapshot = anyio.run(toolcache.refresh, toolcache.configured_servers(home, cwd), home / catalog.TOOL_CACHE)
        print(f"refreshed {len(snapshot['servers'])} MCP servers")
    items = catalog.discover(RouteContext("", cwd=str(cwd), transcript_path=args.transcript_path), home=home)
    for (kind, source), count in sorted(Counter((i.kind, i.source) for i in items).items()):
        print(f"{kind:9} {count:4}  {source}")
    return 0


def cmd_warmup(_args: argparse.Namespace) -> int:
    cmd_catalog(argparse.Namespace(refresh=True, transcript_path=""))
    catalog.clear_cache()
    engine = server.default_engine()
    for harness, items in catalog.harness_catalogs().items():
        print(f"{harness}: {len(items)} items ready for {engine.scorer.model}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    if args.action == "build":
        from .dataset import main as build_main

        return build_main(args.rest)
    from .evaluate import main as run_main

    return run_main(args.rest)
```

- [ ] **Step 4: Run and confirm they pass**

Run: `uv run pytest -v`
Expected: all pass, 3 new.

- [ ] **Step 5: Smoke-test the real CLI**

Run: `uv run laya-router route "my pytest suite fails with a KeyError after the refactor, help me find why"`
Expected: the first line is a `[laya-router] ...` hint naming a debugging-type skill, or `(no hint)`, followed by ranking JSON with `latency_ms`.

- [ ] **Step 6: Commit**

```bash
git add src/laya_router/cli.py tests/test_cli.py
git commit -m "feat: add laya-router CLI (serve, route, catalog, warmup, eval)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 15: Plugin, marketplace, snippets, README, and live verification

**Files:**
- Create: `plugin/.claude-plugin/plugin.json`, `plugin/.mcp.json`, `plugin/hooks/hooks.json`, `.claude-plugin/marketplace.json`, `snippets/gemini-settings.json`, `snippets/cursor-mcp.json`, `snippets/vscode-mcp.json`, `README.md`, `tests/test_plugin_files.py`

**Interfaces:**
- Consumes: `spike/FINDINGS.md` (the hook template field and the command form); the `laya-router` executable from `uv tool install`.
- Produces: an installable plugin `laya-router@layla`, whose hook server is `plugin:laya-router:router`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_files.py
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


def test_plugin_has_no_top_level_bin():
    assert not (ROOT / "plugin" / "bin").exists()


def test_marketplace_points_at_plugin():
    [entry] = load(".claude-plugin/marketplace.json")["plugins"]
    assert (entry["name"], entry["source"]) == ("laya-router", "./plugin")
```

- [ ] **Step 2: Run and confirm it fails**

Run: `uv run pytest tests/test_plugin_files.py -v`
Expected: FAIL with `FileNotFoundError` for `plugin/hooks/hooks.json`

- [ ] **Step 3: Write the plugin, marketplace and snippets.** If Task 2 found that `${prompt}` does not carry the prompt, use the field recorded there in both `hooks.json` and the test. If the plain `laya-router` command is not found on `PATH` in Step 6 or 7, switch `command` to `${HOME}/.local/bin/laya-router`.

```json
{"name": "laya-router", "version": "0.1.0", "description": "Local Laya classifier that suggests relevant skills, connectors and tools for each prompt"}
```
(file: `plugin/.claude-plugin/plugin.json`)

```json
{"mcpServers": {"router": {"command": "laya-router", "args": ["serve"]}}}
```
(file: `plugin/.mcp.json`)

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "mcp_tool", "server": "plugin:laya-router:router", "tool": "route",
  "input": {"prompt": "${prompt}", "cwd": "${cwd}", "transcript_path": "${transcript_path}", "session_id": "${session_id}"},
  "timeout": 5}]}]}}
```
(file: `plugin/hooks/hooks.json`)

```json
{"name": "layla", "owner": {"name": "local"},
 "plugins": [{"name": "laya-router", "source": "./plugin", "description": "Local Laya routing hints for skills, connectors and tools"}]}
```
(file: `.claude-plugin/marketplace.json`)

```json
{"mcpServers": {"laya-router": {"command": "laya-router", "args": ["serve"]}}}
```
(files: `snippets/gemini-settings.json` to merge into `~/.gemini/settings.json`, and `snippets/cursor-mcp.json` to merge into `~/.cursor/mcp.json`)

```json
{"servers": {"laya-router": {"type": "stdio", "command": "laya-router", "args": ["serve"]}}}
```
(file: `snippets/vscode-mcp.json` for `.vscode/mcp.json`)

`README.md`:

````markdown
# laya-router

Local Laya classifier that suggests the skills, connectors and tools relevant to each prompt.
Advisory only: it never hides or blocks anything. Design: `docs/superpowers/specs/2026-09-25-laya-router-design.md`.

## Install (this machine)
```bash
uv tool install -e .          # puts `laya-router` in ~/.local/bin
laya-router warmup            # downloads the checkpoint, snapshots MCP tools, counts catalogs
claude plugin marketplace add "$PWD"
claude plugin install laya-router@layla
```
Cowork: `mkdir -p dist && (cd plugin && zip -r ../dist/laya-router-plugin.zip .)`, then Customize › Plugins › Upload (local sessions only).
Gemini / Cursor / VS Code: merge the matching file from `snippets/`.

## Check it
- `laya-router route "your prompt"` prints the hint plus ranking JSON.
- Decisions: `~/.local/state/laya-router/decisions.jsonl`.
- Env: `LAYA_ROUTER_MODEL`, `LAYA_ROUTER_DEVICE`, `LAYA_ROUTER_K_SKILL`, `LAYA_ROUTER_K_TOOL`, `LAYA_ROUTER_TAU`, `LAYA_ROUTER_LOG` (`off` disables the log).

## Uninstall
`claude plugin uninstall laya-router@layla` · `uv tool uninstall laya-router`
````

- [ ] **Step 4: Run and confirm the tests pass**

Run: `uv run pytest -v`
Expected: all pass, 3 new.

- [ ] **Step 5: Commit**

```bash
git add plugin .claude-plugin snippets README.md tests/test_plugin_files.py
git commit -m "feat: package router as Claude Code/Cowork plugin with MCP snippets

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Install. Ask the user first**, because this changes their Claude Code config and `~/.local/bin`.

Run each line only after a yes:
```bash
claude plugin --help | head -20        # confirm the marketplace/install subcommands exist in this version
uv tool install -e .
laya-router warmup
claude plugin marketplace add "$PWD"
claude plugin install laya-router@layla
```
Expected: warmup prints the item counts for each harness, and the install reports success.

- [ ] **Step 7: Verify in the Claude Code CLI**

```bash
claude -p "Before answering: if your context has a line starting with [laya-router], repeat it verbatim, else say NONE. Task: my pytest suite fails with a KeyError after the refactor; how should I start debugging?"
tail -n 1 ~/.local/state/laya-router/decisions.jsonl
```
Expected: the reply repeats a `[laya-router] ...` line, and the last log record has `"harness": "claude-code"`.

- [ ] **Step 8: Verify in VS Code and Cowork** (the user does these; ask them)
  - **VS Code (2.1.282):** start a new Claude Code session and send the same prompt. Expect the hint line, or record the #97173 symptom.
  - **Cowork:**
    1. Build the zip as in the README and upload it.
    2. Open a **local** session and send the same prompt.
    3. Check `decisions.jsonl` for `"harness": "cowork"`.
    4. Check that the skill IDs in the hint (`anthropic-skills:<name>`) match the names Cowork shows for its skills. If they don't, record the format Cowork actually uses; `cowork_skills` then needs a follow-up fix.
    5. If no hint appears, confirm the fallback: asking "call the laya-router route tool for: <prompt>" should work.
  - Record both results in `tasks/todo.md` § Review.

- [ ] **Step 9: Final commit**

```bash
git add tasks/todo.md
git commit -m "docs: record live verification in Claude Code, VS Code and Cowork

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
