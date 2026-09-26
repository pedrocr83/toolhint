import pytest

from toolhint.engine import NONE_ID, Engine
from toolhint.items import Item

pytestmark = pytest.mark.slow

ITEMS = [
    Item("skill", "superpowers:systematic-debugging", "Use when encountering any bug or test failure",
         "Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes"),
    Item("skill", "anthropic-skills:pptx", "Create or edit PowerPoint slide decks",
         "Use this skill any time a .pptx file is involved: decks, slides, presentations"),
    Item("skill", "anthropic-skills:xlsx", "Work with spreadsheet files",
         "Use this skill any time a spreadsheet file is the primary input or output"),
]


def test_laya_scorer_returns_a_distribution_over_options():
    from toolhint.scorer import LayaScorer

    scores = Engine(LayaScorer()).scores("my pytest suite fails with a KeyError after the refactor", ITEMS)
    assert {item_id for item_id, _ in scores["skill"]} == {i.id for i in ITEMS} | {NONE_ID}
    assert abs(sum(p for _, p in scores["skill"]) - 1.0) < 0.02
