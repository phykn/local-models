import pytest

from local_models.kev.registry import load_registry as load_kev
from local_models.llm.registry import load_registry as load_llm
from local_models.registry import RegistryError

TOML = '''default = "a"

[models."a"]
run = "x/a@v1"
port = 8011   # keep this comment
memory_gb = 16

[models.b]
run = "x/b@v1"
memory_gb = 4
port = 8012
'''


def reg_of(tmp_path, text=TOML, load=load_kev):
    path = tmp_path / "models.toml"
    path.write_text(text)
    return load(path)


def test_project_registries_load():
    for reg in (load_kev(), load_llm()):
        assert reg.default in reg.models


def test_set_port_rewrites_only_that_model(tmp_path):
    reg = reg_of(tmp_path)
    reg.set_port("a", 9000)
    assert reg.path.read_text() == TOML.replace("8011", "9000")
    reg.set_port("b", 9001)
    new = load_kev(reg.path)
    assert (new.get("a").port, new.get("b").port) == (9000, 9001)


def test_set_port_rejects_privileged(tmp_path):
    reg = reg_of(tmp_path)
    with pytest.raises(RegistryError, match="between 1024"):
        reg.set_port("a", 80)
    assert load_kev(reg.path).get("a").port == 8011


def test_set_port_leaves_the_file_alone_when_the_edit_would_change_more(tmp_path):
    reg = reg_of(tmp_path)
    # b's port line comes after a line starting with [, which looks like the start of the next table
    text = TOML.replace("memory_gb = 4", "note = [\n[1, 2]]")
    reg.path.write_text(text)
    with pytest.raises(RegistryError, match="could not find the port line"):
        reg.set_port("b", 9001)
    assert reg.path.read_text() == text


def test_unknown_model(tmp_path):
    with pytest.raises(RegistryError, match="unknown model 'c'; registered: a, b"):
        reg_of(tmp_path).get("c")


@pytest.mark.parametrize("table, error", [
    ('run = "x/y@v1"\nport = 1\nmemory_gbb = 4', "unknown keys memory_gbb"),   # a typo must not silently become memory_gb = 0
    ("port = 1", "missing 1 required positional argument: 'run'"),   # start would otherwise fail with a TypeError
    ('run = "x/y@v1"', "missing 1 required positional argument: 'port'"),   # the app and kev.serve need one
])
def test_kev_registry_rejects_bad_tables(tmp_path, table, error):
    with pytest.raises(RegistryError, match=error):
        reg_of(tmp_path, f"[models.m]\n{table}\n")


@pytest.mark.parametrize("table, error", [
    ('server = "mlx-vlm"\nrun = "a/b@c"\nport = 1\nmin_confidence = 0.5', "unknown keys min_confidence"),
    ('server = "vllm"\nrun = "a/b@c"\nport = 1', "server must be one of mlx-vlm, mlx-lm"),
])
def test_llm_registry_rejects_bad_tables(tmp_path, table, error):
    with pytest.raises(RegistryError, match=error):
        reg_of(tmp_path, f"[models.m]\n{table}\n", load_llm)


def test_default_must_be_a_model(tmp_path):
    with pytest.raises(RegistryError, match="default model 'z'"):
        reg_of(tmp_path, 'default = "z"\n' + TOML.split("\n", 1)[1])


def test_reload_keeps_the_last_good_registry(tmp_path):
    reg = reg_of(tmp_path)
    reg.path.write_text("[models.a\n")   # mid-edit
    assert reg.reload() is reg
    reg.path.write_text(TOML.replace("8011", "8012"))
    assert reg.reload().get("a").port == 8012
