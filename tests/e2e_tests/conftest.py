"""e2e config. These tests require a real Cloudron server and credentials.

Set CLOUDRON_E2E_LOCATION to the subdomain to deploy to. Tests skip if unset.
"""

import os

import pytest


@pytest.fixture
def e2e_location():
    location = os.environ.get("CLOUDRON_E2E_LOCATION")
    if not location:
        pytest.skip("Set CLOUDRON_E2E_LOCATION to run e2e deploys.")
    return location
