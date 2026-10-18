import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time

import httpx

from .. import common
from ..common import ROOT, WEIGHTS, pid_of
from .backends import OpenAIBackend
from .registry import load_registry


def info_of(spec):
    return asyncio.run(OpenAIBackend(spec).info())


def free_gb():
    # pages macOS can hand out without swapping; counts whatever else is running, Kev models included
    s = subprocess.check_output(["vm_stat"], text=True)
    page = int(re.search(r"page size of (\d+)", s)[1])
    pages = sum(int(re.search(rf"{k}:\s+(\d+)", s)[1]) for k in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"))
    return pages * page / 2**30


def command(spec, model):
    host = ["--host", "127.0.0.1", "--port", str(spec.port)]   # mlx-vlm listens on 0.0.0.0 unless told otherwise
    if spec.server == "mlx-lm":
        return [sys.executable, "-m", "mlx_lm", "server", "--model", str(model), *host]
    cmd = [sys.executable, "-m", "mlx_vlm.server", "--model", str(model), *host]
    if spec.max_kv_size:
        cmd += ["--max-kv-size", str(spec.max_kv_size)]
    return cmd


def models(reg, a):
    # LOCAL-MODELS.app reads this; kevctl list --json has the same shape. note is the weights' quantization
    ms = []
    for s in reg.models.values():
        quant = reg.quantization(s)
        ms.append({"name": s.name, "port": s.port, "memory_gb": s.memory_gb, "default": s.name == reg.default,
                   "note": quant or "not downloaded", "missing": quant is None})
    print(json.dumps(ms) if a.json else "\n".join(f"{m['name']:<16} :{m['port']}  {m['memory_gb']:.0f} GB  {m['note']}" for m in ms))


def status(reg, a):
    rows = []
    for spec in reg.models.values():
        info = info_of(spec)
        pid = pid_of(spec.name)
        rows.append({"name": spec.name, "state": common.state(info, pid), "url": f"http://127.0.0.1:{spec.port}/v1"})
        if not a.json:
            default = " (default)" if spec.name == reg.default else ""
            quant = reg.quantization(spec) or "not downloaded"
            print(f"{spec.name:<16} {rows[-1]['state']:<9} :{spec.port}  pid={pid or '-':<7} {quant:<14} {spec.server}  {spec.run}{default}")
    if a.json:
        print(json.dumps(rows))


def pull(reg, a):
    from huggingface_hub import snapshot_download

    spec = reg.get(a.name)
    if "@" not in spec.run:
        print(f"{spec.run} is a local directory; nothing to download")
        return
    repo, rev = spec.run.split("@", 1)
    print(f"{repo}@{rev[:10]} -> {snapshot_download(repo, revision=rev)}")


def start(reg, a):
    spec = reg.get(a.name)
    if pid := pid_of(spec.name):
        # a second server on the same port would fail and orphan the first one's pid file
        print(f"{spec.name} is already running or starting (pid {pid}); see {common.LOGS / f'{spec.name}.log'}")
        return
    if info_of(spec):
        sys.exit(f"another process is already serving {spec.name} on :{spec.port}")
    common.refuse_busy_port(reg, spec)
    if not (model := reg.resolve(spec.run)):
        sys.exit(f"{spec.name} is not downloaded; run: llmctl pull {spec.name}")
    if spec.memory_gb > (free := free_gb()):
        print(f"warning: {spec.name} needs about {spec.memory_gb:.0f} GB and {free:.0f} GB is free; other apps or models may be swapped out")
    common.LOGS.mkdir(exist_ok=True)
    log = open(common.LOGS / f"{spec.name}.log", "ab")
    p = subprocess.Popen(command(spec, model), stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
    (common.LOGS / f"{spec.name}.pid").write_text(str(p.pid))
    print(f"starting {spec.name} (pid {p.pid}), log: {common.LOGS / f'{spec.name}.log'}")
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        if p.poll() is not None:
            (common.LOGS / f"{spec.name}.pid").unlink(missing_ok=True)
            tail = (common.LOGS / f"{spec.name}.log").read_text(errors="replace").splitlines()[-20:]
            sys.exit(f"{spec.name} exited with {p.returncode}:\n" + "\n".join(tail))
        if info_of(spec):
            if spec.server == "mlx-lm":
                # mlx-lm loads the model on the first request; load it now so "ready" means ready
                httpx.post(f"http://127.0.0.1:{spec.port}/v1/chat/completions", timeout=max(deadline - time.time(), 1),
                           json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}).raise_for_status()
            print(f"{spec.name} ready on http://127.0.0.1:{spec.port}/v1")
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


def main():
    ap = argparse.ArgumentParser(prog="llmctl")
    ap.add_argument("--registry", help="llm.toml (default: LLM_LOCAL_REGISTRY or the project's)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=models)
    p = sub.add_parser("status"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=status)
    p = sub.add_parser("pull"); p.add_argument("name"); p.set_defaults(fn=pull)
    p = sub.add_parser("start"); p.add_argument("name"); p.add_argument("--timeout", type=int, default=1800); p.set_defaults(fn=start)
    p = sub.add_parser("stop"); p.add_argument("name"); p.set_defaults(fn=stop)
    p = sub.add_parser("port"); p.add_argument("name"); p.add_argument("port", type=int); p.set_defaults(fn=port)
    a = ap.parse_args()
    os.environ.setdefault("HF_HOME", str(WEIGHTS))   # inherited by the server
    # only pull downloads; everything else, the server included, uses weights already in weight/
    os.environ["HF_HUB_OFFLINE"] = "0" if a.cmd == "pull" else os.environ.get("HF_HUB_OFFLINE", "1")
    a.fn(load_registry(a.registry), a)


if __name__ == "__main__":
    main()
