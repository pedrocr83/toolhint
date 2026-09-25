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

### Re-run with the BM25 shortlist (user chose the hybrid, approach A)

typed-decisions, BM25 over name, connector and description, on GPU:

| K | dev skill top1/top3 | dev tool top1/top3 | test connector top1/top3 | skill P/R at picked τ | silent | test p50/p95 ms |
|---|---|---|---|---|---|---|
| **5** | **0.781 / 0.888** | 0.459 / 0.595 | 0.4 / 0.6 | 0.776 / 0.722 (τ 0.2) | 0.255 | 45 / 58 |
| 10 | 0.69 / 0.882 | 0.486 / 0.676 | 0.4 / 0.6 | 0.777 / 0.54 (τ 0.4) | 0.145 | 60 / 71 |
| 15 | 0.636 / 0.802 | 0.459 / 0.649 | 0.4 / 0.6 | 0.819 / 0.316 (τ 0.5) | 0.10 | 64 / 75 |
| BM25 alone | 0.765 / 0.84 | 0.378 / 0.595 | 0.111 / 0.533 | — | — | 0.5 / 2.1 |

**Gate lines, re-based (spec §12):**

| Criterion | Result |
|---|---|
| Dev top-3 skill recall ≥ 0.70 | **PASS** (0.888) |
| Beats BM25 on dev skill top-3 by ≥ 0.10 | **FAIL** (+0.05), accepted by the user |
| GPU p95 ≤ 250 ms | **PASS** (58 ms, with the GPU throttling at 80–84 °C) |
| Hook injects context | **PASS** |

**Other results:**
- dev_pt skill is 0.571/0.571 at every K.
- VRAM is 2424 MB, and there were 0 head overflows.
- english K10 reaches dev skill 0.711/0.856 but ranks `none` first on 58 of 187, and is silent on 54% of unlabeled turns.

**Defaults set (commit fbefbbe):**
- K is 5 for skills, 15 for connectors (all of them) and 5 for tools.
- τ is 0.2 for skills, 0.2 for connectors and 0.5 for tools.

K=5 beats K=10 on dev skill top-1 and top-3, and it holds precision 0.78 at a higher recall. It also keeps each choice at 6 options or fewer, inside Laya's calibrated temperature buckets. The cost is that gold outside the BM25 top-5 is unreachable (dev recall@5 is 0.89).

## Routing quality (Task 14 smoke test)

**Symptom.** `laya-router route "my pytest suite fails with a KeyError after the refactor, help me find why"` returned `change-report` 0.43, `chrome-devtools-mcp:troubleshooting` 0.32 and connector `playwright` 0.93.

**Root causes, found with systematic debugging:**
1. **The synthetic dev set hid shortlist misses on real phrasing.** It was written from the item descriptions. `eval/natural.jsonl` adds 96 scenario prompts (10 in Portuguese) that avoid the descriptions' wording.
2. **The BM25 tokenizer matched whole words only.**
   - "fails" never met "failure", so `systematic-debugging` scored 0.0 (rank 78 of 83).
   - Function words decided the top 5.
   - Accents split Portuguese words.
   - Natural skill recall@5 was 0.70.
3. **τ was calibrated only on labeled rows.** At τ 0.2, about 60% of real turns that used no skill or tool still got a hint.
4. **Connector choices had 14 options**, which falls into Laya's sharpened `choice:11+` temperature bucket. The raw 0.1006 is clamped to 0.5, which still doubles the logits.
5. **Duplicate skills split the probability.** `anthropic-skills:pptx` and `document-skills:pptx` got 0.30 + 0.22, so neither cleared τ.
6. **Connector labels were raw tool lists** ("Gmail tools: apply_sensitive_message_label, …"). Laya picked Slack for "draft a polite follow-up".

**Fixes (each RED → GREEN, suite green):**
- **Tokenizer:** fold accents, drop English and Portuguese stopwords, and split words longer than 4 characters into 4-grams. Natural recall@5 rose from 0.70 to 0.79, with no dev regression.
- **Calibration:**
  - `calibrate()` reports the alarm rate on 200 real unlabeled turns.
  - `pick_tau()` requires precision ≥ 0.75 and alarms ≤ 10%.
  - The eval calibrates on dev plus natural.
- **Connector K:** connectors follow K like the other kinds. At an equal alarm rate, K5 at τ 0.5 recalled as much as or more than all 13 at τ 0.8.
- **Duplicates:** equivalent items (same short key and label) merge into one option.
- **Connector labels:** a connector without server instructions is labelled by its most frequent tool-name words, e.g. "Gmail: message, thread, label, spam, draft, apply.".

**Result** (typed-decisions, K=5 for every kind, GPU p95 40–53 ms):

| kind | τ | precision | recall | hint of this kind on unrelated real turns |
|---|---|---|---|---|
| skill | 0.5 | 0.93 | 0.36 | 8.5% |
| connector | 0.6 | 1.0 | 0.36 | 5% |
| tool | 0.5 | 0.85 | 0.30 | 7.5% |

- Natural skill top-1/top-3 is 0.62/0.74, and natural connector top-1/top-3 is 0.68/0.88.
- Real connector top-1 is 0.40 (it was 0.22 before the label fix).
- All three smoke prompts (pytest, supplier follow-up, 6-slide deck) now return no hint. That means no false connector, and it also shows how conservative the router is.

**Any hint at all:** at these defaults, 16.1% of the 298 real unlabeled turns that would be routed get some hint (skill 5.7%, connector 5.0%, tool 7.7%). That is 14.9% of all 323 turns; 25 are skipped as short or slash commands. The per-kind rates above do not add up to a per-turn rate, and an earlier version of this section said "quiet on more than 90% of other turns", which overstated how quiet it is.

**Profile:** the router speaks on about a third of the prompts that need a skill or connector. When it speaks it is right about 9 times in 10, and it stays quiet on about 84% of other turns.

**Known gaps, deferred:**
- Prompts with no lexical overlap: the pytest prompt's skill shortlist still misses `systematic-debugging`.
- Workflow continuations, which would need the previous turn as context.
- Better connector labels would come from real server instructions; the tool cache does not capture them.
