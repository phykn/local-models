# local-models

Run decision models and LLMs locally on an Apple Silicon Mac with [MLX](https://github.com/ml-explore/mlx). Use them from Claude Code over MCP, the command line, HTTP, or a Mac app.

Servers listen only on `127.0.0.1` and have no authentication.

## Models

**Decision models** return calibrated probabilities instead of generated text. They answer yes/no, choice, and score questions. The [Kev](https://github.com/jaredpalmer/kev) format is used.

| Model | Memory | Notes |
|---|---|---|
| [Kev-4B](https://huggingface.co/jaredpalmer/kev-4b) | 16 GB | Default |
| [Kev-0.8B](https://huggingface.co/jaredpalmer/kev-0.8b) | 3 GB | Smallest |
| [Malkuth-2B](https://huggingface.co/dhtocks/malkuth-2b) | 7 GB | Fewest high-confidence errors on Korean. Non-commercial |

**LLMs** are for drafting, translating, summarizing, or getting a second opinion. They accept text and image input.

| Model | Memory | Notes |
|---|---|---|
| [Qwen3.8-27B](https://huggingface.co/mlx-community/Qwen3.8-27B-mxfp4) | 23 GB | Default |
| [Qwen3.6-35B-A3B](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4) | 23 GB | Faster (MoE) |
| [MiniCPM-V 4.7 35B-A3B](https://huggingface.co/mlx-community/MiniCPM-V-4.7-35B-A3B-mxfp4) | 25 GB | Strong with images. Up to an ~8k-token prompt on 32 GB |
| [Ternary Bonsai 2 27B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit) | 22 GB | Smallest weights. Up to a ~16k-token prompt on 32 GB |

Memory is the measured peak, with a long prompt for the LLMs. Each section runs one model at a time.

## Install

You need an Apple Silicon Mac and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/phykn/local-models.git && cd local-models
git clone https://github.com/jaredpalmer/kev.git vendor/kev && git -C vendor/kev checkout kev-1.0
uv sync --python 3.13
.venv/bin/llmctl pull qwen3.8-27b                 # weights go to weight/
HF_HUB_OFFLINE=0 .venv/bin/kevctl start kev-4b    # the first start downloads the model
```

## Use

**Mac app**

```bash
scripts/build-app.sh && open LOCAL-MODELS.app
```

**Claude Code**: register the MCP servers, then ask something like "Use kev to decide whether this ticket is urgent".

```bash
claude mcp add kev --scope user -- "$PWD/.venv/bin/kev-mcp"
claude mcp add llm-local --scope user -- "$PWD/.venv/bin/llm-mcp"
```

- `kev` provides `choose`, `yes_no`, `score`, `decide`, and `list_models`. Check answers marked `low_confidence` yourself.
- `llm-local` provides `ask` and `list_models`. Pass `think: true` to `ask` for harder problems.

**Command line**: `kevctl` and `llmctl` take the same commands: `start`, `stop`, `status`, `list`, and `port`.

```bash
.venv/bin/kevctl start kev-4b
```

**HTTP**

- LLMs serve an OpenAI-compatible API at `/v1/chat/completions` on port 8082. Set `model` to the id from `/v1/models`. Send `"enable_thinking": false` to turn thinking off.
- Decision models serve `POST /v1/systemone` on port 8081. See the [Kev README](https://github.com/jaredpalmer/kev) for the request format.

## Configure

Models are registered in `kev.toml` and `llm.toml`. Each entry sets the weights, port, memory, and sampling. Pin `run` to a commit. Unknown keys are an error.

## Test

```bash
.venv/bin/pytest                                                   # fake servers
.venv/bin/pytest -m live                                           # running models
.venv/bin/python scripts/evaluate.py --data evals/ko/smoke.jsonl   # accuracy and calibration
```

## License

This project is MIT licensed. Kev, Qwen, MiniCPM-V, and Bonsai are Apache-2.0. Malkuth-2B is CC BY-NC 4.0, which allows non-commercial use only.
