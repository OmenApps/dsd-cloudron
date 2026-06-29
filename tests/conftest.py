"""Top-level test config for dsd-cloudron."""

import importlib.util

collect_ignore = ["e2e_tests"]


def _integration_harness_available():
    """True only when django-simple-deploy's integration-test harness is importable.

    The integration tests import tests.integration_tests.conftest / utils, which
    the harness supplies (the installed core package does not ship them). When it
    is absent - the normal case for the offline unit suite - skip collecting the
    integration tests so a bare `pytest` run still succeeds. They run in CI or a
    dev checkout that has the harness on the path.
    """
    try:
        spec = importlib.util.find_spec(
            "tests.integration_tests.utils.it_helper_functions"
        )
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
    return spec is not None


if not _integration_harness_available():
    collect_ignore.append("integration_tests")

# The bake suite needs the pytest-cookies plugin (its `cookies` fixture). When it
# is absent - the normal minimal/offline case - every bake test would error at
# setup with "fixture 'cookies' not found", so skip collecting them entirely.
# With the dev extra installed (CI, the bake gate) pytest-cookies is present and
# the suite collects normally.
if importlib.util.find_spec("pytest_cookies") is None:
    collect_ignore.append("bake_tests")
