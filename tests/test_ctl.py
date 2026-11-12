import json
import os
import sys
from types import SimpleNamespace

import pytest
from conftest import decision_spec, registry_of

from local_models import servers
from local_models.decision.ctl import Ctl
from local_models.decision.registry import load_registry


@pytest.fixture
def ctl(tmp_path, monkeypatch):
    monkeypatch.setattr(servers, "LOGS", tmp_path)
    monkeypatch.setattr(Ctl, "info", lambda self, spec: None)
    reg = registry_of(tmp_path / "models.toml", decision_spec("a", port=8011), decision_spec("b", port=8011))
    return Ctl(reg)


def test_start_while_starting_does_not_spawn(ctl, tmp_path, monkeypatch, capsys):
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(servers, "launch", lambda *a, **k: pytest.fail("spawned"))
    ctl.start(SimpleNamespace(name="a", timeout=1))
    assert "still starting" in capsys.readouterr().out
    assert (tmp_path / "a.pid").read_text() == str(os.getpid())


def test_start_on_a_port_another_model_holds(ctl, tmp_path, monkeypatch):
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(servers, "port_in_use", lambda port: port == 8011)
    monkeypatch.setattr(servers, "launch", lambda *a, **k: pytest.fail("spawned"))
    with pytest.raises(SystemExit, match="port 8011 is in use by a; stop it first"):
        ctl.start(SimpleNamespace(name="b", timeout=1))


def test_start_launches_the_command(ctl, monkeypatch, capsys):
    monkeypatch.setattr(servers, "port_in_use", lambda port: False)
    calls = []
    monkeypatch.setattr(servers, "launch", lambda spec, cmd, ready, timeout: calls.append((spec.name, cmd[1:], timeout)))
    ctl.start(SimpleNamespace(name="a", timeout=60))
    assert calls == [("a", ["-m", "local_models.decision.systemone", "--server", "kanana", "--run", "x/a@v1", "--port", "8011"], 60)]
    assert "a ready on http://127.0.0.1:8011" in capsys.readouterr().out


def test_port_while_running(ctl, tmp_path):
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    with pytest.raises(SystemExit, match="stop a"):
        ctl.port(SimpleNamespace(name="a", port=9000))


def test_status_and_list_json(ctl, tmp_path, monkeypatch, capsys):
    (tmp_path / "b.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(Ctl, "info", lambda self, spec: {"run": spec.run} if spec.name == "a" else None)
    ctl.status(SimpleNamespace(json=True))
    assert json.loads(capsys.readouterr().out) == [
        {"name": "a", "state": "external", "url": "http://127.0.0.1:8011"}, {"name": "b", "state": "starting", "url": "http://127.0.0.1:8011"}]
    ctl.list(SimpleNamespace(json=True))
    assert json.loads(capsys.readouterr().out) == [
        {"name": n, "port": 8011, "memory_gb": 0, "default": n == "a", "note": None, "missing": False} for n in "ab"]


def test_list_aligns_long_names(tmp_path, capsys):
    reg = registry_of(tmp_path / "models.toml", decision_spec("a"), decision_spec("a-much-longer-name"))
    Ctl(reg).list(SimpleNamespace(json=False))
    assert len({line.index(":") for line in capsys.readouterr().out.splitlines()}) == 1


def test_unknown_model_is_an_error_not_a_traceback(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["decisionctl", "stop", "nope"])
    monkeypatch.setattr(Ctl, "load_registry", staticmethod(load_registry))
    with pytest.raises(SystemExit, match="unknown model 'nope'; registered: "):
        Ctl.main()
