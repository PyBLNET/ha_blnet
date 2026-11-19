"""Set up a BL-NET in the UI."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
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
from .coordinator import BLNETConfigEntry, blnet_lock, create_blnet, entry_title

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
        with blnet_lock(data):
            create_blnet(data).fetch(data.get(CONF_NODE))
    except (ValueError, AssertionError, OSError) as err:
        raise CannotConnect from err


class BLNETConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a BL-NET."""

    VERSION = 1

    def _abort_if_configured(self, data: dict[str, Any], ignore: str | None = None) -> None:
        """Abort if the CAN node of this BL-NET is set up already.

        Each CAN node of a BL-NET, e.g. one per UVR1611, is an entry of its own.
        """
        for entry in self._async_current_entries(include_ignore=False):
            if (
                entry.entry_id != ignore
                and entry.data[CONF_RESOURCE] == data[CONF_RESOURCE]
                and entry.data.get(CONF_NODE) == data.get(CONF_NODE)
            ):
                raise AbortFlow("already_configured")

    async def _async_check(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Errors of the settings, none if the BL-NET answers with them."""
        if not user_input[CONF_USE_WEB] and not user_input[CONF_USE_TA]:
            return {"base": "no_connection"}
        try:
            await self.hass.async_add_executor_job(_validate, user_input)
        except CannotConnect:
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error connecting to the BL-NET")
            return {"base": "unknown"}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._abort_if_configured(user_input)
            errors = await self._async_check(user_input)
            if not errors:
                return self.async_create_entry(title=entry_title(user_input), data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address, password, CAN node or connections of a BL-NET."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            self._abort_if_configured(user_input, ignore=entry.entry_id)
            errors = await self._async_check(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, title=entry_title(user_input), data=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the setup from configuration.yaml, without checking the connection."""
        self._abort_if_configured(import_data)
        data = dict(import_data)
        scan_interval = data.pop(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_create_entry(
            title=entry_title(data),
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
