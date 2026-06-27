"""Cloudron-specific retrofit deployment, modeled on dsd-flyio."""

from pathlib import Path

from django_simple_deploy.management.commands.utils import plugin_utils
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config

from . import cloudron_cli
from . import deploy_messages as platform_msgs
from . import packaging
from .packaging import CloudronAppConfig
from .plugin_config import plugin_config


class PlatformDeployer:
    def __init__(self):
        self.templates_path = Path(__file__).parent / "templates"
        self.deployed_url = ""
        # Populated by _add_requirements; read by _show_success_message so the
        # user sees exactly which packages were added. Initialized here so the
        # success message is safe even if _add_requirements has not run.
        self._added_requirements = []

    def deploy(self, *args, **options):
        plugin_utils.write_output("\nConfiguring project for deployment to Cloudron...")

        self._validate_platform()
        self.config = self._build_config()
        self._add_cloudron_artifacts()
        self._add_celery_app()
        self._modify_settings()
        self._add_requirements()
        self._conclude_automate_all()
        self._show_success_message()

    # --- Validation and config ---

    def _validate_platform(self):
        if dsd_config.unit_testing:
            self.deployed_project_name = dsd_config.deployed_project_name
            return
        cloudron_cli.check_installed()
        cloudron_cli.check_authenticated()
        # Fail fast: detect a prior Cloudron settings block (and get overwrite
        # permission) before any artifacts are written, matching dsd-flyio's
        # _check_flyio_settings ordering. Under the guard this never runs, so
        # check_settings does not need dsd_config.settings_path in unit tests.
        self._check_cloudron_settings()
        self.deployed_project_name = (
            plugin_config.location or dsd_config.deployed_project_name
        )

    def _check_cloudron_settings(self):
        plugin_utils.check_settings(
            "Cloudron",
            "# dsd-cloudron settings.",
            platform_msgs.cloudron_settings_found,
            platform_msgs.cant_overwrite_settings,
        )

    def _build_config(self):
        app_id = plugin_config.app_id or f"com.example.{dsd_config.local_project_name}"
        return CloudronAppConfig(
            project_name=dsd_config.local_project_name,
            app_id=app_id,
            pkg_manager=dsd_config.pkg_manager,
            enable_redis=plugin_config.enable_redis,
            enable_celery=plugin_config.enable_celery,
            enable_sendmail=plugin_config.enable_sendmail,
            enable_sso=plugin_config.enable_sso,
            memory_limit=plugin_config.memory_limit,
            health_check_path=plugin_config.health_check_path,
        )

    # --- Steps implemented in later tasks ---

    def _add_cloudron_artifacts(self):
        result = packaging.render_all(
            self.config,
            dsd_config.project_root,
            force=plugin_config.force_overwrite,
        )
        self._render_result = result
        root = dsd_config.project_root
        for path in result.written:
            plugin_utils.write_output(f"  Wrote {path.relative_to(root)}")
        for path in result.skipped:
            plugin_utils.write_output(
                f"  Skipped existing {path.relative_to(root)} "
                "(use --force-overwrite to regenerate)"
            )

    def _add_celery_app(self):
        pass

    def _modify_settings(self):
        pass

    def _add_requirements(self):
        pass

    def _conclude_automate_all(self):
        pass

    def _show_success_message(self):
        pass
