import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..common import ROOT, WEIGHTS

SERVERS = ("mlx-vlm", "mlx-lm")


def complete(path):
    """True if every weight file is in path; a snapshot holding only config.json is not downloaded."""
    if (index := path / "model.safetensors.index.json").exists():
        return all((path / f).exists() for f in set(json.loads(index.read_text())["weight_map"].values()))
    return (path / "model.safetensors").exists()


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

    @property
    def repo(self):
        """The Hugging Face id without the revision, or None for a local directory."""
        return self.run.split("@")[0] if "@" in self.run else None


@dataclass(frozen=True)
class Registry:
    path: Path
    default: str
    models: dict[str, ModelSpec]

    def get(self, name=None):
        name = name or self.default
        if name not in self.models:
            raise KeyError(f"unknown model {name!r}; registered: {', '.join(self.models)}")
        return self.models[name]

    def resolve(self, run):
        """Local directory for run: a path next to llm.toml, or the id@commit snapshot in HF_HOME. None if not downloaded."""
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
        """How the downloaded weights are stored, e.g. "4-bit mxfp4"; None if not downloaded."""
        if not (path := self.resolve(spec.run)) or not (cfg := path / "config.json").exists():
            return None
        q = json.loads(cfg.read_text()).get("quantization")
        return f"{q['bits']}-bit {q.get('mode', 'affine')}" if q else "unquantized"


def load_registry(path=None):
    path = Path(path or os.environ.get("LLM_LOCAL_REGISTRY") or ROOT / "llm.toml")
    cfg = tomllib.loads(path.read_text())
    known = set(ModelSpec.__dataclass_fields__) - {"name"}
    models = {}
    for name, d in cfg["models"].items():
        if unknown := set(d) - known:
            raise KeyError(f"model {name!r} in {path}: unknown keys {', '.join(sorted(unknown))}")
        spec = ModelSpec(name=name, **d)
        if spec.server not in SERVERS:
            raise KeyError(f"model {name!r}: server must be one of {', '.join(SERVERS)}, not {spec.server!r}")
        models[name] = spec
    default = cfg.get("default") or next(iter(models))
    if default not in models:
        raise KeyError(f"default model {default!r} is not in {path}")
    return Registry(path, default, models)
