"""Tests for the uv retrofit hook.

Core's dependency-manager detection only knows req_txt/poetry/pipenv, so a
uv-managed project (uv.lock + PEP 621 pyproject, no requirements.txt) aborts core
inspection before this plugin's deploy hook runs. uv_retrofit.prepare runs in the
dsd_pre_inspect hook - ahead of that detection and core's git-clean check - to
export the lock into a staged requirements.txt, which core then reads as req_txt.
"""

import types

import pytest

from dsd_cloudron import uv_retrofit
from dsd_cloudron import deploy_messages as platform_msgs
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


def _completed(returncode=0, stdout=b"", stderr=b""):
    """Stand in for the CompletedProcess run_quick_command returns."""
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _make_uv_project(root):
    """Lay down the marker files of a uv-only project at root."""
    (root / ".git").mkdir()
    (root / "uv.lock").write_text("# lock\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'blog'\ndependencies = ['django>=4.2']\n",
        encoding="utf-8",
    )


# --- find_git_root ---


def test_find_git_root_uses_project_root_when_git_is_there(tmp_path):
    (tmp_path / ".git").mkdir()
    assert uv_retrofit.find_git_root(tmp_path) == tmp_path


def test_find_git_root_uses_parent_for_nested_layout(tmp_path):
    # django-admin startproject name (no dot) puts .git one level above BASE_DIR.
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "blog"
    nested.mkdir()
    assert uv_retrofit.find_git_root(nested) == tmp_path


def test_find_git_root_returns_none_without_a_git_dir(tmp_path):
    # No .git anywhere: return None so core raises its own missing-git error later.
    assert uv_retrofit.find_git_root(tmp_path) is None


# --- is_uv_only_project ---


def test_is_uv_only_project_true_for_uv_markers(tmp_path):
    _make_uv_project(tmp_path)
    assert uv_retrofit.is_uv_only_project(tmp_path) is True


def test_is_uv_only_project_false_without_uv_lock(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert uv_retrofit.is_uv_only_project(tmp_path) is False


def test_is_uv_only_project_false_without_pyproject(tmp_path):
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
    assert uv_retrofit.is_uv_only_project(tmp_path) is False


def test_is_uv_only_project_false_when_requirements_txt_present(tmp_path):
    # core already detects this as req_txt; do not touch it.
    _make_uv_project(tmp_path)
    (tmp_path / "requirements.txt").write_text("django\n", encoding="utf-8")
    assert uv_retrofit.is_uv_only_project(tmp_path) is False


def test_is_uv_only_project_false_when_pipfile_present(tmp_path):
    # core already detects this as pipenv; do not touch it.
    _make_uv_project(tmp_path)
    (tmp_path / "Pipfile").write_text("[packages]\n", encoding="utf-8")
    assert uv_retrofit.is_uv_only_project(tmp_path) is False


# --- prepare ---


def test_prepare_returns_none_for_non_uv_project(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "requirements.txt").write_text("django\n", encoding="utf-8")
    assert uv_retrofit.prepare(tmp_path) is None
    # An existing requirements.txt is left untouched.
    assert (tmp_path / "requirements.txt").read_text() == "django\n"


def test_prepare_returns_none_without_a_git_dir(tmp_path):
    # uv markers but no repo: nothing to stage against, so defer to core.
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert uv_retrofit.prepare(tmp_path) is None


def test_prepare_exports_and_stages_uv_project(tmp_path, monkeypatch):
    _make_uv_project(tmp_path)
    dsd_config.unit_testing = False
    staged = []
    monkeypatch.setattr(uv_retrofit, "_run_uv_export", lambda: "django>=4.2\n")
    monkeypatch.setattr(uv_retrofit, "_stage_requirements", staged.append)

    message = uv_retrofit.prepare(tmp_path)

    req_path = tmp_path / "requirements.txt"
    assert req_path.read_text(encoding="utf-8") == "django>=4.2\n"
    assert staged == [req_path]  # the generated file is staged for core's git check
    assert str(req_path) in message


# --- _run_uv_export ---


def test_run_uv_export_skipped_when_unit_testing():
    dsd_config.unit_testing = True
    assert uv_retrofit._run_uv_export() == ""


def test_run_uv_export_returns_stdout(monkeypatch):
    dsd_config.unit_testing = False
    monkeypatch.setattr(
        uv_retrofit.plugin_utils,
        "run_quick_command",
        lambda cmd: _completed(stdout=b"django>=4.2\n"),
    )
    assert uv_retrofit._run_uv_export() == "django>=4.2\n"


def test_run_uv_export_raises_on_failure(monkeypatch):
    dsd_config.unit_testing = False
    monkeypatch.setattr(
        uv_retrofit.plugin_utils,
        "run_quick_command",
        lambda cmd: _completed(returncode=1, stderr=b"lock is stale"),
    )
    with pytest.raises(DSDCommandError) as excinfo:
        uv_retrofit._run_uv_export()
    assert "lock is stale" in str(excinfo.value)


# --- _stage_requirements ---


def test_stage_requirements_skipped_when_unit_testing(monkeypatch):
    dsd_config.unit_testing = True
    calls = []
    monkeypatch.setattr(
        uv_retrofit.plugin_utils, "run_quick_command", lambda cmd: calls.append(cmd)
    )
    uv_retrofit._stage_requirements(tmp_path_placeholder := object())
    assert calls == []


def test_stage_requirements_runs_git_add(tmp_path, monkeypatch):
    dsd_config.unit_testing = False
    calls = []
    monkeypatch.setattr(
        uv_retrofit.plugin_utils,
        "run_quick_command",
        lambda cmd: calls.append(cmd) or _completed(),
    )
    req_path = tmp_path / "requirements.txt"
    uv_retrofit._stage_requirements(req_path)
    assert len(calls) == 1
    assert calls[0].startswith("git add ")
    assert str(req_path) in calls[0]
