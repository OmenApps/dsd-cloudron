import json

from dsd_cloudron.packaging import (
    CloudronAppConfig,
    render_manifest,
    render_cloudron_settings,
)

# allauth's openid_connect callback for a provider mounted at /accounts/ with
# provider id "cloudron" is /accounts/oidc/cloudron/login/callback/.
EXPECTED_REDIRECT = "/accounts/oidc/cloudron/login/callback/"


def _config():
    return CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", enable_sso=True
    )


def test_manifest_redirect_uri_matches_allauth_callback():
    manifest = json.loads(render_manifest(_config()))
    assert manifest["addons"]["oidc"]["loginRedirectUri"] == EXPECTED_REDIRECT


def test_settings_use_cloudron_provider_id():
    settings = render_cloudron_settings(_config())
    assert '"provider_id": "cloudron"' in settings
    assert 'os.environ["CLOUDRON_OIDC_ISSUER"]' in settings
    assert "optionalSso" not in settings  # sanity: that key belongs in the manifest


def test_manifest_optional_sso_true():
    manifest = json.loads(render_manifest(_config()))
    assert manifest["optionalSso"] is True
