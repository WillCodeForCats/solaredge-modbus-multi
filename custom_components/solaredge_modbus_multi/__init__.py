"""The SolarEdge Modbus Integration."""
import async_timeout
import logging

from .hub import SolarEdgeModbusMultiHub
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry

from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL
)
from homeassistant.core import HomeAssistant
from .const import (
    DOMAIN, DEFAULT_SCAN_INTERVAL,
    CONF_NUMBER_INVERTERS,
    CONF_DEVICE_ID,
    CONF_DETECT_METERS, DEFAULT_DETECT_METERS,
    CONF_DETECT_BATTERIES, DEFAULT_DETECT_BATTERIES,
    CONF_SINGLE_DEVICE_ENTITY, DEFAULT_SINGLE_DEVICE_ENTITY,
    CONF_KEEP_MODBUS_OPEN, DEFAULT_KEEP_MODBUS_OPEN,
)

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarEdge Modbus from a config entry."""
    
    entry_updates: dict[str, Any] = {}
    if CONF_SCAN_INTERVAL in entry.data:
        data = {**entry.data}
        entry_updates["data"] = data
        entry_updates["options"] = {
            **entry.options,
            CONF_SCAN_INTERVAL: data.pop(CONF_SCAN_INTERVAL),
        }
    if entry_updates:
        hass.config_entries.async_update_entry(entry, **entry_updates)
    
    solaredge_hub = SolarEdgeModbusMultiHub(
        hass,
        entry.data[CONF_NAME],
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_NUMBER_INVERTERS, 1),
        entry.data.get(CONF_DEVICE_ID, 1),
        entry.options.get(CONF_DETECT_METERS, DEFAULT_DETECT_METERS),
        entry.options.get(CONF_DETECT_BATTERIES, DEFAULT_DETECT_BATTERIES),
        entry.options.get(CONF_SINGLE_DEVICE_ENTITY, DEFAULT_SINGLE_DEVICE_ENTITY),
        entry.options.get(CONF_KEEP_MODBUS_OPEN, DEFAULT_KEEP_MODBUS_OPEN),
    )

    coordinator = SolarEdgeCoordinator(
        hass,
        solaredge_hub,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = solaredge_hub

    await coordinator.async_config_entry_first_refresh()
    
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    solaredge_hub = hass.data[DOMAIN][entry.entry_id]    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        await solaredge_hub.shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an options update."""
    await hass.config_entries.async_reload(entry.entry_id)

class SolarEdgeCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, hub, scan_interval):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="SolarEdgeCoordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.hub = hub
        
        if scan_interval < 10:
            _LOGGER.warning("Polling frequency < 10, requiring keep modbus open.")
            hub.keep_modbus_open = True
    
    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            async with async_timeout.timeout(3):
                return await self.hub.async_refresh_modbus_data()
        
        except Exception as e:
            raise UpdateFailed(f"Error updating modbus data: {e}")
