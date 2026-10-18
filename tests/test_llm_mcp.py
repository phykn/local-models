import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, HTTPException
from fastmcp import Client

from local_models.llm import mcp_server
from local_models.llm.backends import OpenAIBackend, strip_thinking
from local_models.llm.registry import ModelSpec, Registry, load_registry

REPO = "mlx-community/Qwen3.8-27B-mxfp4"
SNAPSHOT = "/x/weight/hub/models--mlx-community--Qwen3.8-27B-mxfp4/snapshots/abc"


def fake_server(models):
    """An OpenAI-compatible server that answers like mlx-vlm or mlx-lm; app.state.last is the last request body."""
    app = FastAPI()
    app.state.last = None

    @app.post("/v1/chat/completions")
    def chat(body: dict):
        app.state.last = body
        prompt = body["messages"][-1]["content"]
        if prompt == "boom":
            raise HTTPException(500, "internal error")
        content = "<think>reasoning</think>\n\n서울입니다." if body.get("enable_thinking") else "서울입니다."
        return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3}}

    @app.get("/v1/models")
    def list_():
        return {"object": "list", "data": models}
    return app


def serve(app):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started: time.sleep(0.05)
    return port, srv


def spec(server, port, name="m"):
    return ModelSpec(name, server, f"{REPO}@abc", port, nothink={"temperature": 0.7}, think={"temperature": 1.0})


@pytest.fixture(scope="module")
def vlm():
    # mlx-vlm lists HF cache repos (not loaded) and the loaded model by its snapshot path
    app = fake_server([{"id": REPO, "loaded": False}, {"id": SNAPSHOT, "loaded": True}])
    port, srv = serve(app)
    yield port, app
    srv.should_exit = True


@pytest.fixture(scope="module")
def lm():
    app = fake_server([{"id": REPO, "object": "model"}])   # mlx-lm: cache repos only, no loaded flag
    port, srv = serve(app)
    yield port, app
    srv.should_exit = True


@pytest.fixture
def client(vlm, monkeypatch, tmp_path):
    reg = Registry(tmp_path / "models.toml", "m", {"m": spec("mlx-vlm", vlm[0]), "down": spec("mlx-vlm", 1, "down")})
    monkeypatch.setattr(mcp_server, "reg", reg)
    return Client(mcp_server.mcp)


async def test_ask_vlm_sends_loaded_model_and_thinking_off(client, vlm):
    async with client as c:
        r = await c.call_tool("ask", {"prompt": "수도는?", "system": "짧게"})
    assert r.data["text"] == "서울입니다." and r.data["model"] == "m" and r.data["finish_reason"] == "stop"
    sent = vlm[1].state.last
    assert sent["model"] == SNAPSHOT and sent["temperature"] == 0.7
    assert sent["enable_thinking"] is False and sent["chat_template_kwargs"] == {"enable_thinking": False}
    assert sent["messages"] == [{"role": "system", "content": "짧게"}, {"role": "user", "content": "수도는?"}]


async def test_ask_think_strips_reasoning(client, vlm):
    async with client as c:
        r = await c.call_tool("ask", {"prompt": "수도는?", "think": True, "max_tokens": 50})
    assert r.data["text"] == "서울입니다."
    assert vlm[1].state.last["temperature"] == 1.0 and vlm[1].state.last["max_tokens"] == 50


async def test_lm_request_has_no_model(lm):
    # mlx-lm would load any model id it is given as a second model
    out = await OpenAIBackend(spec("mlx-lm", lm[0])).chat([{"role": "user", "content": "q"}])
    assert out["text"] == "서울입니다." and "model" not in lm[1].state.last


async def test_errors(client):
    async with client as c:
        down = await c.call_tool("ask", {"prompt": "q", "model": "down"}, raise_on_error=False)
        unknown = await c.call_tool("ask", {"prompt": "q", "model": "nope"}, raise_on_error=False)
        boom = await c.call_tool("ask", {"prompt": "boom"}, raise_on_error=False)
    assert down.is_error and "llmctl start down" in down.content[0].text
    assert unknown.is_error and "unknown model 'nope'" in unknown.content[0].text
    assert boom.is_error and "answered HTTP 500" in boom.content[0].text


async def test_port_change_while_running(vlm, monkeypatch, tmp_path):
    path = tmp_path / "models.toml"
    path.write_text(f'[models.m]\nserver = "mlx-vlm"\nrun = "{REPO}@abc"\nport = 1\n')
    monkeypatch.setattr(mcp_server, "reg", load_registry(path))
    async with Client(mcp_server.mcp) as c:
        down = await c.call_tool("ask", {"prompt": "q"}, raise_on_error=False)
        path.write_text(path.read_text().replace("port = 1", f"port = {vlm[0]}"))
        up = await c.call_tool("ask", {"prompt": "q"})
    assert down.is_error and up.data["text"] == "서울입니다."


async def test_list_models(client):
    async with client as c:
        r = await c.call_tool("list_models", {})
    by = {m["name"]: m for m in r.data["models"]}
    assert by["m"]["running"] and by["m"]["default"] and by["down"]["start"] == "llmctl start down"


async def test_other_model_on_the_port_is_not_running():
    port, srv = serve(fake_server([{"id": "mlx-community/Other-7B-4bit", "loaded": True}, {"id": REPO, "loaded": False}]))
    try:
        assert await OpenAIBackend(spec("mlx-vlm", port)).info() is None
    finally:
        srv.should_exit = True


async def test_lm_info_matches_cache_repo(lm):
    assert await OpenAIBackend(spec("mlx-lm", lm[0])).info() == {"id": REPO}


def test_strip_thinking():
    assert strip_thinking("<think>a</think>\n\nb") == "b"
    assert strip_thinking("a</think>b") == "b"   # template opened <think> in the prompt
    assert strip_thinking("plain") == "plain"


@pytest.mark.live
async def test_live_korean():
    reg = load_registry()
    ran = 0
    for s in reg.models.values():
        b = OpenAIBackend(s)
        if not await b.info():
            continue
        out = await b.chat([{"role": "user", "content": "대한민국의 수도는? 도시 이름만 답하세요."}], max_tokens=64)
        print(s.name, out)
        assert "서울" in out["text"]
        ran += 1
    if not ran:
        pytest.skip("no model running")
