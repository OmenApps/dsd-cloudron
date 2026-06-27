"""Assert dsd-cloudron CLI args appear in `manage.py deploy --help`.

Runs only where the integration-test harness is importable.
"""

import pytest

from tests.integration_tests.conftest import tmp_project
from tests.integration_tests.utils import manage_sample_project as msp

pytestmark = pytest.mark.skip_auto_dsd_call


def test_plugin_help_output(tmp_project, request):
    cmd = "python manage.py deploy --help"
    stdout, stderr = msp.call_deploy(tmp_project, cmd, platform="cloudron")
    for fragment in [
        "--location",
        "--app-id",
        "--memory-limit",
        "--health-check-path",
        "--force-overwrite",
        "--server",
        "--allow-selfsigned",
        "--no-redis",
        "--no-sendmail",
        "--celery",
        "--sso",
    ]:
        assert fragment in stdout
    # The API token is intentionally not a CLI flag; auth comes from the
    # `cloudron login` session, so --token must not appear in help.
    assert "--token" not in stdout
