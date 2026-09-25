# Laya Router — Design Spec

- **Date:** 2026-09-25
- **Status:** Draft, awaiting review
- **Source doc:** `DYNAMIC-ROUTING.md` (reviewed; corrections in §2)
- **Approach:** A. A router MCP server with a plugin hook. Chosen over B (meta-tool broker) and C (shared daemon); both remain possible add-ons.
- **Amended:** 2026-09-25, after the Phase 0 gate. §12 overrides the shortlist in §4 and the skill criterion in §7.

## 1. Intent

A local Laya model picks, on every user turn, the skills, connectors and tools most likely to be relevant. The harness gets a short advisory hint, so the main model chooses better. It must also work inside Claude Cowork, which gives the user no control over skill, tool or connector routing.

| | What the user said | Assumed (correct if wrong) |
|---|---|---|
| Audience | Own setup, not a distributed product | Linux host only; no macOS or Windows packaging |
| Goal | Better picks and smaller context, weighted equally | Advisory hints are acceptable. Nothing is blocked or hidden from the model |
| Harnesses | Claude Code, Cowork, "any harness" | Primary targets are the Claude Code CLI (2.1.270), Claude Code in VS Code (2.1.282), and Cowork local sessions (bundled Claude Code 2.1.275). Secondary targets are Gemini CLI, Cursor, Copilot CLI and VS Code agent mode, all through MCP only |
| Code size | Deployable with minimal code | Roughly 350 lines of Python plus 3 JSON files |
| Hardware | Not stated | RTX 3070 8 GB for inference, falling back to CPU (i7-11800H) |

**Success criteria**
1. The Phase 0 gate passes (§7).
2. In Claude Code, every non-trivial prompt receives a hint, or deliberately none, within 250 ms p95 on GPU.
3. The same plugin installs in Cowork.
4. Other harnesses reach the router with one MCP config entry each.

**Honest limit:** Claude Code and Cowork already defer MCP tool schemas through tool search. Neither lets anyone unload skills or connectors per turn, and MCP spec 2026-07-28 forbids tool lists that vary per turn. On those platforms the router's win is better picks, plus faster tool search because the hint gives exact tool names. It does not cut context there. A real context cut needs approach B, a later option.

## 2. Verified constraints (review of DYNAMIC-ROUTING.md)

Checked on 2026-09-25 against the Laya 0.3.20 wheel source, the installed Claude Code binary, the official docs, and local Cowork session files.

| Doc claim | Verified reality | Design consequence |
|---|---|---|
| About 33 ms per decision | That is a T4 GPU figure. On CPU a question takes 193 to 580 ms, and loading a checkpoint takes 0.5 to 4.4 s | Keep the model warm in a long-lived process on the GPU. Never load it per prompt |
| `export LAYA_MODEL=typed-decisions` | No such environment variable exists | Call `router.predict(..., model="typed-decisions")` |
| `Router(preload=True)` | Loads all three checkpoints, about 2.4 GB | Preload only `typed-decisions` |
| A flat `choice` over the whole catalog | All options share a 192/256-token head budget, and the docs advise about 20 options at most | Shortlist with encoder cosine similarity, then run one `choice` over the top K |
| The `traverse()` drill-down | Absent from both the wheel and the main branch | Use our own shortlist, built on Laya's `shortlist.embed_fn_from_agent` |
| `multilingual` has 8192 tokens of context | The default is 1024; 8192 only with `max_len=8192` | Use `typed-decisions`, which has 1024 |
| The hook reads `prompt` | Correct for CLI 2.1.270 (binary check). Some docs say `user_input` | Template `${prompt}` and verify in the spike |
| §2 broker using per-turn `list_changed` | Spec 2026-07-28 says `tools/list` "MUST NOT vary per-connection or as a side effect". Claude Code refreshes only on the next turn. Desktop ignores the notification | No dynamic tool lists. Use advisory ranking, or meta-tools (option B) |
| The broker gates connectors | claude.ai connectors (Gmail, Slack, Figma, Drive, Calendar, Sentry) have their OAuth in claude.ai and cannot be proxied locally | Rank and recommend them only |
| §3 `setMcpServers()` | Not found in the official SDK docs | Dropped |
| Cowork behaves like interactive Claude Code | Cowork ignores `~/.claude`. Plugins are the only way in. Plugin hooks are documented, but field reports disagree on whether they run. Local plugin MCP servers run on the host, and only in local sessions | Ship as a plugin, with server `instructions` as the fallback |
| Zero-shot is triage-grade | Base checkpoints score 0.362 on typed decisions against 0.318 for random; the fine-tuned `typed-decisions` scores 0.766. Nothing is measured on our catalog | The Phase 0 gate comes before the build |

