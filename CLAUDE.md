# local-models

- Plan: `docs/groove/PLAN.md` (not in git). A session continuing the build uses groove to do the first unchecked task.
- `src/local_models/registry.py`: reads `decision.toml` / `llm.toml` strictly (one `port` per kind, `run` is `repo@revision`), rewrites the port line.
- `src/local_models/servers.py`: pid files under `logs/`, launch and wait, stop, port and free-memory checks.
- `src/local_models/weights.py`: finds a complete snapshot in `weight/`, downloads one.
- `src/local_models/ctl.py`: `Ctl`, the CLI both kinds share. Its `--json` rows are what `app/Sources/Ctl.swift` decodes; change both together.
- `src/local_models/decision/`: `models.py` (spec), `server.py` (Kanana and pplx-decider behind `POST /v1/systemone`, `GET /v1/info`), `client.py`, `ctl.py`, `mcp_server.py`.
- `src/local_models/llm/`: `models.py`, `client.py` (mlx-vlm chat), `ctl.py` (mlx-vlm command), `mcp_server.py`.
- `app/`: the SwiftUI window; `scripts/build-app.sh` builds it.
- Tests: `.venv/bin/pytest` runs fake servers in a few seconds; `-m live` needs running models.
