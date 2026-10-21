import socket
import threading
import time

import pytest
import uvicorn


@pytest.fixture(scope="module")
def serve():
    """Starts an app on a free local port and returns the port; the servers stop with the module."""
    started = []

    def start(app):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        threading.Thread(target=srv.run, daemon=True).start()
        while not srv.started: time.sleep(0.05)
        started.append(srv)
        return port

    yield start
    for srv in started:
        srv.should_exit = True
