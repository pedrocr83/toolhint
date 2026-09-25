"""Deterministic stand-in for LayaScorer."""
from __future__ import annotations


class FakeScorer:
    model = "fake"

    def __init__(self, answers: dict[str, dict[str, float]] | None = None, max_options: int | None = None) -> None:
        self.answers = answers or {}
        self.max_options = max_options
        self.choose_calls: list[tuple[dict, dict]] = []

    def choose(self, state, questions):
        self.choose_calls.append((state, questions))
        for qid, question in questions.items():
            if self.max_options and len(question["criteria"]) > self.max_options:
                raise ValueError(f"question {qid!r} options exceed head_max_len=192")
        out = {}
        for qid, question in questions.items():
            probs = self._probs(qid, question["criteria"])
            out[qid] = {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs}
        return out

    def _probs(self, qid: str, criteria: dict) -> dict[str, float]:
        preset = {key: p for key, p in self.answers.get(qid, {}).items() if key in criteria}
        rest = [key for key in criteria if key not in preset]
        share = max(0.0, 1.0 - sum(preset.values())) / len(rest) if rest else 0.0
        return {**preset, **dict.fromkeys(rest, share)}
