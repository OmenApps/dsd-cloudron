from dsd_cloudron import platform_deployer as pd
from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.plugin_config import plugin_config


def test_base_requirements(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        pd.plugin_utils, "add_packages", lambda pkgs: captured.update(pkgs=pkgs)
    )

    plugin_config.enable_redis = False
    plugin_config.enable_celery = False
    plugin_config.enable_sso = False
    PlatformDeployer()._add_requirements()
    assert captured["pkgs"] == ["gunicorn", "psycopg2-binary"]
    assert "whitenoise" not in captured["pkgs"]


def test_optional_requirements(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        pd.plugin_utils, "add_packages", lambda pkgs: captured.update(pkgs=pkgs)
    )

    plugin_config.enable_redis = True
    plugin_config.enable_celery = True
    plugin_config.enable_sso = True
    PlatformDeployer()._add_requirements()
    assert "django-redis" in captured["pkgs"]
    assert "celery" in captured["pkgs"]
    assert "django-allauth" in captured["pkgs"]


def test_added_requirements_recorded_for_success_message(monkeypatch):
    monkeypatch.setattr(pd.plugin_utils, "add_packages", lambda pkgs: None)
    plugin_config.enable_redis = True
    plugin_config.enable_celery = False
    plugin_config.enable_sso = False
    deployer = PlatformDeployer()
    deployer._add_requirements()
    assert deployer._added_requirements == [
        "gunicorn",
        "psycopg2-binary",
        "django-redis",
    ]
