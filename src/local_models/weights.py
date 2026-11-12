import json
from pathlib import Path


def find(run):
    """the snapshot directory of run in the Hub cache, or None when it is not fully downloaded"""
    from huggingface_hub import snapshot_download   # reads HF_HOME at import
    from huggingface_hub.errors import LocalEntryNotFoundError

    repo, rev = run.split("@", 1)
    try:
        path = Path(snapshot_download(repo, revision=rev, local_files_only=True))
    except LocalEntryNotFoundError:
        return None
    # an interrupted download can leave a snapshot with config.json and no weights
    if (index := path / "model.safetensors.index.json").exists():
        files = set(json.loads(index.read_text())["weight_map"].values())
    else:
        files = {"model.safetensors"}
    return path if all((path / f).exists() for f in files | {"config.json"}) else None


def pull(run):
    from huggingface_hub import snapshot_download

    repo, rev = run.split("@", 1)
    return Path(snapshot_download(repo, revision=rev))
