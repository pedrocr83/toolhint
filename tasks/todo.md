# laya-router — task tracker

Plan: `plan.md` · Spec: `docs/superpowers/specs/2026-09-25-laya-router-design.md`

## Phase 0 — foundation, spikes, gate
- [ ] 1. Scaffold + dependencies (laya, mcp, pyyaml, pytest)
- [ ] 2. Spike: `mcp_tool` UserPromptSubmit hook probe (CLI)
- [ ] 3. Spike: Laya load/latency/VRAM/head budget
- [ ] 4. Catalog: skills + slash commands
- [ ] 5. Catalog: connectors, tools, `discover()` + TTL
- [ ] 6. Tool cache refresh (local stdio MCP servers)
- [ ] 7. Engine: shortlist, choice + none, thresholds, caches
- [ ] 8. Hint format + Laya scorer
- [ ] 9. Eval dataset from transcripts
- [ ] 10. Synthetic dev prompts (+ Portuguese)
- [ ] 11. Eval runner: BM25 vs cosine vs Laya, calibration, gate lines
- [ ] 12. GATE: user go/no-go

## Phase 1 — build (only after gate passes)
- [ ] 13. Decision log + MCP server
- [ ] 14. CLI
- [ ] 15. Plugin, marketplace, snippets, README, live verification (CLI, VS Code, Cowork)

## Review
Filled in during execution: gate results, deviations from plan, verification outcomes, lessons.
