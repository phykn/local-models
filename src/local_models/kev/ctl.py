import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .. import common
from ..common import ROOT, WEIGHTS, pid_of
from .backends import make_backend
from .registry import load_registry

KEV_SRC = ROOT / "vendor" / "kev"


def info_of(spec):
    return asyncio.run(make_backend(spec).info())


def mem_budget_gb():
    total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) / 2**30
    return total * 0.75   # leave a quarter of unified memory to macOS and everything else


def models(reg, a):
    # LOCAL-MODELS.app reads this; llmctl list --json has the same shape
    ms = [{"name": s.name, "port": s.port, "memory_gb": s.memory_gb, "default": s.name == reg.default, "note": None, "missing": False}
          for s in reg.models.values() if s.backend == "kev-http"]
    print(json.dumps(ms) if a.json else "\n".join(f"{m['name']:<14} :{m['port']}  {m['memory_gb']:.0f} GB" for m in ms))


def status(reg, a):
    rows = []
    for spec in reg.models.values():
        info = info_of(spec) if spec.backend == "kev-http" else None
        pid = pid_of(spec.name)
        rows.append({"name": spec.name, "state": common.state(info, pid), "url": f"http://127.0.0.1:{spec.port}"})
        if not a.json:
            detail = f"{info['backend']} {info['dtype']}" if info else ""
            default = " (default)" if spec.name == reg.default else ""
            print(f"{spec.name:<14} {rows[-1]['state']:<9} :{spec.port}  pid={pid or '-':<7} {detail}  {spec.run}{default}")
    if a.json:
        print(json.dumps(rows))


def start(reg, a):
    spec = reg.get(a.name)
    if spec.backend != "kev-http":
        sys.exit(f"{spec.name} uses backend {spec.backend!r}; kevctl only manages kev-http models")
    if info_of(spec):
        print(f"{spec.name} is already running on :{spec.port}")
        return
    if pid := pid_of(spec.name):
        # a second kev.serve on the same port would fail and orphan the first one's pid file
        print(f"{spec.name} is still starting (pid {pid}); see {common.LOGS / f'{spec.name}.log'}")
        return
    common.refuse_busy_port(reg, spec)
    from kev.checkpoint import is_hub_id   # imports torch; only start needs it

    run = reg.resolve_run(spec)
    if "@" not in run and not (reg.path.parent / run).exists():
        # a missing local path like checkpoints/x also matches the Hub id pattern, and kev.serve would try to download it
        sys.exit(f"{reg.path.parent / run} does not exist; a Hub model needs id@revision in kev.toml")
    if not is_hub_id(run) and not Path(run, "head.pt").exists():
        # kev.serve silently falls back to runs/smoke when --run has no head.pt
        sys.exit(f"{run} has no head.pt; is the checkpoint path in kev.toml right?")
    running = [s for s in reg.models.values() if s.name != spec.name and pid_of(s.name)]
    need = spec.memory_gb + sum(s.memory_gb for s in running)
    if need > mem_budget_gb():
        print(f"warning: {need:.0f} GB with {', '.join(s.name for s in running)} running, budget {mem_budget_gb():.0f} GB")
    common.LOGS.mkdir(exist_ok=True)
    log = open(common.LOGS / f"{spec.name}.log", "ab")
    cmd = [sys.executable, "-m", "kev.serve", "--run", run, "--port", str(spec.port)]
    p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
    (common.LOGS / f"{spec.name}.pid").write_text(str(p.pid))
    print(f"starting {spec.name} (pid {p.pid}), log: {common.LOGS / f'{spec.name}.log'}")
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        if p.poll() is not None:
            (common.LOGS / f"{spec.name}.pid").unlink(missing_ok=True)
            tail = (common.LOGS / f"{spec.name}.log").read_text(errors="replace").splitlines()[-20:]
            sys.exit(f"{spec.name} exited with {p.returncode}:\n" + "\n".join(tail))
        if info := info_of(spec):
            print(f"{spec.name} ready on :{spec.port} ({info['backend']} {info['dtype']})")
            return
        time.sleep(2)
    sys.exit(f"{spec.name} did not answer within {a.timeout}s; it is still starting, see the log")


def stop(reg, a):
    common.stop(reg.get(a.name).name)


def port(reg, a):
    spec = reg.get(a.name)
    if pid_of(spec.name) or info_of(spec):
        sys.exit(f"stop {spec.name} before changing its port")
    common.set_port(reg, spec.name, a.port, load_registry)


def merge(reg, a):
    spec = reg.get(a.name)
    out = ROOT / "checkpoints" / f"{spec.name}-merged"
    cmd = [sys.executable, "scripts/merge_lora_checkpoint.py", "--lora", reg.resolve_run(spec), "--out", str(out), "--weights_dtype", "bf16"]
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
    a.fn(load_registry(a.registry), a)


if __name__ == "__main__":
    main()
