import functools
from pathlib import Path

import pytest

# Resolve from this file, not the CWD, so the bake suite works regardless of
# where pytest is invoked from. conftest.py is at tests/bake_tests/, so parents[2]
# is the repo root.
TEMPLATE = str(Path(__file__).resolve().parents[2] / "dsd_cloudron" / "project_template")


@pytest.fixture
def cookies(cookies):
    """Point the bake suite at the bundled template without a global --template."""
    cookies.bake = functools.partial(cookies.bake, template=TEMPLATE)
    return cookies
