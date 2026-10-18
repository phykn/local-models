import os
import time

import httpx


class BackendError(Exception):
    pass


def normalize(raw, min_confidence):
    t = raw["type"]
    if t == "noul":
        p = raw["noul"]
        # a noul has no confidence of its own; |p - 0.5| * 2 is Kev's choice confidence for two options,
        # so one min_confidence means the same for every question type
        out = {"answer": p >= 0.5, "probability_yes": p, "confidence": round(abs(p - 0.5) * 2, 4)}
    elif t == "choice":
        out = {"answer": raw["choice"], "confidence": raw["confidence"], "probabilities": raw["probabilities"]}
    else:
        legend, probs = raw["legend"], raw["probabilities"]
        mode = max(probs, key=probs.get)
        out = {"answer": legend[mode], "score": raw["score"], "confidence": raw["confidence"],
               "probabilities": {legend[k]: v for k, v in probs.items()}}
    return {"type": t, **out, "low_confidence": out["confidence"] < min_confidence}


class KevHttpBackend:
    """A running kev.serve, through its /v1/systemone API."""

    def __init__(self, spec, timeout=300):
        self.spec = spec
        self.url = f"http://127.0.0.1:{spec.port}"
        key = os.environ.get("KEV_API_KEY")   # kev.serve started with it in the environment requires it on every request
        self.headers = {"authorization": f"Bearer {key}"} if key else {}
        self.timeout = timeout

    async def decide(self, state, questions):
        body = {"state": state, "model": "kev-latest", "questions": questions}
        t0 = time.perf_counter()
        if await self.info() is None:   # models can share a port, so the server there may be another model
            raise BackendError(self.not_running())
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.url}/v1/systemone", json=body, headers=self.headers)
        except httpx.ConnectError:
            raise BackendError(self.not_running())
        except httpx.TimeoutException:
            raise BackendError(f"model {self.spec.name!r} did not answer within {self.timeout}s")
        if r.status_code == 422:
            raise BackendError(f"Kev rejected the request: {r.json().get('detail', r.text)}")
        if r.is_error:
            raise BackendError(f"model {self.spec.name!r} answered HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        answers = {qid: normalize(a, self.spec.min_confidence) for qid, a in d["answers"].items()}
        return {"model": self.spec.name, "answers": answers, "latency_ms": d.get("latency_ms"),
                "roundtrip_ms": round((time.perf_counter() - t0) * 1000)}

    async def info(self):
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(f"{self.url}/v1/models", headers=self.headers)
            r.raise_for_status()
            m = r.json()["models"][0]
        except (httpx.HTTPError, ValueError, KeyError, IndexError):   # nothing there, or a server that is not Kev
            return None
        if not self.serves(m.get("run") or ""):
            return None
        return {k: m.get(k) for k in ("run", "base", "backend", "dtype", "temperature", "device")}

    def serves(self, run):
        # kev.serve reports the --run it got: the id as written, or a local checkpoint as an absolute path
        want = self.spec.run
        return want is None or run == want or run.endswith("/" + want.strip("/"))

    def not_running(self):
        return f"model {self.spec.name!r} is not running on {self.url}. Start it with: kevctl start {self.spec.name}"
