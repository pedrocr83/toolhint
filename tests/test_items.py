from laya_router.items import Ranking, RouteContext

COWORK_TRANSCRIPT = "/home/u/.config/Claude/local-agent-mode-sessions/a/b/local_1/.claude/projects/x/s.jsonl"


def test_harness_detected_from_transcript_path():
    assert RouteContext("hi", transcript_path=COWORK_TRANSCRIPT).harness == "cowork"
    assert RouteContext("hi", transcript_path="/home/u/.claude/projects/x/s.jsonl").harness == "claude-code"
    assert RouteContext("hi").harness == "claude-code"


def test_empty_ranking_reports_empty():
    assert Ranking().is_empty()
