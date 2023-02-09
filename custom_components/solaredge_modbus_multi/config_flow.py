import ipaddress
import re

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_NAME, DOMAIN, ConfDefaultFlag, ConfDefaultInt, ConfName


def host_valid(host):
    """Return True if hostname or IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True
    except ValueError:
        disallowed = re.compile(r"[^a-zA-Z\d\-]")
        return all(x and not disallowed.search(x) for x in host.split("."))


@callback
def solaredge_modbus_multi_entries(hass: HomeAssistant):
    """Return the hosts already configured."""
    return set(
        entry.data[CONF_HOST] for entry in hass.config_entries.async_entries(DOMAIN)
    )


class SolaredgeModbusMultiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Solaredge Modbus configflow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return SolaredgeModbusMultiOptionsFlowHandler(config_entry)

    def _host_in_configuration_exists(self, host) -> bool:
        """Return True if host exists in configuration."""
        if host in solaredge_modbus_multi_entries(self.hass):
            return True
        return False

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            if self._host_in_configuration_exists(user_input[CONF_HOST]):
                errors[CONF_HOST] = "already_configured"
            elif not host_valid(user_input[CONF_HOST]):
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
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )
        else:
            user_input = {
                CONF_NAME: DEFAULT_NAME,
                CONF_HOST: "",
                CONF_PORT: ConfDefaultInt.PORT,
                ConfName.NUMBER_INVERTERS: ConfDefaultInt.NUMBER_INVERTERS,
                ConfName.DEVICE_ID: ConfDefaultInt.DEVICE_ID,
            }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=user_input[CONF_NAME]): cv.string,
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
                },
            ),
            errors=errors,
        )


class SolaredgeModbusMultiOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        errors = {}

        """Manage the options."""
        if user_input is not None:
            if user_input[CONF_SCAN_INTERVAL] < 1:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            elif user_input[CONF_SCAN_INTERVAL] > 86400:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
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
                ConfName.SINGLE_DEVICE_ENTITY: self.config_entry.options.get(
                    ConfName.SINGLE_DEVICE_ENTITY,
                    bool(ConfDefaultFlag.SINGLE_DEVICE_ENTITY),
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
                ConfName.ADV_PWR_CONTROL: self.config_entry.options.get(
                    ConfName.ADV_PWR_CONTROL, bool(ConfDefaultFlag.ADV_PWR_CONTROL)
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
                        f"{ConfName.SINGLE_DEVICE_ENTITY}",
                        default=user_input[ConfName.SINGLE_DEVICE_ENTITY],
                    ): cv.boolean,
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
                        f"{ConfName.ADV_PWR_CONTROL}",
                        default=user_input[ConfName.ADV_PWR_CONTROL],
                    ): cv.boolean,
                },
            ),
            errors=errors,
        )

    async def async_step_battery_options(self, user_input=None) -> FlowResult:
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
                        f"{ConfName.BATTERY_RATING_ADJUST}",
                        default=user_input[ConfName.BATTERY_RATING_ADJUST],
                    ): vol.Coerce(int),
                }
            ),
            errors=errors,
        )

    async def async_step_adv_pwr_ctl(self, user_input=None) -> FlowResult:
        """Power Control Options"""
        errors = {}

        if user_input is not None:
            if user_input[ConfName.SLEEP_AFTER_WRITE] < 0:
                errors[ConfName.SLEEP_AFTER_WRITE] = "invalid_sleep_interval"
            elif user_input[ConfName.SLEEP_AFTER_WRITE] > 60:
                errors[ConfName.SLEEP_AFTER_WRITE] = "invalid_sleep_interval"
            else:
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
                ConfName.SLEEP_AFTER_WRITE: self.config_entry.options.get(
                    ConfName.SLEEP_AFTER_WRITE, ConfDefaultInt.SLEEP_AFTER_WRITE
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
                    vol.Optional(
                        f"{ConfName.SLEEP_AFTER_WRITE}",
                        default=user_input[ConfName.SLEEP_AFTER_WRITE],
                    ): vol.Coerce(int),
                }
            ),
            errors=errors,
        )
