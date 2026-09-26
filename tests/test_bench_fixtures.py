import json

import pytest
from test_bench_formats import workbook

from toolhint.bench import load_tasks
from toolhint.bench.grade import checklist, grade, hidden_tests
from toolhint.bench.session import prepare_workspace


def task(name):
    [loaded] = load_tasks(name)
    return loaded


def score(name, text):
    loaded = task(name)
    return checklist(text, json.loads((loaded.root / loaded.grading["checklist"]).read_text()))


def test_every_task_loads():
    assert [t.name for t in load_tasks("all")] == ["coding-app", "landing-page", "research-local", "research-web",
                                                  "spreadsheet"]


def test_the_reference_solution_passes_every_hidden_test():
    coding = task("coding-app")
    counts = hidden_tests(coding, coding.root / "reference")
    assert counts["failed"] == counts["errors"] == 0 and counts["passed"] == 15


def test_an_empty_workspace_passes_no_hidden_test(tmp_path):
    counts = hidden_tests(task("coding-app"), tmp_path)
    assert counts["passed"] == 0 and counts["failed"] == 15


@pytest.mark.parametrize("name", ["research-local", "research-web"])
def test_each_reference_answer_passes_its_own_checklist(name):
    result = score(name, (task(name).root / "reference.md").read_text())
    assert result["passed"] == result["total"], [check for check, ok in result["checks"].items() if not ok]


def test_the_misleading_email_alone_scores_low_on_the_brief_checklist():
    email = (task("research-local").root / "workspace" / "sources" / "06-email-sales-director.txt").read_text()
    result = score("research-local", email)
    assert result["passed"] / result["total"] < 0.3


def test_graders_and_references_are_outside_the_starting_workspace():
    for loaded in load_tasks("all"):
        workspace = loaded.root / "workspace"
        names = {p.name for p in workspace.rglob("*")} if workspace.is_dir() else set()
        assert not names & {"hidden", "reference", "reference.md", "checklist.json", "task.json", "prompt.md"}


def test_the_brief_checklist_accepts_the_phrasings_real_runs_used():
    result = score("research-local", "## Recommendation\n\n**Sign RouteLoom by 15 July [05].** See [01], [02], [03], [04].")
    assert result["checks"]["recommends_routeloom"] and result["checks"]["cites_4_sources"]
    assert not score("research-local", "## Recommendation\n\nSign Pathwise now.")["checks"]["recommends_routeloom"]
    listed = score("research-local", "HR starts works-council consultation [03, 05]; see [01; 02].")["checks"]
    assert listed["works_council"] and listed["cites_4_sources"]


def graded(name, tmp_path, filename, content):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    target = workspace / filename
    target.write_bytes(content) if isinstance(content, bytes) else target.write_text(content)
    return grade(task(name), workspace, tmp_path, None)


def test_the_reference_workbook_passes_and_typed_numbers_fail(tmp_path):
    reference = (task("spreadsheet").root / "reference" / "comparison.xlsx").read_bytes()
    assert graded("spreadsheet", tmp_path, "comparison.xlsx", reference)["score"] == 1.0
    typed = workbook(tmp_path / "typed.xlsx", ['<c r="A1"><v>680000</v></c>', '<c r="B1"><v>623000</v></c>'])
    assert graded("spreadsheet", tmp_path, "comparison.xlsx", typed.read_bytes())["score"] < 0.3


def test_the_reference_page_passes_and_a_bare_page_fails(tmp_path):
    page = (task("landing-page").root / "reference" / "index.html").read_text()
    assert graded("landing-page", tmp_path, "index.html", page)["score"] == 1.0
    assert graded("landing-page", tmp_path, "index.html", "<h1>RouteLoom</h1><p>Soon.</p>")["score"] < 0.3


def test_the_spreadsheet_workspace_gets_real_copies_of_the_shared_sources(tmp_path):
    workspace = prepare_workspace(task("spreadsheet"), tmp_path / "run")
    source = workspace / "sources" / "03-vendor-quotes.md"
    assert source.is_file() and not source.is_symlink() and not (workspace / "sources").is_symlink()
