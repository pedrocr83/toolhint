"""Rank catalog items for a prompt: BM25 shortlist, then one Laya choice per kind."""
from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import numpy as np

from .bm25 import BM25
from .items import KINDS, Candidate, Item, Ranking

log = logging.getLogger("laya_router.engine")
NONE_ID = "none"
NONE_LABEL = "no specialized skill or tool needed; general request"
MAX_PROMPT_CHARS = 2000
QUESTIONS = {
    "skill": "Which skill should handle this request?",
    "connector": "Which connected app or MCP server does this request need?",
    "tool": "Which tool should be called first for this request?",
}
PLURAL = {"skill": "skills", "connector": "connectors", "tool": "tools"}
DEFAULT_K = {"skill": 10, "connector": 15, "tool": 10}
DEFAULT_TAU = {"skill": 0.35, "connector": 0.35, "tool": 0.35}
DEFAULT_CAP = {"skill": 3, "connector": 2, "tool": 3}
Scores = dict[str, list[tuple[str, float]]]


class Scorer(Protocol):
    model: str

    def choose(self, state: dict, questions: dict) -> dict: ...


@dataclass(frozen=True)
class EngineConfig:
    k: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_K))
    tau: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TAU))
    cap: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CAP))
    min_prompt_chars: int = 12

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> EngineConfig:
        k, tau = dict(DEFAULT_K), dict(DEFAULT_TAU)
        if env.get("LAYA_ROUTER_K_SKILL"):
            k["skill"] = int(env["LAYA_ROUTER_K_SKILL"])
        if env.get("LAYA_ROUTER_K_TOOL"):
            k["tool"] = int(env["LAYA_ROUTER_K_TOOL"])
        if env.get("LAYA_ROUTER_TAU"):
            tau = dict.fromkeys(tau, float(env["LAYA_ROUTER_TAU"]))
        return cls(k=k, tau=tau)


def should_skip(prompt: str, previous: str, min_chars: int) -> bool:
    text = prompt.strip()
    return len(text) < min_chars or text.startswith("/") or text == previous.strip()


def short_key(item: Item) -> str:
    """Compact option key (Laya renders 'key: label' in a small head budget)."""
    return item.id.rsplit("__", 1)[-1].rsplit(":", 1)[-1] or item.id


def doc_text(item: Item) -> str:
    """What BM25 indexes for an item: short name, connector and description."""
    return f"{short_key(item)} {item.connector or ''} {item.text}"


@lru_cache(maxsize=16)
def lexical_index(pool: tuple[Item, ...]) -> BM25:
    """One BM25 index per distinct pool; items are frozen, so an edited description keys a new index."""
    return BM25([doc_text(item) for item in pool])


def option_keys(pool: Sequence[Item]) -> dict[str, Item]:
    """Unique short keys for one question's options; NONE_ID stays reserved."""
    keyed: dict[str, Item] = {}
    for item in pool:
        base = key = short_key(item)
        suffix = 2
        while key in keyed or key == NONE_ID:
            key, suffix = f"{base}-{suffix}", suffix + 1
        keyed[key] = item
    return keyed


def build_questions(keyed: Mapping[str, Mapping[str, Item]]) -> dict:
    return {kind: {"type": "choice", "instructions": QUESTIONS[kind],
                   "criteria": {**{key: item.label for key, item in options.items()}, NONE_ID: NONE_LABEL}}
            for kind, options in keyed.items()}


def translate(answer: Mapping, keyed: Mapping[str, Item]) -> list[tuple[str, float]]:
    """Option-key probabilities -> (item id or NONE_ID, p), best first."""
    probs = answer.get("probabilities", {})
    pairs = [(keyed[key].id if key in keyed else NONE_ID, float(p))
             for key, p in probs.items() if key in keyed or key == NONE_ID]
    return sorted(pairs, key=lambda pair: -pair[1])


