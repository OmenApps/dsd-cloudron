"""Per-test state reset for the offline unit suite.

plugin_config and dsd_config are module-level singletons; restore them before
each test so tests cannot leak flag state or the unit_testing guard into one
another. Importing the plugin already pulls in django-simple-deploy core (the
package __init__ imports deploy.py, which imports the core utils), so dsd_config
is always importable wherever this unit suite runs.
"""

import io

import pytest

from dsd_cloudron.plugin_config import PluginConfig, plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


_DSD_ATTRS = (
    "unit_testing",
    "automate_all",
    "pkg_manager",
    "local_project_name",
    "deployed_project_name",
    "project_root",
    "settings_path",
    "stdout",
)


@pytest.fixture(autouse=True)
def reset_singletons():
    fresh = PluginConfig()
    for name, value in vars(fresh).items():
        setattr(plugin_config, name, value)

    saved = {name: getattr(dsd_config, name, None) for name in _DSD_ATTRS}
    # The unguarded file-writing steps call core's write_output, which writes to
    # dsd_config.stdout whenever logging is not routed to the console. Outside a
    # real deploy that attribute is None, so write_output would raise
    # AttributeError in the offline suite. Point it at an in-memory sink for the
    # duration of each test; the original value is restored below.
    dsd_config.stdout = io.StringIO()
    yield
    for name, value in saved.items():
        setattr(dsd_config, name, value)
