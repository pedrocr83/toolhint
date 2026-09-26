import logging
import types

from toolhint.scorer import LayaScorer


class FakeAgent:
    device = "cuda:0"


AGENT = FakeAgent()


class FakeRouter:
    def __init__(self, device=None):
        pass

    def preload(self, names):
        return self

    def load(self, name):
        return AGENT

    def predict(self, state, questions, model=None):
        return {"answers": {}}


def test_scorer_reports_the_device_and_warns_once_after_a_cpu_fallback(monkeypatch, caplog):
    monkeypatch.setitem(__import__("sys").modules, "laya", types.SimpleNamespace(Router=FakeRouter))
    monkeypatch.setattr(AGENT, "device", "cuda:0")
    scorer = LayaScorer()
    assert scorer.device == "cuda:0"
    AGENT.device = "cpu"
    with caplog.at_level(logging.WARNING, logger="toolhint.scorer"):
        scorer.choose({}, {})
        scorer.choose({}, {})
    assert scorer.device == "cpu"
    assert [r.levelname for r in caplog.records if "CPU" in r.getMessage()] == ["WARNING"]
