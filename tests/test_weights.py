import pytest

from local_models import weights

REV = "a" * 40   # a commit hash, which the cache resolves without refs/


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    from huggingface_hub import constants
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path))
    return tmp_path / "models--org--w" / "snapshots" / REV


def test_find_needs_every_shard(snapshot):
    assert weights.find(f"org/w@{REV}") is None
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    (snapshot / "model.safetensors.index.json").write_text('{"weight_map": {"a": "m-1.safetensors", "b": "m-2.safetensors"}}')
    (snapshot / "m-1.safetensors").touch()
    assert weights.find(f"org/w@{REV}") is None   # an interrupted download
    (snapshot / "m-2.safetensors").touch()
    assert weights.find(f"org/w@{REV}") == snapshot
