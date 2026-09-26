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

### Rulings, decisions and deferred minors (from the execution ledger)

- Task 1: Ruling: tasks/todo.md checkbox updates ride along in each task commit — user CLAUDE.md says mark items complete as you go — cost if wrong: one extra file per commit diff
- Task 1: Ruling: uv.lock not committed — user's ~/.gitignore_global ignores *.lock (explicit preference); direct deps pinned in pyproject — cost if wrong: transitive deps can drift; fix with git add -f uv.lock
- Task 2: Ruling: used --debug-file instead of --debug — CLI's `-d, --debug [filter]` takes an optional arg that could swallow the prompt — cost if wrong: none, same log content
- Task 2: Ruling: probe returns hookSpecificOutput JSON via a literal `"format": "hook"` input — debug log proved plain-text mcp_tool output lands in hook_success (model never sees it) — cost if wrong: none, sentinel then reached the model
- Task 2: Ruling: untracked spike/hook_probe/latest (symlink written by claude --debug-file) and ignored it — local artifact, absolute path — cost if wrong: none
- Task 3: Ruling: FINDINGS records two gate-relevant risks not in plan (2.3 GB VRAM per session; 11+ option choices uncalibrated) — surfaced for the gate decision rather than acted on now — cost if wrong: none, informational
- Task 5: Ruling: smoke test found 6 connectors vs plan's '7 or more' — newest Cowork session has 6 (Sentry only in an older session); data, not code — cost if wrong: none
- Task 9: Ruling: Cowork tool ids are mcp__<connector-uuid>__<tool> (30 transcript labels + session JSON uuid→name map) — plan assumed bare names; claude_ai_items(cc_names=False) now emits mcp__{uuid}__<tool> (bare name when no uuid) and dataset maps Cowork connector uuids to display names — tests test_claude_ai_items_use_cowork_uuid_tool_ids + test_cowork_rows_map_connector_uuid_to_name RED→GREEN, suite 43/43 — cost if wrong: Cowork tool hints would not match callable names
- Task 10: Ruling: synthetic.jsonl emitted by a throwaway scratchpad generator holding the hand-written prompts (not committed) — keeps JSON escaping correct — cost if wrong: none, the committed JSONL is the artifact
- Task 11: Ruling: added canonical_ids() + optional canon arg to evaluate/score_row/calibrate and a canon field on Inputs (not in brief) — implements the T10 carried ruling on duplicate skills — test test_evaluate_counts_equivalent_duplicate_skills_as_hits RED→GREEN, suite 50/50 — cost if wrong: scores for duplicated skills slightly optimistic
- Task 12: Ruling: ran scratch diagnostics beyond the brief (BM25 vs cosine shortlist recall, BM25-shortlist→Laya hybrid, latency breakdown, union shortlist + Portuguese) — gate failed and the options list needed a root cause, not guesses — cost if wrong: ~25 min extra GPU/CPU time; scripts stay in the scratchpad, product code untouched
- Task 12: Decision (user, 2026-09-25): hybrid on approach A — BM25 (name+connector+description) shortlist → Laya typed-decisions choice; embedding cache removed; skill gate criterion on dev set. Plan amended (Task 12 Steps 5–10; T13/T14/T15 embedding lines) and spec §12 — commit 60e46da — cost if wrong: prompts with no lexical overlap (e.g. Portuguese without English terms) get an arbitrary shortlist
- Task 12: Ruling: test_edited_item_text_refreshes_shortlist passes before the change — characterization test (old digest-keyed cache had the same property), kept to guard the lru_cache key — cost if wrong: none
- Task 12: Ruling: defaults K skill=5/tool=5 (amendment Step 10 guessed K=10) — BM25 re-run: K=5 dev skill top1/top3 0.781/0.888 vs K=10 0.69/0.882, better calibrated (skill P0.78/R0.72 at τ0.2 vs P0.78/R0.54 at τ0.4; tool P0.8/R0.32 vs R0.22), within Laya's calibrated ≤10-option buckets, p95 58 ms — cost if wrong: gold outside BM25 top-5 unreachable (dev recall@5 0.89 vs @10 0.92)
- Task 12: Ruling: test_head_budget_overflow_halves_shortlists now pins K=10 explicitly — it relied on the old default K; the behavior under test is halving, not the default — cost if wrong: none
- Task 13: Ruling: implemented the carried Task 2 ruling — route(..., format="text"); format=="hook" returns hook_output(hint) = {"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":hint}}, "" without a hint; tests test_route_hook_format_wraps_hint_for_user_prompt_submit + test_route_hook_format_is_empty_without_hint (RED with the module import, GREEN) — cost if wrong: none
- Task 14: Ruling: my style commit 038a1a2 put '# noqa' inside the STOPWORDS triple-quoted string (made 'word', 'block', 'literal'… stopwords) — fixed in the next commit with regression test test_content_words_survive_the_stopword_filter RED→GREEN; noqa now on the closing line — cost if wrong: none
- Task 14: Ruling: Step 5 smoke mismatch treated as "code wrong" → systematic debugging, 6 root causes, each fixed RED→GREEN in its own commit (natural eval set, tokenizer 4-grams+stopwords+accent fold, alarm-aware τ calibration, connectors follow K, duplicate-option merge, tool-keyword connector labels) — gate numbers were optimistic because the synthetic dev set borrows description wording and τ ignored false alarms — cost if wrong: ~2 h of work beyond the brief; router now conservative (≈⅓ recall at ≈0.9 precision)
- Task 14: Ruling: defaults K=5 all kinds, τ skill 0.5 / connector 0.6 / tool 0.5 (alarm-aware calibration on dev+natural vs 200 real unlabeled turns, max_alarm 0.10 is my choice) — K10 not better at the capped operating point and slower — cost if wrong: max_alarm 0.10 may be too strict or loose for the user's taste; LAYA_ROUTER_TAU overrides
- Task 14: Ruling: added eval/natural.jsonl (96 scenario prompts) and a natural split + calibration input — the plan had no realistic-phrasing eval — cost if wrong: prompts written by me, n=73 skill / 25 connector rows, still small
- Task 15: Ruling: hooks.json input adds "format": "hook" with test test_hook_asks_for_hook_json_output (carried Task 2 ruling) — plain-text mcp_tool output never reaches the model — cost if wrong: none
- Task 15: Ruling: README adds a "What to expect" paragraph (conservative recall/precision/alarm profile, ~2.4 GB VRAM per session, ~50 ms GPU / ~2 s CPU) — the user should know the operating profile before relying on it — cost if wrong: one paragraph to edit
- Task 15: Ruling: RouterService.load() runs one warm-up scores() call — measured warm load 4.3 s + first forward 1.4 s, later calls ~35 ms; test test_load_warms_the_model_before_the_first_prompt RED→GREEN — cost if wrong: one extra forward pass per session start
- Final: Ruling: Important 2 conflicts with spec §5 (read <cwd>/.mcp.json) — dropped project .mcp.json from the snapshot; spec §12 records the override — security over coverage — cost if wrong: project-scoped MCP servers are never suggested
- Final: Ruling: re-graded reviewer Minor 1 (decision-log write failure disabled routing) to Important — effect is the whole feature going silent on an unwritable path / full disk — fixed with test_an_unwritable_decision_log_keeps_the_hint RED→GREEN, suite 78/78
- Final: Ruling: re-graded reviewer Minor 5 (per-turn false-hint rate misstated as 5–8.5%) to must-fix — I had told the user that number; measured any-kind rate 16.1% of 298 routed real unlabeled turns (skill 5.7, connector 5.0, tool 7.7); README/FINDINGS/spec/todo corrected (65ec02f) — cost if wrong: none
- Final: Ruling: declined "VRAM ~2.4 GB per session" — stands, known risk in spec §12, approach C is the fix path — cost if wrong: ≥3 concurrent sessions fall back to CPU (~2 s/prompt)
- Final: Ruling: declined "CPU latency 1.5–2.6 s" — stands, accepted in spec §12 and README — cost if wrong: slow hints on CPU-only machines
- Final: Ruling: declined "conservative operating point" — user's call; surfaced with the LAYA_ROUTER_TAU knob — cost if wrong: few hints
- Final: Ruling: declined "continuations, zero-overlap and non-Latin prompts" — stands as documented deferred gaps — cost if wrong: no hints for those prompts
- Final: Ruling: declined "2000-char head cut loses a question typed after a long paste" — stands for now (spec requires a bound; head+tail cut is a possible follow-up) — cost if wrong: long pastes route on the paste, not the question
- Final: Ruling: declined "Cowork transcript_path shape, skill-id format, VS Code behavior" — pending the user's Task 15 Step 8 checks — cost if wrong: Cowork routed with the Claude Code catalog
- Final: Ruling: declined "route never refreshes the tool snapshot" — stands per spec §5 (explicit refresh/warmup) — cost if wrong: new MCP servers unsuggested until a refresh
- Final: Ruling: declined "names with punctuation beyond spaces" — stands, none of the user's connectors affected — cost if wrong: wrong tool ids for such a future connector
- Final: Ruling: declined "project-scope enabledPlugins, local-scope ~/.claude.json servers, namespaced commands/<dir>" — stands, not in spec §5 — cost if wrong: those items are not routed
- Final: Ruling: declined "decision-log retention (every prompt, 0644, no age limit)" — stands per spec §8 and the user's log-all-prompts preference; single-user machine — cost if wrong: other local accounts could read prompts
- Final: Ruling: declined "transitive drift without a lockfile" — stands per the user's *.lock global ignore — cost if wrong: a transitive upgrade breaks a fresh install
- Final: Ruling: declined "claude.ai connectors for Claude Code from the newest Cowork session JSON" — stands per spec §5 — cost if wrong: no claude.ai connectors in Claude Code for users who never used Cowork
- Final: Ruling: declined "no retry after a failed model load" — stands per fail-open semantics — cost if wrong: a transient load failure silences that session
- Final: minor (deferred): server INSTRUCTIONS invite optional route calls on turns without a hint (most turns) — reword or drop them under the plugin (e.g. serve --hooked)
- Final: minor (deferred): Gemini/Cursor/VS Code snippet harnesses route over the Claude Code catalog (ids that don't exist there) — connector-only mode or README note
- Final: minor (deferred): tool snapshot not filtered against currently enabled plugins/servers
- Final: minor (deferred): refresh rewrites the snapshot wholesale — a transiently failing server loses its cached tools
- Final: minor (deferred): load() publishes the engine before warm-up; a prompt in that ~1.4 s window pays the cold pass; log text says "without an engine"
- Final: minor (deferred): account-specific Cowork connector UUIDs committed in eval/synthetic.jsonl:207-212; eval build --out default is cwd-relative
- Final: minor (deferred): no LAYA_ROUTER_K_CONNECTOR; LAYA_ROUTER_TAU overwrites all three calibrated τ
- Final: minor (deferred): natural-pt rows not reported as their own split
- Final: minor (deferred): numpy and anyio imported directly but not declared in pyproject
- Final: minor (deferred): plan.md Global Constraints still list pre-amendment K/τ defaults
- Final: minor (deferred): no timeout on LayaScorer lock — a hung forward pass makes every later prompt wait the 5 s hook timeout
- Task 15: Ruling: Step 8 — VS Code not tested (user's check ran in the terminal CLI, entrypoint cli); Cowork unreachable: merged experience runs tasks in Anthropic's cloud (grantRemoteSessionFolders cse_…, workspace VM unsupported), so the plugin's local router cannot start — recorded in todo.md and README — cost if wrong: none
- Task 15: Decision (user, 2026-09-26): finish this branch, then a time-boxed spike registering laya-router as a Desktop local MCP server (bridge shows "+0 local-mcp") to reach cloud Cowork sessions

## Rename laya-router → toolhint (backlog REL-1, 2026-09-26)
- [x] Tests expect the new names (RED: 12 × ModuleNotFoundError toolhint)
- [x] `git mv src/laya_router src/toolhint`; rename ids, hint tag, env vars, paths, snippets (GREEN)
- [x] README and backlog.md (links, REL-1 done, EV-3 note on the old `[laya-router]` tag)
- [x] Suite, slow test and ruff as before; no stale names outside history docs (78 passed; slow 1 passed; ruff 5 = baseline)
- [x] Reinstall: plugin, uv tool, move decision log, delete old cache, warmup, live hint check
- [x] Rebuild the Cowork zip (`dist/toolhint-plugin.zip`); fast-forward main

### Review (rename)
- Old install removed: plugin `laya-router@layla`, marketplace `layla`, uv tool `laya-router`; `~/.cache/laya-router` deleted; decision log moved to `~/.local/state/toolhint/`.
- New install: uv tool `toolhint`; `toolhint warmup` → 365 Claude Code items, 131 Cowork items; plugin `toolhint@toolhint` (user scope). `catalog --refresh` skips our own server (7 servers refreshed).
- Live check: headless two-turn session e0e54e4c (tools disabled) → transcript holds `[toolhint] advisory, ignore if irrelevant — skills: anthropic-skills:morning (0.54)`; decision log 845 ms.
- Observed RT-3 live: three leftover `laya-router` servers from open sessions held 5.6 GB of the 8 GB RTX 3070 Laptop GPU, so new processes fell back to CPU (845–895 ms per route). Restarting those sessions frees it.

## Router fixes RT-1 to RT-6 (plan.md, 2026-09-26)
- [x] Task 1 · RT-5 label boilerplate stripped before the 80-char cut (options max 36 tokens, worst 6-option sum 213 of 240: Laya never truncates, so no per-decision token log)
- [x] Task 2 · RT-4 prompt view (code, tags, head+tail) and earlier request for short prompts
- [x] Task 3 · RT-3 device in every decision, one warning on GPU→CPU fallback (no auto-reload: it would fail again under the same memory pressure; RUN-1 is the fix)
- [ ] Task 4 · RT-6 per-session hint memory, reset on compaction
- [ ] Task 5 · RT-1/RT-2 evidence run and decision (rules A/B/C, option-count check)
- [ ] Task 6 · RT-1/RT-2 implement the decision
- [ ] Finish: suite, slow test, ruff baseline, live checks, fresh review, change report, local merge
