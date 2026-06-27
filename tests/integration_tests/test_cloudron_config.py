"""Integration tests for dsd-cloudron, default retrofit build.

These run only where django-simple-deploy's integration-test harness is
importable (it provides the tmp_project / pkg_manager / dsd_version fixtures and
the it_helper_functions helpers). The harness deploys the sample project with
the plugin installed, then these tests diff the generated artifacts against
reference_files/.
"""

from pathlib import Path

import pytest

from tests.integration_tests.utils import it_helper_functions as hf
from tests.integration_tests.conftest import (
    tmp_project,
    pkg_manager,
    dsd_version,
)


def test_manifest(tmp_project):
    hf.check_reference_file(tmp_project, "CloudronManifest.json", "dsd-cloudron")


def test_dockerfile(tmp_project, pkg_manager):
    if pkg_manager == "req_txt":
        hf.check_reference_file(tmp_project, "Dockerfile", "dsd-cloudron")
    elif pkg_manager == "poetry":
        hf.check_reference_file(
            tmp_project,
            "Dockerfile",
            "dsd-cloudron",
            reference_filename="poetry.Dockerfile",
        )
    elif pkg_manager == "pipenv":
        hf.check_reference_file(
            tmp_project,
            "Dockerfile",
            "dsd-cloudron",
            reference_filename="pipenv.Dockerfile",
        )


def test_start_sh(tmp_project):
    hf.check_reference_file(tmp_project, "start.sh", "dsd-cloudron")


def test_nginx_conf(tmp_project):
    hf.check_reference_file(tmp_project, "nginx.conf", "dsd-cloudron")


def test_supervisor_gunicorn(tmp_project):
    hf.check_reference_file(tmp_project, "supervisor/gunicorn.conf", "dsd-cloudron")


def test_readme(tmp_project):
    hf.check_reference_file(tmp_project, "README-cloudron.md", "dsd-cloudron")


def test_cloudron_settings(tmp_project):
    hf.check_reference_file(tmp_project, "blog/cloudron_settings.py", "dsd-cloudron")


def test_settings_import_appended(tmp_project):
    hf.check_reference_file(tmp_project, "blog/settings.py", "dsd-cloudron")


def test_requirements_txt(tmp_project, pkg_manager, tmp_path, dsd_version):
    if pkg_manager == "req_txt":
        context = {"current-version": dsd_version}
        hf.check_reference_file(
            tmp_project,
            "requirements.txt",
            "dsd-cloudron",
            context=context,
            tmp_path=tmp_path,
        )
    else:
        assert not (tmp_project / "requirements.txt").exists()
