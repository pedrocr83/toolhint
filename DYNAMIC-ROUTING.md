# Laya as a live routing layer for agent harnesses

Use a local, fast decision model (Laya) as the System-1 layer that picks **skills,
tools, and connectors** per turn, while the main model does the reasoning. Laya
runs offline (~33 ms/decision, no API key, no rate limits), so it can run on every
turn cheaply. This guide covers three routing surfaces and how each maps onto
Claude Code (interactive / "cowork"), the Claude Agent SDK, and generic MCP hosts.

All claims below are grounded in the Claude Code MCP docs (dynamic tool updates,
plugin MCP lifecycle, Agent SDK `setMcpServers()`, tool search) — verify against
your harness version.

## 0. Bootstrap (once)

The router needs Laya and a checkpoint cached before first use.

```bash
uv add laya            # or: pip install laya
# Optional: pin the fine-tuned routing checkpoint
export LAYA_MODEL=typed-decisions
python -c "from laya import Router; Router(preload=True)"   # warm the cache
```

Put this in the broker/server startup or a skill's setup step so it runs at most
once per environment, guarded by an "already installed" check.

## 1. Route SKILLS — `UserPromptSubmit` hook (immediate, in-turn)

A `UserPromptSubmit` hook runs harness-side on every user message and can inject
context. Have it run Laya over the prompt + skill catalog and inject a
recommendation the model then acts on.

```python
# hook: reads the user prompt on stdin, prints context to inject on stdout
from laya import Router
router = Router()

def route(prompt: str, skills: dict[str, str]) -> str | None:
    r = router.predict(prompt, {
        "skill": {"type": "choice", "instructions": "Which skill handles this?",
                  "criteria": skills},                       # {name: description}
        "needs_skill": {"type": "noul", "instructions": "Does this need a specialized skill?"},
    })
    a = r["answers"]
    conf = max(a["skill"]["probabilities"].values())
    if a["needs_skill"]["noul"] > 0.5 and conf > 0.35:
        return a["skill"]["choice"]
    return None   # let the base model decide
```

- **Claude Code / cowork**: wire as a `UserPromptSubmit` hook in `settings.json`;
  emit `Recommended skill: <name>` as injected context.
- **Agent SDK**: run the same function before each turn and prepend to the system
  or user message.
- **Other harnesses**: any pre-turn hook that can inject text works.
- Keep a confidence floor + fall back to full-model reasoning when unsure.

## 2. Route TOOLS — a "capability-broker" MCP server (`list_changed`)

An MCP server can change its own exposed tools at runtime by sending a
`notifications/tools/list_changed`; Claude Code refreshes that server's tools
with no reconnect. Build **one broker server** that holds Laya and exposes only
the tools relevant to the current task.

```
broker MCP server:
  - on each turn / context signal: run Laya over (task, full tool catalog)
  - compute the relevant subset (choice top-k, or one noul per tool > threshold)
  - update the advertised tool list, emit tools/list_changed
  - proxy calls through to the real tool implementations
```

- Works on **any MCP-compatible host** (Claude Code, SDK, third-party) — this is
  the most portable mechanism.
- Prefer one broker that gates many tools over many always-on servers: smaller
  tool surface = better model tool-selection and lower prompt cost.
- With **MCP tool search** on, a server that finishes connecting mid-work has its
  tool names handed to the model the same turn — no wait for the next message.

### Restricting which tools are loaded vs. usable

Two separate levers — use both:

- **Usable (gate calls):** allow/deny lists naming individual MCP tools
  (`mcp__<server>__<tool>` or `mcp__<server>__*`; plugin form
  `mcp__plugin_<plugin>_<server>__<tool>`) in `settings.json` permissions or the
  Agent SDK `allowedTools`/`disallowedTools`; or a `PreToolUse` hook that denies
  by matcher at runtime.
- **Loaded into context (save prompt space):** **MCP tool search / deferred
  tools** (default-on recently; `ENABLE_TOOL_SEARCH`) keeps tool schemas out of
  the prompt until fetched on demand. `alwaysLoad` and cached discovery control
  eager vs connect-on-first-use.

The broker makes this dynamic: Laya scores the tool catalog against the turn, the
broker advertises only the top-k via `list_changed`, and tool search keeps the
rest deferred — small loaded set *and* small usable set, chosen per turn.

## 3. Route CONNECTORS (whole MCP servers) — swap the server set

- **Agent SDK (true hot-add)**: call `setMcpServers([...])` at runtime to replace
  the session's connector list; Claude Code retries a server added mid-session.
  This is the cleanest dynamic-connector path.
- **Claude Code interactive / cowork**: bundle connectors in a **plugin**;
  enabling/disabling the plugin mid-session connects/disconnects its MCP servers
  (`/reload-plugins`). Also `claude mcp add` / the `/mcp` toggle / cached
  discovery (`connects on first use`).
- **Constraint**: in **non-interactive** sessions, `/reload-plugins` does *not*
  connect/disconnect — those changes land next session. Use the SDK
  `setMcpServers()` path (or a `list_changed` broker) when you need in-turn change
  without a terminal.

## Putting it together

```
Agent SDK harness (most dynamic):
  pre-turn:  skill = laya_route_skill(prompt, skills)      # §1 inject
             connectors = laya_route_connectors(task)      # §3 setMcpServers()
  in-turn:   broker MCP server gates tools via list_changed # §2
  fallback:  low confidence -> full-model reasoning, no routing
```

## Caveats

- **Context budget**: Laya `english` = 512 tokens, `multilingual` = up to 8192.
  Large skill/tool catalogs blow 512 fast — use `multilingual`, or trim
  descriptions, or route hierarchically (category -> specific), reusing the
  `traverse()` drill-down pattern in this repo.
- **Large label sets** degrade a flat choice; prefer per-item `noul` (batched) or
  the hierarchical choice.
- **Zero-shot is triage-grade.** Fine-tune Laya on *your* skill/tool catalog for
  the real accuracy jump (repo shows 0.362 -> 0.766). Routing over distinct,
  well-described skills is in-distribution for `laya-typed-decisions`.
- **Interactive vs non-interactive** differ for plugin reloads (above).
- Laya only *picks*; the harness still loads/runs the skill, tool, or connector.
