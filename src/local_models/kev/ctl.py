import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from .. import ROOT, WEIGHTS, servers
from ..registry import RegistryError
from .backends import KevHttpBackend
from .registry import load_registry

KEV_SRC = ROOT / "vendor" / "kev"


def info_of(spec):
    return asyncio.run(KevHttpBackend(spec).info())


def models(reg, a):
    rows = [servers.list_row(reg, s) for s in reg.models.values()]
    w = max(map(len, reg.models))
    print(json.dumps(rows) if a.json else "\n".join(f"{r['name']:<{w}} :{r['port']}  {r['memory_gb']:.0f} GB" for r in rows))


def status(reg, a):
    rows, w = [], max(map(len, reg.models))
    for spec in reg.models.values():
        info, pid = info_of(spec), servers.pid_of(spec.name)
        rows.append(servers.status_row(spec, info, pid, f"http://127.0.0.1:{spec.port}"))
        if not a.json:
            detail = f"{info['backend']} {info['dtype']}" if info else ""
            default = " (default)" if spec.name == reg.default else ""
            print(f"{spec.name:<{w}} {rows[-1]['state']:<9} :{spec.port}  pid={pid or '-':<7} {detail}  {spec.run}{default}")
    if a.json:
        print(json.dumps(rows))


def start(reg, a):
    spec = reg.get(a.name)
    if info_of(spec):
        print(f"{spec.name} is already running on :{spec.port}")
        return
    if pid := servers.pid_of(spec.name):
        # a second kev.serve on the same port would fail and orphan the first one's pid file
        print(f"{spec.name} is still starting (pid {pid}); see {servers.LOGS / f'{spec.name}.log'}")
        return
    servers.refuse_busy_port(reg, spec)
    from kev.checkpoint import is_hub_id   # imports torch; only start needs it

    run = reg.resolve(spec)
    if "@" not in run and not (reg.path.parent / run).exists():
        # a missing local path like checkpoints/x also matches the Hub id pattern, and kev.serve would try to download it
        sys.exit(f"{reg.path.parent / run} does not exist; a Hub model needs id@revision in kev.toml")
    if not is_hub_id(run) and not Path(run, "head.pt").exists():
        # kev.serve silently falls back to runs/smoke when --run has no head.pt
        sys.exit(f"{run} has no head.pt; is the checkpoint path in kev.toml right?")
    cmd = [sys.executable, "-m", "kev.serve", "--run", run, "--port", str(spec.port)]
    info = servers.launch(spec, cmd, lambda: info_of(spec), a.timeout)
    print(f"{spec.name} ready on :{spec.port} ({info['backend']} {info['dtype']})")


def stop(reg, a):
    servers.stop(reg.get(a.name).name)


def port(reg, a):
    spec = reg.get(a.name)
    if servers.pid_of(spec.name) or info_of(spec):
        sys.exit(f"stop {spec.name} before changing its port")
    reg.set_port(spec.name, a.port)
    print(f"{spec.name} now uses port {a.port}")


def merge(reg, a):
    spec = reg.get(a.name)
    out = ROOT / "checkpoints" / f"{spec.name}-merged"
    cmd = [sys.executable, "scripts/merge_lora_checkpoint.py", "--lora", reg.resolve(spec), "--out", str(out), "--weights_dtype", "bf16"]
    subprocess.run(cmd, cwd=KEV_SRC, check=True)   # the script imports scripts.interpolate_checkpoint from the kev checkout
    print(f"merged into {out / 'checkpoint'}; set run = \"{(out / 'checkpoint').relative_to(ROOT)}\" in kev.toml to use it")


def main():
    ap = argparse.ArgumentParser(prog="kevctl")
    ap.add_argument("--registry", help="kev.toml (default: KEV_MCP_REGISTRY or the project's)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=models)
    p = sub.add_parser("status"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=status)
    p = sub.add_parser("start"); p.add_argument("name"); p.add_argument("--timeout", type=int, default=3600); p.set_defaults(fn=start)
    p = sub.add_parser("stop"); p.add_argument("name"); p.set_defaults(fn=stop)
    p = sub.add_parser("port"); p.add_argument("name"); p.add_argument("port", type=int); p.set_defaults(fn=port)
    p = sub.add_parser("merge"); p.add_argument("name"); p.set_defaults(fn=merge)
    a = ap.parse_args()
    os.environ.setdefault("HF_HOME", str(WEIGHTS))   # inherited by kev.serve and the merge script
    os.environ.setdefault("HF_HUB_OFFLINE", "1")     # use only weights already in HF_HOME; HF_HUB_OFFLINE=0 allows downloading
    try:
        a.fn(load_registry(a.registry), a)
    except RegistryError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
