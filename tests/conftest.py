"""Fixtures for the BLNET tests."""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_RESOURCE, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blnet.const import (
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DOMAIN,
)

RESOURCE = "http://192.168.1.10"

ENTRY_DATA = {
    CONF_RESOURCE: RESOURCE,
    CONF_USE_WEB: True,
    CONF_WEB_PORT: 80,
    CONF_USE_TA: False,
    CONF_TA_PORT: 40000,
}

# What BLNET.fetch returns with the web interface: values are strings
WEB_DATA = {
    "analog": {
        1: {"id": "1", "name": "T.Kollektor", "value": "55.5",
            "unit_of_measurement": "°C", "type": "temperature"},
        2: {"id": "2", "name": "T.Kollektor", "value": "40.0",
            "unit_of_measurement": "°C", "type": "temperature"},
        3: {"id": "3", "name": "Durchfluss", "value": "300",
            "unit_of_measurement": "l/h", "type": "volume_flow"},
        4: {"id": "4", "name": "Strahlung", "value": "512",
            "unit_of_measurement": "W/m²", "type": "radiation"},
        5: {"id": "5", "name": "Schalter", "value": "1",
            "unit_of_measurement": None, "type": "digital"},
    },
    "digital": {
        1: {"id": "1", "name": "Pumpe", "mode": "AUTO", "value": "EIN"},
        2: {"id": "2", "name": "Ventil", "mode": "HAND", "value": "AUS"},
    },
    "speed": {1: {"value": 30, "unit_of_measurement": None}},
    "energy": {1: {"value": 12.3, "unit_of_measurement": "kWh"}},
    "power": {1: {"value": 1.2, "unit_of_measurement": "kW"}},
}

# What BLNET.fetch returns with the direct connection only: values have no name
DIRECT_DATA = {
    "analog": {1: {"value": 21.3, "type": "temperature", "unit_of_measurement": "°C"}},
    "digital": {1: {"value": "1"}, 2: {"value": "0"}},
    "speed": {},
    "energy": {1: {"value": 12.3, "unit_of_measurement": "kWh"}},
    "power": {},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    yield


@pytest.fixture
def blnet():
    """
    The pyblnet.aio.Client that Client.create (blnet.create) returns.
    Its fetch returns WEB_DATA, set fetch.return_value to change it.
    """
    blnet = MagicMock()
    for method in ("fetch", "turn_on", "turn_off", "turn_auto", "close"):
        setattr(blnet, method, AsyncMock())
    blnet.fetch.return_value = copy.deepcopy(WEB_DATA)
    with patch(
        "custom_components.blnet.coordinator.Client.create", AsyncMock(return_value=blnet)
    ) as create:
        blnet.create = create
        yield blnet


@pytest.fixture
def config_entry(hass):
    """A BL-NET set up in the UI."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=RESOURCE,
        data=dict(ENTRY_DATA),
        options={CONF_SCAN_INTERVAL: 360},
    )
    entry.add_to_hass(hass)
    return entry
