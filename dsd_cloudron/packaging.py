"""The dsd-cloudron packaging core.

Single source of truth for the generated Cloudron artifact set. Pure render
functions: no network, no `cloudron` CLI, no django-simple-deploy core. Both the
retrofit deployer (M1) and the greenfield scaffolder (M2) call render_all().
"""

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from django.template import Context, Engine

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Package managers whose Dockerfile install block is supported. "dsd" is the
# allowed abbreviation in this codebase; these tokens mirror DSD core's
# pkg_manager values plus uv.
SUPPORTED_PKG_MANAGERS = ("req_txt", "poetry", "pipenv", "uv")

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
        # Reject an unsupported package manager at construction; otherwise the
        # Dockerfile install block silently falls through to the req_txt default
        # and produces a Dockerfile that does not match the project.
        if self.pkg_manager not in SUPPORTED_PKG_MANAGERS:
            raise ValueError(
                f"Unsupported pkg_manager {self.pkg_manager!r}; "
                f"expected one of {', '.join(SUPPORTED_PKG_MANAGERS)}."
            )
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
        # Booleans are localization-safe (Django's localize() short-circuits
        # bool) and are only consumed by {% if %} tags, never emitted as {{ }}.
        "enable_redis": config.enable_redis,
        "enable_celery": config.enable_celery,
        "enable_sendmail": config.enable_sendmail,
        "enable_sso": config.enable_sso,
        "pip_install_block": _pip_install_block(config.pkg_manager),
    }


def _render_template(filename, context):
    """Render a templates/<filename> file with the standalone engine."""
    text = (TEMPLATES_DIR / filename).read_text(encoding="utf-8")
    # autoescape=False must be set on the Context, not just the Engine: a
    # manually constructed Context defaults to autoescape=True regardless of the
    # engine, which would HTML-escape variable values (e.g. "&&" -> "&amp;&amp;")
    # and corrupt shell/config output.
    return _ENGINE.from_string(text).render(Context(context, autoescape=False))


