import argparse
import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

JSON = str | dict | list | int | float | bool | None


# the request of TypeSafe's System One API; a choice or score has 1 to 255 options
class Noul(BaseModel):
    type: Literal["noul"]
    instructions: JSON = None
    criteria: dict[str, JSON] | None = None


class Choice(BaseModel):
    type: Literal["choice"]
    instructions: JSON = None
    criteria: dict[str, JSON] = Field(min_length=1, max_length=255)


class Score(BaseModel):
    type: Literal["score"]
    instructions: JSON = None
    criteria: list[JSON] = Field(min_length=1, max_length=255)


class SystemOneRequest(BaseModel):
    state: JSON
    questions: dict[str, Noul | Choice | Score] = Field(min_length=1)


class Kanana:
    def __init__(self, path, device):
        import torch
        from transformers import AutoModel

        self.model = AutoModel.from_pretrained(path, trust_remote_code=True, dtype=torch.bfloat16,
                                               attn_implementation="sdpa").to(device).eval()

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

    def decide(self, state, questions):
        # one question per request, the mode the model card recommends; the requests still run as one batch
        out = self.decider.decide([{"state": state, "questions": {qid: q}} for qid, q in questions.items()])
        return {qid: r["answers"][qid] for qid, r in zip(questions, out)}


RUNTIMES = {"kanana": Kanana, "pplx-decider": PplxDecider}

app = FastAPI()
# one thread loads the model and runs every request, so one model answers one request at a time
WORKER = ThreadPoolExecutor(max_workers=1)


@app.post("/v1/systemone")
async def systemone(req: SystemOneRequest):
    t0 = time.perf_counter()
    questions = {qid: q.model_dump(exclude_none=True) for qid, q in req.questions.items()}
    try:
        answers = await asyncio.get_running_loop().run_in_executor(WORKER, app.state.runtime.decide, req.state, questions)
    except (ValueError, TypeError) as e:   # both runtimes raise ValueError subclasses for inputs they cannot answer
        raise HTTPException(422, str(e))
    return {"answers": answers, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


@app.get("/v1/info")
def info():
    return app.state.info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, choices=list(RUNTIMES))
    ap.add_argument("--run", required=True, help="Hugging Face id@revision, reported by /v1/info")
    ap.add_argument("--model", required=True, type=Path, help="the downloaded snapshot of --run")
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    import torch
    import uvicorn

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    app.state.runtime = WORKER.submit(RUNTIMES[a.server], a.model, device).result()
    app.state.info = {"run": a.run, "server": a.server, "device": device}
    print(f"serving {a.run} ({a.model}) via {a.server} on {device} at 127.0.0.1:{a.port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
