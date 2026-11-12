import os
import subprocess
import time
from types import SimpleNamespace

import pytest

from local_models import servers


@pytest.fixture(autouse=True)
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(servers, "LOGS", tmp_path)


def test_stale_pid_file_is_removed(tmp_path):
    p = subprocess.Popen(["true"])
    p.wait()
    (tmp_path / "m.pid").write_text(str(p.pid))
    assert servers.pid_of("m") is None and not (tmp_path / "m.pid").exists()


def test_pid_reused_by_another_user(tmp_path):
    (tmp_path / "m.pid").write_text("1")   # launchd, owned by root
    assert servers.pid_of("m") is None and not (tmp_path / "m.pid").exists()


def test_pid_reused_after_the_pid_file_was_written(tmp_path):
    # a pid file left by a reboot: its pid now belongs to a process that started later, which stop must not kill
    f = tmp_path / "m.pid"
    f.write_text(str(os.getpid()))
    os.utime(f, (time.time() - 86400 * 400, time.time() - 86400 * 400))
    assert servers.pid_of("m") is None and not f.exists()


def test_pid_of_a_live_server(tmp_path):
    (tmp_path / "m.pid").write_text(str(os.getpid()))   # this process started before the file was written
    assert servers.pid_of("m") == os.getpid()


def test_free_gb_is_positive():
    assert 0 < servers.free_gb() < 10_000


def test_launch_waits_until_ready_and_stop_ends_it(monkeypatch, capsys):
    monkeypatch.setattr(servers, "free_gb", lambda: 1)
    monkeypatch.setattr(servers.time, "sleep", lambda s: None)
    answers = iter([None, True])
    servers.launch(SimpleNamespace(name="m", memory_gb=2), ["sleep", "5"], lambda: next(answers), 60)
    assert servers.pid_of("m") and "needs about 2 GB and 1 GB is free" in capsys.readouterr().out
    servers.stop("m")
    assert servers.pid_of("m") is None


def test_launch_reports_a_server_that_dies(tmp_path, monkeypatch):
    monkeypatch.setattr(servers, "free_gb", lambda: 100)
    with pytest.raises(SystemExit, match="m exited with 3:\nno weights"):
        servers.launch(SimpleNamespace(name="m", memory_gb=2), ["sh", "-c", "echo no weights; exit 3"], lambda: time.sleep(0.2), 60)
    assert not (tmp_path / "m.pid").exists()
