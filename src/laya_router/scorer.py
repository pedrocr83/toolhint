"""Laya adapter: the only module that imports laya (and so torch)."""
from __future__ import annotations

import threading


class LayaScorer:
    """Warm Laya checkpoint answering typed choice questions."""

    def __init__(self, model: str = "typed-decisions", device: str | None = None) -> None:
        from laya import Router

        self.model = model
        self._router = Router(device=device)
        self._router.preload([model])
        self._lock = threading.Lock()  # one forward pass at a time, as laya.serve does

    def choose(self, state: dict, questions: dict) -> dict:
        with self._lock:
            return self._router.predict(state, questions, model=self.model)["answers"]
