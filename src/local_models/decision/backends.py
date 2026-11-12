import httpx


class BackendError(Exception):
    pass


def normalize(raw):
    t = raw["type"]
    if t == "noul":
        p = raw["noul"]
        # a noul has no confidence of its own; |p - 0.5| * 2 is the choice confidence for two options,
        # so one threshold means the same for every question type
        out = {"answer": p >= 0.5, "probability_yes": p, "confidence": round(abs(p - 0.5) * 2, 4)}
    elif t == "choice":
        out = {"answer": raw["choice"], "confidence": raw["confidence"], "probabilities": raw["probabilities"]}
    else:
        legend, probs = raw["legend"], raw["probabilities"]
        mode = max(probs, key=probs.get)
        out = {"answer": legend[mode], "score": raw["score"], "confidence": raw["confidence"],
               "probabilities": {legend[k]: v for k, v in probs.items()}}
    return {"type": t, **out, "low_confidence": out["confidence"] < 0.5}


class SystemOneBackend:
    def __init__(self, spec, timeout=300):
        self.spec = spec
        self.url = f"http://127.0.0.1:{spec.port}"
        self.timeout = timeout

    async def decide(self, state, questions):
        body = {"state": state, "model": "kev-latest", "questions": questions}
        if await self.info() is None:
            raise BackendError(self.not_running())
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.url}/v1/systemone", json=body)
        except httpx.ConnectError:
            raise BackendError(self.not_running())
        except httpx.TimeoutException:
            raise BackendError(f"model {self.spec.name!r} did not answer within {self.timeout}s")
        if r.status_code == 422:
            raise BackendError(f"model {self.spec.name!r} rejected the request: {r.json().get('detail', r.text)}")
        if r.is_error:
            raise BackendError(f"model {self.spec.name!r} answered HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        answers = {qid: normalize(a) for qid, a in d["answers"].items()}
        return {"model": self.spec.name, "answers": answers, "latency_ms": d.get("latency_ms")}

    async def info(self):
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(f"{self.url}/v1/models")
            r.raise_for_status()
            m = r.json()["models"][0]
        except (httpx.HTTPError, ValueError, KeyError, IndexError):   # nothing there, or another kind of server
            return None
        if m.get("run") != self.spec.run:   # models can share a port, so the server there may be another model
            return None
        return {k: m.get(k) for k in ("run", "base", "backend", "dtype", "temperature", "device")}

    def not_running(self):
        return f"model {self.spec.name!r} is not running on {self.url}. Start it with: decisionctl start {self.spec.name}"
