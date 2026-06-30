import json
import re

from dsd_cloudron.packaging import (
    CloudronAppConfig,
    render_manifest,
    render_cloudron_settings,
)


def _config():
    return CloudronAppConfig(
        project_name="blog", app_id="com.example.blog", enable_sso=True
    )


def test_manifest_and_settings_agree_on_provider_id():
    # The cross-artifact invariant no single other unit test pins: the OIDC
    # provider id in the rendered settings must match the provider segment of the
    # manifest's allauth callback redirect URI. test_render_manifest and
    # test_render_settings each pin one side against a constant; this checks that
    # the two render functions agree - the fast unit twin of the bake-level check.
    config = _config()
    manifest = json.loads(render_manifest(config))
    settings = render_cloudron_settings(config)
    redirect = manifest["addons"]["oidc"]["loginRedirectUri"]
    match = re.search(r'"provider_id": "([^"]+)"', settings)
    assert match and f"/{match.group(1)}/" in redirect
