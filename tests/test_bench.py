import json
import sys
from pathlib import Path

from toolhint.bench import Task
from toolhint.bench.grade import checklist, judge_verdict, pytest_counts
from toolhint.bench.metrics import summarize
from toolhint.bench.report import render
from toolhint.bench.session import (
    OFF_SETTINGS,
    clean_env,
    command,
    prepare_workspace,
    run,
)

TDD = "superpowers:test-driven-development"
RESULT = {"type": "result", "subtype": "success", "session_id": "s1", "total_cost_usd": 1.25, "num_turns": 7,
          "modelUsage": {"sonnet": {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 300,
                                    "cacheCreationInputTokens": 400},
                         "haiku": {"inputTokens": 1, "outputTokens": 2, "cacheReadInputTokens": 3,
                                   "cacheCreationInputTokens": 4}},
          "permission_denials": [{"tool_name": "Bash"}], "subagent_stats": {"spawned": 1}}
DECISION = {"session": "s1", "skills": [{"id": TDD, "p": 0.61}], "connectors": [], "tools": [], "device": "cuda",
            "latency_ms": 50.0}
TASK = Task("t", Path("."), "do it", 2.0, 60, ("WebSearch",), {"kind": "checklist"})


def init(plugins=("toolhint",), connected=True):
    servers = [{"name": "plugin:toolhint:router", "status": "connected"}] if connected else []
    return {"type": "system", "subtype": "init", "session_id": "s1", "plugins": [{"name": p} for p in plugins],
            "mcp_servers": servers}


def tool_use(name, uid, parent=None, **data):
    block = {"type": "tool_use", "id": uid, "name": name, "input": data}
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [block]}}


def test_summarize_counts_tools_skills_tokens_and_hint_uptake():
    events = [init(), tool_use("Skill", "t1", skill=TDD), tool_use("Read", "t2"), tool_use("Read", "t2"),
              tool_use("Bash", "t3", parent="t9"), RESULT]
    m = summarize("on", events, [DECISION, {"session": "", "skills": []}])
    assert m["valid"] and m["tools"] == {"Skill": 1, "Read": 1} and m["subagent_tools"] == {"Bash": 1}
    assert m["skills"] == [TDD] and m["hints"] == [{"id": TDD, "kind": "skill", "p": 0.61}] and m["hint_uptake"] == [TDD]
    assert m["tokens"] == {"input": 11, "output": 22, "cache_read": 303, "cache_creation": 404}
    assert m["denials"] == ["Bash"] and m["subagents"] == 1 and m["model_route_calls"] == 1
    assert (m["router_device"], m["cost_usd"], m["num_turns"]) == ("cuda", 1.25, 7)


def test_arm_checks_flag_mislabelled_runs():
    assert summarize("off", [init(), RESULT], [])["invalid_reason"] == "toolhint loaded in the off arm"
    assert summarize("off", [init(plugins=(), connected=False), RESULT], [])["valid"]
    assert "not routed" in summarize("on", [init(), RESULT], [])["invalid_reason"]
    assert summarize("on", [init(connected=False), RESULT], [DECISION])["invalid_reason"] == "toolhint router not connected"
    assert summarize("on", [init()], [DECISION])["invalid_reason"] == "no result event"


def test_checklist_supports_one_pattern_all_patterns_distinct_hits_and_a_word_limit():
    checks = [{"id": "a", "pattern": r"route\w*"}, {"id": "b", "patterns": [r"1\.9\s?%", r"1\.1\s?%"]},
              {"id": "c", "distinct": r"0[1-6]-[a-z]+\.md", "min": 2}, {"id": "d", "max_words": 5}]
    result = checklist("RouteLoom cut mis-picks from 1.9% to 1.1% (01-pilot.md, 01-pilot.md)", checks)
    assert result["checks"] == {"a": True, "b": True, "c": False, "d": False}
    assert (result["passed"], result["total"]) == (2, 4)


def test_pytest_counts_reads_the_summary_line():
    assert pytest_counts("..F\n1 failed, 12 passed, 2 errors in 0.52s\n") == {"passed": 12, "failed": 1, "errors": 2}
    assert pytest_counts("no tests ran in 0.01s") == {"passed": 0, "failed": 0, "errors": 0}


def test_judge_verdict_parses_the_json_in_the_reply():
    reply = json.dumps({"result": 'Here:\n{"score": 8, "reason": "solid"}', "total_cost_usd": 0.02})
    assert judge_verdict(reply) == {"score": 8, "reason": "solid", "cost_usd": 0.02}
    assert judge_verdict(json.dumps({"result": "no idea", "total_cost_usd": 0.01}))["score"] is None
    assert judge_verdict("not json")["score"] is None


def test_off_arm_disables_both_toolhint_copies():
    on, off = command(TASK, "on", "sonnet"), command(TASK, "off", "sonnet")
    assert "--settings" not in on and json.loads(off[off.index("--settings") + 1]) == OFF_SETTINGS
    assert OFF_SETTINGS["enabledPlugins"] == {"toolhint@toolhint": False, "toolhint@synced": False}
    assert on[on.index("--max-budget-usd") + 1] == "2" and on[-1] == "WebSearch" and "--no-session-persistence" in on


