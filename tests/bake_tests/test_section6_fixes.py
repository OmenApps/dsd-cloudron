import argparse
import json
from pathlib import Path

from dsd_cloudron import new, packaging


def _scaffold(tmp_path, **toggles):
    # Mirror the argparse dests build_context reads: default-on toggles (redis,
    # sendmail) use the no_<x> dest; default-off toggles use the bare <x> dest.
    args = argparse.Namespace(
        command="new",
        project_name="My Shop",
        output_dir=str(tmp_path),
        no_redis=toggles.get("no_redis", False),
        no_sendmail=toggles.get("no_sendmail", False),
        celery=toggles.get("celery", False),
        sso=toggles.get("sso", False),
        ninja=toggles.get("ninja", False),
        htmx=toggles.get("htmx", False),
        s3=toggles.get("s3", False),
    )
    return Path(new.scaffold(args))


def test_fix_base_image_pinned(tmp_path):
    project = _scaffold(tmp_path)
    dockerfile = (project / "Dockerfile").read_text()
    assert (
        "cloudron/base:5.0.0@sha256:"
        "04fd70dbd8ad6149c19de39e35718e024417c3e01dc9c6637eaf4a41ec4e596c"
    ) in dockerfile


def test_fix_oidc_addon_not_oauth(tmp_path):
    project = _scaffold(tmp_path, sso=True)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    assert "oidc" in manifest["addons"]
    assert "oauth" not in manifest["addons"]
    assert manifest["optionalSso"] is True
    # Manifest id is the hyphenated reverse-DNS form (no underscores), offline.
    assert manifest["id"] == "com.example.my-shop"


def test_fix_secret_key_marker_and_gosu(tmp_path):
    project = _scaffold(tmp_path)
    start = (project / "start.sh").read_text()
    assert "/app/data/.secret_key" in start
    assert "gosu cloudron:cloudron" in start
    assert "useradd" not in start  # no custom 'django' user


def test_fix_redis_url_uses_cloudron_redis_url(tmp_path):
    # redis is on by default (infra), so no toggle needed.
    project = _scaffold(tmp_path)
    settings = (project / "my_shop" / "cloudron_settings.py").read_text()
    assert 'os.environ["CLOUDRON_REDIS_URL"]' in settings
    # No hand-assembled redis://:password@ URL that breaks under noPassword.
    assert "redis://:" not in settings


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
    assert "CLOUDRON_MAIL_SMTP_SERVER" not in settings


def test_celery_module_matches_m0_render(tmp_path):
    # The template ships its own celery.py and render_all's copy is skipped
    # (skip-if-present), so guard against the two drifting: the shipped bytes must
    # equal render_celery_app's output for the same slug.
    project = _scaffold(tmp_path, celery=True)
    shipped = (project / "my_shop" / "celery.py").read_text()
    expected = packaging.render_celery_app(
        packaging.CloudronAppConfig(
            project_name="my_shop",
            app_id="com.example.my-shop",
            pkg_manager="uv",
            enable_redis=True,
            enable_celery=True,
        )
    )
    assert shipped == expected


def test_fix_no_scheduler_with_missing_commands(tmp_path):
    project = _scaffold(tmp_path, celery=True)
    manifest = json.loads((project / "CloudronManifest.json").read_text())
    # render_all does not emit a scheduler addon, so the prototype's broken
    # cleanup_mfa / celery_cleanup cron entries cannot occur.
    assert "scheduler" not in manifest["addons"]
