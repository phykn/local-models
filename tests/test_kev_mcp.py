import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI
from fastmcp import Client

from local_models.kev import mcp_server
from local_models.kev.backends import BackendError, KevHttpBackend, normalize
from local_models.kev.registry import ModelSpec, Registry, load_registry

CANNED = {
    "choice": {"type": "choice", "choice": "returns", "confidence": 0.21,
               "probabilities": {"returns": 0.47, "shipping": 0.28, "billing": 0.25}},
    "noul": {"type": "noul", "noul": 0.93},
    "score": {"type": "score", "score": 1.44, "confidence": 0.34, "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
              "probabilities": {"0": 0.0, "1": 0.56, "2": 0.44}},
}


def fake_kev():
    app = FastAPI()
    app.state.last = None

    @app.post("/v1/systemone")
    def systemone(body: dict):
        app.state.last = body
        from fastapi import HTTPException
        if body["state"] == "too long":
            raise HTTPException(422, "state has 70,000 tokens; the limit is 65,536")
        if body["state"] == "boom":
            raise HTTPException(500, "internal error")
        return {"model": "kev-latest", "answers": {qid: CANNED[q["type"]] for qid, q in body["questions"].items()}, "latency_ms": 12}

    @app.get("/v1/models")
    def models():
        return {"models": [{"name": "kev-latest", "run": "fake", "backend": "mlx", "dtype": "bfloat16"}]}
    return app


@pytest.fixture(scope="module")
def fake_port():
    app = fake_kev()
    port, srv = serve(app)
    yield port, app
    srv.should_exit = True


@pytest.fixture
def client(fake_port, monkeypatch, tmp_path):
    port, _ = fake_port
    reg = Registry(tmp_path / "models.toml", "fake", {
        "fake": ModelSpec("fake", "kev-http", run="fake", port=port, min_confidence=0.3),
        "down": ModelSpec("down", "kev-http", port=1),
    })
    monkeypatch.setattr(mcp_server, "reg", reg)
    return Client(mcp_server.mcp)


async def test_choose(client, fake_port):
    async with client as c:
        r = await c.call_tool("choose", {"text": "신발이 늦게 왔어요", "question": "어느 팀?", "options": {"returns": "반품", "shipping": None, "billing": None}})
    assert r.data["answer"] == "returns" and r.data["model"] == "fake" and r.data["low_confidence"] is True
    sent = fake_port[1].state.last["questions"]["q"]
    assert sent == {"type": "choice", "instructions": "어느 팀?", "criteria": {"returns": "반품", "shipping": None, "billing": None}}


async def test_yes_no(client, fake_port):
    async with client as c:
        r = await c.call_tool("yes_no", {"text": "t", "question": "급한가?", "yes_means": "오늘 처리 필요"})
    assert r.data["answer"] is True and r.data["probability_yes"] == 0.93 and r.data["confidence"] == 0.86
    assert fake_port[1].state.last["questions"]["q"]["criteria"] == {"true": "오늘 처리 필요"}


async def test_score(client):
    async with client as c:
        r = await c.call_tool("score", {"text": "t", "question": "화난 정도", "levels": ["Calm", "Frustrated", "Very angry"]})
    assert r.data["answer"] == "Frustrated" and r.data["score"] == 1.44
    assert r.data["probabilities"] == {"Calm": 0.0, "Frustrated": 0.56, "Very angry": 0.44}


async def test_decide(client):
    qs = {"team": {"type": "choice", "instructions": "팀", "criteria": {"returns": None, "billing": None}},
          "urgent": {"type": "noul", "instructions": "급함?"}}
    async with client as c:
        r = await c.call_tool("decide", {"text": "t", "questions": qs})
    assert set(r.data["answers"]) == {"team", "urgent"} and r.data["answers"]["urgent"]["low_confidence"] is False


