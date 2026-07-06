from dsd_cloudron import deploy_messages as dm
from dsd_cloudron.deploy_messages import followup_notes
from dsd_cloudron.packaging import CloudronAppConfig


def _config(**kwargs):
    return CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)


def test_followup_notes_sso_ships_copy_paste_wiring_block():
    notes = followup_notes(_config(enable_sso=True))
    # The exact INSTALLED_APPS / urls / migrate lines, not a prose description.
    assert '"allauth.socialaccount.providers.openid_connect",' in notes
    assert '"allauth.mfa",' in notes
    assert '"allauth.account.middleware.AccountMiddleware",' in notes
    assert "SITE_ID = 1" in notes
    assert '"allauth.account.auth_backends.AuthenticationBackend",' in notes
    assert 'path("accounts/", include("allauth.urls")),' in notes
    assert "python manage.py migrate" in notes
    # LOGIN_REDIRECT_URL matches greenfield (settings.py:127); without it a
    # successful OIDC login lands on Django's default /accounts/profile/ and 404s.
    assert 'LOGIN_REDIRECT_URL = "/"' in notes
    # Names the shipped adapters and the installed MFA extra.
    assert "cloudron_adapters.py" in notes
    assert "MFA" in notes
    # The plugin still does not touch the user's files, and the stale
    # "planned for a later release" line is gone.
    assert "does not edit" in notes
    assert "planned for a later release" not in notes


def test_followup_notes_without_sso_has_no_wiring_block():
    assert "allauth" not in followup_notes(_config())


def test_followup_notes_celery_only_has_no_allauth_leakage():
    # With a note present (celery on) but sso off, the two branches must stay
    # independently gated - the celery note appears and no allauth wiring leaks in.
    notes = followup_notes(_config(enable_celery=True))
    assert "Celery" in notes
    assert "allauth" not in notes


def test_changes_summary_names_adapters_on_sso():
    from dsd_cloudron.deploy_messages import changes_summary

    assert "cloudron_adapters.py" in changes_summary(_config(enable_sso=True), [])
    assert "cloudron_adapters.py" not in changes_summary(_config(), [])
    # Mirrors render_all's write condition: greenfield ships its own adapters.
    assert "cloudron_adapters.py" not in changes_summary(
        _config(enable_sso=True, greenfield=True), []
    )


def test_followup_notes_wagtail_block():
    notes = dm.followup_notes(_config(enable_wagtail=True))
    assert "Wagtail:" in notes
    assert "update_index" in notes
    assert "healthz/" in notes
    assert "i18n_patterns" in notes
    assert "wagtail_localize" in notes
    # The Postgres database search backend requires django.contrib.postgres in
    # INSTALLED_APPS, and the plugin does not edit settings.py, so the note must
    # hand the operator that step (a validated Wagtail requirement).
    assert "django.contrib.postgres" in notes
    # Pin the safety-critical code line. The note discusses both =False (recommended)
    # and =True (the alternative that breaks the health check) in prose, so a
    # transcription slip that flipped the actual code line to =True would still pass
    # every substring check above.
    assert "include(wagtail_urls)), prefix_default_language=False" in notes
    # update_index must run against the Cloudron database (not the operator's local
    # one), so the printed command is wrapped in cloudron exec.
    assert "cloudron exec" in notes
    # wagtail-localize ships models, so the multilingual wiring needs a migrate step,
    # like the SSO wiring block.
    assert "migrate" in notes


def test_followup_notes_no_wagtail_by_default():
    assert "Wagtail:" not in dm.followup_notes(_config())


def test_changes_summary_mentions_wagtail():
    summary = dm.changes_summary(_config(enable_wagtail=True), [])
    assert "Wagtail" in summary
    # Pin the load-bearing claims, not just the word "Wagtail", so a future edit
    # cannot silently drop them while the word survives.
    assert "WAGTAILADMIN_BASE_URL" in summary
    assert "memoryLimit" in summary
    assert "django.contrib.postgres" in summary
    assert "Wagtail" not in dm.changes_summary(_config(), [])


def test_changes_summary_notes_generated_requirements_for_locked_managers():
    # A poetry/pipenv retrofit generates requirements.txt from the lock for the image;
    # the summary must say so (and tell the user to re-lock if deps changed). A uv or
    # req_txt project adds no such note.
    for manager in ("poetry", "pipenv"):
        summary = dm.changes_summary(_config(pkg_manager=manager), [])
        assert "Generated requirements.txt" in summary
        assert manager in summary
    assert "Generated requirements.txt" not in dm.changes_summary(_config(), [])


def test_changes_summary_addon_line_reflects_disabled_infra():
    # The declared-addons line is built by appending per enabled flag. With redis and
    # sendmail off, only the always-on addons (and any others) appear - exercising the
    # skip side of those conditionals, not just the append side the defaults cover.
    summary = dm.changes_summary(_config(enable_redis=False, enable_sendmail=False), [])
    assert "postgresql, localstorage" in summary
    assert "redis" not in summary
    assert "sendmail" not in summary
