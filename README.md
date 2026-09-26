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
The router is conservative. On prompts that need a skill or connector, it adds a hint about a third of the time, and those hints are right about 9 times in 10. On other turns it adds a hint about 16% of the time; each kind fires on 5–8% of them, and tool hints are the most common. Each session loads the model, which takes about 2.4 GB of VRAM; routing takes about 50 ms on a GPU and about 2 s on a CPU. The measurements are in `spike/FINDINGS.md`.

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

## Uninstall
```bash
claude plugin uninstall toolhint@toolhint
uv tool uninstall toolhint
```
