"""Cloudron settings, appended to the project settings via `from .cloudron_settings import *`.

Active only on Cloudron: the whole block is gated on CLOUDRON_APP_ORIGIN,
so it stays inert during local development and during the image build.
"""
import os

if os.environ.get("CLOUDRON_APP_ORIGIN"):
    DEBUG = False

    SECRET_KEY = os.environ["SECRET_KEY"]

    ALLOWED_HOSTS = [os.environ["CLOUDRON_APP_DOMAIN"]]
    CSRF_TRUSTED_ORIGINS = [os.environ["CLOUDRON_APP_ORIGIN"]]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["CLOUDRON_POSTGRESQL_DATABASE"],
            "USER": os.environ["CLOUDRON_POSTGRESQL_USERNAME"],
            "PASSWORD": os.environ["CLOUDRON_POSTGRESQL_PASSWORD"],
            "HOST": os.environ["CLOUDRON_POSTGRESQL_HOST"],
            "PORT": os.environ["CLOUDRON_POSTGRESQL_PORT"],
            "CONN_MAX_AGE": 60,
        }
    }

    STATIC_URL = "/static/"
    STATIC_ROOT = "/run/blog/static"
    MEDIA_URL = "/media/"
    MEDIA_ROOT = "/app/data/media"

    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": os.environ["CLOUDRON_REDIS_URL"],
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }

    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["CLOUDRON_MAIL_SMTP_SERVER"]
    EMAIL_PORT = int(os.environ["CLOUDRON_MAIL_SMTP_PORT"])
    EMAIL_HOST_USER = os.environ["CLOUDRON_MAIL_SMTP_USERNAME"]
    EMAIL_HOST_PASSWORD = os.environ["CLOUDRON_MAIL_SMTP_PASSWORD"]
    EMAIL_USE_TLS = False
    EMAIL_USE_SSL = False
    DEFAULT_FROM_EMAIL = os.environ.get("CLOUDRON_MAIL_FROM", "")
    SERVER_EMAIL = DEFAULT_FROM_EMAIL

    _custom_settings = "/app/data/custom_settings.py"
    if os.path.exists(_custom_settings):
        with open(_custom_settings, encoding="utf-8") as _f:
            exec(_f.read())
