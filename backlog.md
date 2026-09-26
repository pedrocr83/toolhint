# Backlog

Compiled 2026-09-26 from:
- a review of about 45 public repos, papers and docs on Laya/Jev routing and context cleaning;
- a check of each finding against our own code.

Themes group the items; the roadmap orders them.

**How to read an item:**
- **Format:** `ID · title · effort · priority`.
- **Effort:** S = hours, M = days, L = a week or more.
- **Priority:** Now, Next or Later.
- **Evidence:** names the source. A repo written as `owner/repo` lives at `github.com/owner/repo`.
- **How far to trust each fact:**
  - Facts about our own code and Claude Code's docs were verified at the source.
  - External numbers come from reviewers who read those repos, and were spot-checked rather than reproduced.
  - *(claimed)* marks a number with no published data behind it.

## Decisions the research supports

1. **Keep the core design.**
   - The design: keyword shortlist (BM25), then one Laya choice per kind with a "none" option, then a per-kind threshold τ calibrated on real transcripts.
   - No other project routes skills, connectors and tools together with that kind of calibrated "none" answer.
2. **Do not use Jev as a context-cleaning judge**, hosted or imitated with a local model. See the verdict under "Context cleaning". Build the cleaning *mechanism* with deterministic, reversible rules instead.
3. **Do not use Laya to judge which tool output or history is relevant.**
   - Its AUC is 0.45–0.47 on keep/drop decisions (below trivial rules).
   - On passage ranking it scores at the BM25 floor.
4. **Stay on laya 0.3.20** (the latest PyPI release) and upgrade at the next release (RUN-10). `main` carries unreleased fixes under the same version string.
5. **Hosted Jev is only ever an opt-in backend.** Never train or calibrate on its outputs; its terms forbid that.
6. **Rename before publishing (REL-1).** At least 8 GitHub repos already use a "laya-router" variant, and the name reads like Laya's own `laya.Router` class.

## Roadmap

**Now:** release prep and cheap fixes inside the current design.

| Group | Items |
|---|---|
| Release | REL-1, REL-2, REL-3, REL-4 |
| Cowork | COW-1 |
| Router fixes | RT-1, RT-3 to RT-6 |
| Recall | REC-1 |
| Evaluation | EV-1, EV-3 |
| Privacy | SEC-1, SEC-2 |
| Runtime | RUN-3, RUN-4, RUN-5 |
| Housekeeping | HK-1 to HK-9 |

**Next:** the bigger levers.

| Lever | Items |
|---|---|
| Shared background process | RUN-1 |
| Context cleaning v1 | CLN-1 to CLN-4 |
| Skill listing | CTX-1 |
| Recall | REC-2, REC-3, REC-4, REC-7 |
| False alarms | FA-1, FA-2, FA-3 |
| Scorer backends | SCO-1, SCO-2 |
| Install | INS-1, INS-2 |
| Security and UX | SEC-3, SEC-4, UX-1 |
| Learning from usage | LRN-1, LRN-2 |

**Later:** experiments and bigger bets.

| Theme | Items |
|---|---|
| Recall | REC-5, REC-6, REC-8 |
| False alarms | FA-4 |
| Context listings | CTX-2, CTX-3, CTX-4 |
| Context cleaning | CLN-5 to CLN-8 |
| Scorer backends | SCO-3, SCO-4 |
| Learning from usage | LRN-3 to LRN-6 |
| Runtime | RUN-2, RUN-6 to RUN-10 |
| Install | INS-3 to INS-6 |
| Evaluation | EV-2, EV-4, EV-5, EV-6 |
| Cowork | COW-2 |
| Router fixes | RT-2 |

---

## REL: Release prep

- [x] **REL-1 · Rename the project · M · Now**
  - **Do:**
    - Pick the name. Recommended: `toolhint`; the alternative is `hunch-router`. Both are unused on GitHub and free on PyPI.
    - Rename in one commit:
      - the package name and command in `pyproject.toml`, and the `src/laya_router` folder;
      - the plugin, marketplace and hook ids;
      - the `[laya-router]` hint tag;
      - the `LAYA_ROUTER_*` environment variables;
      - the state and cache paths;
      - the config snippets, README and tests.
    - Reinstall the uv tool and the Claude Code plugin, and rebuild the Cowork zip.
    - Keep the dated specs and plans as history.
  - **Why:** the name collides with other repos and implies it is an official Laya component.
- [x] **REL-2 · Remove private data before going public · S · Now**
  - **Done 2026-09-26:** rewrote all 43 commits. The 6 rows now keep connector-level gold only, and author and committer use the GitHub noreply address.
  - `eval/synthetic.jsonl` contains 6 lines with real Cowork connector UUIDs. Git history keeps them, so either scrub the history or publish a fresh single squashed commit.
  - Optionally rewrite the commit author email to the GitHub noreply address.
- [x] **REL-3 · Merge `feat/laya-router`** into `main`. Done 2026-09-26 (fast-forward). · S · Now
- [ ] **REL-4 · Publish the repo · S · Now**
  - Run `gh auth login`.
  - Write a description that mentions Laya, and add the topics `laya`, `claude-code`, `mcp` and `agent-skills`.

## RT: Fix the current router (all verified in our code)

