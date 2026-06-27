import subprocess
from types import SimpleNamespace

import pytest

from dsd_cloudron import cloudron_cli
from dsd_cloudron.packaging import CloudronAppConfig
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


def test_guard_makes_wrappers_noop():
    dsd_config.unit_testing = True
    # These must not call subprocess and must not raise.
    cloudron_cli.check_installed()
    cloudron_cli.check_authenticated()
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    assert cloudron_cli.install(config, "blog") == ""


def test_global_flags_built_from_config():
    plugin_config.server = "my.example.com"
    plugin_config.allow_selfsigned = True
    flags = cloudron_cli._global_flags()
    assert "--server my.example.com" in flags
    assert "--allow-selfsigned" in flags


def test_global_flags_empty_without_options():
    # No server and no self-signed allowance -> no flags. The reset fixture
    # restores plugin_config to defaults (server="", allow_selfsigned=False).
    assert cloudron_cli._global_flags() == ""


def test_install_runs_slow_command_and_returns_empty(monkeypatch):
    # The real run_slow_command returns None; install() must never touch a return
    # value. With the guard off it should still run cleanly and return "".
    dsd_config.unit_testing = False
    calls = []
    monkeypatch.setattr(
        cloudron_cli.plugin_utils,
        "run_slow_command",
        lambda cmd, **kwargs: calls.append(cmd),
    )
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    assert cloudron_cli.install(config, "blog") == ""
    assert calls[0].startswith("cloudron install -l blog")


def test_install_includes_global_flags(monkeypatch):
    dsd_config.unit_testing = False
    plugin_config.server = "my.example.com"
    plugin_config.allow_selfsigned = True
    calls = []
    monkeypatch.setattr(
        cloudron_cli.plugin_utils,
        "run_slow_command",
        lambda cmd, **kwargs: calls.append(cmd),
    )
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    cloudron_cli.install(config, "blog")
    assert "--server my.example.com" in calls[0]
    assert "--allow-selfsigned" in calls[0]


def test_install_wraps_failure_in_dsd_error(monkeypatch):
    dsd_config.unit_testing = False

    def boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(cloudron_cli.plugin_utils, "run_slow_command", boom)
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    with pytest.raises(DSDCommandError):
        cloudron_cli.install(config, "blog")


def test_check_installed_reports_missing_cli(monkeypatch):
    dsd_config.unit_testing = False

    def missing(cmd, **kwargs):
        raise FileNotFoundError(cmd)

    monkeypatch.setattr(cloudron_cli.plugin_utils, "run_quick_command", missing)
    with pytest.raises(DSDCommandError):
        cloudron_cli.check_installed()


def test_check_installed_reports_nonzero_exit(monkeypatch):
    dsd_config.unit_testing = False
    monkeypatch.setattr(
        cloudron_cli.plugin_utils,
        "run_quick_command",
        lambda cmd, **kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(DSDCommandError):
        cloudron_cli.check_installed()


def test_check_authenticated_raises_when_logged_out(monkeypatch):
    dsd_config.unit_testing = False
    monkeypatch.setattr(
        cloudron_cli.plugin_utils,
        "run_quick_command",
        lambda cmd, **kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(DSDCommandError):
        cloudron_cli.check_authenticated()
