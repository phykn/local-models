# local-models

- Plan: `docs/groove/PLAN.md` (not in git). A session continuing the build uses groove to do the first unchecked task.
- `src/local_models/registry.py`: loads `decision.toml` / `llm.toml` strictly (`run` is `repo@revision`), reloads, rewrites one port line.
- `src/local_models/servers.py`: pid files under `logs/`, launch and wait, stop, busy-port and free-memory checks.
- `src/local_models/ctl.py`: `Ctl`, the shared `list`/`status`/`start`/`stop`/`port` CLI. Its `--json` rows are what `app/Sources/Ctl.swift` decodes; change both together.
- `src/local_models/decision/`: `ctl.py` (the `systemone.py` command), `backends.py` (HTTP client, answer normalizing), `mcp_server.py`, `systemone.py` (Kanana and pplx-decider runtimes behind `POST /v1/systemone`; `GET /v1/info` names the model it serves).
- `src/local_models/llm/`: `ctl.py` (weights check, mlx-vlm command, `pull`), `backends.py` (OpenAI-style client), `mcp_server.py`.
- `app/`: the AppKit window; `scripts/build-app.sh` builds it.
- Tests: `.venv/bin/pytest` runs fake servers in a few seconds; `-m live` needs running models.
