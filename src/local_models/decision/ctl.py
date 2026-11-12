import sys

from .. import ctl
from .client import SystemOneClient
from .models import load_registry


class Ctl(ctl.Ctl):
    prog = "decisionctl"
    load_registry = staticmethod(load_registry)
    client = SystemOneClient
    timeout = 3600

    def command(self, spec, path):
        return [sys.executable, "-m", "local_models.decision.server", "--server", spec.server, "--run", spec.run,
                "--model", str(path), "--port", str(self.reg.port)]
