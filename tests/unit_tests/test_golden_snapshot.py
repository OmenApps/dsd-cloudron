from pathlib import Path

import pytest

from dsd_cloudron.packaging import (
    CloudronAppConfig,
    render_manifest,
    render_dockerfile,
    render_start_sh,
    render_nginx_conf,
    render_cloudron_settings,
    render_celery_app,
)

EXPECTED = Path(__file__).parent / "expected"

CASES = {
    "CloudronManifest.json": render_manifest,
    "Dockerfile": render_dockerfile,
    "start.sh": render_start_sh,
    "nginx.conf": render_nginx_conf,
    "cloudron_settings.py": render_cloudron_settings,
    "celery.py": render_celery_app,
}


def _config():
    return CloudronAppConfig(project_name="blog", app_id="com.example.blog")


@pytest.mark.parametrize("name,func", CASES.items())
def test_matches_golden(name, func):
    # Read with explicit utf-8 to match _write's encoding on the generation side.
    expected = (EXPECTED / name).read_text(encoding="utf-8")
    assert func(_config()) == expected
