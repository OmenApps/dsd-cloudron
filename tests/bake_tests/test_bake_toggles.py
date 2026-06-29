import importlib.util
import subprocess
import sys

import pytest


def _check(project_path, env):
    proc = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=project_path,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr


def test_celery_off_prunes_celery_module(cookies, clean_env):
    # celery-off needs no celery import: the inner __init__ renders empty and the
    # module is pruned, so this runs on a bare `dev` env.
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_celery": "no"})
    assert result.exit_code == 0
    assert not (result.project_path / "my_shop" / "celery.py").exists()
    _check(result.project_path, clean_env)


def test_celery_on_keeps_celery_module(cookies, clean_env):
    # celery-on bakes an inner __init__ that does `from .celery import app`, so
    # `manage.py check` imports celery; skip when the optional dep is absent.
    pytest.importorskip("celery")
    result = cookies.bake(
        extra_context={"project_name": "My Shop", "use_celery": "yes"}
    )
    assert result.exit_code == 0
    assert (result.project_path / "my_shop" / "celery.py").exists()
    _check(result.project_path, clean_env)


def test_sso_on_bakes_and_checks(cookies, clean_env):
    pytest.importorskip("allauth")  # INSTALLED_APPS gains allauth.* incl. allauth.mfa
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_sso": "yes"})
    assert result.exit_code == 0
    _check(result.project_path, clean_env)


def test_htmx_on_bakes_and_checks(cookies, clean_env):
    pytest.importorskip("django_htmx")
    pytest.importorskip("crispy_bootstrap5")
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_htmx": "yes"})
    assert result.exit_code == 0
    _check(result.project_path, clean_env)


def test_dev_harness_present(cookies):
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    compose = result.project_path / "docker-compose.yml"
    assert compose.exists()
    text = compose.read_text()
    assert "postgres" in text
    assert "redis" in text
    # The web service must actually wire to the backing services, not just declare
    # them: it builds the dev image and receives POSTGRES_HOST so settings.py
    # switches off sqlite onto the compose Postgres.
    assert "Dockerfile.dev" in text
    assert "POSTGRES_HOST" in text
    assert (result.project_path / "Dockerfile.dev").exists()


def test_ninja_on_bakes_and_checks(cookies, clean_env):
    # Presence check via find_spec, not importorskip: importing ninja eagerly
    # validates Django settings at module load, which raises in this unconfigured
    # pytest process. The baked project imports ninja inside a configured Django
    # (the manage.py check subprocess), where it works.
    if importlib.util.find_spec("ninja") is None:
        pytest.skip("django-ninja not installed")
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_ninja": "yes"})
    assert result.exit_code == 0
    assert (result.project_path / "my_shop" / "core" / "api.py").exists()
    _check(result.project_path, clean_env)


def test_ninja_off_prunes_api(cookies, clean_env):
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_ninja": "no"})
    assert not (result.project_path / "my_shop" / "core" / "api.py").exists()
    _check(result.project_path, clean_env)


def test_redis_off_omits_cache(cookies, clean_env):
    # redis defaults on (infra); --no-redis must drop the CACHES block from settings
    # and django-redis from the deps, and the project must still check.
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_redis": "no"})
    settings = (result.project_path / "my_shop" / "settings.py").read_text()
    # Assert on the redis-specific cache backend module, not the bare string
    # "REDIS_URL" (which also appears in an always-present prose comment).
    assert "django_redis" not in settings
    assert "django-redis" not in (result.project_path / "pyproject.toml").read_text()
    _check(result.project_path, clean_env)


def test_s3_on_wires_storage_and_checks(cookies, clean_env):
    # --s3 is settings-level (no template file). Assert the baked settings carry the
    # env-gated S3 STORAGES block and the dependency, and that the project still
    # checks. The block is env-gated, so `check` needs no boto3 in the test env.
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_s3": "yes"})
    assert result.exit_code == 0
    settings = (result.project_path / "my_shop" / "settings.py").read_text()
    assert "storages.backends.s3.S3Storage" in settings
    assert (
        "django-storages[boto3]" in (result.project_path / "pyproject.toml").read_text()
    )
    _check(result.project_path, clean_env)


def test_s3_off_omits_storage(cookies, clean_env):
    result = cookies.bake(extra_context={"project_name": "My Shop", "use_s3": "no"})
    settings = (result.project_path / "my_shop" / "settings.py").read_text()
    assert "S3Storage" not in settings
    _check(result.project_path, clean_env)
