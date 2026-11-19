"""Switches of the digital outputs of the UVR1611, via the web interface of the BL-NET."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DIGITAL
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity, new_values, unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add an output and a mode switch for every digital output."""
    coordinator = entry.runtime_data
    if not coordinator.use_web:
        # outputs can only be set via the web interface, they are sensors then
        return
    known: set[tuple[str, int]] = set()

    @callback
    def add_new_switches() -> None:
        new = new_values(coordinator, (DIGITAL,), known)
        async_add_entities(
            entity
            for _, value_id in new
            for entity in (
                BLNETSwitch(coordinator, DIGITAL, value_id),
                BLNETModeSwitch(coordinator, DIGITAL, value_id),
            )
        )

    add_new_switches()
    entry.async_on_unload(coordinator.async_add_listener(add_new_switches))


class BLNETSwitch(BLNETEntity, SwitchEntity):
    """Switch a digital output on or off, this sets it to manual (HAND) mode."""

    @property
    def name(self) -> str:
        return self.value_name

    @property
    def is_on(self) -> bool:
        return (self.blnet_value or {}).get("value") == "EIN"

    @property
    def icon(self) -> str:
        return "mdi:flash" if self.is_on else "mdi:flash-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode": (self.blnet_value or {}).get("mode")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_digital("on", self._value_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_digital("off", self._value_id)


class BLNETModeSwitch(BLNETEntity, SwitchEntity):
    """On if the UVR1611 controls a digital output (AUTO), off if it is set manually (HAND)."""

    def __init__(self, coordinator: BLNETCoordinator, domain: str, value_id: int) -> None:
        super().__init__(coordinator, domain, value_id)
        self._attr_unique_id = mode_unique_id(coordinator.config_entry.entry_id, value_id)

    @property
    def name(self) -> str:
        return f"{self.value_name} automated"

    @property
    def is_on(self) -> bool:
        return (self.blnet_value or {}).get("mode") != "HAND"

    @property
    def icon(self) -> str:
        return "mdi:cog" if self.is_on else "mdi:cog-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_digital("auto", self._value_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # keep the output as it is, but control it manually
        action = "on" if (self.blnet_value or {}).get("value") == "EIN" else "off"
        await self.coordinator.async_set_digital(action, self._value_id)


def mode_unique_id(entry_id: str, value_id: int | str) -> str:
    """Unique id of the mode switch of a digital output."""
    return f"{unique_id(entry_id, DIGITAL, value_id)}_mode"
