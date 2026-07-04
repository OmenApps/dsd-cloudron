import ast
import itertools

import pytest

from dsd_cloudron.packaging import CloudronAppConfig, render_cloudron_settings


def _settings(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_cloudron_settings(config)


# The CLOUDRON_* environment the generated settings read when exec'd under the
# ON_CLOUDRON gate. Shared by the tests that execute the rendered module; the
# full-config test extends it with the OIDC keys.
_BASE_CLOUDRON_ENV = {
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


def test_settings_sso_sets_retrofit_adapter_pointers():
    retrofit = _settings(enable_sso=True)
    assert (
        'ACCOUNT_ADAPTER = "blog.cloudron_adapters.NoSignupAccountAdapter"' in retrofit
    )
    assert (
        'SOCIALACCOUNT_ADAPTER = "blog.cloudron_adapters.CloudronSocialAccountAdapter"'
        in retrofit
    )


def test_settings_sso_greenfield_omits_adapter_pointers():
    config = CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", enable_sso=True, greenfield=True
    )
    greenfield = render_cloudron_settings(config)
    # Greenfield wires ACCOUNT_ADAPTER in its own settings.py against its accounts
    # app, so cloudron_settings.py must not set it (and must not name the retrofit
    # cloudron_adapters module greenfield does not ship).
    assert "ACCOUNT_ADAPTER" not in greenfield
    assert "cloudron_adapters" not in greenfield


def test_settings_pins_secure_headers():
    # Restate Django's own secure defaults so the headers stay correct even if a
    # project overrode them or a future Django default relaxes. same-origin is the
    # current Django default; do not regress to a looser cross-origin policy.
    text = _settings()
    assert "SECURE_CONTENT_TYPE_NOSNIFF = True" in text
    assert 'SECURE_REFERRER_POLICY = "same-origin"' in text


def test_settings_custom_override_gate():
    # The override is exec'd only when the file is root-owned, not a symlink, and
    # not group/other-writable, so an attacker-dropped, cloudron-owned file is
    # skipped. Assert the gate's shape on the rendered text; the real ownership
    # behavior needs a real /app/data and multiple uids, so it is a server check.
    text = _settings()
    assert '_custom_settings = "/app/data/custom_settings.py"' in text
    # lstat, not stat: a cloudron-owned symlink to a root file must not pass.
    assert "os.lstat(_custom_settings)" in text
    assert "(_st.st_mode & 0o170000) == 0o120000" in text  # reject symlinks
    assert "_st.st_uid == 0" in text
    assert "not (_st.st_mode & 0o022)" in text  # reject group/other-writable
    # A missing or mispermissioned file cannot brick startup, and a rejected but
    # present file logs a skip line to stderr so an operator can diagnose it.
    assert "except OSError" in text
    assert "file=_sys.stderr" in text
    # exec runs OUTSIDE the read try (in its else): a SyntaxError in a trusted,
    # root-owned override must propagate, not be swallowed. And there is only one.
    assert text.count("exec(") == 1
    assert "exec(_code)" in text
    # Pin the structural placement: exec must come AFTER the read-try's handler,
    # so moving it inside the try (which would swallow an OSError from the override)
    # is caught here.
    assert text.index("exec(_code)") > text.index("except OSError as _exc:")
    # The old unconditional read+exec is gone.
    assert "exec(_f.read())" not in text


def test_settings_custom_override_gate_behavior(monkeypatch):
    # The gate hardcodes /app/data/custom_settings.py, which does not exist here,
    # so drive the generated code's logic offline: fake os.lstat's ownership/mode
    # for that path and redirect open() to a marker file, then exec the settings
    # and check whether the override applied. This proves the branch behavior
    # (root-owned applies; cloudron-owned / symlink / group-writable / unreadable
    # skipped) without a real /app/data or multiple uids.
    import io
    import os
    import builtins

    for key, value in _BASE_CLOUDRON_ENV.items():
        monkeypatch.setenv(key, value)

    path = "/app/data/custom_settings.py"
    code = "MARKER_APPLIED = True\n"

    class FakeStat:
        def __init__(self, st_uid, st_mode):
            self.st_uid = st_uid
            self.st_mode = st_mode

    def run(st_uid, st_mode, readable=True):
        real_lstat = os.lstat

        def fake_lstat(p):
            if p == path:
                return FakeStat(st_uid, st_mode)
            return real_lstat(p)

        real_open = builtins.open

        def fake_open(p, *a, **k):
            if p == path:
                if not readable:
                    raise PermissionError("simulated unreadable file")
                return io.StringIO(code)
            return real_open(p, *a, **k)

        monkeypatch.setattr(os, "lstat", fake_lstat)
        monkeypatch.setattr(builtins, "open", fake_open)
        namespace = {}
        exec(compile(_settings(), "<cloudron_settings>", "exec"), namespace)
        return "MARKER_APPLIED" in namespace

    reg = 0o100000  # S_IFREG
    lnk = 0o120000  # S_IFLNK
    # root-owned, regular, 0640 -> applies.
    assert run(0, reg | 0o640) is True
    # cloudron-owned -> skipped.
    assert run(1000, reg | 0o640) is False
    # root-owned symlink -> skipped (lstat sees the link, not its target).
    assert run(0, lnk | 0o777) is False
    # root-owned but group-writable -> skipped.
    assert run(0, reg | 0o660) is False
    # root-owned but unreadable by the app user -> skipped, no crash.
    assert run(0, reg | 0o600, readable=False) is False


def test_settings_execute_default_config(monkeypatch):
    # ast.parse proves syntax; this proves semantics. Execute the generated
    # module under a Cloudron-like environment and assert the bindings that
    # matter actually land with the right values (a misnamed key or a block that
    # escaped the ON_CLOUDRON gate would pass ast.parse but fail here).
    for key, value in _BASE_CLOUDRON_ENV.items():
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
    assert namespace["SESSION_COOKIE_SECURE"] is True
    assert namespace["CSRF_COOKIE_SECURE"] is True
    assert namespace["SECURE_CONTENT_TYPE_NOSNIFF"] is True
    assert namespace["SECURE_REFERRER_POLICY"] == "same-origin"


def test_settings_execute_full_config(monkeypatch):
    # Execute the celery + sso conditional blocks (which the default-config golden
    # snapshot never covers) so a misspelled CLOUDRON_* env var or a wrong
    # structure surfaces as a KeyError/AssertionError instead of shipping green.
    env = {
        **_BASE_CLOUDRON_ENV,
        "CLOUDRON_OIDC_ISSUER": "https://login.example.com",
        "CLOUDRON_OIDC_CLIENT_ID": "client",
        "CLOUDRON_OIDC_CLIENT_SECRET": "secret",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    namespace = {}
    exec(
        compile(
            _settings(enable_celery=True, enable_sso=True),
            "<cloudron_settings>",
            "exec",
        ),
        namespace,
    )

    assert namespace["CELERY_BROKER_URL"] == "redis://127.0.0.1:6379/0"
    assert namespace["CELERY_RESULT_BACKEND"] == "redis://127.0.0.1:6379/0"
    app = namespace["SOCIALACCOUNT_PROVIDERS"]["openid_connect"]["APPS"][0]
    assert app["provider_id"] == "cloudron"
    assert app["client_id"] == "client"
    assert (
        app["settings"]["server_url"]
        == "https://login.example.com/.well-known/openid-configuration"
    )


def test_settings_inert_without_cloudron_origin(monkeypatch):
    # Off Cloudron the whole block is gated out, so no overrides leak into a
    # local dev or build environment.
    monkeypatch.delenv("CLOUDRON_APP_ORIGIN", raising=False)
    namespace = {}
    exec(compile(_settings(), "<cloudron_settings>", "exec"), namespace)
    assert "DEBUG" not in namespace
    assert "DATABASES" not in namespace
