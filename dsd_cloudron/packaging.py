"""The dsd-cloudron packaging core.

Single source of truth for the generated Cloudron artifact set. Pure render
functions: no network, no `cloudron` CLI, no django-simple-deploy core. Both the
retrofit deployer and the greenfield scaffolder call render_all().
"""

import json
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
# IMPORTANT: every value in _context must be a str or a bool. Django localizes
# non-string values (int/float) through the global settings during rendering,
# which raises ImproperlyConfigured when settings are unconfigured (offline unit
# tests, greenfield console script) and applies locale formatting (e.g. "8,000")
# when they are configured (retrofit). Keeping the context to str/bool sidesteps
# both: Django's localize() special-cases bool before the settings-touching
# int/float branch, so a bool value cannot raise offline. readme_cloudron.md is
# the one template carrying {% if %} conditionals (its greenfield/enable_sso
# branches); every other template keeps conditional logic in Python.
# Autoescape off because we render shell/config/text, not HTML.
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
    author: str = "Your Name"
    # True only for the greenfield scaffolder, which wires allauth into the
    # generated project. The retrofit deployer leaves it False (it cannot safely
    # rewrite an existing project's INSTALLED_APPS/urls), which flips the readme's
    # SSO section to "allauth is not auto-wired" instead of claiming it is.
    greenfield: bool = False

    def __post_init__(self):
        # project_name is spliced into generated Python (STATIC_ROOT) and into
        # templates (the wsgi module path, socket/static paths). It is the Django
        # project package, so it must be a valid Python identifier; rejecting
        # anything else closes a code-injection / broken-output hole.
        if not self.project_name.isidentifier():
            raise ValueError(
                f"project_name {self.project_name!r} is not a valid Python "
                "identifier (it names the Django project package)."
            )
        # Reject an unsupported package manager at construction; otherwise the
        # Dockerfile install block silently falls through to the req_txt default
        # and produces a Dockerfile that does not match the project.
        if self.pkg_manager not in SUPPORTED_PKG_MANAGERS:
            raise ValueError(
                f"Unsupported pkg_manager {self.pkg_manager!r}; "
                f"expected one of {', '.join(SUPPORTED_PKG_MANAGERS)}."
            )
        # Cloudron's manifest schema rejects an author shorter than 2 characters,
        # so an empty author fails `cloudron install` server-side. Catch it at
        # construction with a clear message instead of a late install error.
        if len(self.author.strip()) < 2:
            raise ValueError(
                f"author {self.author!r} is too short; Cloudron requires the "
                "manifest author to be at least 2 characters."
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
    """Template context shared by the flat-text render functions.

    Only the variables the flat templates actually reference are included.
    Most conditional logic (addons, settings blocks, supervisor programs) lives
    in Python, not in the templates; the exception is readme_cloudron.md, whose
    SSO wiring section branches on greenfield/enable_sso. Values must be str or
    bool: the standalone Engine localizes non-string ints/floats through global
    settings during rendering, which raises offline, but bools are safe.
    """
    return {
        "project_name": config.project_name,
        "http_port": str(config.http_port),
        "pip_install_block": _pip_install_block(config.pkg_manager),
        # Real bools, not str(): a stringified "False" is truthy in a Django
        # template and would flip the readme's SSO branch to the wired claim.
        "greenfield": config.greenfield,
        "enable_sso": config.enable_sso,
    }


def _render_template(filename, context):
    """Render a templates/<filename> file with the standalone engine."""
    text = (TEMPLATES_DIR / filename).read_text(encoding="utf-8")
    # autoescape=False must be set on the Context, not just the Engine: a
    # manually constructed Context defaults to autoescape=True regardless of the
    # engine, which would HTML-escape variable values (e.g. "&&" -> "&amp;&amp;")
    # and corrupt shell/config output.
    return _ENGINE.from_string(text).render(Context(context, autoescape=False))


@dataclass
class RenderResult:
    written: list
    skipped: list


def _write(path, contents, result, force, executable=False):
    """Write contents unless the file exists and force is False; record outcome."""
    path = Path(path)
    if path.exists() and not force:
        result.skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Force LF + UTF-8 so artifacts generated on Windows still run inside the
    # Linux container (CRLF in start.sh/Dockerfile breaks the shebang). The
    # open() form is used instead of Path.write_text(newline=...) because the
    # newline kwarg only exists on write_text since Python 3.10 and the floor
    # here is 3.9.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result.written.append(path)


def _pip_install_block(pkg_manager):
    """The Dockerfile dependency-install snippet for the chosen package manager.

    Two shapes, both uv. The greenfield/uv path installs from pyproject.toml (the
    real-server-verified path). Every retrofit manager (req_txt/poetry/pipenv)
    installs from a requirements.txt with uv - generated at deploy time from the
    user's lock for poetry/pipenv - so poetry/pipenv never run inside the image.
    """
    if pkg_manager == "uv":
        return (
            "COPY pyproject.toml /app/code/pyproject.toml\n"
            "RUN $VENV_PATH/bin/pip install --no-cache-dir --upgrade pip uv && \\\n"
            "    cd /app/code && \\\n"
            "    uv pip install --python $VENV_PATH/bin/python -r pyproject.toml"
        )
    # req_txt / poetry / pipenv: install from requirements.txt with uv.
    return (
        "COPY requirements.txt /app/code/requirements.txt\n"
        "RUN $VENV_PATH/bin/pip install --no-cache-dir --upgrade pip uv && \\\n"
        "    uv pip install --python $VENV_PATH/bin/python -r /app/code/requirements.txt"
    )


def render_dockerfile(config):
    """Render the Dockerfile for the project's package manager."""
    return _render_template("dockerfile", _context(config))


def render_start_sh(config):
    """Render the root-run start script."""
    return _render_template("start.sh", _context(config))


def render_nginx_conf(config):
    """Render the nginx config that fronts gunicorn."""
    return _render_template("nginx.conf", _context(config))


def render_supervisor_confs(config):
    """Return {output_filename: contents} for the enabled supervisor programs."""
    context = _context(config)
    confs = {
        "gunicorn.conf": _render_template("supervisor_gunicorn.conf", context),
        "nginx.conf": _render_template("supervisor_nginx.conf", context),
    }
    if config.enable_celery:
        confs["celery-worker.conf"] = _render_template(
            "supervisor_celery_worker.conf", context
        )
        confs["celery-beat.conf"] = _render_template(
            "supervisor_celery_beat.conf", context
        )
    return confs


def render_readme(config):
    """Render the per-project Cloudron control-surface README."""
    return _render_template("readme_cloudron.md", _context(config))


def render_dockerignore(config):
    """Render the .dockerignore (static text; config reserved for future use)."""
    return _render_template("dockerignore", _context(config))


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
                "message": "Retrieve and secure the generated admin password",
            }
        },
        "postInstallMessage": (
            "This app was configured with dsd-cloudron. A local admin account "
            "`admin` was created; its generated password is on the server at "
            "/app/data/.initial_admin_password (read it with `cloudron exec`). "
            "Read it during this first-boot window: the file is removed "
            "automatically on the next start once the app is initialized. If you "
            "miss it, reset the password with `cloudron exec` and `manage.py "
            "changepassword admin`.\n\n"
            "<nosso>\n"
            "Sign in at /admin/ with that account, then change the password "
            "immediately.\n"
            "</nosso>\n\n"
            "<sso>\n"
            "Sign in with your Cloudron account. The `admin` account above is a "
            "local break-glass admin; use it (or `cloudron exec`) to promote your "
            "Cloudron user in the Django admin.\n"
            "</sso>\n\n"
            "See README-cloudron.md in the app source for the full configuration "
            "control surface."
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
        '    ALLOWED_HOSTS = [os.environ["CLOUDRON_APP_DOMAIN"]]\n'
        '    CSRF_TRUSTED_ORIGINS = [os.environ["CLOUDRON_APP_ORIGIN"]]\n'
        '    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")\n'
        "    SESSION_COOKIE_SECURE = True\n"
        "    CSRF_COOKIE_SECURE = True\n"
        # Restate Django's own secure defaults so the headers stay correct if a
        # project overrode them or a future Django default relaxes. same-origin is
        # already Django's default; do not regress to a looser cross-origin policy.
        # These apply only when SecurityMiddleware is in MIDDLEWARE (greenfield has
        # it; a retrofit project may not - best-effort).
        "    SECURE_CONTENT_TYPE_NOSNIFF = True\n"
        '    SECURE_REFERRER_POLICY = "same-origin"\n'
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
            "    EMAIL_USE_SSL = False\n"
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

    # Exec an operator override only when the file is owned by root and not
    # group/other-writable. The app runs as `cloudron`, which cannot chown a file
    # to root, so an attacker-dropped file (e.g. via a media-upload path traversal
    # into /app/data) stays cloudron-owned and is skipped; an operator file created
    # as root via `cloudron exec` runs. lstat (not stat) so a cloudron-owned symlink
    # to a root file does not pass. exec sits OUTSIDE the read try: a SyntaxError in
    # a trusted root-owned override should propagate, not be swallowed. start.sh
    # excludes this file from its recursive chown so the ownership signal survives.
    blocks.append(
        '    _custom_settings = "/app/data/custom_settings.py"\n'
        "    try:\n"
        "        _st = os.lstat(_custom_settings)\n"
        "    except OSError:\n"
        "        _st = None\n"
        "    if _st is not None:\n"
        "        _is_symlink = (_st.st_mode & 0o170000) == 0o120000\n"
        "        if _st.st_uid == 0 and not _is_symlink and not (_st.st_mode & 0o022):\n"
        "            try:\n"
        '                with open(_custom_settings, encoding="utf-8") as _f:\n'
        "                    _code = _f.read()\n"
        "            except OSError as _exc:\n"
        "                import sys as _sys\n"
        '                print(f"custom_settings.py present but unreadable ({_exc}); skipping", file=_sys.stderr)\n'
        "            else:\n"
        "                exec(_code)\n"
        "        else:\n"
        "            import sys as _sys\n"
        '            print("custom_settings.py must be owned by root and not group/other-writable (create it root:cloudron mode 640 via cloudron exec); skipping", file=_sys.stderr)\n'
    )

    return "\n".join(blocks)


def render_celery_app(config):
    """Render the <project>/celery.py module the Celery programs import.

    The worker/beat supervisor confs run `celery -A <project>`, which needs this
    module to define `app`. Rendering it here (rather than in a deployer) keeps
    the packaging core's Celery output self-contained, so the retrofit deployer
    and the greenfield scaffolder share one definition that cannot drift from the
    supervisor confs.
    """
    return _render_template("celery_app", _context(config))


def render_all(config, target_dir, force=False):
    """Write the full Cloudron artifact set into target_dir.

    Not transactional: files are written one at a time, so an I/O failure
    partway through can leave target_dir partially rendered. Callers (the
    deployer, the scaffolder) own recovery; the returned RenderResult lists
    exactly what was written and what was skipped.
    """
    target_dir = Path(target_dir)
    pkg_dir = target_dir / config.project_name
    supervisor_dir = target_dir / "supervisor"
    result = RenderResult(written=[], skipped=[])

    _write(target_dir / "CloudronManifest.json", render_manifest(config), result, force)
    _write(target_dir / "Dockerfile", render_dockerfile(config), result, force)
    _write(
        target_dir / "start.sh",
        render_start_sh(config),
        result,
        force,
        executable=True,
    )
    _write(target_dir / "nginx.conf", render_nginx_conf(config), result, force)
    _write(target_dir / ".dockerignore", render_dockerignore(config), result, force)
    _write(target_dir / "README-cloudron.md", render_readme(config), result, force)
    _write(
        pkg_dir / "cloudron_settings.py",
        render_cloudron_settings(config),
        result,
        force,
    )
    # celery.py belongs to the project package and only exists when Celery is on;
    # the worker/beat supervisor confs below import it.
    if config.enable_celery:
        _write(pkg_dir / "celery.py", render_celery_app(config), result, force)
    for name, contents in render_supervisor_confs(config).items():
        _write(supervisor_dir / name, contents, result, force)

    return result
