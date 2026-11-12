<div align="center">

# local-models

Run decision models and LLMs locally on an Apple Silicon Mac, and use them from Claude Code, the command line, HTTP, or a Mac app.

![macOS](https://img.shields.io/badge/macOS-14%2B%20Apple%20Silicon-black) ![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue) ![License](https://img.shields.io/badge/license-MIT-green)

</div>

- **Decision models** return calibrated probabilities instead of text: yes/no, choice, and score questions
- **LLMs** draft, translate, summarize, or give a second opinion, with text and image input
- One model per kind runs at a time; servers listen only on `127.0.0.1` and have no authentication

| Decision model | Memory | Notes |
|---|---|---|
| [Kanana-2-V-Decide-3B](https://huggingface.co/kakaocorp/kanana-2-v-decide-3b-2611) | 10 GB | Default. Most accurate on Korean. Own license |
| [pplx-decider-flash v1.2](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2) | 15 GB | Best calibrated. Apache-2.0 |

| LLM | Memory | Notes |
|---|---|---|
| [Gemma 4 26B-A4B](https://huggingface.co/mlx-community/gemma-4-26B-A4B-it-qat-4bit) | 21 GB | Fast (MoE), good at prose |
| [Qwen3.6-35B-A3B](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4) | 23 GB | Faster than Qwen3.8 (MoE) |
| [Qwen3.8-27B](https://huggingface.co/mlx-community/Qwen3.8-27B-mxfp4) | 23 GB | Default |

Memory is the measured peak, with a long prompt for the LLMs.

## Install

You need [uv](https://docs.astral.sh/uv/). Weights go to `weight/`.

```bash
git clone https://github.com/phykn/local-models.git && cd local-models
uv sync --python 3.13
.venv/bin/decisionctl pull kanana-2-v-decide-3b
.venv/bin/llmctl pull qwen3.8-27b
```

## Use

**Mac app**: pick a model, press Start. The app stops the models it started when it quits.

```bash
scripts/build-app.sh && open LOCAL-MODELS.app
```

**Claude Code**: register the MCP servers, then ask something like "Use decision to decide whether this ticket is urgent".

```bash
claude mcp add decision --scope user -- "$PWD/.venv/bin/decision-mcp"
claude mcp add llm-local --scope user -- "$PWD/.venv/bin/llm-mcp"
```

- `decision` provides `choose`, `yes_no`, `score`, `decide`, and `list_models`. Check answers marked `low_confidence` yourself.
- `llm-local` provides `ask` and `list_models`. Pass `think: true` to `ask` for harder problems.

**Command line**: `decisionctl` and `llmctl` take `list`, `status`, `pull`, `start`, `stop`, and `port`.

```bash
.venv/bin/decisionctl start kanana-2-v-decide-3b
.venv/bin/decisionctl port 8091   # every decision model; stop it first
```

**HTTP**

- Decision models serve `POST /v1/systemone` on port 8081: `{"state": text, "questions": {id: question}}`, with questions shaped as in the `decide` tool.
- LLMs serve an OpenAI-compatible API at `/v1/chat/completions` on port 8082. Set `model` to the id from `/v1/models`, and send `"enable_thinking": false` to turn thinking off.

## Configure

Models and the port of each kind are in `decision.toml` and `llm.toml`. Pin `run` to a commit. Unknown keys are an error.

## Test

```bash
.venv/bin/pytest            # fake servers, a few seconds
.venv/bin/pytest -m live    # the models that are running
```

## License

MIT. Qwen, Gemma 4, and pplx-decider are Apache-2.0. Kanana-2-V-Decide is under the Kanana Open License: some uses need a separate commercial license from Kakao, and services built on it must show "Powered by Kanana". Read its LICENSE before use.
