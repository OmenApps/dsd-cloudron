"""Config object shared with django-simple-deploy core."""


class PluginConfig:
    """Attributes core reads back from the plugin.

    Mirrors dsd-flyio's PluginConfig. New shared values are added here rather
    than changing the core-plugin interface. M1 adds the CLI-derived fields.
    """

    def __init__(self):
        self.automate_all_supported = True
        self.platform_name = "Cloudron"
        # confirm_automate_all_msg is wired to deploy_messages in M1.
        self.confirm_automate_all_msg = ""


plugin_config = PluginConfig()
