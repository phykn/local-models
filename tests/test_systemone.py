import pytest

from local_models.decision import systemone
from local_models.decision.backends import BackendError, KevHttpBackend
from conftest import decision_spec


class FakeRuntime:
    dtype, temperature = "bf16", 1.5

    def decide(self, state, questions):
        if state == "too long":
            raise ValueError("input has 30,000 tokens; the limit is 20,480")
        self.last = questions
        return {qid: {"type": "noul", "noul": 0.9} for qid in questions}


@pytest.fixture(scope="module")
def port(serve):
    systemone.app.state.runtime = FakeRuntime()
    systemone.app.state.server, systemone.app.state.run, systemone.app.state.device = "kanana", "x/y@abc", "mps"
    return serve(systemone.app)


async def test_backend_talks_to_the_systemone_server(port):
    b = KevHttpBackend(decision_spec(run="x/y@abc", port=port, server="kanana"))
    assert (await b.info())["dtype"] == "bf16"
    out = await b.decide("환불해 주세요", {"q": {"type": "noul", "instructions": "환불 요청인가?"}})
    assert out["answers"]["q"]["answer"] is True
    # questions reach the runtime as plain dicts without the fields the caller left out
    assert systemone.app.state.runtime.last == {"q": {"type": "noul", "instructions": "환불 요청인가?"}}


async def test_runtime_value_error_is_a_422(port):
    b = KevHttpBackend(decision_spec(run="x/y@abc", port=port, server="kanana"))
    with pytest.raises(BackendError, match="the limit is 20,480"):
        await b.decide("too long", {"q": {"type": "noul"}})


async def test_another_model_on_the_port_is_not_running(port):
    b = KevHttpBackend(decision_spec("other", run="x/z@abc", port=port, server="kanana"))
    with pytest.raises(BackendError, match="not running"):
        await b.decide("x", {"q": {"type": "noul"}})


def test_pplx_asks_one_question_per_request():
    class Decider:
        def decide(self, requests):
            self.requests = requests
            return [{"answers": {qid: {"type": "noul", "noul": 0.5}}} for r in requests for qid in r["questions"]]

    rt = object.__new__(systemone.PplxDecider)
    rt.decider = Decider()
    out = rt.decide("s", {"a": {"type": "noul"}, "b": {"type": "noul"}})
    assert [r["questions"] for r in rt.decider.requests] == [{"a": {"type": "noul"}}, {"b": {"type": "noul"}}]
    assert set(out) == {"a", "b"}
