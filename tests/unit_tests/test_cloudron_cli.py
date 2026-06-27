import subprocess
from types import SimpleNamespace

import pytest

from dsd_cloudron import cloudron_cli
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


def test_guard_makes_wrappers_noop(monkeypatch):
    dsd_config.unit_testing = True

    # Bomb both subprocess paths so the test proves the guard returns before any
    # shell-out, regardless of whether the cloudron CLI exists on this machine.
    def _no_subprocess(cmd, **kwargs):
        raise AssertionError(f"subprocess escaped the unit_testing guard: {cmd!r}")

    monkeypatch.setattr(cloudron_cli.plugin_utils, "run_quick_command", _no_subprocess)
    monkeypatch.setattr(cloudron_cli.plugin_utils, "run_slow_command", _no_subprocess)

    cloudron_cli.check_installed()
    cloudron_cli.check_authenticated()
    assert cloudron_cli.install("blog") == ""


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
    assert cloudron_cli.install("blog") == ""
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
    cloudron_cli.install("blog")
    assert "--server my.example.com" in calls[0]
    assert "--allow-selfsigned" in calls[0]


def test_install_wraps_failure_in_dsd_error(monkeypatch):
    dsd_config.unit_testing = False

    def boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(cloudron_cli.plugin_utils, "run_slow_command", boom)
    with pytest.raises(DSDCommandError):
        cloudron_cli.install("blog")


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


def test_check_authenticated_succeeds_when_logged_in(monkeypatch):
    dsd_config.unit_testing = False
    monkeypatch.setattr(
        cloudron_cli.plugin_utils,
        "run_quick_command",
        lambda cmd, **kwargs: SimpleNamespace(returncode=0),
    )
    cloudron_cli.check_authenticated()  # must not raise


def test_check_installed_succeeds_on_zero_exit(monkeypatch):
    dsd_config.unit_testing = False
    monkeypatch.setattr(
        cloudron_cli.plugin_utils,
        "run_quick_command",
        lambda cmd, **kwargs: SimpleNamespace(returncode=0),
    )
    cloudron_cli.check_installed()  # must not raise
