"""A green full-deploy: deploy() composes end to end with nothing failing.

Every other deploy test drives a single step or the OSError failure branch, so
deploy() has never been proven green. A wiring regression between two steps -
the __init__ celery import, the appended settings block, the requirements call -
would be invisible today. This test runs the whole orchestration under the
unit-testing guard and asserts the deployer wiring ABOVE render_all (which
test_render_all already covers), not merely that files exist.
"""

from dsd_cloudron import platform_deployer as pd
from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def test_deploy_composes_end_to_end(monkeypatch, tmp_path):
    # Project skeleton the deployer's in-place file edits read and rewrite.
    pkg = tmp_path / "blog"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    settings = pkg / "settings.py"
    settings.write_text("SECRET_KEY = 'x'\nDEBUG = True\n", encoding="utf-8")

    dsd_config.unit_testing = True
    dsd_config.local_project_name = "blog"
    dsd_config.deployed_project_name = "blog"
    dsd_config.pkg_manager = "req_txt"
    dsd_config.project_root = tmp_path
    dsd_config.settings_path = settings
    dsd_config.automate_all = False

    # Celery on (redis stays on by default, so the combination is valid); it is
    # the toggle that exercises the __init__ import wiring and the celery[redis]
    # requirement, both above render_all.
    plugin_config.enable_celery = True

    # _add_requirements calls add_package(name, version=...) once per package.
    added = []
    monkeypatch.setattr(
        pd.plugin_utils, "add_package", lambda name, version="": added.append(name)
    )

    PlatformDeployer().deploy()  # the whole orchestration, and it must not raise

    # Deployer wiring above render_all - what this test uniquely proves.
    init_py = (pkg / "__init__.py").read_text(encoding="utf-8")
    assert "from .celery import app as celery_app" in init_py  # _add_celery_app ran
    assert "# dsd-cloudron settings." in settings.read_text(  # _modify_settings ran
        encoding="utf-8"
    )
    assert "celery[redis]" in added  # _add_requirements ran with celery on

    # Light smoke that the full sub-paths landed on disk from one deploy() call.
    for relative in (
        "CloudronManifest.json",
        "blog/cloudron_settings.py",
        "blog/celery.py",
        "supervisor/celery-worker.conf",
    ):
        assert (tmp_path / relative).exists(), f"missing {relative}"
