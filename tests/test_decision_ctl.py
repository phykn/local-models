import sys

from conftest import decision_spec, registry_of

from local_models.decision.ctl import Ctl


def test_other_runtimes_run_the_systemone_server(tmp_path):
    spec = decision_spec(port=8011, server="kanana")
    assert Ctl(registry_of(tmp_path, spec)).command(spec) == [
        sys.executable, "-m", "local_models.decision.systemone", "--server", "kanana", "--run", "x/m@v1", "--port", "8011"]
