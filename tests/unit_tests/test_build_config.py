import pytest

from django.core.exceptions import ImproperlyConfigured
from django.urls import Resolver404

from dsd_cloudron import platform_deployer as pd
from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.packaging import CloudronAppConfig
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


def _deployer_with_health_path(path):
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", health_check_path=path
    )
    return deployer


def test_health_check_warns_on_resolver404(monkeypatch):
    # A path that does not resolve in the URLconf must produce a best-effort warning
    # before the install burns a build cycle on a 404.
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )

    def raise_404(path):
        raise Resolver404()

    monkeypatch.setattr(pd, "resolve", raise_404)
    _deployer_with_health_path("/")._check_health_check_path()
    assert any("health check path" in m for m in written)


def test_health_check_silent_when_path_resolves(monkeypatch):
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )
    monkeypatch.setattr(pd, "resolve", lambda path: object())  # a resolved match
    _deployer_with_health_path("/healthz/")._check_health_check_path()
    assert written == []


def test_health_check_silent_on_non_resolver_error(monkeypatch):
    # Offline (no configured settings) resolve() raises ImproperlyConfigured, and a
    # broken urls.py raises an import error; neither is a missing route, so the
    # method must stay silent and never crash.
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )

    def raise_other(path):
        raise ImproperlyConfigured("settings are not configured")

    monkeypatch.setattr(pd, "resolve", raise_other)
    _deployer_with_health_path("/")._check_health_check_path()
    assert written == []


def test_build_config_maps_flags():
    dsd_config.unit_testing = True
    dsd_config.local_project_name = "blog"
    dsd_config.pkg_manager = "req_txt"

    plugin_config.app_id = ""
    plugin_config.memory_limit = 1073741824
    plugin_config.health_check_path = "/healthz/"
    plugin_config.enable_redis = True
    plugin_config.enable_sendmail = False
    plugin_config.enable_celery = True
    plugin_config.enable_sso = True

    config = PlatformDeployer()._build_config()
    assert config.project_name == "blog"
    assert config.app_id == "com.example.blog"
    assert config.pkg_manager == "req_txt"
    assert config.health_check_path == "/healthz/"
    assert config.enable_redis is True
    assert config.enable_sendmail is False
    assert config.enable_celery is True
    assert config.enable_sso is True


def test_build_config_respects_explicit_app_id():
    dsd_config.local_project_name = "blog"
    dsd_config.pkg_manager = "req_txt"
    plugin_config.app_id = "io.omenapps.blog"
    config = PlatformDeployer()._build_config()
    assert config.app_id == "io.omenapps.blog"


def test_build_config_wraps_value_error_as_dsd_error():
    # A non-identifier project name makes CloudronAppConfig.__post_init__ raise
    # ValueError; the deployer must translate it into a clean DSDCommandError.
    dsd_config.local_project_name = "my-project"
    dsd_config.pkg_manager = "req_txt"
    plugin_config.app_id = ""
    with pytest.raises(DSDCommandError):
        PlatformDeployer()._build_config()


def test_validate_platform_unguarded_uses_location(monkeypatch):
    # Drive the non-guarded validate path: stub the network/CLI checks so it runs
    # offline, and confirm deployed_project_name comes from plugin_config.location.
    dsd_config.unit_testing = False
    dsd_config.deployed_project_name = "fallback"
    plugin_config.location = "blog"
    monkeypatch.setattr(pd.cloudron_cli, "check_installed", lambda: None)
    monkeypatch.setattr(pd.cloudron_cli, "check_authenticated", lambda: None)
    monkeypatch.setattr(pd.plugin_utils, "check_settings", lambda *a, **k: None)

    deployer = PlatformDeployer()
    deployer._validate_platform()
    assert deployer.deployed_project_name == "blog"


def test_validate_platform_unguarded_falls_back_to_deployed_name(monkeypatch):
    dsd_config.unit_testing = False
    dsd_config.deployed_project_name = "fallback"
    plugin_config.location = ""
    monkeypatch.setattr(pd.cloudron_cli, "check_installed", lambda: None)
    monkeypatch.setattr(pd.cloudron_cli, "check_authenticated", lambda: None)
    monkeypatch.setattr(pd.plugin_utils, "check_settings", lambda *a, **k: None)

    deployer = PlatformDeployer()
    deployer._validate_platform()
    assert deployer.deployed_project_name == "fallback"


def test_deploy_wraps_filesystem_error_as_dsd_error(monkeypatch, tmp_path):
    # A non-transactional write failure mid-deploy must abort cleanly, not with a
    # raw OSError traceback.
    dsd_config.unit_testing = True
    dsd_config.deployed_project_name = "blog"
    dsd_config.local_project_name = "blog"
    dsd_config.pkg_manager = "req_txt"
    dsd_config.project_root = tmp_path

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pd.packaging, "render_all", boom)
    with pytest.raises(DSDCommandError):
        PlatformDeployer().deploy()


