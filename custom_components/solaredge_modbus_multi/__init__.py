"""The SolarEdge Modbus Integration."""
from .hub import SolarEdgeModbusMultiHub

#import asyncio

from homeassistant.config_entries import ConfigEntry

from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL
)
from homeassistant.core import HomeAssistant
from .const import (
    DOMAIN,
    CONF_NUMBER_INVERTERS,
    CONF_DEVICE_ID
)

PLATFORMS: list[str] = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarEdge Modbus from a config entry."""
    solaredge_hub = SolarEdgeModbusMultiHub(
        hass,
        entry.data[CONF_NAME],
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_SCAN_INTERVAL, 300),
        entry.data.get(CONF_NUMBER_INVERTERS, 1),
        entry.data.get(CONF_DEVICE_ID, 1)
    )
        
    await solaredge_hub.async_init_solaredge()
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = solaredge_hub

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        solaredge_hub = hass.data[DOMAIN][entry.entry_id]
        await solaredge_hub.shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an options update."""
    await hass.config_entries.async_reload(entry.entry_id)
