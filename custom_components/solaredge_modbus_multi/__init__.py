"""The SolarEdge Modbus Multi Integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, ConfDefaultInt, ConfName, RetrySettings
from .hub import DataUpdateFailed, HubInitFailed, SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# This is probably not allowed per ADR-0010, but I need a way to
# set advanced config that shouldn't appear in any UI dialogs.
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                "retry": vol.Schema(
                    {
                        vol.Optional("time"): vol.Coerce(int),
                        vol.Optional("ratio"): vol.Coerce(int),
                        vol.Optional("limit"): vol.Coerce(int),
                    }
                ),
                "modbus": vol.Schema(
                    {
                        vol.Optional("timeout"): vol.Coerce(int),
                        vol.Optional("retries"): vol.Coerce(int),
                        vol.Optional("reconnect_delay"): vol.Coerce(float),
                        vol.Optional("reconnect_delay_max"): vol.Coerce(float),
                    }
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up SolarEdge Modbus Muti advanced YAML config."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = config.get(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarEdge Modbus Muti from a config entry."""

    solaredge_hub = SolarEdgeModbusMultiHub(
        hass, entry.entry_id, entry.data, entry.options
    )

    coordinator = SolarEdgeCoordinator(
        hass,
        solaredge_hub,
        entry.options.get(CONF_SCAN_INTERVAL, ConfDefaultInt.SCAN_INTERVAL),
    )

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
            _LOGGER.error(f"Unable to remove entry: device {device_id} is in use")
            return False

    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating from config version "
        f"{config_entry.version}.{config_entry.minor_version}"
    )

    if config_entry.version > 2:
        return False

    if config_entry.version == 1:
        _LOGGER.debug("Migrating from version 1")

        update_data = {**config_entry.data}
        update_options = {**config_entry.options}

        if CONF_SCAN_INTERVAL in update_data:
            update_options = {
                **update_options,
                CONF_SCAN_INTERVAL: update_data.pop(CONF_SCAN_INTERVAL),
            }

        start_device_id = update_data.pop(ConfName.DEVICE_ID)
        number_of_inverters = update_data.pop(ConfName.NUMBER_INVERTERS)

        inverter_list = []
        for inverter_index in range(number_of_inverters):
            inverter_unit_id = inverter_index + start_device_id
            inverter_list.append(inverter_unit_id)

        update_data = {
            **update_data,
            ConfName.DEVICE_LIST: inverter_list,
        }

        hass.config_entries.async_update_entry(
            config_entry,
            data=update_data,
            options=update_options,
            version=2,
            minor_version=0,
        )

    if config_entry.version == 2 and config_entry.minor_version < 1:
        _LOGGER.debug("Migrating from version 2.0")

        config_entry_data = {**config_entry.data}

        # Use host:port address string as the config entry unique ID.
        # This is technically not a valid HA unique ID, but with modbus
        # we can't know anything like a serial number per IP since a
        # single SE modbus IP could have up to 32 different serial numbers
        # and the "leader" modbus unit id can't be known programmatically.

        old_unique_id = config_entry.unique_id
        new_unique_id = f"{config_entry_data[CONF_HOST]}:{config_entry_data[CONF_PORT]}"

        _LOGGER.warning(
            "Migrating config entry unique ID from %s to %s",
            old_unique_id,
            new_unique_id,
        )

        hass.config_entries.async_update_entry(
            config_entry, unique_id=new_unique_id, version=2, minor_version=1
        )

    _LOGGER.warning(
        "Migrated to config version "
        f"{config_entry.version}.{config_entry.minor_version}"
    )

    return True


class SolarEdgeCoordinator(DataUpdateCoordinator):

    def __init__(
        self, hass: HomeAssistant, hub: SolarEdgeModbusMultiHub, scan_interval: int
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="SolarEdge Coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._hub = hub
        self._yaml_config = hass.data[DOMAIN]["yaml"]

    async def _async_update_data(self) -> bool:
        try:
            while self._hub.has_write:
                _LOGGER.debug(f"Waiting for write {self._hub.has_write}")
                await asyncio.sleep(1)

            return await self._refresh_modbus_data_with_retry(
                ex_type=DataUpdateFailed,
                limit=self._yaml_config.get("retry", {}).get(
                    "limit", RetrySettings.Limit
                ),
                wait_ms=self._yaml_config.get("retry", {}).get(
                    "time", RetrySettings.Time
                ),
                wait_ratio=self._yaml_config.get("retry", {}).get(
                    "ratio", RetrySettings.Ratio
                ),
            )

        except HubInitFailed as e:
            raise UpdateFailed(f"{e}")

        except DataUpdateFailed as e:
            raise UpdateFailed(f"{e}")

    async def _refresh_modbus_data_with_retry(
        self,
        ex_type=Exception,
        limit: int = 0,
        wait_ms: int = 100,
        wait_ratio: int = 2,
    ) -> bool:
        """
        Retry refresh until no exception occurs or retries exhaust
        :param ex_type: retry only if exception is subclass of this type
        :param limit: maximum number of invocation attempts
        :param wait_ms: initial wait time after each attempt in milliseconds.
        :param wait_ratio: increase wait by multiplying by this after each try.
        :return: result of first successful invocation
        :raises: last invocation exception if attempts exhausted
                 or exception is not an instance of ex_type
        Credit: https://gist.github.com/davidohana/c0518ff6a6b95139e905c8a8caef9995
        """
        _LOGGER.debug(f"Retry limit={limit} time={wait_ms} ratio={wait_ratio}")
        attempt = 1
        while True:
            try:
                return await self._hub.async_refresh_modbus_data()
            except Exception as ex:
                if not isinstance(ex, ex_type):
                    raise ex
                if 0 < limit <= attempt:
                    _LOGGER.debug(f"No more data refresh attempts (maximum {limit})")
                    raise ex

                _LOGGER.debug(f"Failed data refresh attempt {attempt}")

                attempt += 1
                _LOGGER.debug(
                    f"Waiting {wait_ms} ms before data refresh attempt {attempt}"
                )
                await asyncio.sleep(wait_ms / 1000)
                wait_ms *= wait_ratio
