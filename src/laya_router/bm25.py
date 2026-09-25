"""Okapi BM25: the lexical shortlist in front of Laya and the no-model eval baseline."""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class BM25:
    """Plain Okapi BM25 over short item documents."""

    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = [Counter(tokens(doc)) for doc in docs]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths) if self.lengths else 1.0
        df = Counter(term for doc in self.docs for term in doc)
        self.idf = {term: math.log(1 + (len(self.docs) - f + 0.5) / (f + 0.5)) for term, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        terms = tokens(query)
        return [sum(self._term(doc, length, term) for term in terms) for doc, length in zip(self.docs, self.lengths)]

    def _term(self, doc: Counter, length: int, term: str) -> float:
        freq = doc.get(term, 0)
        if not freq:
            return 0.0
        norm = freq + self.k1 * (1 - self.b + self.b * length / (self.avg or 1.0))
        return self.idf[term] * freq * (self.k1 + 1) / norm
