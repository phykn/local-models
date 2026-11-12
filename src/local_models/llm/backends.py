import httpx


class BackendError(Exception):
    pass


def strip_thinking(text):
    # servers that do not split reasoning out leave it in content; the template may open <think> in the prompt
    return text.rsplit("</think>", 1)[-1].lstrip() if "</think>" in text else text


class OpenAIBackend:
    def __init__(self, spec, timeout=900):
        self.spec = spec
        self.url = f"http://127.0.0.1:{spec.port}"
        self.timeout = timeout

    async def info(self):
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(f"{self.url}/v1/models")
            r.raise_for_status()
            data = r.json()["data"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        # mlx-vlm lists HF cache repos, and the loaded model by its snapshot path with loaded=true
        cache = "models--" + self.spec.repo.replace("/", "--")
        for m in data if isinstance(data, list) else []:
            mid = str(m.get("id", "")) if isinstance(m, dict) else ""
            if cache in mid and m.get("loaded"):
                return {"id": mid}
        return None

    async def chat(self, messages, think=False, max_tokens=2048):
        s = self.spec
        if not (info := await self.info()):
            raise BackendError(self.not_running())
        # mlx-vlm requires the loaded model's id
        body = {"model": info["id"], "messages": messages, "max_tokens": max_tokens, **(s.think if think else s.nothink),
                "enable_thinking": think}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.url}/v1/chat/completions", json=body)
        except httpx.ConnectError:
            raise BackendError(self.not_running())
        except httpx.TimeoutException:
            raise BackendError(f"model {s.name!r} did not answer within {self.timeout}s")
        if r.is_error:
            raise BackendError(f"model {s.name!r} answered HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        choice = d["choices"][0]
        return {"model": s.name, "text": strip_thinking(choice["message"].get("content") or ""),
                "finish_reason": choice.get("finish_reason"), "usage": d.get("usage")}

    def not_running(self):
        return f"model {self.spec.name!r} is not running on {self.url}. Start it with: llmctl start {self.spec.name}"
