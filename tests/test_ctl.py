import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import decision_spec, llm_spec, registry_of

from local_models import servers, weights
from local_models.decision.ctl import Ctl
from local_models.decision.models import load_registry
from local_models.llm.ctl import Ctl as LlmCtl


@pytest.fixture
def ctl(tmp_path, monkeypatch):
    monkeypatch.setattr(servers, "LOGS", tmp_path)
    monkeypatch.setattr(servers, "launch", lambda *a, **k: pytest.fail("spawned"))
    monkeypatch.setattr(Ctl, "info", lambda self, spec: None)
    monkeypatch.setattr(weights, "find", lambda run: Path("/w") if run == "x/a@v1" else None)
    toml = tmp_path / "decision.toml"
    toml.write_text("port = 8011\n")
    return Ctl(registry_of(toml, decision_spec("a"), decision_spec("b", server="pplx-decider")))


def test_start_while_starting_does_not_spawn(ctl, tmp_path, capsys):
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    ctl.start(SimpleNamespace(name="a", timeout=1))
    assert "still starting" in capsys.readouterr().out
    assert (tmp_path / "a.pid").read_text() == str(os.getpid())


def test_start_on_a_port_another_model_holds(ctl, tmp_path, monkeypatch):
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(servers, "port_in_use", lambda port: port == 8011)
    with pytest.raises(SystemExit, match="port 8011 is in use by a; stop it first"):
        ctl.start(SimpleNamespace(name="b", timeout=1))


def test_start_without_weights_says_pull(ctl, monkeypatch):
    monkeypatch.setattr(servers, "port_in_use", lambda port: False)
    with pytest.raises(SystemExit, match="b is not downloaded; run: decisionctl pull b"):
        ctl.start(SimpleNamespace(name="b", timeout=1))


def test_start_launches_the_server(ctl, monkeypatch, capsys):
    monkeypatch.setattr(servers, "port_in_use", lambda port: False)
    calls = []
    monkeypatch.setattr(servers, "launch", lambda spec, cmd, ready, timeout: calls.append((spec.name, cmd[1:], timeout)))
    ctl.start(SimpleNamespace(name="a", timeout=60))
    assert calls == [("a", ["-m", "local_models.decision.server", "--server", "kanana", "--run", "x/a@v1",
                            "--model", "/w", "--port", "8011"], 60)]
    assert "a ready on http://127.0.0.1:8011" in capsys.readouterr().out


def test_port_while_running(ctl, tmp_path):
    (tmp_path / "b.pid").write_text(str(os.getpid()))
    with pytest.raises(SystemExit, match="stop b before changing the port"):
        ctl.port(SimpleNamespace(port=9000))


def test_port(ctl, capsys):
    ctl.port(SimpleNamespace(port=9000))
    assert ctl.reg.path.read_text() == "port = 9000\n" and "decision models now use port 9000" in capsys.readouterr().out


def test_status_and_list_json(ctl, tmp_path, monkeypatch, capsys):
    (tmp_path / "b.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(Ctl, "info", lambda self, spec: {"run": spec.run} if spec.name == "a" else None)
    ctl.status(SimpleNamespace(json=True))
    assert json.loads(capsys.readouterr().out) == [
        {"name": "a", "state": "external", "url": "http://127.0.0.1:8011"}, {"name": "b", "state": "starting", "url": "http://127.0.0.1:8011"}]
    ctl.list(SimpleNamespace(json=True))
    assert json.loads(capsys.readouterr().out) == [
        {"name": "a", "port": 8011, "memory_gb": 0, "default": True, "note": None, "missing": False},
        {"name": "b", "port": 8011, "memory_gb": 0, "default": False, "note": "not downloaded", "missing": True}]


def test_list_aligns_long_names(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(weights, "find", lambda run: None)
    Ctl(registry_of(tmp_path, decision_spec("a"), decision_spec("a-much-longer-name"))).list(SimpleNamespace(json=False))
    assert len({line.index(":") for line in capsys.readouterr().out.splitlines()}) == 1


def test_unknown_model_is_an_error_not_a_traceback(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["decisionctl", "stop", "nope"])
    monkeypatch.setattr(Ctl, "load_registry", staticmethod(load_registry))
    with pytest.raises(SystemExit, match="unknown model 'nope'; registered: "):
        Ctl.main()


def test_llm_runs_mlx_vlm_and_reads_quantization(tmp_path):
    (tmp_path / "config.json").write_text('{"quantization": {"group_size": 32, "bits": 4, "mode": "mxfp4"}}')
    ctl = LlmCtl(registry_of(tmp_path, llm_spec(), port=8082))
    assert ctl.note(tmp_path) == "4-bit mxfp4" and ctl.url() == "http://127.0.0.1:8082/v1"
    assert ctl.command(ctl.reg.get(), tmp_path) == [sys.executable, "-m", "mlx_vlm.server", "--model", str(tmp_path),
                                                    "--host", "127.0.0.1", "--port", "8082", "--max-kv-size", "32768"]
