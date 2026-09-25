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
