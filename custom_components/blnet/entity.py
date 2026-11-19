"""Base entity of the BLNET integration."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
        value = self.blnet_value or {}
        return value.get("name") or f"{self._domain} {self._value_id}"


def unique_id(entry_id: str, domain: str, value_id: int | str) -> str:
    """Unique id of the entity of a value."""
    return f"{entry_id}_{domain}_{value_id}"


def new_values(coordinator: BLNETCoordinator, domains, known: set) -> list[tuple[str, int]]:
    """(domain, id) of the values fetched for the first time, adds them to known."""
    new = [
        (domain, value_id)
        for domain in domains
        for value_id in coordinator.data.get(domain, {})
        if (domain, value_id) not in known
    ]
    known.update(new)
    return new
