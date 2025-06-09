"""Repairs for SolarEdge Modbus Multi Device."""

from __future__ import annotations

import re
from typing import cast

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .config_flow import generate_config_schema
from .const import DOMAIN, ConfDefaultStr, ConfName
from .helpers import device_list_from_string, host_valid


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
            user_input[ConfName.DEVICE_LIST] = re.sub(
                r"\s+", "", user_input[ConfName.DEVICE_LIST], flags=re.UNICODE
            )

            try:
                inverter_count = len(
                    device_list_from_string(user_input[ConfName.DEVICE_LIST])
                )
            except HomeAssistantError as e:
                errors[ConfName.DEVICE_LIST] = f"{e}"

            else:
                if not host_valid(user_input[CONF_HOST]):
                    errors[CONF_HOST] = "invalid_host"
                elif not 1 <= user_input[CONF_PORT] <= 65535:
                    errors[CONF_PORT] = "invalid_tcp_port"
                elif not 1 <= inverter_count <= 32:
                    errors[ConfName.DEVICE_LIST] = "invalid_inverter_count"
                else:
                    user_input[ConfName.DEVICE_LIST] = device_list_from_string(
                        user_input[ConfName.DEVICE_LIST]
                    )
                    this_unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                    existing_entry = (
                        self.hass.config_entries.async_entry_for_domain_unique_id(
                            DOMAIN, this_unique_id
                        )
                    )

                    if (
                        existing_entry is not None
                        and self._entry.unique_id != this_unique_id
                    ):
                        errors[CONF_HOST] = "already_configured"
                        errors[CONF_PORT] = "already_configured"

                    else:
                        self.hass.config_entries.async_update_entry(
                            self._entry,
                            unique_id=this_unique_id,
                            data={**self._entry.data, **user_input},
                        )

                        return self.async_create_entry(title="", data={})

        else:
            reconfig_device_list = ",".join(
                str(device)
                for device in self._entry.data.get(
                    ConfName.DEVICE_LIST, ConfDefaultStr.DEVICE_LIST
                )
            )

            user_input = {
                CONF_HOST: self._entry.data[CONF_HOST],
                CONF_PORT: self._entry.data[CONF_PORT],
                ConfName.DEVICE_LIST: reconfig_device_list,
            }

        return self.async_show_form(
            step_id="confirm",
            data_schema=generate_config_schema("confirm", user_input),
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
