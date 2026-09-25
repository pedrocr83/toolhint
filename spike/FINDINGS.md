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
