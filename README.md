# toolhint

Local Laya classifier that suggests the skills, connectors and tools relevant to each prompt.
It is advisory only: it never hides or blocks anything. The design is in `docs/superpowers/specs/2026-09-25-laya-router-design.md`.

## Install (this machine)
```bash
uv tool install -e .          # puts `toolhint` in ~/.local/bin
toolhint warmup               # downloads the checkpoint, snapshots MCP tools, counts catalogs
claude plugin marketplace add "$PWD"
claude plugin install toolhint@toolhint
```
- **Cowork:** build the zip with `mkdir -p dist && (cd plugin && zip -r ../dist/toolhint-plugin.zip .)`, then upload it under Customize › Plugins › Upload. It only works when Cowork runs the task on this computer. Where Cowork runs tasks in Anthropic's cloud (the merged Claude experience, or no local VM support), the plugin cannot reach the local router and gives no hints.
- **Gemini, Cursor, VS Code:** merge the matching file from `snippets/`.

## What to expect
The router is conservative. On prompts that need a skill or connector, it adds a hint about a third of the time, and those hints are right about 9 times in 10. On other turns it adds a hint about 16% of the time; each kind fires on 5–8% of them, and tool hints are the most common. Each item is hinted at most once per session, and again after the conversation is compacted. Each session loads the model, which takes about 2.4 GB of VRAM; routing takes about 50 ms on a GPU and about 2 s on a CPU. The measurements are in `spike/FINDINGS.md`.

## Check it
- **Try a prompt:** `toolhint route "your prompt"` prints the hint plus the ranking JSON.
- **Decisions:** they are logged to `~/.local/state/toolhint/decisions.jsonl`.
- **Environment variables:**
  - `TOOLHINT_MODEL`
  - `TOOLHINT_DEVICE`
  - `TOOLHINT_K_SKILL`
  - `TOOLHINT_K_TOOL`
  - `TOOLHINT_TAU` sets one τ for every kind.
  - `TOOLHINT_LOG`: set it to `off` to disable the log.

## Benchmark
`python -m toolhint.bench` runs real tasks in headless Claude Code sessions, once with toolhint and once without, and compares the results. Everything else about your setup stays the same: the same plugins, hooks and CLAUDE.md.
- **Tasks** (`bench/tasks/`):
  - `coding-app`: build a command-line expense tracker; graded by 15 hidden acceptance tests.
  - `research-local`: brief a COO from six bundled sources that contain traps; graded by a 17-point checklist.
  - `research-web`: research MCP transports and authorization on the web; graded by a 15-point checklist.
  - `spreadsheet`: build `comparison.xlsx` with live formulas; graded by 14 checks. The formulas must be computed and saved, and the totals and payback correct. The router hints the xlsx skill (0.80). This machine has no openpyxl, so agents have to go through LibreOffice.
  - `landing-page`: a distinctive single-file page; graded by 14 structure and accessibility checks. The router hints the frontend-design skill (0.67).
  - Every task is also scored 1–10 by a separate Sonnet judge that runs without your hooks or plugins.
- **Measured per run:** the score, hints shown, skills and tools used (subagents included), permission denials, tokens (input, output, cache), cost, turns and time.
- **Run it:**
  - From Claude Code: `/bench` (add `--dry-run` to see the plan first).
  - From a terminal: `uv run python -m toolhint.bench`, with options `--tasks`, `--reps` (default 3), `--model` (default sonnet), `--judge-model`, `--warmup` (default 45 s).
  - To rebuild a report: `uv run python -m toolhint.bench --report bench/runs/<stamp>`.
  - To rescore saved runs after a grader fix, at no model cost (judge scores are kept): `--regrade bench/runs/<stamp>`.
- **Cost and time:** the default 30 runs (5 tasks × 3 reps × 2 arms) take a few hours. The first full run averaged about $0.60 a run on Sonnet, so expect roughly $20. Each run has a budget cap; the caps add up to $126. Sessions cannot install packages.
- **Before running:** close other toolhint sessions (VS Code panels, the desktop app). Each one holds about 2.7 GB of GPU memory, and the on-arm router falls back to CPU when the GPU is full.
- **Output:** `bench/runs/<stamp>/` holds `report.md`, `results.jsonl`, and each run's workspace, stream events and router decisions. The folder is gitignored.

## Update
The router is an editable install, so it follows this checkout. Claude Code keeps its own copy of the plugin's hooks, so refresh that copy after pulling, then restart open sessions:
```bash
claude plugin marketplace update toolhint
claude plugin update toolhint@toolhint
```
For Cowork, rebuild the zip and upload it again.

## Uninstall
```bash
claude plugin uninstall toolhint@toolhint
uv tool uninstall toolhint
```

## License
Apache-2.0. See `LICENSE`.
