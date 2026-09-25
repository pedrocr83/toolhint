# laya-router

Local Laya classifier that suggests the skills, connectors and tools relevant to each prompt.
It is advisory only: it never hides or blocks anything. The design is in `docs/superpowers/specs/2026-09-25-laya-router-design.md`.

## Install (this machine)
```bash
uv tool install -e .          # puts `laya-router` in ~/.local/bin
laya-router warmup            # downloads the checkpoint, snapshots MCP tools, counts catalogs
claude plugin marketplace add "$PWD"
claude plugin install laya-router@layla
```
- **Cowork:** build the zip with `mkdir -p dist && (cd plugin && zip -r ../dist/laya-router-plugin.zip .)`, then upload it under Customize › Plugins › Upload. This works in local sessions only.
- **Gemini, Cursor, VS Code:** merge the matching file from `snippets/`.

## What to expect
The router is conservative. On prompts that need a skill or connector, it adds a hint about a third of the time, and those hints are right about 9 times in 10. On other turns it adds a hint about 16% of the time; each kind fires on 5–8% of them, and tool hints are the most common. Each session loads the model, which takes about 2.4 GB of VRAM; routing takes about 50 ms on a GPU and about 2 s on a CPU. The measurements are in `spike/FINDINGS.md`.

## Check it
- **Try a prompt:** `laya-router route "your prompt"` prints the hint plus the ranking JSON.
- **Decisions:** they are logged to `~/.local/state/laya-router/decisions.jsonl`.
- **Environment variables:**
  - `LAYA_ROUTER_MODEL`
  - `LAYA_ROUTER_DEVICE`
  - `LAYA_ROUTER_K_SKILL`
  - `LAYA_ROUTER_K_TOOL`
  - `LAYA_ROUTER_TAU` sets one τ for every kind.
  - `LAYA_ROUTER_LOG`: set it to `off` to disable the log.

## Uninstall
```bash
claude plugin uninstall laya-router@layla
uv tool uninstall laya-router
```
