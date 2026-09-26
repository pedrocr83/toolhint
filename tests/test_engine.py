from fakes import FakeScorer

from toolhint.engine import NONE_ID, Engine, EngineConfig, option_keys, should_skip
from toolhint.items import Item

K2 = EngineConfig(k={"skill": 2, "connector": 15, "tool": 10})
PROMPT = "please debug the failing test"


def skill(item_id: str, text: str) -> Item:
    return Item("skill", item_id, text[:80], text)


SKILLS = [skill("debugging", "debug failing test errors"), skill("slides", "make slides decks"),
          skill("email-writer", "write email drafts"), skill("calendar-helper", "calendar scheduling"),
          skill("browser-bot", "drive the browser"), skill("deployer", "deploy services"),
          skill("doc-writer", "write docs pages"), skill("tester", "write test suites")]


def test_skip_rules():
    assert should_skip("/brainstorm build x", "", 12)
    assert should_skip("ok thanks", "", 12)
    assert should_skip("same prompt here!", "same prompt here!", 12)
    assert not should_skip(PROMPT, "", 12)


def test_rank_skips_without_calling_scorer():
    scorer = FakeScorer()
    assert Engine(scorer).rank("/compact now please", SKILLS).is_empty()
    assert not scorer.choose_calls


def test_shortlist_keeps_top_k_lexical_matches():
    scorer = FakeScorer()
    Engine(scorer, K2).scores("debug this failing test", SKILLS)
    assert set(scorer.choose_calls[0][1]["skill"]["criteria"]) == {"debugging", "tester", NONE_ID}


def test_shortlist_ranks_by_bm25_over_name_and_description():
    pool = [skill("slides", "make slides decks"), skill("notes", "take meeting notes"),
            skill("anthropic-skills:xlsx", "work with tabular files"), skill("reports", "build quarterly workbook reports")]
    scorer = FakeScorer()
    Engine(scorer, K2).scores("turn this csv into an xlsx workbook", pool)
    assert set(scorer.choose_calls[0][1]["skill"]["criteria"]) == {"xlsx", "reports", NONE_ID}


def test_tool_shortlist_matches_connector_name():
    tools = [Item("tool", f"mcp__srv{i}__op{i}", "run operation", "run operation", f"srv{i}") for i in range(3)]
    tools.append(Item("tool", "mcp__claude_ai_Gmail__search_threads", "Search threads", "Search threads by query", "Gmail"))
    scorer = FakeScorer()
    Engine(scorer, EngineConfig(k={"skill": 10, "connector": 15, "tool": 1})).scores("anything new in my gmail inbox", tools)
    assert set(scorer.choose_calls[0][1]["tool"]["criteria"]) == {"search_threads", NONE_ID}


def test_equivalent_duplicates_become_one_option():
    pool = [Item("skill", "anthropic-skills:pptx", "Make slide decks", "slide decks"),
            Item("skill", "document-skills:pptx", "Make slide decks", "slide decks"), skill("notes", "take meeting notes")]
    scorer = FakeScorer()
    Engine(scorer).scores("make a slide deck", pool)
    assert set(scorer.choose_calls[0][1]["skill"]["criteria"]) == {"pptx", "notes", NONE_ID}


class ChooseOnly:
    model = "choose-only"

    def choose(self, state, questions):
        return {qid: {"probabilities": {NONE_ID: 1.0}} for qid in questions}


def test_scorer_needs_only_choose():
    assert Engine(ChooseOnly(), K2).scores(PROMPT, SKILLS)["skill"] == [(NONE_ID, 1.0)]


def test_edited_item_text_refreshes_shortlist():
    scorer = FakeScorer()
    engine = Engine(scorer, K2)
    engine.scores("rotate the api keys", SKILLS)
    engine.scores("rotate the api keys", SKILLS[:-1] + [skill("tester", "rotate api keys and secrets")])
    assert "tester" in scorer.choose_calls[1][1]["skill"]["criteria"]


def test_none_winning_empties_kind():
    scorer = FakeScorer({"skill": {NONE_ID: 0.7, "debugging": 0.2}})
    assert Engine(scorer).rank(PROMPT, SKILLS).skills == []


def test_threshold_and_cap():
    scorer = FakeScorer({"skill": {"debugging": 0.5, "tester": 0.36, "slides": 0.1}})
    cfg = EngineConfig(cap={"skill": 1, "connector": 2, "tool": 3})
    ranking = Engine(scorer, cfg).rank(PROMPT, SKILLS)
    assert [(c.id, c.p) for c in ranking.skills] == [("debugging", 0.5)]


def test_option_keys_are_short_and_unique():
    pool = [Item("tool", "mcp__a__search", "a", "a"), Item("tool", "mcp__b__search", "b", "b"),
            Item("skill", "x:none", "n", "n")]
    assert list(option_keys(pool)) == ["search", "search-2", "none-2"]


def test_scores_translate_option_keys_back_to_item_ids():
    items = [Item("tool", "mcp__claude_ai_Gmail__search_threads", "Gmail: search", "gmail search email", "Gmail")]
    scores = Engine(FakeScorer({"tool": {"search_threads": 0.8}})).scores("find the email from Ana", items)
    assert scores["tool"][0] == ("mcp__claude_ai_Gmail__search_threads", 0.8)


def test_empty_kind_pool_omits_question():
    scorer = FakeScorer()
    Engine(scorer).scores(PROMPT, SKILLS)
    assert set(scorer.choose_calls[0][1]) == {"skill"}


def test_no_items_returns_empty_without_model_calls():
    scorer = FakeScorer()
    assert Engine(scorer).scores(PROMPT, []) == {}
    assert not scorer.choose_calls


def test_giant_prompt_is_truncated():
    scorer = FakeScorer()
    Engine(scorer).scores("debug " * 20000, SKILLS)
    assert len(scorer.choose_calls[0][0]["request"]) == 2000


def test_unicode_prompt_passes_through():
    scorer = FakeScorer()
    Engine(scorer).scores("depura o teste que está a falhar, por favor", SKILLS)
    assert scorer.choose_calls[0][0]["request"] == "depura o teste que está a falhar, por favor"


def test_head_budget_overflow_halves_shortlists():
    scorer = FakeScorer(max_options=5)
    engine = Engine(scorer, EngineConfig(k={"skill": 10, "connector": 15, "tool": 10}))
    scores = engine.scores(PROMPT, SKILLS)
    assert len(scorer.choose_calls) == 2 and engine.overflows == 1
    assert len(scorer.choose_calls[1][1]["skill"]["criteria"]) == 5
    assert scores["skill"]


def test_config_from_env():
    cfg = EngineConfig.from_env({"TOOLHINT_K_SKILL": "7", "TOOLHINT_TAU": "0.6"})
    assert cfg.k == {"skill": 7, "connector": 5, "tool": 5}
    assert cfg.tau == {"skill": 0.6, "connector": 0.6, "tool": 0.6}
    assert EngineConfig().tau == {"skill": 0.5, "connector": 0.6, "tool": 0.5}
