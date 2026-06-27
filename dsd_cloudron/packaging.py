"""The dsd-cloudron packaging core.

Single source of truth for the generated Cloudron artifact set. Pure render
functions: no network, no `cloudron` CLI, no django-simple-deploy core. Both the
retrofit deployer (M1) and the greenfield scaffolder (M2) call render_all().
"""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from django.template import Context, Engine

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Standalone engine so rendering does not depend on the user's project settings.
# IMPORTANT: every value in _context must be a string. Django localizes
# non-string values (int/float) through the global settings during rendering,
# which raises ImproperlyConfigured when settings are unconfigured (offline unit
# tests, greenfield console script) and applies locale formatting (e.g. "8,000")
# when they are configured (retrofit). Keeping the context string-only sidesteps
# both. Autoescape off because we render shell/config/text, not HTML.
# string_if_invalid surfaces a context/template drift (an undefined variable)
# loudly instead of rendering an empty string; an invariant test asserts no
# rendered artifact contains the sentinel.
_ENGINE = Engine(autoescape=False, string_if_invalid="INVALID_TEMPLATE_VAR[%s]")


@dataclass
class CloudronAppConfig:
    project_name: str
    app_id: str
    pkg_manager: str = "req_txt"
    enable_redis: bool = True
    enable_celery: bool = False
    enable_sendmail: bool = True
    enable_sso: bool = False
    memory_limit: int = 1073741824
    http_port: int = 8000
    health_check_path: str = "/"
    title: str = ""
    version: str = "1.0.0"
    author: str = ""

    def __post_init__(self):
        # Celery's broker is the Redis addon URL (CELERY_BROKER_URL reads
        # CLOUDRON_REDIS_URL), and the manifest only declares the redis addon
        # when enable_redis is on. Celery without Redis renders a settings module
        # that KeyErrors at runtime, so reject the combination at construction.
        if self.enable_celery and not self.enable_redis:
            raise ValueError(
                "enable_celery requires enable_redis (Celery uses the Redis broker)."
            )

    def display_title(self):
        """Human title for the manifest; derived from project_name if unset."""
        return self.title or self.project_name.replace("_", " ").title()


def _context(config):
    """Template context shared by the flat-text render functions."""
    return {
        "project_name": config.project_name,
        "app_id": config.app_id,
        "http_port": str(config.http_port),  # string-only context; see _ENGINE note
        "health_check_path": config.health_check_path,
        "enable_redis": config.enable_redis,
        "enable_celery": config.enable_celery,
        "enable_sendmail": config.enable_sendmail,
        "enable_sso": config.enable_sso,
        "pip_install_block": _pip_install_block(config.pkg_manager),
    }


def _render_template(filename, context):
    """Render a templates/<filename> file with the standalone engine."""
    text = (TEMPLATES_DIR / filename).read_text()
    return _ENGINE.from_string(text).render(Context(context))


def _write(path, contents, executable=False):
    """Write contents to path, creating parents, optionally chmod +x."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _pip_install_block(pkg_manager):
    """The Dockerfile dependency-install snippet for the chosen package manager.

    Stub returns empty so the module imports; the real per-manager blocks are
    added in Task 5.
    """
    return ""
