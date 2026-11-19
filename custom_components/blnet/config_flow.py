"""Set up a BL-NET in the UI."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DOMAIN,
)
from .coordinator import BLNETConfigEntry, create_blnet

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({
    vol.Required(CONF_RESOURCE): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
    vol.Optional(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    vol.Optional(CONF_NODE): cv.positive_int,
    vol.Required(CONF_USE_WEB, default=True): bool,
    vol.Required(CONF_WEB_PORT, default=DEFAULT_WEB_PORT): cv.port,
    vol.Required(CONF_USE_TA, default=False): bool,
    vol.Required(CONF_TA_PORT, default=DEFAULT_TA_PORT): cv.port,
})


class CannotConnect(Exception):
    """No BL-NET answered."""


def _validate(data: dict[str, Any]) -> None:
    """Fetch the values once to check the settings (blocking)."""
    try:
        create_blnet(data).fetch(data.get(CONF_NODE))
    except (ValueError, AssertionError, OSError) as err:
        raise CannotConnect from err


class BLNETConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a BL-NET."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_RESOURCE: user_input[CONF_RESOURCE]})
            if not user_input[CONF_USE_WEB] and not user_input[CONF_USE_TA]:
                errors["base"] = "no_connection"
            else:
                try:
                    await self.hass.async_add_executor_job(_validate, user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error connecting to the BL-NET")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_RESOURCE], data=user_input
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the setup from configuration.yaml, without checking the connection."""
        self._async_abort_entries_match({CONF_RESOURCE: import_data[CONF_RESOURCE]})
        data = dict(import_data)
        scan_interval = data.pop(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_create_entry(
            title=data[CONF_RESOURCE],
            data=data,
            options={CONF_SCAN_INTERVAL: scan_interval},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: BLNETConfigEntry) -> BLNETOptionsFlow:
        return BLNETOptionsFlow()


class BLNETOptionsFlow(OptionsFlow):
    """Change how often the BL-NET is polled."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=10)
            ),
        })
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