Other confirmed facts:
- Claude Code hook types include `mcp_tool`. It fills `${path}` placeholders from the hook input, is skipped only when no MCP client context exists (SessionStart and Setup), and addresses plugin servers as `plugin:<plugin>:<server>`.
- Claude Code injects MCP server `instructions` into the system prompt, truncated at about 2 KB. This session shows it happening.
- The Cowork VM's egress allowlist excludes huggingface.co. That is irrelevant here because the plugin's MCP servers run on the host.

## 3. Architecture

```
Claude Code / Cowork session
  user prompt ─► UserPromptSubmit hook  {type: mcp_tool, server: plugin:laya-router:router, tool: route,
                                         input: {prompt: "${prompt}", cwd: "${cwd}", transcript_path: "${transcript_path}", session_id: "${session_id}"}}
                        │
                        ▼
  laya-router MCP server (stdio, one per session; Laya warm on GPU; loads in background after handshake)
     catalog.discover ─► engine.rank (shortlist → Laya choice incl. "none") ─► format_hint
                        │
  ◄── additionalContext: one advisory line (or nothing)

Other harnesses: same server via their MCP config; the model calls `route` itself (server instructions say when).
```

### Units and interfaces

| Unit | Responsibility | Interface | Depends on |
|---|---|---|---|
| `catalog.py` | Discover routable items for the calling harness | `discover(ctx: RouteContext) -> list[Item]` | Filesystem only |
| `engine.py` | Rank items for a prompt | `Engine(scorer, cfg).rank(prompt, items) -> Ranking`; `format_hint(ranking) -> str` | A `Scorer` protocol |
| `scorer.py` | Laya adapter (can be swapped for a fake) | `embed(texts) -> ndarray`; `choose(state, questions) -> answers` | `laya` |
| `server.py` | MCP stdio server; loads the model in the background | tool `route(prompt, cwd="", transcript_path="", session_id="") -> str` | `mcp`, engine, catalog |
| `cli.py` | Entry points | `laya-router serve \| route "<text>" \| catalog [--refresh] \| warmup \| eval` | All of the above |

Types (dataclasses):
- `RouteContext{prompt, cwd, transcript_path, harness: "claude-code" | "cowork"}`
- `Item{kind: "skill" | "connector" | "tool", id, label, text, connector: str | None, source}`
  - `label` is a one-line summary of at most 80 characters, used as choice option text.
  - `text` is the description, at most 1500 characters, used for embeddings.
- `Candidate{id, label, p, connector}`
- `Ranking{skills, connectors, tools: list[Candidate], latency_ms, model}`

The engine knows nothing about MCP or harnesses. The server knows nothing about Laya internals. That boundary lets approach C (an HTTP daemon) or B (a broker) wrap the same engine later.

### Repository layout

```
layla/
├── pyproject.toml                 # package laya-router; entry point laya-router; Python 3.12
├── src/laya_router/{__init__,catalog,engine,scorer,server,cli}.py
├── plugin/                        # Claude Code + Cowork plugin (no top-level bin/: Cowork rejects it)
│   ├── .claude-plugin/plugin.json
│   ├── .mcp.json
│   └── hooks/hooks.json
├── .claude-plugin/marketplace.json  # local marketplace "layla" → ./plugin
├── snippets/                      # MCP entries: gemini, cursor, copilot-cli, vscode
├── eval/                          # Phase 0: dataset builder, runner, results
└── tests/
```

## 4. Engine

Steps for each `route` call:

1. **Skip before the model** and return `""` when any of these hold:
   - the prompt starts with `/` (the user already chose);
   - the stripped prompt is shorter than 12 characters;
   - the prompt matches the previous prompt from this server.
2. **Catalog.**
   - `transcript_path` under `~/.config/Claude/local-agent-mode-sessions/` means `harness = cowork`. Otherwise it is `claude-code`.
   - Discovery runs at most every 30 s per harness.
