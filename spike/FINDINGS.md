# Phase 0 spike findings

## Hook probe (Task 2) — Claude Code CLI 2.1.270

- **Sentinel reached the model:**
  - **no** when the tool returned plain text. out1 was "NONE". The debug log shows `Hook output does not start with {, treating as plain text`, and the text landed in a `hook_success` attachment, which the model only sees as "UserPromptSubmit completed".
  - **yes** when the tool returned hook JSON `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"LAYA_SENTINEL_42"}}`. out1 was "LAYA_SENTINEL_42", and the debug log shows `Hook UserPromptSubmit (plugin:laya-probe:probe/route) provided additionalContext (16 chars)`.
- **Hook args received (calls.jsonl):** prompt ok (exact text), cwd ok, transcript_path ok (`~/.claude/projects/<proj>/<session>.jsonl`), session_id ok.
  - A literal (non-`${}`) input value such as `"format": "hook"` is passed through unchanged.
- **`${CLAUDE_PLUGIN_ROOT}` expanded in .mcp.json command/args:** yes. The server started from `${CLAUDE_PLUGIN_ROOT}/../../.venv/bin/python`.
- **Empty result injects nothing:** yes. out2 was "NONE", and there was no `provided additionalContext` line for the probe.
- **Timing in `-p` mode:** the plugin server connected in 887 ms, before `UserPromptSubmit` ran, and the hook got its result in about 3 ms. The MCP connect timeout is 30000 ms.
- **Debug lines:**
  - `Hooks: mcp_tool calling plugin:laya-probe:probe/route with 5 arg(s)`
  - `Hook UserPromptSubmit (plugin:laya-probe:probe/route) provided additionalContext (16 chars)`
- **Side note:** at shutdown `SIGINT failed, sending SIGTERM to MCP server process`. It is harmless and the server exits cleanly.
- **Decisions for Tasks 13 and 15:**
  - The hook input field `${prompt}` is **confirmed**.
  - The `route` tool needs a `format` parameter. The hook passes the literal `"format": "hook"`. In that mode, `route` returns the hook JSON above when there is a hint, and `""` when there is none. Model-initiated calls keep the plain-text line.
- **Gate hook criterion:** **PASS**, provided the output uses the hook JSON format.

## Laya probe (Task 3)
- **Devices:** auto → actual device **cuda**. Load time was 9.0 s on auto, including CUDA init, and 0.42 s on CPU with the weights already cached. Peak VRAM was **2335 MB**, which is per process and therefore per session under approach A.
- **Predict**, 3 questions × (5 options + none):
  - auto: p50/p95 **121/153 ms**;
  - CPU: **1468/1596 ms**.
- **Embed:**
  - 1 text: p50 36 ms on auto, 190 ms on CPU;
  - 100 texts: p50 463 ms on auto, 2481 ms on CPU. This is a one-time catalog cost, because embeddings are cached on disk.
- **Head budget (default head):** n5, n10, n15 and n20 are all **ok**, as are heads 256 and 384. There is no overflow at 67-character labels.
- **Calibration warning (new):** the checkpoint "ships invalid temperatures ... using choice:11+=0.1006 -> 0.5. Treat confidence from the affected entries as uncalibrated." Choice questions with **11 or more options** therefore have uncalibrated probabilities, and K=10 plus `none` is exactly 11. The eval's K ∈ {5, 10, 15} comparison and the τ calibration expose the effect. K ≤ 9 keeps within the calibrated buckets.
- **Decisions:**
  - `LABEL_CHARS` stays 80, because the budget has headroom.
  - LayaScorer `device=None` (auto) works and picks CUDA, so no explicit device is needed.
  - Per-session VRAM of about 2.3 GB is flagged for the gate. Several concurrent sessions could exhaust the 8 GB card, and approach C (one shared process) would remove that cost.

## Gate (Task 12)

Data:
- **test:** 84 labeled transcript turns. Of these, 12 skill, 45 connector and 45 tool labels are in the catalog; 27 built-in Cowork tool labels count as unknown.
- **dev:** 224 synthetic prompts (187 skill rows and 37 connector/tool rows), including 12 in Portuguese.
- **silent rate:** measured on 200 unlabeled turns.

The full tables are in `eval/results/report-{cuda,cpu}.md`, which are local and gitignored. The diagnostics below came from scratch scripts, which are not committed.

### Gate as planned: cosine shortlist, then Laya choice

The gate rule picks the best configuration by test skill top-3, which gives `laya-typed-decisions-k5`.

| method | test skill top1/top3 | test connector top1/top3 | test tool top1/top3 | dev skill top3 | GPU p50/p95 ms |
|---|---|---|---|---|---|
| BM25 | 0.0 / 0.0 | 0.089 / 0.533 | 0.044 / 0.111 | 0.797 | 0.6 / 2.4 |
| cosine (typed-decisions encoder) | 0.083 / 0.083 | 0.067 / 0.178 | 0.0 / 0.022 | — | 48 / 127 |
| Laya typed-decisions K5 | 0.167 / 0.167 | 0.4 / 0.6 | 0.089 / 0.089 | 0.332 | 307 / 413 |
| Laya typed-decisions K10 | 0.167 / 0.167 | 0.4 / 0.6 | 0.044 / 0.156 | 0.487 | 393 / 522 |
| Laya typed-decisions K15 | 0.0 / 0.167 | 0.4 / 0.6 | 0.067 / 0.133 | 0.529 | 344 / 439 |
| Laya english K15 | 0.083 / 0.167 | 0.356 / 0.644 | 0.111 / 0.111 | 0.578 | 123 / 184 |

