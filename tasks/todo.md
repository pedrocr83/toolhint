# laya-router — task tracker

Plan: `plan.md` · Spec: `docs/superpowers/specs/2026-09-25-laya-router-design.md`

## Phase 0 — foundation, spikes, gate
- [x] 1. Scaffold + dependencies (laya, mcp, pyyaml, pytest)
- [x] 2. Spike: `mcp_tool` UserPromptSubmit hook probe (CLI)
- [x] 3. Spike: Laya load/latency/VRAM/head budget
- [x] 4. Catalog: skills + slash commands
- [x] 5. Catalog: connectors, tools, `discover()` + TTL
- [x] 6. Tool cache refresh (local stdio MCP servers)
- [x] 7. Engine: shortlist, choice + none, thresholds, caches
- [x] 8. Hint format + Laya scorer
- [x] 9. Eval dataset from transcripts
- [x] 10. Synthetic dev prompts (+ Portuguese)
- [x] 11. Eval runner: BM25 vs cosine vs Laya, calibration, gate lines
- [x] 12. GATE: user go/no-go (hybrid, approach A)

## Phase 1 — build (only after gate passes)
- [x] 13. Decision log + MCP server
- [x] 14. CLI (+ routing-quality fixes from its smoke test)
- [x] 15. Plugin, marketplace, snippets, README, live verification (CLI verified; VS Code untested; Cowork unreachable in cloud mode → follow-up spike)

## Review
Filled in during execution: gate results, deviations from plan, verification outcomes, lessons.

### Gate (Task 12): FAIL as planned

Details are in `spike/FINDINGS.md` § Gate.

- **As planned** (cosine shortlist → Laya), the best configuration is typed-decisions K5:
  - test skill top-3 0.167, a FAIL against the 0.70 target;
  - beats BM25 by at least 0.10: PASS, but only because BM25 scores 0.0 on those 12 rows;
  - GPU p95 413 ms: FAIL, though that number is inflated by the run environment; the same code measured 124–127 ms p95 minutes later;
  - hook: PASS when the tool returns hook JSON;
  - CPU p95 2.6 s;
  - peak VRAM 2.5 GB per process.
- **Causes:**
  1. The cosine shortlist over mean-pooled Laya encoder vectors caps recall: dev skill recall@10 is 0.51, against 0.92 for BM25.
  2. About 7 of the 12 real skill labels are workflow continuations that no prompt-only router can see.
- **Candidate fix measured:** BM25 (name + description) shortlist → Laya typed-decisions choice, K=10:
  - dev skill top-3 0.88 (was 0.49);
  - dev tool top-1 0.49 (was 0.03);
  - real connector top-1 0.40 (BM25 alone: 0.11);
  - GPU p95 about 70 ms.
- **Decision:** the user chose the hybrid on approach A. The re-run with the BM25 shortlist gives:
  - dev skill top-3 0.888, a PASS;
  - beats BM25 by +0.05, a FAIL that the user accepted;
  - GPU p95 58 ms, a PASS.
  - The defaults are K 5/15/5 and τ 0.2/0.2/0.5.
  - Details are in `spike/FINDINGS.md` § Re-run.

### Routing quality (Task 14 smoke test)
- The smoke prompt exposed six root causes:
  1. tokenizer morphology and stopwords;
  2. τ calibrated without false alarms;
  3. 14-option connector choices in the sharpened temperature bucket;
  4. duplicate skills splitting the probability;
  5. connector labels that were raw tool lists;
  6. a dev set written in the descriptions' own wording.
- Each cause is fixed and has a test.
- The profile now:
  - The router speaks on about a third of the prompts that need a skill or connector, with precision 0.85–1.0.
  - It adds a hint to about 16% of real turns that used no skill or tool (any kind; 5–8% per kind).
  - GPU p95 is 40–53 ms.
- Details are in `spike/FINDINGS.md` § Routing quality.

### Live verification (Task 15)

**Install:**
- `uv tool install -e .` put `laya-router` at `~/.local/bin/laya-router`.
- `laya-router warmup` found 361 Claude Code items and 127 Cowork items.
- The `layla` marketplace was added and the `laya-router@layla` plugin installed at user scope.
- `claude plugin validate` passed, with author/description warnings only.

**Claude Code CLI 2.1.270:** verified with a two-turn `claude -p --input-format stream-json` session.
- Turn 1 arrived while the model was still loading. `route` returned `""` (fail-open), and nothing was injected.
- Turn 2, 18 s later, got `provided additionalContext (101 chars)` in 74 ms, and the model repeated the `[laya-router] …` line verbatim.
- `decisions.jsonl` recorded `"harness": "claude-code"`.

**Model loading:** a warm load takes 4.3 s, plus 1.4 s of first-pass CUDA warm-up. That warm-up now happens at load (fix 6359f94). So a prompt sent within about 6 s of a session starting gets no hint.

**Cowork prerequisites:** Claude Desktop's PATH includes `~/.local/bin`, and the zip is built at `dist/laya-router-plugin.zip`.

**Interactive Claude Code CLI 2.1.270** (session `0e6838e3`, run by the user on 2026-09-26):
- Both prompts were routed, and each reached the model as `hook_additional_context` (50 ms and 54 ms).
- "give me my morning brief" got `anthropic-skills:morning` (0.54), which is right, and Claude then invoked the Skill.
- "what's on my schedule tomorrow afternoon?" got `slack_schedule_message` (0.67), which is wrong. Claude ignored it and called Google Calendar `list_events`.
- Claude never called `route` on its own, even though the server's instructions are in context (`mcp_instructions_delta`).

**Tool-hint trade-off** (measured on the 298 routed real unlabeled turns and 62 natural+dev connector rows):

| Tool hints | Any hint on other turns | Right connector surfaced |
|---|---|---|
| Standalone (current) | 15.8% | 50% |
| Only under a shown connector | 9.7% | 35.5% |

**VS Code:** not tested. The user's check ran in the terminal CLI (`entrypoint: cli`); the VS Code extension shares the same plugin config.

**Cowork (merged experience, Claude Desktop on Linux): the router is not reachable.**
- The plugin was uploaded under Customize › Plugins (Yours › Created by you › Laya router).
- The test request did not create a local session. The newest `local-agent-mode-sessions` file is from 2026-09-16.
- The Desktop logs show why:
  - `workspace VM not supported (status=unsupported)`;
  - `grantRemoteSessionFolders: cse_…`, meaning the task ran in Anthropic's cloud and the local folder was bridged to it.
- The plugin's `laya-router serve` cannot start in the cloud, so no hint was given and nothing reached the local decision log.
- The Desktop's bridge to cloud sessions exposes device, file, artifact, built-in browser and memory tools, plus `+0 local-mcp`: MCP servers configured in the Desktop app itself.

**Follow-up spike** (the user chose to finish this branch first): register `laya-router serve` as a Desktop local MCP server so the bridge exposes `route` to cloud Cowork sessions. Open questions:
- Can a plugin hook call a bridged server?
- What skill and connector ids do cloud sessions use?
