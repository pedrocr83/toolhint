"""Throwaway: measure Laya load/latency/VRAM and the choice head budget on this machine."""
import json
import statistics
import sys
import time
from pathlib import Path

import torch
from laya import Router
from laya.shortlist import embed_fn_from_agent

MODEL = "typed-decisions"
STATE = {"request": "my pytest suite fails with a KeyError after the refactor, help me find why"}
LABEL = "Use when encountering any bug, test failure or unexpected behavior"


def timed(fn, runs: int) -> dict:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {"p50_ms": round(statistics.median(samples), 1), "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 1)}


def questions(n: int) -> dict:
    criteria = {**{f"skill-name-{i}": LABEL for i in range(n)}, "none": "no specialized skill or tool needed"}
    return {kind: {"type": "choice", "instructions": f"Which {kind} fits?", "criteria": criteria}
            for kind in ("skill", "connector", "tool")}


def head_budget(router: Router) -> dict:
    out = {}
    for n in (5, 10, 15, 20):
        for head in (None, 256, 384):
            try:
                router.predict(STATE, {"skill": questions(n)["skill"]}, model=MODEL, head_max_len=head)
                out[f"n{n}_head{head}"] = "ok"
            except ValueError as exc:
                out[f"n{n}_head{head}"] = f"ValueError: {exc}"
    return out


def probe(device: str) -> dict:
    start = time.perf_counter()
    router = Router(device=None if device == "auto" else device)
    router.preload([MODEL])
    agent = router.load(MODEL)
    load_s = round(time.perf_counter() - start, 2)
    embed = embed_fn_from_agent(agent)
    result = {"device": device, "actual_device": str(agent.device), "load_s": load_s,
              "embed_1": timed(lambda: embed([STATE["request"]]), 20),
              "embed_100": timed(lambda: embed([f"item text {i} about things" for i in range(100)]), 3),
              "predict_3q_k5": timed(lambda: router.predict(STATE, questions(5), model=MODEL), 20),
              "head_budget": head_budget(router)}
    if torch.cuda.is_available():
        result["vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
    return result


if __name__ == "__main__":
    report = [probe(device) for device in (sys.argv[1:] or ["auto", "cpu"])]
    Path("spike/results").mkdir(parents=True, exist_ok=True)
    Path("spike/results/laya_probe.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
