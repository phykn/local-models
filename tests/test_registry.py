import pytest

from local_models.decision.models import load_registry as load_decision
from local_models.llm.models import load_registry as load_llm
from local_models.registry import RegistryError

TOML = '''default = "a"
port = 8011   # keep this comment

[models."a"]
server = "kanana"
run = "x/a@v1"
memory_gb = 16
description = ""

[models.b]
server = "pplx-decider"
run = "x/b@v1"
memory_gb = 4
description = "port = 1"
'''
DECISION = 'server = "kanana"\nrun = "x/y@v1"\nmemory_gb = 4\ndescription = ""\n'
LLM = 'run = "x/y@v1"\nmemory_gb = 4\ndescription = ""\nthink = {}\nnothink = {}\n'


def reg_of(tmp_path, text=TOML, load=load_decision):
    path = tmp_path / "models.toml"
    path.write_text(text)
    return load(path)


def test_project_registries_load():
    for reg in (load_decision(), load_llm()):
        assert reg.default in reg.models and 1024 <= reg.port


def test_set_port_rewrites_only_the_port_line(tmp_path):
    reg = reg_of(tmp_path)
    reg.set_port(9000)
    assert reg.path.read_text() == TOML.replace("port = 8011", "port = 9000")
    assert load_decision(reg.path).port == 9000


def test_set_port_rejects_privileged(tmp_path):
    reg = reg_of(tmp_path)
    with pytest.raises(RegistryError, match="between 1024"):
        reg.set_port(80)
    assert reg.path.read_text() == TOML


def test_unknown_model(tmp_path):
    with pytest.raises(RegistryError, match="unknown model 'c'; registered: a, b"):
        reg_of(tmp_path).get("c")


@pytest.mark.parametrize("text, error", [
    ("port = 8011\n[models.m]\n" + DECISION.replace("memory_gb", "memory_gbb"), "unknown keys memory_gbb"),   # a typo must not pass
    ("port = 8011\n[models.m]\n" + DECISION.replace('run = "x/y@v1"\n', ""), "missing 1 required positional argument: 'run'"),
    ("port = 8011\n[models.m]\n" + DECISION.replace('"kanana"', '"kev"'), "server must be one of kanana, pplx-decider"),
    ("port = 8011\n[models.m]\n" + DECISION.replace("x/y@v1", "checkpoints/x"), "run must be repo@revision"),
    ("[models.m]\n" + DECISION, "has no port"),
    ("port = 80\n[models.m]\n" + DECISION, "between 1024 and 65535"),
    ("port = 8011\nprot = 1\n[models.m]\n" + DECISION, "unknown keys prot"),
    ('default = "z"\nport = 8011\n[models.m]\n' + DECISION, "default model 'z'"),
])
def test_decision_registry_rejects_bad_files(tmp_path, text, error):
    with pytest.raises(RegistryError, match=error):
        reg_of(tmp_path, text)


def test_llm_registry_needs_sampling(tmp_path):
    with pytest.raises(RegistryError, match="missing 2 required positional arguments: 'think' and 'nothink'"):
        reg_of(tmp_path, "port = 8082\n[models.m]\n" + LLM.replace("think = {}\nnothink = {}\n", ""), load_llm)


def test_reload_keeps_the_last_good_registry(tmp_path):
    reg = reg_of(tmp_path)
    reg.path.write_text("[models.a\n")   # mid-edit
    assert reg.reload() is reg
    reg.path.write_text(TOML.replace("8011", "8012"))
    assert reg.reload().port == 8012
