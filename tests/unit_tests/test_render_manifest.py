import json

from dsd_cloudron.packaging import CloudronAppConfig, render_manifest


def _manifest(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return json.loads(render_manifest(config))


def test_manifest_core_fields():
    m = _manifest()
    assert m["manifestVersion"] == 2
    assert m["id"] == "com.example.blog"
    assert m["httpPort"] == 8000
    assert m["healthCheckPath"] == "/"
    assert m["memoryLimit"] == 1073741824
    assert m["optionalSso"] is True
    assert m["title"] == "Blog"


def test_manifest_default_addons():
    addons = _manifest()["addons"]
    assert addons["localstorage"] == {}
    assert addons["postgresql"] == {}
    assert addons["redis"] == {"noPassword": True}
    assert addons["sendmail"] == {"supportsDisplayName": True}
    assert "oidc" not in addons


def test_manifest_addons_toggle_off():
    addons = _manifest(enable_redis=False, enable_sendmail=False)["addons"]
    assert "redis" not in addons
    assert "sendmail" not in addons
    assert addons["localstorage"] == {}
    assert addons["postgresql"] == {}


def test_manifest_sso_adds_oidc():
    addons = _manifest(enable_sso=True)["addons"]
    assert addons["oidc"] == {
        "loginRedirectUri": "/accounts/oidc/cloudron/login/callback/"
    }


def test_manifest_checklist_and_message():
    m = _manifest()
    assert m["checklist"]["change-default-password"]["message"]
    assert "admin" in m["postInstallMessage"]


def test_manifest_is_valid_json_with_trailing_newline():
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    text = render_manifest(config)
    assert text.endswith("\n")
    json.loads(text)  # raises if invalid