def _write(path, contents, executable=False):
    """Write contents to path, creating parents, optionally chmod +x."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Force LF + UTF-8 so artifacts generated on Windows still run inside the
    # Linux container (CRLF in start.sh/Dockerfile breaks the shebang). The
    # open() form is used instead of Path.write_text(newline=...) because the
    # newline kwarg only exists on write_text since Python 3.10 and the floor
    # here is 3.9.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _pip_install_block(pkg_manager):
    """The Dockerfile dependency-install snippet for the chosen package manager.

    Stub returns empty so the module imports; the real per-manager blocks are
    added in Task 5.
    """
    return ""


def render_manifest(config):
    """Build CloudronManifest.json as a dict and serialize it."""
    addons = {
        "localstorage": {},
        "postgresql": {},
    }
    if config.enable_redis:
        addons["redis"] = {"noPassword": True}
    if config.enable_sendmail:
        addons["sendmail"] = {"supportsDisplayName": True}
    if config.enable_sso:
        addons["oidc"] = {"loginRedirectUri": "/accounts/oidc/cloudron/login/callback/"}

    manifest = {
        "manifestVersion": 2,
        "id": config.app_id,
        "title": config.display_title(),
        "author": config.author,
        "version": config.version,
        "description": "Deployed with dsd-cloudron.",
        "tagline": "A Django application on Cloudron.",
        "healthCheckPath": config.health_check_path,
        "httpPort": config.http_port,
        "memoryLimit": config.memory_limit,
        "optionalSso": True,
        "addons": addons,
        "checklist": {
            "change-default-password": {
                "message": "Change the default admin password",
            }
        },
        "postInstallMessage": (
            "This app was configured with dsd-cloudron. A default admin account "
            "was created (username `admin`, password `changeme123`). Sign in and "
            "change the password immediately. See README-cloudron.md in the app "
            "source for the full configuration control surface."
        ),
    }
    return json.dumps(manifest, indent=2) + "\n"


def render_cloudron_settings(config):
    """Assemble cloudron_settings.py. Every override is under the ON_CLOUDRON gate."""
    p = config.project_name
    blocks = []

    blocks.append(
        '"""Cloudron settings, appended to the project settings via '
        "`from .cloudron_settings import *`.\n\n"
        "Active only on Cloudron: the whole block is gated on CLOUDRON_APP_ORIGIN,\n"
        "so it stays inert during local development and during the image build.\n"
        '"""\n'
        "import os\n\n"
        'if os.environ.get("CLOUDRON_APP_ORIGIN"):\n'
        "    DEBUG = False\n\n"
        '    SECRET_KEY = os.environ["SECRET_KEY"]\n\n'
        '    ALLOWED_HOSTS = [os.environ.get("CLOUDRON_APP_DOMAIN", "")]\n'
        '    CSRF_TRUSTED_ORIGINS = [os.environ["CLOUDRON_APP_ORIGIN"]]\n'
        '    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")\n'
    )

    blocks.append(
        "    DATABASES = {\n"
        '        "default": {\n'
        '            "ENGINE": "django.db.backends.postgresql",\n'
        '            "NAME": os.environ["CLOUDRON_POSTGRESQL_DATABASE"],\n'
        '            "USER": os.environ["CLOUDRON_POSTGRESQL_USERNAME"],\n'
        '            "PASSWORD": os.environ["CLOUDRON_POSTGRESQL_PASSWORD"],\n'
        '            "HOST": os.environ["CLOUDRON_POSTGRESQL_HOST"],\n'
        '            "PORT": os.environ["CLOUDRON_POSTGRESQL_PORT"],\n'
        '            "CONN_MAX_AGE": 60,\n'
        "        }\n"
        "    }\n"
    )

    blocks.append(
        '    STATIC_URL = "/static/"\n'
        f'    STATIC_ROOT = "/run/{p}/static"\n'
        '    MEDIA_URL = "/media/"\n'
        '    MEDIA_ROOT = "/app/data/media"\n'
    )

    if config.enable_redis:
        blocks.append(
            "    CACHES = {\n"
            '        "default": {\n'
            '            "BACKEND": "django_redis.cache.RedisCache",\n'
            '            "LOCATION": os.environ["CLOUDRON_REDIS_URL"],\n'
            '            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},\n'
            "        }\n"
            "    }\n"
        )

    if config.enable_celery:
        blocks.append(
            '    CELERY_BROKER_URL = os.environ["CLOUDRON_REDIS_URL"]\n'
            "    CELERY_RESULT_BACKEND = CELERY_BROKER_URL\n"
        )

    if config.enable_sendmail:
        blocks.append(
            '    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"\n'
            '    EMAIL_HOST = os.environ["CLOUDRON_MAIL_SMTP_SERVER"]\n'
            '    EMAIL_PORT = int(os.environ["CLOUDRON_MAIL_SMTP_PORT"])\n'
            '    EMAIL_HOST_USER = os.environ["CLOUDRON_MAIL_SMTP_USERNAME"]\n'
            '    EMAIL_HOST_PASSWORD = os.environ["CLOUDRON_MAIL_SMTP_PASSWORD"]\n'
            "    EMAIL_USE_TLS = False\n"
            '    DEFAULT_FROM_EMAIL = os.environ.get("CLOUDRON_MAIL_FROM", "")\n'
            "    SERVER_EMAIL = DEFAULT_FROM_EMAIL\n"
        )

    if config.enable_sso:
        blocks.append(
            '    if os.environ.get("CLOUDRON_OIDC_ISSUER"):\n'
            "        SOCIALACCOUNT_PROVIDERS = {\n"
            '            "openid_connect": {\n'
            '                "APPS": [\n'
            "                    {\n"
            '                        "provider_id": "cloudron",\n'
            '                        "name": os.environ.get("CLOUDRON_OIDC_PROVIDER_NAME", "Cloudron"),\n'
            '                        "client_id": os.environ["CLOUDRON_OIDC_CLIENT_ID"],\n'
            '                        "secret": os.environ["CLOUDRON_OIDC_CLIENT_SECRET"],\n'
            '                        "settings": {"server_url": os.environ["CLOUDRON_OIDC_ISSUER"] + "/.well-known/openid-configuration"},\n'
            "                    }\n"
            "                ]\n"
            "            }\n"
            "        }\n"
        )

    blocks.append(
        '    _custom_settings = "/app/data/custom_settings.py"\n'
        "    if os.path.exists(_custom_settings):\n"
        "        with open(_custom_settings) as _f:\n"
        "            exec(_f.read())\n"
    )

    return "\n".join(blocks)
