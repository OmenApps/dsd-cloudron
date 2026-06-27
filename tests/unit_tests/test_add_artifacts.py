from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.packaging import CloudronAppConfig
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def _deployer(tmp_path, **config_overrides):
    dsd_config.unit_testing = True
    dsd_config.project_root = tmp_path
    plugin_config.force_overwrite = False
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", **config_overrides
    )
    return deployer


def test_add_artifacts_writes_full_default_set(tmp_path):
    deployer = _deployer(tmp_path)
    deployer._add_cloudron_artifacts()

    expected = [
        "CloudronManifest.json",
        "Dockerfile",
        "start.sh",
        "nginx.conf",
        ".dockerignore",
        "README-cloudron.md",
        "blog/cloudron_settings.py",
        "supervisor/gunicorn.conf",
        "supervisor/nginx.conf",
    ]
    for relative in expected:
        assert (tmp_path / relative).exists(), f"missing {relative}"
    # Exact count guards against the deployer silently dropping (or gaining) an
    # artifact in the default configuration.
    assert len(deployer._render_result.written) == len(expected)


def test_add_artifacts_skips_existing_without_force(tmp_path):
    deployer = _deployer(tmp_path)
    deployer._add_cloudron_artifacts()
    first_written = len(deployer._render_result.written)

    # Second pass with force=False must skip every existing file.
    deployer._add_cloudron_artifacts()
    assert deployer._render_result.written == []
    assert len(deployer._render_result.skipped) == first_written


def test_add_artifacts_writes_celery_files_when_enabled(tmp_path):
    deployer = _deployer(tmp_path, enable_celery=True)
    deployer._add_cloudron_artifacts()

    assert (tmp_path / "blog" / "celery.py").exists()
    assert (tmp_path / "supervisor" / "celery-worker.conf").exists()
    assert (tmp_path / "supervisor" / "celery-beat.conf").exists()
