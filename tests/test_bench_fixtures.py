import json

import pytest

from toolhint.bench import load_tasks
from toolhint.bench.grade import checklist, hidden_tests


def task(name):
    [loaded] = load_tasks(name)
    return loaded


def score(name, text):
    loaded = task(name)
    return checklist(text, json.loads((loaded.root / loaded.grading["checklist"]).read_text()))


def test_every_task_loads():
    assert [t.name for t in load_tasks("all")] == ["coding-app", "research-local", "research-web"]


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
