import sys

from .. import ctl
from .backends import KevHttpBackend
from .registry import load_registry


class Ctl(ctl.Ctl):
    prog = "decisionctl"
    backend = KevHttpBackend
    load_registry = staticmethod(load_registry)
    timeout = 3600

    def command(self, spec):
        if spec.server == "kev":
            return [sys.executable, "-m", "kev.serve", "--run", spec.run, "--port", str(spec.port)]
        return [sys.executable, "-m", "local_models.decision.systemone", "--server", spec.server, "--run", spec.run,
                "--port", str(spec.port)]
