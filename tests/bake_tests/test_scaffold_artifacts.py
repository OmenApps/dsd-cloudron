"""End-to-end checks of the full scaffold path: cookiecutter skeleton + render_all.

These drive `new.scaffold` (the real CLI path) and assert the rendered Cloudron
artifact set is correct and internally consistent - the base image pin, the OIDC
addon wiring, the secret-key handling, the redis/celery/sendmail settings, and the
template-vs-render_all celery.py byte-equality.
"""

import json
import re
from pathlib import Path

import pytest

from dsd_cloudron import new, packaging


def _args(tmp_path, **toggles):
    # Route through the real parser so the toggle dests are not spelled out a third
    # time (after new._TOGGLES and cookiecutter.json). Each kwarg name equals its
    # dest, and "--" + dest.replace("_", "-") reproduces both flag forms
    # (no_redis -> --no-redis, celery -> --celery).
    argv = ["new", "My Shop", "--output-dir", str(tmp_path)]
    argv += ["--" + dest.replace("_", "-") for dest, on in toggles.items() if on]
    return new.parse_args(argv)


def _scaffold(tmp_path, **toggles):
    return Path(new.scaffold(_args(tmp_path, **toggles)))


def test_base_image_pinned(tmp_path):
    project = _scaffold(tmp_path)
    dockerfile = (project / "Dockerfile").read_text()
    assert (
        "cloudron/base:5.0.0@sha256:"
        "04fd70dbd8ad6149c19de39e35718e024417c3e01dc9c6637eaf4a41ec4e596c"
    ) in dockerfile


def test_root_url_serves_home(tmp_path, run_manage):
    # Without a root route a bare visit to the app root 404s; the scaffold wires a
    # home view at "/" for every project.
    project = _scaffold(tmp_path)
    urls = (project / "my_shop" / "urls.py").read_text()
    views = (project / "my_shop" / "core" / "views.py").read_text()
    assert 'path("", home' in urls
    assert "def home(" in views
    # `check` resolves urls.py, so it catches a broken home import or view
    # reference that the text assertions above would miss; this is also the only
    # `check` over the default (no-toggle) scaffold.
    run_manage(project, "check")


def test_sso_login_redirect_targets_the_home_route(tmp_path):
    # SSO sets LOGIN_REDIRECT_URL = "/", so the post-login redirect only resolves
    # because the home view is wired at "/"; a 404 here was the real-server symptom.
    project = _scaffold(tmp_path, sso=True)
    settings = (project / "my_shop" / "settings.py").read_text()
    urls = (project / "my_shop" / "urls.py").read_text()
    assert 'LOGIN_REDIRECT_URL = "/"' in settings
    assert 'path("", home' in urls


def test_oidc_addon_not_oauth(tmp_path):
    project = _scaffold(tmp_path, sso=True)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    assert "oidc" in manifest["addons"]
    assert "oauth" not in manifest["addons"]
    # optionalSso is unconditionally True (a platform field, not coupled to --sso);
    # asserted here only to lock the manifest shape, not as an SSO-specific signal.
    assert manifest["optionalSso"] is True
    # Manifest id is the hyphenated reverse-DNS form (no underscores), offline.
    assert manifest["id"] == "com.example.my-shop"


def test_secret_key_marker_and_gosu(tmp_path):
    project = _scaffold(tmp_path)
    start = (project / "start.sh").read_text()
    assert "/app/data/.secret_key" in start
    assert "gosu cloudron:cloudron" in start
    assert "useradd" not in start  # no custom 'django' user


def test_redis_url_uses_cloudron_redis_url(tmp_path):
    # redis is on by default (infra), so no toggle needed.
    project = _scaffold(tmp_path)
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    assert 'os.environ["CLOUDRON_REDIS_URL"]' in settings
    # No hand-assembled redis://:password@ URL that breaks under noPassword.
    assert "redis://:" not in settings


def test_celery_wires_redis_broker(tmp_path):
    # The CACHES assertion above does not cover the Celery broker. If the celery
    # block were dropped, Celery would fall back to amqp://localhost at runtime with
    # no startup error and silently never enqueue tasks - assert the broker here.
    project = _scaffold(tmp_path, celery=True)
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    assert 'CELERY_BROKER_URL = os.environ["CLOUDRON_REDIS_URL"]' in settings
    assert "CELERY_RESULT_BACKEND" in settings


