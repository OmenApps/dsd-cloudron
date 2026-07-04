"""Let a uv-managed project retrofit onto Cloudron.

django-simple-deploy core detects a project's dependency manager purely by file
markers (see core's `_get_dep_man_approach`): a `Pipfile` means pipenv, a
`pyproject.toml` with `[tool.poetry]` means poetry, a `requirements.txt` means
req_txt, and anything else aborts the deploy. A uv project declares its
dependencies in PEP 621 `[project]` with a `uv.lock`, so core sees none of those
markers and bails before this plugin's deploy hook ever runs.

The fix runs in the `dsd_pre_inspect` hook, which fires before core inspects the
project. We export the uv lock into a `requirements.txt`, which core then detects
as req_txt - reusing the whole existing req_txt retrofit path (the image installs
that file with uv either way). Two ordering details matter:

- Core's git-clean check also runs after this hook and rejects a new untracked
  file, so the generated requirements.txt is staged. A staged add is invisible to
  that check, where a plain untracked file would fail it.
- `dsd_config.project_root`/`git_path` are not set yet at pre_inspect time, so we
  locate the repo root ourselves from `settings.BASE_DIR`, mirroring core.
"""

import shlex
from pathlib import Path

from django_simple_deploy.management.commands.utils import plugin_utils
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)

from . import deploy_messages as platform_msgs

# --frozen keeps the export read-only (never rewrites uv.lock mid-deploy);
# --no-hashes is required because we append deploy deps and pip rejects a mix of
# hashed and unhashed lines; --no-dev drops dev-only groups; --no-emit-project
# omits the project's own package, which a Django app is not meant to install.
_EXPORT_CMD = "uv export --frozen --no-hashes --no-dev --no-emit-project"


def find_git_root(project_root):
    """Return the repo root core will use, or None if there is no .git dir.

    Mirrors core's `_find_git_dir`: the .git dir sits at project_root or its parent
    (the nested `startproject name` layout). Returning None lets core raise its own
    missing-git error later, unchanged.
    """
    project_root = Path(project_root)
    if (project_root / ".git").exists():
        return project_root
    if (project_root.parent / ".git").exists():
        return project_root.parent
    return None


def is_uv_only_project(git_root):
    """True only for a uv project core's detection would miss.

    A uv.lock next to a pyproject.toml is the uv signature; poetry and pipenv never
    write uv.lock. If a requirements.txt or Pipfile is already present, core detects
    the project on its own, so we leave it alone.
    """
    git_root = Path(git_root)
    if not (git_root / "uv.lock").exists():
        return False
    if not (git_root / "pyproject.toml").exists():
        return False
    if (git_root / "Pipfile").exists():
        return False
    if (git_root / "requirements.txt").exists():
        return False
    return True


def prepare(project_root=None):
    """Materialize a uv project's lock into a staged requirements.txt.

    Returns a status message if a requirements.txt was written, or None if this is
    not a uv-only project (so core proceeds unchanged). Called from dsd_pre_inspect,
    before core's inspection and git-clean check.
    """
    if project_root is None:
        from django.conf import settings

        project_root = settings.BASE_DIR

    git_root = find_git_root(project_root)
    if git_root is None or not is_uv_only_project(git_root):
        return None

    req_path = git_root / "requirements.txt"
    req_path.write_text(_run_uv_export(), encoding="utf-8")
    _stage_requirements(req_path)
    return platform_msgs.uv_requirements_exported(req_path)


def _run_uv_export():
    """Return the uv lock as requirements.txt text.

    Capturing stdout (rather than uv's -o) mirrors the poetry/pipenv export in
    platform_deployer: core's run_quick_command runs with no shell, so we write the
    file in Python.
    """
    if dsd_config.unit_testing:
        return ""

    try:
        output = plugin_utils.run_quick_command(_EXPORT_CMD)
    except OSError as error:
        # A missing or non-executable uv would otherwise surface as a raw traceback
        # before core has done anything; abort cleanly instead.
        raise DSDCommandError(platform_msgs.uv_export_failed(str(error))) from error

    if output.returncode != 0:
        stderr = (output.stderr or b"").decode("utf-8", errors="replace")
        raise DSDCommandError(platform_msgs.uv_export_failed(stderr))

    return (output.stdout or b"").decode("utf-8", errors="replace")


def _stage_requirements(req_path):
    """Stage the generated requirements.txt so core's git-clean check passes.

    That check (which runs next) rejects a new untracked file but ignores a staged
    add. Staging also leaves the file ready to land in the deploy commit, which is
    the right home for it: the Cloudron image installs from requirements.txt.
    """
    if dsd_config.unit_testing:
        return

    cmd = f"git add {shlex.quote(str(req_path))}"
    try:
        output = plugin_utils.run_quick_command(cmd)
    except OSError as error:
        raise DSDCommandError(platform_msgs.uv_export_failed(str(error))) from error

    if output.returncode != 0:
        stderr = (output.stderr or b"").decode("utf-8", errors="replace")
        raise DSDCommandError(platform_msgs.uv_export_failed(stderr))
