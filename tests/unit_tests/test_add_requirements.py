import pytest

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
    assert calls == [("gunicorn", ">=22.0"), ("psycopg[binary]", ">=3.1.12")]


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
        ("psycopg[binary]", ">=3.1.12"),
        ("django-redis", ">=5.4"),
        ("celery[redis]", ">=5.3"),
        ("django-allauth[mfa,socialaccount]", ">=65"),
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


@pytest.mark.parametrize("manager", ["poetry", "pipenv"])
def test_generate_requirements_file_for_locked_managers(monkeypatch, tmp_path, manager):
    # poetry/pipenv retrofits write a requirements.txt (the image installs from it
    # with uv) instead of mutating the manifest, so core add_package is not called.
    called = []
    monkeypatch.setattr(
        pd.plugin_utils, "add_package", lambda *a, **k: called.append(a)
    )
    dsd_config.pkg_manager = manager
    dsd_config.project_root = tmp_path
    dsd_config.unit_testing = True  # skip the export subprocess offline
    plugin_config.enable_redis = True
    plugin_config.enable_celery = False
    plugin_config.enable_sso = False
    PlatformDeployer()._add_requirements()
    text = (tmp_path / "requirements.txt").read_text()
    for dep in ("gunicorn", "psycopg[binary]", "django-redis"):
        assert dep in text
    assert called == []  # core manifest mutation not used for poetry/pipenv


def test_generate_requirements_append_rule_adds_redis_transport(monkeypatch, tmp_path):
    # When Celery is on and the export already locks celery, celery[redis] is
    # skipped (bare name present), so a bare redis line is appended for the broker
    # transport and celery is not duplicated.
    dsd_config.pkg_manager = "poetry"
    dsd_config.project_root = tmp_path
    dsd_config.unit_testing = False  # take the export path...
    monkeypatch.setattr(
        PlatformDeployer,
        "_export_locked_requirements",
        lambda self: "django==4.2\ncelery==5.3.0\n",  # ...but stub the subprocess
    )
    plugin_config.enable_redis = True
    plugin_config.enable_celery = True
    plugin_config.enable_sso = False
    PlatformDeployer()._add_requirements()
    lines = (tmp_path / "requirements.txt").read_text().splitlines()
    assert "redis" in lines  # broker transport added
    assert "celery[redis]" not in lines  # skipped: celery already locked
    assert lines.count("celery==5.3.0") == 1  # export line not duplicated
