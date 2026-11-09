import argparse
import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from kev.api import SystemOneRequest

app = FastAPI()
# one thread loads the model and runs every request, so one model answers one request at a time
WORKER = ThreadPoolExecutor(max_workers=1)


class Kanana:
    def __init__(self, path, device):
        import torch
        from transformers import AutoModel

        self.model = AutoModel.from_pretrained(path, trust_remote_code=True, dtype=torch.bfloat16,
                                               attn_implementation="sdpa").to(device).eval()
        self.dtype = "bf16"
        self.temperature = self.model.config.decision_temperature

    def decide(self, state, questions):
        return self.model.system_one(state=state, questions=questions)["answers"]


class PplxDecider:
    def __init__(self, path, device):
        import torch

        sys.path.insert(0, str(path / "source" / "src"))   # the repository ships its runtime as source
        from pplx_decider import Decider, model

        # Decider loads the backbone in fp32 everywhere but CUDA: 18 GB and swapping on a 32 GB Mac.
        # Load it in bf16 instead, the dtype of the reference path on CUDA.
        backbone = model.Qwen3_5Model
        model.Qwen3_5Model = type("BF16", (), {"from_pretrained": staticmethod(
            lambda path, **kw: backbone.from_pretrained(path, **{**kw, "dtype": torch.bfloat16}))})
        try:
            self.decider = Decider.from_pretrained(path, device=device)
        finally:
            model.Qwen3_5Model = backbone
        self.decider.readout.to(torch.bfloat16)
        self.dtype = "bf16"
        self.temperature = self.decider.temperature

    def decide(self, state, questions):
        # one question per request, the mode the model card recommends; the requests still run as one batch
        out = self.decider.decide([{"state": state, "questions": {qid: q}} for qid, q in questions.items()])
        return {qid: r["answers"][qid] for qid, r in zip(questions, out)}


RUNTIMES = {"kanana": Kanana, "pplx-decider": PplxDecider}


@app.post("/v1/systemone")
async def systemone(req: SystemOneRequest):
    t0 = time.perf_counter()
    questions = {qid: q.model_dump(exclude_none=True) for qid, q in req.questions.items()}
    try:
        answers = await asyncio.get_running_loop().run_in_executor(WORKER, app.state.runtime.decide, req.state, questions)
    except (ValueError, TypeError) as e:   # both runtimes raise ValueError subclasses for inputs they cannot answer
        raise HTTPException(422, str(e))
    return {"model": req.model, "answers": answers, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


@app.get("/v1/models")
def models():
    s = app.state
    return {"models": [{"name": "kev-latest", "description": f"{s.server} on {s.device}", "run": s.run, "base": s.server,
                        "backend": "torch", "dtype": s.runtime.dtype, "device": s.device,
                        "temperature": s.runtime.temperature}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, choices=list(RUNTIMES))
    ap.add_argument("--run", required=True, help="Hugging Face id@revision, or the model folder")
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    import torch
    from huggingface_hub import snapshot_download

    if "@" in a.run:
        repo, rev = a.run.split("@", 1)
        path = Path(snapshot_download(repo, revision=rev))
    else:
        path = Path(a.run)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    app.state.runtime = WORKER.submit(RUNTIMES[a.server], path, device).result()
    app.state.server, app.state.run, app.state.device = a.server, a.run, device
    print(f"serving {a.run} ({path}) via {a.server} on {device} at 127.0.0.1:{a.port}", flush=True)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
