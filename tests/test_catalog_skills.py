import json

import pytest

from toolhint.catalog import claude_code_skills, cowork_skills, make_item, one_line, scan_commands, scan_skills


def test_one_line_takes_first_sentence_and_truncates():
    assert one_line("Fix bugs. Then more.") == "Fix bugs."
    assert len(one_line("x" * 200)) == 80


@pytest.mark.parametrize(("description", "label"), [
    ("Use when a task needs reading many files. More text.", "a task needs reading many files."),
    ("Use this skill to draft replies to email threads.", "draft replies to email threads."),
    ("This skill should be used when the user asks for slides.", "the user asks for slides."),
    ("Use AFTER code changes are complete.", "AFTER code changes are complete."),
    ("Useful helpers for PDFs.", "Useful helpers for PDFs."),
])
def test_labels_drop_leading_boilerplate(description, label):
    item = make_item("skill", "s", description, "user")
    assert item.label == label
    assert item.text == description


def test_scan_skills_reads_name_and_description(tmp_path, write_skill):
    write_skill(tmp_path, "graphify", '---\nname: graphify\ndescription: "any input to knowledge graph. Use when asked."\n---\n')
    [item] = scan_skills(tmp_path)
    assert (item.kind, item.id, item.label) == ("skill", "graphify", "any input to knowledge graph.")


def test_scan_skills_skips_malformed_and_disabled(tmp_path, write_skill):
    write_skill(tmp_path, "bad-yaml", "---\nname: [unclosed\ndescription: x\n---\n")
    write_skill(tmp_path, "no-desc", "---\nname: no-desc\n---\n")
    write_skill(tmp_path, "bad-date", "---\nname: bad-date\ndescription: x\ncreated: 2024-02-30\n---\n")
    write_skill(tmp_path, "no-frontmatter", "# just a heading\n")
    write_skill(tmp_path, "hidden", "---\nname: hidden\ndescription: secret\ndisable-model-invocation: true\n---\n")
    (tmp_path / "binary").mkdir()
    (tmp_path / "binary" / "SKILL.md").write_bytes(b"\xff\xfe---\x00")
    write_skill(tmp_path, "good", "---\nname: good\ndescription: >\n  Folded block\n  description.\n---\n")
    items = scan_skills(tmp_path)
    assert [i.id for i in items] == ["good"]
    assert items[0].label == "Folded block description."


def test_scan_commands_uses_file_stem(tmp_path):
    (tmp_path / "explore.md").write_text("---\ndescription: Delegate read-only exploration\n---\nbody\n")
    (tmp_path / "nodesc.md").write_text("no frontmatter\n")
    assert [i.id for i in scan_commands(tmp_path, prefix="p")] == ["p:explore"]


def test_claude_code_skills_include_synced_commands_and_enabled_plugins(tmp_path, write_skill):
    home = tmp_path
    write_skill(home / ".claude" / "skills", "mine")
    write_skill(home / ".claude" / "skills" / "synced" / "org_acct", "pdf")
    (home / ".claude" / "commands").mkdir(parents=True)
    (home / ".claude" / "commands" / "fix.md").write_text("---\ndescription: Small scoped fix\n---\n")
    plugin_root, off_root = home / "cache" / "superpowers" / "6.4.1", home / "cache" / "off" / "1"
    write_skill(plugin_root / "skills", "brainstorming")
    write_skill(off_root / "skills", "nope")
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"superpowers@official": True, "off@official": False}}))
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "superpowers@official": [{"installPath": str(plugin_root)}],
        "off@official": [{"installPath": str(off_root)}]}}))
    ids = sorted(i.id for i in claude_code_skills(home, cwd=None))
    assert ids == ["anthropic-skills:pdf", "fix", "mine", "superpowers:brainstorming"]


def test_cowork_skills_from_manifest_and_session_plugins(tmp_path, write_skill):
    manifest = tmp_path / ".config/Claude/local-agent-mode-sessions/skills-plugin/org/acct/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"skills": [
        {"name": "pdf", "description": "Work with PDF files.", "enabled": True},
        {"name": "off", "description": "Disabled.", "enabled": False}]}))
    plugin = tmp_path / "userplugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "mytools"}))
    write_skill(plugin / "skills", "deploy")
    session = {"skillsEnabled": "true", "pluginInstallPaths": [str(plugin)]}
    assert sorted(i.id for i in cowork_skills(tmp_path, session)) == ["anthropic-skills:pdf", "mytools:deploy"]
    assert cowork_skills(tmp_path, {"skillsEnabled": False}) == []
