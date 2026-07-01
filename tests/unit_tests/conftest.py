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


@pytest.fixture(autouse=True)
def reset_singletons():
    fresh = PluginConfig()
    for name, value in vars(fresh).items():
        setattr(plugin_config, name, value)

    # Snapshot every dsd_config attribute rather than a hand-maintained allowlist,
    # so a test that mutates a new attribute cannot silently leak it into the next
    # test. The unguarded file-writing steps call core's write_output, which writes
    # to dsd_config.stdout whenever logging is not routed to the console; outside a
    # real deploy that is None, so point it at an in-memory sink for each test.
    saved = dict(vars(dsd_config))
    dsd_config.stdout = io.StringIO()
    yield
    for name in list(vars(dsd_config)):
        if name not in saved:
            delattr(dsd_config, name)
    for name, value in saved.items():
        setattr(dsd_config, name, value)
