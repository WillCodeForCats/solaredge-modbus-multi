"""Config flow for the SolarEdge Modbus Multi integration."""

from __future__ import annotations

import re
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    ConfDefaultFlag,
    ConfDefaultInt,
    ConfDefaultStr,
    ConfName,
)
from .helpers import device_list_from_string, host_valid


def generate_config_schema(step_id: str, user_input: dict[str, Any]) -> vol.Schema:
    """Generate config flow or repair schema."""
    schema: dict[vol.Marker, Any] = {}

    if step_id == "user":
        schema |= {vol.Required(CONF_NAME, default=user_input[CONF_NAME]): cv.string}

    if step_id in ["reconfigure", "confirm", "user"]:
        schema |= {
            vol.Required(CONF_HOST, default=user_input[CONF_HOST]): cv.string,
            vol.Required(CONF_PORT, default=user_input[CONF_PORT]): vol.Coerce(int),
            vol.Required(
                f"{ConfName.DEVICE_LIST}",
                default=user_input[ConfName.DEVICE_LIST],
            ): cv.string,
        }

    return vol.Schema(schema)


class SolaredgeModbusMultiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SolarEdge Modbus Multi."""

    VERSION = 2
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow for SolarEdge Modbus Multi."""
        return SolaredgeModbusMultiOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial config flow step."""
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
                    new_unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                    await self.async_set_unique_id(new_unique_id)

                    self._abort_if_unique_id_configured()

                    user_input[ConfName.DEVICE_LIST] = device_list_from_string(
                        user_input[ConfName.DEVICE_LIST]
                    )

                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=user_input
                    )
        else:
            user_input = {
                CONF_NAME: DEFAULT_NAME,
                CONF_HOST: "",
                CONF_PORT: ConfDefaultInt.PORT,
                ConfName.DEVICE_LIST: ConfDefaultStr.DEVICE_LIST,
            }

        return self.async_show_form(
            step_id="user",
            data_schema=generate_config_schema("user", user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the reconfigure flow step."""
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

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

                    if this_unique_id != config_entry.unique_id:
                        self._async_abort_entries_match(
                            {
                                "host": user_input[CONF_HOST],
                                "port": user_input[CONF_PORT],
                            }
                        )

                    return self.async_update_reload_and_abort(
                        config_entry,
                        unique_id=this_unique_id,
                        data={**config_entry.data, **user_input},
                        reason="reconfigure_successful",
                    )
        else:
            reconfig_device_list = ",".join(
                str(device)
                for device in config_entry.data.get(
                    ConfName.DEVICE_LIST, ConfDefaultStr.DEVICE_LIST
                )
            )

            user_input = {
                CONF_HOST: config_entry.data.get(CONF_HOST),
                CONF_PORT: config_entry.data.get(CONF_PORT, ConfDefaultInt.PORT),
                ConfName.DEVICE_LIST: reconfig_device_list,
            }

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=generate_config_schema("reconfigure", user_input),
            errors=errors,
        )


