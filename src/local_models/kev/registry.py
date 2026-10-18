import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..common import ROOT



@dataclass(frozen=True)
class ModelSpec:
    name: str
    backend: str
    description: str = ""
    run: str | None = None
    port: int | None = None
    memory_gb: float = 0
    min_confidence: float = 0.5
    extra: dict = field(default_factory=dict)


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

    def resolve_run(self, spec):
        local = self.path.parent / spec.run
        return str(local) if local.exists() else spec.run


def load_registry(path=None):
    path = Path(path or os.environ.get("KEV_MCP_REGISTRY") or ROOT / "kev.toml")
    cfg = tomllib.loads(path.read_text())
    known = set(ModelSpec.__dataclass_fields__) - {"name", "extra"}
    models = {}
    for name, d in cfg["models"].items():
        models[name] = ModelSpec(name=name, **{k: v for k, v in d.items() if k in known},
                                 extra={k: v for k, v in d.items() if k not in known})
    default = cfg.get("default") or next(iter(models))
    if default not in models:
        raise KeyError(f"default model {default!r} is not in {path}")
    return Registry(path, default, models)
