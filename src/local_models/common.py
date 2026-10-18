import os
import re
import signal
import socket
import time
import tomllib
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "weight"   # HF_HOME for every model
LOGS = ROOT / "logs"        # server logs and pid files, named after the model


def pid_of(name):
    f = LOGS / f"{name}.pid"
    if not f.exists():
        return None
    pid = int(f.read_text())
    try:
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, PermissionError):   # PermissionError: the pid now belongs to another user's process
        f.unlink()
        return None


def port_in_use(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def state(info, pid):
    """running: started here and answering; external: answering but not started by a ctl; starting: started, not answering yet."""
    return "running" if info and pid else "external" if info else "starting" if pid else "stopped"


def refuse_busy_port(reg, spec):
    if port_in_use(spec.port):
        # models may share a port, so this is usually another model; the server would fail and orphan its pid file
        on = [s.name for s in reg.models.values() if s.port == spec.port and s.name != spec.name and pid_of(s.name)]
        raise SystemExit(f"port {spec.port} is in use" + (f" by {', '.join(on)}; stop it first" if on else ""))


def stop(name):
    pid = pid_of(name)
    if not pid:
        print(f"{name} is not running")
        return
    with suppress(ProcessLookupError):   # the server may exit on its own at any point
        os.killpg(pid, signal.SIGTERM)
        for _ in range(30):
            if not pid_of(name):
                break
            time.sleep(0.5)
        else:
            os.killpg(pid, signal.SIGKILL)
    (LOGS / f"{name}.pid").unlink(missing_ok=True)
    print(f"stopped {name}")


def set_port(reg, name, port, load_registry):
    """Rewrite the port line of [models."name"] in the registry file, keeping its comments and layout."""
    if not 1024 <= port <= 65535:
        raise SystemExit(f"port must be between 1024 and 65535, not {port}")
    text = reg.path.read_text()
    lines = text.splitlines(keepends=True)
    head = re.compile(rf"""\s*\[\s*models\s*\.\s*(["']?){re.escape(name)}\1\s*\]""")
    start = next((i for i, l in enumerate(lines) if head.match(l)), None)
    if start is None:
        raise SystemExit(f"could not find [models.\"{name}\"] in {reg.path}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    key = next((i for i in range(start + 1, end) if re.match(r"\s*port\s*=", lines[i])), None)
    if key is None:
        lines.insert(start + 1, f"port = {port}\n")
    else:
        lines[key] = re.sub(r"=\s*\d+", f"= {port}", lines[key], count=1)
    reg.path.write_text("".join(lines))
    try:   # the edit must not break or misplace anything in the file
        ok = load_registry(reg.path).get(name).port == port
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        ok = False
    if not ok:
        reg.path.write_text(text)
        raise SystemExit(f"could not set the port of {name} in {reg.path}")
    print(f"{name} now uses port {port}")
