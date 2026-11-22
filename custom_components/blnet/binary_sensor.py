"""Binary sensors of the digital inputs, and of the digital outputs without the web interface."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DIGITAL, DOMAIN, SENSOR_DOMAINS
from .coordinator import BLNETConfigEntry
from .entity import BLNETEntity, is_binary, new_values, unique_id

# what the BL-NET reports for on: digital inputs "1", outputs via the web interface "EIN"
ON_VALUES = {"1", "EIN"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a binary sensor for every digital value that can't be switched."""
    coordinator = entry.runtime_data
    domains = SENSOR_DOMAINS if coordinator.use_web else (*SENSOR_DOMAINS, DIGITAL)
    known: set[tuple[str, int]] = set()

    @callback
    def add_new_binary_sensors() -> None:
        new = new_values(coordinator, domains, known, is_binary)
        for domain, value_id in new:
            _migrate_sensor(hass, entry, unique_id(entry.entry_id, domain, value_id))
        async_add_entities(BLNETBinarySensor(coordinator, domain, value_id) for domain, value_id in new)

    add_new_binary_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_binary_sensors))


@callback
def _migrate_sensor(hass: HomeAssistant, entry: BLNETConfigEntry, value_unique_id: str) -> None:
    """Replace the sensor of a digital value, up to 0.15, by a binary sensor.

    The binary sensor keeps the object id and the name set in the UI.
    """
    registry = er.async_get(hass)
    old_entity_id = registry.async_get_entity_id(Platform.SENSOR, DOMAIN, value_unique_id)
    if old_entity_id is None or registry.async_get_entity_id(
        Platform.BINARY_SENSOR, DOMAIN, value_unique_id
    ):
        return
    old = registry.async_get(old_entity_id)
    registry.async_remove(old_entity_id)
    object_id = old_entity_id.split(".", 1)[1]
    new = registry.async_get_or_create(
        Platform.BINARY_SENSOR,
        DOMAIN,
        value_unique_id,
        config_entry=entry,
        suggested_object_id=object_id,
    )
    if old.name is not None or old.icon is not None:
        registry.async_update_entity(new.entity_id, name=old.name, icon=old.icon)


class BLNETBinarySensor(BLNETEntity, BinarySensorEntity):
    """A digital value of the BL-NET, on or off."""

    @property
    def name(self) -> str:
        return self.value_name

    @property
    def is_on(self) -> bool | None:
        value = (self.blnet_value or {}).get("value")
        return None if value is None else str(value) in ON_VALUES

    @property
    def icon(self) -> str:
        return "mdi:toggle-switch" if self.is_on else "mdi:toggle-switch-off"
