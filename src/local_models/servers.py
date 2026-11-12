import os
import re
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress

from . import LOGS, ROOT


def pid_of(name):
    f = LOGS / f"{name}.pid"
    if not f.exists():
        return None
    pid = int(f.read_text())
    try:
        os.kill(pid, 0)
        # a pid file left by a crash or reboot may name a pid since reused; the server started before its pid file was written
        alive = started_at(pid) <= f.stat().st_mtime + 2
    except (ProcessLookupError, PermissionError):   # PermissionError: the pid now belongs to another user's process
        alive = False
    if not alive:
        f.unlink(missing_ok=True)
        return None
    return pid


def started_at(pid):
    out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    if not out:
        raise ProcessLookupError(pid)
    days, _, clock = out.rpartition("-")   # etime is [[dd-]hh:]mm:ss
    secs = 0
    for part in clock.split(":"):
        secs = secs * 60 + int(part)
    return time.time() - secs - int(days or 0) * 86400


def port_in_use(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_gb():
    # what macOS can hand out without swapping; LOCAL-MODELS.app counts it the same way
    s = subprocess.check_output(["vm_stat"], text=True)
    page = int(re.search(r"page size of (\d+)", s)[1])
    pages = sum(int(re.search(rf"{k}:\s+(\d+)", s)[1]) for k in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"))
    return pages * page / 2**30


def launch(spec, cmd, ready, timeout):
    if spec.memory_gb > (free := free_gb()):
        print(f"warning: {spec.name} needs about {spec.memory_gb:.0f} GB and {free:.0f} GB is free; other apps or models may be swapped out")
    LOGS.mkdir(exist_ok=True)
    log, pidf = LOGS / f"{spec.name}.log", LOGS / f"{spec.name}.pid"
    with open(log, "ab") as out:
        p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
    pidf.write_text(str(p.pid))
    print(f"starting {spec.name} (pid {p.pid}), log: {log}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if p.poll() is not None:
            pidf.unlink(missing_ok=True)
            tail = log.read_text(errors="replace").splitlines()[-20:]
            sys.exit(f"{spec.name} exited with {p.returncode}:\n" + "\n".join(tail))
        if ready():
            return
        time.sleep(2)
    sys.exit(f"{spec.name} did not answer within {timeout}s; it is still starting, see the log")


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
