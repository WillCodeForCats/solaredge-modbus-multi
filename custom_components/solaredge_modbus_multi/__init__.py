"""The SolarEdge Modbus Multi Integration."""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONFIGURABLE_POLL_GROUPS,
    DOMAIN,
    MODBUS_CONNECTION_REQUIRED_VERSION,
    POLL_MULTIPLIER_MAX,
    POLL_MULTIPLIER_MIN,
    PYMODBUS_REQUIRED_VERSION,
    ConfDefaultInt,
    ConfName,
    RetrySettings,
)
from .exceptions import DataUpdateFailed, HubInitFailed
from .helpers import async_delete_entry_issues, safe_version_tuple

if TYPE_CHECKING:
    from .hub import SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)

# (display name, distribution name, minimum version)
_REQUIRED_LIBRARIES = (
    ("modbus-connection", "modbus_connection", MODBUS_CONNECTION_REQUIRED_VERSION),
    ("pymodbus", "pymodbus", PYMODBUS_REQUIRED_VERSION),
)


def _check_dependency_versions() -> dict[str, str]:
    """Fail setup, before the modbus backend is imported, on a missing or old library.

    HA installs a custom integration's requirements only while they are
    unsatisfied, so another integration pinning the same package can leave an
    older copy in place unnoticed (both production containers ran
    modbus-connection 4.4.0 for weeks that way). Blocking file I/O: run it in
    the executor.
    """
    installed: dict[str, str] = {}

    for display_name, distribution, required in _REQUIRED_LIBRARIES:
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            raise ConfigEntryError(
                f"{display_name} is not installed. Restart Home Assistant so it "
                "installs the integration's requirements; if that does not help, "
                "look for a failed pip install in the log."
            )

        if safe_version_tuple(version) < safe_version_tuple(required):
            raise ConfigEntryError(
                f"{display_name} {version} is installed but at least {required} is "
                "required. Another custom integration is pinning an older version; "
                "remove or update it, then recreate the container."
            )

        installed[display_name] = version

    return installed


@dataclass
class SolarEdgeData:
    """Runtime data for a SolarEdge Modbus Multi config entry."""

    hub: SolarEdgeModbusMultiHub
    coordinator: SolarEdgeCoordinator


type SolarEdgeConfigEntry = ConfigEntry[SolarEdgeData]

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
                        vol.Optional("time"): vol.All(
                            vol.Coerce(int), vol.Range(min=10, max=60000)
                        ),
                        vol.Optional("ratio"): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=10)
                        ),
                        # limit <= 0 would mean "retry forever" to the
                        # coordinator but "fail instantly" to the hub's
                        # timeout counter — forbidden rather than defined.
                        vol.Optional("limit"): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=100)
                        ),
                    }
                ),
                # Per-group poll cadence. Strict on purpose: an unknown group
                # name (or "core", which is always every cycle) fails at
                # startup rather than silently polling everything.
                "poll": vol.Schema(
                    {
                        vol.Optional(f"{group}"): vol.All(
                            vol.Coerce(int),
                            vol.Range(min=POLL_MULTIPLIER_MIN, max=POLL_MULTIPLIER_MAX),
                        )
                        for group in CONFIGURABLE_POLL_GROUPS
                    }
                ),
                "modbus": vol.Schema(
                    {
                        vol.Optional("timeout"): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=60)
                        ),
                        vol.Optional("retries"): vol.All(
                            vol.Coerce(int), vol.Range(min=0, max=10)
                        ),
                        # 0 keeps pymodbus auto-reconnect disabled (the default).
                        vol.Optional("reconnect_delay"): vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=300)
                        ),
                        vol.Optional("reconnect_delay_max"): vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=600)
                        ),
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


