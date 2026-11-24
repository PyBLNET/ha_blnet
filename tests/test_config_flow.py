"""Tests of setting up a BL-NET in the UI."""
from unittest.mock import ANY

import aiohttp
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL, CONF_TIMEOUT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.blnet.const import CONF_NODE, CONF_USE_TA, CONF_USE_WEB, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    assert result["title"] == f"{RESOURCE} (CAN node 20)"
    assert result["data"] == user_input
    blnet.create.assert_called_with(
        RESOURCE,
        ANY,
        password="0128",
        timeout=30,
        web_port=80,
        ta_port=40000,
        use_web=True,
        use_ta=False,
    )
    # the integration's own session, pyblnet sends the login cookie itself
    session = blnet.create.call_args.args[1]
    assert isinstance(session.cookie_jar, aiohttp.DummyCookieJar)
    blnet.fetch.assert_called_with(20)
    blnet.close.assert_awaited()


async def test_user_cannot_connect(hass, blnet):
    blnet.create.side_effect = ValueError("No BLNET found")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ENTRY_DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # it works once the BL-NET answers
    blnet.create.side_effect = None
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
    blnet.create.assert_not_called()


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
        result["flow_id"], {CONF_SCAN_INTERVAL: 60, CONF_TIMEOUT: 45}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SCAN_INTERVAL: 60, CONF_TIMEOUT: 45}
    # the entry is reloaded to poll at the new interval, with the new timeout
    assert config_entry.runtime_data.update_interval.total_seconds() == 60
    assert blnet.create.call_args.kwargs["timeout"] == 45


async def test_options_timeout_default(hass, blnet, config_entry):
    """Entries from before the timeout option get 30 s, also in the form."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert blnet.create.call_args.kwargs["timeout"] == 30

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 360}
    )
    assert config_entry.options == {CONF_SCAN_INTERVAL: 360, CONF_TIMEOUT: 30}


async def test_user_second_can_node(hass, blnet, config_entry):
    """Another UVR1611 behind the same BL-NET is set up by its CAN node."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NODE: 2}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{RESOURCE} (CAN node 2)"
    blnet.fetch.assert_any_call(2)

    # but each node only once
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NODE: 2}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_can_node(hass, blnet, config_entry):
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NODE: 3}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_NODE] == 3
    assert config_entry.title == f"{RESOURCE} (CAN node 3)"
    # reloaded to read the new node
    assert config_entry.runtime_data.node == 3
    blnet.fetch.assert_called_with(3)


async def test_reconfigure_to_configured_node(hass, blnet, config_entry):
    other = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, CONF_NODE: 2})
    other.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NODE: 2}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert CONF_NODE not in config_entry.data


async def test_user_address_without_scheme(hass, blnet):
    """An address like 10.0.0.47 is stored with http://."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_RESOURCE: " 192.168.1.10 "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RESOURCE] == RESOURCE
    assert result["title"] == RESOURCE
    assert blnet.create.call_args.args[0] == RESOURCE


async def test_user_address_without_scheme_already_configured(hass, blnet, config_entry):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_RESOURCE: "192.168.1.10"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
