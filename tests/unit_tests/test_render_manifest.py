import json

from dsd_cloudron.packaging import CloudronAppConfig, render_manifest


def _manifest(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return json.loads(render_manifest(config))


def test_manifest_core_fields():
    m = _manifest()
    assert m["manifestVersion"] == 2
    assert m["minBoxVersion"] == "8.0.0"
    assert m["id"] == "com.example.blog"
    assert m["httpPort"] == 8000
    assert m["healthCheckPath"] == "/"
    assert m["memoryLimit"] == 1073741824
    assert m["optionalSso"] is True
    assert m["title"] == "Blog"


def test_manifest_custom_memory_limit_and_health_check_path():
    # The default core fields are covered above; this pins the one untested link
    # in the CLI -> config -> manifest chain: a non-default memory_limit and
    # health_check_path must reach the rendered JSON, not silently fall back.
    m = _manifest(memory_limit=2147483648, health_check_path="/healthz/")
    assert m["memoryLimit"] == 2147483648
    assert m["healthCheckPath"] == "/healthz/"


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
    assert (
        m["checklist"]["change-default-password"]["message"]
        == "Retrieve and secure the generated admin password"
    )
    assert "admin" in m["postInstallMessage"]


def test_manifest_postinstall_uses_sso_tags():
    msg = _manifest()["postInstallMessage"]
    assert "<nosso>" in msg
    assert "</nosso>" in msg
    assert "<sso>" in msg
    assert "</sso>" in msg
    assert "admin" in msg
    assert "changeme123" not in msg  # no literal credential in the public manifest


def test_manifest_postinstall_explains_acknowledgement_retirement():
    # The password file is retired on operator acknowledgement, not by restart count.
    # The message must not claim automatic removal on the next start (which strands
    # the password across image updates and health-check restarts), and must point
    # the operator at the acknowledgement marker instead.
    msg = _manifest()["postInstallMessage"]
    assert "removed automatically on the next start" not in msg
    assert ".initial_admin_password.acknowledged" in msg
    assert "reprints these steps every" in msg


def test_manifest_version_and_author_passthrough():
    m = _manifest(version="2.1.0", author="ACME Corp")
    assert m["version"] == "2.1.0"
    assert m["author"] == "ACME Corp"


def test_manifest_is_valid_json_with_trailing_newline():
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    text = render_manifest(config)
    assert text.endswith("\n")
    json.loads(text)  # raises if invalid
