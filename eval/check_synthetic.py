"""Validate eval/synthetic.jsonl against the live catalog (Phase 0 helper)."""
import collections
import json
import sys
from pathlib import Path

from toolhint.catalog import harness_catalogs

rows = [json.loads(line) for line in Path("eval/synthetic.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
catalogs = harness_catalogs()
known = {h: {(i.kind, i.id) for i in items} for h, items in catalogs.items()}
unknown = [r for r in rows for kind, value in r["gold"].items() if (kind, value) not in known.get(r["harness"], set())]
counts = collections.Counter((r["harness"], kind, value) for r in rows for kind, value in r["gold"].items() if kind != "tool")
needed = {("claude-code", i.kind, i.id) for i in catalogs["claude-code"] if i.kind != "tool"}
thin = sorted(key for key in needed if counts[key] < 2)
portuguese = sum(1 for r in rows if r["source"] == "synthetic-pt")
print(f"rows={len(rows)} unknown_gold={len(unknown)} under_2={len(thin)} portuguese={portuguese}")
for row in unknown[:10]:
    print("unknown:", row["gold"])
for key in thin[:10]:
    print("thin:", key)
sys.exit(1 if unknown or thin or portuguese < 10 else 0)
