import json
import os
import sys
from types import SimpleNamespace

import pytest

from local_models import servers
from local_models.kev import ctl
from local_models.kev.registry import ModelSpec, Registry, load_registry


def test_start_while_starting_does_not_spawn(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(servers, "LOGS", tmp_path)
    (tmp_path / "m.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(ctl, "info_of", lambda spec: None)
    monkeypatch.setattr(servers, "launch", lambda *a, **k: pytest.fail("spawned"))
    reg = Registry(tmp_path / "models.toml", "m", {"m": ModelSpec("m", run="x/y", port=1)})
    ctl.start(reg, SimpleNamespace(name="m", timeout=1))
    assert "still starting" in capsys.readouterr().out
    assert (tmp_path / "m.pid").read_text() == str(os.getpid())


def test_start_with_missing_local_checkpoint(tmp_path):
    reg = Registry(tmp_path / "models.toml", "m", {"m": ModelSpec("m", run="checkpoints/ko-4b", port=1)})
    with pytest.raises(SystemExit, match="does not exist"):
        ctl.start(reg, SimpleNamespace(name="m", timeout=1))


def port_reg(tmp_path, monkeypatch, text):
    monkeypatch.setattr(servers, "LOGS", tmp_path)
    monkeypatch.setattr(ctl, "info_of", lambda spec: None)
    path = tmp_path / "models.toml"
    path.write_text(text)
    return load_registry(path)


TOML = '''default = "a"

[models."a"]
run = "x/a@v1"
port = 8011   # keep this comment
memory_gb = 16

[models.b]
run = "x/b@v1"
memory_gb = 4
port = 8012
'''


def test_start_on_a_port_another_model_holds(tmp_path, monkeypatch):
    reg = port_reg(tmp_path, monkeypatch, TOML.replace("port = 8012", "port = 8011"))
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(servers, "port_in_use", lambda port: port == 8011)
    monkeypatch.setattr(servers, "launch", lambda *a, **k: pytest.fail("spawned"))
    with pytest.raises(SystemExit, match="port 8011 is in use by a; stop it first"):
        ctl.start(reg, SimpleNamespace(name="b", timeout=1))


def test_port_while_running(tmp_path, monkeypatch):
    reg = port_reg(tmp_path, monkeypatch, TOML)
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    with pytest.raises(SystemExit, match="stop a"):
        ctl.port(reg, SimpleNamespace(name="a", port=9000))


def test_status_and_list_json(tmp_path, monkeypatch, capsys):
    reg = port_reg(tmp_path, monkeypatch, TOML.replace("port = 8012", "port = 8011"))
    (tmp_path / "b.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(ctl, "info_of", lambda spec: {"backend": "mlx", "dtype": "bf16"} if spec.name == "a" else None)
    ctl.status(reg, SimpleNamespace(json=True))
    assert json.loads(capsys.readouterr().out) == [
        {"name": "a", "state": "external", "url": "http://127.0.0.1:8011"}, {"name": "b", "state": "starting", "url": "http://127.0.0.1:8011"}]
    ctl.models(reg, SimpleNamespace(json=True))
    assert [m["name"] for m in json.loads(capsys.readouterr().out) if m["default"]] == ["a"]


def test_unknown_model_is_an_error_not_a_traceback(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["kevctl", "start", "nope"])
    with pytest.raises(SystemExit, match="unknown model 'nope'; registered: "):
        ctl.main()


def test_start_runs_kev_serve_on_the_model_port(tmp_path, monkeypatch, capsys):
    (tmp_path / "ck").mkdir()
    (tmp_path / "ck/head.pt").touch()
    reg = Registry(tmp_path / "kev.toml", "m", {"m": ModelSpec("m", run="ck", port=8011, memory_gb=4)})
    monkeypatch.setattr(servers, "LOGS", tmp_path)
    monkeypatch.setattr(servers, "port_in_use", lambda port: False)
    monkeypatch.setattr(ctl, "info_of", lambda spec: None)
    calls = []
    monkeypatch.setattr(servers, "launch", lambda spec, cmd, ready, timeout: calls.append((spec.name, cmd[1:], timeout)) or {"backend": "mlx", "dtype": "bf16"})
    ctl.start(reg, SimpleNamespace(name="m", timeout=60))
    assert calls == [("m", ["-m", "kev.serve", "--run", str(tmp_path / "ck"), "--port", "8011"], 60)]
    assert "m ready on :8011 (mlx bf16)" in capsys.readouterr().out
