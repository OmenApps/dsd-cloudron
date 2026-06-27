"""Config object shared with django-simple-deploy core."""

from . import deploy_messages as platform_msgs


class PluginConfig:
    """Attributes core reads back from the plugin, plus CLI-derived values.

    Mirrors dsd-flyio's PluginConfig. New shared values are added here rather
    than changing the core-plugin interface.
    """

    def __init__(self):
        # Required by core.
        self.automate_all_supported = True
        self.platform_name = "Cloudron"
        self.confirm_automate_all_msg = platform_msgs.confirm_automate_all

        # CLI-derived (set by cli.validate_cli).
        self.location = ""
        self.app_id = ""
        self.memory_limit = 1073741824
        self.health_check_path = "/"
        self.force_overwrite = False
        self.enable_redis = True
        self.enable_sendmail = True
        self.enable_celery = False
        self.enable_sso = False
        self.server = ""
        self.token = ""
        self.allow_selfsigned = False


plugin_config = PluginConfig()
