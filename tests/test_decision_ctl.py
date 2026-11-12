import sys

from conftest import decision_spec, registry_of

from local_models.decision.ctl import Ctl


def test_pplx_runs_the_systemone_server(tmp_path):
    spec = decision_spec(port=8011, server="pplx-decider")
    assert Ctl(registry_of(tmp_path, spec)).command(spec) == [
        sys.executable, "-m", "local_models.decision.systemone", "--server", "pplx-decider", "--run", "x/m@v1", "--port", "8011"]
