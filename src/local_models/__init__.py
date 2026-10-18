from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # the project: kev.toml, llm.toml, weight/, logs/
WEIGHTS = ROOT / "weight"                    # HF_HOME for every model
