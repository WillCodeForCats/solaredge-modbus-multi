"""The SolarEdge Modbus Multi Integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from modbus_connection import ModbusTcpParams
import voluptuous as vol

from .const import (
    DOMAIN,
    MESSAGE_SPACING,
    ConfDefaultInt,
    ConfName,
    ConnectionMode,
    RetrySettings,
)
from .helpers import get_connection_mode
from .hub import DataUpdateFailed, HubInitFailed, SharedUnits, SolarEdgeModbusMultiHub

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
            },
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up SolarEdge Modbus Muti advanced YAML config."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = config.get(DOMAIN, {})

    if "modbus" in hass.data[DOMAIN]["yaml"]:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "deprecated_yaml_modbus",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml_modbus",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "deprecated_yaml_modbus")

    return True


# Earlier versions misnamed the DER State of Charge sensor (SunSpec model 713
# SoC) as State of Energy, with the unique ID suffix "battery_soe"; it is
# migrated to "soc". SolarEdge does not report State of Health or Status in
# model 713, so those sensors of earlier versions are removed.
_LEGACY_DER_SOE_SUFFIX = "battery_soe"
_LEGACY_DER_UNSUPPORTED_SUFFIXES = ("battery_soh", "status")


@callback
def _async_migrate_legacy_der_entities(
    hass: HomeAssistant, solaredge_hub: SolarEdgeModbusMultiHub
) -> None:
    """Keep the DER State of Charge sensor of earlier versions.

    Earlier versions had a device per DER block with unique IDs like
    "<inverter>_DERB1_battery_soe", where "soe" was used instead of "soc".
    Renaming it to the current unique ID keeps its entity ID and history;
    the sensor platform then moves it to the inverter device. The unsupported
    State of Health and Status sensors are removed. Must run before the sensor
    platform is set up.
    """
    entity_registry = er.async_get(hass)
    for inverter in solaredge_hub.inverters:
        for der_id, scan_id in enumerate(inverter.der_storage_scan_ids, 1):
            legacy_prefix = f"{inverter.uid_base}_DERB{scan_id}"

            for suffix in _LEGACY_DER_UNSUPPORTED_SUFFIXES:
                entity_id = entity_registry.async_get_entity_id(
                    Platform.SENSOR, DOMAIN, f"{legacy_prefix}_{suffix}"
                )
                if entity_id is not None:
                    _LOGGER.debug("Removing unsupported DER sensor %s", entity_id)
                    entity_registry.async_remove(entity_id)

            old_unique_id = f"{legacy_prefix}_{_LEGACY_DER_SOE_SUFFIX}"
            new_unique_id = f"{inverter.uid_base}_storage_{der_id}_soc"
            entity_id = entity_registry.async_get_entity_id(
                Platform.SENSOR, DOMAIN, old_unique_id
            )
            if entity_id is None or entity_registry.async_get_entity_id(
                Platform.SENSOR, DOMAIN, new_unique_id
            ):
                continue
            _LOGGER.debug("Migrating DER sensor %s to %s", old_unique_id, new_unique_id)
            entity_registry.async_update_entity(entity_id, new_unique_id=new_unique_id)


@callback
def _async_remove_legacy_der_devices(
    hass: HomeAssistant, entry: ConfigEntry, solaredge_hub: SolarEdgeModbusMultiHub
) -> None:
    """Remove the separate DER battery devices from earlier versions.

    DER battery sensors are now on the inverter device. Only devices for DER
    blocks found in this run are removed, after the sensor platform has moved
    their entities to the inverter device, so a failed scan never deletes an
    entity. Removing a device also removes the entities still registered to it.
    """
    legacy_ids = {
        f"{inverter.uid_base}_DERB{scan_id}"
        for inverter in solaredge_hub.inverters
        for scan_id in inverter.der_storage_scan_ids
    }
    if not legacy_ids:
        return

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if any(
            ident[0] == DOMAIN and ident[1] in legacy_ids
            for ident in device.identifiers
        ):
            _LOGGER.debug("Removing legacy DER battery device %s", device.name)
            device_registry.async_remove_device(device.id)


def _async_get_shared_units(
    hass: HomeAssistant,
    entry: ConfigEntry,
    params: ModbusTcpParams,
    request_timeout: float,
) -> SharedUnits:
    """Get a unit per device ID on the modbus integration's shared connection.

    The connection itself belongs to the modbus integration, which closes it
    behind the last entry holding a unit, so there is nothing for us to close
    on unload.
    """
    units = {}
    try:
        for unit_id in entry.data[ConfName.DEVICE_LIST]:
            unit = async_get_unit(hass, entry, params, unit_id)
            unit.set_message_spacing(MESSAGE_SPACING)
            unit.require_timeout(request_timeout)
            units[unit_id] = unit
    except HomeAssistantError as err:
        # Another integration holds this device over different link settings,
        # which one shared connection cannot honour.
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="link_settings_in_use",
            translation_placeholders={
                "host": entry.data[CONF_HOST],
                "port": str(entry.data[CONF_PORT]),
            },
        ) from err
    return SharedUnits(units)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolarEdge Modbus Muti from a config entry."""

    request_timeout = entry.options.get(
        ConfName.REQUEST_TIMEOUT, ConfDefaultInt.REQUEST_TIMEOUT
    )
    params = ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT])

    mode = get_connection_mode(entry.options)

    # Ensure the modbus connection closes when Home Assistant stops
    async def _async_handle_shutdown(event: Event) -> None:
        await connection.close()

    if mode != ConnectionMode.SHARED:
        # Optional: we can open a direct connection instead of sharing
        # one from the core modbus integration.
        from modbus_connection.tmodbus import ModbusConnection  # noqa: PLC0415

        _LOGGER.warning("Using direct modbus connection")
        connection = ModbusConnection(
            params,
            timeout=request_timeout,
            message_spacing=MESSAGE_SPACING,
        )

        entry.async_on_unload(connection.close)

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_handle_shutdown)
        )
    else:
        connection = _async_get_shared_units(hass, entry, params, request_timeout)

    solaredge_hub = SolarEdgeModbusMultiHub(
        hass, entry.entry_id, entry.data, entry.options, connection
    )

    coordinator = SolarEdgeCoordinator(
        hass,
        solaredge_hub,
        entry.options.get(CONF_SCAN_INTERVAL, ConfDefaultInt.SCAN_INTERVAL),
    )

    # Drop the entry-independent issue ID used by earlier versions.
    ir.async_delete_issue(hass, DOMAIN, "check_configuration")
    ir.async_delete_issue(hass, DOMAIN, "deprecated_keep_modbus_open")

    # Raised again while polling if another shared connection is detected.
    ir.async_delete_issue(
        hass, DOMAIN, f"shared_connection_other_integration_{entry.entry_id}"
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "hub": solaredge_hub,
        "coordinator": coordinator,
    }

    await coordinator.async_config_entry_first_refresh()

    _async_migrate_legacy_der_entities(hass, solaredge_hub)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_remove_legacy_der_devices(hass, entry, solaredge_hub)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


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
        known_devices.extend(inverter_device_ids)

    for meter in solaredge_hub.meters:
        meter_device_ids = {
            dev_id[1]
            for dev_id in meter.device_info["identifiers"]
            if dev_id[0] == DOMAIN
        }
        known_devices.extend(meter_device_ids)

    for battery in solaredge_hub.batteries:
        battery_device_ids = {
            dev_id[1]
            for dev_id in battery.device_info["identifiers"]
            if dev_id[0] == DOMAIN
        }
        known_devices.extend(battery_device_ids)

    this_device_ids = {
        dev_id[1] for dev_id in device_entry.identifiers if dev_id[0] == DOMAIN
    }

    for device_id in this_device_ids:
        if device_id in known_devices:
            _LOGGER.error("Unable to remove entry: device %s is in use", device_id)
            return False

    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating from config version %s.%s",
        config_entry.version,
        config_entry.minor_version,
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

    if config_entry.version == 2 and config_entry.minor_version < 2:
        _LOGGER.debug("Migrating from version 2.1")

        update_options = {**config_entry.options}
        had_keep_modbus_open = update_options.pop("keep_modbus_open", False)

        if had_keep_modbus_open:
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"deprecated_keep_modbus_open_{config_entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="deprecated_keep_modbus_open",
            )

        hass.config_entries.async_update_entry(
            config_entry, options=update_options, version=2, minor_version=2
        )

    if config_entry.version == 2 and config_entry.minor_version < 3:
        _LOGGER.debug("Migrating from version 2.2")

        # config 2.3 added the close_after_polling option, which 2.4 replaced
        # with the connection mode option.
        hass.config_entries.async_update_entry(config_entry, version=2, minor_version=3)

    if config_entry.version == 2 and config_entry.minor_version < 4:
        _LOGGER.debug("Migrating from version 2.3")

        # close_after_polling became part of the connection mode option, which
        # only has it with a direct connection.
        update_options = {**config_entry.options}

        if update_options.pop("close_after_polling", False):
            update_options[ConfName.CONNECTION_MODE] = (
                ConnectionMode.OWN_CLOSE_AFTER_POLLING.value
            )

        hass.config_entries.async_update_entry(
            config_entry, options=update_options, version=2, minor_version=4
        )

    _LOGGER.warning(
        "Migrated to config version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    return True


class SolarEdgeCoordinator(TimestampDataUpdateCoordinator):
    """Solar edge coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: SolarEdgeModbusMultiHub,
        scan_interval: int,
    ):
        """Initialize the solar edge coordinator."""
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
        """Retry refresh until no exception occurs or retries exhaust.

        :param ex_type: retry only if exception is subclass of this type
        :param limit: maximum number of invocation attempts
        :param wait_ms: initial wait time after each attempt in milliseconds.
        :param wait_ratio: increase wait by multiplying by this after each try.
        :return: result of first successful invocation
        :raises: last invocation exception if attempts exhausted
                 or exception is not an instance of ex_type

        Credit: https://gist.github.com/davidohana/c0518ff6a6b95139e905c8a8caef9995
        """
        _LOGGER.debug("Retry limit=%s time=%s ratio=%s", limit, wait_ms, wait_ratio)
        attempt = 1
        while True:
            try:
                return await self._hub.async_refresh_modbus_data()
            except Exception as ex:  # noqa: PERF203
                if not isinstance(ex, ex_type):
                    raise
                if 0 < limit <= attempt:
                    _LOGGER.debug("No more data refresh attempts (maximum %s)", limit)
                    raise

                _LOGGER.debug("Failed data refresh attempt %s", attempt)

                attempt += 1
                _LOGGER.debug(
                    "Waiting %s ms before data refresh attempt %s", wait_ms, attempt
                )
                await asyncio.sleep(wait_ms / 1000)
                wait_ms *= wait_ratio
