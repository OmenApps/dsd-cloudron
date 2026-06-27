"""Thin, guarded wrappers around the `cloudron` CLI.

Every wrapper begins with the unit_testing guard so unit and integration tests
never shell out or hit the network.
"""

import subprocess

from django_simple_deploy.management.commands.utils import plugin_utils
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)

from . import deploy_messages as platform_msgs
from .plugin_config import plugin_config


def _global_flags():
    """Assemble --server/--allow-selfsigned from plugin_config.

    The deploy authenticates through the `cloudron login` session, so no secret
    is ever placed on the command line; these flags only select which server to
    target and whether to accept a self-signed certificate.
    """
    parts = []
    if plugin_config.server:
        parts.append(f"--server {plugin_config.server}")
    if plugin_config.allow_selfsigned:
        parts.append("--allow-selfsigned")
    return " ".join(parts)


def check_installed():
    """Verify the `cloudron` CLI is available."""
    if dsd_config.unit_testing:
        return
    # A missing executable raises FileNotFoundError from subprocess before any
    # CompletedProcess is returned, so checking returncode alone would miss the
    # very case this guard exists for. Catch it and raise the clean message.
    try:
        output = plugin_utils.run_quick_command("cloudron --version")
    except FileNotFoundError as error:
        raise DSDCommandError(platform_msgs.cli_not_installed) from error
    if output.returncode != 0:
        raise DSDCommandError(platform_msgs.cli_not_installed)


def check_authenticated():
    """Verify we are logged in to a Cloudron server."""
    if dsd_config.unit_testing:
        return
    cmd = f"cloudron list {_global_flags()}".rstrip()
    output = plugin_utils.run_quick_command(cmd)
    if output.returncode != 0:
        raise DSDCommandError(platform_msgs.cli_logged_out)


def install(location):
    """Build on the server and install the app at `location`.

    The memory limit travels in CloudronManifest.json, so no -m flag is needed.
    Returns "": the deployed URL is not scraped from the build output. The build
    streams through run_slow_command, which returns None and raises
    CalledProcessError on a nonzero exit, wrapped here as a clean DSDCommandError.
    """
    if dsd_config.unit_testing:
        return ""
    cmd = f"cloudron install -l {location} {_global_flags()}".rstrip()
    try:
        plugin_utils.run_slow_command(cmd)
    except subprocess.CalledProcessError as error:
        raise DSDCommandError(platform_msgs.install_failed) from error
    return ""
