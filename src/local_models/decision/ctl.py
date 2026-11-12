import sys

from .. import ctl
from .backends import SystemOneBackend
from .registry import load_registry


class Ctl(ctl.Ctl):
    prog = "decisionctl"
    backend = SystemOneBackend
    load_registry = staticmethod(load_registry)
    timeout = 3600

    def command(self, spec):
        return [sys.executable, "-m", "local_models.decision.systemone", "--server", spec.server, "--run", spec.run,
                "--port", str(spec.port)]
