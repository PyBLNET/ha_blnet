"""Sensors of the values the BL-NET reports."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SENSOR_DOMAINS
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity, is_binary, new_values

# Units the BL-NET reports in another spelling than Home Assistant
UNITS = {"l/h": UnitOfVolumeFlowRate.LITERS_PER_HOUR}

DEVICE_CLASSES = {
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    UnitOfIrradiance.WATTS_PER_SQUARE_METER: SensorDeviceClass.IRRADIANCE,
    UnitOfVolumeFlowRate.LITERS_PER_HOUR: SensorDeviceClass.VOLUME_FLOW_RATE,
    UnitOfPower.KILO_WATT: SensorDeviceClass.POWER,
    UnitOfEnergy.KILO_WATT_HOUR: SensorDeviceClass.ENERGY,
}

ICONS = {
    "analog": "mdi:thermometer",
    "speed": "mdi:speedometer",
    "power": "mdi:power-plug",
    "energy": "mdi:power-plug",
}

# Icons of analog inputs by the input type pyblnet reports
TYPE_ICONS = {
    "temperature": "mdi:thermometer",
    "volume_flow": "mdi:water-pump",
    "radiation": "mdi:white-balance-sunny",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a sensor for every measured value, digital ones are binary sensors."""
    coordinator = entry.runtime_data
    known: set[tuple[str, int]] = set()

    @callback
    def add_new_sensors() -> None:
        async_add_entities(
            BLNETSensor(coordinator, domain, value_id)
            for domain, value_id in new_values(
                coordinator, SENSOR_DOMAINS, known, lambda domain, value: not is_binary(domain, value)
            )
        )

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))


class BLNETSensor(BLNETEntity, SensorEntity):
    """A value of the BL-NET."""

    @property
    def name(self) -> str:
        return self.value_name

    @property
    def native_value(self) -> float | None:
        value = (self.blnet_value or {}).get("value")
        if value is None or isinstance(value, (int, float)):
            # the direct connection reports numbers, e.g. speed as a level 0-30
            return value
        try:
            # the web interface reports values as strings
            return float(value)
        except ValueError:
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        unit = self._last_value.get("unit_of_measurement")
        return UNITS.get(unit, unit)

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return DEVICE_CLASSES.get(self.native_unit_of_measurement)

    @property
    def state_class(self) -> SensorStateClass:
        if self._domain == "energy":
            return SensorStateClass.TOTAL_INCREASING
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self) -> str:
        if self._domain == "analog":
            value_type = self._last_value.get("type")
            return TYPE_ICONS.get(value_type, ICONS["analog"])
        return ICONS[self._domain]
