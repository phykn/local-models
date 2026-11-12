import argparse
import asyncio
import json
import os
import sys

from . import WEIGHTS, servers
from .registry import RegistryError


class Ctl:
    def __init__(self, reg):
        self.reg = reg

    @classmethod
    def main(cls):
        ap = argparse.ArgumentParser(prog=cls.prog)
        sub = ap.add_subparsers(dest="cmd", required=True)
        sub.add_parser("list").add_argument("--json", action="store_true")
        sub.add_parser("status").add_argument("--json", action="store_true")
        p = sub.add_parser("start"); p.add_argument("name"); p.add_argument("--timeout", type=int, default=cls.timeout)
        sub.add_parser("stop").add_argument("name")
        p = sub.add_parser("port"); p.add_argument("name"); p.add_argument("port", type=int)
        if hasattr(cls, "pull"):
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
        return asyncio.run(self.backend(spec).info())

    def url(self, spec):
        return f"http://127.0.0.1:{spec.port}"

    def note(self, spec):
        return {}

    # the rows of list and status are the JSON that LOCAL-MODELS.app decodes; change Ctl.swift with them
    def list(self, a):
        rows = [{"name": s.name, "port": s.port, "memory_gb": s.memory_gb, "default": s.name == self.reg.default,
                 "note": None, "missing": False, **self.note(s)} for s in self.reg.models.values()]
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
            rows.append({"name": spec.name, "state": state, "url": self.url(spec)})
            if not a.json:
                default = " (default)" if spec.name == self.reg.default else ""
                print(f"{spec.name:<{w}} {state:<9} :{spec.port}  pid={pid or '-':<7} {spec.run}{default}")
        if a.json:
            print(json.dumps(rows))

    def start(self, a):
        spec = self.reg.get(a.name)
        if self.info(spec):
            print(f"{spec.name} is already running on :{spec.port}")
            return
        if pid := servers.pid_of(spec.name):
            # a second server on the same port would fail and orphan the first one's pid file
            print(f"{spec.name} is still starting (pid {pid}); see {servers.LOGS / f'{spec.name}.log'}")
            return
        servers.refuse_busy_port(self.reg, spec)
        servers.launch(spec, self.command(spec), lambda: self.info(spec), a.timeout)
        print(f"{spec.name} ready on {self.url(spec)}")

    def stop(self, a):
        servers.stop(self.reg.get(a.name).name)

    def port(self, a):
        spec = self.reg.get(a.name)
        if servers.pid_of(spec.name) or self.info(spec):
            sys.exit(f"stop {spec.name} before changing its port")
        self.reg.set_port(spec.name, a.port)
        print(f"{spec.name} now uses port {a.port}")
