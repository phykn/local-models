# local-models

Run local models on an Apple Silicon Mac with [MLX](https://github.com/ml-explore/mlx), call them from Claude Code through MCP, and start and stop them from one Mac app.

- **Kev** ([jaredpalmer/kev](https://github.com/jaredpalmer/kev)): decision models. Given a text and a question, Kev returns a calibrated answer instead of generated text: `choose` picks one of several options, `yes_no` answers a yes/no question and `score` places the text on an ordered scale.
- **LLM**: [Qwen3.8-27B](https://huggingface.co/mlx-community/Qwen3.8-27B-mxfp4) and the faster, weaker [Qwen3.6-35B-A3B](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-mxfp4), both 4-bit mxfp4. Use them for drafting, rewriting, translating, summarizing or a second opinion, through MCP or an OpenAI-compatible API.

Both run in one Python environment. Servers listen only on `127.0.0.1`. Nothing is exposed to the network, and there is no authentication.

## Install

You need an Apple Silicon Mac and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/phykn/local-models.git && cd local-models
git clone https://github.com/jaredpalmer/kev.git vendor/kev && git -C vendor/kev checkout kev-1.0
uv sync --python 3.13
.venv/bin/llmctl pull qwen3.8-27b        # downloads the weights into weight/ once
.venv/bin/llmctl pull qwen3.6-35b-a3b    # optional
HF_HUB_OFFLINE=0 .venv/bin/kevctl start kev-4b   # the first start downloads Kev's weights
```

Memory while running: Kev-4B about 16 GB, Kev-0.8B about 4 GB, Qwen3.8-27B about 21 GB, Qwen3.6-35B-A3B about 22 GB. Check that what you run together fits.

## Mac app

```bash
scripts/build-app.sh
open LOCAL-MODELS.app
```

The window has one section for Kev and one for the LLMs. Each section runs one model at a time, and the two sections are independent, so you can run either one or both.

- Pick a model, then press **Start**. Once the model answers, its row turns green and the address appears under the list, with a button to copy it.
- The picked model's port (`:8081`) sits in a small field. Click it, type a new port and press Return to save it to `kev.toml` or `llm.toml`; Escape cancels. Ports can change only while nothing in that section runs.
- A model's memory turns orange when it needs more than is free, and starting it then asks first. The bar at the bottom fills with the memory in use, turning orange and then red as it runs out.
- When a start fails, the section says why and **Show Log** opens the model's log in `logs/`.
- Quitting the app, even with Force Quit, stops the models it started. A model started from the command line keeps running; one started from another checkout shows as "Running, not started here" and can only be stopped there.

## Claude Code

```bash
claude mcp add kev --scope user -- "$PWD/.venv/bin/kev-mcp"
claude mcp add llm-local --scope user -- "$PWD/.venv/bin/llm-mcp"
```

Start a new Claude Code session and ask, for example: "Use kev to decide whether this ticket is urgent: ..." or "Use llm-local to translate this paragraph into Korean: ...".

- **kev**: `choose`, `yes_no`, `score`, `decide` (several questions about one text) and `list_models`. Every answer includes a `confidence`. When `low_confidence` is true, check the answer before acting on it.
- **llm-local**: `ask` sends a prompt (and an optional system prompt) and returns the answer text. Thinking is off by default; pass `think: true` for harder problems. It is slower, and the reasoning itself is not returned. `list_models` shows what is running.

The MCP servers reread `kev.toml` and `llm.toml` on every call, so a port changed in the app takes effect without restarting them.

## Command line

`kevctl` and `llmctl` take the same commands:

```bash
.venv/bin/kevctl start kev-4b        # waits until the model answers
.venv/bin/kevctl stop kev-4b
.venv/bin/kevctl status              # what is running; --json for scripts
.venv/bin/kevctl list                # the registered models; --json for scripts
.venv/bin/kevctl port kev-4b 8083    # while the model is stopped
```

`llmctl pull <model>` downloads an LLM. Nothing else downloads weights: everything uses only what is already in `weight/`.

## HTTP API

The LLMs serve an OpenAI-compatible API. With mlx-vlm, `model` must be the id of the loaded model: the entry with `"loaded": true` in `curl -s http://127.0.0.1:8082/v1/models` (its snapshot path under `weight/`).

```bash
curl http://127.0.0.1:8082/v1/chat/completions -H 'content-type: application/json' -d '{
  "model": "<id of the loaded model>",
  "messages": [{"role": "user", "content": "Hello"}],
  "enable_thinking": false,
  "max_tokens": 256
}'
```

Qwen thinks before answering by default. Send `"enable_thinking": false` (mlx-vlm) or `"chat_template_kwargs": {"enable_thinking": false}` (mlx-lm) to turn it off.

Kev serves `POST /v1/systemone` on its port; see the [Kev README](https://github.com/jaredpalmer/kev) for the request format.

## Models

`kev.toml` and `llm.toml` list the models. The ctl, the MCP server and the app read them.

```toml
# kev.toml
[models."my-4b"]
backend = "kev-http"
run = "checkpoints/my-4b"   # local checkpoint directory, or a Hugging Face id@revision
port = 8081                 # models may share a port; only one of them can run at a time
memory_gb = 16
min_confidence = 0.5        # answers below this confidence are marked low_confidence

# llm.toml
[models."qwen3.8-27b"]
server = "mlx-vlm"          # mlx-vlm or mlx-lm
run = "mlx-community/Qwen3.8-27B-mxfp4@97ab0819817ab1c61d7d39f9169fc71999915641"   # Hugging Face id@commit, or a local directory
port = 8082
memory_gb = 21              # llmctl warns when less memory than this is free
max_kv_size = 32768         # context limit in tokens (mlx-vlm only)
think = { temperature = 1.0, top_p = 0.95, top_k = 20 }
nothink = { temperature = 0.7, top_p = 0.8, top_k = 20, presence_penalty = 1.5 }
```

Pin `run` to a commit so the weights do not change under you. A key that is not listed above is an error, so a typo cannot silently fall back to a default.

## Versions

One environment serves both. Kev's MLX backend needs `mlx-lm` below 0.32, which the LLM side does not use (`mlx-vlm` serves Qwen), and `mlx-vlm` 0.7.8 needs `mlx` 0.32.3 or later. Kev was released on `mlx` 0.32.2, and on 0.32.4 its probabilities differ from the release by at most about 0.02.

## Layout

- `src/local_models/kev/` and `src/local_models/llm/`: each has `registry.py` (its model spec and `.toml`), `backends.py` (calls a running server), `ctl.py` (`kevctl` / `llmctl`) and `mcp_server.py` (`kev-mcp` / `llm-mcp`).
- `src/local_models/registry.py`: what `kev.toml` and `llm.toml` share: loading, the default model, and rewriting a port in place.
- `src/local_models/servers.py`: the server processes both ctls run: pid files and logs in `logs/`, starting and waiting until the model answers, stopping, and the `list --json` / `status --json` rows the app reads.
- `app/Sources/`: the Mac app in Swift. It knows nothing about Kev or Qwen; it runs `list --json`, `status --json`, `start`, `stop` and `port` on each ctl (`Ctl.swift`). `Section.swift` is one ctl's part of the window, `ModelRow.swift` one model in it. `app/icon.swift` draws the icon at build time.
- `vendor/kev`: the Kev checkout. `weight/`: downloaded weights (`HF_HOME`). `logs/`: server logs and pid files.

## Evaluate and test

```bash
.venv/bin/python scripts/evaluate.py --data evals/ko/smoke.jsonl   # Kev: accuracy, Brier score, coverage at 5% error
.venv/bin/pytest                                                   # uses fake servers
.venv/bin/pytest -m live                                           # against running models
```

`scripts/evaluate.py` runs every Kev model that is currently running.

## License

MIT. Kev and its weights are licensed under Apache-2.0, and the Qwen weights under Apache-2.0, separately.
