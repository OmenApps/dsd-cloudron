from dsd_cloudron.platform_deployer import PlatformDeployer
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def _setup(tmp_path, body="SECRET_KEY = 'x'\nDEBUG = True\n"):
    settings = tmp_path / "settings.py"
    settings.write_text(body, encoding="utf-8")
    dsd_config.unit_testing = True
    dsd_config.settings_path = settings
    dsd_config.local_project_name = "blog"
    return settings


def test_modify_settings_appends_absolute_import_block(tmp_path):
    settings = _setup(tmp_path)
    PlatformDeployer()._modify_settings()

    text = settings.read_text(encoding="utf-8")
    # Original content is preserved.
    assert "SECRET_KEY = 'x'" in text
    assert "DEBUG = True" in text
    # The marker comment and the absolute import of the generated module. The
    # import is absolute (by package name) so it resolves whether settings.py
    # sits in the package root or under a settings/ subpackage.
    assert "# dsd-cloudron settings." in text
    assert "from blog.cloudron_settings import *" in text


def test_modify_settings_marker_detected_by_check_settings(tmp_path):
    # Round-trip: the marker _modify_settings writes must be the literal
    # _check_cloudron_settings searches for, or re-run detection silently breaks.
    settings = _setup(tmp_path, body="SECRET_KEY = 'x'\n")
    deployer = PlatformDeployer()
    deployer._modify_settings()
    assert "# dsd-cloudron settings." in settings.read_text()

    # Under unit_testing, check_settings auto-confirms and strips the detected
    # block. The block disappearing proves the writer and checker markers match.
    deployer._check_cloudron_settings()
    after = settings.read_text()
    assert "cloudron_settings import *" not in after
    assert "SECRET_KEY = 'x'" in after