class SolaredgeModbusMultiOptionsFlowHandler(OptionsFlow):
    """Handle an options flow for SolarEdge Modbus Multi."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial options flow step."""
        errors = {}

        if user_input is not None:
            if user_input[CONF_SCAN_INTERVAL] < 1:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            elif user_input[CONF_SCAN_INTERVAL] > 86400:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            elif user_input[ConfName.SLEEP_AFTER_WRITE] < 0:
                errors[ConfName.SLEEP_AFTER_WRITE] = "invalid_sleep_interval"
            elif user_input[ConfName.SLEEP_AFTER_WRITE] > 60:
                errors[ConfName.SLEEP_AFTER_WRITE] = "invalid_sleep_interval"
            else:
                if user_input[ConfName.DETECT_BATTERIES] is True:
                    self.init_info = user_input
                    return await self.async_step_battery_options()
                else:
                    if user_input[ConfName.ADV_PWR_CONTROL] is True:
                        self.init_info = user_input
                        return await self.async_step_adv_pwr_ctl()

                    else:
                        return self.async_create_entry(title="", data=user_input)

        else:
            user_input = {
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, ConfDefaultInt.SCAN_INTERVAL
                ),
                ConfName.KEEP_MODBUS_OPEN: self.config_entry.options.get(
                    ConfName.KEEP_MODBUS_OPEN, bool(ConfDefaultFlag.KEEP_MODBUS_OPEN)
                ),
                ConfName.DETECT_METERS: self.config_entry.options.get(
                    ConfName.DETECT_METERS, bool(ConfDefaultFlag.DETECT_METERS)
                ),
                ConfName.DETECT_BATTERIES: self.config_entry.options.get(
                    ConfName.DETECT_BATTERIES, bool(ConfDefaultFlag.DETECT_BATTERIES)
                ),
                ConfName.DETECT_EXTRAS: self.config_entry.options.get(
                    ConfName.DETECT_EXTRAS, bool(ConfDefaultFlag.DETECT_EXTRAS)
                ),
                ConfName.ADV_PWR_CONTROL: self.config_entry.options.get(
                    ConfName.ADV_PWR_CONTROL, bool(ConfDefaultFlag.ADV_PWR_CONTROL)
                ),
                ConfName.SLEEP_AFTER_WRITE: self.config_entry.options.get(
                    ConfName.SLEEP_AFTER_WRITE, ConfDefaultInt.SLEEP_AFTER_WRITE
                ),
            }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=user_input[CONF_SCAN_INTERVAL],
                    ): vol.Coerce(int),
                    vol.Optional(
                        f"{ConfName.KEEP_MODBUS_OPEN}",
                        default=user_input[ConfName.KEEP_MODBUS_OPEN],
                    ): cv.boolean,
                    vol.Optional(
                        f"{ConfName.DETECT_METERS}",
                        default=user_input[ConfName.DETECT_METERS],
                    ): cv.boolean,
                    vol.Optional(
                        f"{ConfName.DETECT_BATTERIES}",
                        default=user_input[ConfName.DETECT_BATTERIES],
                    ): cv.boolean,
                    vol.Optional(
                        f"{ConfName.DETECT_EXTRAS}",
                        default=user_input[ConfName.DETECT_EXTRAS],
                    ): cv.boolean,
                    vol.Optional(
                        f"{ConfName.ADV_PWR_CONTROL}",
                        default=user_input[ConfName.ADV_PWR_CONTROL],
                    ): cv.boolean,
                    vol.Optional(
                        f"{ConfName.SLEEP_AFTER_WRITE}",
                        default=user_input[ConfName.SLEEP_AFTER_WRITE],
                    ): vol.Coerce(int),
                },
            ),
            errors=errors,
        )

    async def async_step_battery_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Battery Options"""
        errors = {}

        if user_input is not None:
            if user_input[ConfName.BATTERY_RATING_ADJUST] < 0:
                errors[ConfName.BATTERY_RATING_ADJUST] = "invalid_percent"
            elif user_input[ConfName.BATTERY_RATING_ADJUST] > 100:
                errors[ConfName.BATTERY_RATING_ADJUST] = "invalid_percent"
            else:
                if self.init_info[ConfName.ADV_PWR_CONTROL] is True:
                    self.init_info = {**self.init_info, **user_input}
                    return await self.async_step_adv_pwr_ctl()

                return self.async_create_entry(
                    title="", data={**self.init_info, **user_input}
                )

        else:
            user_input = {
                ConfName.ALLOW_BATTERY_ENERGY_RESET: self.config_entry.options.get(
                    ConfName.ALLOW_BATTERY_ENERGY_RESET,
                    bool(ConfDefaultFlag.ALLOW_BATTERY_ENERGY_RESET),
                ),
                ConfName.BATTERY_ENERGY_RESET_CYCLES: self.config_entry.options.get(
                    ConfName.BATTERY_ENERGY_RESET_CYCLES,
                    ConfDefaultInt.BATTERY_ENERGY_RESET_CYCLES,
                ),
                ConfName.BATTERY_RATING_ADJUST: self.config_entry.options.get(
                    ConfName.BATTERY_RATING_ADJUST,
                    ConfDefaultInt.BATTERY_RATING_ADJUST,
                ),
            }

        return self.async_show_form(
            step_id="battery_options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        f"{ConfName.ALLOW_BATTERY_ENERGY_RESET}",
                        default=user_input[ConfName.ALLOW_BATTERY_ENERGY_RESET],
                    ): cv.boolean,
                    vol.Optional(
                        f"{ConfName.BATTERY_ENERGY_RESET_CYCLES}",
                        default=user_input[ConfName.BATTERY_ENERGY_RESET_CYCLES],
                    ): vol.Coerce(int),
                    vol.Optional(
                        f"{ConfName.BATTERY_RATING_ADJUST}",
                        default=user_input[ConfName.BATTERY_RATING_ADJUST],
                    ): vol.Coerce(int),
                }
            ),
            errors=errors,
        )

    async def async_step_adv_pwr_ctl(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Power Control Options"""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.init_info, **user_input}
            )

        else:
            user_input = {
                ConfName.ADV_STORAGE_CONTROL: self.config_entry.options.get(
                    ConfName.ADV_STORAGE_CONTROL,
                    bool(ConfDefaultFlag.ADV_STORAGE_CONTROL),
                ),
                ConfName.ADV_SITE_LIMIT_CONTROL: self.config_entry.options.get(
                    ConfName.ADV_SITE_LIMIT_CONTROL,
                    bool(ConfDefaultFlag.ADV_SITE_LIMIT_CONTROL),
                ),
            }

        return self.async_show_form(
            step_id="adv_pwr_ctl",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        f"{ConfName.ADV_STORAGE_CONTROL}",
                        default=user_input[ConfName.ADV_STORAGE_CONTROL],
                    ): cv.boolean,
                    vol.Required(
                        f"{ConfName.ADV_SITE_LIMIT_CONTROL}",
                        default=user_input[ConfName.ADV_SITE_LIMIT_CONTROL],
                    ): cv.boolean,
                }
            ),
            errors=errors,
        )
