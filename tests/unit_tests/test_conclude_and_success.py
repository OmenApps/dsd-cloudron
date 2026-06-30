from dsd_cloudron import deploy_messages
from dsd_cloudron import platform_deployer as pd
from dsd_cloudron.platform_deployer import PlatformDeployer
from dsd_cloudron.packaging import CloudronAppConfig
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


def _deployer():
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    return deployer


def test_conclude_noop_without_automate_all(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pd.plugin_utils, "commit_changes", lambda: calls.append("commit")
    )
    dsd_config.automate_all = False
    _deployer()._conclude_automate_all()
    assert calls == []


def test_conclude_guarded_under_unit_testing(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pd.plugin_utils, "commit_changes", lambda: calls.append("commit")
    )
    dsd_config.automate_all = True
    dsd_config.unit_testing = True
    _deployer()._conclude_automate_all()
    # automate_all is on, but the unit_testing guard stops the commit/install.
    assert calls == []


def test_conclude_commits_and_installs(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pd.plugin_utils, "commit_changes", lambda: calls.append("commit")
    )

    def fake_install(location):
        calls.append("install")
        return ""  # mirror the real install(), which returns "" (no scraped URL)

    monkeypatch.setattr(pd.cloudron_cli, "install", fake_install)
    dsd_config.automate_all = True
    dsd_config.unit_testing = False
    _deployer()._conclude_automate_all()
    assert calls == ["commit", "install"]


def test_success_messages_omit_literal_password():
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    messages = [
        deploy_messages.success_msg(config, "blog"),
        deploy_messages.success_msg_automate_all("https://blog.example.com"),
    ]
    for message in messages:
        assert "changeme123" not in message
        assert "/app/data/.initial_admin_password" in message


def test_success_message_config_only(monkeypatch):
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )
    dsd_config.automate_all = False
    deployer = _deployer()
    deployer._show_success_message()
    assert any("configured for deployment to Cloudron" in m for m in written)
    assert any("2xx" in m for m in written)


def test_success_message_automate_all_branch(monkeypatch):
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )
    dsd_config.automate_all = True
    deployer = _deployer()
    deployer.deployed_url = ""  # the URL is never scraped from the build output.
    deployer._show_success_message()
    # The automate-all branch is chosen on automate_all alone, not on a URL.
    assert any("deployed to Cloudron" in m for m in written)
    # With an empty URL the message must fall back to telling the user how to
    # find the running app; that fallback is all they ever see in practice.
    assert any("cloudron list" in m for m in written)


def test_success_message_lists_changes(monkeypatch):
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )
    dsd_config.automate_all = False
    deployer = _deployer()
    deployer._added_requirements = ["gunicorn", "psycopg[binary]", "django-redis"]
    deployer._show_success_message()
    blob = "\n".join(written)
    assert "Changes made to your project" in blob
    assert "django-redis" in blob
    assert "postgresql" in blob


def test_success_message_mentions_log_when_logging_on(monkeypatch):
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )
    dsd_config.automate_all = False
    dsd_config.log_output = True
    _deployer()._show_success_message()
    assert any("dsd_logs" in m for m in written)


def test_success_message_includes_followup_notes(monkeypatch):
    written = []
    monkeypatch.setattr(
        pd.plugin_utils, "write_output", lambda msg: written.append(msg)
    )
    dsd_config.automate_all = False
    deployer = PlatformDeployer()
    deployer.config = CloudronAppConfig(
        project_name="blog",
        app_id="com.example.blog",
        enable_celery=True,
        enable_sso=True,
    )
    deployer._show_success_message()
    assert any("Celery" in m for m in written)
    assert any("SSO" in m for m in written)
