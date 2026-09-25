"""Laya adapter: the only module that imports laya (and so torch)."""
from __future__ import annotations

import threading
from collections.abc import Sequence

import numpy as np


class LayaScorer:
    """Warm Laya checkpoint: encoder embeddings for shortlisting plus typed choice answers."""

    def __init__(self, model: str = "typed-decisions", device: str | None = None) -> None:
        from laya import Router
        from laya.shortlist import embed_fn_from_agent

        self.model = model
        self._router = Router(device=device)
        self._router.preload([model])
        self._embed = embed_fn_from_agent(self._router.load(model))
        self._lock = threading.Lock()  # one forward pass at a time, as laya.serve does

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        with self._lock:
            return self._embed(list(texts))

    def choose(self, state: dict, questions: dict) -> dict:
        with self._lock:
            return self._router.predict(state, questions, model=self.model)["answers"]
