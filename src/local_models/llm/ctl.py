import json
import sys

from .. import ctl
from .client import ChatClient
from .models import load_registry


class Ctl(ctl.Ctl):
    prog = "llmctl"
    load_registry = staticmethod(load_registry)
    client = ChatClient
    timeout = 1800

    def url(self):
        return f"http://127.0.0.1:{self.reg.port}/v1"

    def note(self, path):
        q = json.loads((path / "config.json").read_text()).get("quantization")
        return f"{q['bits']}-bit {q.get('mode', 'affine')}" if q else "unquantized"

    def command(self, spec, path):
        # mlx-vlm listens on 0.0.0.0 unless told otherwise
        return [sys.executable, "-m", "mlx_vlm.server", "--model", str(path), "--host", "127.0.0.1",
                "--port", str(self.reg.port), "--max-kv-size", "32768"]
