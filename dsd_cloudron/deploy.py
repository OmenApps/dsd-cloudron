"""django-simple-deploy hook implementations for Cloudron."""

import django_simple_deploy

from .platform_deployer import PlatformDeployer
from .plugin_config import plugin_config
from .cli import PluginCLI, validate_cli
from . import uv_retrofit


@django_simple_deploy.hookimpl
def dsd_get_plugin_config():
    """Return platform attributes needed by core."""
    return plugin_config


@django_simple_deploy.hookimpl
def dsd_pre_inspect():
    """Prepare a uv project so core's dependency detection can see it.

    Core detects only req_txt/poetry/pipenv, so a uv-only project would abort core's
    inspection before this plugin runs. Runs before that inspection; see uv_retrofit.
    """
    return uv_retrofit.prepare()


@django_simple_deploy.hookimpl
def dsd_get_plugin_cli(parser):
    """Add plugin-specific CLI args."""
    PluginCLI(parser)


@django_simple_deploy.hookimpl
def dsd_validate_cli(options):
    """Validate and parse plugin-specific CLI args."""
    validate_cli(options)


@django_simple_deploy.hookimpl
def dsd_deploy():
    """Carry out the Cloudron deployment."""
    PlatformDeployer().deploy()