- [x] **RT-1 · Allow more than one pick per kind · S + M · Now**
  - **Closed 2026-09-26, not adopted.** Real turns do use several items: 28% of skill turns, 16% of connector turns and 53% of tool turns use two or more. But on the same stored scores, at precision ≥ 0.75 and false alarms ≤ 10%, the relative rule loses recall on every kind. Top pick only: skill 0.335 → 0.085, connector 0.355 → 0.177, tool 0.355 → 0.194. Multi-pick does no better. The cause: `p / (p + p_none)` is never below `p`, so prompts that need nothing score high too, and τ′ has to rise to 0.8–0.9. Numbers in `tasks/todo.md`.
  - **Problem:**
    - [engine.py:171](src/toolhint/engine.py#L171) keeps items with `p ≥ τ`, and Laya's choice is one softmax whose probabilities add up to 1. With τ at 0.5 or 0.6, at most one item per kind can ever pass, so the caps of 3/2/3 never matter.
    - When two items are relevant, they split the probability and both can miss τ.
  - **Do:**
    - First measure how many eval turns have two or more correct items.
    - Then add a relative rule: keep item *i* when `p_i / (p_i + p_none) ≥ τ′_kind`. It needs no extra model calls.
    - Recalibrate on multi-item turns under the same false-alarm budget.
  - **Evidence:**
    - janmejai2002/gutcheck: 17% of its test prompts need 2–3 items, and it only gets multiple picks by using a 0.2 threshold.
    - pilotspace/laya-codex, 0xSarnavo/laya-coding-router.
- [ ] **RT-2 · Calibrate per option count · S · Later**
  - **Measured 2026-09-26; stays open.**
    - The problem statement below is backwards. On 150 labeled prompts, shrinking the pool from 5 candidates to 1 raises `p_gold` by 0.24 on average, and to 2 raises it by 0.06. Small pools inflate p; they don't flatten it.
    - Pinning every temperature to the 6–10 value makes the drift worse (0.36 and 0.17).
    - Both local catalogs have at least 6 items of every kind, so only users with fewer than 5 items of a kind are affected.
    - Fitting τ per option count needs prompts that need nothing, scored at small pool sizes. Not done, and K is not in the decision log yet.
  - **Problem:**
    - The typed-decisions checkpoint's `temperature_by_options` is an exact copy of the base checkpoint's (verified in the cached configs).
    - Laya divides by T = 1.76 for 3–5 options but T = 1.00 for 6–10. Our τ was tuned at 6 options.
    - Pools of 4 or fewer items (for example a user with 2–4 MCP servers), or shortlists halved after an overflow, get flatter probabilities, so hints almost never fire.
  - **Do:**
    - Fit our own temperature or τ per (kind, option-count group) on our labels, and override `agent.temperature_by_options` after loading.
    - Record K in the decision log.
  - **Evidence:**
    - PerryLink/laya-mcp `calibration.py`: at least 30 samples per group, otherwise no adjustment.
    - omkarghugarkar007/system-one-model-finetuning `TemperatureMap`.
    - wuyoscar/jev-skill `references/calibration.md`: "do not transfer thresholds silently across K".
- [x] **RT-3 · Detect the silent fallback from GPU to CPU · S · Now**
  - **Done 2026-09-26:** every decision logs its device, and the server warns once on a fallback. There is no automatic reload, since it would hit the same memory pressure. RUN-1 is the fix.
  - **Problem:** after any CUDA out-of-memory error, laya 0.3.20 moves the model to CPU for the rest of the process (`laya/agent.py:625-635`) and only prints a warning. At 2.4 GB per session, a few parallel sessions can trigger it, and routing then takes about 2 s a turn.
  - **Do:** log the device with every decision. On a fallback, reload on the GPU or report a degraded state (SEC-4). RUN-1 makes it much less likely.
  - **Seen live 2026-09-26:** three per-session servers held 5.6 GB of an 8 GB RTX 3070 Laptop GPU; the next process fell back to CPU (845–895 ms per route).
- [x] **RT-4 · Give Laya a better view of the prompt · S · Now**
  - **Done 2026-09-26:**
    - Code fences and tag blocks are collapsed, and long prompts keep their start and end.
    - Prompts under 60 characters also carry the previous prompt.
    - `project` is not added.
    - **Effect on the eval sets:** neutral, apart from 2 fewer false tool hints out of 323. Their prompts are already cleaned when extracted.
    - **Live prompts:** 5 of 20 logged hook prompts carried tag blocks, and 8 were under 60 characters.
    - **Review fix:** compaction summaries and interrupt markers no longer count as prompts, and the transcript tail read is up to 4 MB. "Short" is judged on the cleaned view. Replayed over every local short prompt that has an earlier one, 120 of 121 now get the right earlier prompt (55 before), and the worst read takes 20 ms.
  - **Do:**
    - Keep the start and the end of long prompts instead of only the first 2000 characters ([engine.py:140](src/toolhint/engine.py#L140)). A pasted log with the question at the end currently loses the question.
    - Strip fenced code, pasted logs and `<system-reminder>` blocks.
    - When the prompt is under about 60 characters ("ok do it"), add the previous user prompt, read from `transcript_path`.
    - Optionally add `project: basename(cwd)`.
  - **Evidence:**
    - rabi/pi-laya-router `classifyState`: keeps the prose at the end.
    - ericmjl/pi-laya-skill-router: its minimum-length rule.
    - mmornati/system-one-router `trimMiddle`.
    - SupremeDreamZ/laya-code-router `newTurnPrompt`.
    - 0xSarnavo: the `{prompt, project}` state.
  - **Risk:** an earlier topic can leak into routing, so watch the false-alarm rate.
- [x] **RT-5 · Fit Laya's option budget · S · Now**
  - **Closed 2026-09-26:**
    - **No truncation happens.** The longest option is 36 tokens, and the worst 6-option total is 213 of 240.
    - **Boilerplate stripping was tried and reverted.** On the same GPU, over 260 labeled skill prompts, 4 correct hints were gained and 9 lost. All 9 were still ranked first but fell below τ.
  - **Problem:**
    - On typed-decisions, the options share a 256-token budget.
    - With 6 options, once they total more than about 240 tokens, each is cut to 40 tokens, and the instruction to whatever is left (at least 8 tokens). This is `build_sequence` in `laya/common.py`.
  - **Do:**
    - Put the distinguishing words first.
    - Strip boilerplate such as "Use this skill when…".
    - Log per-option token counts and truncations.
    - Optionally A/B `head_max_len=384` per call.
  - **Evidence:**
    - PerryLink/laya-mcp: token-budget preflight.
    - AdelysAlberto/pi-laya-router: `plan/laya-api-contract.md`.
    - Upstream Laya's browser-agent fine-tune notes: raising `head_max_len` helped.
- [x] **RT-6 · Session memory for hints · S · Now**
  - **Done 2026-09-26:**
    - An item is hinted once per session. The memory holds ids only, for at most 64 sessions.
    - A `SessionStart` hook with matcher `compact` clears it.
    - **Verified live:** after `/compact` the hint came back. With the hook removed, it stayed silent.
    - **Opt-in, from plugin 0.2.0:** the hook passes `"dedupe": true`. An older cached plugin copy, which has no compaction hook, keeps getting repeats rather than losing hints for good. This was verified live with main's `hooks.json`.
  - **Do:**
    - Don't repeat an identical hint within a session.
    - Re-send the active hints after compaction, using a SessionStart hook with matcher `compact`. Verify that `mcp_tool` hooks run for that source; the docs say they are skipped at launch because servers aren't up yet.
  - **Evidence:**
    - pilotspace/laya-codex: per-session memory.
    - ericmjl: deduplication that resets on compaction.

## REC: Recall (today about 1/3)

- [ ] **REC-1 · Measure where recall is lost · S · Now**
  - Compare how often the right item is in the BM25 top 5 against final recall, per kind. That decides whether to fix the shortlist or the chooser.
  - **Evidence:** SkillRouter (arXiv 2603.22455) shows the first stage caps everything: BM25 has the right skill in its top 20 only 36.5% of the time, against 75.4% for a trained embedder.
- [ ] **REC-2 · Give BM25 more text per item · S–M · Next**
  - **Do:**
    - Index the first ~2,000 characters of each SKILL.md body, weighted lower.
    - Add 1–2 real past prompts per item, taken from the training split only.
    - Optionally add synthetic trigger phrases generated offline with the prompt "write a request that needs this skill; don't name it".
  - **Evidence:**
    - SkillRouter: removing the skill body costs 37–44 points, though that was on an 80k-skill pool.
    - glukicov/laya_router: example-led option wording raised accuracy from 0.600 to 0.639 (in-sample).
    - conorluddy/AgentLoadout: per-tool `tags`.
  - **Risk:** leaking eval data into the index. Keep the test split clean.
- [ ] **REC-3 · Strip "do not use for…" sentences from BM25 text · S · Next**
  - **Why:** those sentences attract exactly the prompts they rule out.
  - **Do:** optionally pass them to Laya as "not for: …" if the option budget allows (RT-5).
  - **Evidence:** angel291592/Intent-Router `references/domains.md`.
- [ ] **REC-4 · A/B the typed-decisions checkpoint against Laya's standard English one · S · Next**
  - **Mixed evidence:**
    - The model card calls typed-decisions a specialist for four synthetic workflows, and uncalibrated.
    - In laya-codex, typed-decisions scored MRR 0.441 against 0.479 for the standard checkpoint.
    - In jabr/classifier-benchmark, typed-decisions was 3.7 points better.
  - **Note:** the English checkpoint has smaller limits: 512 tokens for the prompt and 192 shared by the options, about 29 tokens each at 6 options.
- [ ] **REC-5 · Add embedding search to the shortlist · M · Later**
  - **Do:**
    - Merge embedding search with BM25 using reciprocal rank fusion (k = 60).
    - Use a small multilingual embedder, because Portuguese is needed.
    - Cache item vectors at `catalog --refresh`.
    - Keep the Laya choice at 5–10 options.
  - **Evidence:**
    - janmejai2002/gutcheck: the right item is in the top 5 94.4% of the time with bge-base int8, on synthetic labels.
    - SkillRouter.
  - **Alternative:** `laya.shortlist.embed_fn_from_agent` needs no download, but its own docstring says it is weaker, and our earlier cosine-similarity attempt failed our gate.
  - **Needs:** a new dependency, so ask first.
- [ ] **REC-6 · Two-tier hint · S · Later**
  - **Do:** confident picks, plus a names-only "also relevant" tier, shown only when "none" is unlikely and within the false-alarm budget.
  - **Evidence:** gutcheck `render_context`. On synthetic data, 95% of needed items were at least named, against 65% loaded.
  - **Risk:** noise.
- [ ] **REC-7 · Hints in the middle of a turn · M · Next**
  - **Why:** in ericmjl's data, 53 of 59 skill uses happened after more than 6 tool calls. A hint at prompt time cannot catch those.
  - **Do:**
    - After each batch of tool calls, route on the latest request plus recent tool activity, taken from the end of the transcript.
    - Deliver it through `PostToolBatch` → `hookSpecificOutput.additionalContext`. It is verified in the hooks docs: injected once, before the next model call, up to 10,000 characters.
    - Only hint when a new item clears τ, deduplicate, and rate-limit.
  - **Evidence:**
    - The Claude Code hooks docs.
    - ericmjl's RESULTS.md.
    - Dicklesworthstone/skillranker: builds its input from the transcript tail, but only at prompt time. Its license rider means ideas only.
  - **Needs:** RUN-1 and a GPU for latency.
  - **Risk:** hint fatigue.
- [ ] **REC-8 · Per-candidate second check (experimental) · M · Later**
  - **Do:** for the top 2–3 candidates, add a yes/no question per candidate in the same call: "does X do the specific thing requested?", with described true/false outcomes.
  - **Evidence:**
    - TypeSafe's skill-suggestion cookbook, rerank step.
    - 0xSarnavo's question wording.
  - **Risk:** Laya's untrained yes/no answers are weak. With the default true/false labels it answered "false" on 40 of 40 items (PerryLink), so always describe the outcomes.

## FA: False alarms (we hint on about 16% of unrelated turns)

- [ ] **FA-1 · Gate on the kind of request · S–M · Next**
  - **Do:**
    - In the same Laya call, ask 2–3 yes/no questions:
      - Does it act on the user's files, accounts or services?
      - Would a careful expert follow a documented procedure?
      - Would a prose answer do? (inverted)
    - Hint only when their mean clears a calibrated threshold.
  - **Why:** a question about topic cannot tell "explain what a monad is" apart from a request that needs a skill.
  - **Evidence:**
    - TypeSafe's skill_suggestion cookbook: wrong loads fell from 16.8% to 7.3% (vendor figures).
    - `GATE_QUESTIONS` in shimo4228/jev-skill-router `scripts/router.py`.
    - skillranker's gate questions.
- [ ] **FA-2 · Require the top pick to beat "none" by a margin · S · Next**
  - **Do:** require `p_top − p_none ≥ m`, with m calibrated.
  - **Evidence:**
    - AdelysAlberto `readMargin`.
    - rabi: switch only when the new pick is clearly better.
- [ ] **FA-3 · More skip rules and explicit mentions · S · Next**
  - We already skip prompts under 12 characters, `/` commands and repeats.
  - **Add:**
    - Prompts that are mostly pasted code or logs.
    - Longer acknowledgements ("thanks, that works").
    - `@`-only prompts.
    - A prompt that names a catalog item ("use slack"): skip it, or force-include the item and log the override.
  - **Evidence:**
    - AmRitJain0442/Tern `preflight`: reason codes.
    - AdelysAlberto `gateInput`.
    - laya-codex `skip_prompt`.
    - ricardochen1996/dsh-laya-router `signals[]`.
- [ ] **FA-4 · Test other wordings of the "none" option · S · Later**
  - Today it reads "no specialized skill or tool needed; general request" for all three kinds. Upstream warns that yes/no-like labels can dominate a choice. Try wording specific to each kind.

## RUN: Memory, latency, robustness

- [ ] **RUN-1 · One shared background process per user · M · Next**
  - **Do:** each session's MCP server becomes a thin client with no torch import, talking to one warm model.
    - **Socket:** a Unix socket in `$XDG_RUNTIME_DIR` with 0600 permissions and a check that the caller is the same user. Never `/tmp`, never TCP on 0.0.0.0.
    - **Version check:** restart a stale process after an upgrade.
    - **Start:** on the first `route` call, or from a SessionStart hook of type `command`; `mcp_tool` hooks are skipped when a session starts.
    - **Idle:** exit after idling.
    - **Busy or down:** a single lock, and return "" immediately instead of waiting.
    - **Per-session state:** the previous prompt and dedup memory, keyed by `session_id`.
  - **Fixes:**
    - 2.4 GB of VRAM per session.
    - The missed first prompt, for every session after the first.
    - Sessions fighting over CPU threads.
    - It also lets Desktop, Cursor and Gemini share one model, and gives one place to handle the GPU→CPU fallback (RT-3).
  - **Evidence:**
    - pilotspace/laya-codex `daemon.rs`/`client.rs`: 4 sessions, 151,326 hook calls, 0 failures, about 1 GB of memory, flat.
    - F0Rextasy/omp-laya-judge: binds its port before importing torch, exits when idle.
    - ericmjl's local server, PerryLink `Backend`.
    - harshadptl `ensureServer`, whose `/tmp` socket is the mistake to avoid.
- [ ] **RUN-2 · Keep weights in 16-bit on the GPU · S–M · Later**
  - **Why:** stock laya keeps fp32 weights on the GPU, about 1.7 GB of our 2.4 GB.
  - **Upstream parity measurements:**
    - fp16 moves probabilities by at most 0.019.
    - bf16 moves them by up to 0.073 and changed 3 of 864 top answers.
  - **Do:** check decisions near τ before switching.
- [ ] **RUN-3 · Pin CPU threads · S · Now**
  - **Do:** `torch.set_num_threads(<physical cores>)` and `torch.set_num_interop_threads(1)`.
  - **Evidence:** a contributed upstream run went from 9.4 s to 0.78 s on a busy host.
- [ ] **RUN-4 · Deadline and circuit breaker in `route` · S · Now**
  - **Do:**
    - Return "" once inference passes about 1.5 s.
    - After 3 failures, skip routing for 15 s.
    - Add a timeout to the scorer lock.
  - **Evidence:** AmRitJain0442/Tern `LayaGPUClient`.
- [ ] **RUN-5 · Pin the checkpoint version · S · Now**
  - **Why:** thresholds are only valid for one checkpoint revision, and Hugging Face `main` moves.
  - **Do:**
    - On 0.3.20, use `snapshot_download(revision=SHA)` + `Router.attach`.
    - Log the revision.
    - Set `HF_HUB_OFFLINE=1` once cached, so startup needs no network.
  - **Evidence:**
    - Tern `MODEL_REVISION`.
    - leo1394/oh-my-laya: pinned download with a sha256 check.
- [ ] **RUN-6 · Warm up every expected input shape at load · S · Later**
  - **Why:** the first call at a new input length is slow.
  - **Evidence:** DJLougen/laya-fast brought that first call from 76–80 ms down to 11–15 ms.
- [ ] **RUN-7 · Keyword-only hints while the model loads or is busy · S · Later**
  - Only when the BM25 score margin is high. laya-codex falls back to keyword ranking when busy.
  - **Risk:** lower precision.
- [ ] **RUN-8 · MLX backend for Macs · M–L · Later**
  - **Evidence:** laya-fast measured 17.0 ms against 35.6 ms on the standard Apple GPU path, and loads in 0.07 s against 22 s.
  - **Caveats:** third-party port; needs its own τ calibration.
- [ ] **RUN-9 · Try Laya's ONNX CPU path · S–M · Later**
  - `laya.onnx_agent.ONNXAgent` exists but no one has published measurements, so measure before adopting.
- [ ] **RUN-10 · Upgrade laya at the next PyPI release · S · Later**
  - **Gains:**
    - a lock around the tokenizer;
    - a GPU fallback that only lasts one request;
    - `revision=`/`expected_sha256=` pinning;
    - `LAYA_CUDA_AMP`.
  - Don't install from git: `main` reports the same version string.

## CTX: Context savings from skill and tool listings

- [ ] **CTX-1 · Show only the names of rarely used skills · S–M · Next**
  - **How it works:** `skillOverrides` with `name-only` for rarely used personal and project skills, picked from transcript usage counts. The router adds the description only when it's relevant.
  - **Verified in the docs:**
    - `on` / `name-only` / `user-invocable-only` / `off` are the supported values.
    - **Plugin skills are not affected by `skillOverrides`.** That limits how much this can save.
    - A plugin can't ship this setting. So make it an opt-in command that writes user settings with backup and restore.
  - **Measure:** with `/context` before claiming savings.
  - **Evidence:** the davila7/claude-code-templates `jev-skill-suggestion` mod reports 5,496 tokens saved with 40 skills (claimed).
  - **Risk:** skills are harder to discover when the router misses them.
- [ ] **CTX-2 · Optional add-on on Claude Code's early-access "function hooks" · M · Later**
  - **Do:**
    - `prompt.attachment{type:'skill_listing'}` withholds the skill listing, for every skill including plugin skills.
    - `prompt.submit` attaches the chosen skill.
    - A constant answer keeps the prompt cache.
  - **Evidence:** davila7 `jev-skill-suggestion.ts:211-246`.
  - **Risk:** early access (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`), may change, Claude Code only.
- [ ] **CTX-3 · Keep tool hints; shorten our server instructions · S · Later**
  - Claude Code already loads MCP tool details on demand (ToolSearch).
  - Our hint adds descriptions Claude can't see yet and exact `mcp__server__tool` names (already done).
  - Our server instructions are always loaded, so keep them short and stop inviting Claude to call `route` itself (HK-1).
- [ ] **CTX-4 · Optionally move personal skills out of the scanned folder · M–L · Later**
  - **Do:** move them into a library folder, and have the hint give the file path.
  - **Evidence:** gutcheck `_how_to_use`, and its backup/uninstall in `claude.py`.
  - **Risk:** moved skills can no longer be invoked through the Skill tool or a slash command.

## CLN: Context cleaning (tool outputs and history)

### Verdict on Jev's context cleaning

**What it is:**
- TypeSafe has **no official context-cleaning feature**. The closest official recipe is its "Classifying RAG passages" cookbook.
- "Jev compaction" is a community pattern:
  - The original is `tamaratran/fast-jev-compaction`, created 2026-09-17 and mostly written by a bot.
  - About ten ports exist, for pi, OpenCode, DeepSeek Harness and Claude Code.
- It asks two yes/no questions about each older tool call:
  - "does this call still matter?"
  - "is the full output still needed verbatim?"
- Then it keeps the call, cuts the output to a 300-character head, or drops the call. It never generates a summary.

**The judging does not work:**
- Three authors found Jev's keep probabilities bunched at about 0.1–0.25, so at the default threshold of 0.5 it acts like simple "drop the oldest".
- On real sessions, iefnaf/pi-jev measured size-matched AUC 0.510, against 0.507 for random.
- A no-model rule that cuts outputs of repeatable tools to their start kept **16 of 60** later-used results. Jev kept **4 of 60** at a similar size.
- shitianfang/jev-use: Jev agreed with Claude Opus 5 on 56.3% of keep/drop decisions, below the 68.7% you get by always guessing the majority answer.
- jcressler/fast-jev-compaction-codex: 8/12 tasks succeeded with Jev, against 12/12 without.
- The best Claude Code design, GhalebDweikat/winnow, safely hid only 4.6% of large-output text.
- compozy/yoshi saved 34% of input tokens on one session (at 4–5× the wall time) and 0% on another.

**A local model doesn't fix it:**
- Laya scored AUC 0.45–0.47 in Dymyt-ry/tool-output-pruning-lab, below trivial rules at 0.55–0.62.
- lucasmartins-ai/lcc removed 0% with the real Laya model.
- Laya's input limit (1,024 tokens) is far smaller than the ~25k-token history these designs send.
- The same lab found that no line-selector beats simply keeping the start and end of an output (70/30) at the same size. Which lines matter later just isn't predictable when the output arrives.

**Risks:** conversation text, code and paths go to TypeSafe, and text inside the conversation can steer the judge.

**Decision:** adopt the mechanism, not the judge:
- keep text verbatim;
- make every cut reversible;
- cut when output arrives (safe for the prompt cache), or only at compaction;
- start in shadow mode, and gate every step on replaying real transcripts.

Add a model ranker only if replay shows it beats head+tail (CLN-6).

### Items

- [ ] **CLN-1 · Transcript replay harness (gates everything below) · M · Next**
  - **Do:**
    - Replay local transcripts.
    - Label a tool result "used later" when the agent later repeats a distinctive token from it. Remove cases where the agent restated the token itself.
    - Compare policies at equal kept size:
      - keep the start and end (70/30), recency, the no-model mask rule, random;
      - a Laya chunk ranker;
      - a local reranking model.
    - Report later-used content kept, size-matched AUC, and savings.
  - **Evidence:**
    - iefnaf/pi-jev `eval/README.md`.
    - Dymyt-ry/tool-output-pruning-lab `experiments/circularity.py`.
    - winnow `replay.py`.
  - **Rule:** transcripts stay local.
- [ ] **CLN-2 · Shadow mode plus a log with no content · S · Next**
  - **Do:** log would-cut decisions, sizes and projected savings; change nothing until the user opts in.
  - **Evidence:**
    - nrdz-labs/fast-jev-opencode: `dryRun` on by default.
    - winnow `WINNOW_MODE=shadow`.
    - yoshi `YOSHI_DRY_RUN`.
- [ ] **CLN-3 · Local store of originals plus a `recall` tool · S · Next**
  - **Do:**
    - Store a copy of every trimmed output, keyed by content hash, with 0600 permissions and a TTL or size cap.
    - Add `recall(id, start, end)` to our MCP server.
    - Each stub names its id, so a wrong cut costs one call.
  - **Evidence:**
    - yangyu666/dsh-jev-prune `jev_restore`.
    - winnow `winnow_recall`.
  - **Risk:** secrets on disk. Redact, and keep the TTL short.
- [ ] **CLN-4 · Trim large outputs as they arrive · M · Next**
  - **Mechanism:** `PostToolUse` → `hookSpecificOutput.updatedToolOutput`.
    - Verified: it works for all tools and only changes what Claude sees.
    - The value must match the tool's output shape, or it is ignored.
  - **Do:** for Bash/Grep/WebFetch/MCP outputs over a size threshold, keep:
    - the start and end (70/30);
    - error and traceback lines;
    - lines naming paths or identifiers from the request.
  - **Stub:** `[router] lines A–B hidden (N lines); recall(id=…)`.
  - **Never trim:** error outputs, Write/Edit results, or small outputs.
  - It only appends to the conversation, so it breaks neither the prompt cache nor thinking blocks.
  - **Evidence:**
    - winnow's stub design.
    - tool-output-pruning-lab: start + end is hard to beat.
    - The hooks docs.
  - **Depends on:** CLN-1 to CLN-3.
  - **Risk:** a silently ignored shape mismatch (test each tool); detail needed on the next step (covered by `recall`).
  - **Open question:** whether an `mcp_tool`-type hook can return `updatedToolOutput`. If not, use a small `command` hook that calls RUN-1.
- [ ] **CLN-5 · Collapse exact duplicate outputs · S–M · Later**
  - Replace a repeated tool output with a pointer to the first one, and keep that decision fixed for the session.
  - **Evidence:** yoshi `rewrite.ts:232`.
  - **Depends on:** CLN-3.
- [ ] **CLN-6 · Rank chunks by relevance, only if CLN-1 shows it wins · M · Later**
  - **Do:** within one output, rank chunks against the current request, using either:
    - a local reranking model (mxbai-rerank-base-v2 on CPU, Qwen3-Reranker-4B on GPU); or
    - one Laya yes/no question per chunk with explicit criteria, used as a rank within the output, never a fixed 0.5 cut.
  - **Evidence:**
    - anessbelbati/jev-rerank-bench, nDCG@10:

      | Ranker | nDCG@10 |
      |---|---|
      | BM25 | 0.486 |
      | Laya | 0.483 |
      | mxbai | 0.642 |
      | Qwen3-Reranker-4B | 0.660 |
      | Jev | 0.692 |

    - TypeSafe's `classifying_rag_passages` cookbook: thresholds.
  - **Needs:** a new dependency, so ask first.
- [ ] **CLN-7 · Verbatim pruning at compaction (early-access function hooks) · M · Later**
  - **Do:**
    - A `session.compact` hook returns trimmed messages, or passes them on to the built-in summary.
    - Fall back on errors, or when the reduction is under 25%.
    - Prune only when the cache is lost anyway, never on every request.
  - **Evidence:**
    - tamaratran `hooks/fast-jev.ts`.
    - hoshinodis/opencode-context-pruner: prunes only what goes into compaction.
    - QuentinDanblon/pi-fast-jev-compaction: cache cost accounting.
- [ ] **CLN-8 · Evidence packet after compaction · M · Later**
  - **Do:**
    - A `PreCompact` hook archives key results from `transcript_path` into the CLN-3 store.
    - `SessionStart` with matcher `compact` injects a short verbatim packet: user constraints, open errors, edited files, recall ids.
  - **Evidence:** the hooks docs; jcressler's paired results.
  - **Risk:** the benefit is unproven, so measure first.

## SCO: Scorer backends and models

- [ ] **SCO-1 · Generic `/v1/systemone` HTTP scorer · S · Next**
  - **Do:**
    - Implement our `Scorer` protocol over `POST {model, state, questions}`, reading probabilities only.
    - Map model ids per backend.
    - Back off on 429/529.
    - Warn on silent truncation.
  - **Covers:** `laya-serve`, `von serve`, Mapika/decider, hosted Jev and OpenRouter.
  - In-process Laya stays the default.
  - **Evidence:**
    - fstandhartinger/jevbench `adapters/typesafe.py`.
    - `laya/serve.py`.
    - The TypeSafe API docs.
- [ ] **SCO-2 · Compare routing models on our labels · M · Next**
  - **Candidates:**
    - Laya typed-decisions and standard English;
    - Von 1.2;
    - decider-2b/4b v2;
    - GLiNER2.5-Decide;
    - Jev, opt-in.
  - **Metrics:**
    - top-1 accuracy;
    - how often "none" is caught;
    - precision within our false-alarm budget;
    - calibration error on the top probability;
    - p50/p95 latency on GPU and CPU;
    - how often answers flip across 3 option orders.
  - **Public evidence:**

    | Benchmark | Measure | Laya | Von | Jev | Other |
    |---|---|---|---|---|---|
    | JevBench v1.4.2 | public accuracy | 0.584 | 0.571 | 0.866 | |
    | jabr/classifier-benchmark | choice accuracy | 0.736 (typed-decisions) | 0.814 | 0.982 | GLiNER2.5-Decide 0.853 |
    | JevBench routing items | correct | 10/16 | | 16/16 | SemIf-style Qwen3.5-4B 16/16 |

  - **Risk:** public benchmarks overlap the candidates' training data.
- [ ] **SCO-3 · Escalate uncertain prompts to a bigger model (GPU) · M · Later**
  - **Do:** when Laya's margin is low, escalate to decider-4b v2 or a SemIf-style 4B model.
  - **Candidates:**
    - **decider-4b v2:** JevBench #1 with 0.835 public accuracy, p50 17 ms on a workstation GPU, 8.4 GB in BF16, 4 days old. Some of its training data was generated from the names of the sealed test families.
    - **SemIf-style 4B:** p50 133 ms on an RTX 3090, 8.9–11.6 GB of VRAM.
  - **Risk:** decider's README says generic options like "other" absorb in-scope items, so test our "none" option.
  - **Depends on:** SCO-1 and SCO-2.
- [ ] **SCO-4 · Opt-in hosted Jev backend with guardrails · S · Later**
  - **Guardrails:**
    - off by default, with explicit consent;
    - redact secrets;
    - a token budget;
    - only for asynchronous escalation, because median latency is 220–650 ms.
  - **Terms:** TypeSafe's customer agreement, typesafe.ai/legal/mca:
    - §2.3(b) bars using the service or its output to distill or train imitating models, so never calibrate or train on Jev outputs.
    - §4.1 keeps customer data for telemetry indefinitely.
    - Zero data retention is enterprise-only.
  - **Cost:** about $0.04 per 1,000 decisions.
  - It is also a possible route for Cowork (COW-2).

## LRN: Learning from usage

- [ ] **LRN-1 · Held-back turns · S–M · Next**
  - On about 10% of turns, compute and log the hint but don't show it.
  - That gives uncontaminated labels and measures whether hints change behavior.
  - **Evidence:**
    - Tern: shadow mode by default.
    - mmornati: runs a candidate router alongside and explores at random.
- [ ] **LRN-2 · Record `hint_shown` · S · Next**
  - Exclude or separate hinted turns when relabeling from transcripts; otherwise the router grades itself.
  - **Evidence:** Intent-Router, Limitations section.
- [ ] **LRN-3 · Learn a per-item adjustment from usage · M · Later**
  - **Do:**
    - Join the decision log with actual usage.
    - Pull adjustments toward zero when data is thin, and require a minimum number of samples.
    - Propose a diff for review; don't apply it automatically.
  - **Evidence:** mmornati `cmd/refit`.
- [ ] **LRN-4 · Fine-tune the model · L · Later**
  - **Do:**
    - Start with the head only: frozen encoder, cached states, soft labels, our exact 6-option format, and a question that doesn't depend on the item.
    - Use SkillRouter's hard negatives (4 similar in meaning, 3 BM25 matches, 2 from the same category, 1 random) with its false-negative filter.
    - Refit temperatures afterwards.
    - Promote a new model only if recall rises, false alarms don't, and latency is fine. Swap it in with a health check and rollback.
  - **Evidence:**
    - 0xSarnavo `tune.py`.
    - ericmjl `nightly_loop.decide_promotion`.
    - The SkillRouter paper.
    - Upstream Laya's Kaggle fine-tuning notebook.
    - system-one-model-finetuning: freezing lower layers fits a 16 GB machine.
  - **Caveats:**
    - 0xSarnavo's fine-tune didn't improve overall (60.8% → 58.6%, claimed), and ericmjl's headline number is unverified.
    - It uses Laya internals, which may break across versions.
- [ ] **LRN-5 · Labels from a frontier model · M · Later**
  - **Do:** `claude -p` with a pinned model labels, per turn:
    - which skills and tools *should* have been used, with evidence;
    - which were tangential;
    - "none needed";
    - `when`: at turn start, or after N tools.
  - That gives true recall and the ceiling for prompt-time routing.
  - **Evidence:**
    - ericmjl `distiller.py`.
    - glukicov `label_blind`: never show the labeler our labels.
- [ ] **LRN-6 · A `/router-feedback` command that turns user feedback into labels · S · Later**
  - **Evidence:** SupremeDreamZ.

## EV: Evaluation

- [ ] **EV-1 · Freeze thresholds before measuring · S–M · Now**
  - **Do:**
    - Split data by session.
    - Choose τ on a calibration split, freeze it, and report on an untouched test split.
    - Add bootstrap confidence intervals by session, and a paired significance test (McNemar) when comparing variants.
  - **Check:** whether our 0.93 precision was measured on the same data τ was tuned on.
  - **Evidence:**
    - Tern `evaluation.py`.
    - glukicov `metrics.py`.
- [ ] **EV-2 · LLM baseline and blind label audit · M (about $1 of API) · Later**
  - **Do:** give a cheap LLM our exact question (5 candidates + none):
    - on the same shortlist, to isolate the chooser;
    - on the full catalog, to isolate the shortlist.
  - **Evidence:** glukicov.
- [ ] **EV-3 · Clean the labels · S · Now**
  - **Drop:**
    - meta, sidechain and compaction-summary messages;
    - command output;
    - hook-injected text, including our own hints (tagged `[toolhint]`, or `[laya-router]` in transcripts from before the rename).
  - **Deduplicate:** streamed messages.
  - **Add:** subagent transcripts (`<session>/subagents/*.jsonl`) as their own slice.
  - **Separate:** treat `/command` turns as the user's own choice and leave them out of the routing eval.
  - **Evidence:** jverhoeks/claude-laya `transcript.py`.
- [ ] **EV-4 · Paired test prompts · S · Later**
  - **Add:**
    - paraphrase pairs;
    - "use X" and "ignore routing" prefixes;
    - an explanation-only slice ("what does X do") in the false-alarm set.
  - **Evidence:**
    - Tern `scripts/probe_robustness.py`.
    - Intent-Router's question-not-trigger case.
- [ ] **EV-5 · Standard eval outputs · S · Later**
  - Per-kind calibration error on the top probability, reliability bins, a deferral curve, metrics per option count, and the Portuguese natural prompts as their own split.
- [ ] **EV-6 · Weight real turns and audit the log regularly · S · Later**
  - Hand-picked test sets overstate accuracy: cdepuy/hermes-skill-router scored 0.84 on its curated set and about 7–25% in production.

## INS: Install and harness reach

- [ ] **INS-1 · `install` / `uninstall` commands · M · Next**
  - **Do:**
    - `install --targets …|all --dry-run`.
    - Use each client's own CLI where it has one (`claude mcp add -s user`, `codex mcp add`, `hermes mcp add`).
    - Elsewhere, edit config files inside marked blocks, record ownership with sha256, and back up first.
    - Uninstall removes only entries we own that haven't changed.
    - Verify with each harness's `mcp list`.
    - Launch through `python -m` for Windows.
  - **Evidence:**
    - wangmiaozero/laya-router-skill `install.py`/`uninstall.py`.
    - oh-my-laya `installer.py`.
    - PerryLink `harnesses.py`.
    - itsmostafa/system-one-connector `setup.go`.
- [ ] **INS-2 · Hook into each harness's prompt submission · S (investigate) + M per harness · Next**
  - **Why:** offering only an MCP tool rarely fires. In wangmiaozero's end-to-end tests, models rarely called helper tools themselves.
  - **Do:**
    - Find the prompt hook for pi (`before_agent_start`), Codex, OpenCode, Gemini CLI and Cursor.
    - A pi bridge is about 120 lines (oh-my-laya `integrations/pi`).
- [ ] **INS-3 · A catalog per harness, plus `~/.agents/skills` · S–M · Later**
  - `~/.agents/skills` is the skill folder shared across harnesses.
  - This fixes other harnesses getting Claude Code's catalog (HK-2).
- [ ] **INS-4 · Publish on PyPI · S · Later**
  - So `uvx <name>` works, with a pinned, hash-checked checkpoint download.
- [ ] **INS-5 · Plugin `userConfig` · S · Later**
  - `userConfig` is verified in the plugins reference.
  - Expose τ, caps, on/off and log mode, editable in `/config`.
- [ ] **INS-6 · Codex plugin packaging · S–M · Later**
  - **Evidence:** oh-my-laya `codex_plugin.py`.

## SEC / UX: Privacy, security, user experience

- [ ] **SEC-1 · Keep prompts out of the decision log by default · S · Now**
  - **Do:**
    - Store a hash and length, not the text.
    - Set 0600 permissions and prune old entries.
    - Make full text opt-in for eval.
  - **Evidence:** wangmiaozero `events.py`.
- [ ] **SEC-2 · Clean the hint text · S · Now**
  - **Why:** skill, connector and tool names come from third-party plugins and flow into Claude's context.
  - **Do:**
    - Strip control characters and `<>{}`.
    - Restrict names to identifier characters.
    - Cap each name at about 80 characters.
  - **Evidence:** dsh-laya-router's output rules.
- [ ] **SEC-3 · Secure the background process · S · Next (with RUN-1)**
  - **Do:**
    - Unix socket with 0600 permissions and a same-user check.
    - Never bind 0.0.0.0; `laya-serve` does by default.
    - If it's HTTP, check the Host header (against DNS rebinding) and cap request size.
  - **Evidence:**
    - laya-codex.
    - wdobry/laya-playground `server.py _host_ok`.
- [ ] **SEC-4 · Tell "degraded" apart from "no hint needed" · S · Next**
  - **Do:**
    - Reason codes for not loaded, timeout, error, and GPU→CPU fallback.
    - A `status` command.
    - Optionally one user-visible note per session when degraded, never in Claude's context.
  - **Evidence:** Intent-Router §5.
- [ ] **UX-1 · Make hints visible to the user · S · Next**
  - **Do:**
    - An optional one-line `systemMessage` when a hint fires (the field is verified; up to 10,000 characters).
    - A status line showing the last hint.
    - A `/router-why` skill with `disable-model-invocation: true` that reads the decision log.
  - **Evidence:**
    - obsfx/promptscout.
    - SupremeDreamZ: status line and `/laya-explain`.

## COW: Cowork

- [ ] **COW-1 · Desktop local-MCP test · S · Now**
  - **Do:**
    - With the user's explicit OK and a backup, register the server in `claude_desktop_config.json`.
    - Restart Desktop and check that the bridge line shows `+1 local-mcp`.
    - Test whether cloud Cowork tasks can call `route`.
- [ ] **COW-2 · Remote route, if COW-1 fails · M–L · Later**
  - **Options:**
    - Host Laya yourself behind an authenticated HTTPS endpoint. Tern's figures: a Cloud Run L4 GPU at about $764/month always on, or 31–41 s cold starts if it scales to zero.
    - Opt-in hosted Jev (SCO-4).
  - Either way, prompts leave the machine.
  - None of the reviewed projects solves Cowork.

## HK: Housekeeping (deferred minors from the final code review)

- [ ] **HK-1** · The server instructions invite Claude to call `route` itself. Make them neutral and short (CTX-3). · S
- [ ] **HK-2** · Harnesses set up from the snippets get Claude Code's catalog (INS-3). · S–M
- [ ] **HK-3** · The tool snapshot isn't pruned when a plugin is disabled. · S
- [ ] **HK-4** · `catalog --refresh` drops a failing server's cached tools; keep the last good snapshot. · S
- [ ] **HK-5** · The engine is published before warm-up finishes, so the first call can still pay the cold start. · S
- [ ] **HK-6** · The `eval build --out` default is relative to the current directory. · S
- [ ] **HK-7** · There's no `TOOLHINT_K_CONNECTOR`, and `TOOLHINT_TAU` sets all three kinds at once; add per-kind variables. · S
- [ ] **HK-8** · numpy and anyio are used but not declared in `pyproject.toml`. · S
- [x] **HK-9** · `plan.md` Global Constraints still list the old defaults. Closed 2026-09-26: that plan is archived as history in `docs/superpowers/plans/2026-09-25-laya-router-plan.md`. · S

## Design rules (what not to do)

Each rule was learned from another project's failure.

- **Don't inject whole SKILL.md files.**
  - ericmjl measured it as a net loss.
  - cdepuy disabled his router after a production audit.
- **Don't ask one choice over the whole catalog, or over more than 10 options.** Laya's temperature for 11+ options is 0.10 (it overconfidently picks one) and it degrades past 20.
- **Don't decide on Laya's `confidence` or `act_probability`.**
  - `confidence` is 1 − normalized entropy, not a probability.
  - `act_probability` carries no signal (upstream issue #185, AUROC 0.30).
  - Use the per-option probabilities.
- **Don't route without a "none" option, or with an untested fixed threshold.**
- **Don't drop picks that share no word with the prompt.** It kills recall on paraphrases.
- **Don't use untrained per-item yes/no questions to find candidates.** They perform near chance on rare items.
- **Don't fall back to an LLM inside the 5-second prompt hook.**
- **Don't put one MCP "gateway" in front of all tools in Claude Code.**
  - It loses per-tool permission rules.
  - Claude Code already loads tool details on demand.
- **Don't rewrite earlier history on every request through a proxy.**
  - It breaks the prompt cache and, on current Claude models, thinking blocks.
  - yoshi took 4–5× the wall time.
- **Don't use Laya or Jev to decide what history to keep** (see CLN).
- **Don't change the tool set, skill listing or model in the middle of a session.** Choose once per session and only ever add.
- **Don't expose the router insecurely:**
  - no TCP on 0.0.0.0;
  - no `/tmp` sockets;
  - no `curl | sh` installers;
  - no loading the model on every call.
- **Don't train or calibrate on hosted Jev outputs.** Its terms forbid it.
- **Don't copy code from repos without a license** (0xSarnavo, cdepuy, harshadptl) or with restrictive license riders (Dicklesworthstone/skillranker). Use their ideas only.

## Already done (don't redo)

- One batched `predict` call covers all three kinds ([engine.py:155](src/toolhint/engine.py#L155)).
- A lock around every model call, which covers the tokenizer thread-safety bug in 0.3.20.
- Decisions use the per-option probabilities, not Laya's `confidence`.
- Skipping prompts under 12 characters, `/` commands and repeats.
- Exact `mcp__server__tool` ids in tool hints, so Claude can load them directly with ToolSearch.
- A BM25 shortlist of K = 5 plus a "none" option, and a per-kind τ calibrated within a false-alarm budget.
- Fail-open everywhere, with the model loading in the background plus a warm-up pass.

## Open questions (check before building)

1. Does a hook of type `mcp_tool` get to return `updatedToolOutput`? What is each built-in tool's exact output shape? (CLN-4)
2. Can `PreCompact` change the compaction instructions, or only block compaction? (CLN-8)
3. ~~Do `mcp_tool` hooks run for `SessionStart` with source `compact`? (RT-6)~~ Yes. This was verified live on 2026-09-26: the server stays up across compaction, and the hook reaches it.
4. Is our 0.93 skill precision measured on data τ wasn't tuned on? (EV-1)
5. For our own usage, how many skill and tool uses happen after N tool calls? That is, what's the ceiling for routing at the prompt? (LRN-5, REC-7)
6. Can cloud Cowork reach a local MCP server at all? (COW-1)

## Sources

**Laya-based routing:**

| Repo | What it offers |
|---|---|
| janmejai2002/gutcheck | Closest rival: keyword + embedding shortlist, Laya choice with "none", shared process, two-tier hints |
| ericmjl/pi-laya-skill-router | Nightly fine-tune with a promotion check; mid-turn finding |
| cdepuy/hermes-skill-router | Curated vs production gap; disabled by its author |
| ricardochen1996/dsh-laya-router | Clean hint output; staged plan from advising to pruning |
| 0xSarnavo/laya-coding-router | Fine-tune recipe |
| wangmiaozero/laya-router-skill | Ownership-tracking installer; models rarely call tools on their own |
| SupremeDreamZ/laya-code-router | Cache-aware rule; status line |
| harshadptl/laya-claude-code | Function hooks; shared socket |
| AdelysAlberto/pi-laya-router, rabi/pi-laya-router | Input and margin gates; prose-tail state |
| leo1394/oh-my-laya | Multi-harness installer; pi bridge |

**Infrastructure and models:**

| Repo | What it offers |
|---|---|
| NandhaKishorM/laya | Upstream |
| pilotspace/laya-codex | Reference design for the shared process |
| F0Rextasy/omp-laya-judge | Single-instance local server |
| PerryLink/laya-mcp | Calibration store per option-count group; token check before calls |
| itsmostafa/system-one-connector | Install through each client's CLI |
| DJLougen/laya-fast | MLX runtime |
| omkarghugarkar007/system-one-model-finetuning | Per-group temperature fitting |
| wfzyx/von, TheoLeeCJ/SemIf-OpenJev, Mapika/decider | Local alternatives to Jev |

**Evaluation and model routers:**

| Repo | What it offers |
|---|---|
| glukicov/laya_router | Eval design against an LLM baseline |
| mmornati/system-one-router | Silent candidate router; refitting from outcomes |
| AmRitJain0442/Tern | Skip reason codes; deadline; frozen-threshold protocol |
| jverhoeks/claude-laya | Transcript parsing |
| wdobry/laya-playground | Laya vs Jev benchmark |
| fstandhartinger/jevbench, jabr/classifier-benchmark, anessbelbati/jev-rerank-bench, shitianfang/jev-use | Independent evaluations |

**Context cleaning:**

| Repo | What it offers |
|---|---|
| tamaratran/fast-jev-compaction | The original pattern |
| joelhooks/pi-fast-jev-compaction, nrdz-labs/fast-jev-opencode, kevinpita/pi-jev-context, yangyu666/dsh-jev-prune, hoshinodis/opencode-context-pruner | Ports |
| iefnaf/pi-jev | Eval on real sessions |
| QuentinDanblon/pi-fast-jev-compaction | Cache cost accounting |
| jcressler/fast-jev-compaction-codex | Task-success tests |
| GhalebDweikat/winnow | Claude Code output filter with recall |
| compozy/yoshi | Proxy pruning with fixed decisions |
| Dymyt-ry/tool-output-pruning-lab | Laya and line selectors vs keeping start + end |
| tristankenney/laya-compaction, lucasmartins-ai/lcc, krw82/jev-playwright-mcp | Other attempts |

**Skill routing beyond Laya:**
- SkillRouter paper (arXiv 2603.22455).
- TypeSafe cookbooks `skill_suggestion` and `classifying_rag_passages`, and the TypeSafe customer agreement.
- shimo4228/jev-skill-router.
- davila7/claude-code-templates: the `jev-skill-suggestion` mod.
- Dicklesworthstone/skillranker.
- angel291592/Intent-Router, obsfx/promptscout, conorluddy/AgentLoadout.

**Claude Code docs** (code.claude.com/docs/en/):
- `hooks`
- `skills`
- `plugins-reference`
- `mcp`
- `prompt-caching`
- `context-window`
