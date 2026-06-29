import subprocess
import sys


def test_bakes_clean(cookies):
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    assert result.exit_code == 0
    assert result.exception is None
    project = result.project_path
    assert (project / "manage.py").exists()
    assert (project / "my_shop" / "settings.py").exists()
    assert (project / "my_shop" / "accounts" / "models.py").exists()
    assert (project / "my_shop" / "core" / "views.py").exists()


def test_baked_project_passes_check(cookies, clean_env):
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    proc = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=result.project_path,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert proc.returncode == 0, proc.stderr


def test_baked_project_migrates(cookies, clean_env):
    # `check` passes without migrations, so it cannot catch a custom user model
    # that ships no initial migration. `migrate` can: with AUTH_USER_MODEL set and
    # no accounts migration it aborts ("Dependency on app with no migrations:
    # accounts"). This is the gate that proves the app can actually create its
    # tables - the same `migrate` start.sh runs on every Cloudron boot.
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    proc = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=result.project_path,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert proc.returncode == 0, proc.stderr
