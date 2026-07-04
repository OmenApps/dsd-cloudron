"""Assemble a minimal req_txt retrofit Django project for the CI build smoke test.

The offline unit suite proves render_all() produces byte-perfect artifacts; this
module produces a real, buildable project so CI can build and boot the
requirements.txt Dockerfile shape. It writes a minimal Django project, then
renders the Cloudron artifact set into it through the shared packaging core - the
same render_all() the retrofit deployer calls.
"""

from pathlib import Path

from dsd_cloudron.packaging import CloudronAppConfig, render_all

PROJECT_NAME = "smoke"

_MANAGE_PY = """\
#!/usr/bin/env python3
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smoke.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
"""

_SETTINGS_PY = '''\
"""Minimal settings for the CI build smoke-test project.

The local defaults here are overridden on Cloudron by cloudron_settings, which
the import at the bottom activates only when CLOUDRON_APP_ORIGIN is set.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "insecure-local-only-overridden-on-cloudron"
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "smoke.urls"
WSGI_APPLICATION = "smoke.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Activates the Cloudron overrides when CLOUDRON_APP_ORIGIN is present; inert
# locally and during the image build. Mirrors what the retrofit deployer appends.
from .cloudron_settings import *  # noqa: E402,F401,F403
'''

_URLS_PY = """\
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path


def health(request):
    return HttpResponse("ok")


urlpatterns = [
    path("", health),
    path("admin/", admin.site.urls),
]
"""

_WSGI_PY = """\
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smoke.settings")
application = get_wsgi_application()
"""

_REQUIREMENTS = """\
Django>=4.2
gunicorn>=21
psycopg[binary]>=3.1
django-redis>=5.4
"""


def assemble_retrofit_sample(target_dir):
    """Write the minimal project into target_dir and render the artifact set.

    target_dir may be a str or Path and must already exist. On return it holds a
    buildable requirements.txt-shape Cloudron project.
    """
    target_dir = Path(target_dir)
    pkg_dir = target_dir / PROJECT_NAME
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "manage.py").write_text(_MANAGE_PY)
    (target_dir / "requirements.txt").write_text(_REQUIREMENTS)
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "settings.py").write_text(_SETTINGS_PY)
    (pkg_dir / "urls.py").write_text(_URLS_PY)
    (pkg_dir / "wsgi.py").write_text(_WSGI_PY)

    config = CloudronAppConfig(
        project_name=PROJECT_NAME,
        app_id="com.example.smoke",
        pkg_manager="req_txt",
        enable_redis=True,
        enable_sendmail=False,
        enable_celery=False,
        enable_sso=False,
        health_check_path="/",
    )
    render_all(config, target_dir)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print(
            "usage: python tests/build_tests/assemble_retrofit_sample.py <dir>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    assemble_retrofit_sample(out)
    print(f"assembled retrofit sample into {out}")
