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


def test_changes_summary_names_adapters_on_sso():
    from dsd_cloudron.deploy_messages import changes_summary

    assert "cloudron_adapters.py" in changes_summary(_config(enable_sso=True), [])
    assert "cloudron_adapters.py" not in changes_summary(_config(), [])
    # Mirrors render_all's write condition: greenfield ships its own adapters.
    assert "cloudron_adapters.py" not in changes_summary(
        _config(enable_sso=True, greenfield=True), []
    )