def test_clean_env_drops_the_launching_sessions_identity(tmp_path):
    base = {"PATH": "/bin", "HOME": "/h", "CLAUDECODE": "1", "CLAUDE_EFFORT": "xhigh", "VSCODE_PID": "1",
            "ENABLE_TOOL_SEARCH": "1"}
    assert clean_env(base, tmp_path / "d.jsonl") == {"PATH": "/bin", "HOME": "/h", "TOOLHINT_LOG": str(tmp_path / "d.jsonl")}


def test_workspace_gets_the_starting_files_but_not_the_graders(tmp_path):
    root = tmp_path / "task"
    (root / "workspace" / "sources").mkdir(parents=True)
    (root / "workspace" / "sources" / "a.md").write_text("x")
    (root / "hidden").mkdir()
    (root / "hidden" / "test_x.py").write_text("")
    (root / "reference.md").write_text("answer")
    ws = prepare_workspace(Task("t", root, "p", 1, 1, (), {}), tmp_path / "run")
    assert (ws / "sources" / "a.md").read_text() == "x" and (ws / ".git").is_dir()
    assert not any(p.name in ("hidden", "test_x.py", "reference.md") for p in ws.rglob("*"))


FAKE_CLAUDE = """import json, sys, time
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}), flush=True)
for line in sys.stdin:
    if "hang" in line:
        time.sleep(60)
    print(json.dumps({"type": "result", "subtype": "success", "result": json.loads(line)["message"]["content"]}), flush=True)
"""


def test_run_sends_the_prompt_and_stops_at_the_result(tmp_path):
    fake = tmp_path / "claude.py"
    fake.write_text(FAKE_CLAUDE)
    out = run([sys.executable, str(fake)], tmp_path, None, "hello", 0, 10, tmp_path / "err.log")
    assert not out["timed_out"] and out["events"][-1]["result"] == "hello" and out["exit_code"] == 0


def test_run_kills_a_session_that_times_out(tmp_path):
    fake = tmp_path / "claude.py"
    fake.write_text(FAKE_CLAUDE)
    out = run([sys.executable, str(fake)], tmp_path, None, "hang", 0, 1, tmp_path / "err.log")
    assert out["timed_out"] and out["events"][-1]["subtype"] == "init"


def record(arm, rep, score, cost, skills=(), valid=True):
    return {"task": "coding-app", "arm": arm, "rep": rep, "valid": valid, "invalid_reason": "" if valid else "no result",
            "grade": {"score": score, "judge": {"score": 7}}, "cost_usd": cost, "num_turns": 5, "wall_s": 600,
            "tokens": {"input": 1, "output": 2, "cache_read": 3, "cache_creation": 4}, "tools": {"Read": 2},
            "subagent_tools": {}, "subagents": 0, "denials": [], "skills": list(skills), "hints": [], "hint_uptake": [],
            "result_subtype": "success"}


def test_report_compares_arms_on_valid_runs_only():
    text = render([record("on", 1, 1.0, 2.0, [TDD]), record("on", 2, 0.5, 4.0), record("off", 1, 0.8, 1.0),
                   record("off", 2, 0.0, 9.0, valid=False)])
    assert "## coding-app" in text and "| score (tests or checklist) | 0.75 ± 0.35 (2) | 0.8 (1) |" in text
    assert f"{TDD} ×1" in text and "no result" in text


def test_schedule_alternates_arms_and_flips_the_first_arm_each_rep():
    from toolhint.bench.__main__ import schedule
    order = [(rep, arm) for rep, _, arm in schedule([TASK], ["on", "off"], 3)]
    assert order == [(1, "on"), (1, "off"), (2, "off"), (2, "on"), (3, "on"), (3, "off")]


