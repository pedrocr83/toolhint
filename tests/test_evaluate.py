from laya_router.engine import NONE_ID
from laya_router.evaluate import bm25_method, calibrate, canonical_ids, evaluate, gate_lines, none_rate, pick_tau
from laya_router.items import Item

KNOWN = {"claude-code": {"skill": {"x", "y", "z", "w"}, "connector": set(), "tool": set()}}


def test_bm25_baseline_indexes_item_names():
    items = [Item("skill", "pptx", "Work with files", "Use for decks"),
             Item("skill", "xlsx", "Work with files", "Use for tabular work")]
    assert bm25_method(items)("export it as xlsx")["skill"][0] == "xlsx"


def test_evaluate_counts_top1_top3_and_skips_unknown_gold():
    rows = [{"prompt": p, "harness": "claude-code", "gold": {"skill": g}} for p, g in (("a", "x"), ("b", "y"), ("c", "gone"))]
    ranked = {"a": {"skill": ["x", "y", "z"]}, "b": {"skill": [NONE_ID, "z", "w", "y"]}, "c": {"skill": ["x"]}}
    result = evaluate(rows, KNOWN, {"claude-code": lambda prompt: ranked[prompt]})
    assert result["kinds"]["skill"] == {"n": 2, "top1": 0.5, "top3": 1.0, "unknown": 1, "none_first": 1}


def test_evaluate_counts_equivalent_duplicate_skills_as_hits():
    items = [Item("skill", "anthropic-skills:pdf", "Work with PDF files.", "t"),
             Item("skill", "document-skills:pdf", "Work with PDF files.", "t"),
             Item("skill", "anthropic-skills:xlsx", "Work with spreadsheets.", "t")]
    canon = {"claude-code": canonical_ids(items)}
    known = {"claude-code": {"skill": {i.id for i in items}, "connector": set(), "tool": set()}}
    rows = [{"prompt": "a", "harness": "claude-code", "gold": {"skill": "document-skills:pdf"}}]
    ranked = {"a": {"skill": ["anthropic-skills:pdf", "anthropic-skills:xlsx"]}}
    result = evaluate(rows, known, {"claude-code": lambda prompt: ranked[prompt]}, canon)
    assert result["kinds"]["skill"]["top1"] == 1.0


def test_calibrate_treats_none_first_as_abstain():
    rows = [{"prompt": p, "harness": "claude-code", "gold": {"skill": "x"}} for p in ("a", "b", "c")]
    scored = {"a": {"skill": [("x", 0.8)]}, "b": {"skill": [("y", 0.6)]}, "c": {"skill": [(NONE_ID, 0.9)]}}
    assert calibrate(rows, "skill", scored, taus=(0.5, 0.7)) == [
        {"tau": 0.5, "precision": 0.5, "recall": 0.333, "alarm": 0.0},
        {"tau": 0.7, "precision": 1.0, "recall": 0.333, "alarm": 0.0}]


def test_calibrate_reports_alarm_rate_on_unlabeled_turns():
    rows = [{"prompt": "a", "harness": "claude-code", "gold": {"skill": "x"}}]
    scored = {"a": {"skill": [("x", 0.8)]}, "n1": {"skill": [("y", 0.6)]}, "n2": {"skill": [(NONE_ID, 0.9)]}}
    table = calibrate(rows, "skill", scored, taus=(0.5, 0.7), negatives=["n1", "n2"])
    assert [row["alarm"] for row in table] == [0.5, 0.0]


def test_pick_tau_prefers_smallest_tau_meeting_precision_else_best_f1():
    table = [{"tau": 0.2, "precision": 0.6, "recall": 0.9}, {"tau": 0.3, "precision": 0.8, "recall": 0.7}]
    assert pick_tau(table, 0.75) == 0.3
    assert pick_tau([{"tau": 0.2, "precision": 0.5, "recall": 0.9}, {"tau": 0.3, "precision": 0.6, "recall": 0.2}], 0.75) == 0.2


def test_pick_tau_keeps_false_alarms_under_the_cap():
    table = [{"tau": 0.2, "precision": 0.8, "recall": 0.7, "alarm": 0.6},
             {"tau": 0.5, "precision": 0.9, "recall": 0.3, "alarm": 0.08}]
    assert pick_tau(table, 0.75, max_alarm=0.10) == 0.5


def test_none_rate_counts_turns_where_every_kind_abstains():
    rows = [{"prompt": "a", "harness": "claude-code"}, {"prompt": "b", "harness": "claude-code"}]
    ranked = {"a": {"skill": [NONE_ID, "x"], "tool": [NONE_ID]}, "b": {"skill": ["x", NONE_ID]}}
    assert none_rate(rows, {"claude-code": lambda prompt: ranked[prompt]}) == 0.5


def test_gate_lines_rate_best_laya_on_dev_skills():
    def result(dev_top3: float, p95: float) -> dict:
        return {"dev": {"kinds": {"skill": {"top3": dev_top3}}}, "test": {"p95_ms": p95}}

    lines = gate_lines({"bm25": result(0.5, 1.0), "laya-english-k10": result(0.6, 90.0),
                        "laya-typed-decisions-k10": result(0.75, 120.0)}, "cuda")
    assert lines[2] == "Best: laya-typed-decisions-k10"
    assert "dev top-3 skill recall 0.75 >= 0.70: PASS" in lines[3]
    assert "+0.25" in lines[4] and lines[4].endswith("PASS") and lines[5].endswith("PASS")
