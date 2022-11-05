"""The SolarEdge Modbus Integration."""
import logging
from datetime import timedelta
from typing import Any

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    DEFAULT_KEEP_MODBUS_OPEN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SINGLE_DEVICE_ENTITY,
    DOMAIN,
)
from .hub import DataUpdateFailed, HubInitFailed, SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


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
        entry.options.get(CONF_ADV_PWR_CONTROL, DEFAULT_ADV_PWR_CONTROL),
        entry.options.get(CONF_ADV_STOREDGE_CONTROL, DEFAULT_ADV_STOREDGE_CONTROL),
        entry.options.get(CONF_ADV_EXPORT_CONTROL, DEFAULT_ADV_EXPORT_CONTROL),
    )

    coordinator = SolarEdgeCoordinator(
        hass,
        solaredge_hub,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": solaredge_hub,
        "coordinator": coordinator,
    }

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    solaredge_hub = hass.data[DOMAIN][entry.entry_id]["hub"]
    await solaredge_hub.shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    solaredge_hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]

    known_devices = []

    for inverter in solaredge_hub.inverters:
        inverter_device_ids = {
            dev_id[1]
            for dev_id in inverter.device_info["identifiers"]
            if dev_id[0] == DOMAIN
        }
        for dev_id in inverter_device_ids:
            known_devices.append(dev_id)

    for meter in solaredge_hub.meters:
        meter_device_ids = {
            dev_id[1]
            for dev_id in meter.device_info["identifiers"]
            if dev_id[0] == DOMAIN
        }
        for dev_id in meter_device_ids:
            known_devices.append(dev_id)

    for battery in solaredge_hub.batteries:
        battery_device_ids = {
            dev_id[1]
            for dev_id in battery.device_info["identifiers"]
            if dev_id[0] == DOMAIN
        }
        for dev_id in battery_device_ids:
            known_devices.append(dev_id)

    this_device_ids = {
        dev_id[1] for dev_id in device_entry.identifiers if dev_id[0] == DOMAIN
    }

    for device_id in this_device_ids:
        if device_id in known_devices:
            _LOGGER.error(f"Failed to remove device entry: device {device_id} in use")
            return False

    return True


class SolarEdgeCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, hub, scan_interval):
        super().__init__(
            hass,
            _LOGGER,
            name="SolarEdge Coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._hub = hub

        if scan_interval < 10 and not self._hub.keep_modbus_open:
            _LOGGER.warning("Polling frequency < 10, requiring keep modbus open.")
            self._hub.keep_modbus_open = True

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(self._hub.coordinator_timeout):
                return await self._hub.async_refresh_modbus_data()

        except HubInitFailed as e:
            raise UpdateFailed(f"{e}")

        except DataUpdateFailed as e:
            raise UpdateFailed(f"{e}")
