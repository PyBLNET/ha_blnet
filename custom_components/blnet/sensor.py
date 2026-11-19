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

from .const import DIGITAL, SENSOR_DOMAINS
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity, new_values

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
    DIGITAL: "mdi:toggle-switch",
}

# Icons of analog inputs by the input type pyblnet reports
TYPE_ICONS = {
    "temperature": "mdi:thermometer",
    "volume_flow": "mdi:water-pump",
    "radiation": "mdi:white-balance-sunny",
    "digital": "mdi:toggle-switch",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a sensor for every value, and for digital outputs without the web interface."""
    coordinator = entry.runtime_data
    domains = SENSOR_DOMAINS if coordinator.use_web else (*SENSOR_DOMAINS, DIGITAL)
    known: set[tuple[str, int]] = set()

    @callback
    def add_new_sensors() -> None:
        async_add_entities(
            BLNETSensor(coordinator, domain, value_id)
            for domain, value_id in new_values(coordinator, domains, known)
        )

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))


class BLNETSensor(BLNETEntity, SensorEntity):
    """A value of the BL-NET."""

    @property
    def name(self) -> str:
        return self.value_name

    @property
    def _numeric(self) -> bool:
        """Whether the value is a number, and not the state of a digital input or output."""
        value = self.blnet_value or {}
        return self._domain != DIGITAL and value.get("type") != "digital"

    @property
    def native_value(self) -> float | str | None:
        value = (self.blnet_value or {}).get("value")
        if value is None or not self._numeric:
            return value
        try:
            # the web interface reports values as strings
            return float(value)
        except ValueError:
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        unit = (self.blnet_value or {}).get("unit_of_measurement")
        return UNITS.get(unit, unit)

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return DEVICE_CLASSES.get(self.native_unit_of_measurement)

    @property
    def state_class(self) -> SensorStateClass | None:
        if not self._numeric:
            return None
        if self._domain == "energy":
            return SensorStateClass.TOTAL_INCREASING
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self) -> str:
        if self._domain == "analog":
            value_type = (self.blnet_value or {}).get("type")
            return TYPE_ICONS.get(value_type, ICONS["analog"])
        return ICONS[self._domain]
