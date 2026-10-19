import os
from dataclasses import dataclass

from .. import ROOT, registry


@dataclass(frozen=True)
class ModelSpec:
    name: str
    backend: str
    port: int
    description: str = ""
    run: str | None = None
    memory_gb: float = 0
    min_confidence: float = 0.5

    def __post_init__(self):
        if self.backend != "kev-http":
            raise ValueError(f"backend must be kev-http, not {self.backend!r}")


class Registry(registry.Registry):
    spec = ModelSpec

    def resolve_run(self, spec):
        """run as kev.serve takes it: a checkpoint directory next to kev.toml as an absolute path, a Hub id as written."""
        local = self.path.parent / spec.run
        return str(local) if local.exists() else spec.run


def load_registry(path=None):
    return Registry.load(path or os.environ.get("KEV_MCP_REGISTRY") or ROOT / "kev.toml")
