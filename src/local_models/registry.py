import re
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class RegistryError(Exception):
    pass


def check_port(port):
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise RegistryError(f"port must be between 1024 and 65535, not {port!r}")


@dataclass(frozen=True)
class Registry:
    path: Path
    spec: type
    default: str
    port: int
    models: dict

    @classmethod
    def load(cls, path, spec):
        path = Path(path)
        cfg = tomllib.loads(path.read_text())
        if unknown := set(cfg) - {"default", "port", "models"}:
            raise RegistryError(f"{path}: unknown keys {', '.join(sorted(unknown))}")
        if "port" not in cfg:
            raise RegistryError(f"{path} has no port")
        check_port(cfg["port"])
        if not cfg.get("models"):
            raise RegistryError(f'{path} has no [models."name"] tables')
        known = {f.name for f in fields(spec)} - {"name"}
        models = {}
        for name, table in cfg["models"].items():
            if unknown := set(table) - known:
                raise RegistryError(f"model {name!r} in {path}: unknown keys {', '.join(sorted(unknown))}")
            try:
                models[name] = spec(name=name, **table)
            except (TypeError, ValueError) as e:
                raise RegistryError(f"model {name!r} in {path}: {e}") from None
            if "@" not in models[name].run:
                raise RegistryError(f"model {name!r} in {path}: run must be repo@revision, not {models[name].run!r}")
        default = cfg.get("default", next(iter(models)))
        if default not in models:
            raise RegistryError(f"default model {default!r} is not in {path}")
        return cls(path, spec, default, cfg["port"], models)

    def reload(self):
        try:
            return self.load(self.path, self.spec)
        except (OSError, tomllib.TOMLDecodeError, RegistryError):   # the app may be rewriting the file
            return self

    def get(self, name=None):
        name = name or self.default
        if name not in self.models:
            raise RegistryError(f"unknown model {name!r}; registered: {', '.join(self.models)}")
        return self.models[name]

    def set_port(self, port):
        # edit the one line rather than re-serialize, so the file keeps its comments and layout
        check_port(port)
        text = self.path.read_text()
        head, sep, tables = text.partition("\n[")   # the port line sits above the first table
        new = re.sub(r"(?m)^port\s*=\s*\d+", f"port = {port}", head, count=1) + sep + tables
        want = {**tomllib.loads(text), "port": port}
        if tomllib.loads(new) != want:
            raise RegistryError(f"could not set the port in {self.path}")
        self.path.write_text(new)
