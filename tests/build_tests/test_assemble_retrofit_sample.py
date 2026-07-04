"""Offline checks that the retrofit build-context assembler produces a
buildable requirements.txt-shape project. No Docker here; the build itself is
exercised by the CI build job."""

from tests.build_tests.assemble_retrofit_sample import assemble_retrofit_sample


def test_dockerfile_is_requirements_shape(tmp_path):
    assemble_retrofit_sample(tmp_path)
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "COPY requirements.txt /app/code/requirements.txt" in dockerfile
    assert "pyproject.toml" not in dockerfile


def test_writes_buildable_project_and_artifacts(tmp_path):
    assemble_retrofit_sample(tmp_path)
    assert (tmp_path / "manage.py").exists()
    assert (tmp_path / "requirements.txt").exists()
    assert (tmp_path / "CloudronManifest.json").exists()
    assert (tmp_path / "start.sh").exists()
    settings = (tmp_path / "smoke" / "settings.py").read_text()
    assert "from .cloudron_settings import *" in settings
    assert (tmp_path / "smoke" / "cloudron_settings.py").exists()


def test_requirements_carry_runtime_deps(tmp_path):
    assemble_retrofit_sample(tmp_path)
    reqs = (tmp_path / "requirements.txt").read_text()
    for pkg in ("Django", "gunicorn", "psycopg[binary]", "django-redis"):
        assert pkg in reqs


def test_root_path_served_for_health_check(tmp_path):
    assemble_retrofit_sample(tmp_path)
    urls = (tmp_path / "smoke" / "urls.py").read_text()
    assert 'path("", health)' in urls
