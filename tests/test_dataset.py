import json

from toolhint.dataset import build, previous_prompt, prompt_text, rows_from_transcript


def user(content, **extra):
    return {"type": "user", "message": {"role": "user", "content": content}, **extra}


def tool_result():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}


def assistant(*uses, **extra):
    blocks = [{"type": "tool_use", "name": name, "input": data} for name, data in uses]
    return {"type": "assistant", "message": {"content": blocks}, **extra}


def write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\nnot json\n", encoding="utf-8")


def test_prompt_text_filters_non_prompts():
    assert prompt_text(user("hello there")) == "hello there"
    assert prompt_text(tool_result()) is None
    assert prompt_text(user("x", isMeta=True)) is None
    assert prompt_text(user("x", isSidechain=True)) is None
    assert prompt_text(user("<command-name>/compact</command-name>")) is None
    assert prompt_text(user("<ide_opened_file>a.py</ide_opened_file> fix the bug")) == "fix the bug"
    assert prompt_text(user([{"type": "text", "text": "list form"}])) == "list form"


def test_rows_label_first_skill_and_mcp_tool(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, [
        user("plan the new feature"),
        assistant(("Skill", {"skill": "superpowers:brainstorming"}), ("Skill", {"skill": "other"})),
        tool_result(),
        assistant(("mcp__claude_ai_Gmail__search_threads", {"q": "x"})),
        assistant(("mcp__context7__query-docs", {}), isSidechain=True),
        user("thanks, now explain it"),
    ])
    rows = list(rows_from_transcript(path, "claude-code"))
    assert rows[0]["gold"] == {"skill": "superpowers:brainstorming",
                               "tool": "mcp__claude_ai_Gmail__search_threads", "connector": "Gmail"}
    assert rows[1]["gold"] == {} and rows[1]["source"] == "transcript-none"


def test_build_dedupes_and_splits(tmp_path):
    entries = [user("plan the new feature"), assistant(("Skill", {"skill": "superpowers:brainstorming"})),
               user("small talk only")]
    write(tmp_path / ".claude" / "projects" / "-p1" / "a.jsonl", entries)
    write(tmp_path / ".claude" / "projects" / "-p2" / "b.jsonl", entries)
    assert build(tmp_path, tmp_path / "out") == {"labeled": 1, "negatives": 1}
    rows = [json.loads(line) for line in (tmp_path / "out" / "transcripts.jsonl").read_text().splitlines()]
    assert rows[0]["harness"] == "claude-code"


def test_cowork_rows_map_connector_uuid_to_name(tmp_path):
    root = tmp_path / ".config" / "Claude" / "local-agent-mode-sessions" / "acct" / "org"
    (root / "local_1.json").parent.mkdir(parents=True)
    (root / "local_1.json").write_text(json.dumps({"remoteMcpServersConfig": [{"name": "Gmail", "uuid": "7729dcbf"}]}))
    write(root / "local_1" / ".claude" / "projects" / "p" / "s.jsonl",
          [user("find the contract email"), assistant(("mcp__7729dcbf__search_threads", {}))])
    assert build(tmp_path, tmp_path / "out") == {"labeled": 1, "negatives": 0}
    row = json.loads((tmp_path / "out" / "transcripts.jsonl").read_text())
    assert row["harness"] == "cowork"
    assert row["gold"] == {"tool": "mcp__7729dcbf__search_threads", "connector": "Gmail"}


def test_previous_prompt_is_the_latest_real_prompt_before_the_current_one(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, [user("refactor the auth module"), assistant(("Read", {})), tool_result(), user("and the unit tests?")])
    assert previous_prompt(str(path), "and the unit tests?") == "refactor the auth module"
    assert previous_prompt(str(path), "a brand new prompt") == "and the unit tests?"


def test_previous_prompt_reads_only_the_tail_and_fails_open(tmp_path):
    path = tmp_path / "s.jsonl"
    write(path, [user("an old prompt")] + [assistant(("Read", {"file_path": "x" * 500}))] * 20)
    assert previous_prompt(str(path), "now", tail_bytes=2048) == ""
    assert previous_prompt(str(tmp_path / "missing.jsonl"), "now") == ""
    assert previous_prompt("", "now") == ""


def test_prompt_text_skips_compaction_summaries_and_interrupt_markers():
    assert prompt_text(user("This session is being continued from a previous conversation", isCompactSummary=True)) is None
    assert prompt_text(user([{"type": "text", "text": "[Request interrupted by user]"}])) is None
    assert prompt_text(user([{"type": "text", "text": "[Request interrupted by user for tool use]"}])) is None


def test_previous_prompt_reaches_past_large_tool_results(tmp_path):
    path = tmp_path / "s.jsonl"
    big = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x" * 1_000_000}]}}
    write(path, [user("refactor the auth module"), assistant(("Read", {})), big, user("ok do it")])
    assert previous_prompt(str(path), "ok do it") == "refactor the auth module"
