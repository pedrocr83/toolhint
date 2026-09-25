"""Okapi BM25: the lexical shortlist in front of Laya and the no-model eval baseline."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

TOKEN = re.compile(r"[a-z0-9]+")
GRAM = 4
# English and Portuguese function words plus chat filler: on real prompts they outvote the content words.
STOPWORDS = frozenset("""  # noqa: SIM905 - one readable word block beats a 200-item literal
a about above after again against all also am an and any are as at be because been before being below between both
but by can cant could did do does doing dont down during each few for from further get go going got had has have
having he help her here hers herself him himself his how i if im in into is it its itself ive just let lets like make
me more most my myself need no nor not now of off ok okay on once one only or other our ours ourselves out over own
please same she should so some such than that thats the their theirs them themselves then there these they this those
through to too under until up use used using very want was we were what whats when where which while who whom why will
with would you your yours yourself yourselves
ao aos as aquilo com da das de do dos e em essa esse esta estas este estes faz fazer foi isso isto lhe mas me meu meus
minha minhas na nas no nos o os ou para pela pelas pelo pelos pode podes por que quero se sem ser sim te ter teu tua um
uma umas uns vos
""".split())


def fold(text: str) -> str:
    """Lowercase ASCII: accents dropped, so Portuguese words tokenize whole."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def tokens(text: str) -> list[str]:
    """Content words; words longer than GRAM become overlapping GRAM-grams, so 'failing' meets 'failure'."""
    out: list[str] = []
    for word in TOKEN.findall(fold(text)):
        if word in STOPWORDS:
            continue
        out += [word] if len(word) <= GRAM else [word[i:i + GRAM] for i in range(len(word) - GRAM + 1)]
    return out


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
