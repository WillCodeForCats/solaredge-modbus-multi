"""Repairs for SolarEdge Modbus Multi Device."""
from __future__ import annotations

from typing import cast

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import ConfName
from .helpers import host_valid


class CheckConfigurationRepairFlow(RepairsFlow):
    """Handler for an issue fixing flow."""

    _entry: ConfigEntry

    def __init__(self, entry: ConfigEntry) -> None:
        """Create flow."""

        self._entry = entry
        super().__init__()

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""
        errors = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].lower()

            if not host_valid(user_input[CONF_HOST]):
                errors[CONF_HOST] = "invalid_host"
            elif user_input[CONF_PORT] < 1:
                errors[CONF_PORT] = "invalid_tcp_port"
            elif user_input[CONF_PORT] > 65535:
                errors[CONF_PORT] = "invalid_tcp_port"
            elif user_input[ConfName.DEVICE_ID] > 247:
                errors[ConfName.DEVICE_ID] = "max_device_id"
            elif user_input[ConfName.DEVICE_ID] < 1:
                errors[ConfName.DEVICE_ID] = "min_device_id"
            elif user_input[ConfName.NUMBER_INVERTERS] > 32:
                errors[ConfName.NUMBER_INVERTERS] = "max_inverters"
            elif user_input[ConfName.NUMBER_INVERTERS] < 1:
                errors[ConfName.NUMBER_INVERTERS] = "min_inverters"
            elif (
                user_input[ConfName.NUMBER_INVERTERS] + user_input[ConfName.DEVICE_ID]
                > 247
            ):
                errors[ConfName.NUMBER_INVERTERS] = "too_many_inverters"
            else:
                self.hass.config_entries.async_update_entry(
                    self._entry, data={**self._entry.data, **user_input}
                )
                return self.async_create_entry(title="", data={})
        else:
            user_input = {
                CONF_HOST: self._entry.data[CONF_HOST],
                CONF_PORT: self._entry.data[CONF_PORT],
                ConfName.NUMBER_INVERTERS: self._entry.data[ConfName.NUMBER_INVERTERS],
                ConfName.DEVICE_ID: self._entry.data[ConfName.DEVICE_ID],
            }

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=user_input[CONF_HOST]): cv.string,
                    vol.Required(CONF_PORT, default=user_input[CONF_PORT]): vol.Coerce(
                        int
                    ),
                    vol.Required(
                        f"{ConfName.NUMBER_INVERTERS}",
                        default=user_input[ConfName.NUMBER_INVERTERS],
                    ): vol.Coerce(int),
                    vol.Required(
                        f"{ConfName.DEVICE_ID}", default=user_input[ConfName.DEVICE_ID]
                    ): vol.Coerce(int),
                }
            ),
            errors=errors,
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""

    entry_id = cast(str, data["entry_id"])

    if (entry := hass.config_entries.async_get_entry(entry_id)) is not None:
        if issue_id == "check_configuration":
            return CheckConfigurationRepairFlow(entry)
