"""Read and control a UVR1611 via a BL-NET."""
from __future__ import annotations

import logging
import re

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_RESOURCE,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DIGITAL,
    DOMAIN,
)
from .coordinator import (
    BLNETConfigEntry,
    BLNETCoordinator,
    async_create_blnet,
    entry_title,
    with_normalized_resource,
)
from .entity import unique_id
from .switch import mode_unique_id

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

# The configuration.yaml setup, imported into a config entry
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_RESOURCE): cv.url,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NODE): cv.positive_int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
        vol.Optional(CONF_WEB_PORT, default=DEFAULT_WEB_PORT): cv.positive_int,
        vol.Optional(CONF_TA_PORT, default=DEFAULT_TA_PORT): cv.positive_int,
        vol.Optional(CONF_USE_WEB, default=True): cv.boolean,
        vol.Optional(CONF_USE_TA, default=False): cv.boolean,
    }),
}, extra=vol.ALLOW_EXTRA)

# Unique ids of the entities set up from configuration.yaml
LEGACY_UNIQUE_ID = re.compile(
    r"blnet_sensor_blnet (?P<domain>\w+) (?P<id>\d+)"
    r"|blnet_(?P<mode>mode_)?switch_(?P<switch_id>\d+)"
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Import the BL-NET set up in configuration.yaml."""
    if DOMAIN in config:
        # the imported entry can only be set up once this returns
        hass.async_create_task(_async_import(hass, dict(config[DOMAIN])))
    return True


async def _async_import(hass: HomeAssistant, yaml_config: dict) -> None:
    """Import configuration.yaml and ask to remove it from there."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=yaml_config
    )
    if (
        result["type"] is FlowResultType.CREATE_ENTRY
        or result.get("reason") == "already_configured"
    ):
        ir.async_create_issue(
            hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            breaks_in_ha_version=None,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={"domain": DOMAIN, "integration_title": "BLNET"},
        )


async def async_setup_entry(hass: HomeAssistant, entry: BLNETConfigEntry) -> bool:
    """Connect to the BL-NET and set up its entities."""
    _migrate_resource(hass, entry)
    try:
        blnet = await async_create_blnet(hass, dict(entry.data))
    except (ValueError, AssertionError, OSError) as err:
        raise ConfigEntryNotReady(f"No BL-NET reached at {entry.data[CONF_RESOURCE]}") from err

    coordinator = BLNETCoordinator(hass, entry, blnet)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await blnet.close()
        raise
    entry.runtime_data = coordinator

    _migrate_legacy_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BLNETConfigEntry) -> bool:
    """Unload the entities of a BL-NET and close its direct connection."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.blnet.close()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: BLNETConfigEntry) -> None:
    """Apply changed options."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _migrate_resource(hass: HomeAssistant, entry: BLNETConfigEntry) -> None:
    """Add http:// to an address stored without a scheme, e.g. 10.0.0.47."""
    data = with_normalized_resource(dict(entry.data))
    if data == entry.data:
        return
    title = entry.title
    if title == entry_title(entry.data):
        title = entry_title(data)
    hass.config_entries.async_update_entry(entry, data=data, title=title)


@callback
def _migrate_legacy_entities(hass: HomeAssistant, entry: BLNETConfigEntry) -> None:
    """Hand the entities set up from configuration.yaml to the config entry.

    They keep their entity ids, names and history.
    """
    registry = er.async_get(hass)
    for registry_entry in list(registry.entities.values()):
        if registry_entry.platform != DOMAIN or registry_entry.config_entry_id is not None:
            continue
        match = LEGACY_UNIQUE_ID.fullmatch(registry_entry.unique_id)
        if match is None:
            continue
        if match["switch_id"] is not None:
            if match["mode"]:
                new_unique_id = mode_unique_id(entry.entry_id, match["switch_id"])
            else:
                new_unique_id = unique_id(entry.entry_id, DIGITAL, match["switch_id"])
        else:
            new_unique_id = unique_id(entry.entry_id, match["domain"], match["id"])
        if registry.async_get_entity_id(registry_entry.domain, DOMAIN, new_unique_id):
            continue
        _LOGGER.info("Moving %s to the BL-NET set up in the UI", registry_entry.entity_id)
        registry.async_update_entity(
            registry_entry.entity_id,
            new_unique_id=new_unique_id,
            config_entry_id=entry.entry_id,
        )
