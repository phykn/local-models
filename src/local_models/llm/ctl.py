import json
import sys
from pathlib import Path

from .. import ctl
from .backends import OpenAIBackend
from .registry import load_registry


class Ctl(ctl.Ctl):
    prog = "llmctl"
    backend = OpenAIBackend
    load_registry = staticmethod(load_registry)
    timeout = 1800

    def url(self, spec):
        return f"http://127.0.0.1:{spec.port}/v1"

    def note(self, spec):
        if not (path := self.weights(spec)):
            return {"note": "not downloaded", "missing": True}
        q = json.loads((path / "config.json").read_text()).get("quantization")
        return {"note": f"{q['bits']}-bit {q.get('mode', 'affine')}" if q else "unquantized"}

    def weights(self, spec):
        from huggingface_hub import snapshot_download   # reads HF_HOME at import
        from huggingface_hub.errors import LocalEntryNotFoundError

        repo, rev = spec.run.split("@", 1)
        try:
            path = Path(snapshot_download(repo, revision=rev, local_files_only=True))
        except LocalEntryNotFoundError:
            return None
        # an interrupted download can leave a snapshot with config.json and no weights
        if (index := path / "model.safetensors.index.json").exists():
            files = set(json.loads(index.read_text())["weight_map"].values())
        else:
            files = {"model.safetensors"}
        return path if all((path / f).exists() for f in files | {"config.json"}) else None

    def command(self, spec):
        if not (path := self.weights(spec)):
            sys.exit(f"{spec.name} is not downloaded; run: llmctl pull {spec.name}")
        # mlx-vlm listens on 0.0.0.0 unless told otherwise
        return [sys.executable, "-m", "mlx_vlm.server", "--model", str(path), "--host", "127.0.0.1",
                "--port", str(spec.port), "--max-kv-size", "32768"]

    def pull(self, a):
        from huggingface_hub import snapshot_download

        spec = self.reg.get(a.name)
        repo, rev = spec.run.split("@", 1)
        print(f"{repo}@{rev[:10]} -> {snapshot_download(repo, revision=rev)}")
