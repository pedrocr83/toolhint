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
- [ ] 13. Decision log + MCP server
- [ ] 14. CLI
- [ ] 15. Plugin, marketplace, snippets, README, live verification (CLI, VS Code, Cowork)

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