async def test_errors(client):
    async with client as c:
        down = await c.call_tool("yes_no", {"text": "t", "question": "q", "model": "down"}, raise_on_error=False)
        unknown = await c.call_tool("yes_no", {"text": "t", "question": "q", "model": "nope"}, raise_on_error=False)
        long = await c.call_tool("yes_no", {"text": "too long", "question": "q"}, raise_on_error=False)
        boom = await c.call_tool("yes_no", {"text": "boom", "question": "q"}, raise_on_error=False)
    assert down.is_error and "kevctl start down" in down.content[0].text
    assert unknown.is_error and "unknown model 'nope'" in unknown.content[0].text
    assert long.is_error and "65,536" in long.content[0].text
    assert boom.is_error and "answered HTTP 500" in boom.content[0].text


async def test_port_change_while_running(fake_port, monkeypatch, tmp_path):
    path = tmp_path / "models.toml"
    path.write_text('[models.m]\nbackend = "kev-http"\nport = 1\n')
    monkeypatch.setattr(mcp_server, "reg", load_registry(path))
    async with Client(mcp_server.mcp) as c:
        down = await c.call_tool("yes_no", {"text": "t", "question": "q"}, raise_on_error=False)
        path.write_text(path.read_text().replace("port = 1", f"port = {fake_port[0]}"))
        up = await c.call_tool("yes_no", {"text": "t", "question": "q"})
    assert down.is_error and up.data["answer"] is True


def test_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("KEV_API_KEY", "secret")
    assert KevHttpBackend(ModelSpec("m", "kev-http", port=1)).headers == {"authorization": "Bearer secret"}


async def test_list_models(client):
    async with client as c:
        r = await c.call_tool("list_models", {})
    by = {m["name"]: m for m in r.data["models"]}
    assert by["fake"]["running"] and by["fake"]["default"] and by["down"]["start"] == "kevctl start down"


def serve(app):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started: time.sleep(0.05)
    return port, srv


async def test_other_server_on_the_port_is_not_kev():
    app = FastAPI()
    app.get("/v1/models")(lambda: {"object": "list", "data": [{"id": "some-llm"}]})   # an OpenAI-style server
    port, srv = serve(app)
    try:
        assert await KevHttpBackend(ModelSpec("m", "kev-http", port=port)).info() is None
    finally:
        srv.should_exit = True


async def test_another_model_on_a_shared_port(fake_port):
    other = KevHttpBackend(ModelSpec("other", "kev-http", run="jaredpalmer/kev-0.8b@v1.0", port=fake_port[0]))
    assert await other.info() is None
    with pytest.raises(BackendError, match="'other' is not running"):
        await other.decide("t", {"q": {"type": "noul", "instructions": "q"}})
    local = KevHttpBackend(ModelSpec("local", "kev-http", run="checkpoints/fake", port=fake_port[0]))
    assert local.serves("/Users/me/local-models/checkpoints/fake") and not local.serves("/x/other-fake")


def test_normalize_noul_boundary():
    assert normalize({"type": "noul", "noul": 0.5}, 0.5) == {"type": "noul", "answer": True, "probability_yes": 0.5, "confidence": 0.0, "low_confidence": True}


@pytest.mark.live
async def test_live_korean():
    reg = load_registry()
    ran = 0
    for spec in reg.models.values():
        b = KevHttpBackend(spec)
        if not await b.info():
            continue
        out = await b.decide("어제 주문한 신발이 2주 늦게 왔고 사이즈도 틀렸어요. 카드 결제도 두 번 됐네요.", {
            "team": {"type": "choice", "instructions": "어느 팀이 처리해야 하나요?",
                     "criteria": {"반품": "교환, 환불, 잘못 온 상품", "배송": "배송 상태, 지연, 분실", "결제": "청구, 결제 오류"}},
            "urgent": {"type": "noul", "instructions": "사람이 급히 봐야 하나요?"},
            "angry": {"type": "score", "instructions": "고객이 얼마나 화가 났나요?", "criteria": ["차분함", "불만", "매우 화남"]}})
        print(spec.name, out)
        assert out["answers"]["team"]["answer"] in {"반품", "배송", "결제"}
        ran += 1
    if not ran:
        pytest.skip("no model running")
