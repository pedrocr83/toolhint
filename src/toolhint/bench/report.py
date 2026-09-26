"""Markdown comparison of benchmark runs: per task, toolhint on against off, over valid runs only."""
from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Callable

ARMS = ("on", "off")
ROWS: tuple[tuple[str, Callable[[dict], float | None]], ...] = (
    ("score (tests or checklist)", lambda r: r["grade"]["score"]),
    ("judge (1-10)", lambda r: (r["grade"].get("judge") or {}).get("score")),
    ("cost (USD)", lambda r: r["cost_usd"]),
    ("input tokens", lambda r: r["tokens"]["input"]),
    ("output tokens", lambda r: r["tokens"]["output"]),
    ("cache read tokens", lambda r: r["tokens"]["cache_read"]),
    ("cache write tokens", lambda r: r["tokens"]["cache_creation"]),
    ("context at first call (tokens)", lambda r: r.get("context_first")),
    ("peak context (tokens)", lambda r: r.get("context_peak")),
    ("tool output in context (~tokens)", lambda r: r.get("tool_output_tokens")),
    ("follow-ups needed", lambda r: r.get("followups")),
    ("turns", lambda r: r["num_turns"]),
    ("minutes", lambda r: r["wall_s"] / 60),
    ("tool calls", lambda r: sum(r["tools"].values()) + sum(r["subagent_tools"].values())),
    ("subagents", lambda r: r["subagents"]),
    ("permission denials", lambda r: len(r["denials"])),
    ("skill uses", lambda r: len(r["skills"])),
)


def stat(values: list[float | None]) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "–"
    mean = statistics.fmean(values)
    spread = f" ± {shown(statistics.stdev(values), 2)}" if len(values) > 1 else ""
    return f"{shown(mean, 3)}{spread} ({len(values)})"


def shown(value: float, digits: int) -> str:
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:.{digits}g}"


def tally(runs: list[dict], pick: Callable[[dict], list[str]], top: int = 8) -> str:
    counts = Counter(name for run in runs for name in pick(run))
    return ", ".join(f"{name} ×{n}" for name, n in counts.most_common(top)) or "–"


def render(results: list[dict]) -> str:
    lines = ["# toolhint benchmark", "",
             ("Mean ± standard deviation (number of valid runs). With 3 runs per arm, a difference smaller than "
              "the spread is noise."), ""]
    for task in sorted({r["task"] for r in results}):
        runs = {arm: [r for r in results if r["task"] == task and r["arm"] == arm and r["valid"]] for arm in ARMS}
        lines += [f"## {task}", "", "| metric | toolhint on | toolhint off |", "|---|---|---|"]
        lines += [f"| {label} | {stat([pick(r) for r in runs['on']])} | {stat([pick(r) for r in runs['off']])} |"
                  for label, pick in ROWS]
        for label, pick in (("skills used", lambda r: r["skills"]),
                            ("tools used", lambda r: list((Counter(r["tools"]) + Counter(r["subagent_tools"])).elements()))):
            lines.append(f"| {label} | {tally(runs['on'], pick)} | {tally(runs['off'], pick)} |")
        hinted = [r for r in runs["on"] if r["hints"]]
        lines += ["", f"- **Hints shown (on):** {tally(runs['on'], lambda r: [h['id'] for h in r['hints']])}",
                  (f"- **Hinted item used afterwards:** {sum(bool(r['hint_uptake']) for r in hinted)} of "
                   f"{len(hinted)} runs with a hint"), ""]
    lines += ["## Runs", "", "| task | arm | rep | valid | score | judge | cost | min | skills | hints | router | end |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: (r["task"], r["rep"], r["arm"])):
        judge = (r["grade"].get("judge") or {}).get("score")
        lines.append(f"| {r['task']} | {r['arm']} | {r['rep']} | {'yes' if r['valid'] else r['invalid_reason']} | "
                     f"{r['grade']['score']} | {judge if judge is not None else '–'} | {r['cost_usd'] or 0:.2f} | "
                     f"{r['wall_s'] / 60:.1f} | {', '.join(r['skills']) or '–'} | "
                     f"{', '.join(h['id'] for h in r['hints']) or '–'} | {r.get('router_device') or '–'} | {r['result_subtype']} |")
    return "\n".join(lines) + "\n"
