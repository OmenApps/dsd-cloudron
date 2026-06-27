from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.packaging import CloudronAppConfig
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config

IMPORT_LINE = "from .celery import app as celery_app"


def _deployer(tmp_path, init_contents="", enable_celery=True):
    # Build the project package, then a deployer whose config drives
    # _add_celery_app. Call this before _add_celery_app in every test.
    pkg = tmp_path / "blog"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(init_contents, encoding="utf-8")
    dsd_config.unit_testing = True
    dsd_config.project_root = tmp_path
    dsd_config.local_project_name = "blog"
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", enable_celery=enable_celery
    )
    return deployer


def test_celery_wires_init_when_enabled(tmp_path):
    deployer = _deployer(tmp_path)
    deployer._add_celery_app()
    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    assert IMPORT_LINE in init_py
    # We deliberately do not impose an __all__ on the user's package.
    assert "__all__" not in init_py


def test_celery_skips_init_when_disabled(tmp_path):
    deployer = _deployer(tmp_path, enable_celery=False)
    deployer._add_celery_app()
    assert "celery_app" not in (tmp_path / "blog" / "__init__.py").read_text()


def test_celery_import_inserted_once(tmp_path):
    deployer = _deployer(tmp_path)
    deployer._add_celery_app()
    deployer._add_celery_app()  # a second run must not duplicate the import
    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    assert init_py.count(IMPORT_LINE) == 1


def test_celery_preserves_existing_all(tmp_path):
    # A retrofit project may already define __all__; we must not touch it (adding
    # to or rewriting it would change the package's public surface).
    deployer = _deployer(tmp_path, init_contents='__all__ = ("existing",)\n')
    deployer._add_celery_app()
    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    assert IMPORT_LINE in init_py
    assert init_py.count("__all__") == 1
    assert '"existing"' in init_py


def test_celery_normalizes_missing_trailing_newline(tmp_path):
    deployer = _deployer(tmp_path, init_contents="import os")  # no trailing newline
    deployer._add_celery_app()
    init_py = (tmp_path / "blog" / "__init__.py").read_text()
    # The import lands on its own line, not concatenated to "import os".
    assert "\n" + IMPORT_LINE in init_py
    assert "import os" in init_py


def test_celery_creates_init_when_file_absent(tmp_path):
    # Namespace package / accidentally absent __init__.py: still wire the import.
    pkg = tmp_path / "blog"
    pkg.mkdir()
    dsd_config.unit_testing = True
    dsd_config.project_root = tmp_path
    dsd_config.local_project_name = "blog"
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", enable_celery=True
    )
    deployer._add_celery_app()
    assert IMPORT_LINE in (tmp_path / "blog" / "__init__.py").read_text()
