from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.packaging import CloudronAppConfig
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def _project(tmp_path):
    pkg = tmp_path / "blog"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    dsd_config.unit_testing = True
    dsd_config.project_root = tmp_path
    dsd_config.local_project_name = "blog"


def _deployer():
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", enable_celery=True
    )
    return deployer


def test_celery_wires_init_when_enabled(tmp_path):
    _project(tmp_path)
    _deployer()._add_celery_app()
    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    assert "from .celery import app as celery_app" in init_py


def test_celery_skips_init_when_disabled(tmp_path):
    _project(tmp_path)
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    deployer._add_celery_app()
    assert "celery_app" not in (tmp_path / "blog" / "__init__.py").read_text()


def test_celery_import_inserted_once(tmp_path):
    _project(tmp_path)
    deployer = _deployer()
    deployer._add_celery_app()
    deployer._add_celery_app()  # a second run must not duplicate the import
    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    assert init_py.count("from .celery import app as celery_app") == 1


def test_celery_preserves_existing_all(tmp_path):
    # A retrofit project may already define __all__; we must not shadow it with a
    # second assignment (that would silently narrow the package's public surface).
    _project(tmp_path)
    (tmp_path / "blog" / "__init__.py").write_text(
        '__all__ = ("existing",)\n', encoding="utf-8"
    )

    deployer = _deployer()
    deployer._add_celery_app()

    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    assert "from .celery import app as celery_app" in init_py
    assert init_py.count("__all__") == 1
    assert '"existing"' in init_py
