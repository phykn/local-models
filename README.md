# local-models

Run local models on an Apple Silicon Mac with [MLX](https://github.com/ml-explore/mlx), use them from Claude Code over MCP, and start or stop them from a Mac app.

- **Kev** ([jaredpalmer/kev](https://github.com/jaredpalmer/kev)): decision models that return a calibrated answer, not generated text (`choose`, `yes_no`, `score`).
- **LLM**: [Qwen3.8-27B](https://huggingface.co/mlx-community/Qwen3.8-27B-mxfp4) and the faster [Qwen3.6-35B-A3B](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4) (4-bit mxfp4) for drafting, translating, summarizing or a second opinion.

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

Memory: Kev-4B ~16 GB, Kev-0.8B ~4 GB, Qwen3.8-27B ~21 GB, Qwen3.6-35B-A3B ~22 GB.

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

`kev.toml` and `llm.toml` register the models (weights, port, memory, sampling). Pin `run` to a commit; unknown keys are an error.

## Test

```bash
.venv/bin/pytest                                                   # fake servers
.venv/bin/pytest -m live                                           # running models
.venv/bin/python scripts/evaluate.py --data evals/ko/smoke.jsonl   # Kev accuracy and calibration
```

## License

MIT. Kev, its weights and the Qwen weights are Apache-2.0.
