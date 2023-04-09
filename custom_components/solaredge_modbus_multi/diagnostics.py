"""Diagnostics support for SolarEdge Modbus Multi Device."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

REDACT_CONFIG = {"unique_id", "host"}
REDACT_INVERTER = {"C_SerialNumber"}
REDACT_METER = {"C_SerialNumber"}
REDACT_BATTERY = {"B_SerialNumber"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]

    data: dict[str, Any] = {
        "config_entry": async_redact_data(config_entry.as_dict(), REDACT_CONFIG)
    }

    for inverter in hub.inverters:
        inverter: dict[str, Any] = {
            f"inverter_unit_id_{inverter.inverter_unit_id}": {
                "common": inverter.decoded_common,
                "model": inverter.decoded_model,
                "mmppt": inverter.decoded_mmppt,
                "storage": inverter.decoded_storage,
            }
        }
        data.update(async_redact_data(inverter, REDACT_INVERTER))

    for meter in hub.meters:
        meter: dict[str, Any] = {
            f"meter_id_{meter.meter_id}": {
                "inverter_unit_id": meter.inverter_unit_id,
                "common": meter.decoded_common,
                "model": meter.decoded_model,
            }
        }
        data.update(async_redact_data(meter, REDACT_METER))

    for battery in hub.batteries:
        battery: dict[str, Any] = {
            f"battery_id_{battery.battery_id}": {
                "inverter_unit_id": battery.inverter_unit_id,
                "common": battery.decoded_common,
                "model": battery.decoded_model,
            }
        }
        data.update(async_redact_data(battery, REDACT_BATTERY))

    return data
