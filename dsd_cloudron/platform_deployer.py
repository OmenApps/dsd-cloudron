"""Cloudron-specific retrofit deployment, modeled on dsd-flyio."""

import re
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


def _bare_name(requirement):
    """Return a requirement's bare package name, without extras or a version.

    django-simple-deploy records bare names (its parser stops at "["), so matching
    a candidate like "psycopg[binary]" or "gunicorn>=21" against what is already
    present has to compare on the bare "psycopg"/"gunicorn".
    """
    return re.split(r"[\[<>=!~ ]", requirement, maxsplit=1)[0].strip()


# The settings block core writes always begins with this marker on its own line.
_SETTINGS_MARKER = "# dsd-cloudron settings."
# Match the marker line-anchored (unlike core, which substring-matches). The
# force-overwrite path below strips without a prompt, so the marker text appearing
# inside a comment or a string must not be mistaken for a real block and silently
# truncate settings.py. Greedy .* strips back to the last marker, matching core's
# behavior when a file already holds more than one block.
_settings_block_re = re.compile(
    r"(.*)^" + re.escape(_SETTINGS_MARKER) + r"$", re.DOTALL | re.MULTILINE
)


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
        # render_all is not transactional and _add_celery_app/_modify_settings
        # edit files in place, so a filesystem error mid-write would otherwise
        # surface as a raw traceback with the project left partially modified.
        # Translate it into a clean abort that says so.
        try:
            self._add_cloudron_artifacts()
            self._add_celery_app()
            self._modify_settings()
        except OSError as error:
            raise DSDCommandError(platform_msgs.partial_write_failed(error)) from error
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
        # Decide before core's interactive prompt runs. core check_settings ends in
        # get_confirmation -> input(), which only auto-answers under unit/e2e
        # testing (not under --automate-all), so an unattended re-deploy over an
        # existing block would hang or raise EOFError. Branch on the flags first,
        # and only read settings.py in the automate/force arms so the interactive
        # default still delegates straight to core.
        if not dsd_config.automate_all and not plugin_config.force_overwrite:
            plugin_utils.check_settings(
                "Cloudron",
                "# dsd-cloudron settings.",
                platform_msgs.cloudron_settings_found,
                platform_msgs.cant_overwrite_settings,
            )
            return

        text = dsd_config.settings_path.read_text()
        match = _settings_block_re.match(text)
        if match is None:
            # First deploy (no marker on its own line): nothing to overwrite or
            # abort on.
            return
        if plugin_config.force_overwrite:
            # core modify_settings_file only ever appends, so strip the prior block
            # ourselves - mirroring core check_settings on a confirmed overwrite -
            # or the later append would leave a duplicate block. group(1) is
            # everything before the block marker.
            dsd_config.settings_path.write_text(match.group(1))
            return
        # --automate-all with no --force-overwrite: abort cleanly instead of
        # blocking on core's overwrite prompt.
        raise DSDCommandError(platform_msgs.noninteractive_settings_conflict())

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

    # --- Artifact rendering and project edits ---

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
        # render_all wrote <project>/celery.py; here we load it from the package
        # __init__ so Django picks the Celery app up on startup. This edits the
        # user's existing __init__.py (a retrofit-specific mutation), so it lives
        # in the deployer, not the shared packaging core. We append only the
        # import line and deliberately write no __all__: that would silently
        # narrow the user's `from <project> import *` surface and is not needed
        # for Celery to find the app.
        if not self.config.enable_celery:
            return
        root = dsd_config.project_root
        init_path = root / dsd_config.local_project_name / "__init__.py"
        existing = init_path.read_text(encoding="utf-8") if init_path.exists() else ""
        import_line = "from .celery import app as celery_app"
        if import_line in existing:
            return
        prefix = (
            existing if (not existing or existing.endswith("\n")) else existing + "\n"
        )
        init_path.write_text(prefix + import_line + "\n", encoding="utf-8")
        plugin_utils.write_output(
            f"  Wired celery_app into {init_path.relative_to(root)}"
        )

    def _modify_settings(self):
        # The existing-block detection and overwrite prompt already ran in
        # _validate_platform (_check_cloudron_settings), fail-fast before any
        # artifacts were written. Here we only append the import block. The
        # template needs project_name for the absolute import; modify_settings_file
        # injects current_settings into the context itself.
        template_path = self.templates_path / "settings_import"
        plugin_utils.modify_settings_file(
            template_path, {"project_name": dsd_config.local_project_name}
        )

    def _add_requirements(self):
        # psycopg[binary] is psycopg3 (native in Django 4.2+) and matches what
        # README-cloudron.md tells the user is installed. celery[redis] pulls the
        # redis transport explicitly rather than leaning on django-redis to
        # supply the client.
        requirements = ["gunicorn", "psycopg[binary]"]
        if plugin_config.enable_redis:
            requirements.append("django-redis")
        if plugin_config.enable_celery:
            requirements.append("celery[redis]")
        if plugin_config.enable_sso:
            requirements.append("django-allauth")
        # Skip any requirement whose bare name django-simple-deploy already parsed
        # from the user's requirements. core's dedup is an exact-string match that
        # bracketed extras (psycopg[binary] vs bare psycopg) defeat, so a re-run
        # would otherwise append a duplicate line every deploy. requirements is
        # None until a real deploy populates it, hence the `or []`.
        present = dsd_config.requirements or []
        to_add = [r for r in requirements if _bare_name(r) not in present]
        self._added_requirements = to_add
        plugin_utils.add_packages(to_add)

    def _conclude_automate_all(self):
        if not dsd_config.automate_all:
            return
        if dsd_config.unit_testing:
            return
        plugin_utils.commit_changes()
        # install() streams the build, raises a clean DSDCommandError on failure,
        # and returns "" (the URL is not scraped from the slow-command output).
        self.deployed_url = cloudron_cli.install(plugin_config.location)

    def _show_success_message(self):
        # Branch on automate_all, not on deployed_url: the deployed URL is not
        # scraped from the build output (always empty), so keying on it would
        # never show the automate-all message after a real install.
        if dsd_config.automate_all:
            msg = platform_msgs.success_msg_automate_all(self.deployed_url)
        else:
            msg = platform_msgs.success_msg(
                self.config, plugin_config.location, log_output=dsd_config.log_output
            )
        summary = platform_msgs.changes_summary(self.config, self._added_requirements)
        msg = f"{msg}\n{summary}\n"
        notes = platform_msgs.followup_notes(self.config)
        if notes:
            msg = f"{msg}\n{notes}\n"
        plugin_utils.write_output(msg)
