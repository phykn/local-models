import time
from pathlib import Path

import httpx

from .registry import ModelSpec


class BackendError(Exception):
    pass


def strip_thinking(text):
    # servers that do not split reasoning out leave it in content; the template may open <think> in the prompt
    return text.rsplit("</think>", 1)[-1].lstrip() if "</think>" in text else text


class OpenAIBackend:
    """A running mlx-lm or mlx-vlm server, through its OpenAI-compatible API."""

    def __init__(self, spec: ModelSpec, timeout=900):
        self.spec = spec
        self.url = f"http://127.0.0.1:{spec.port}"
        self.timeout = timeout

    async def info(self):
        """The served entry for this model from /v1/models, or None if the port has nothing or another model."""
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(f"{self.url}/v1/models")
            r.raise_for_status()
            data = r.json()["data"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        needles = self.needles()
        for m in data if isinstance(data, list) else []:
            mid = str(m.get("id", "")) if isinstance(m, dict) else ""
            if any(n in mid for n in needles) and m.get("loaded", True):
                return {"id": mid}
        return None

    def needles(self):
        # mlx-vlm lists the loaded model by its snapshot path with loaded=true; mlx-lm lists HF cache repos by id
        s = self.spec
        return [s.repo, "models--" + s.repo.replace("/", "--")] if s.repo else [Path(s.run).name]

    async def chat(self, messages, think=False, max_tokens=2048):
        s = self.spec
        body = {"messages": messages, "max_tokens": max_tokens, **(s.think if think else s.nothink),
                # mlx-lm reads chat_template_kwargs, mlx-vlm reads enable_thinking; each ignores the other
                "chat_template_kwargs": {"enable_thinking": think}, "enable_thinking": think}
        if s.server == "mlx-vlm":
            # mlx-vlm requires the loaded model's id; mlx-lm treats any id as a model to load, so it gets none
            if not (info := await self.info()):
                raise BackendError(self.not_running())
            body["model"] = info["id"]
        t0 = time.perf_counter()
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
                "finish_reason": choice.get("finish_reason"), "usage": d.get("usage"),
                "roundtrip_ms": round((time.perf_counter() - t0) * 1000)}

    def not_running(self):
        return f"model {self.spec.name!r} is not running on {self.url}. Start it with: llmctl start {self.spec.name}"
