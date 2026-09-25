from laya_router.engine import PREFIX, format_hint
from laya_router.items import Candidate, Ranking


def test_empty_ranking_formats_to_empty_string():
    assert format_hint(Ranking()) == ""


def test_hint_groups_tools_under_connectors():
    ranking = Ranking(
        skills=[Candidate("superpowers:systematic-debugging", "Use when...", 0.62)],
        connectors=[Candidate("Gmail", "Gmail tools", 0.71)],
        tools=[Candidate("mcp__claude_ai_Gmail__search_threads", "Gmail: Search", 0.55, "Gmail"),
               Candidate("mcp__context7__query-docs", "context7: Query", 0.4, "context7")])
    assert format_hint(ranking) == (
        PREFIX + "skills: superpowers:systematic-debugging (0.62) · "
        "connectors: Gmail (0.71) → mcp__claude_ai_Gmail__search_threads · "
        "tools: mcp__context7__query-docs (0.40)")


def test_hint_is_capped():
    hint = format_hint(Ranking(skills=[Candidate("s" * 300, "x", 0.9), Candidate("t" * 300, "y", 0.5)]))
    assert len(hint) == 400 and hint.endswith("…")