def test_secure_proxy_ssl_header_set(tmp_path):
    # Drives request.is_secure() behind Cloudron's TLS-terminating proxy, which in
    # turn gates the secure-cookie settings. Core block (not toggled), so this only
    # guards against a regression in render_cloudron_settings restructuring.
    project = _scaffold(tmp_path)
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    assert 'SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")' in settings


def test_sendmail_on_by_default_declares_addon(tmp_path):
    # sendmail defaults on (infra); the greenfield mapping (the no_sendmail dest)
    # is otherwise untested, so this exercises config_from_context's sendmail path.
    project = _scaffold(tmp_path)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    assert "sendmail" in manifest["addons"]


def test_no_sendmail_drops_addon_and_email_settings(tmp_path):
    project = _scaffold(tmp_path, no_sendmail=True)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    assert "sendmail" not in manifest["addons"]
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    # Match the whole SMTP prefix so a single residual EMAIL_* var is also caught.
    assert "CLOUDRON_MAIL_SMTP" not in settings


def test_sso_wires_socialaccount_providers(tmp_path):
    # The manifest oidc addon is not enough: the runtime login flow only appears if
    # cloudron_settings.py wires the allauth OIDC provider. Assert its shape.
    project = _scaffold(tmp_path, sso=True)
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    assert "SOCIALACCOUNT_PROVIDERS" in settings
    assert '"openid_connect"' in settings
    assert '"provider_id": "cloudron"' in settings
    assert "CLOUDRON_OIDC_CLIENT_ID" in settings
    assert "/.well-known/openid-configuration" in settings


def test_sso_off_omits_socialaccount_block(tmp_path):
    # Symmetry with the sendmail-off test: no SSO toggle -> no allauth OIDC block.
    project = _scaffold(tmp_path)  # sso defaults off
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    assert "SOCIALACCOUNT_PROVIDERS" not in settings


def test_sso_provider_id_matches_manifest_redirect_uri(tmp_path):
    # The single most fragile SSO invariant: the provider_id in cloudron_settings.py
    # must equal the <id> segment of the manifest loginRedirectUri
    # (/accounts/oidc/<id>/login/callback/), or allauth's callback 404s. render_all
    # owns both sides; couple them so an edit to one without the other goes red.
    project = _scaffold(tmp_path, sso=True)
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    match = re.search(r'"provider_id": "([^"]+)"', settings)
    assert match, "no provider_id in cloudron_settings.py"
    provider_id = match.group(1)
    redirect = manifest["addons"]["oidc"]["loginRedirectUri"]
    assert f"/{provider_id}/" in redirect


def test_celery_module_matches_render_celery_app(tmp_path):
    # The template ships its own celery.py and render_all's copy is skipped
    # (skip-if-present), so guard against the two drifting: the shipped bytes must
    # equal render_celery_app's output for the SAME config the scaffold built.
    args = _args(tmp_path, celery=True)
    project = Path(new.scaffold(args))
    shipped = (project / "my_shop" / "celery.py").read_text()
    expected = packaging.render_celery_app(
        new.config_from_context(new.build_context(args))
    )
    assert shipped == expected, (
        "Template celery.py has drifted from render_celery_app output. Resync "
        "dsd_cloudron/project_template/{{cookiecutter.project_slug}}/"
        "{{cookiecutter.project_slug}}/celery.py with dsd_cloudron/templates/celery_app."
    )


def test_celery_sso_scaffold_passes_check(tmp_path, run_manage):
    # The bake suite checks each toggle alone; this is the only test that runs
    # `check` on the combined --celery --sso scaffold (the full new.scaffold path).
    pytest.importorskip("celery")
    pytest.importorskip("allauth")
    project = _scaffold(tmp_path, celery=True, sso=True)
    run_manage(project, "check")


def test_s3_adds_no_manifest_addon(tmp_path):
    # Cloudron has no managed S3 addon: --s3 is settings/deps only. Assert render_all
    # does not accidentally inject an "s3" addon into the manifest (the bake suite
    # cannot check this - a direct cookiecutter bake renders no manifest).
    project = _scaffold(tmp_path, s3=True)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    assert "s3" not in manifest["addons"]


def test_no_scheduler_addon(tmp_path):
    project = _scaffold(tmp_path, celery=True)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    # render_all emits no scheduler addon, so no broken scheduled-job entries can
    # ship (the failure mode an earlier cookiecutter prototype had).
    assert "scheduler" not in manifest["addons"]
