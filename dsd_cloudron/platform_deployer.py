"""Cloudron-specific retrofit deployment, modeled on dsd-flyio."""

import json
import re
from pathlib import Path

from django.urls import Resolver404, resolve

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

# Tested version floors, keyed by bare package name. Attached to the retrofit's
# generated requirements so a future `cloudron update` rebuild resolves a
# known-good release rather than an older, untested one. gunicorn's floor is the
# request-smuggling fix (CVE-2024-1135); psycopg's is Django's own enforced
# minimum for the postgresql backend (Django 6.0 requires psycopg 3.1.12+); the
# celery/django-redis/django-allauth floors match the dsd-cloudron pyproject.toml
# bake extra.
_REQUIREMENT_FLOORS = {
    "gunicorn": ">=22.0",
    "psycopg": ">=3.1.12",
    "django-redis": ">=5.4",
    "celery": ">=5.3",
    "django-allauth": ">=65",
}


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
        # Reconfigure preserves the deployed healthCheckPath (it reads it back from the
        # manifest), so it must branch before _check_health_check_path: that pre-flight
        # resolve() check would otherwise run against the CLI-default path ("/"), not the
        # value actually shipped, and print a warning about a path that is never used.
        if plugin_config.reconfigure:
            self._reconfigure()
            return
        self._check_health_check_path()
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
        # Reconfigure is a purely local re-render: no cloudron CLI, no settings.py
        # edit, so it skips the CLI/auth checks and the settings-block prompt. It
        # still needs deployed_project_name for its messages.
        if plugin_config.reconfigure:
            self.deployed_project_name = (
                plugin_config.location or dsd_config.deployed_project_name
            )
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
                _SETTINGS_MARKER,
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
        # The container must load the settings module core actually appended the
        # Cloudron import to (dsd_config.settings_path). For a flat settings.py that
        # is <project>.settings, but for a split-settings Wagtail project core writes
        # to settings/production.py while wsgi/manage.py default to settings/dev - so
        # the module must be pinned in start.sh or every container process (gunicorn,
        # migrate, celery) loads the ungated dev settings. Derive the dotted module
        # from the path core chose; fall back to empty (the <project>.settings default,
        # which pins nothing) if it is missing or somehow outside the project root.
        settings_module = ""
        if dsd_config.settings_path is not None:
            try:
                settings_module = ".".join(
                    dsd_config.settings_path.relative_to(dsd_config.project_root)
                    .with_suffix("")
                    .parts
                )
            except ValueError:
                settings_module = ""
        # CloudronAppConfig validates project_name/pkg_manager/celery+redis in
        # __post_init__ and raises ValueError. Translate that into a clean
        # DSDCommandError so a bad project (e.g. a non-identifier package name)
        # aborts with a one-line message instead of a traceback.
        try:
            # greenfield stays at its False default: a retrofit deploy does not
            # wire allauth into the user's project, so the generated readme must
            # tell an --sso user the wiring is still theirs to do.
            return CloudronAppConfig(
                project_name=dsd_config.local_project_name,
                app_id=app_id,
                pkg_manager=dsd_config.pkg_manager,
                enable_redis=plugin_config.enable_redis,
                enable_celery=plugin_config.enable_celery,
                enable_sendmail=plugin_config.enable_sendmail,
                enable_sso=plugin_config.enable_sso,
                enable_wagtail=plugin_config.enable_wagtail,
                memory_limit=plugin_config.memory_limit,
                health_check_path=plugin_config.health_check_path,
                settings_module=settings_module,
            )
        except ValueError as error:
            raise DSDCommandError(str(error)) from error

    def _check_health_check_path(self):
        # Best-effort, non-blocking: warn now if the configured healthCheckPath
        # (default "/") does not resolve in the project's URLconf, so the user
        # learns it before burning a full `cloudron install` build cycle on a 404.
        # This runs inside core's Django management command, so the retrofit
        # project's settings ARE configured and resolve() works. Warn ONLY on a
        # genuine Resolver404: offline (the unit suite has no configured settings)
        # resolve() raises ImproperlyConfigured, and a project with a broken urls.py
        # raises an import error - neither is a missing route, so both return
        # silently. Never block: a middleware-gated route can fail to resolve while
        # still being reachable.
        path = self.config.health_check_path
        try:
            resolve(path)
        except Resolver404:
            plugin_utils.write_output(platform_msgs.health_check_path_unresolved(path))
        except Exception:
            return

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

    def _reconfigure(self):
        # Re-render with the per-file diff-and-confirm policy and the manifest-scalar
        # sync. This deliberately does not run _modify_settings, _add_requirements, or
        # _add_celery_app: reconfigure re-renders the plugin's own artifacts only and
        # never rewrites the user's settings.py. packaging.reconfigure refuses (with
        # ReconfigureError) when the project is not deployed, the manifest is corrupt, or
        # the flags would change a stack; translate that, like an I/O failure, into a
        # clean abort.
        plugin_utils.write_output(
            "\nReconfiguring Cloudron artifacts. Review each change before it is written."
        )
        root = dsd_config.project_root
        # Preserve the deployed sizing. The retrofit CLI's --memory-limit/--health-check-path
        # default to concrete values (1 GB, "/"), so syncing them from a reconfigure that did
        # not restate them would silently revert a manifest the operator tuned. Read the two
        # scalars back from the deployed manifest into the config so the sync preserves them;
        # on a retrofit project, change sizing by editing CloudronManifest.json (the control
        # surface) or re-deploying. The read is defensive: a missing or corrupt manifest is
        # reported cleanly by packaging.reconfigure's own precondition/guard below.
        try:
            deployed = json.loads(
                (Path(root) / "CloudronManifest.json").read_text(encoding="utf-8")
            )
            self.config.memory_limit = deployed.get(
                "memoryLimit", self.config.memory_limit
            )
            self.config.health_check_path = deployed.get(
                "healthCheckPath", self.config.health_check_path
            )
        except (OSError, ValueError, AttributeError):
            # AttributeError covers a valid-JSON-but-wrong-shape manifest (a top-level
            # array has no .get); let it fall through so packaging.reconfigure's own
            # guard reports it as a clean ReconfigureError instead of a raw traceback.
            pass

        # enable_wagtail is not reflected in the manifest addons or a supervisor
        # program, so reconstruct it from the deployed cloudron_settings.py. Without
        # this, a reconfigure that omitted --wagtail would re-render the settings
        # without the Wagtail block and offer to strip it from a working deploy. This
        # only ever sets the flag True (it never clears a passed --wagtail); turning
        # Wagtail off is a re-deploy, matching the one-way spirit of the stack guard.
        cloudron_settings_path = (
            Path(root) / self.config.project_name / "cloudron_settings.py"
        )
        try:
            if "WAGTAILADMIN_BASE_URL" in cloudron_settings_path.read_text(
                encoding="utf-8"
            ):
                self.config.enable_wagtail = True
        except (OSError, ValueError):
            pass

        def _confirm(path):
            return plugin_utils.get_confirmation(
                platform_msgs.reconfigure_overwrite_prompt(path.relative_to(root))
            )

        try:
            result = packaging.reconfigure(
                self.config, root, confirm=_confirm, output=plugin_utils.write_output
            )
        except packaging.ReconfigureError as error:
            raise DSDCommandError(str(error)) from error
        except OSError as error:
            raise DSDCommandError(platform_msgs.partial_write_failed(error)) from error

        if result.changed:
            plugin_utils.write_output(platform_msgs.reconfigure_update_reminder)
        else:
            plugin_utils.write_output("\nReconfigure complete. No changes were made.\n")

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
        # The deploy dependencies the generated config needs, on top of whatever
        # the user already depends on. psycopg[binary] is psycopg3 (native in
        # Django 4.2+); celery[redis] pulls the redis broker transport; the allauth
        # [mfa,socialaccount] extras pull the OIDC runtime deps the provider imports
        # plus MFA support, matching what greenfield ships.
        requirements = ["gunicorn", "psycopg[binary]"]
        if plugin_config.enable_redis:
            requirements.append("django-redis")
        if plugin_config.enable_celery:
            requirements.append("celery[redis]")
        if plugin_config.enable_sso:
            requirements.append("django-allauth[mfa,socialaccount]")

        if dsd_config.pkg_manager in ("poetry", "pipenv"):
            # These images install from a requirements.txt exported from the user's
            # own lock, so poetry/pipenv never run inside the image (avoiding the
            # optional-group and stale-lock traps of installing them in-image).
            self._generate_requirements_file(requirements)
            return

        # req_txt: dsd-cloudron owns requirements.txt, so add each dep through core
        # with its tested floor. Skip any bare name already present: core's dedup is
        # an exact-string match that bracketed extras (psycopg[binary] vs bare
        # psycopg) defeat, so a re-run would otherwise append a duplicate every
        # deploy. requirements is None until a real deploy populates it (the or []).
        present = dsd_config.requirements or []
        to_add = [r for r in requirements if _bare_name(r) not in present]
        self._added_requirements = to_add
        # add_package takes a per-package version; add_packages (plural) does not.
        for name in to_add:
            plugin_utils.add_package(
                name, version=_REQUIREMENT_FLOORS.get(_bare_name(name), "")
            )

    def _generate_requirements_file(self, requirements):
        """Write requirements.txt for a poetry/pipenv retrofit image.

        Export the user's locked graph, then append the deploy deps the export does
        not already cover - without floors, since the export already pins the user's
        resolved graph and a floor could make the set unsatisfiable.
        """
        exported = "" if dsd_config.unit_testing else self._export_locked_requirements()

        present = set()
        for line in exported.splitlines():
            line = line.strip()
            # Skip blanks, comments, and pip option/editable lines (-e, --hash).
            if not line or line.startswith(("#", "-")):
                continue
            present.add(_bare_name(line))

        appended = [r for r in requirements if _bare_name(r) not in present]
        # If Celery is on but celery is already locked, celery[redis] was skipped
        # above; add a bare redis so the broker transport library is still present.
        if (
            plugin_config.enable_celery
            and "celery" in present
            and "redis" not in present
        ):
            appended.append("redis")
        self._added_requirements = appended

        body = exported.rstrip("\n")
        lines = ([body] if body else []) + appended
        req_path = dsd_config.project_root / "requirements.txt"
        req_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        plugin_utils.write_output("  Wrote requirements.txt for the Cloudron image")

    def _export_locked_requirements(self):
        """Return the user's locked dependencies as requirements.txt text.

        core run_quick_command runs with no shell on Linux, so we capture stdout
        and write it in Python rather than shell-redirecting the export.
        """
        manager = dsd_config.pkg_manager
        cmd = (
            "poetry export --only main --without-hashes"
            if manager == "poetry"
            else "pipenv requirements"
        )
        try:
            output = plugin_utils.run_quick_command(cmd)
        except OSError as error:
            # A missing (FileNotFoundError) or non-executable (PermissionError)
            # export tool would otherwise surface as a raw traceback with the
            # project already partially modified; abort cleanly instead.
            raise DSDCommandError(
                platform_msgs.requirements_export_failed(manager, str(error))
            ) from error
        stderr = (output.stderr or b"").decode("utf-8", errors="replace")
        if output.returncode != 0:
            raise DSDCommandError(
                platform_msgs.requirements_export_failed(manager, stderr)
            )
        if stderr.strip():
            # poetry warns to stderr when the lock is stale; surface it.
            plugin_utils.write_output(stderr)
        return (output.stdout or b"").decode("utf-8", errors="replace")

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
        self._write_next_steps_file(summary, notes)

    def _write_next_steps_file(self, summary, notes):
        # Persist the change summary and follow-up notes to a sibling
        # CLOUDRON_NEXT_STEPS.md so the operator still has them after the stdout
        # scrolls away. Overwritten fresh each deploy, so it never accumulates.
        # Written directly (not through packaging._write, whose RenderResult
        # signature is aimed at the artifact set) and NOT appended to
        # README-cloudron.md, which render_all diffs and skips on a re-deploy.
        #
        # Guard on a real project_root and not-unit_testing: the success-message
        # unit tests call this with neither set (both default to None/falsy), so an
        # unguarded write would drop a file into the test's cwd. The file carries no
        # secrets (summary/notes never include the admin password, only its path),
        # so it is safe if a later --automate-all commit sweeps it in via `git add`;
        # the .dockerignore entry keeps a stale copy out of later image builds.
        if dsd_config.unit_testing or not dsd_config.project_root:
            return
        header = (
            "# Cloudron next steps\n\n"
            "Regenerated by dsd-cloudron on each deploy; an operator aid, safe to "
            "commit or ignore. It carries no secrets.\n"
        )
        body = f"{summary}\n\n{notes}" if notes else summary
        path = Path(dsd_config.project_root) / "CLOUDRON_NEXT_STEPS.md"
        try:
            path.write_text(f"{header}\n{body}\n", encoding="utf-8")
        except OSError as error:
            # This file is an optional aid written after the artifacts (and, under
            # --automate-all, after the commit and install). A write failure here
            # must not look like a failed deploy, so warn and move on rather than
            # raising - the same notes were just printed to stdout.
            plugin_utils.write_output(
                f"  Could not write CLOUDRON_NEXT_STEPS.md: {error}"
            )
            return
        plugin_utils.write_output("  Wrote CLOUDRON_NEXT_STEPS.md")
