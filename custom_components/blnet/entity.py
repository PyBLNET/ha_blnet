"""Base entity of the BLNET integration."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DIGITAL
from .coordinator import BLNETCoordinator


class BLNETEntity(CoordinatorEntity[BLNETCoordinator]):
    """A value of the BL-NET, by its domain and id in the fetched data."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BLNETCoordinator, domain: str, value_id: int) -> None:
        super().__init__(coordinator)
        self._domain = domain
        self._value_id = value_id
        self._attr_unique_id = unique_id(coordinator.config_entry.entry_id, domain, value_id)
        self._attr_device_info = coordinator.device_info
        # the value as last reported, its name, type and unit stay while it is missing
        self._last_value: dict[str, Any] = self.blnet_value or {}

    @callback
    def _handle_coordinator_update(self) -> None:
        if (value := self.blnet_value) is not None:
            self._last_value = value
        super()._handle_coordinator_update()

    @property
    def blnet_value(self) -> dict[str, Any] | None:
        """The fetched value, None if the BL-NET didn't report it."""
        return self.coordinator.data.get(self._domain, {}).get(self._value_id)

    @property
    def available(self) -> bool:
        return super().available and self.blnet_value is not None

    @property
    def value_name(self) -> str:
        """Name of the value, values read only via the direct connection have none."""
        return self._last_value.get("name") or f"{self._domain} {self._value_id}"


def unique_id(entry_id: str, domain: str, value_id: int | str) -> str:
    """Unique id of the entity of a value."""
    return f"{entry_id}_{domain}_{value_id}"


def is_binary(domain: str, value: dict[str, Any]) -> bool:
    """Whether a value is on or off: a digital input, or a digital output read as a sensor."""
    return domain == DIGITAL or value.get("type") == "digital"


def new_values(
    coordinator: BLNETCoordinator,
    domains,
    known: set,
    include: Callable[[str, dict[str, Any]], bool] | None = None,
) -> list[tuple[str, int]]:
    """(domain, id) of the values fetched for the first time, adds them to known.

    include(domain, value) selects the values of the platform, default all.
    """
    new = [
        (domain, value_id)
        for domain in domains
        for value_id, value in coordinator.data.get(domain, {}).items()
        if (domain, value_id) not in known and (include is None or include(domain, value))
    ]
    known.update(new)
    return new
