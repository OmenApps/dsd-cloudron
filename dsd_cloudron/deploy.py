"""django-simple-deploy hook implementations for Cloudron."""

import django_simple_deploy

from .platform_deployer import PlatformDeployer
from .plugin_config import plugin_config
from .cli import PluginCLI, validate_cli


@django_simple_deploy.hookimpl
def dsd_get_plugin_config():
    """Return platform attributes needed by core."""
    return plugin_config


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
