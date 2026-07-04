from pathlib import Path

import pytest

from dsd_cloudron.packaging import (
    CloudronAppConfig,
    render_celery_app,
    render_cloudron_settings,
    render_dockerfile,
    render_manifest,
    render_nginx_conf,
    render_readme,
    render_start_sh,
    render_supervisor_confs,
)

EXPECTED = Path(__file__).parent / "expected"
# The celery+sso goldens are the SAME fixtures the harness-gated integration test
# diffs, read here (not copied) so there is one source of truth checked both
# offline and by the integration suite.
REFERENCE = Path(__file__).parent.parent / "integration_tests" / "reference_files"


def _default_config():
    return CloudronAppConfig(project_name="blog", app_id="com.example.blog")


def _celery_sso_config():
    # Exactly the defaults plus the two toggles: the retrofit
    # `deploy --location blog --celery --sso` that produced the reference files.
    # greenfield stays False - greenfield=True flips render_readme to the
    # SSO-auto-wired branch and would fail the diff.
    return CloudronAppConfig(
        project_name="blog",
        app_id="com.example.blog",
        enable_celery=True,
        enable_sso=True,
    )


def _uv_config():
    return CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", pkg_manager="uv"
    )


def _worker_conf(config):
    return render_supervisor_confs(config)["celery-worker.conf"]


def _beat_conf(config):
    return render_supervisor_confs(config)["celery-beat.conf"]


# The config x artifact matrix: each case pairs a zero-arg render thunk with the
# byte-exact golden it must match. The supervisor artifacts come from
# render_supervisor_confs (a dict), so they are extracted by key rather than
# assuming every render function returns a string.
CASES = [
    # Default blog config: the full render-produced set with its own goldens.
    pytest.param(
        lambda: render_manifest(_default_config()),
        EXPECTED / "CloudronManifest.json",
        id="default-manifest",
    ),
    pytest.param(
        lambda: render_dockerfile(_default_config()),
        EXPECTED / "Dockerfile",
        id="default-dockerfile",
    ),
    pytest.param(
        lambda: render_start_sh(_default_config()),
        EXPECTED / "start.sh",
        id="default-start_sh",
    ),
    pytest.param(
        lambda: render_nginx_conf(_default_config()),
        EXPECTED / "nginx.conf",
        id="default-nginx",
    ),
    pytest.param(
        lambda: render_cloudron_settings(_default_config()),
        EXPECTED / "cloudron_settings.py",
        id="default-settings",
    ),
    pytest.param(
        lambda: render_celery_app(_default_config()),
        EXPECTED / "celery.py",
        id="default-celery",
    ),
    # celery+sso config. init.py is excluded: the deployer writes it, not a render
    # function, so it stays covered by the integration suite alone.
    pytest.param(
        lambda: render_manifest(_celery_sso_config()),
        REFERENCE / "celery_sso.CloudronManifest.json",
        id="celery_sso-manifest",
    ),
    pytest.param(
        lambda: render_cloudron_settings(_celery_sso_config()),
        REFERENCE / "celery_sso.cloudron_settings.py",
        id="celery_sso-settings",
    ),
    pytest.param(
        lambda: render_celery_app(_celery_sso_config()),
        REFERENCE / "celery_sso.celery.py",
        id="celery_sso-celery",
    ),
    pytest.param(
        lambda: render_readme(_celery_sso_config()),
        REFERENCE / "celery_sso.README-cloudron.md",
        id="celery_sso-readme",
    ),
    pytest.param(
        lambda: _worker_conf(_celery_sso_config()),
        REFERENCE / "celery_sso.supervisor.celery-worker.conf",
        id="celery_sso-worker",
    ),
    pytest.param(
        lambda: _beat_conf(_celery_sso_config()),
        REFERENCE / "celery_sso.supervisor.celery-beat.conf",
        id="celery_sso-beat",
    ),
    # uv pkg_manager Dockerfile: drift protection on the exact install block that
    # test_render_dockerfile.py only substring-covers.
    pytest.param(
        lambda: render_dockerfile(_uv_config()),
        EXPECTED / "uv.Dockerfile",
        id="uv-dockerfile",
    ),
]


@pytest.mark.parametrize("render,expected_path", CASES)
def test_matches_golden(render, expected_path):
    # Read with explicit utf-8 to match _write's encoding on the generation side.
    expected = expected_path.read_text(encoding="utf-8")
    assert render() == expected
