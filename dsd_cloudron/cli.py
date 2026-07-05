"""Extends the core django-simple-deploy CLI with Cloudron options."""

import re

from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)

from . import deploy_messages as platform_msgs
from .plugin_config import plugin_config

# location and server are interpolated into `cloudron` command strings, so
# restrict them to the characters real subdomains and hostnames use; anything
# else (whitespace, quotes, shell metacharacters) is rejected up front. The
# value must start with an alphanumeric so it cannot be read as a CLI flag
# (e.g. a leading "-" turning the value into an option to `cloudron`).
_SAFE_CLI_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def _reject_unsafe(value, flag):
    if value and not _SAFE_CLI_VALUE.match(value):
        raise DSDCommandError(platform_msgs.unsafe_cli_value(flag, value))


class PluginCLI:
    def __init__(self, parser):
        group = parser.add_argument_group(
            title="Options for dsd-cloudron",
            description=(
                "Configure and deploy a Django project to Cloudron. Authenticate "
                "first with `cloudron login` (or the cloudron CLI's CLOUDRON_* "
                "environment variables for non-interactive use); the deploy reuses "
                "that session rather than taking an API token on the command line."
            ),
        )

        # Deploy / identity.
        group.add_argument(
            "--location",
            type=str,
            default="",
            help="Cloudron subdomain to install to, e.g. 'blog'.",
        )
        group.add_argument(
            "--app-id",
            type=str,
            default="",
            help="Reverse-DNS app id, e.g. com.example.blog.",
        )
        group.add_argument(
            "--memory-limit",
            type=int,
            default=1073741824,
            help="Memory limit in bytes (default ~1 GB).",
        )
        group.add_argument(
            "--health-check-path",
            type=str,
            default="/",
            help="Path that returns 2xx when healthy (default '/').",
        )
        group.add_argument(
            "--force-overwrite",
            action="store_true",
            help=(
                "Regenerate Cloudron artifacts that already exist, and replace an "
                "existing Cloudron settings block without prompting."
            ),
        )
        group.add_argument(
            "--reconfigure",
            action="store_true",
            help=(
                "Re-render the Cloudron artifacts against an already-configured "
                "project, showing a diff and asking before overwriting each file. "
                "Pass the same toggles you deployed with; reconfigure cannot change "
                "which stacks are enabled, and it preserves the manifest's memoryLimit "
                "and healthCheckPath (change those in CloudronManifest.json or re-deploy)."
            ),
        )
        group.add_argument(
            "--server",
            type=str,
            default="",
            help="Cloudron server domain, e.g. my.example.com (selects the logged-in session to use).",
        )
        group.add_argument(
            "--allow-selfsigned",
            action="store_true",
            help="Allow a self-signed Cloudron server certificate.",
        )

        # Default-on infra, opt out.
        group.add_argument(
            "--no-redis", action="store_true", help="Do not configure the Redis addon."
        )
        group.add_argument(
            "--no-sendmail",
            action="store_true",
            help="Do not configure the sendmail addon.",
        )

        # App-intrusive, opt in.
        group.add_argument(
            "--celery",
            action="store_true",
            help="Add Celery worker/beat, generate <project>/celery.py, and add celery to requirements.",
        )
        group.add_argument(
            "--sso",
            action="store_true",
            help="Render Cloudron OIDC config (oidc addon + allauth provider settings) and add django-allauth. You finish wiring allauth into INSTALLED_APPS/urls; see the success message.",
        )


def validate_cli(options):
    """Validate options and write them onto the plugin_config singleton."""
    plugin_config.location = options["location"]
    plugin_config.app_id = options["app_id"]
    plugin_config.memory_limit = options["memory_limit"]
    plugin_config.health_check_path = options["health_check_path"]
    plugin_config.force_overwrite = options["force_overwrite"]
    plugin_config.server = options["server"]
    plugin_config.allow_selfsigned = options["allow_selfsigned"]
    plugin_config.reconfigure = options["reconfigure"]

    plugin_config.enable_redis = not options["no_redis"]
    plugin_config.enable_sendmail = not options["no_sendmail"]
    plugin_config.enable_celery = options["celery"]
    plugin_config.enable_sso = options["sso"]

    # location and server end up in `cloudron` command strings; reject values
    # that could mis-split the command before anything is written.
    _reject_unsafe(plugin_config.location, "--location")
    _reject_unsafe(plugin_config.server, "--server")

    # Celery's broker is the Redis addon URL, so the combination is invalid.
    # Reject it here, at CLI-validation time and before any files are written,
    # so the user sees a clean DSDCommandError instead of the raw ValueError
    # that CloudronAppConfig.__post_init__ would later raise in _build_config.
    if plugin_config.enable_celery and not plugin_config.enable_redis:
        raise DSDCommandError(platform_msgs.celery_requires_redis)

    # Reconfigure is an interactive review flow: it shows a per-file diff and asks
    # before overwriting each artifact, and core's get_confirmation only auto-answers
    # under unit/e2e testing, never under --automate-all. The combination would block
    # on input() (or EOFError under cron/CI) at the first changed file, and deploy()
    # returns right after the re-render, so --automate-all would not commit or install
    # anyway. Reject it up front with a clear message.
    if plugin_config.reconfigure and dsd_config.automate_all:
        raise DSDCommandError(platform_msgs.reconfigure_automate_all_conflict)

    # --location is required with --automate-all to avoid an interactive prompt.
    if dsd_config.automate_all and not plugin_config.location:
        raise DSDCommandError(platform_msgs.location_required)
