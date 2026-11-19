"""Tests of setting up a BL-NET in the UI."""
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.blnet.const import CONF_NODE, CONF_USE_TA, CONF_USE_WEB, DOMAIN

from .conftest import ENTRY_DATA, RESOURCE


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user(hass, blnet):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    user_input = {**ENTRY_DATA, CONF_PASSWORD: "0128", CONF_NODE: 20}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == RESOURCE
    assert result["data"] == user_input
    blnet.cls.assert_called_with(
        RESOURCE, password="0128", web_port=80, ta_port=40000, use_web=True, use_ta=False
    )
    blnet.fetch.assert_called_with(20)


async def test_user_cannot_connect(hass, blnet):
    blnet.cls.side_effect = ValueError("No BLNET found")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # it works once the BL-NET answers
    blnet.cls.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_unknown_error(hass, blnet):
    blnet.fetch.side_effect = KeyError("analog")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["errors"] == {"base": "unknown"}


async def test_user_no_connection(hass, blnet):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_USE_WEB: False, CONF_USE_TA: False}
    )
    assert result["errors"] == {"base": "no_connection"}
    blnet.cls.assert_not_called()


async def test_user_already_configured(hass, blnet, config_entry):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_import(hass, blnet):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={CONF_RESOURCE: RESOURCE, CONF_SCAN_INTERVAL: 60, CONF_USE_WEB: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_RESOURCE: RESOURCE, CONF_USE_WEB: True}
    assert result["options"] == {CONF_SCAN_INTERVAL: 60}


async def test_options(hass, blnet, config_entry):
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SCAN_INTERVAL: 60}
    # the entry is reloaded to poll at the new interval
    assert config_entry.runtime_data.update_interval.total_seconds() == 60