def test_dry_run_lists_every_run_without_starting_one(capsys):
    from toolhint.bench.__main__ import main
    assert main(["--dry-run", "--tasks", "research-local", "--reps", "2"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines[:4]] == ["rep 1 research-local on", "rep 1 research-local off",
                                                         "rep 2 research-local off", "rep 2 research-local on"]
    assert "--settings" in lines[1] and "--settings" not in lines[0] and "4 runs" in lines[4]


def test_the_router_log_path_is_absolute_because_the_router_runs_inside_the_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert clean_env({}, Path("runs/d.jsonl"))["TOOLHINT_LOG"] == str(tmp_path / "runs" / "d.jsonl")


def test_distinct_counts_the_capture_group_when_the_pattern_has_one():
    checks = [{"id": "sources", "distinct": r"(?:\b|\[)0([1-6])(?:-[a-z]|\])", "min": 3}]
    assert checklist("[01] and 01-pilot.md and [02]", checks)["passed"] == 0
    assert checklist("[01], 02-metrics.csv and [03]", checks)["passed"] == 1


def test_regrade_rescores_saved_workspaces_and_keeps_the_judge(tmp_path):
    from toolhint.bench.__main__ import main
    workspace = tmp_path / "research-local" / "on-1" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "BRIEF.md").write_text("## Recommendation\n\nSign RouteLoom by 15 July [05].")
    old = {**record("on", 1, 0.0, 1.0), "task": "research-local"}
    old["grade"]["judge"] = {"score": 5}
    call = {"type": "assistant", "message": {"id": "m1", "usage": usage(1, 2, 3), "content": []}}
    (workspace.parent / "events.jsonl").write_text("\n".join(json.dumps(e) for e in [init(), call, RESULT]) + "\n")
    (tmp_path / "results.jsonl").write_text(json.dumps(old) + "\n")
    assert main(["--regrade", str(tmp_path)]) == 0
    [new] = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert new["grade"]["detail"]["checks"]["recommends_routeloom"] and new["grade"]["score"] > 0
    assert new["grade"]["judge"] == {"score": 5} and new["context_first"] == 6
    assert (tmp_path / "report.md").exists()
    main(["--regrade", str(tmp_path)])
    [kept] = [json.loads(line) for line in (tmp_path / "results.jsonl.bak").read_text().splitlines()]
    assert kept["grade"]["score"] == 0.0  # the first backup holds the original grades


def test_sessions_cannot_install_packages():
    cmd = command(TASK, "on", "sonnet")
    denied = cmd[cmd.index("--disallowedTools") + 1:cmd.index("--allowedTools")]
    assert {"Bash(pip:*)", "Bash(python3 -m pip:*)", "Bash(uv pip:*)", "Bash(npm install:*)"} <= set(denied)


def test_run_sends_follow_ups_while_the_callback_returns_text(tmp_path):
    fake = tmp_path / "claude.py"
    fake.write_text(FAKE_CLAUDE)
    replies = iter(["go ahead", None])
    out = run([sys.executable, str(fake)], tmp_path, None, "hello", 0, 10, tmp_path / "err.log", lambda: next(replies))
    assert [e["result"] for e in out["events"] if e["type"] == "result"] == ["hello", "go ahead"]
    assert out["followups"] == 1 and not out["timed_out"]


def usage(total_input, cache_read, cache_write):
    return {"input_tokens": total_input, "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": cache_write}


def test_summarize_adds_up_turns_and_measures_context():
    first = {"type": "assistant", "message": {"id": "m1", "usage": usage(10, 0, 40000), "content": [
        {"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}}
    result_block = {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 4000}
    tool_result = {"type": "user", "parent_tool_use_id": None, "message": {"content": [result_block]}}
    later = {"type": "assistant", "message": {"id": "m2", "usage": usage(5, 40000, 1200), "content": []}}
    sub = {"type": "assistant", "parent_tool_use_id": "t9", "message": {"id": "m3", "usage": usage(1, 0, 90000),
                                                                           "content": []}}
    results = [{**RESULT, "num_turns": 3, "permission_denials": [{"tool_name": "Bash"}]},
               {**RESULT, "num_turns": 2, "permission_denials": [{"tool_name": "WebFetch"}]}]
    m = summarize("off", [init(plugins=(), connected=False), first, tool_result, later, sub, *results], [])
    assert m["num_turns"] == 5 and m["denials"] == ["Bash", "WebFetch"]
    assert (m["context_first"], m["context_peak"], m["tool_output_tokens"]) == (40010, 41205, 1000)


def test_large_numbers_read_as_thousands():
    from toolhint.bench.report import stat
    assert stat([39882.0, 39912.0]) == "39,897 ± 21 (2)" and stat([0.5]) == "0.5 (1)"


GROUP_KILLER = """import json, os, signal, sys
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}), flush=True)
sys.stdin.readline()
print(json.dumps({"type": "result", "subtype": "success", "result": "done"}), flush=True)
os.killpg(os.getpgid(0), signal.SIGTERM)  # what cleaning up background shells by process group can do
"""


def test_a_session_that_signals_its_process_group_cannot_take_the_harness_down(tmp_path):
    fake = tmp_path / "claude.py"
    fake.write_text(GROUP_KILLER)
    out = run([sys.executable, str(fake)], tmp_path, None, "hello", 0, 10, tmp_path / "err.log")
    assert out["events"][-1]["result"] == "done" and not out["timed_out"]


def test_a_run_that_crashes_the_harness_is_skipped_and_the_batch_goes_on(tmp_path, monkeypatch, capsys):
    import toolhint.bench.__main__ as cli
    outcomes = iter([RuntimeError("boom"), {**record("off", 1, 1.0, 0.1), "task": "research-local"}])

    def fake_run_one(*_args):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(cli, "run_one", fake_run_one)
    assert cli.main(["--tasks", "research-local", "--reps", "1", "--out", str(tmp_path)]) == 0
    assert "harness error" in capsys.readouterr().out
    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == 1 and (tmp_path / "report.md").exists()
