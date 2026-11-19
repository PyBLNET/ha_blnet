"""Fetch the values of a BL-NET and control its digital outputs."""
from __future__ import annotations

from datetime import timedelta
import logging
import threading
from typing import Any

from pyblnet import BLNET

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
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

# One lock per BL-NET: entries reading different CAN nodes of the same BL-NET
# must not switch its node while another one reads
_LOCKS: dict[str, threading.Lock] = {}


def blnet_lock(data: dict[str, Any]) -> threading.Lock:
    """The lock of the BL-NET at the address in data."""
    return _LOCKS.setdefault(data[CONF_RESOURCE], threading.Lock())


def entry_title(data: dict[str, Any]) -> str:
    """Title of the entry of a BL-NET, with the CAN node if one is set."""
    node = data.get(CONF_NODE)
    return data[CONF_RESOURCE] if node is None else f"{data[CONF_RESOURCE]} (CAN node {node})"


def create_blnet(data: dict[str, Any]) -> BLNET:
    """Connect to the BL-NET, raises ValueError if none answers (blocking)."""
    return BLNET(
        data[CONF_RESOURCE],
        password=data.get(CONF_PASSWORD) or None,
        web_port=data.get(CONF_WEB_PORT, DEFAULT_WEB_PORT),
        ta_port=data.get(CONF_TA_PORT, DEFAULT_TA_PORT),
        use_web=data.get(CONF_USE_WEB, True),
        use_ta=data.get(CONF_USE_TA, False),
    )


class BLNETCoordinator(DataUpdateCoordinator[dict[str, dict[int, dict[str, Any]]]]):
    """Poll a BL-NET, the data is what BLNET.fetch returns."""

    config_entry: BLNETConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BLNETConfigEntry, blnet: BLNET) -> None:
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
        self.lock = blnet_lock(entry.data)
        self.node = entry.data.get(CONF_NODE)
        self.use_web = entry.data.get(CONF_USE_WEB, True)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="BL-NET" if self.node is None else f"BL-NET CAN node {self.node}",
            manufacturer="Technische Alternative",
            model="BL-NET",
            configuration_url=entry.data[CONF_RESOURCE] if self.use_web else None,
        )

    async def _async_update_data(self) -> dict[str, dict[int, dict[str, Any]]]:
        try:
            return await self.hass.async_add_executor_job(self._locked, self.blnet.fetch, self.node)
        except Exception as err:  # pyblnet raises all kinds of errors
            raise UpdateFailed(f"Error fetching BL-NET values: {err}") from err

    async def async_set_digital(self, action: str, digital_id: int) -> None:
        """Turn a digital output on, off or to auto, then fetch its new state."""
        await self.hass.async_add_executor_job(
            self._locked, getattr(self.blnet, f"turn_{action}"), digital_id, self.node
        )
        await self.async_request_refresh()

    def _locked(self, func, *args):
        """Call func while no other entry talks to the BL-NET (blocking)."""
        with self.lock:
            return func(*args)
