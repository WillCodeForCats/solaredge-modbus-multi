"""The SolarEdge Modbus Integration."""
#import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .hub import SolarEdgeModbusHub

from .const import (
    DOMAIN,
    CONF_NUMBER_INVERTERS, CONF_DEVICE_ID,
    CONF_READ_METER1, CONF_READ_METER2, CONF_READ_METER3, 
)

PLATFORMS: list[str] = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarEdge Modbus from a config entry."""
    hub = SolarEdgeModbusHub(
        hass,
        entry.data[CONF_NAME],
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_SCAN_INTERVAL],
        entry.data.get(CONF_READ_METER1, False),
        entry.data.get(CONF_READ_METER2, False),
        entry.data.get(CONF_READ_METER3, False),
        entry.data.get(CONF_NUMBER_INVERTERS, 1),
        entry.data.get(CONF_DEVICE_ID, 1)
    )
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Solaredge mobus entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
    return unload_ok
