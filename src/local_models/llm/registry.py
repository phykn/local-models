from dataclasses import dataclass

from .. import ROOT
from ..registry import Registry


@dataclass(frozen=True)
class ModelSpec:
    name: str
    run: str
    port: int
    memory_gb: float
    description: str
    think: dict
    nothink: dict

    @property
    def repo(self):
        return self.run.split("@")[0]


def load_registry(path=ROOT / "llm.toml"):
    return Registry.load(path, ModelSpec)
