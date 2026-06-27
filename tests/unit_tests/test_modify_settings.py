from dsd_cloudron.platform_deployer import PlatformDeployer
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def test_modify_settings_appends_import_block(tmp_path):
    settings = tmp_path / "settings.py"
    settings.write_text("SECRET_KEY = 'x'\nDEBUG = True\n", encoding="utf-8")
    dsd_config.unit_testing = True
    dsd_config.settings_path = settings

    PlatformDeployer()._modify_settings()

    text = settings.read_text(encoding="utf-8")
    # Original content is preserved.
    assert "SECRET_KEY = 'x'" in text
    assert "DEBUG = True" in text
    # The marker comment that _check_cloudron_settings matches on a re-run, and
    # the package-relative import of the generated cloudron_settings module.
    assert "# dsd-cloudron settings." in text
    assert "from .cloudron_settings import *" in text


def test_modify_settings_marker_matches_check_settings(tmp_path):
    # The start marker the deployer writes must be exactly the literal that
    # _check_cloudron_settings looks for, or re-run detection silently breaks.
    settings = tmp_path / "settings.py"
    settings.write_text("SECRET_KEY = 'x'\n", encoding="utf-8")
    dsd_config.unit_testing = True
    dsd_config.settings_path = settings

    PlatformDeployer()._modify_settings()
    text = settings.read_text(encoding="utf-8")

    start_marker = "# dsd-cloudron settings."
    assert start_marker in text
    # Re-running detection on the modified file finds the block.
    import re

    assert re.match(f"(.*)({start_marker})(.*)", text, re.DOTALL)
