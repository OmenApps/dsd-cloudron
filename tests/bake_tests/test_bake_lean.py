def test_bakes_clean(cookies):
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    assert result.exit_code == 0
    assert result.exception is None
    project = result.project_path
    assert (project / "manage.py").exists()
    assert (project / "my_shop" / "settings.py").exists()
    assert (project / "my_shop" / "accounts" / "models.py").exists()
    assert (project / "my_shop" / "core" / "views.py").exists()


def test_baked_project_passes_check(cookies, run_manage):
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    run_manage(result.project_path, "check")


def test_baked_project_migrates(cookies, run_manage):
    # `check` passes without migrations, so it cannot catch a custom user model
    # that ships no initial migration. `migrate` can: with AUTH_USER_MODEL set and
    # no accounts migration it aborts ("Dependency on app with no migrations:
    # accounts"). This is the gate that proves the app can actually create its
    # tables - the same `migrate` start.sh runs on every Cloudron boot.
    result = cookies.bake(extra_context={"project_name": "My Shop"})
    run_manage(result.project_path, "migrate", "--noinput")
