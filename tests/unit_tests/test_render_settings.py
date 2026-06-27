import ast
import itertools

import pytest

from dsd_cloudron.packaging import CloudronAppConfig, render_cloudron_settings


def _settings(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_cloudron_settings(config)


# Every VALID toggle combination must assemble to syntactically valid Python.
# Celery-without-Redis is rejected by CloudronAppConfig, so it is filtered out
# (the condition `redis or not celery`). This exercises the indentation-sensitive
# sso and celery blocks under all permitted combinations, not just the default.
_VALID_COMBOS = [
    (redis, celery, sendmail, sso)
    for redis, celery, sendmail, sso in itertools.product([False, True], repeat=4)
    if redis or not celery
]


@pytest.mark.parametrize("redis,celery,sendmail,sso", _VALID_COMBOS)
def test_settings_is_valid_python(redis, celery, sendmail, sso):
    text = _settings(
        enable_redis=redis,
        enable_celery=celery,
        enable_sendmail=sendmail,
        enable_sso=sso,
    )
    ast.parse(text)  # raises SyntaxError if the generated module is broken


def test_settings_on_cloudron_gate_and_core():
    text = _settings()
    assert 'if os.environ.get("CLOUDRON_APP_ORIGIN"):' in text
    assert "DEBUG = False" in text
    assert 'SECRET_KEY = os.environ["SECRET_KEY"]' in text
    assert "SECURE_PROXY_SSL_HEADER" in text
    assert '"django.db.backends.postgresql"' in text
    assert 'STATIC_ROOT = "/run/blog/static"' in text


def test_settings_redis_conditional():
    on = _settings(enable_redis=True)
    off = _settings(enable_redis=False)
    assert "django_redis.cache.RedisCache" in on
    assert "django_redis.cache.RedisCache" not in off
    assert 'os.environ["CLOUDRON_REDIS_URL"]' in on


def test_settings_celery_conditional():
    on = _settings(enable_celery=True)
    off = _settings(enable_celery=False)
    assert "CELERY_BROKER_URL" in on
    assert "CELERY_BROKER_URL" not in off


def test_settings_sendmail_conditional():
    on = _settings(enable_sendmail=True)
    off = _settings(enable_sendmail=False)
    assert "EMAIL_HOST" in on
    assert "EMAIL_USE_TLS = False" in on
    assert "EMAIL_HOST" not in off


def test_settings_sso_conditional():
    on = _settings(enable_sso=True)
    off = _settings(enable_sso=False)
    assert "SOCIALACCOUNT_PROVIDERS" in on
    assert 'os.environ.get("CLOUDRON_OIDC_ISSUER")' in on
    # server_url must be the discovery document, not the bare issuer.
    assert "/.well-known/openid-configuration" in on
    assert "SOCIALACCOUNT_PROVIDERS" not in off


def test_settings_custom_override_hook_last():
    text = _settings()
    assert "/app/data/custom_settings.py" in text
    # The exec hook must be the final statement so operator overrides win.
    assert text.rstrip().endswith("exec(_f.read())")


def test_settings_execute_default_config(monkeypatch):
    # ast.parse proves syntax; this proves semantics. Execute the generated
    # module under a Cloudron-like environment and assert the bindings that
    # matter actually land with the right values (a misnamed key or a block that
    # escaped the ON_CLOUDRON gate would pass ast.parse but fail here).
    env = {
        "CLOUDRON_APP_ORIGIN": "https://blog.example.com",
        "CLOUDRON_APP_DOMAIN": "blog.example.com",
        "SECRET_KEY": "test-key",
        "CLOUDRON_POSTGRESQL_DATABASE": "app",
        "CLOUDRON_POSTGRESQL_USERNAME": "app",
        "CLOUDRON_POSTGRESQL_PASSWORD": "pw",
        "CLOUDRON_POSTGRESQL_HOST": "127.0.0.1",
        "CLOUDRON_POSTGRESQL_PORT": "5432",
        "CLOUDRON_REDIS_URL": "redis://127.0.0.1:6379/0",
        "CLOUDRON_MAIL_SMTP_SERVER": "mail",
        "CLOUDRON_MAIL_SMTP_PORT": "25",
        "CLOUDRON_MAIL_SMTP_USERNAME": "app",
        "CLOUDRON_MAIL_SMTP_PASSWORD": "pw",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    namespace = {}
    exec(compile(_settings(), "<cloudron_settings>", "exec"), namespace)

    assert namespace["DEBUG"] is False
    assert namespace["SECRET_KEY"] == "test-key"
    assert namespace["ALLOWED_HOSTS"] == ["blog.example.com"]
    assert namespace["STATIC_ROOT"] == "/run/blog/static"
    assert (
        namespace["DATABASES"]["default"]["ENGINE"] == "django.db.backends.postgresql"
    )
    assert namespace["CACHES"]["default"]["BACKEND"] == "django_redis.cache.RedisCache"
    assert namespace["EMAIL_USE_TLS"] is False
    assert namespace["EMAIL_USE_SSL"] is False


def test_settings_inert_without_cloudron_origin(monkeypatch):
    # Off Cloudron the whole block is gated out, so no overrides leak into a
    # local dev or build environment.
    monkeypatch.delenv("CLOUDRON_APP_ORIGIN", raising=False)
    namespace = {}
    exec(compile(_settings(), "<cloudron_settings>", "exec"), namespace)
    assert "DEBUG" not in namespace
    assert "DATABASES" not in namespace