**Gate lines:**

| Criterion | Result |
|---|---|
| Top-3 skill recall ≥ 0.70 | **FAIL** (0.167) |
| Beats BM25 by ≥ 0.10 | **PASS**, but only because BM25 scores 0.0 |
| GPU p95 ≤ 250 ms | **FAIL** (413 ms) |
| Hook injects context | **PASS**, when the tool returns hook JSON (Task 2) |

**Other results:**
- **dev_pt**, typed-decisions K10: skill 0.143/0.286 (7 rows), connector 0.8/1.0 (5 rows).
- **Picked τ**, typed-decisions K10 on dev:
  - skill 0.6 (P 0.78, R 0.21);
  - connector 0.2 (P 0.89, R 0.65);
  - tool 0.35 (P 0.07, which makes tool picks useless at any τ).
- **Silent on unlabeled turns** (K5 / K10 / K15):
  - typed-decisions 0.22 / 0.105 / 0.055;
  - english 0.62 / 0.55 / 0.505.
- **Resources:** peak VRAM is 2552 MB per process, and every run had 0 head overflows.
- **CPU**, typed-decisions K10 on 60 rows: p50/p95 is 1629/2590 ms on real prompts and 1502/1934 ms on dev. That is too slow for a hook on every prompt, though it stays within the 5 s hook timeout.

### Why it failed

1. **The shortlist is the bottleneck, not the choice.**
   - Mean-pooled Laya encoder vectors are weak retrieval embeddings; Laya's own docstring says a dedicated bi-encoder shortlists better.
   - Dev skill recall@10 is 0.51 for cosine with either encoder, against 0.90 for BM25 (0.92 with the item name added).
   - Dev tool recall@10 is 0.03–0.11 for cosine, against 0.68–0.73 for BM25.
   - Laya's dev skill top-3 at K5/10/15 (0.33/0.49/0.53) tracks cosine recall@K (0.33/0.51/0.59). Once the gold item makes the shortlist, Laya almost always ranks it in the top 3.
2. **Most real skill labels are workflow continuations.**
   - About 7 of the 12 known skill labels follow short replies such as a bare option number, "implement" or "try again". Their skill comes from the previous turn, not from the prompt, so no prompt-only router can recover them: BM25 recall@10 is 0.08 and cosine 0.17–0.25.
   - Many of the Cowork connector and tool labels are Gmail follow-ups of the same kind. That is why Laya ranks `none` first on 35 of the 45.
3. **The run environment inflated the latency numbers.**
   - A breakdown taken minutes later, with the same code and 40 real prompts, measured:
     - cosine path: p50 85–98 ms, p95 124–127 ms (choose 70–85 ms, query embed about 15 ms, shortlist about 1.5 ms);
     - BM25 path: p50 73–78 ms, p95 105–151 ms.
   - The main run was slow at the start and faster later, and english also ran about 2× slower than in later runs.
   - The GPU idled at 75 °C afterwards, so thermal throttling during the 15-minute sustained run is the likely cause. This is not proven.

### Candidate fix measured: BM25 shortlist, then Laya choice

Setup: typed-decisions, BM25 over name and description, K=10 for skills and tools, all connectors, 80-character labels.

| dev (synthetic) | skill top1/top3 | connector top1/top3 | tool top1/top3 |
|---|---|---|---|
| BM25 alone (name + description) | 0.765 / 0.84 | 0.757 / 0.838 | 0.378 / 0.595 |
| cosine → Laya K10 (as planned) | 0.406 / 0.487 | 0.757 / 0.892 | 0.027 / 0.027 |
| **BM25 → Laya K10** | 0.69 / 0.882 | 0.757 / 0.892 | 0.486 / 0.676 |

- **Real (test) results:**
  - connector top1/top3 0.40/0.60, against 0.11/0.53 for BM25 alone;
  - skill 0/0, because of the continuations;
  - tool 0.067/0.133.
- **Run stats:** GPU p95 was 67–73 ms in the diagnostic session. Silent rate 0.16, τ skill 0.4 and connector 0.2, 0 overflows.
- **english with the same shortlist:** skill 0.711/0.856 and tool 0.514/0.676. It ranks `none` first on 58 of 187 dev skill rows (typed-decisions: 4) and is silent on 55% of unlabeled turns.
- **Other variants:**
  - 200-character labels gain 0.006 skill top-3, lose 0.04 real connector top-1 and add 7 ms, so they are not worth it.
  - Dropping the tool question saves 5–15 ms and loses the tool hints.
- **Portuguese** (7 skill rows, too few to conclude):
  - BM25 → Laya reaches skill top-3 0.571, against 0.286 for cosine → Laya.
  - BM25 recall@10 is 0.571, against 0.286 for cosine, because the PT prompts carry English technical terms.
  - A union shortlist (7 BM25 picks plus 3 cosine picks) gave the same PT result, +0.05 English skill top-1 and −0.005 top-3, at a cost of 15–25 ms. It is not worth keeping the embedding cache for.
- **Caveat:** the dev prompts were written from the item descriptions, which favours BM25.
  - On skills, the hybrid beats BM25 alone by only 0.04 top-3 and loses 0.075 top-1.
  - Laya's measured value over BM25 is:
    - routing real phrasing to connectors (+0.29 top-1);
    - tool top-1 (+0.11 on dev);
    - the ability to abstain.
