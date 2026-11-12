import pytest
from conftest import llm_spec, registry_of
from fastapi import FastAPI, HTTPException
from fastmcp import Client

from local_models.llm import mcp_server
from local_models.llm.client import ChatClient, strip_thinking
from local_models.llm.models import load_registry

RUN = "mlx-community/Qwen3.8-27B-mxfp4@abc"
SNAPSHOT = "/x/weight/hub/models--mlx-community--Qwen3.8-27B-mxfp4/snapshots/abc"


def fake_server(models):
    """An OpenAI-compatible server that answers like mlx-vlm; app.state.last is the last request body."""
    app = FastAPI()
    app.state.last = None

    @app.post("/v1/chat/completions")
    def chat(body: dict):
        app.state.last = body
        if body["messages"][-1]["content"] == "boom":
            raise HTTPException(500, "internal error")
        content = "<think>reasoning</think>\n\n서울입니다." if body.get("enable_thinking") else "서울입니다."
        return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3}}

    @app.get("/v1/models")
    def models_():
        return {"object": "list", "data": models}
    return app


@pytest.fixture(scope="module")
def vlm(serve):
    # mlx-vlm lists HF cache repos (not loaded) and the loaded model by its snapshot path
    app = fake_server([{"id": RUN.split("@")[0], "loaded": False}, {"id": SNAPSHOT, "loaded": True}])
    return serve(app), app


@pytest.fixture
def client(vlm, monkeypatch, tmp_path):
    reg = registry_of(tmp_path / "llm.toml", llm_spec(run=RUN), llm_spec("down", run="x/down@v1"), port=vlm[0])
    monkeypatch.setattr(mcp_server, "reg", reg)
    return Client(mcp_server.mcp)


async def test_ask_sends_the_loaded_model_and_thinking_off(client, vlm):
    async with client as c:
        r = await c.call_tool("ask", {"prompt": "수도는?", "system": "짧게"})
    assert r.data["text"] == "서울입니다." and r.data["model"] == "m" and r.data["finish_reason"] == "stop"
    sent = vlm[1].state.last
    assert sent["model"] == SNAPSHOT and sent["temperature"] == 0.7 and sent["enable_thinking"] is False
    assert sent["messages"] == [{"role": "system", "content": "짧게"}, {"role": "user", "content": "수도는?"}]


async def test_ask_think_strips_reasoning(client, vlm):
    async with client as c:
        r = await c.call_tool("ask", {"prompt": "수도는?", "think": True, "max_tokens": 50})
    assert r.data["text"] == "서울입니다."
    assert vlm[1].state.last["temperature"] == 1.0 and vlm[1].state.last["max_tokens"] == 50


async def test_errors(client):
    async with client as c:
        down = await c.call_tool("ask", {"prompt": "q", "model": "down"}, raise_on_error=False)
        unknown = await c.call_tool("ask", {"prompt": "q", "model": "nope"}, raise_on_error=False)
        boom = await c.call_tool("ask", {"prompt": "boom"}, raise_on_error=False)
    assert down.is_error and "llmctl start down" in down.content[0].text
    assert unknown.is_error and "unknown model 'nope'" in unknown.content[0].text
    assert boom.is_error and "answered HTTP 500" in boom.content[0].text


async def test_list_models(client, vlm):
    async with client as c:
        r = await c.call_tool("list_models", {})
    by = {m["name"]: m for m in r.data["models"]}
    assert by["m"]["running"] and by["m"]["default"] and by["m"]["url"] == f"http://127.0.0.1:{vlm[0]}/v1"
    assert by["down"]["start"] == "llmctl start down"


async def test_port_change_while_running(vlm, monkeypatch, tmp_path):
    path = tmp_path / "llm.toml"
    path.write_text(f'port = 1024\n[models.m]\nrun = "{RUN}"\nmemory_gb = 4\ndescription = ""\nthink = {{}}\nnothink = {{}}\n')
    monkeypatch.setattr(mcp_server, "reg", load_registry(path))
    async with Client(mcp_server.mcp) as c:
        down = await c.call_tool("ask", {"prompt": "q"}, raise_on_error=False)
        path.write_text(path.read_text().replace("port = 1024", f"port = {vlm[0]}"))
        up = await c.call_tool("ask", {"prompt": "q"})
    assert down.is_error and up.data["text"] == "서울입니다."


async def test_another_model_loaded_is_not_running(serve):
    port = serve(fake_server([{"id": "/w/models--mlx-community--Other-7B-4bit/snapshots/1", "loaded": True},
                              {"id": RUN.split("@")[0], "loaded": False}]))
    assert await ChatClient(llm_spec(run=RUN), port).info() is None


def test_strip_thinking():
    assert strip_thinking("<think>a</think>\n\nb") == "b"
    assert strip_thinking("a</think>b") == "b"   # template opened <think> in the prompt
    assert strip_thinking("plain") == "plain"


@pytest.mark.live
async def test_live_korean():
    reg = load_registry()
    ran = 0
    for spec in reg.models.values():
        c = ChatClient(spec, reg.port)
        if not await c.info():
            continue
        out = await c.chat([{"role": "user", "content": "대한민국의 수도는? 도시 이름만 답하세요."}], max_tokens=64)
        print(spec.name, out)
        assert "서울" in out["text"]
        ran += 1
    if not ran:
        pytest.skip("no model running")
