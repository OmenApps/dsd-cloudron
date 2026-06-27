"""django-simple-deploy hook implementations for Cloudron."""

import django_simple_deploy

from .plugin_config import plugin_config


@django_simple_deploy.hookimpl
def dsd_get_plugin_config():
    """Return platform attributes needed by core."""
    return plugin_config


@django_simple_deploy.hookimpl
def dsd_deploy():
    """Carry out the Cloudron deployment. Implemented in platform_deployer.py."""
    from .platform_deployer import PlatformDeployer

    PlatformDeployer().deploy()
