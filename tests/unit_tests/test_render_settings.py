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
