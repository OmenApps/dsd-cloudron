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
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_SSL_REDIRECT = True
    # HSTS starts conservative; raise toward a year (31536000) once HTTPS is
    # confirmed end to end. Leave INCLUDE_SUBDOMAINS and PRELOAD off - preload
    # is a hard-to-reverse commitment.
    SECURE_HSTS_SECONDS = 3600

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
    try:
        _st = os.lstat(_custom_settings)
    except OSError:
        _st = None
    if _st is not None:
        _is_symlink = (_st.st_mode & 0o170000) == 0o120000
        if _st.st_uid == 0 and not _is_symlink and not (_st.st_mode & 0o022):
            try:
                with open(_custom_settings, encoding="utf-8") as _f:
                    _code = _f.read()
            except OSError as _exc:
                import sys as _sys
                print(f"custom_settings.py present but unreadable ({_exc}); skipping", file=_sys.stderr)
            else:
                exec(_code)
        else:
            import sys as _sys
            print("custom_settings.py must be owned by root and not group/other-writable (create it root:cloudron mode 640 via cloudron exec); skipping", file=_sys.stderr)
