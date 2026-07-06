"""Tests for the poetry/pipenv locked-requirements export.

A poetry or pipenv retrofit does not mutate the manifest; it writes a
requirements.txt the Cloudron image installs from (with uv). _export_locked_requirements
runs the export subprocess and returns its stdout. It is the sibling of the uv path's
uv_retrofit._run_uv_export, so it guards the same failure modes: a missing export tool
(OSError), a non-zero return, and a stale-lock warning on stderr. The unit_testing guard
lives in _generate_requirements_file, so these tests drive the method directly with the
guard off and the subprocess stubbed.
"""

import types

import pytest

from dsd_cloudron import platform_deployer as pd
from dsd_cloudron.platform_deployer import PlatformDeployer
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


def _completed(returncode=0, stdout=b"", stderr=b""):
    """Stand in for the CompletedProcess run_quick_command returns."""
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize(
    "manager, expected_prefix",
    [("poetry", "poetry export"), ("pipenv", "pipenv requirements")],
)
def test_export_runs_the_right_command_and_returns_stdout(
    monkeypatch, manager, expected_prefix
):
    dsd_config.unit_testing = False
    dsd_config.pkg_manager = manager
    seen = []
    monkeypatch.setattr(
        pd.plugin_utils,
        "run_quick_command",
        lambda cmd: seen.append(cmd) or _completed(stdout=b"django==4.2\n"),
    )
    assert PlatformDeployer()._export_locked_requirements() == "django==4.2\n"
    assert seen[0].startswith(expected_prefix)


@pytest.mark.parametrize(
    "manager, remedy_hint",
    [("poetry", "poetry-plugin-export"), ("pipenv", "pipenv")],
)
def test_export_aborts_cleanly_when_tool_is_missing(monkeypatch, manager, remedy_hint):
    # A missing (FileNotFoundError) or non-executable (PermissionError) export tool
    # would otherwise surface as a raw traceback with the project already partially
    # modified; abort cleanly and name the remedy so the user can fix it and re-run.
    dsd_config.unit_testing = False
    dsd_config.pkg_manager = manager

    def raise_missing(cmd):
        raise FileNotFoundError(manager)

    monkeypatch.setattr(pd.plugin_utils, "run_quick_command", raise_missing)
    with pytest.raises(DSDCommandError) as excinfo:
        PlatformDeployer()._export_locked_requirements()
    assert remedy_hint in str(excinfo.value)


def test_export_raises_on_nonzero_return(monkeypatch):
    dsd_config.unit_testing = False
    dsd_config.pkg_manager = "poetry"
    monkeypatch.setattr(
        pd.plugin_utils,
        "run_quick_command",
        lambda cmd: _completed(returncode=1, stderr=b"lock is out of date"),
    )
    with pytest.raises(DSDCommandError) as excinfo:
        PlatformDeployer()._export_locked_requirements()
    assert "lock is out of date" in str(excinfo.value)


def test_export_surfaces_a_stale_lock_warning_but_still_returns(monkeypatch):
    # poetry warns to stderr (not a failure) when the lock is stale; the export must
    # surface that warning to the operator and still return the exported requirements.
    dsd_config.unit_testing = False
    dsd_config.pkg_manager = "poetry"
    written = []
    monkeypatch.setattr(pd.plugin_utils, "write_output", written.append)
    monkeypatch.setattr(
        pd.plugin_utils,
        "run_quick_command",
        lambda cmd: _completed(stdout=b"django==4.2\n", stderr=b"Warning: lock stale"),
    )
    result = PlatformDeployer()._export_locked_requirements()
    assert result == "django==4.2\n"
    assert any("lock stale" in message for message in written)
