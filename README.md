# local-models

Run local models on an Apple Silicon Mac with [MLX](https://github.com/ml-explore/mlx), use them from Claude Code over MCP, and start or stop them from a Mac app.

- **Kev** ([jaredpalmer/kev](https://github.com/jaredpalmer/kev)): decision models that return a calibrated answer, not generated text (`choose`, `yes_no`, `score`). Kev-4B and Kev-0.8B, plus two Kev-style models: [Malkuth-2B](https://huggingface.co/dhtocks/malkuth-2b), the best calibrated on Korean, and [Jev-Style-0.8B](https://huggingface.co/chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX), which is small and accepts states up to 25.6k tokens.
- **LLM**: [Qwen3.8-27B](https://huggingface.co/mlx-community/Qwen3.8-27B-mxfp4), the faster [Qwen3.6-35B-A3B](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4), [MiniCPM-V 4.7 35B-A3B](https://huggingface.co/mlx-community/MiniCPM-V-4.7-35B-A3B-mxfp4) for images, and [Ternary Bonsai 2 27B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit) with the smallest weights. Use them for drafting, translating, summarizing or a second opinion.

Servers listen only on `127.0.0.1`, with no authentication.

## Install

Requires an Apple Silicon Mac and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/phykn/local-models.git && cd local-models
git clone https://github.com/jaredpalmer/kev.git vendor/kev && git -C vendor/kev checkout kev-1.0
uv sync --python 3.13
.venv/bin/llmctl pull qwen3.8-27b                 # weights go to weight/
HF_HUB_OFFLINE=0 .venv/bin/kevctl start kev-4b    # first start downloads Kev
```

Measured peak memory: Kev-4B 16 GB, Kev-0.8B 3 GB, Malkuth-2B 7 GB, Jev-Style-0.8B 8 GB (long state); Qwen3.8-27B and Qwen3.6-35B-A3B 23 GB each (28k-token prompt), MiniCPM-V 25 GB and Bonsai 2 22 GB. On a 32 GB Mac, MiniCPM-V runs out of memory above an ~8k-token prompt and Bonsai above ~16k. The first MiniCPM-V request after a start takes about a minute.

## Use

**Mac app** — one section for Kev, one for the LLMs; each runs one model at a time.

```bash
scripts/build-app.sh && open LOCAL-MODELS.app
```

**Claude Code** — register the MCP servers, then ask e.g. "Use kev to decide whether this ticket is urgent".

```bash
claude mcp add kev --scope user -- "$PWD/.venv/bin/kev-mcp"
claude mcp add llm-local --scope user -- "$PWD/.venv/bin/llm-mcp"
```

- `kev`: `choose`, `yes_no`, `score`, `decide`, `list_models`. Check answers marked `low_confidence`.
- `llm-local`: `ask` (pass `think: true` for harder problems), `list_models`.

**Command line** — `kevctl` and `llmctl` share the same commands.

```bash
.venv/bin/kevctl start kev-4b      # also: stop, status, list, port <model> <port>
```

**HTTP** — the LLMs serve an OpenAI-compatible API (`/v1/chat/completions`, default port 8082). Set `model` to the loaded id from `/v1/models` and send `"enable_thinking": false` to skip thinking. Kev serves `POST /v1/systemone` (see the [Kev README](https://github.com/jaredpalmer/kev)).

## Configure

`kev.toml` and `llm.toml` register the models (weights, port, memory, sampling). Pin `run` to a commit; unknown keys are an error. In `kev.toml`, `backend = "kev-http"` runs `kev.serve`, and `backend = "jev-style"` runs `local_models.kev.jev_style`, which serves the same `/v1/systemone` API with the runtime shipped in a Jev-Style MLX repository.

## Test

```bash
.venv/bin/pytest                                                   # fake servers
.venv/bin/pytest -m live                                           # running models
.venv/bin/python scripts/evaluate.py --data evals/ko/smoke.jsonl   # Kev accuracy and calibration
```

## License

MIT. Kev, its weights, Jev-Style, and the Qwen, MiniCPM-V and Bonsai weights are Apache-2.0. Malkuth-2B is CC BY-NC 4.0 (non-commercial only).
