import functools
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve from this file, not the CWD, so the bake suite works regardless of
# where pytest is invoked from. conftest.py is at tests/bake_tests/, so parents[2]
# is the repo root.
TEMPLATE = str(
    Path(__file__).resolve().parents[2] / "dsd_cloudron" / "project_template"
)

# Env vars the baked settings.py / manage.py read. They are scrubbed from the bake
# subprocess environment so an exported value cannot make a baked project behave
# differently from a clean checkout:
#   - DJANGO_SETTINGS_MODULE: the baked manage.py uses os.environ.setdefault, so an
#     inherited value (a CI runner running other Django tests) would point the bake
#     subprocess at the wrong settings module and fail with ModuleNotFoundError.
#   - POSTGRES_HOST / REDIS_URL / AWS_STORAGE_BUCKET_NAME: settings.py reads these to
#     switch off its sqlite / local-memory defaults onto the compose services, which
#     would flip a baked project onto Postgres mid-test and fail migrate.
_SCRUB = {
    "DJANGO_SETTINGS_MODULE",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "REDIS_URL",
    "AWS_STORAGE_BUCKET_NAME",
}


@pytest.fixture
def cookies(cookies):
    """Point the bake suite at the bundled template without a global --template."""
    cookies.bake = functools.partial(cookies.bake, template=TEMPLATE)
    return cookies


@pytest.fixture
def clean_env():
    """os.environ minus the keys the baked project reads - keeps bakes hermetic."""
    return {k: v for k, v in os.environ.items() if k not in _SCRUB}


@pytest.fixture
def run_manage(clean_env):
    """Run a baked project's manage.py command in a hermetic subprocess.

    Asserts the command succeeded (returncode 0) and returns the CompletedProcess;
    every current caller wants success, so the assertion lives here.
    """

    def _run(project_path, *command):
        proc = subprocess.run(
            [sys.executable, "manage.py", *command],
            cwd=project_path,
            capture_output=True,
            text=True,
            env=clean_env,
        )
        assert proc.returncode == 0, proc.stderr
        return proc

    return _run
