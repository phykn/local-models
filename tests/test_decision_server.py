import pytest
from conftest import decision_spec

from local_models.decision import server
from local_models.decision.client import ClientError, SystemOneClient


class FakeRuntime:
    def decide(self, state, questions):
        if state == "too long":
            raise ValueError("input has 30,000 tokens; the limit is 20,480")
        self.last = questions
        return {qid: {"type": "noul", "noul": 0.9} for qid in questions}


@pytest.fixture(scope="module")
def port(serve):
    server.app.state.runtime = FakeRuntime()
    server.app.state.info = {"run": "x/m@v1", "server": "kanana", "device": "mps"}
    return serve(server.app)


async def test_client_talks_to_the_server(port):
    c = SystemOneClient(decision_spec(), port)
    assert await c.info() == {"run": "x/m@v1", "server": "kanana", "device": "mps"}
    out = await c.decide("환불해 주세요", {"q": {"type": "noul", "instructions": "환불 요청인가?"}})
    assert out["answers"]["q"]["answer"] is True and out["latency_ms"] >= 0
    # questions reach the runtime as plain dicts without the fields the caller left out
    assert server.app.state.runtime.last == {"q": {"type": "noul", "instructions": "환불 요청인가?"}}


async def test_bad_requests_are_rejected(port):
    c = SystemOneClient(decision_spec(), port)
    with pytest.raises(ClientError, match="the limit is 20,480"):   # the runtime's ValueError
        await c.decide("too long", {"q": {"type": "noul"}})
    with pytest.raises(ClientError, match="rejected the request"):   # a choice needs at least one option
        await c.decide("x", {"q": {"type": "choice", "criteria": {}}})


async def test_another_model_on_the_port_is_not_running(port):
    with pytest.raises(ClientError, match="'other' is not running"):
        await SystemOneClient(decision_spec("other"), port).decide("x", {"q": {"type": "noul"}})


def test_pplx_asks_one_question_per_request():
    class Decider:
        def decide(self, requests):
            self.requests = requests
            return [{"answers": {qid: {"type": "noul", "noul": 0.5}}} for r in requests for qid in r["questions"]]

    rt = object.__new__(server.PplxDecider)
    rt.decider = Decider()
    out = rt.decide("s", {"a": {"type": "noul"}, "b": {"type": "noul"}})
    assert [r["questions"] for r in rt.decider.requests] == [{"a": {"type": "noul"}}, {"b": {"type": "noul"}}]
    assert set(out) == {"a", "b"}
