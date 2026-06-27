"""Cloudron-specific retrofit deployment, modeled on dsd-flyio."""

from pathlib import Path

from django_simple_deploy.management.commands.utils import plugin_utils
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)

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
        # Set by _add_cloudron_artifacts. Initialized here for the same reason:
        # downstream reads stay safe if artifact rendering aborted early.
        self._render_result = None

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
        # permission) before any artifacts are written. The CLI/auth checks run
        # first, so a missing or logged-out CLI surfaces its own clear error
        # rather than prompting to overwrite a settings block we may never reach.
        # Under the guard this never runs, so check_settings does not need
        # dsd_config.settings_path in unit tests.
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
        # CloudronAppConfig validates project_name/pkg_manager/celery+redis in
        # __post_init__ and raises ValueError. Translate that into a clean
        # DSDCommandError so a bad project (e.g. a non-identifier package name)
        # aborts with a one-line message instead of a traceback.
        try:
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
        except ValueError as error:
            raise DSDCommandError(str(error)) from error

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
        # The existing-block detection and overwrite prompt already ran in
        # _validate_platform (_check_cloudron_settings), fail-fast before any
        # artifacts were written. Here we only append the import block. The
        # template references only {{current_settings}}, so no extra context is
        # passed (modify_settings_file injects current_settings itself).
        template_path = self.templates_path / "settings_import"
        plugin_utils.modify_settings_file(template_path)

    def _add_requirements(self):
        requirements = ["gunicorn", "psycopg2-binary"]
        if plugin_config.enable_redis:
            requirements.append("django-redis")
        if plugin_config.enable_celery:
            requirements.append("celery")
        if plugin_config.enable_sso:
            requirements.append("django-allauth")
        self._added_requirements = requirements
        plugin_utils.add_packages(requirements)

    def _conclude_automate_all(self):
        pass

    def _show_success_message(self):
        pass
