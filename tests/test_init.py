"""Tests of the entities of a BL-NET."""
from datetime import timedelta
import copy

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_RESOURCE, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.blnet.const import CONF_NODE, CONF_USE_WEB, DOMAIN

from .conftest import DIRECT_DATA, ENTRY_DATA, RESOURCE, WEB_DATA


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_web_entities(hass, blnet, config_entry):
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    temp = hass.states.get("sensor.bl_net_t_kollektor")
    assert temp.state == "55.5"
    assert temp.attributes["unit_of_measurement"] == "°C"
    assert temp.attributes["device_class"] == "temperature"
    assert temp.attributes["state_class"] == "measurement"
    assert temp.attributes["icon"] == "mdi:thermometer"
    # values sharing a name both get an entity
    assert hass.states.get("sensor.bl_net_t_kollektor_2").state == "40.0"

    flow = hass.states.get("sensor.bl_net_durchfluss")
    assert flow.attributes["unit_of_measurement"] == "L/h"
    assert flow.attributes["device_class"] == "volume_flow_rate"
    assert flow.attributes["icon"] == "mdi:water-pump"
    radiation = hass.states.get("sensor.bl_net_strahlung")
    assert radiation.attributes["device_class"] == "irradiance"
    assert radiation.attributes["icon"] == "mdi:white-balance-sunny"
    digital_input = hass.states.get("sensor.bl_net_schalter")
    assert digital_input.state == "1"
    assert "state_class" not in digital_input.attributes

    assert hass.states.get("sensor.bl_net_speed_1").state == "30"
    energy = hass.states.get("sensor.bl_net_energy_1")
    assert energy.attributes["state_class"] == "total_increasing"
    assert energy.attributes["device_class"] == "energy"
    assert hass.states.get("sensor.bl_net_power_1").attributes["device_class"] == "power"

    pump = hass.states.get("switch.bl_net_pumpe")
    assert pump.state == STATE_ON
    assert pump.attributes["mode"] == "AUTO"
    assert hass.states.get("switch.bl_net_pumpe_automated").state == STATE_ON
    assert hass.states.get("switch.bl_net_ventil").state == STATE_OFF
    assert hass.states.get("switch.bl_net_ventil_automated").state == STATE_OFF


async def test_switches(hass, blnet, config_entry):
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, CONF_NODE: 20}
    )
    await _setup(hass, config_entry)

    async def call(service, entity_id):
        await hass.services.async_call(
            "switch", service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    await call("turn_off", "switch.bl_net_can_node_20_pumpe")
    blnet.turn_off.assert_called_once_with(1, 20)
    await call("turn_on", "switch.bl_net_can_node_20_ventil")
    blnet.turn_on.assert_called_once_with(2, 20)
    await call("turn_on", "switch.bl_net_can_node_20_ventil_automated")
    blnet.turn_auto.assert_called_once_with(2, 20)
    # turning automation off keeps the output as it is
    await call("turn_off", "switch.bl_net_can_node_20_pumpe_automated")
    assert blnet.turn_on.call_args_list[-1].args == (1, 20)


async def test_direct_only(hass, blnet, config_entry):
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, CONF_USE_WEB: False}
    )
    blnet.fetch.return_value = copy.deepcopy(DIRECT_DATA)
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.bl_net_analog_1").state == "21.3"
    assert hass.states.get("sensor.bl_net_energy_1").state == "12.3"
    # digital outputs can't be set without the web interface
    assert hass.states.get("sensor.bl_net_digital_1").state == "1"
    assert hass.states.get("sensor.bl_net_digital_2").state == "0"
    assert hass.states.async_entity_ids("switch") == []


async def test_new_and_missing_values(hass, blnet, config_entry):
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.bl_net_power_2") is None

    data = copy.deepcopy(WEB_DATA)
    data["power"][2] = {"value": 0.5, "unit_of_measurement": "kW"}
    del data["energy"][1]
    blnet.fetch.return_value = data
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=361))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get("sensor.bl_net_power_2").state == "0.5"
    assert hass.states.get("sensor.bl_net_energy_1").state == STATE_UNAVAILABLE


async def test_not_ready(hass, blnet, config_entry):
    blnet.create.side_effect = ValueError("No BLNET found")
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY

    blnet.create.side_effect = None
    blnet.fetch.side_effect = ConnectionError("Could not log in")
    await hass.config_entries.async_reload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass, blnet, config_entry):
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    # the direct connection is closed
    blnet.close.assert_awaited_once()


async def test_import_yaml(hass, blnet):
    """configuration.yaml is imported, its entities keep their entity ids."""
    registry = er.async_get(hass)
    legacy = {
        "sensor.t_kollektor": ("sensor", "blnet_sensor_blnet analog 1"),
        "sensor.blnet_energy_1": ("sensor", "blnet_sensor_blnet energy 1"),
        "switch.pumpe": ("switch", "blnet_switch_1"),
        "switch.pumpe_automated": ("switch", "blnet_mode_switch_1"),
    }
    for entity_id, (domain, unique_id) in legacy.items():
        registry.async_get_or_create(
            domain, DOMAIN, unique_id, suggested_object_id=entity_id.split(".")[1]
        )

    assert await async_setup_component(
        hass, DOMAIN, {DOMAIN: {CONF_RESOURCE: RESOURCE, "scan_interval": 60}}
    )
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.options == {"scan_interval": 60}
    assert ir.async_get(hass).async_get_issue("homeassistant", f"deprecated_yaml_{DOMAIN}")

    for entity_id in legacy:
        registry_entry = registry.async_get(entity_id)
        assert registry_entry.config_entry_id == entry.entry_id
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get("sensor.t_kollektor").state == "55.5"
    assert hass.states.get("switch.pumpe").state == STATE_ON
    # no duplicates of the moved entities
    assert hass.states.get("sensor.bl_net_energy_1") is None
    assert hass.states.get("switch.bl_net_pumpe") is None


async def test_device_named_by_can_node(hass, blnet):
    entry = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, CONF_NODE: 2})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.name == "BL-NET CAN node 2"
    blnet.fetch.assert_called_with(2)


async def test_address_without_scheme_migrated(hass, blnet):
    """Entries stored by 0.15.2 with a bare address get http:// added."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="192.168.1.10", data={**ENTRY_DATA, CONF_RESOURCE: "192.168.1.10"}
    )
    entry.add_to_hass(hass)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_RESOURCE] == RESOURCE
    assert entry.title == RESOURCE
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.configuration_url == RESOURCE
    assert hass.states.get("sensor.bl_net_t_kollektor").state == "55.5"
