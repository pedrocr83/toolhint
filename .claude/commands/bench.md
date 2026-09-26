---
description: Benchmark Claude Code with and without toolhint on the coding and research tasks, then summarize the report
argument-hint: "[--tasks coding-app,research-local,research-web] [--reps 3] [--model sonnet] [--dry-run]"
---
Run the toolhint on/off benchmark from the repo root (design: `plan.md`, usage: README "Benchmark").

1. Run `nvidia-smi --query-gpu=memory.free --format=csv,noheader`. If less than 3000 MiB is free, tell me that on-arm routers will fall back to CPU (slower hints; the report's router column will say cpu) and name the processes holding GPU memory.
2. If the arguments contain `--dry-run`, run `uv run python -m toolhint.bench $ARGUMENTS` and show me its output. Stop there.
3. Otherwise start `uv run python -m toolhint.bench $ARGUMENTS` with the Bash tool in the background (it takes hours). Tell me the output folder from its first line. Do not poll it.
4. When it finishes, read the `report.md` whose path it printed last. Summarize per task, toolhint on against off: score, judge, cost, tokens, turns, skills and tools used, hints shown and whether they were used. Call any difference smaller than the spread noise, and list invalid runs with their reason.