class Engine:
    """Stateless apart from the last prompt (for repeat-skipping)."""

    def __init__(self, scorer: Scorer, cfg: EngineConfig | None = None) -> None:
        self.scorer = scorer
        self.cfg = cfg or EngineConfig()
        self.overflows = 0
        self._previous = ""

    def rank(self, prompt: str, items: Sequence[Item]) -> Ranking:
        """Thresholded, capped candidates; empty when skipped or nothing clears tau."""
        started = time.perf_counter()
        ranking = Ranking(model=self.scorer.model)
        if should_skip(prompt, self._previous, self.cfg.min_prompt_chars):
            return ranking
        self._previous = prompt
        for kind, scored in self.scores(prompt, items).items():
            by_id = {item.id: item for item in items if item.kind == kind}
            setattr(ranking, PLURAL[kind], self._select(kind, scored, by_id))
        ranking.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return ranking

    def scores(self, prompt: str, items: Sequence[Item]) -> Scores:
        """Per kind: (item id or NONE_ID, probability), best first. No thresholds, no skipping."""
        text = prompt.strip()[:MAX_PROMPT_CHARS]
        pools = {kind: [item for item in items if item.kind == kind] for kind in KINDS}
        pools = {kind: pool for kind, pool in pools.items() if pool}
        if not pools:
            return {}
        keyed = {kind: option_keys(self._shortlist(text, pool, self.cfg.k[kind])) for kind, pool in pools.items()}
        answers, keyed = self._choose(text, keyed)
        return {kind: translate(answers[kind], keyed[kind]) for kind in keyed if kind in answers}

    def _shortlist(self, text: str, pool: list[Item], k: int) -> list[Item]:
        if len(pool) <= k:
            return pool
        scores = np.asarray(lexical_index(tuple(pool)).scores(text))
        return [pool[int(i)] for i in np.argsort(-scores, kind="stable")[:k]]

    def _choose(self, text: str, keyed: dict[str, dict[str, Item]]) -> tuple[dict, dict[str, dict[str, Item]]]:
        """One predict call; halve option lists while they overflow Laya's head budget."""
        for _ in range(3):
            try:
                return self.scorer.choose({"request": text}, build_questions(keyed)), keyed
            except ValueError as exc:
                if "head_max_len" not in str(exc):
                    raise
                self.overflows += 1
                log.info("choice options exceed head budget; halving shortlists")
                keyed = {kind: dict(list(opts.items())[: max(1, len(opts) // 2)]) for kind, opts in keyed.items()}
        return {}, keyed

    def _select(self, kind: str, scored: list[tuple[str, float]], by_id: Mapping[str, Item]) -> list[Candidate]:
        if not scored or scored[0][0] == NONE_ID:
            return []
        keep = [(item_id, p) for item_id, p in scored if item_id in by_id and p >= self.cfg.tau[kind]]
        return [Candidate(item_id, by_id[item_id].label, round(p, 2), by_id[item_id].connector)
                for item_id, p in keep[: self.cfg.cap[kind]]]


PREFIX = "[laya-router] advisory, ignore if irrelevant — "
MAX_HINT_CHARS = 400


def format_hint(ranking: Ranking, max_chars: int = MAX_HINT_CHARS) -> str:
    """One advisory line; tools are grouped under their connector when it was also picked."""
    if ranking.is_empty():
        return ""
    parts = []
    if ranking.skills:
        parts.append("skills: " + ", ".join(f"{c.id} ({c.p:.2f})" for c in ranking.skills))
    grouped: dict[str, list[Candidate]] = {c.id: [] for c in ranking.connectors}
    loose = []
    for tool in ranking.tools:
        (grouped[tool.connector] if tool.connector in grouped else loose).append(tool)
    if ranking.connectors:
        parts.append("connectors: " + ", ".join(_connector_text(c, grouped[c.id]) for c in ranking.connectors))
    if loose:
        parts.append("tools: " + ", ".join(f"{t.id} ({t.p:.2f})" for t in loose))
    line = PREFIX + " · ".join(parts)
    return line if len(line) <= max_chars else line[: max_chars - 1] + "…"


def _connector_text(connector: Candidate, tools: list[Candidate]) -> str:
    base = f"{connector.id} ({connector.p:.2f})"
    return base + (" → " + ", ".join(tool.id for tool in tools) if tools else "")