async def async_setup_entry(hass: HomeAssistant, entry: SolarEdgeConfigEntry) -> bool:
    """Set up SolarEdge Modbus Muti from a config entry."""

    installed = await hass.async_add_executor_job(_check_dependency_versions)
    hass.data.setdefault(DOMAIN, {})["installed_versions"] = installed

    # Imported only now: hub.py pulls in the modbus backend at import time, and
    # the check above has to run before that happens.
    from .hub import SolarEdgeModbusMultiHub

    solaredge_hub = SolarEdgeModbusMultiHub(
        hass, entry.entry_id, entry.data, entry.options
    )

    coordinator = SolarEdgeCoordinator(
        hass,
        entry,
        solaredge_hub,
        entry.options.get(CONF_SCAN_INTERVAL, ConfDefaultInt.SCAN_INTERVAL),
    )

    entry.runtime_data = SolarEdgeData(hub=solaredge_hub, coordinator=coordinator)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        # The coordinator turns HubInitFailed / DataUpdateFailed into
        # UpdateFailed, which first_refresh surfaces as ConfigEntryNotReady;
        # close the half-open modbus client before HA schedules the retry.
        await solaredge_hub.shutdown()
        raise

    try:
        # Register the inverters before any platform creates entities: meters,
        # batteries and MPPT units link to their inverter by device-registry
        # id (via_device_id), which exists only once the inverter is registered.
        device_registry = dr.async_get(hass)
        for inverter in solaredge_hub.inverters:
            inverter.registry_device_id = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id, **inverter.device_info
            ).id

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # A failed (or cancelled) platform setup must not leak the connected
        # modbus client — the inverter has a single TCP session slot.
        await solaredge_hub.shutdown()
        raise

    # No update listener: the options flow reloads via OptionsFlowWithReload,
    # reconfigure via async_update_reload_and_abort, repairs schedule their
    # own reload. A listener alongside those double-reloads (error in 2026.12).

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolarEdgeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.hub.shutdown()
        async_delete_entry_issues(hass, entry)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: SolarEdgeConfigEntry) -> None:
    """Clean up after a removed config entry.

    An entry removed while in setup-retry (the usual state behind a live
    check_configuration repair) is never unloaded, so its issues must be
    deleted here or they orphan.
    """
    async_delete_entry_issues(hass, entry)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    solaredge_hub = config_entry.runtime_data.hub

    # Every device the hub currently knows, EVSEs included — a live device
    # must not be deletable from the UI (it would only come back on reload).
    known_devices = {
        dev_id[1]
        for device in (
            *solaredge_hub.inverters,
            *solaredge_hub.meters,
            *solaredge_hub.batteries,
            *solaredge_hub.evses,
        )
        for dev_id in device.device_info["identifiers"]
        if dev_id[0] == DOMAIN
    }

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
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        hub: SolarEdgeModbusMultiHub,
        scan_interval: int,
    ):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="SolarEdge Coordinator",
            update_interval=timedelta(seconds=scan_interval),
            # Note: always_update defaults to True, which is required because
            # _async_update_data returns a boolean, not the actual sensor data.
            # Entities access data via self.hub directly, so they need coordinator
            # callbacks to trigger state updates even when return value is unchanged.
        )
        self._hub = hub
        self._yaml_config = hass.data[DOMAIN]["yaml"]

    async def _async_update_data(self) -> bool:
        try:
            # Wait for any pending writes, bounded so a cancelled write task
            # (which would leave has_write set) can't stall polling forever.
            # has_write is only legitimately held for sleep_after_write (<=60s).
            try:
                async with asyncio.timeout(self._hub.sleep_after_write + 5):
                    while self._hub.has_write:
                        await asyncio.sleep(0.1)
            except TimeoutError:
                _LOGGER.warning(
                    "Pending write at address %s did not clear in time; "
                    "clearing it and continuing with data refresh",
                    self._hub.has_write,
                )
                self._hub.has_write = None

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
            raise UpdateFailed(f"{e}") from e

        except DataUpdateFailed as e:
            raise UpdateFailed(f"{e}") from e

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
