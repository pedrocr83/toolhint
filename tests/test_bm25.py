from laya_router.bm25 import BM25, tokens


def test_tokens_fold_accents_drop_stopwords_and_split_long_words():
    assert tokens("Começaram the tests, v2!") == ["come", "omec", "meca", "ecar", "cara", "aram",
                                                 "test", "ests", "v2"]


def test_content_words_survive_the_stopword_filter():
    assert tokens("write a word document") == ["writ", "rite", "word", "docu", "ocum", "cume", "umen", "ment"]


def test_bm25_matches_across_word_forms():
    scores = BM25(["test failure diagnosis", "slide decks"]).scores("my pytest run keeps failing")
    assert scores[0] > 0 and scores[1] == 0


def test_bm25_prefers_matching_doc():
    scores = BM25(["send email drafts", "debug failing tests", "make slides"]).scores("my tests are failing")
    assert scores.index(max(scores)) == 1


def test_bm25_scores_zero_without_overlap():
    assert BM25(["send email drafts"]).scores("olá mundo") == [0.0]
