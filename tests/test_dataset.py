import json

from laya_router.dataset import build, prompt_text, rows_from_transcript


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
