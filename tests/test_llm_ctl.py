import sys
from types import SimpleNamespace

import pytest
from conftest import llm_spec, registry_of

from local_models.llm.ctl import Ctl

REV = "a" * 40   # a commit hash, which the cache resolves without refs/


@pytest.fixture
def ctl(tmp_path, monkeypatch):
    from huggingface_hub import constants
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path / "hub"))
    return Ctl(registry_of(tmp_path / "llm.toml", llm_spec(run=f"org/w@{REV}", port=8020)))


def snapshot(tmp_path):
    path = tmp_path / "hub" / "models--org--w" / "snapshots" / REV
    path.mkdir(parents=True)
    return path


def test_weights_need_every_shard(ctl, tmp_path):
    spec = ctl.reg.get()
    assert ctl.note(spec) == {"note": "not downloaded", "missing": True}
    path = snapshot(tmp_path)
    (path / "config.json").write_text('{"quantization": {"group_size": 32, "bits": 4, "mode": "mxfp4"}}')
    (path / "model.safetensors.index.json").write_text('{"weight_map": {"a": "m-1.safetensors", "b": "m-2.safetensors"}}')
    (path / "m-1.safetensors").touch()
    assert ctl.weights(spec) is None   # an interrupted download
    (path / "m-2.safetensors").touch()
    assert ctl.note(spec) == {"note": "4-bit mxfp4"}
    assert ctl.command(spec) == [sys.executable, "-m", "mlx_vlm.server", "--model", str(path), "--host", "127.0.0.1",
                                 "--port", "8020", "--max-kv-size", "32768"]


def test_start_without_weights_says_pull(ctl, tmp_path, monkeypatch):
    monkeypatch.setattr("local_models.servers.LOGS", tmp_path)
    monkeypatch.setattr("local_models.servers.launch", lambda *a, **k: pytest.fail("spawned"))
    monkeypatch.setattr(Ctl, "info", lambda self, spec: None)
    with pytest.raises(SystemExit, match="llmctl pull m"):
        ctl.start(SimpleNamespace(name="m", timeout=1))
