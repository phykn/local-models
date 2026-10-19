import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .. import ROOT, WEIGHTS, registry

SERVERS = ("mlx-vlm", "mlx-lm")


@dataclass(frozen=True)
class ModelSpec:
    name: str
    server: str
    run: str
    port: int
    memory_gb: float = 0
    max_kv_size: int | None = None
    description: str = ""
    think: dict = field(default_factory=dict)
    nothink: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.server not in SERVERS:
            raise ValueError(f"server must be one of {', '.join(SERVERS)}, not {self.server!r}")

    @property
    def repo(self):
        return self.run.split("@")[0] if "@" in self.run else None


class Registry(registry.Registry):
    spec = ModelSpec

    def resolve(self, run):
        if "@" not in run:
            local = self.path.parent / run
            return local if local.exists() else None
        os.environ.setdefault("HF_HOME", str(WEIGHTS))
        from huggingface_hub import snapshot_download   # reads HF_HOME at import
        from huggingface_hub.errors import LocalEntryNotFoundError

        repo, rev = run.split("@", 1)
        try:
            path = Path(snapshot_download(repo, revision=rev, local_files_only=True))
        except LocalEntryNotFoundError:
            return None
        return path if complete(path) else None

    def quantization(self, spec):
        if not (path := self.resolve(spec.run)) or not (cfg := path / "config.json").exists():
            return None
        q = json.loads(cfg.read_text()).get("quantization")
        return f"{q['bits']}-bit {q.get('mode', 'affine')}" if q else "unquantized"


def complete(path):
    # an interrupted download can leave a snapshot with config.json and no weights
    if (index := path / "model.safetensors.index.json").exists():
        return all((path / f).exists() for f in set(json.loads(index.read_text())["weight_map"].values()))
    return (path / "model.safetensors").exists()


def load_registry(path=None):
    return Registry.load(path or os.environ.get("LLM_LOCAL_REGISTRY") or ROOT / "llm.toml")
