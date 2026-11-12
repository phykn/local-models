from dataclasses import dataclass

from .. import ROOT
from ..registry import Registry

SERVERS = ("kanana", "pplx-decider")


@dataclass(frozen=True)
class ModelSpec:
    name: str
    server: str
    run: str
    memory_gb: float
    description: str

    def __post_init__(self):
        if self.server not in SERVERS:
            raise ValueError(f"server must be one of {', '.join(SERVERS)}, not {self.server!r}")


def load_registry(path=ROOT / "decision.toml"):
    return Registry.load(path, ModelSpec)
