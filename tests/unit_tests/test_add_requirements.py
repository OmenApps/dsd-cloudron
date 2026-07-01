from dsd_cloudron import platform_deployer as pd
from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def test_base_requirements(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pd.plugin_utils,
        "add_package",
        lambda name, version="": calls.append((name, version)),
    )

    plugin_config.enable_redis = False
    plugin_config.enable_celery = False
    plugin_config.enable_sso = False
    PlatformDeployer()._add_requirements()
    assert calls == [("gunicorn", ">=22.0"), ("psycopg[binary]", ">=3.1")]


def test_all_optional_requirements(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pd.plugin_utils,
        "add_package",
        lambda name, version="": calls.append((name, version)),
    )

    plugin_config.enable_redis = True
    plugin_config.enable_celery = True
    plugin_config.enable_sso = True
    PlatformDeployer()._add_requirements()
    # Exact ordered list of (name, floor) so a reorder, a dropped floor, or an
    # extra package is caught.
    assert calls == [
        ("gunicorn", ">=22.0"),
        ("psycopg[binary]", ">=3.1"),
        ("django-redis", ">=5.4"),
        ("celery[redis]", ">=5.3"),
        ("django-allauth", ">=65"),
    ]


def test_added_requirements_recorded_for_success_message(monkeypatch):
    monkeypatch.setattr(pd.plugin_utils, "add_package", lambda name, version="": None)
    plugin_config.enable_redis = True
    plugin_config.enable_celery = False
    plugin_config.enable_sso = False
    deployer = PlatformDeployer()
    deployer._add_requirements()
    # The success message lists the full names actually added, without floors.
    assert deployer._added_requirements == [
        "gunicorn",
        "psycopg[binary]",
        "django-redis",
    ]


def test_add_requirements_skips_already_present_bracketed_extras(monkeypatch):
    # core dedups by exact string, which bracketed extras defeat: psycopg[binary]
    # never matches the bare "psycopg" its parser records, so a re-run would append
    # a duplicate. The deployer must match on the bare name and skip it.
    added = []
    monkeypatch.setattr(
        pd.plugin_utils,
        "add_package",
        lambda name, version="": added.append(name),
    )
    dsd_config.requirements = ["psycopg", "celery", "gunicorn"]
    plugin_config.enable_celery = True
    plugin_config.enable_redis = True
    PlatformDeployer()._add_requirements()
    assert "psycopg[binary]" not in added  # bare "psycopg" already satisfies it
    assert "celery[redis]" not in added
    assert "gunicorn" not in added
    assert "django-redis" in added  # not yet present, still added
