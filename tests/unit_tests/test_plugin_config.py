from dsd_cloudron.plugin_config import PluginConfig, plugin_config


def test_required_core_fields():
    assert plugin_config.automate_all_supported is True
    assert plugin_config.platform_name == "Cloudron"
    assert plugin_config.confirm_automate_all_msg  # non-empty


def test_cli_derived_defaults():
    config = PluginConfig()
    assert config.location == ""
    assert config.app_id == ""
    assert config.memory_limit == 1073741824
    assert config.health_check_path == "/"
    assert config.force_overwrite is False
    assert config.enable_redis is True
    assert config.enable_sendmail is True
    assert config.enable_celery is False
    assert config.enable_sso is False
    assert config.server == ""
    assert config.allow_selfsigned is False
