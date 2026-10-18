import os
import subprocess

import pytest

from local_models import common
from local_models.kev.registry import ModelSpec, Registry, load_registry


@pytest.fixture(autouse=True)
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "LOGS", tmp_path)


def test_stale_pid_file_is_removed(tmp_path):
    p = subprocess.Popen(["true"]); p.wait()
    (tmp_path / "m.pid").write_text(str(p.pid))
    assert common.pid_of("m") is None and not (tmp_path / "m.pid").exists()


def test_pid_reused_by_another_user(tmp_path):
    (tmp_path / "m.pid").write_text("1")   # launchd, owned by root
    assert common.pid_of("m") is None and not (tmp_path / "m.pid").exists()


def test_state():
    assert [common.state(i, p) for i, p in ((1, 1), (1, None), (None, 1), (None, None))] == ["running", "external", "starting", "stopped"]


TOML = '''default = "a"

[models."a"]
backend = "kev-http"
port = 8011   # keep this comment
memory_gb = 16

[models.b]
backend = "kev-http"
memory_gb = 4
'''


def reg_of(tmp_path, text=TOML):
    path = tmp_path / "models.toml"
    path.write_text(text)
    return load_registry(path)


def test_set_port_rewrites_only_that_model(tmp_path):
    reg = reg_of(tmp_path)
    common.set_port(reg, "a", 9000, load_registry)
    assert reg.path.read_text() == TOML.replace("8011", "9000")
    common.set_port(reg, "b", 9001, load_registry)   # b has no port line yet
    new = load_registry(reg.path)
    assert (new.get("a").port, new.get("b").port) == (9000, 9001)


def test_set_port_rejects_privileged(tmp_path):
    reg = reg_of(tmp_path)
    with pytest.raises(SystemExit, match="between 1024"):
        common.set_port(reg, "a", 80, load_registry)
    assert load_registry(reg.path).get("a").port == 8011


def test_busy_port_names_the_model_holding_it(tmp_path, monkeypatch):
    reg = Registry(tmp_path / "models.toml", "a", {n: ModelSpec(n, "kev-http", port=8011) for n in "ab"})
    (tmp_path / "a.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(common, "port_in_use", lambda port: True)
    with pytest.raises(SystemExit, match="port 8011 is in use by a; stop it first"):
        common.refuse_busy_port(reg, reg.get("b"))
