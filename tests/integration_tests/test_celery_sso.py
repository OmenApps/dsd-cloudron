"""The one app-intrusive reference build: --celery --sso.

Runs only where the integration-test harness is importable.
"""

import pytest

from tests.integration_tests.conftest import tmp_project
from tests.integration_tests.utils import it_helper_functions as hf
from tests.integration_tests.utils import manage_sample_project as msp

pytestmark = pytest.mark.skip_auto_dsd_call


def test_celery_sso_artifacts(tmp_project, request):
    cmd = "python manage.py deploy --location blog --celery --sso"
    msp.call_deploy(tmp_project, cmd, platform="cloudron")

    hf.check_reference_file(
        tmp_project,
        "supervisor/celery-worker.conf",
        "dsd-cloudron",
        reference_filename="celery_sso.supervisor.celery-worker.conf",
    )
    hf.check_reference_file(
        tmp_project,
        "supervisor/celery-beat.conf",
        "dsd-cloudron",
        reference_filename="celery_sso.supervisor.celery-beat.conf",
    )
    hf.check_reference_file(
        tmp_project,
        "blog/cloudron_settings.py",
        "dsd-cloudron",
        reference_filename="celery_sso.cloudron_settings.py",
    )
    hf.check_reference_file(
        tmp_project,
        "CloudronManifest.json",
        "dsd-cloudron",
        reference_filename="celery_sso.CloudronManifest.json",
    )
    # The celery.py app and its __init__ wiring are what make the rendered
    # worker/beat confs actually start; diff them too so a regression that drops
    # them fails here instead of only crash-looping on a real Cloudron box.
    hf.check_reference_file(
        tmp_project,
        "blog/celery.py",
        "dsd-cloudron",
        reference_filename="celery_sso.celery.py",
    )
    hf.check_reference_file(
        tmp_project,
        "blog/__init__.py",
        "dsd-cloudron",
        reference_filename="celery_sso.init.py",
    )
