import os
from dataclasses import dataclass

from .. import ROOT, registry


@dataclass(frozen=True)
class ModelSpec:
    name: str
    run: str
    port: int
    description: str = ""
    memory_gb: float = 0
    min_confidence: float = 0.5


class Registry(registry.Registry):
    spec = ModelSpec

    def resolve(self, spec):
        """run as kev.serve takes it: a checkpoint directory next to decision.toml as an absolute path, a Hub id as written."""
        local = self.path.parent / spec.run
        return str(local) if local.exists() else spec.run


def load_registry(path=None):
    return Registry.load(path or os.environ.get("DECISION_MCP_REGISTRY") or ROOT / "decision.toml")
