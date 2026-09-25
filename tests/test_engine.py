import numpy as np
from fakes import FakeScorer

from laya_router.engine import (
    NONE_ID, EmbeddingCache, Engine, EngineConfig, digest, option_keys, should_skip,
)
from laya_router.items import Item

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
    assert not scorer.embed_calls and not scorer.choose_calls


def test_shortlist_keeps_top_k_by_cosine():
    scorer = FakeScorer()
    Engine(scorer, K2).scores("debug this failing test", SKILLS)
    assert set(scorer.choose_calls[0][1]["skill"]["criteria"]) == {"debugging", "tester", NONE_ID}


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
    assert not scorer.embed_calls


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
    engine = Engine(scorer)
    scores = engine.scores(PROMPT, SKILLS)
    assert len(scorer.choose_calls) == 2 and engine.overflows == 1
    assert len(scorer.choose_calls[1][1]["skill"]["criteria"]) == 5
    assert scores["skill"]


def test_embedding_cache_persists_and_skips_known_texts(tmp_path):
    path = tmp_path / "emb.npz"
    Engine(FakeScorer(), K2, EmbeddingCache(path)).scores(PROMPT, SKILLS)
    second = FakeScorer()
    Engine(second, K2, EmbeddingCache(path)).scores(PROMPT, SKILLS)
    assert path.exists()
    assert second.embed_calls == [[PROMPT]]


def test_corrupt_cache_file_is_ignored(tmp_path):
    path = tmp_path / "emb.npz"
    path.write_bytes(b"not a zip")
    scorer = FakeScorer()
    Engine(scorer, K2, EmbeddingCache(path)).scores(PROMPT, SKILLS)
    assert len(scorer.embed_calls) == 2


def test_mixed_dimension_cache_rebuilds(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.npz")
    cache._vecs[digest(SKILLS[0].text)] = np.zeros(3, dtype=np.float32)
    scores = Engine(FakeScorer(), K2, cache).scores(PROMPT, SKILLS)
    assert scores["skill"]


def test_config_from_env():
    cfg = EngineConfig.from_env({"LAYA_ROUTER_K_SKILL": "5", "LAYA_ROUTER_TAU": "0.5"})
    assert cfg.k == {"skill": 5, "connector": 15, "tool": 10}
    assert cfg.tau == {"skill": 0.5, "connector": 0.5, "tool": 0.5}
