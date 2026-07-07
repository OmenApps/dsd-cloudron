"""The dsd-cloudron packaging core.

Single source of truth for the generated Cloudron artifact set. Pure render
functions: no network, no `cloudron` CLI, no django-simple-deploy core. Both the
retrofit deployer and the greenfield scaffolder call render_all().
"""

import difflib
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
    enable_wagtail: bool = False
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
    # The dotted settings module the CONTAINER must load. Empty means the
    # <project>.settings default (a flat settings.py). The retrofit deployer sets it
    # to the module django-simple-deploy actually appended the Cloudron import to:
    # for a split-settings Wagtail project that is <project>.settings.production, not
    # the <project>.settings.dev that wsgi/manage.py/celery default to.
    settings_module: str = ""

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

    @property
    def ships_retrofit_adapters(self):
        """True when this deploy writes cloudron_adapters.py and points the allauth
        adapters at it: retrofit SSO only. Greenfield brings its own
        accounts/adapters.py and wires the pointers in its own settings.py, so it
        must never claim or reference the retrofit module. The settings pointers,
        the file write, and the changes summary all gate on this one signal."""
        return self.enable_sso and not self.greenfield


def _context(config):
    """Template context shared by the flat-text render functions.

    Only the variables the flat templates actually reference are included.
    Most conditional logic (addons, settings blocks, supervisor programs) lives
    in Python, not in the templates; the exception is readme_cloudron.md, whose
    SSO and Wagtail sections branch on greenfield/enable_sso and enable_wagtail.
    Values must be str or bool: the standalone Engine localizes non-string
    ints/floats through global settings during rendering, which raises offline,
    but bools are safe.
    """
    # Pin DJANGO_SETTINGS_MODULE as a Dockerfile ENV when it differs from the
    # <project>.settings default. A split-settings (Wagtail) project has the Cloudron
    # gate appended to settings/production.py while wsgi/manage.py/celery default to
    # settings/dev, so without a pin every container process loads the ungated dev
    # settings - and so does a `cloudron exec` shell, where `manage.py changepassword
    # admin` recovery then hits SQLite on the read-only rootfs ("unable to open
    # database file"). Baking it into the image ENV covers the supervisor process tree
    # AND exec shells; a start.sh export would reach only the former. The flat-settings
    # case emits nothing, so the Dockerfile stays byte-for-byte identical there.
    effective_settings_module = (
        config.settings_module or f"{config.project_name}.settings"
    )
    if effective_settings_module == f"{config.project_name}.settings":
        settings_module_env = ""
    else:
        settings_module_env = (
            "# Pin the production settings module so `cloudron exec` shells (e.g. for\n"
            "# `manage.py changepassword admin`) load it too, not the project's dev default.\n"
            f'ENV DJANGO_SETTINGS_MODULE="{effective_settings_module}"\n'
        )
    return {
        "project_name": config.project_name,
        "http_port": str(config.http_port),
        "pip_install_block": _pip_install_block(config.pkg_manager),
        # Real bools, not str(): a stringified "False" is truthy in a Django
        # template and would flip the readme's SSO branch to the wired claim.
        "greenfield": config.greenfield,
        "enable_sso": config.enable_sso,
        "enable_wagtail": config.enable_wagtail,
        # An `ENV DJANGO_SETTINGS_MODULE=...` block (with its explanatory comment)
        # for a split-settings project, or "" for the flat-settings default.
        "settings_module_env": settings_module_env,
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
    # Linux container (CRLF in start.sh/Dockerfile breaks the shebang).
    path.write_text(contents, encoding="utf-8", newline="\n")
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


def apply_manifest_values(config, manifest_path):
    """Sync the two flag-controlled scalar values into an existing CloudronManifest.json.

    Reconfigure changes only memoryLimit and healthCheckPath and writes the file
    back. The addon set is left exactly as it is on disk: reconfigure's stack guard
    has already proven the config declares the same addons, so there is nothing to
    change and, crucially, no addon can be silently dropped by a mismatched flag.
    Every other top-level key (title, author, id, checklist, addons, httpPort, ...)
    survives. Returns True when a scalar actually changed and the file was rewritten.
    """
    manifest_path = Path(manifest_path)
    # Reconfigure's stack guard already parsed this file, but this is a fresh read
    # (the file could change between the two), so guard it the same way rather than
    # assuming well-formed input - a bad shape here would corrupt the write below.
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReconfigureError(
            f"{manifest_path.name} could not be read as UTF-8 JSON ({error}); fix it "
            "before reconfiguring."
        ) from error
    if not isinstance(data, dict):
        raise ReconfigureError(
            f"{manifest_path.name} is not a JSON object; fix it before reconfiguring."
        )

    # Compare the parsed values, not the serialized text: an operator who reformatted
    # the manifest (different indentation, key order, trailing newline) but left the
    # two scalars alone should see no rewrite and no "changed" signal, so reconfigure
    # does not fire a spurious "run cloudron update" reminder for a cosmetic-only edit.
    if (
        data.get("memoryLimit") == config.memory_limit
        and data.get("healthCheckPath") == config.health_check_path
    ):
        return False

    data["memoryLimit"] = config.memory_limit
    data["healthCheckPath"] = config.health_check_path
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


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
        # The addon and env-var surface is verified against Cloudron 8.0.2; gate
        # installs to that baseline so a materially older box is rejected up front
        # rather than failing partway through a deploy.
        "minBoxVersion": "8.0.0",
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
            "/app/data/.initial_admin_password. Read it with `cloudron exec --app "
            "<subdomain> -- cat /app/data/.initial_admin_password`, then mark it "
            "retrieved so the file is removed: `cloudron exec --app <subdomain> -- "
            "touch /app/data/.initial_admin_password.acknowledged`. Until you "
            "acknowledge, start.sh keeps the file and reprints these steps every "
            "boot, so a restart cannot strand it. If you lose it, reset the "
            "password with `cloudron exec` and `manage.py changepassword admin`.\n\n"
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
        "    # start.sh generates and exports SECRET_KEY, but only into its own\n"
        "    # process tree; a `cloudron exec` shell (the documented `changepassword\n"
        "    # admin` recovery) has none, so fall back to the key file start.sh writes\n"
        "    # to /app/data (mode 600) when the env var is absent.\n"
        '    SECRET_KEY = os.environ.get("SECRET_KEY") or open("/app/data/.secret_key").read().strip()\n\n'
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
        "    # TLS is enforced at the Cloudron edge; nginx.conf pins X-Forwarded-Proto\n"
        "    # to https, so SECURE_PROXY_SSL_HEADER always reads secure and this redirect\n"
        "    # never actually fires. It is defense in depth, and that pinned header is the\n"
        "    # load-bearing invariant - reflecting $scheme instead would 301-loop the\n"
        "    # internal health probe. Keep the two in step.\n"
        "    SECURE_SSL_REDIRECT = True\n"
        "    # HSTS starts conservative; raise toward a year (31536000) once HTTPS is\n"
        "    # confirmed end to end. Leave INCLUDE_SUBDOMAINS and PRELOAD off - preload\n"
        "    # is a hard-to-reverse commitment.\n"
        "    SECURE_HSTS_SECONDS = 3600\n"
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

    if config.enable_wagtail:
        blocks.append(
            '    WAGTAILADMIN_BASE_URL = os.environ["CLOUDRON_APP_ORIGIN"]\n'
            "    # Force the database search backend on Cloudron. If the project\n"
            "    # configured Elasticsearch or OpenSearch (not available here without\n"
            "    # that addon), this keeps search working on Postgres full-text.\n"
            "    WAGTAILSEARCH_BACKENDS = {\n"
            '        "default": {"BACKEND": "wagtail.search.backends.database"},\n'
            "    }\n"
        )

    if config.enable_sso:
        # The retrofit path ships cloudron_adapters.py and points the allauth
        # adapters at it here, so applying the wiring block closes local signup
        # without hand-authoring an adapter. Greenfield sets these in its own
        # settings.py against its accounts app, so skip them there to avoid a
        # double set that would name a module greenfield does not ship.
        adapter_pointers = ""
        if config.ships_retrofit_adapters:
            adapter_pointers = (
                f'    ACCOUNT_ADAPTER = "{p}.cloudron_adapters.NoSignupAccountAdapter"\n'
                f'    SOCIALACCOUNT_ADAPTER = "{p}.cloudron_adapters.CloudronSocialAccountAdapter"\n'
            )
        blocks.append(
            adapter_pointers + '    if os.environ.get("CLOUDRON_OIDC_DISCOVERY_URL"):\n'
            "        SOCIALACCOUNT_PROVIDERS = {\n"
            '            "openid_connect": {\n'
            '                "APPS": [\n'
            "                    {\n"
            '                        "provider_id": "cloudron",\n'
            '                        "name": os.environ.get("CLOUDRON_OIDC_PROVIDER_NAME", "Cloudron"),\n'
            '                        "client_id": os.environ["CLOUDRON_OIDC_CLIENT_ID"],\n'
            '                        "secret": os.environ["CLOUDRON_OIDC_CLIENT_SECRET"],\n'
            '                        "settings": {"server_url": os.environ["CLOUDRON_OIDC_DISCOVERY_URL"]},\n'
            "                    }\n"
            "                ]\n"
            "            }\n"
            "        }\n"
        )

    # Exec an operator override only when the file is owned by root and not
    # group/other-writable. The app runs as `cloudron`, which cannot chown a file
    # to root, so an attacker-dropped file (e.g. via a media-upload path traversal
    # into /app/data) stays cloudron-owned and is skipped; an operator file created
    # as root via `cloudron exec` runs. Open once with O_NOFOLLOW (fails on a
    # final-component symlink) and O_NONBLOCK, then fstat/read that same fd, so the
    # inode checked is the inode read - no lstat-then-open TOCTOU window an attacker
    # could swap through. O_NONBLOCK and the S_IFREG (regular-file) check matter
    # because the open precedes the ownership check: a cloudron-owned FIFO dropped at
    # this path would otherwise block a read-only open forever and hang startup; with
    # O_NONBLOCK the open returns at once and the non-regular file is then skipped.
    # exec sits OUTSIDE the read try: a SyntaxError in a trusted
    # root-owned override should propagate, not be swallowed. start.sh excludes this
    # file from its recursive chown so the ownership signal survives.
    blocks.append(
        '    _custom_settings = "/app/data/custom_settings.py"\n'
        "    try:\n"
        "        _fd = os.open(_custom_settings, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)\n"
        "    except FileNotFoundError:\n"
        "        _fd = None\n"
        "    except OSError:\n"
        "        _fd = None\n"
        "        import sys as _sys\n"
        '        print("custom_settings.py must be owned by root and not group/other-writable (create it root:cloudron mode 640 via cloudron exec); skipping", file=_sys.stderr)\n'
        "    if _fd is not None:\n"
        "        _code = None\n"
        "        _st = os.fstat(_fd)\n"
        "        if _st.st_uid == 0 and (_st.st_mode & 0o170000) == 0o100000 and not (_st.st_mode & 0o022):\n"
        "            try:\n"
        '                with os.fdopen(_fd, encoding="utf-8") as _f:\n'
        "                    _code = _f.read()\n"
        "            except OSError as _exc:\n"
        "                import sys as _sys\n"
        '                print(f"custom_settings.py present but unreadable ({_exc}); skipping", file=_sys.stderr)\n'
        "        else:\n"
        "            os.close(_fd)\n"
        "            import sys as _sys\n"
        '            print("custom_settings.py must be owned by root and not group/other-writable (create it root:cloudron mode 640 via cloudron exec); skipping", file=_sys.stderr)\n'
        "        if _code is not None:\n"
        "            exec(_code)\n"
    )

    # Fail closed on a Cloudron image whose CLOUDRON_APP_ORIGIN is somehow absent.
    # The whole hardening block above is gated on that var; without this branch a
    # missing origin would silently fall back to the project's local-development
    # settings (DEBUG on, ALLOWED_HOSTS ["*"], throwaway SECRET_KEY). DSD_CLOUDRON_IMAGE
    # is baked into the image by the generated Dockerfile and is never set in local
    # development, so this refuses to boot in production instead of serving insecurely,
    # while leaving local runs on their normal defaults.
    blocks.append(
        'elif os.environ.get("DSD_CLOUDRON_IMAGE"):\n'
        "    raise RuntimeError(\n"
        '        "CLOUDRON_APP_ORIGIN is unset on a Cloudron image; refusing to start "\n'
        '        "with insecure development settings."\n'
        "    )\n"
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


def render_cloudron_adapters(config):
    """Render the standalone allauth adapters for an assisted retrofit SSO wiring.

    Shipped into the retrofit project package as cloudron_adapters.py so the operator
    can point ACCOUNT_ADAPTER/SOCIALACCOUNT_ADAPTER at a real file instead of
    hand-authoring one. The greenfield scaffolder ships its own accounts/adapters.py,
    so render_all writes this only for the retrofit path (enable_sso and not greenfield).
    """
    return _render_template("cloudron_adapters", _context(config))


def _planned_artifacts(config, target_dir):
    """Yield (path, contents, executable) for every file render_all writes.

    One enumeration of the artifact set, so render_all (skip/force) and reconfigure
    (diff-and-confirm) cannot drift on which files exist. The manifest is yielded
    first; reconfigure handles it surgically rather than by diff.
    """
    target_dir = Path(target_dir)
    pkg_dir = target_dir / config.project_name
    supervisor_dir = target_dir / "supervisor"

    yield target_dir / "CloudronManifest.json", render_manifest(config), False
    yield target_dir / "Dockerfile", render_dockerfile(config), False
    yield target_dir / "start.sh", render_start_sh(config), True
    yield target_dir / "nginx.conf", render_nginx_conf(config), False
    yield target_dir / ".dockerignore", render_dockerignore(config), False
    yield target_dir / "README-cloudron.md", render_readme(config), False
    yield pkg_dir / "cloudron_settings.py", render_cloudron_settings(config), False
    # Gate on the property render_all uses, not a re-inlined expression, so the
    # single "does this deploy ship the retrofit adapters" signal cannot drift.
    if config.ships_retrofit_adapters:
        yield pkg_dir / "cloudron_adapters.py", render_cloudron_adapters(config), False
    if config.enable_celery:
        yield pkg_dir / "celery.py", render_celery_app(config), False
    for name, contents in render_supervisor_confs(config).items():
        yield supervisor_dir / name, contents, False


def render_all(config, target_dir, force=False):
    """Write the full Cloudron artifact set into target_dir.

    Not transactional: files are written one at a time, so an I/O failure partway
    through can leave target_dir partially rendered. Callers (the deployer, the
    scaffolder) own recovery; the returned RenderResult lists exactly what was
    written and what was skipped.
    """
    result = RenderResult(written=[], skipped=[])
    for path, contents, executable in _planned_artifacts(config, target_dir):
        _write(path, contents, result, force, executable=executable)
    return result


@dataclass
class ReconfigureResult:
    overwritten: list  # paths whose diff the operator accepted
    unchanged: list  # paths identical on disk (never prompted)
    declined: list  # paths with a diff the operator rejected
    manifest_changed: bool

    @property
    def changed(self):
        """True when reconfigure wrote something worth rolling out - an artifact
        overwrite or a manifest scalar sync. Both entry points key their "run cloudron
        update" reminder on this, so the predicate lives here rather than being restated.
        """
        return bool(self.overwritten or self.manifest_changed)


class ReconfigureError(Exception):
    """Reconfigure cannot proceed: the project is not deployed, or the resolved
    config would change which stacks are enabled. Callers translate this into their
    own clean abort (a DSDCommandError for retrofit, a _fail for greenfield)."""


_MANIFEST_NAME = "CloudronManifest.json"

# The stack flags reconfigure must not change: each needs dependencies, app wiring,
# or supervisor programs reconfigure never touches. redis/sendmail/sso are visible
# in the manifest addons; celery is visible as its supervisor program.
_STACK_FLAGS = ("enable_redis", "enable_sendmail", "enable_sso", "enable_celery")


def _stack_flags_from_disk(target_dir):
    """Reconstruct the enabled-stack flags a deployed project already declares.

    redis/sendmail/sso are read back from the manifest addons; celery from the
    presence of its supervisor program. This is the deployed truth reconfigure
    compares the resolved config against, so a re-render can never quietly turn a
    stack on (deps absent) or off (a stale supervisor conf the platform still runs).
    """
    target_dir = Path(target_dir)
    try:
        data = json.loads((target_dir / _MANIFEST_NAME).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        # A non-UTF-8 manifest raises UnicodeDecodeError before json even parses it;
        # translate both into the same clean abort (this runs before any write, so
        # nothing is half-written) rather than letting one leak as a raw traceback.
        raise ReconfigureError(
            f"{_MANIFEST_NAME} could not be read as UTF-8 JSON ({error}); fix it "
            "before reconfiguring."
        ) from error
    # A syntactically valid manifest of the wrong shape (a top-level array, or addons
    # set to null) would otherwise slip past the decode guard and raise a raw
    # AttributeError/TypeError; keep it a clean abort like the malformed-JSON case.
    if not isinstance(data, dict):
        raise ReconfigureError(
            f"{_MANIFEST_NAME} is not a JSON object; fix it before reconfiguring."
        )
    addons = data.get("addons", {})
    if not isinstance(addons, dict):
        raise ReconfigureError(
            f'{_MANIFEST_NAME} "addons" is not a JSON object; fix it before reconfiguring.'
        )
    return {
        "enable_redis": "redis" in addons,
        "enable_sendmail": "sendmail" in addons,
        "enable_sso": "oidc" in addons,
        "enable_celery": (target_dir / "supervisor" / "celery-worker.conf").exists(),
    }


def _unified_diff(before, after, label):
    """A unified diff between two artifact texts, labeled for the operator."""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{label} (current)",
        tofile=f"{label} (new)",
    )
    return "".join(lines)


def reconfigure(config, target_dir, confirm, output):
    """Re-render the deployed artifact set with a review-before-overwrite policy.

    Preconditions (raise ReconfigureError, never write): the project must already be
    deployed (its manifest exists), and the resolved config must declare the same
    stacks the deployed project does. Reconfigure renders artifacts but never installs
    dependencies, wires the celery __init__, or adds/removes supervisor programs, so
    it cannot enable or disable a stack; it refuses rather than ship a broken image.

    For every artifact except the manifest, compute a unified diff between the on-disk
    file and the freshly rendered content:
      - identical -> reported as "no change", never prompted, never written;
      - different (or missing) -> the diff is emitted via output(), then confirm(path)
        decides whether to overwrite.
    An unreviewed file is never touched. The manifest is never diffed: its two
    flag-controlled scalars (memoryLimit, healthCheckPath) are synced with
    apply_manifest_values after the loop.

    confirm(path) -> bool: ask the operator whether to overwrite `path` (the diff has
      already been emitted via output). The retrofit path passes core's
      get_confirmation; the greenfield path passes a plain input() prompt.
    output(message): emit a progress or diff line.
    """
    target_dir = Path(target_dir)
    manifest_path = target_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        raise ReconfigureError(
            f"no {_MANIFEST_NAME} in {target_dir}: reconfigure re-renders an "
            "already-deployed project. Run a normal deploy first."
        )
    on_disk = _stack_flags_from_disk(target_dir)
    changed = [name for name in _STACK_FLAGS if getattr(config, name) != on_disk[name]]
    if changed:
        stacks = ", ".join(name[len("enable_") :] for name in changed)
        raise ReconfigureError(
            f"reconfigure cannot change which stacks are enabled ({stacks}); it does "
            "not install dependencies or wire apps. Re-run a full deploy (retrofit) "
            "or re-scaffold (greenfield) to change a stack."
        )

    result = ReconfigureResult(
        overwritten=[], unchanged=[], declined=[], manifest_changed=False
    )
    for path, contents, executable in _planned_artifacts(config, target_dir):
        if path.name == _MANIFEST_NAME:
            continue  # synced surgically after the loop, never diffed
        rel = path.relative_to(target_dir)
        try:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
        except UnicodeDecodeError as error:
            # A hand-edited artifact saved in a non-UTF-8 encoding cannot be diffed;
            # abort cleanly (as ReconfigureError, which both callers translate) rather
            # than raising a raw UnicodeDecodeError - a ValueError the retrofit caller's
            # OSError handler would miss.
            raise ReconfigureError(
                f"{rel} on disk is not valid UTF-8 ({error}); reconfigure cannot diff "
                "it. Fix or remove the file, then reconfigure again."
            ) from error
        if current == contents:
            result.unchanged.append(path)
            output(f"  No change: {rel}")
            continue
        output(_unified_diff(current, contents, rel))
        if confirm(path):
            # The diff-and-confirm already ran, so this is an unconditional write; a
            # throwaway RenderResult keeps _write's signature satisfied.
            _write(
                path, contents, RenderResult([], []), force=True, executable=executable
            )
            result.overwritten.append(path)
            output(f"  Overwrote {rel}")
        else:
            result.declined.append(path)
            output(f"  Left unchanged: {rel}")

    result.manifest_changed = apply_manifest_values(config, manifest_path)
    rel = manifest_path.relative_to(target_dir)
    output(f"  Updated {rel}" if result.manifest_changed else f"  No change: {rel}")
    return result
