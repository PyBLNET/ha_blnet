"""Fetch the values of a BL-NET and control its digital outputs."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

import aiohttp
from pyblnet.aio import Client

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type BLNETConfigEntry = ConfigEntry[BLNETCoordinator]

def _domain_data(hass: HomeAssistant) -> dict[str, Any]:
    return hass.data.setdefault(DOMAIN, {})


def blnet_lock(hass: HomeAssistant, data: dict[str, Any]) -> asyncio.Lock:
    """The lock of the BL-NET at the address in data.

    Entries reading different CAN nodes of the same BL-NET must not switch
    its node while another one reads.
    """
    return _domain_data(hass).setdefault("locks", {}).setdefault(
        data[CONF_RESOURCE], asyncio.Lock()
    )


def blnet_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """The HTTP session for the web interfaces of the BL-NETs.

    pyblnet sends the cookie of its login itself. A cookie jar, like the one
    of Home Assistant's shared session, could mix the logins of entries.
    """
    domain_data = _domain_data(hass)
    if "session" not in domain_data:
        domain_data["session"] = async_create_clientsession(
            hass, cookie_jar=aiohttp.DummyCookieJar()
        )
    return domain_data["session"]


def normalize_resource(resource: str) -> str:
    """The address of a BL-NET as a URL, with http:// if no scheme is given.

    Home Assistant only accepts a configuration URL with a scheme, a bare
    address like 10.0.0.47 fails to set up the device.
    """
    resource = resource.strip()
    if "://" not in resource:
        resource = f"http://{resource}"
    return resource


def with_normalized_resource(data: dict[str, Any]) -> dict[str, Any]:
    """A copy of data with the address of the BL-NET normalized."""
    return {**data, CONF_RESOURCE: normalize_resource(data[CONF_RESOURCE])}


def entry_title(data: dict[str, Any]) -> str:
    """Title of the entry of a BL-NET, with the CAN node if one is set."""
    node = data.get(CONF_NODE)
    return data[CONF_RESOURCE] if node is None else f"{data[CONF_RESOURCE]} (CAN node {node})"


async def async_create_blnet(hass: HomeAssistant, data: dict[str, Any]) -> Client:
    """Connect to the BL-NET.

    Raises ValueError if none answers at the web interface, and OSError
    (e.g. ConnectionError, TimeoutError) if the direct connection fails.
    """
    return await Client.create(
        data[CONF_RESOURCE],
        blnet_session(hass),
        password=data.get(CONF_PASSWORD) or None,
        web_port=data.get(CONF_WEB_PORT, DEFAULT_WEB_PORT),
        ta_port=data.get(CONF_TA_PORT, DEFAULT_TA_PORT),
        use_web=data.get(CONF_USE_WEB, True),
        use_ta=data.get(CONF_USE_TA, False),
    )


class BLNETCoordinator(DataUpdateCoordinator[dict[str, dict[int, dict[str, Any]]]]):
    """Poll a BL-NET, the data is what pyblnet's Client.fetch returns."""

    config_entry: BLNETConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BLNETConfigEntry, blnet: Client) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.blnet = blnet
        self.lock = blnet_lock(hass, entry.data)
        self.node = entry.data.get(CONF_NODE)
        self.use_web = entry.data.get(CONF_USE_WEB, True)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="BL-NET" if self.node is None else f"BL-NET CAN node {self.node}",
            manufacturer="Technische Alternative",
            model="BL-NET",
            configuration_url=(
                normalize_resource(entry.data[CONF_RESOURCE]) if self.use_web else None
            ),
        )

    async def _async_update_data(self) -> dict[str, dict[int, dict[str, Any]]]:
        try:
            async with self.lock:
                return await self.blnet.fetch(self.node)
        except Exception as err:  # pyblnet raises all kinds of errors
            raise UpdateFailed(f"Error fetching BL-NET values: {err}") from err

    async def async_set_digital(self, action: str, digital_id: int) -> None:
        """Turn a digital output on, off or to auto, then fetch its new state."""
        async with self.lock:
            await getattr(self.blnet, f"turn_{action}")(digital_id, self.node)
        await self.async_request_refresh()
