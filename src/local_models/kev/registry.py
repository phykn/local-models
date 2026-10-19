import os
from dataclasses import dataclass

from .. import ROOT, registry

# kev-http: kev.serve (LoRA + head.pt checkpoints); jev-style: local_models.kev.jev_style (Jev-Style MLX repositories).
# Both serve /v1/systemone, so the MCP server talks to either the same way.
BACKENDS = ("kev-http", "jev-style")


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
        if self.backend not in BACKENDS:
            raise ValueError(f"backend must be one of {', '.join(BACKENDS)}, not {self.backend!r}")


class Registry(registry.Registry):
    spec = ModelSpec

    def resolve_run(self, spec):
        """run as kev.serve takes it: a checkpoint directory next to kev.toml as an absolute path, a Hub id as written."""
        local = self.path.parent / spec.run
        return str(local) if local.exists() else spec.run


def load_registry(path=None):
    return Registry.load(path or os.environ.get("KEV_MCP_REGISTRY") or ROOT / "kev.toml")
