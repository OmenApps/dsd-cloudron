"""The --wagtail retrofit reference build.

Runs only where the integration-test harness is importable.
"""

import pytest

from tests.integration_tests.conftest import tmp_project
from tests.integration_tests.utils import it_helper_functions as hf
from tests.integration_tests.utils import manage_sample_project as msp

pytestmark = pytest.mark.skip_auto_dsd_call


def test_wagtail_artifacts(tmp_project, request):
    cmd = "python manage.py deploy --location blog --wagtail"
    msp.call_deploy(tmp_project, cmd, platform="cloudron")

    hf.check_reference_file(
        tmp_project,
        "blog/cloudron_settings.py",
        "dsd-cloudron",
        reference_filename="wagtail.cloudron_settings.py",
    )
    hf.check_reference_file(
        tmp_project,
        "CloudronManifest.json",
        "dsd-cloudron",
        reference_filename="wagtail.CloudronManifest.json",
    )
    hf.check_reference_file(
        tmp_project,
        "README-cloudron.md",
        "dsd-cloudron",
        reference_filename="wagtail.README-cloudron.md",
    )
