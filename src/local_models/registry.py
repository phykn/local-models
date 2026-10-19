import re
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class Registry:
    path: Path
    default: str
    models: dict

    spec = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        cfg = tomllib.loads(path.read_text())
        if not cfg.get("models"):
            raise RegistryError(f'{path} has no [models."name"] tables')
        known = {f.name for f in fields(cls.spec)} - {"name"}
        models = {}
        for name, table in cfg["models"].items():
            if unknown := set(table) - known:
                raise RegistryError(f"model {name!r} in {path}: unknown keys {', '.join(sorted(unknown))}")
            try:
                models[name] = cls.spec(name=name, **table)
            except (TypeError, ValueError) as e:
                raise RegistryError(f"model {name!r} in {path}: {e}") from None
        default = cfg.get("default") or next(iter(models))
        if default not in models:
            raise RegistryError(f"default model {default!r} is not in {path}")
        return cls(path, default, models)

    def reload(self):
        try:
            return self.load(self.path)
        except (OSError, tomllib.TOMLDecodeError, RegistryError):   # the app may be rewriting the file
            return self

    def get(self, name=None):
        name = name or self.default
        if name not in self.models:
            raise RegistryError(f"unknown model {name!r}; registered: {', '.join(self.models)}")
        return self.models[name]

    def set_port(self, name, port):
        # edit the one line rather than re-serialize, so the file keeps its comments and layout
        if not 1024 <= port <= 65535:
            raise RegistryError(f"port must be between 1024 and 65535, not {port}")
        text = self.path.read_text()
        lines = text.splitlines(keepends=True)
        head = re.compile(rf"""\s*\[\s*models\s*\.\s*(["']?){re.escape(name)}\1\s*\]""")
        start = next((i for i, line in enumerate(lines) if head.match(line)), None)
        if start is None:
            raise RegistryError(f'could not find [models."{name}"] in {self.path}')
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        key = next((i for i in range(start + 1, end) if re.match(r"\s*port\s*=", lines[i])), None)
        if key is None:
            raise RegistryError(f'could not find the port line of [models."{name}"] in {self.path}')
        lines[key] = re.sub(r"=\s*\d+", f"= {port}", lines[key], count=1)
        want = tomllib.loads(text)
        want["models"][name]["port"] = port
        try:   # the edit must change that one value and nothing else
            ok = tomllib.loads("".join(lines)) == want
        except tomllib.TOMLDecodeError:
            ok = False
        if not ok:
            raise RegistryError(f"could not set the port of {name} in {self.path}")
        self.path.write_text("".join(lines))
