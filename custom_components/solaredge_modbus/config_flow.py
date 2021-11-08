import voluptuous as vol
import ipaddress
import re

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
import homeassistant.helpers.config_validation as cv
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_PORT,
    CONF_NUMBER_INVERTERS,
    DEFAULT_NUMBER_INVERTERS,
    CONF_READ_METER1,
    CONF_READ_METER2,
    CONF_READ_METER3,
    DEFAULT_READ_METER1,
    DEFAULT_READ_METER2,
    DEFAULT_READ_METER3,
)
from homeassistant.core import HomeAssistant, callback


def host_valid(host):
    """Return True if hostname or IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True
    except ValueError:
        disallowed = re.compile(r"[^a-zA-Z\d\-]")
        return all(x and not disallowed.search(x) for x in host.split("."))

@callback
def solaredge_modbus_entries(hass: HomeAssistant):
    """Return the hosts already configured."""
    return set(
        entry.data[CONF_HOST] for entry in hass.config_entries.async_entries(DOMAIN)
    )

class SolaredgeModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Solaredge Modbus configflow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def _host_in_configuration_exists(self, host) -> bool:
        """Return True if host exists in configuration."""
        if host in solaredge_modbus_entries(self.hass):
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
            elif user_input[CONF_NUMBER_INVERTERS] > 32:
                errors[CONF_NUMBER_INVERTERS] = "max_inverters"  
            elif user_input[CONF_NUMBER_INVERTERS] < 1:
                errors[CONF_NUMBER_INVERTERS] = "min_inverters"
            elif user_input[CONF_PORT] < 1:
                errors[CONF_PORT] = "invalid_tcp_port"
            elif user_input[CONF_PORT] > 65535:
                errors[CONF_PORT] = "invalid_tcp_port"
            elif user_input[CONF_SCAN_INTERVAL] < 10:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            elif user_input[CONF_SCAN_INTERVAL] > 86400:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
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
                CONF_READ_METER1: DEFAULT_READ_METER1,
                CONF_READ_METER2: DEFAULT_READ_METER2,
                CONF_READ_METER3: DEFAULT_READ_METER3,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default=user_input[CONF_NAME]
                    ): cv.string,
                    vol.Required(
                        CONF_HOST, default=user_input[CONF_HOST]
                    ): cv.string,
                    vol.Required(
                        CONF_PORT, default=user_input[CONF_PORT]
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_NUMBER_INVERTERS, default=user_input[CONF_NUMBER_INVERTERS]
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_READ_METER1, default=user_input[CONF_READ_METER1]
                    ): cv.boolean,
                    vol.Optional(
                        CONF_READ_METER2, default=user_input[CONF_READ_METER2]
                    ): cv.boolean,
                    vol.Optional(
                        CONF_READ_METER3, default=user_input[CONF_READ_METER3]
                    ): cv.boolean,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=user_input[CONF_SCAN_INTERVAL]
                    ): vol.Coerce(int),
                },
            ),
            errors=errors
        )
