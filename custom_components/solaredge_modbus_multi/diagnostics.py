"""Diagnostics support for SolarEdge Modbus Multi Device."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .helpers import float_to_hex

REDACT_CONFIG = {"unique_id", "host"}
REDACT_INVERTER = {"identifiers", "C_SerialNumber", "serial_number"}
REDACT_METER = {"identifiers", "C_SerialNumber", "serial_number", "via_device"}
REDACT_BATTERY = {"identifiers", "B_SerialNumber", "serial_number", "via_device"}


def format_values(format_input) -> Any:
    if isinstance(format_input, dict):
        formatted_dict = {}
        for name, value in iter(format_input.items()):
            if isinstance(value, dict):
                display_value = format_values(value)
            elif isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value

            formatted_dict[name] = display_value

        return formatted_dict

    return format_input


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]

    data: dict[str, Any] = {
        "pymodbus_version": hub.pymodbus_version,
        "config_entry": async_redact_data(config_entry.as_dict(), REDACT_CONFIG),
        "yaml": async_redact_data(hass.data[DOMAIN]["yaml"], REDACT_CONFIG),
    }

    for inverter in hub.inverters:
        inverter: dict[str, Any] = {
            f"inverter_unit_id_{inverter.inverter_unit_id}": {
                "device_info": inverter.device_info,
                "global_power_control": inverter.global_power_control,
                "advanced_power_control": inverter.advanced_power_control,
                "site_limit_control": inverter.site_limit_control,
                "common": inverter.decoded_common,
                "model": format_values(inverter.decoded_model),
                "is_mmppt": inverter.is_mmppt,
                "mmppt": format_values(inverter.decoded_mmppt),
                "has_battery": inverter.has_battery,
                "storage_control": format_values(inverter.decoded_storage_control),
            }
        }

        data.update(async_redact_data(inverter, REDACT_INVERTER))

    for meter in hub.meters:
        meter: dict[str, Any] = {
            f"meter_id_{meter.meter_id}": {
                "device_info": meter.device_info,
                "inverter_unit_id": meter.inverter_unit_id,
                "common": meter.decoded_common,
                "model": format_values(meter.decoded_model),
            }
        }
        data.update(async_redact_data(meter, REDACT_METER))

    for battery in hub.batteries:
        battery: dict[str, Any] = {
            f"battery_id_{battery.battery_id}": {
                "device_info": battery.device_info,
                "inverter_unit_id": battery.inverter_unit_id,
                "common": battery.decoded_common,
                "model": format_values(battery.decoded_model),
            }
        }
        data.update(async_redact_data(battery, REDACT_BATTERY))

    return data
