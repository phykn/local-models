import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from local_models import common
from local_models.llm import ctl
from local_models.llm.registry import ModelSpec, Registry, load_registry


def reg_of(tmp_path, **kw):
    return Registry(tmp_path / "models.toml", "m", {"m": ModelSpec("m", kw.pop("server", "mlx-vlm"), kw.pop("run", "a/b@c"), 1, **kw)})


def test_start_while_starting_does_not_spawn(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(common, "LOGS", tmp_path)
    (tmp_path / "m.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    ctl.start(reg_of(tmp_path), SimpleNamespace(name="m", timeout=1))
    assert "already running or starting" in capsys.readouterr().out
    assert (tmp_path / "m.pid").read_text() == str(os.getpid())


def test_start_without_weights_says_pull(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "LOGS", tmp_path)
    monkeypatch.setattr(ctl, "info_of", lambda spec: None)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(SystemExit, match="llmctl pull m"):
        ctl.start(reg_of(tmp_path, run="checkpoints/missing"), SimpleNamespace(name="m", timeout=1))


def test_commands():
    vlm = ModelSpec("m", "mlx-vlm", "a/b@c", 8020, max_kv_size=32768)
    assert ctl.command(vlm, Path("/w")) == [
        sys.executable, "-m", "mlx_vlm.server", "--model", "/w", "--host", "127.0.0.1", "--port", "8020",
        "--max-kv-size", "32768"]
    lm = ModelSpec("m", "mlx-lm", "a/b@c", 8020, max_kv_size=32768)
    assert ctl.command(lm, Path("/w")) == [
        sys.executable, "-m", "mlx_lm", "server", "--model", "/w", "--host", "127.0.0.1", "--port", "8020"]


def test_free_gb_is_positive():
    assert 0 < ctl.free_gb() < 10_000


def test_quantization(tmp_path):
    reg = reg_of(tmp_path, run="w")
    assert reg.quantization(reg.get()) is None
    (tmp_path / "w").mkdir()
    (tmp_path / "w/config.json").write_text('{"quantization": {"group_size": 32, "bits": 4, "mode": "mxfp4"}}')
    assert reg.quantization(reg.get()) == "4-bit mxfp4"
    (tmp_path / "w/config.json").write_text("{}")
    assert reg.quantization(reg.get()) == "unquantized"


def test_complete(tmp_path):
    from local_models.llm.registry import complete
    assert not complete(tmp_path)
    (tmp_path / "model.safetensors.index.json").write_text('{"weight_map": {"a": "m-1.safetensors", "b": "m-2.safetensors"}}')
    (tmp_path / "m-1.safetensors").touch()
    assert not complete(tmp_path)
    (tmp_path / "m-2.safetensors").touch()
    assert complete(tmp_path)


TOML = """default = "a"

[models."a"]
server = "mlx-vlm"
run = "x/a@1"
port = 8082   # keep this comment
memory_gb = 21

[models.b]
server = "mlx-vlm"
run = "x/b@1"
memory_gb = 22
"""


def port_reg(tmp_path, monkeypatch, text=TOML):
    monkeypatch.setattr(common, "LOGS", tmp_path)
    monkeypatch.setattr(ctl, "info_of", lambda spec: None)
    path = tmp_path / "models.toml"
    path.write_text(text)
    return path


def test_port_while_running(tmp_path, monkeypatch):
    path = port_reg(tmp_path, monkeypatch, TOML.replace("memory_gb = 22", "memory_gb = 22\nport = 8082"))
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    with pytest.raises(SystemExit, match="stop a"):
        ctl.port(load_registry(path), SimpleNamespace(name="a", port=9000))
    assert load_registry(path).get("a").port == 8082


def test_start_on_a_port_another_model_holds(tmp_path, monkeypatch):
    path = port_reg(tmp_path, monkeypatch, TOML.replace("memory_gb = 22", "memory_gb = 22\nport = 8082"))
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(common, "port_in_use", lambda port: port == 8082)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    with pytest.raises(SystemExit, match="port 8082 is in use by a; stop it first"):
        ctl.start(load_registry(path), SimpleNamespace(name="b", timeout=1))