3. **Shortlist.**
   - Embed the prompt with the loaded checkpoint's encoder, mean-pooled (`laya.shortlist.embed_fn_from_agent`).
   - Item embeddings are cached at `~/.cache/laya-router/emb-<model>.npz`, keyed by the sha256 of `text`.
   - Take the top-K per kind by cosine similarity. Defaults: skills 10, tools 10, connectors 15 (all of them when there are 15 or fewer).
4. **Decide.** Make one `router.predict(state, questions, model="typed-decisions")`:
   - `state = {"request": prompt}`
   - `questions` holds up to three `choice` questions (skill, connector, tool).
   - Each question's `criteria` is `{item.id: item.label}` for the shortlisted items, plus `"none": "no specialized skill/tool needed; general request"`.
   - A kind with no items is omitted.
5. **Select.**
   - For each kind, keep candidates with `p >= τ_kind`, where τ starts at 0.35 and is calibrated in Phase 0.
   - Sort by `p`. Cap at 3 skills, 2 connectors and 3 tools.
   - If `none` has the top probability, that kind contributes nothing.
6. **Format.**
   - Produce one line of 400 characters or fewer, or `""` when all kinds are empty:
     `[laya-router] advisory, ignore if irrelevant — skills: superpowers:systematic-debugging (0.62) · connectors: Gmail (0.71) → search_threads, get_thread`
   - Tools are grouped under their connector, using the exact tool names that Claude Code's `ToolSearch select:` accepts.

Model lifecycle:
- The server answers `initialize` immediately and loads the Router in a background thread (`Router(device=auto)`, then `preload(["typed-decisions"])`).
- `route` returns `""` until the model is ready.
- Device selection is automatic: CUDA if present, otherwise CPU. Laya falls back from GPU to CPU on its own.

Configuration: environment variables only, with defaults in code. These are `LAYA_ROUTER_MODEL`, `LAYA_ROUTER_DEVICE`, `LAYA_ROUTER_K_SKILL`, `LAYA_ROUTER_K_TOOL`, `LAYA_ROUTER_TAU` and `LAYA_ROUTER_LOG`. Phase 0 results become the defaults.

## 5. Catalog sources

**Claude Code** (`harness = claude-code`):

- Skills:
  - `~/.claude/skills/*/SKILL.md` and `<cwd>/.claude/skills/*/SKILL.md`, with id `<name>`.
  - Enabled plugins: take `~/.claude/settings.json` `enabledPlugins` entries that are `true`, joined with `~/.claude/plugins/installed_plugins.json` (v2: `plugins["<plugin>@<marketplace>"][0].installPath`). Skills are `<installPath>/skills/*/SKILL.md`, with id `<plugin>:<name>`.
  - `.agents/skills/*/SKILL.md` in `<cwd>` and `~`.
  - Frontmatter `name` and `description` are required. Skills with `disable-model-invocation: true` are skipped, because the model cannot invoke them.
- Local MCP servers and tools:
  - `laya-router catalog --refresh` reads `~/.claude.json` `mcpServers`, `<cwd>/.mcp.json`, and each enabled plugin's `<installPath>/.mcp.json`.
  - It connects to each server with the official `mcp` client, calls `tools/list`, and writes `~/.cache/laya-router/mcp-tools.json`.
  - A server that fails is skipped and logged. `route` reads only the cache and never connects to anything.
  - Tool ids are `mcp__<server>__<tool>`; plugin servers use `mcp__plugin_<plugin>_<server>__<tool>`.
- claude.ai connectors: `remoteMcpServersConfig` from the newest Cowork session JSON, which covers the same account's connectors. Tool id is `mcp__claude_ai_<Name, spaces→_>__<tool>`.

**Cowork** (`harness = cowork`):

- The session JSON is `<acct>/<org>/local_<id>.json`, the sibling of the `local_<id>/` directory that contains the transcript.
- Connectors and tools come from `remoteMcpServersConfig[]`, fields `name`, `instructions`, and `tools[].name`/`description`.
- Skills come from `skills-plugin/*/*/manifest.json`, keeping `skills[]` entries with `enabled: true`, with id `anthropic-skills:<name>`. User plugins come from the session's `pluginInstallPaths[]`.
- If `skillsEnabled` is false, no skills are included.

Malformed or missing sources are skipped with a log line and never raise.

## 6. Harness integration

