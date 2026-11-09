import os
from dataclasses import dataclass

from .. import ROOT, registry

# kev: kev.serve (Kev LoRA + head.pt checkpoints); the others: local_models.decision.systemone with that runtime.
# All serve /v1/systemone, so the MCP server talks to every model the same way.
SERVERS = ("kev", "kanana", "pplx-decider")


@dataclass(frozen=True)
class ModelSpec:
    name: str
    run: str
    port: int
    description: str = ""
    memory_gb: float = 0
    min_confidence: float = 0.5
    server: str = "kev"

    def __post_init__(self):
        if self.server not in SERVERS:
            raise ValueError(f"server must be one of {', '.join(SERVERS)}, not {self.server!r}")


class Registry(registry.Registry):
    spec = ModelSpec

    def resolve(self, spec):
        """run as the server takes it: a checkpoint directory next to decision.toml as an absolute path, a Hub id as written."""
        local = self.path.parent / spec.run
        return str(local) if local.exists() else spec.run


def load_registry(path=None):
    return Registry.load(path or os.environ.get("DECISION_MCP_REGISTRY") or ROOT / "decision.toml")
