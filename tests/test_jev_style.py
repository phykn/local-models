from kev.api import SystemOneRequest

from local_models.kev.jev_style import answer, question


def req(**qs):
    return SystemOneRequest(model="kev-latest", state="s", questions=qs)


def test_questions_map_onto_the_runtime():
    r = req(n={"type": "noul", "instructions": "refund?"},
            c={"type": "choice", "instructions": "team?", "criteria": {"a": "billing", "b": None}},
            s={"type": "score", "instructions": "urgency?", "criteria": ["low", "high"]})
    n, c, s = (question(q) for q in r.questions.values())
    assert n == {"t": "noul", "ins": "refund?", "crit": None}
    assert c == {"t": "choice", "ins": "team?", "crit": {"a": "billing", "b": None}}
    assert s == {"t": "score", "ins": "urgency?", "crit": ["low", "high"]}


def test_answers_map_onto_kev_serve():
    r = req(n={"type": "noul", "instructions": "x"},
            c={"type": "choice", "instructions": "x", "criteria": {"a": "", "b": ""}},
            s={"type": "score", "instructions": "x", "criteria": ["low", "high"]})
    n, c, s = r.questions.values()
    assert answer(n, {"probabilities": {"false": 0.2, "true": 0.8}})["noul"] == 0.8
    a = answer(c, {"answer": "b", "probabilities": {"a": 0.25, "b": 0.75}})
    assert (a["choice"], a["confidence"]) == ("b", 0.5)
    a = answer(s, {"probabilities": {"low": 0.25, "high": 0.75}})
    assert a["score"] == 0.75 and a["legend"] == {"0": "low", "1": "high"}
