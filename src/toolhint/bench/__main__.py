"""python -m toolhint.bench: run each task with toolhint on and off, grade every run, and write report.md."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import time
from pathlib import Path

from ..dataset import read_jsonl
from . import TASKS_DIR, Task, load_tasks
from .grade import grade
from .metrics import summarize
from .report import render
from .session import clean_env, command, prepare_workspace, run

RUNS_DIR = TASKS_DIR.parent / "runs"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m toolhint.bench", description=__doc__)
    p.add_argument("--tasks", default="all", help="comma-separated task names, or all (default)")
    p.add_argument("--reps", type=int, default=3, help="runs per task and arm (default 3)")
    p.add_argument("--arms", default="on,off", help="on, off, or on,off (default)")
    p.add_argument("--model", default="sonnet", help="model for the benchmarked sessions (default sonnet)")
    p.add_argument("--judge-model", default="sonnet", help="judge model, or none to skip the judge (default sonnet)")
    p.add_argument("--warmup", type=float, default=45, help="seconds to wait before the prompt so the router loads")
    p.add_argument("--out", help="output folder (default bench/runs/<timestamp>)")
    p.add_argument("--claude", default="claude", help="claude executable")
    p.add_argument("--dry-run", action="store_true", help="print the planned runs and commands, then stop")
    p.add_argument("--report", metavar="DIR", help="rebuild DIR/report.md from DIR/results.jsonl and stop")
    p.add_argument("--regrade", metavar="DIR", help="re-grade DIR's saved workspaces with the current tests and "
                   "checklists (judge scores are kept), rebuild the report, and stop")
    return p


def schedule(tasks: list[Task], arms: list[str], reps: int) -> list[tuple[int, Task, str]]:
    """Arms alternate, and each rep flips which arm goes first, so drift during the batch hits both arms."""
    return [(rep, task, arm) for rep in range(1, reps + 1) for task in tasks for arm in (arms if rep % 2 else arms[::-1])]


def run_one(task: Task, arm: str, rep: int, run_dir: Path, args: argparse.Namespace) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace = prepare_workspace(task, run_dir)
    decisions = run_dir / "decisions.jsonl"
    session = run(command(task, arm, args.model, args.claude), workspace, clean_env(os.environ, decisions),
                  task.prompt, args.warmup, task.timeout_s, run_dir / "stderr.log")
    (run_dir / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in session["events"]), encoding="utf-8")
    metrics = summarize(arm, session["events"], list(read_jsonl(decisions)) if decisions.exists() else [])
    if session["timed_out"]:
        metrics.update(valid=False, invalid_reason=f"timed out after {task.timeout_s} s")
    judge_model = None if args.judge_model == "none" else args.judge_model
    return {"task": task.name, "arm": arm, "rep": rep, "model": args.model, **metrics,
            "timed_out": session["timed_out"], "exit_code": session["exit_code"], "wall_s": session["wall_s"],
            "grade": grade(task, workspace, run_dir, judge_model, args.claude)}


def write_report(out: Path) -> Path:
    report = out / "report.md"
    report.write_text(render(list(read_jsonl(out / "results.jsonl"))), encoding="utf-8")
    return report


def regrade(out: Path) -> Path:
    """Deterministic grading only, so a fixed checklist rescores old runs at no model cost."""
    path = out / "results.jsonl"
    records = list(read_jsonl(path))
    tasks = {task.name: task for task in load_tasks(",".join(sorted({r["task"] for r in records})))}
    for record in records:
        run_dir = out / record["task"] / f"{record['arm']}-{record['rep']}"
        graded = grade(tasks[record["task"]], run_dir / "workspace", run_dir, None)
        record["grade"] = {**graded, "judge": record["grade"].get("judge")}
    if not (out / "results.jsonl.bak").exists():  # keep the first backup: it holds the original grades
        path.replace(out / "results.jsonl.bak")
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return write_report(out)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.regrade:
        print(regrade(Path(args.regrade)))
        return 0
    if args.report:
        print(write_report(Path(args.report)))
        return 0
    tasks = load_tasks(args.tasks)
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    if not arms or set(arms) - {"on", "off"}:
        raise SystemExit("--arms takes on, off, or on,off")
    plan = schedule(tasks, arms, args.reps)
    worst = sum(task.budget_usd for _, task, _ in plan)
    if args.dry_run:
        for rep, task, arm in plan:
            print(f"rep {rep} {task.name} {arm}: {shlex.join(command(task, arm, args.model, args.claude))}")
        print(f"{len(plan)} runs; worst case if every run hits its budget cap: ${worst:.0f} plus the judge")
        return 0
    out = Path(args.out) if args.out else RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    print(f"{len(plan)} runs into {out} (budget caps total ${worst:.0f})", flush=True)
    for i, (rep, task, arm) in enumerate(plan, 1):
        record = run_one(task, arm, rep, out / task.name / f"{arm}-{rep}", args)
        with (out / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        judge = (record["grade"].get("judge") or {}).get("score")
        print(f"[{i}/{len(plan)}] {task.name} {arm} rep {rep}: "
              f"{'ok' if record['valid'] else record['invalid_reason']} · score {record['grade']['score']} · "
              f"judge {judge} · ${record['cost_usd'] or 0:.2f} · {record['wall_s'] / 60:.1f} min", flush=True)
    print(write_report(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
