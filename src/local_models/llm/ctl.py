import argparse
import asyncio
import json
import os
import sys
import time

import httpx

from .. import WEIGHTS, servers
from ..registry import RegistryError
from .backends import OpenAIBackend
from .registry import load_registry


def info_of(spec):
    return asyncio.run(OpenAIBackend(spec).info())


def command(spec, model):
    host = ["--host", "127.0.0.1", "--port", str(spec.port)]   # mlx-vlm listens on 0.0.0.0 unless told otherwise
    if spec.server == "mlx-lm":
        return [sys.executable, "-m", "mlx_lm", "server", "--model", str(model), *host]
    cmd = [sys.executable, "-m", "mlx_vlm.server", "--model", str(model), *host]
    if spec.max_kv_size:
        cmd += ["--max-kv-size", str(spec.max_kv_size)]
    return cmd


def models(reg, a):
    rows, w = [], max(map(len, reg.models))
    for s in reg.models.values():
        quant = reg.quantization(s)
        rows.append(servers.list_row(reg, s, note=quant or "not downloaded", missing=quant is None))
    print(json.dumps(rows) if a.json else "\n".join(f"{r['name']:<{w}} :{r['port']}  {r['memory_gb']:.0f} GB  {r['note']}" for r in rows))


def status(reg, a):
    rows, w = [], max(map(len, reg.models))
    for spec in reg.models.values():
        info, pid = info_of(spec), servers.pid_of(spec.name)
        rows.append(servers.status_row(spec, info, pid, f"http://127.0.0.1:{spec.port}/v1"))
        if not a.json:
            default = " (default)" if spec.name == reg.default else ""
            quant = reg.quantization(spec) or "not downloaded"
            print(f"{spec.name:<{w}} {rows[-1]['state']:<9} :{spec.port}  pid={pid or '-':<7} {quant:<14} {spec.server}  {spec.run}{default}")
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
    if pid := servers.pid_of(spec.name):
        # a second server on the same port would fail and orphan the first one's pid file
        print(f"{spec.name} is already running or starting (pid {pid}); see {servers.LOGS / f'{spec.name}.log'}")
        return
    if info_of(spec):
        sys.exit(f"another process is already serving {spec.name} on :{spec.port}")
    servers.refuse_busy_port(reg, spec)
    if not (model := reg.resolve(spec)):
        sys.exit(f"{spec.name} is not downloaded; run: llmctl pull {spec.name}")
    deadline = time.time() + a.timeout
    servers.launch(spec, command(spec, model), lambda: info_of(spec), a.timeout)
    if spec.server == "mlx-lm":
        # mlx-lm loads the model on the first request; load it now so "ready" means ready
        httpx.post(f"http://127.0.0.1:{spec.port}/v1/chat/completions", timeout=max(deadline - time.time(), 1),
                   json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}).raise_for_status()
    print(f"{spec.name} ready on http://127.0.0.1:{spec.port}/v1")


def stop(reg, a):
    servers.stop(reg.get(a.name).name)


def port(reg, a):
    spec = reg.get(a.name)
    if servers.pid_of(spec.name) or info_of(spec):
        sys.exit(f"stop {spec.name} before changing its port")
    reg.set_port(spec.name, a.port)
    print(f"{spec.name} now uses port {a.port}")


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
    try:
        a.fn(load_registry(a.registry), a)
    except RegistryError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
