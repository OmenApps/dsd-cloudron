from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.packaging import CloudronAppConfig
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def test_add_artifacts_writes_into_project_root(tmp_path):
    dsd_config.unit_testing = True
    dsd_config.project_root = tmp_path
    plugin_config.force_overwrite = False

    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    deployer._add_cloudron_artifacts()

    assert (tmp_path / "CloudronManifest.json").exists()
    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / "blog" / "cloudron_settings.py").exists()
    assert (tmp_path / "supervisor" / "gunicorn.conf").exists()
    assert deployer._render_result.written
