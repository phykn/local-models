from dataclasses import dataclass

from .. import ROOT
from ..registry import Registry

# kev: kev.serve; the others: local_models.decision.systemone with that runtime. All serve /v1/systemone.
SERVERS = ("kev", "kanana", "pplx-decider")


@dataclass(frozen=True)
class ModelSpec:
    name: str
    run: str
    port: int
    memory_gb: float
    description: str
    server: str = "kev"

    def __post_init__(self):
        if self.server not in SERVERS:
            raise ValueError(f"server must be one of {', '.join(SERVERS)}, not {self.server!r}")


def load_registry(path=ROOT / "decision.toml"):
    return Registry.load(path, ModelSpec)
