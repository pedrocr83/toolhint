# Benchmark: Claude Code with and without toolhint

**Goal:** a harness that runs realistic tasks in headless Claude Code sessions, with toolhint on and off. It compares each output against expected results, and records the skills, tools and tokens each run used.

**Decided with the user (2026-09-26):**
- **Tasks:** one coding-app task, plus two research variants, one working from fixed local sources and one from live web research.
- **Runs:** 3 per arm, on Sonnet.
- **Permissions:** `acceptEdits` plus a command allowlist.
- **Grading:** deterministic checks plus a Sonnet judge.

## How a run works (verified by probes on 2026-09-26)
- **Isolation:** every run gets a fresh workspace, `bench/runs/<stamp>/<task>/<arm>-<rep>/workspace`, which is its own git repo. The folder is gitignored.
- **Command:** `claude -p --input-format stream-json --output-format stream-json --verbose --model sonnet --permission-mode acceptEdits --allowedTools … --max-budget-usd … --no-session-persistence`. This is the user's real setup: all their plugins, hooks and CLAUDE.md. The flag keeps benchmark prompts out of `~/.claude/projects`, and so out of toolhint's eval extraction.
- **Off arm:** `--settings '{"enabledPlugins": {"toolhint@toolhint": false, "toolhint@synced": false}}'`.
  - Turning off only the local copy lets the synced Cowork upload load instead (seen in a probe).
  - Each run checks the `init` event: the on arm must show `plugin:toolhint:router` connected, and the off arm must show no toolhint plugin. A mismatch marks the run invalid.
- **Warm-up:** both arms wait before the prompt, 45 s by default, so the router's model has loaded. Without the wait, the first prompt of a session gets no hint.
- **Hints:** the stream carries no UserPromptSubmit hook output. So each run points `TOOLHINT_LOG` at its own `decisions.jsonl`; the probe confirmed the server inherits the env.
  - For a task's first prompt nothing is suppressed as a repeat yet, so the logged ranking is exactly the hint shown.
  - A record carrying the session's id proves the hook ran. A record with no session id is the model calling `route` itself.
  - The user's own decision log stays clean.
- **Metrics:** taken from the stream.
  - **Tools:** `tool_use` blocks, subagents included (`parent_tool_use_id`).
  - **Skills:** the `Skill` tool's input.
  - **Result event:** `usage`, `modelUsage`, `total_cost_usd`, `num_turns`, `duration_ms`, `permission_denials` and `subagent_stats`.
- **Judge:** `claude -p --model sonnet --setting-sources project --strict-mcp-config --tools "" --no-session-persistence`, run from an empty folder. The probe showed no hooks, no user plugins, no MCP servers, about 9.5k tokens of context, and about 0.02 USD a call.
  - `--bare` is not usable: it needs `ANTHROPIC_API_KEY`, and the user logs in with OAuth.
- **Order:** runs go one at a time; each on-arm session loads a 2.7 GB router on an 8 GB GPU. Arms alternate, with the starting arm flipped each rep, so drift over the session (rate limits, the web) hits both arms.

## Tasks
- **`coding-app`:**
  - **Brief:** a Python command-line expense tracker using only the standard library, with a pinned interface: `add`, `list`, `summary`, `delete`, JSON storage and exit codes. The prompt asks for tests too.
  - **Graded by:**
    - hidden acceptance tests, run after the session through a subprocess;
    - the agent's own tests;
    - the judge, who sees the spec, the code and the rubric.
  - **Proof the tests are right:** a reference solution under `reference/` passes every hidden test.
- **`research-local`:**
  - **Brief:** six fictional sources (Markdown, CSV and plain text) about a warehouse-software decision, with deliberate traps: a conflicting claim, a dependency and a deadline. The prompt asks for a COO brief in `BRIEF.md`, at most 600 words, citing sources.
  - **Graded by:**
    - a checklist of regex points, plus checks on word count, the number of distinct sources cited, and whether the file exists;
    - the judge, against `reference.md`.
  - **Proof the checklist is right:** `reference.md` passes every point.
- **`research-web`:**
  - **Brief:** a report on MCP transports and authorization, in `RESEARCH.md`, at most 700 words, with URLs.
  - **Graded by:** a checklist of stable facts (stdio, Streamable HTTP, SSE deprecated, JSON-RPC, OAuth 2.1, PKCE, RFC 9728/8707, and so on), at least 3 URLs including modelcontextprotocol.io, and the judge. The judge is told the reference may be out of date and must not penalize newer, sourced facts.

## Build (TDD for every pure part)
1. **Fixtures:** `bench/tasks/*`, with tests that the reference solution passes the hidden tests and that `reference.md` passes each checklist.
2. **`toolhint.bench.metrics`:** events plus decision records give tools, skills, subagents, denials, usage, cost, hints, uptake and the arm check.
3. **`toolhint.bench.grade`:** the hidden-tests runner and pytest summary parser, the checklist, and the judge command and its JSON parsing.
4. **`toolhint.bench.session`:** spawn, warm-up, prompt, read until the result or a timeout, then kill. Tested against a fake `claude` script.
5. **`toolhint.bench.report`:** a markdown table per task per arm (mean ± sd) plus a per-run table.
6. **CLI:** `python -m toolhint.bench`, with `--tasks`, `--reps`, `--arms`, `--model`, `--judge-model`, `--warmup`, `--dry-run` and `--report DIR`.
7. **Docs:** a `/bench` project command, a README section, and a `.gitignore` entry for `bench/runs/`.
8. **Smoke run:** 1 rep of `research-local`, both arms, on haiku with a small budget, checked end to end. Cost about 0.5 USD.

## Constraints
- Nothing is installed; the harness uses the repo's venv, and pytest is already a dev dependency.
- Hidden tests, reference solutions and reference answers are never copied into the workspace.
- Budget caps (USD) per run: coding-app 6, research-local 3, research-web 4. With the 121k-token setup context a session starts at about 0.45 USD on Sonnet.
- No file outside the repo is written, apart from what Claude Code itself writes for headless sessions.

## Review focus
1. **A wrongly labelled arm:** the off arm must never load any toolhint copy, and the on arm must be routed.
2. **Leaks:** a hidden test or reference must not end up in the workspace.
3. **Hangs:** a timed-out or crashed session must be killed and recorded, not stop the batch.
4. **Budget:** hitting the budget cap is recorded as such, not as a grading failure of the harness.
5. **Fair grading:** both arms are graded by the same code and the same judge prompt.
