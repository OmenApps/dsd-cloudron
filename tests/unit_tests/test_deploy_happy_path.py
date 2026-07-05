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


def test_deploy_reconfigure_reruns_artifacts_and_skips_settings(monkeypatch, tmp_path):
    # An already-configured project: pre-render the artifact set, then hand-edit one
    # file so the fresh render differs. deploy() with --reconfigure must restore it
    # (get_confirmation auto-yes under unit testing) while touching neither settings.py
    # nor the requirements.
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    pkg = tmp_path / "blog"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    settings = pkg / "settings.py"
    settings.write_text("SECRET_KEY = 'x'\n", encoding="utf-8")
    render_all(
        CloudronAppConfig(project_name="blog", app_id="com.example.blog"), tmp_path
    )
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("HAND EDIT\n", encoding="utf-8")

    dsd_config.unit_testing = True
    dsd_config.local_project_name = "blog"
    dsd_config.deployed_project_name = "blog"
    dsd_config.pkg_manager = "req_txt"
    dsd_config.project_root = tmp_path
    dsd_config.settings_path = settings
    dsd_config.automate_all = False
    plugin_config.reconfigure = True

    added = []
    monkeypatch.setattr(
        pd.plugin_utils, "add_package", lambda name, version="": added.append(name)
    )

    PlatformDeployer().deploy()

    assert "HAND EDIT" not in dockerfile.read_text(encoding="utf-8")  # restored
    assert "# dsd-cloudron settings." not in settings.read_text(encoding="utf-8")
    assert added == []
    # A file was overwritten, so the "run cloudron update" reminder fires (and not the
    # "no changes" branch). This proves the deploy went through _reconfigure's tail.
    out = dsd_config.stdout.getvalue()
    assert "cloudron update" in out
    assert "No changes were made" not in out


def test_deploy_reconfigure_preserves_tuned_manifest_sizing(monkeypatch, tmp_path):
    # An operator who tuned memoryLimit and runs --reconfigure without restating
    # --memory-limit must not have it reverted to the 1 GB CLI default. The retrofit
    # path reads the two scalars back from the deployed manifest before the sync.
    import json

    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    pkg = tmp_path / "blog"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    settings = pkg / "settings.py"
    settings.write_text("SECRET_KEY = 'x'\n", encoding="utf-8")
    render_all(
        CloudronAppConfig(project_name="blog", app_id="com.example.blog"), tmp_path
    )
    manifest = tmp_path / "CloudronManifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["memoryLimit"] = 2147483648  # operator-tuned, above the 1 GB default
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    dsd_config.unit_testing = True
    dsd_config.local_project_name = "blog"
    dsd_config.deployed_project_name = "blog"
    dsd_config.pkg_manager = "req_txt"
    dsd_config.project_root = tmp_path
    dsd_config.settings_path = settings
    dsd_config.automate_all = False
    plugin_config.reconfigure = True  # memory_limit left at the 1 GB CLI default

    # Monkeypatch add_package so the test does not rely on the normal path crashing on a
    # None requirements list to "prove" reconfigure ran; the assertions below discriminate
    # the reconfigure branch from a fall-through to a full deploy instead.
    added = []
    monkeypatch.setattr(
        pd.plugin_utils, "add_package", lambda name, version="": added.append(name)
    )

    PlatformDeployer().deploy()

    assert json.loads(manifest.read_text(encoding="utf-8"))["memoryLimit"] == 2147483648
    # Discriminate the reconfigure branch: a fall-through to the full deploy would append
    # the settings block and call add_package. Nothing changed on disk (only the manifest
    # was hand-tuned, and reconfigure reads that sizing back), so the "no changes" branch
    # fires rather than the update reminder.
    assert "# dsd-cloudron settings." not in settings.read_text(encoding="utf-8")
    assert added == []
    assert "No changes were made" in dsd_config.stdout.getvalue()
