import ipaddress
import re

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ADV_EXPORT_CONTROL,
    CONF_ADV_PWR_CONTROL,
    CONF_ADV_STOREDGE_CONTROL,
    CONF_DETECT_BATTERIES,
    CONF_DETECT_METERS,
    CONF_DEVICE_ID,
    CONF_KEEP_MODBUS_OPEN,
    CONF_NUMBER_INVERTERS,
    CONF_SINGLE_DEVICE_ENTITY,
    DEFAULT_ADV_EXPORT_CONTROL,
    DEFAULT_ADV_PWR_CONTROL,
    DEFAULT_ADV_STOREDGE_CONTROL,
    DEFAULT_DETECT_BATTERIES,
    DEFAULT_DETECT_METERS,
    DEFAULT_DEVICE_ID,
    DEFAULT_KEEP_MODBUS_OPEN,
    DEFAULT_NAME,
    DEFAULT_NUMBER_INVERTERS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SINGLE_DEVICE_ENTITY,
    DOMAIN,
)


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
            elif user_input[CONF_DEVICE_ID] > 247:
                errors[CONF_DEVICE_ID] = "max_device_id"
            elif user_input[CONF_DEVICE_ID] < 1:
                errors[CONF_DEVICE_ID] = "min_device_id"
            elif user_input[CONF_NUMBER_INVERTERS] > 32:
                errors[CONF_NUMBER_INVERTERS] = "max_inverters"
            elif user_input[CONF_NUMBER_INVERTERS] < 1:
                errors[CONF_NUMBER_INVERTERS] = "min_inverters"
            elif user_input[CONF_NUMBER_INVERTERS] + user_input[CONF_DEVICE_ID] > 247:
                errors[CONF_NUMBER_INVERTERS] = "too_many_inverters"
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
                CONF_PORT: DEFAULT_PORT,
                CONF_NUMBER_INVERTERS: DEFAULT_NUMBER_INVERTERS,
                CONF_DEVICE_ID: DEFAULT_DEVICE_ID,
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
                        CONF_NUMBER_INVERTERS,
                        default=user_input[CONF_NUMBER_INVERTERS],
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_DEVICE_ID, default=user_input[CONF_DEVICE_ID]
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
                if user_input[CONF_ADV_PWR_CONTROL] is True:
                    self.init_info = user_input
                    return await self.async_step_adv_pwr_ctl()
                else:
                    return self.async_create_entry(title="", data=user_input)

        else:
            user_input = {
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
                CONF_SINGLE_DEVICE_ENTITY: self.config_entry.options.get(
                    CONF_SINGLE_DEVICE_ENTITY, DEFAULT_SINGLE_DEVICE_ENTITY
                ),
                CONF_KEEP_MODBUS_OPEN: self.config_entry.options.get(
                    CONF_KEEP_MODBUS_OPEN, DEFAULT_KEEP_MODBUS_OPEN
                ),
                CONF_DETECT_METERS: self.config_entry.options.get(
                    CONF_DETECT_METERS, DEFAULT_DETECT_METERS
                ),
                CONF_DETECT_BATTERIES: self.config_entry.options.get(
                    CONF_DETECT_BATTERIES, DEFAULT_DETECT_BATTERIES
                ),
                CONF_ADV_PWR_CONTROL: self.config_entry.options.get(
                    CONF_ADV_PWR_CONTROL, DEFAULT_ADV_PWR_CONTROL
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
                        CONF_SINGLE_DEVICE_ENTITY,
                        default=user_input[CONF_SINGLE_DEVICE_ENTITY],
                    ): cv.boolean,
                    vol.Optional(
                        CONF_KEEP_MODBUS_OPEN,
                        default=user_input[CONF_KEEP_MODBUS_OPEN],
                    ): cv.boolean,
                    vol.Optional(
                        CONF_DETECT_METERS,
                        default=user_input[CONF_DETECT_METERS],
                    ): cv.boolean,
                    vol.Optional(
                        CONF_DETECT_BATTERIES,
                        default=user_input[CONF_DETECT_BATTERIES],
                    ): cv.boolean,
                    vol.Optional(
                        CONF_ADV_PWR_CONTROL,
                        default=user_input[CONF_ADV_PWR_CONTROL],
                    ): cv.boolean,
                },
            ),
            errors=errors,
        )

    async def async_step_adv_pwr_ctl(self, user_input=None) -> FlowResult:
        """Advanced Power Control"""
        errors = {}
        agree = {True: "Enable", False: "Disable"}

        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.init_info, **user_input}
            )

        else:
            user_input = {
                CONF_ADV_STOREDGE_CONTROL: self.config_entry.options.get(
                    CONF_ADV_STOREDGE_CONTROL, DEFAULT_ADV_STOREDGE_CONTROL
                ),
                CONF_ADV_EXPORT_CONTROL: self.config_entry.options.get(
                    CONF_ADV_EXPORT_CONTROL, DEFAULT_ADV_EXPORT_CONTROL
                ),
            }

        return self.async_show_form(
            step_id="adv_pwr_ctl",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADV_STOREDGE_CONTROL,
                        default=user_input[CONF_ADV_STOREDGE_CONTROL],
                    ): vol.In(agree),
                    vol.Required(
                        CONF_ADV_EXPORT_CONTROL,
                        default=user_input[CONF_ADV_EXPORT_CONTROL],
                    ): vol.In(agree),
                }
            ),
            errors=errors,
        )
