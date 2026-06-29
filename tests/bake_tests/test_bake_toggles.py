import os
import subprocess
import sys

import pytest


def _clean_env():
    # Bake subprocesses inherit os.environ; drop the vars the baked settings.py
    # reads (POSTGRES_HOST/REDIS_URL/AWS_*) so an exported value can't flip a baked
    # project off its sqlite/local defaults mid-test. See test_bake_lean.py.
    drop = {"POSTGRES_HOST", "POSTGRES_PORT", "REDIS_URL", "AWS_STORAGE_BUCKET_NAME"}
    return {k: v for k, v in os.environ.items() if k not in drop}


def _check(project_path):
    proc = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=project_path, capture_output=True, text=True, env=_clean_env(),
    )
    assert proc.returncode == 0, proc.stderr


def test_celery_off_prunes_celery_module(cookies):
    # celery-off needs no celery import: the inner __init__ renders empty and the
    # module is pruned, so this runs on a bare `dev` env.
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_celery": "no"})
    assert result.exit_code == 0
    assert not (result.project_path / "my_shop" / "celery.py").exists()
    _check(result.project_path)


def test_celery_on_keeps_celery_module(cookies):
    # celery-on bakes an inner __init__ that does `from .celery import app`, so
    # `manage.py check` imports celery; skip when the optional dep is absent.
    pytest.importorskip("celery")
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_celery": "yes"})
    assert result.exit_code == 0
    assert (result.project_path / "my_shop" / "celery.py").exists()
    _check(result.project_path)


def test_sso_on_bakes_and_checks(cookies):
    pytest.importorskip("allauth")  # INSTALLED_APPS gains allauth.* incl. allauth.mfa
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_sso": "yes"})
    assert result.exit_code == 0
    _check(result.project_path)


def test_htmx_on_bakes_and_checks(cookies):
    pytest.importorskip("django_htmx")
    pytest.importorskip("crispy_bootstrap5")
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_htmx": "yes"})
    assert result.exit_code == 0
    _check(result.project_path)
