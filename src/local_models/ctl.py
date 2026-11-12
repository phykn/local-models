import argparse
import asyncio
import json
import os
import sys

from . import LOGS, WEIGHTS, servers, weights
from .registry import RegistryError


class Ctl:
    """The CLI both kinds share; a subclass sets prog, load_registry, client and timeout, and defines command."""

    def __init__(self, reg):
        self.reg = reg

    @classmethod
    def main(cls):
        ap = argparse.ArgumentParser(prog=cls.prog)
        sub = ap.add_subparsers(dest="cmd", required=True)
        sub.add_parser("list").add_argument("--json", action="store_true")
        sub.add_parser("status").add_argument("--json", action="store_true")
        p = sub.add_parser("start")
        p.add_argument("name")
        p.add_argument("--timeout", type=int, default=cls.timeout)
        sub.add_parser("stop").add_argument("name")
        sub.add_parser("port").add_argument("port", type=int)
        sub.add_parser("pull").add_argument("name")
        a = ap.parse_args()
        os.environ.setdefault("HF_HOME", str(WEIGHTS))   # inherited by the servers
        # only pull downloads; everything else, the servers included, uses weights already in weight/
        os.environ["HF_HUB_OFFLINE"] = "0" if a.cmd == "pull" else os.environ.get("HF_HUB_OFFLINE", "1")
        try:
            getattr(cls(cls.load_registry()), a.cmd)(a)
        except RegistryError as e:
            sys.exit(str(e))

    def info(self, spec):
        return asyncio.run(self.client(spec, self.reg.port).info())

    def url(self):
        return f"http://127.0.0.1:{self.reg.port}"

    def note(self, path):
        return None

    # the rows of list and status are the JSON that LOCAL-MODELS.app decodes; change Ctl.swift with them
    def list(self, a):
        rows = []
        for spec in self.reg.models.values():
            path = weights.find(spec.run)
            rows.append({"name": spec.name, "port": self.reg.port, "memory_gb": spec.memory_gb,
                         "default": spec.name == self.reg.default,
                         "note": self.note(path) if path else "not downloaded", "missing": path is None})
        if a.json:
            print(json.dumps(rows))
            return
        w = max(map(len, self.reg.models))
        for r in rows:
            print(f"{r['name']:<{w}} :{r['port']}  {r['memory_gb']:.0f} GB  {r['note'] or ''}".rstrip())

    def status(self, a):
        rows, w = [], max(map(len, self.reg.models))
        for spec in self.reg.models.values():
            info, pid = self.info(spec), servers.pid_of(spec.name)
            state = "running" if info and pid else "external" if info else "starting" if pid else "stopped"
            rows.append({"name": spec.name, "state": state, "url": self.url()})
            if not a.json:
                default = " (default)" if spec.name == self.reg.default else ""
                print(f"{spec.name:<{w}} {state:<9} pid={pid or '-':<7} {spec.run}{default}")
        if a.json:
            print(json.dumps(rows))

    def start(self, a):
        spec = self.reg.get(a.name)
        if self.info(spec):
            print(f"{spec.name} is already running on :{self.reg.port}")
            return
        if pid := servers.pid_of(spec.name):
            # a second server on the same port would fail and orphan the first one's pid file
            print(f"{spec.name} is still starting (pid {pid}); see {LOGS / f'{spec.name}.log'}")
            return
        if servers.port_in_use(self.reg.port):
            on = [s.name for s in self.reg.models.values() if servers.pid_of(s.name)]
            sys.exit(f"port {self.reg.port} is in use" + (f" by {', '.join(on)}; stop it first" if on else ""))
        if not (path := weights.find(spec.run)):
            sys.exit(f"{spec.name} is not downloaded; run: {self.prog} pull {spec.name}")
        servers.launch(spec, self.command(spec, path), lambda: self.info(spec), a.timeout)
        print(f"{spec.name} ready on {self.url()}")

    def stop(self, a):
        servers.stop(self.reg.get(a.name).name)

    def port(self, a):
        if on := [s.name for s in self.reg.models.values() if servers.pid_of(s.name) or self.info(s)]:
            sys.exit(f"stop {', '.join(on)} before changing the port")
        self.reg.set_port(a.port)
        print(f"{self.prog.removesuffix('ctl')} models now use port {a.port}")

    def pull(self, a):
        spec = self.reg.get(a.name)
        print(f"{spec.name} -> {weights.pull(spec.run)}")
