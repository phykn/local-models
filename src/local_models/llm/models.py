from dataclasses import dataclass

from .. import ROOT
from ..registry import Registry


@dataclass(frozen=True)
class ModelSpec:
    name: str
    run: str
    memory_gb: float
    description: str
    think: dict
    nothink: dict


def load_registry(path=ROOT / "llm.toml"):
    return Registry.load(path, ModelSpec)