def test_validate_platform_under_guard_sets_name():
    dsd_config.unit_testing = True
    dsd_config.deployed_project_name = "blog"
    deployer = PlatformDeployer()
    deployer._validate_platform()
    assert deployer.deployed_project_name == "blog"


def test_check_cloudron_settings_aborts_on_existing_block(tmp_path, monkeypatch):
    # Exercise the re-run safety guard directly. It sits behind the unit_testing
    # guard in _validate_platform, so neither the unit nor the integration suite
    # reaches it otherwise; this test drives it with the guard off.
    settings = tmp_path / "settings.py"
    settings.write_text(
        "SECRET_KEY = 'x'\n\n# dsd-cloudron settings.\n"
        "from .cloudron_settings import *\n",
        encoding="utf-8",
    )
    dsd_config.unit_testing = False
    dsd_config.settings_path = settings
    # Decline the overwrite prompt -> check_settings raises DSDCommandError.
    monkeypatch.setattr(pd.plugin_utils, "get_confirmation", lambda msg: False)

    with pytest.raises(DSDCommandError):
        PlatformDeployer()._check_cloudron_settings()


def test_existing_block_with_automate_all_aborts_cleanly(tmp_path):
    # A non-interactive re-deploy over an existing block must abort with a clean
    # DSDCommandError, not hang or EOFError on core's interactive input() prompt.
    settings = tmp_path / "settings.py"
    settings.write_text(
        "SECRET_KEY = 'x'\n# dsd-cloudron settings.\nFROM_CLOUDRON = True\n"
    )
    dsd_config.unit_testing = False
    dsd_config.settings_path = settings
    dsd_config.automate_all = True
    plugin_config.force_overwrite = False
    with pytest.raises(DSDCommandError) as exc:
        PlatformDeployer()._check_cloudron_settings()
    assert "--force-overwrite" in str(exc.value)


@pytest.mark.parametrize("automate_all", [True, False])
def test_force_overwrite_strips_existing_block(tmp_path, automate_all):
    # --force-overwrite strips the prior block itself (core modify_settings_file
    # only appends) without prompting, whether or not --automate-all is set: the
    # flag is inert on this path. Parametrized to pin that inertness. The strip is
    # exact - everything before the marker is kept, the block and the text after it
    # removed - so the later _modify_settings append yields one block.
    settings = tmp_path / "settings.py"
    settings.write_text(
        "SECRET_KEY = 'x'\n# dsd-cloudron settings.\nFROM_CLOUDRON = True\n"
    )
    dsd_config.unit_testing = False
    dsd_config.settings_path = settings
    dsd_config.automate_all = automate_all
    plugin_config.force_overwrite = True
    PlatformDeployer()._check_cloudron_settings()  # does not raise, no prompt
    assert settings.read_text() == "SECRET_KEY = 'x'\n"


def test_first_deploy_without_block_is_left_untouched(tmp_path):
    # The common first-deploy path: no existing block. Even under --automate-all the
    # method must not raise and must leave settings.py byte-for-byte untouched.
    settings = tmp_path / "settings.py"
    original = "SECRET_KEY = 'x'\nDEBUG = True\n"
    settings.write_text(original)
    dsd_config.unit_testing = False
    dsd_config.settings_path = settings
    dsd_config.automate_all = True
    plugin_config.force_overwrite = False
    PlatformDeployer()._check_cloudron_settings()  # does not raise
    assert settings.read_text() == original


def test_marker_inside_a_string_is_not_treated_as_a_block(tmp_path):
    # The marker text can legitimately appear mid-line in a comment or string. The
    # force path strips without a prompt, so a bare substring match there would
    # silently truncate settings.py; the line-anchored match must ignore it and
    # treat the file as a first deploy.
    settings = tmp_path / "settings.py"
    original = 'NOTE = "# dsd-cloudron settings. not a real block"\nDEBUG = True\n'
    settings.write_text(original)
    dsd_config.unit_testing = False
    dsd_config.settings_path = settings
    dsd_config.automate_all = True
    plugin_config.force_overwrite = True
    PlatformDeployer()._check_cloudron_settings()  # treats it as a first deploy
    assert settings.read_text() == original


def test_force_overwrite_then_modify_yields_single_block(tmp_path):
    # Round trip: strip an existing block, then run the real append. Because core
    # modify_settings_file only appends, the file must still end with exactly one
    # settings block - the whole point of stripping the prior one ourselves.
    settings = tmp_path / "settings.py"
    settings.write_text(
        "SECRET_KEY = 'x'\n\n# dsd-cloudron settings.\n"
        "from myproj.cloudron_settings import *\n"
    )
    dsd_config.unit_testing = False
    dsd_config.settings_path = settings
    dsd_config.local_project_name = "myproj"
    dsd_config.automate_all = True
    plugin_config.force_overwrite = True
    deployer = PlatformDeployer()
    deployer._check_cloudron_settings()
    deployer._modify_settings()
    text = settings.read_text()
    assert text.count("# dsd-cloudron settings.") == 1
    assert "from myproj.cloudron_settings import *" in text
