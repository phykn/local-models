"""A /v1/systemone server for Jev-Style decision models on MLX, the same API as kev.serve so KevHttpBackend talks to it.

The model repository ships its own runtime, jev_style_decision_mlx.py (rendering, readout and calibration); this module
only loads it and maps TypeSafe-shaped questions onto it. Usage: python -m local_models.kev.jev_style --run id@rev --port N
"""
import argparse
import asyncio
import importlib.util
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from kev.api import SystemOneRequest, choice_confidence, render, round_prob, score_confidence

app = FastAPI()
# MLX streams belong to the thread that created them, so one thread loads the model and runs every request,
# which also keeps one model to one request at a time
WORKER = ThreadPoolExecutor(max_workers=1)
# what the server needs from the repository besides one precision folder ("*.json" would also match 8bit/*.json)
RUNTIME_FILES = ["jev_style_decision_mlx.py", "readout_config.json", "release_config.json", "manifest.json"]


def load_runtime(path):
    spec = importlib.util.spec_from_file_location("jev_style_decision_mlx", path / "jev_style_decision_mlx.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def question(q):
    """A SystemOneRequest question as the runtime's {"t", "ins", "crit"}."""
    ins = render(q.instructions)
    if q.type == "noul":
        crit = {k: render(v) for k, v in q.criteria.items() if k in ("false", "true")} if q.criteria else None
        return {"t": "noul", "ins": ins, "crit": crit or None}
    if q.type == "choice":
        return {"t": "choice", "ins": ins, "crit": {k: (None if v is None or v == "" else render(v)) for k, v in q.criteria.items()}}
    return {"t": "score", "ins": ins, "crit": [render(x) for x in q.criteria]}


def answer(q, r):
    """The runtime's result as kev.serve's answer for that question type."""
    if q.type == "noul":
        return {"type": "noul", "noul": round_prob(r["probabilities"]["true"])}
    p = list(r["probabilities"].values())
    if q.type == "choice":
        return {"type": "choice", "choice": r["answer"], "confidence": round_prob(choice_confidence(p)),
                "probabilities": {k: round_prob(v) for k, v in r["probabilities"].items()}}
    return {"type": "score", "score": round_prob(sum(i * pi for i, pi in enumerate(p))),
            "legend": {str(i): render(x) for i, x in enumerate(q.criteria)},
            "probabilities": {str(i): round_prob(v) for i, v in enumerate(p)}, "confidence": round_prob(score_confidence(p))}


@app.post("/v1/systemone")
async def systemone(req: SystemOneRequest):
    s = app.state
    t0 = time.perf_counter()
    qs = [question(q) for q in req.questions.values()]
    try:
        results = await asyncio.get_running_loop().run_in_executor(WORKER, s.model.decide_many, req.state, qs)
    except (s.runtime.InputBudgetError, s.runtime.QuestionError) as e:
        raise HTTPException(422, str(e))
    answers = {qid: answer(q, r) for (qid, q), r in zip(req.questions.items(), results)}
    return {"model": req.model, "answers": answers, "usage": {"input_tokens": sum(r["input_tokens"] for r in results)},
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


@app.get("/v1/models")
def models():
    s = app.state
    return {"models": [{"name": "kev-latest", "description": f"{s.runtime.MODEL_NAME} on MLX", "run": s.run,
                        "base": s.runtime.MODEL_NAME, "backend": "mlx", "dtype": s.model.precision, "device": "gpu",
                        "temperature": s.model.temperatures["global"]}]}


def main():
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Hugging Face id@revision of a Jev-Style MLX repository, or its folder")
    ap.add_argument("--precision", default="bf16", choices=("bf16", "8bit"))
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    if "@" in a.run:
        from huggingface_hub import snapshot_download
        repo, rev = a.run.split("@", 1)
        path = Path(snapshot_download(repo, revision=rev, allow_patterns=[*RUNTIME_FILES, f"{a.precision}/*"]))
    else:
        path = Path(a.run)
    app.state.runtime = load_runtime(path)
    app.state.model = WORKER.submit(app.state.runtime.JevStyleDecisionMLX, path, precision=a.precision).result()
    app.state.run = a.run
    print(f"serving {a.run} ({path}) via mlx ({a.precision}) on 127.0.0.1:{a.port}", flush=True)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
