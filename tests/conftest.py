import socket
import threading
import time

import pytest
import uvicorn

from local_models.registry import Registry


@pytest.fixture(scope="module")
def serve():
    """Starts an app on a free local port and returns the port; the servers stop with the module."""
    started = []

    def start(app):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=srv.run, daemon=True).start()
        while not srv.started:
            time.sleep(0.05)
        started.append(srv)
        return port

    yield start
    for srv in started:
        srv.should_exit = True


def decision_spec(name="m", **kw):
    from local_models.decision.models import ModelSpec
    return ModelSpec(name, **{"server": "kanana", "run": f"x/{name}@v1", "memory_gb": 0, "description": "", **kw})


def llm_spec(name="m", **kw):
    from local_models.llm.models import ModelSpec
    return ModelSpec(name, **{"run": f"x/{name}@v1", "memory_gb": 0, "description": "",
                              "think": {"temperature": 1.0}, "nothink": {"temperature": 0.7}, **kw})


def registry_of(path, *specs, port=8011):
    return Registry(path, type(specs[0]), specs[0].name, port, {s.name: s for s in specs})
