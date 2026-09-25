from laya_router.bm25 import BM25, tokens


def test_tokens_split_on_non_alphanumerics():
    assert tokens("Send-Email_drafts, v2!") == ["send", "email", "drafts", "v2"]


def test_bm25_prefers_matching_doc():
    scores = BM25(["send email drafts", "debug failing tests", "make slides"]).scores("my tests are failing")
    assert scores.index(max(scores)) == 1


def test_bm25_scores_zero_without_overlap():
    assert BM25(["send email drafts"]).scores("olá mundo") == [0.0]
