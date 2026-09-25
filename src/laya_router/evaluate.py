"""Phase 0: compare routing methods on eval rows and write a markdown report."""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .catalog import harness_catalogs
from .dataset import read_jsonl
from .engine import NONE_ID, EmbeddingCache, Engine, EngineConfig, cosine, short_key
from .items import KINDS, Item

TOKEN = re.compile(r"[a-z0-9]+")
TAUS = (0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7)
CACHE_DIR = Path.home() / ".cache" / "laya-router"
RankFn = Callable[[str], dict[str, list[str]]]
Scored = dict[str, dict[str, list[tuple[str, float]]]]
Canon = Mapping[str, Mapping[str, str]]


@dataclass
class Inputs:
    catalogs: dict[str, list[Item]]
    known: dict[str, dict[str, set[str]]]
    canon: dict[str, dict[str, str]]
    test: list[dict]
    dev: list[dict]
    negatives: list[dict]


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class BM25:
    """Plain Okapi BM25 over item texts: the no-model baseline."""

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


def canonical_ids(items: Sequence[Item]) -> dict[str, str]:
    """id -> representative id; items of one kind with the same short key and label are interchangeable."""
    first: dict[tuple[str, str, str], str] = {}
    return {item.id: first.setdefault((item.kind, short_key(item), item.label), item.id) for item in items}


def pools(items: Sequence[Item]) -> dict[str, list[Item]]:
    grouped = {kind: [item for item in items if item.kind == kind] for kind in KINDS}
    return {kind: pool for kind, pool in grouped.items() if pool}


def order(pool: list[Item], scores: Sequence[float]) -> list[str]:
    return [pool[int(i)].id for i in np.argsort(-np.asarray(scores, dtype=np.float64), kind="stable")]


def bm25_method(items: Sequence[Item]) -> RankFn:
    grouped = pools(items)
    indexes = {kind: BM25([item.text for item in pool]) for kind, pool in grouped.items()}
    return lambda prompt: {kind: order(grouped[kind], index.scores(prompt)) for kind, index in indexes.items()}


def cosine_method(engine: Engine, items: Sequence[Item]) -> RankFn:
    grouped = pools(items)
    matrices = {kind: engine.cache.vectors(pool, engine.scorer.embed) for kind, pool in grouped.items()}

    def rank(prompt: str) -> dict[str, list[str]]:
        query = np.asarray(engine.scorer.embed([prompt]), dtype=np.float32)[0]
        return {kind: order(grouped[kind], cosine(query, matrix)) for kind, matrix in matrices.items()}

    return rank


def laya_method(engine: Engine, items: Sequence[Item], store: Scored) -> RankFn:
    def rank(prompt: str) -> dict[str, list[str]]:
        store[prompt] = engine.scores(prompt, items)
        return {kind: [item_id for item_id, _ in ranked] for kind, ranked in store[prompt].items()}

    return rank


def evaluate(rows: list[dict], known: dict[str, dict[str, set[str]]], rankers: dict[str, RankFn],
             canon: Canon | None = None) -> dict:
    """top-1/top-3 per kind (ignoring 'none'), none-first counts and latency percentiles."""
    tally = {kind: Counter() for kind in KINDS}
    latencies: list[float] = []
    for row in rows:
        rank_fn = rankers.get(row["harness"])
        if rank_fn is None:
            continue
        started = time.perf_counter()
        ranked = rank_fn(row["prompt"])
        latencies.append((time.perf_counter() - started) * 1000)
        same = (canon or {}).get(row["harness"], {})
        for kind, gold in row["gold"].items():
            score_row(tally[kind], gold, ranked.get(kind, []), known[row["harness"]].get(kind, set()), same)
    return {"kinds": {kind: summarize(counts) for kind, counts in tally.items()}, **percentiles(latencies)}


def score_row(counts: Counter, gold: str, ranked: list[str], known: set[str], canon: Mapping[str, str]) -> None:
    if gold not in known:
        counts["unknown"] += 1
        return
    target = canon.get(gold, gold)
    ids = [canon.get(item_id, item_id) for item_id in ranked if item_id != NONE_ID]
    counts["n"] += 1
    counts["top1"] += ids[:1] == [target]
    counts["top3"] += target in ids[:3]
    counts["none_first"] += bool(ranked) and ranked[0] == NONE_ID


