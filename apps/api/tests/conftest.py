import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_parcel_gis_by_default():
    """No test may reach a live GIS service.

    ``ParcelTool`` only calls out when an address misses every fixture *and* carries
    coordinates, which the deterministic address path never produces -- but a runner
    that happens to have GOOGLE_MAPS_API_KEY set would turn a unit test into a network
    call. Tests that exercise the lookup opt back in and stub the transport.
    """

    os.environ.setdefault("PARCEL_GIS_ENABLED", "false")
