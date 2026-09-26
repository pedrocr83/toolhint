# Router fixes (backlog RT-1 to RT-6)

- **Scope:** backlog items RT-1 to RT-6. The user approved it on 2026-09-26 ("do the router fixes").
- **Branch:** `feat/router-fixes`, from `main` at `0bbea65`. Nothing is pushed until the user says so.
- **Earlier plan:** the build plan now lives in `docs/superpowers/plans/2026-09-25-laya-router-plan.md`.

## Evidence gathered before planning

- **Multi-item turns are common.** Across 137 labeled real turns, the share using two or more distinct items is 21% for skills, 16% for connectors and 56% for tools. Today at most one item per kind can pass τ (backlog RT-1).
- **Skill timing.** Of 48 skill turns, the skill is the turn's first tool call in 16. In 12 it comes after 1–6 tool calls, and in 20 (42%) after more than 6.
- **Labels already fit Laya's budget.**
  - Labels are one sentence of at most 80 characters (`catalog.one_line`), so 6 options stay well below Laya's 256-token option budget.
  - The waste is boilerplate: 24 of 87 skill labels start with "Use when…", "Use this…" or "This skill…".
- **The GPU is full.** Leftover per-session servers hold 5.6 of 8 GB, so eval runs on CPU at about 1.8 s per prompt.

## Global constraints

- **Behavior:** fail-open everywhere, and the hint stays at or under 400 characters.
- **Dependencies:** no new dependencies; `laya==0.3.20` is unchanged.
- **Testing:** tests come first, with `FakeScorer`.
- **Lint:** ruff stays at its 5 baseline issues.
- **Private data:** anything derived from transcripts stays in `eval/data` and `eval/results`, both gitignored.

## Tasks

### Task 1 · RT-5 · Strip label boilerplate before the 80-character cut
- **Change:** `catalog.make_item` removes a leading "Use when…", "Use this skill when/to/for…" or "This skill should be used when…" before `one_line`. The BM25 text stays unchanged.
- **Tests:**
  - Boilerplate is stripped.
  - The distinguishing words survive the 80-character cut.
  - Other labels are unchanged.
- **Measure once with Laya's tokenizer:** the longest option at 6 options, before and after the change.
- **Ruling:** if nothing is truncated, per-decision token logging is not needed.

### Task 2 · RT-4 · A better view of the prompt
- **`engine.prompt_view(prompt)`:**
  - Fenced code becomes `[code]`.
  - Tag blocks are removed, reusing `dataset.TAG_BLOCK`.
  - Past 2000 characters, it keeps the first 1200 and the last 800 characters.
- **Short prompts (under 60 characters):**
  - The server reads the previous user prompt from `transcript_path`.
  - `dataset.previous_prompt` reads at most the last 256 KB, reuses `prompt_text` and skips the current prompt.
  - The server passes it to `Engine.rank(..., previous=)`, so Laya's state becomes `{"request": …, "earlier request": …}`.
- **Tests:**
  - The `prompt_view` cases.
  - `previous_prompt` reads only the tail and skips tool results, meta entries and the current prompt.
  - The earlier request is added only for short prompts.

### Task 3 · RT-3 · The device in every decision; a single warning on a GPU→CPU fallback
- **Change:**
  - The `Scorer` protocol gains `device`.
  - `LayaScorer.device` reads the agent's current device, and a drop from CUDA to CPU logs one warning.
  - `Ranking.device` carries it, and so does the decision log.
- **Tests:** a fake `laya.Router` for `LayaScorer`, and the device field in the log.
- **Ruling:** no automatic reload on the GPU. Under the same memory pressure it would fail again; the real fix is RUN-1.

### Task 4 · RT-6 · Session memory for hints
- **Remember per session:** `RouterService` remembers which item ids it has already hinted in each session. Repeats are dropped from the hint, and "" is returned when nothing is new. The map holds at most 64 sessions, evicting the oldest first.
- **Reset on compaction:**
  - `route(event="compact")` clears that session's memory.
  - `hooks.json` adds a SessionStart hook with matcher `compact` that calls `route` with `{session_id, event: "compact"}`.
- **Tests:**
  - A repeat is suppressed.
  - Other sessions are unaffected.
  - Compaction resets the memory.
  - The hook entry exists.
- **Live check:** compaction in a headless session, if the CLI allows it; otherwise record it as unverified.

### Task 5 · RT-1 + RT-2 · Evidence run and decision
- **Scoring run:** score the final pipeline once on CPU and store the probabilities under `eval/results`. The inputs are dev (224), natural (96), transcripts (84) and negatives (200).
- **Rules compared per kind, on the same scores, at precision ≥ 0.75 and false alarms ≤ 10%:**
  - **A** (today): the top candidate, when `p ≥ τ`.
  - **B:** the top candidate, when `r = p / (p + p_none) ≥ τ′`. Under a softmax, r depends only on that item and "none", not on the other options.
  - **C:** every candidate with `r ≥ τ′`, up to the caps (3/2/3). This is the multi-pick rule.
- **Measuring multi-pick precision:**
  - Per hint: is the gold item in the shown set?
  - Per item: how many shown items are gold?
  - For real transcript rows, every item used in the turn counts as gold.
- **Option-count check:** on a labeled subset, shrink the pools to 2 and 3 candidates. Compare how much `p_gold` and `r_gold` move under Laya's per-option-count temperatures and under one pinned temperature (the 6–10 option value).
- **Decision:**
  - Adopt C if its recall is at least A's for every kind, with per-item precision at least 0.6.
  - Otherwise adopt B if it is no worse than A.
  - Otherwise keep A, and record why.
- **Outcome (2026-09-26):** A kept. B and C lose recall on every kind (skill 0.335 → 0.085, connector 0.355 → 0.177, tool 0.355 → 0.194), because r ≥ p lifts negatives too. Pinning the temperature makes the option-count drift worse, not better. The run also showed RT-5 costs 5 skill hints of 260, so Task 1 is reverted. Details in `tasks/todo.md`.

### Task 6 · RT-1 + RT-2 · Implement the decision
- **Code:** `engine._select` and `evaluate.shows`/`calibrate` switch to the chosen rule. `LayaScorer` pins every choice temperature to the 6–10 option value, if Task 5 supports it.
- **Settings and docs:**
  - Recalibrate `DEFAULT_TAU`.
  - Update the README's "What to expect" section.
  - Update the backlog's status.
- **Tests:**
  - Two items at 0.4 each with "none" at 0.2 give two picks.
  - "None" on top still means no hint.
  - The caps are honored.
  - The temperatures are pinned.
- **Outcome:** no code change. Task 5 chose A with Laya's own temperatures, so these tests have nothing to pin.

### Finish
- Run the full suite, the slow test and ruff (baseline).
- Do a live `toolhint route` and a headless hook check.
- Get a review from a fresh reviewer, then write the change report.
- Merge into local `main` without pushing.

## Review focus

1. **Hook latency:** `previous_prompt` reads only the transcript's tail, and only for short prompts.
2. **Fail-open:** transcript read errors, a missing `session_id` or a device read error must never break routing or the log.
3. **Memory:** session memory holds item ids only, is bounded per session, and holds at most 64 sessions.
4. **Deduplication:** it must not leak across sessions, and it must reset after compaction.
5. **Fair comparison:** every rule is compared on the same stored scores, with n reported, and nothing is chosen after the fact.