def summarize(counts: Counter) -> dict:
    n = counts["n"]
    return {"n": n, "top1": round(counts["top1"] / n, 3) if n else 0.0, "top3": round(counts["top3"] / n, 3) if n else 0.0,
            "unknown": counts["unknown"], "none_first": counts["none_first"]}


def percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50_ms": 0.0, "p95_ms": 0.0}
    ordered = sorted(samples)
    return {"p50_ms": round(statistics.median(ordered), 1), "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 1)}


def none_rate(rows: list[dict], rankers: dict[str, RankFn]) -> float:
    """Share of unlabeled turns where every kind ranks 'none' first (the router stays silent)."""
    silent = total = 0
    for row in rows:
        rank_fn = rankers.get(row["harness"])
        if rank_fn is None:
            continue
        ranked = rank_fn(row["prompt"])
        total += 1
        silent += all(ids and ids[0] == NONE_ID for ids in ranked.values())
    return round(silent / total, 3) if total else 0.0


def calibrate(rows: list[dict], kind: str, scored: Scored, taus: Sequence[float] = TAUS,
              canon: Canon | None = None) -> list[dict]:
    """Precision/recall of 'top candidate is gold and p >= tau'; 'none' first means abstain."""
    labeled = [row for row in rows if row["gold"].get(kind) and row["prompt"] in scored]
    table = []
    for tau in taus:
        predicted = correct = 0
        for row in labeled:
            ranked = scored[row["prompt"]].get(kind, [])
            if not ranked or ranked[0][0] == NONE_ID or ranked[0][1] < tau:
                continue
            same = (canon or {}).get(row["harness"], {})
            predicted += 1
            correct += same.get(ranked[0][0], ranked[0][0]) == same.get(row["gold"][kind], row["gold"][kind])
        table.append({"tau": tau, "precision": round(correct / predicted, 3) if predicted else 0.0,
                      "recall": round(correct / len(labeled), 3) if labeled else 0.0})
    return table


def pick_tau(table: list[dict], min_precision: float = 0.75) -> float:
    """Smallest tau reaching min_precision; otherwise the tau with the best F1."""
    for row in table:
        if row["precision"] >= min_precision:
            return row["tau"]

    def f1(row: dict) -> float:
        total = row["precision"] + row["recall"]
        return 2 * row["precision"] * row["recall"] / total if total else 0.0

    return max(table, key=f1)["tau"]


def vram_mb() -> int:
    import torch

    return round(torch.cuda.max_memory_allocated() / 2**20) if torch.cuda.is_available() else 0


def run_model(model: str, device: str, ks: Sequence[int], data: Inputs) -> dict:
    """cosine-only plus shortlist→choice at each K, for one checkpoint."""
    from .scorer import LayaScorer

    scorer = LayaScorer(model=model, device=None if device == "auto" else device)
    cache = EmbeddingCache(CACHE_DIR / f"emb-{model}.npz")
    base = Engine(scorer, EngineConfig(), cache)
    cosine_rankers = {h: cosine_method(base, i) for h, i in data.catalogs.items()}
    out = {f"cosine-{model}": {"test": evaluate(data.test, data.known, cosine_rankers, data.canon)}}
    pt_rows = [row for row in data.dev if row.get("source") == "synthetic-pt"]
    for k in ks:
        engine = Engine(scorer, EngineConfig(k={"skill": k, "connector": 15, "tool": k}), cache)
        store: Scored = {}
        rankers = {h: laya_method(engine, i, store) for h, i in data.catalogs.items()}
        out[f"laya-{model}-k{k}"] = {
            "test": evaluate(data.test, data.known, rankers, data.canon),
            "dev": evaluate(data.dev, data.known, rankers, data.canon),
            "dev_pt": evaluate(pt_rows, data.known, rankers, data.canon),
            "silent_on_unlabeled": none_rate(data.negatives, rankers),
            "calibration": {kind: calibrate(data.dev, kind, store, canon=data.canon) for kind in KINDS},
            "overflows": engine.overflows, "vram_mb": vram_mb()}
    return out


def table_rows(split: str, result: dict) -> list[str]:
    return [f"| {split} | {kind} | {m['n']} | {m['top1']} | {m['top3']} | {m['none_first']} | {m['unknown']} "
            f"| {result['p50_ms']} | {result['p95_ms']} |" for kind, m in result["kinds"].items()]


def extra_lines(sets: dict) -> list[str]:
    lines = [""]
    if "silent_on_unlabeled" in sets:
        lines.append(f"Silent on unlabeled turns: {sets['silent_on_unlabeled']} · head overflows: "
                     f"{sets['overflows']} · VRAM MB: {sets['vram_mb']}")
    for kind, table in sets.get("calibration", {}).items():
        cells = ", ".join(f"τ={row['tau']} P={row['precision']} R={row['recall']}" for row in table)
        lines.append(f"Calibration {kind}: {cells} → pick τ={pick_tau(table)}")
    return lines + [""]


def gate_lines(results: dict, device: str) -> list[str]:
    laya = {name: r for name, r in results.items() if name.startswith("laya-")}
    if not laya:
        return ["## Gate", "", "No Laya results."]
    bm25 = results["bm25"]["test"]["kinds"]["skill"]["top3"]
    name, best = max(laya.items(), key=lambda kv: kv[1]["test"]["kinds"]["skill"]["top3"])
    top3, p95 = best["test"]["kinds"]["skill"]["top3"], best["test"]["p95_ms"]
    latency = "n/a on CPU" if device == "cpu" else ("PASS" if p95 <= 250 else "FAIL")
    return ["## Gate", "", f"Best: {name}",
            f"- top-3 skill recall {top3} >= 0.70: {'PASS' if top3 >= 0.70 else 'FAIL'}",
            f"- beats BM25 ({bm25}) by >= 0.10: {'PASS' if top3 - bm25 >= 0.10 else 'FAIL'}",
            f"- p95 {p95} ms <= 250 on GPU: {latency}",
            "- hook injects context in Claude Code CLI: see spike/FINDINGS.md"]


def render(results: dict, device: str) -> str:
    lines = [f"# Phase 0 routing eval ({device})", ""]
    for method, sets in results.items():
        lines += [f"## {method}", "", "| split | kind | n | top1 | top3 | none_first | unknown | p50 ms | p95 ms |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for split in ("test", "dev", "dev_pt"):
            if split in sets:
                lines += table_rows(split, sets[split])
        lines += extra_lines(sets)
    return "\n".join(lines + gate_lines(results, device))


def load_inputs(args: argparse.Namespace) -> Inputs:
    limit = args.limit or None
    catalogs = harness_catalogs()
    known = {h: {kind: {i.id for i in items if i.kind == kind} for kind in KINDS} for h, items in catalogs.items()}
    canon = {h: canonical_ids(items) for h, items in catalogs.items()}
    data_dir = Path(args.data)
    return Inputs(catalogs, known, canon, list(read_jsonl(data_dir / "transcripts.jsonl"))[:limit],
                  list(read_jsonl(Path(args.synthetic)))[:limit],
                  list(read_jsonl(data_dir / "negatives.jsonl"))[: args.negatives])


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="laya-router eval run")
    parser.add_argument("--data", default="eval/data")
    parser.add_argument("--synthetic", default="eval/synthetic.jsonl")
    parser.add_argument("--out", default="eval/results")
    parser.add_argument("--device", default="auto", help="auto | cuda | cpu")
    parser.add_argument("--models", nargs="+", default=["typed-decisions", "english"])
    parser.add_argument("--ks", nargs="+", type=int, default=[5, 10, 15])
    parser.add_argument("--negatives", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0, help="cap test/dev rows (0 = all), for quick CPU runs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    data = load_inputs(args)
    bm25 = {h: bm25_method(items) for h, items in data.catalogs.items()}
    results = {"bm25": {"test": evaluate(data.test, data.known, bm25, data.canon),
                        "dev": evaluate(data.dev, data.known, bm25, data.canon)}}
    for model in args.models:
        results.update(run_model(model, args.device, args.ks, data))
    report = render(results, args.device)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"report-{args.device}.md").write_text(report, encoding="utf-8")
    (out / f"raw-{args.device}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
