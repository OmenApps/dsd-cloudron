"""Direct tests of the @hookimpl wrappers in dsd_cloudron/deploy.py.

These wrappers are the real pluggy registration surface core discovers and calls.
Every other test drives the underlying PlatformDeployer/PluginCLI/validate_cli
directly, so the thin delegating wrappers themselves have no coverage - a wrapper
that called the wrong thing (or nothing) would pass the whole rest of the suite.
"""

from dsd_cloudron import deploy
from dsd_cloudron.deploy import (
    dsd_deploy,
    dsd_get_plugin_cli,
    dsd_get_plugin_config,
    dsd_pre_inspect,
    dsd_validate_cli,
)
from dsd_cloudron.plugin_config import plugin_config
from dsd_cloudron.platform_deployer import PlatformDeployer


def test_get_plugin_config_returns_the_singleton():
    # core reads platform attributes off exactly this object, so the getter must
    # hand back the module singleton, not a fresh PluginConfig.
    assert dsd_get_plugin_config() is plugin_config


def test_get_plugin_cli_delegates_to_plugin_cli(monkeypatch):
    calls = []
    # Patch the name deploy.py bound via `from .cli import PluginCLI`; patching
    # cli.PluginCLI would not touch the reference this wrapper actually holds.
    monkeypatch.setattr(deploy, "PluginCLI", lambda parser: calls.append(parser))
    parser = object()
    dsd_get_plugin_cli(parser)
    assert calls == [parser]


def test_validate_cli_delegates_to_validate_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(deploy, "validate_cli", lambda options: calls.append(options))
    options = object()
    dsd_validate_cli(options)
    assert calls == [options]


def test_pre_inspect_delegates_to_uv_retrofit(monkeypatch):
    # The hook must hand core back exactly what uv_retrofit.prepare returns: a
    # status message (written by core) when a uv project was materialized, or None
    # (dropped by pluggy) otherwise.
    sentinel = "exported uv requirements"
    monkeypatch.setattr(deploy.uv_retrofit, "prepare", lambda: sentinel)
    assert dsd_pre_inspect() == sentinel


def test_deploy_delegates_to_platform_deployer(monkeypatch):
    calls = []
    # Patch deploy on the class: the wrapper constructs a fresh PlatformDeployer
    # and calls .deploy() on it, so the recorder must capture that instance.
    monkeypatch.setattr(
        PlatformDeployer, "deploy", lambda self, *args, **kwargs: calls.append(self)
    )
    dsd_deploy()
    assert len(calls) == 1
    assert isinstance(calls[0], PlatformDeployer)
