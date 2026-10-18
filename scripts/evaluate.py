import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

from local_models import ROOT
from local_models.kev.backends import KevHttpBackend
from local_models.kev.registry import load_registry

ERROR_BUDGET = 0.05


def probs_and_target(q, ans):
    if q["type"] == "noul":
        p = ans["probability_yes"]
        return [1 - p, p], int(bool(q["label"]))
    if q["type"] == "choice":
        keys = list(q["criteria"])
        return [ans["probabilities"][k] for k in keys], keys.index(q["label"])
    return [ans["probabilities"][lvl] for lvl in q["criteria"]], int(q["label"])


def coverage(rows):
    rows = sorted(rows, key=lambda r: -r["confidence"])
    best, threshold, wrong = 0.0, None, 0
    for i, r in enumerate(rows, 1):
        wrong += not r["correct"]
        if wrong / i <= ERROR_BUDGET:
            best, threshold = i / len(rows), r["confidence"]
    return best, threshold


async def run_model(spec, records):
    backend = KevHttpBackend(spec)
    rows, latencies = [], []
    for i, rec in enumerate(records):
        qs = {qid: {k: v for k, v in q.items() if k != "label"} for qid, q in rec["questions"].items()}
        out = await backend.decide(rec["state"], qs)
        latencies.append(out["latency_ms"])
        for qid, q in rec["questions"].items():
            ans = out["answers"][qid]
            p, y = probs_and_target(q, ans)
            rows.append({"record": i, "question": qid, "type": q["type"], "label": q["label"], "answer": ans["answer"],
                         "confidence": ans["confidence"], "correct": max(range(len(p)), key=p.__getitem__) == y,
                         "brier": sum((pk - (k == y)) ** 2 for k, pk in enumerate(p))})
    return rows, latencies


def summarize(rows, latencies):
    n = len(rows)
    cov, thr = coverage(rows)
    by_type = {}
    for t in sorted({r["type"] for r in rows}):
        sub = [r for r in rows if r["type"] == t]
        by_type[t] = {"n": len(sub), "accuracy": sum(r["correct"] for r in sub) / len(sub)}
    return {"n": n, "accuracy": sum(r["correct"] for r in rows) / n, "brier": sum(r["brier"] for r in rows) / n,
            "latency_ms": sum(latencies) / len(latencies), "coverage_at_5pct": cov, "threshold_at_5pct": thr, "by_type": by_type}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--models", help="comma-separated names from kev.toml (default: every running one)")
    ap.add_argument("--out", default=str(ROOT / "evals" / "results"))
    a = ap.parse_args()
    reg = load_registry()
    records = [json.loads(line) for line in open(a.data, encoding="utf-8") if line.strip()]
    if not records:
        sys.exit(f"{a.data} has no records")
    if a.models:
        specs = [reg.get(n) for n in a.models.split(",")]
    else:
        specs = [s for s in reg.models.values() if await KevHttpBackend(s).info()]
    if not specs:
        sys.exit("no model running; start one with: kevctl start <name>")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    print(f"{'model':<14} {'n':>4} {'acc':>6} {'brier':>6} {'ms':>6} {'cov@5%':>7} {'thr':>5}  by type")
    for spec in specs:
        t0 = time.time()
        rows, lat = await run_model(spec, records)
        s = summarize(rows, lat)
        out = Path(a.out) / f"{date.today()}-{Path(a.data).stem}-{spec.name}.json"
        out.write_text(json.dumps({"model": spec.name, "data": a.data, "seconds": round(time.time() - t0, 1), "summary": s, "rows": rows},
                                  ensure_ascii=False, indent=1))
        types = " ".join(f"{t}={v['accuracy']:.2f}" for t, v in s["by_type"].items())
        thr = f"{s['threshold_at_5pct']:.2f}" if s["threshold_at_5pct"] is not None else "-"
        print(f"{spec.name:<14} {s['n']:>4} {s['accuracy']:>6.3f} {s['brier']:>6.3f} {s['latency_ms']:>6.0f} {s['coverage_at_5pct']:>7.2f} {thr:>5}  {types}")


if __name__ == "__main__":
    asyncio.run(main())
