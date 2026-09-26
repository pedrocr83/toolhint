"""Laya adapter: the only module that imports laya (and so torch)."""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("toolhint.scorer")


class LayaScorer:
    """Warm Laya checkpoint answering typed choice questions."""

    def __init__(self, model: str = "typed-decisions", device: str | None = None) -> None:
        from laya import Router

        self.model = model
        self._router = Router(device=device)
        self._router.preload([model])
        self._agent = self._router.load(model)
        self._start_device = self.device
        self._warned = False
        self._lock = threading.Lock()  # one forward pass at a time, as laya.serve does

    @property
    def device(self) -> str:
        return str(self._agent.device)

    def choose(self, state: dict, questions: dict) -> dict:
        with self._lock:
            answers = self._router.predict(state, questions, model=self.model)["answers"]
        if not self._warned and self._start_device != "cpu" and self.device == "cpu":
            # laya 0.3.20 moves to CPU for good after a GPU memory error; say so once
            self._warned = True
            log.warning("Laya fell back from %s to CPU after a GPU memory error; routing stays slower "
                        "until this server restarts", self._start_device)
        return answers