**Plugin** (`plugin/`):
- `.claude-plugin/plugin.json` contains `{"name": "laya-router", "version": "0.1.0", "description": "Local Laya classifier that suggests relevant skills, connectors and tools for each prompt"}`.
- `.mcp.json`:
  ```json
  {"mcpServers": {"router": {"command": "laya-router", "args": ["serve"]}}}
  ```
  Environment-variable expansion and `PATH` inside Cowork are verified in the spike. The fallback is an absolute `~/.local/bin/laya-router` path.
- `hooks/hooks.json`:
  ```json
  {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "mcp_tool",
    "server": "plugin:laya-router:router", "tool": "route",
    "input": {"prompt": "${prompt}", "cwd": "${cwd}", "transcript_path": "${transcript_path}", "session_id": "${session_id}"},
    "timeout": 5}]}]}}
  ```
- Server `instructions` (fallback when hooks don't fire, and the only path in other harnesses), under 300 characters: "If a user request arrives without a `[laya-router]` line in context, you may call `route` with the request text to get ranked skill/connector/tool candidates. Treat them as advisory."

**Install:**
1. `uv tool install -e <repo>`
2. `laya-router warmup`, which downloads the checkpoint, runs `catalog --refresh`, and pre-embeds the catalog.
3. Claude Code: `claude plugin marketplace add <repo>`, then `claude plugin install laya-router@layla`.
4. Cowork: build the zip with `cd plugin && zip -r ../dist/laya-router-plugin.zip .` (`dist/` is gitignored), then upload it via Customize › Plugins › Upload. Local sessions only.
5. Gemini, Cursor, Copilot CLI and VS Code: paste the matching file from `snippets/`.

## 7. Phase 0 spike and go/no-go gate

The spike is throwaway work. The data files it produces are kept.

1. **Environment.** A `uv` project with `laya` and `mcp` (dependencies approved at execution). Record load time, VRAM, and latency on GPU and on CPU.
2. **Eval set**, written as `eval/data/*.jsonl` with rows `{prompt, harness, gold: {skill?, connector?, tool?}, source}`:
   - From transcripts in `~/.claude/projects/**/*.jsonl` and Cowork `local_*/.claude/projects/**`, collect each real user prompt. Label it with the next `Skill` tool call, a slash command, or the first `mcp__*` tool call before the next user turn.
   - Add 2 or 3 synthetic prompts per skill and per connector, written from their descriptions. Mark them `source=synthetic`. They inflate scores, so they are reported separately.
   - Split into dev (for thresholds and K) and test.
3. **Compare** BM25, encoder cosine only, and shortlist → `choice` with the `english` and `typed-decisions` checkpoints, for K ∈ {5, 10, 15}. Metrics:
   - top-1 and top-3 recall per kind;
   - abstain rate on turns with no labeled use (for information only, not ground truth);
   - p50 and p95 latency.
4. **Hook check.** Use a scratch plugin whose `route` returns a sentinel string:
   - CLI 2.1.270 with `--plugin-dir`;
   - VS Code extension 2.1.282 (known stdio handshake bug #97173);
   - Cowork, from a zip the user uploads.

   For each, confirm the sentinel reaches context and that an empty result injects nothing.
5. **Gate.** Build only if all three hold:
   - on the transcript-derived test set, top-3 skill recall is at least 0.70 and at least 10 points above BM25;
   - p95 latency is at most 250 ms on GPU;
   - the `mcp_tool` hook injects context in the Claude Code CLI.

   Otherwise stop and report the options: fine-tune Laya on the eval data, route with cosine only, or move the hook to approach C (`http` hook plus daemon).

## 8. Errors, logging, security

- **Fail-open everywhere.** An unready model, an exception, a hook timeout (5 s), or a broken catalog source all give `route` an empty result and a log line. The user's prompt is never blocked.
- **Decision log.** `~/.local/state/laya-router/decisions.jsonl` records `ts`, `harness`, `session`, `prompt[:500]`, candidates with `p`, `latency_ms`, `model` and `catalog_size`. It rotates once it passes 10 MB and stays local. Joined with transcripts, it becomes future fine-tuning data. The server also writes diagnostics to stderr, which Claude Code captures.
- **Security.**
  - Stdio only, with no network listener.
  - The router never executes or proxies tools, so it cannot bypass per-tool permissions.
  - Network access happens only at `warmup`, to download the Hugging Face checkpoint.
  - Prompts stay on the machine.

## 9. Testing

- **Unit tests** (`uv run pytest`):
  - catalog parsers on fixture trees that mimic the Claude Code and Cowork layouts;
  - the engine with a `FakeScorer` (deterministic embeddings and probabilities), covering thresholds, `none` winning, caps, skip rules and formatting;
  - the `route` tool through the `mcp` SDK in-process client, including a not-ready model returning `""`.
- **Slow tests** (`-m slow`): real Laya on 5 canned prompts, plus a latency assertion.
- **Manual:** the hook matrix from §7 step 4.

## 10. Out of scope (possible later add-ons on the same engine)

- **B:** a meta-tool broker (`find_tools`/`call_tool`) over local MCP servers, for a real context cut in harnesses without tool search. Per-tool permission semantics need handling.
- **C:** a shared HTTP daemon with a single model in memory, giving `http` or `command` hooks to Gemini (`BeforeAgent`), Codex and VS Code.
- Enforcement through `PreToolUse` deny, unloading skills from the listing, fine-tuning, `list_changed`, and macOS or Windows support.

## 11. Open items the spike resolves

1. Environment-variable expansion and `PATH` for the plugin's `.mcp.json` command in Claude Code and in Cowork.
2. `mcp_tool` output rendering: does an empty result inject nothing, and what exact text reaches the model?
3. Whether Cowork local sessions fire plugin `UserPromptSubmit` hooks, what their `transcript_path` looks like, and which skill id format Cowork uses (assumed `anthropic-skills:<name>`).
4. Laya internals:
   - how to get the loaded `Agent` from the `Router` (needed for `embed_fn_from_agent`);
   - whether `head_max_len` can widen the option budget;
   - VRAM per session.
5. Whether Claude Code 2.1.282's stdio handshake bug (#97173) affects `mcp_tool` hooks.

## 12. Amendment after the Phase 0 gate (2026-09-25)

The gate failed as planned. The evidence is in `spike/FINDINGS.md` § Gate. The user chose the measured fix, keeping approach A.

- **Shortlist (overrides §4, steps 1–2).** BM25 now indexes each item's short name, its connector and its description, and takes the top-K per kind. It replaces the encoder cosine.
  - Mean-pooled Laya encoder vectors retrieve poorly: dev skill recall@10 is 0.51 for cosine against 0.92 for BM25. Laya's own docstring recommends a dedicated bi-encoder for shortlisting.
  - Item embeddings, `emb-<model>.npz` and `Scorer.embed` are gone, and `warmup` no longer pre-embeds.
  - K, the `none` option, τ and the caps are unchanged in kind. Their values come from the re-run eval.
- **Model:** `typed-decisions`. `english` ranks `none` first on about 30% of the dev prompts that need a skill.
- **Skill criterion (overrides §7, step 5).** Top-3 skill recall ≥ 0.70 is now measured on the synthetic dev set. Most real transcript skill labels are workflow continuations, such as a bare option number or "implement", which no prompt-only router can see. "Beats BM25" is reported on the same dev metric. On that metric the hybrid is +0.04, which is below the 0.10 bar, and the user accepted that. Laya's measured value over BM25 is:
  - routing real prompts to connectors (+0.29 top-1);
  - tool top-1 (+0.11 on dev);
  - the `none` abstain.
- **Latency:** GPU p95 measured 65–150 ms with the BM25 shortlist. CPU p95 is about 2.6 s.
- **Known risk carried into Phase 1:** each session holds about 2.5 GB of VRAM. Approach C remains the fix if concurrent sessions exhaust the card.
- **Routing-quality amendment (Task 14 smoke test).**
  - The BM25 tokenizer folds accents, drops English and Portuguese stopwords, and splits words longer than 4 characters into 4-grams.
  - Equivalent items (same short key and label) become one option.
  - A connector without server instructions is labelled by its most frequent tool-name words.
  - The eval adds `eval/natural.jsonl` (scenario prompts that avoid the descriptions' wording).
  - τ is calibrated against the alarm rate on real unlabeled turns: precision must be ≥ 0.75, with a hint on no more than 10% of turns that used no skill or tool.
  - Defaults are K=5 for every kind (6 options, inside Laya's calibrated buckets) and τ of 0.5 for skills, 0.6 for connectors and 0.5 for tools.
  - Details are in `spike/FINDINGS.md` § Routing quality.
- **Tool snapshot scope (final review, overrides §5).** `catalog --refresh` and `warmup` leave out a project's `.mcp.json`. Claude Code runs those servers only after the user approves them, and a global snapshot would also carry one project's servers into every other project.
