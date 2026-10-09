"""The SolarEdge Modbus Multi hub module."""

from __future__ import annotations

import asyncio
import logging

from awesomeversion import AwesomeVersion, AwesomeVersionStrategy
from awesomeversion.exceptions import (
    AwesomeVersionCompareException,
    AwesomeVersionStrategyException,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.entity import DeviceInfo
from modbus_connection.exceptions import (
    IllegalDataAddressError,
    IllegalDataValueError,
    IllegalFunctionError,
    ModbusConnectionError,
    ModbusError,
    ModbusExceptionError,
    ModbusProtocolError,
    ModbusTimeoutError,
)
from modbus_connection.model.sunspec import SunSpecError, scan as suns_scan

from .components import (
    AdvancedPowerControl,
    BatteryData,
    BatteryInfo,
    DERStorageCapacity,
    EvseCommon,
    GlobalDynamicPowerControl,
    InverterCommon,
    InverterData,
    MeterData,
    MeterInfo,
    MmpptCommon,
    MmpptData,
    SiteLimitControl,
    StorageControl,
    component_field_names,
)
from .const import (
    BATTERY_REG_BASE,
    DETECT_EVSE_REGEX,
    DOMAIN,
    METER_REG_BASE,
    MMPPT_UNITS_VERSION,
    STATUS_VENDOR4_VERSION,
    WRITE_SETTLE_CYCLES,
    ConfDefaultFlag,
    ConfDefaultInt,
    ConfDefaultStr,
    ConfName,
    RetrySettings,
    SolarEdgeTimeouts,
    SunSpecNotImpl,
)
from .helpers import float_to_hex

_LOGGER = logging.getLogger(__name__)


class SolarEdgeException(Exception):
    """Base class for other exceptions."""


class HubInitFailed(SolarEdgeException):
    """Raised when an error happens during init."""


class DeviceIsEVSE(SolarEdgeException):
    """Raised when an inverter device matches a EVSE model."""


class DataUpdateFailed(SolarEdgeException):
    """Raised when an update cycle fails."""


class DeviceInvalid(SolarEdgeException):
    """Raised when a device is not usable or invalid."""


async def async_update_with_retry(component) -> None:
    """Call component.async_update(), retrying connection/timeout errors.

    modbus-connection has no built-in per-request retry, unlike pymodbus's
    `retries` option, so this method mimics that behavior.
    """
    for attempt in range(1, RetrySettings.RequestRetries + 1):
        try:
            await component.async_update()

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:  # noqa: PERF203
            _LOGGER.debug(
                "%s.async_update() attempt %s of %s failed: %s",
                type(component).__name__,
                attempt,
                RetrySettings.RequestRetries,
                e,
            )

            if attempt >= RetrySettings.RequestRetries:
                raise

        else:
            return


async def async_write_with_retry(component, field: str, value) -> None:
    """Call component.write(field, value), retrying connection/timeout errors.

    Like async_update_with_retry() but for writes.
    """
    for attempt in range(1, RetrySettings.RequestRetries + 1):
        try:
            await component.write(field, value)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:  # noqa: PERF203
            _LOGGER.debug(
                "%s.write(%r) attempt %s of %s failed: %s",
                type(component).__name__,
                field,
                attempt,
                RetrySettings.RequestRetries,
                e,
            )

            if attempt >= RetrySettings.RequestRetries:
                raise

        else:
            return


async def async_suns_scan_with_retry(connection, base_address: int):
    """Call suns_scan(), retrying connection/timeout errors.

    Like async_update_with_retry() but for the SunSpec model scan.
    """
    for attempt in range(1, RetrySettings.RequestRetries + 1):
        try:
            models = await suns_scan(connection, base_address)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:  # noqa: PERF203
            _LOGGER.debug(
                "suns_scan() attempt %s of %s failed: %s",
                attempt,
                RetrySettings.RequestRetries,
                e,
            )

            if attempt >= RetrySettings.RequestRetries:
                raise

        else:
            return models

    return None


def _parse_se_version(version_str: str) -> AwesomeVersion:
    """Strip zero-padding from SolarEdge firmware version strings."""
    stripped = ".".join(str(int(p)) for p in version_str.split("."))
    return AwesomeVersion(stripped, ensure_strategy=AwesomeVersionStrategy.SIMPLEVER)


def _log_component_fields(prefix: str, component) -> None:
    """Debug-log every field of a just-read component, by name."""
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return

    for name in component_field_names(component):
        value = getattr(component, name)
        if isinstance(value, float):
            display_value = float_to_hex(value)
        else:
            display_value = hex(value) if isinstance(value, int) else value
        _LOGGER.debug("%s: %s %s %s", prefix, name, display_value, type(value))


def _device_anchor(entry_id: str, *parts: str | int) -> str:
    """Build a stable device_registry identifier independent of model/serial.

    Unlike uid_base (model_serial), this never changes when hardware at a given
    Modbus device ID is replaced. It lets us find "whatever device previously
    occupied this Modbus ID" in the device registry so we can detect the swap
    and offer a repair. See SolarEdgeModbusMultiHub._check_inverter_replaced().
    """
    return "_".join([entry_id, *(str(part) for part in parts)])


class SolarEdgeModbusMultiHub:
    """Solar edge modbus multi hub."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, entry_data, entry_options, connection
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._yaml_config = hass.data[DOMAIN]["yaml"]
        self._name = entry_data[CONF_NAME]
        self._host = entry_data[CONF_HOST]
        self._port = entry_data[CONF_PORT]
        self._entry_id = entry_id
        self._inverter_list = entry_data.get(
            ConfName.DEVICE_LIST, [ConfDefaultStr.DEVICE_LIST]
        )
        self._detect_meters = entry_options.get(
            ConfName.DETECT_METERS, bool(ConfDefaultFlag.DETECT_METERS)
        )
        self._detect_batteries = entry_options.get(
            ConfName.DETECT_BATTERIES, bool(ConfDefaultFlag.DETECT_BATTERIES)
        )
        self._detect_extras = entry_options.get(
            ConfName.DETECT_EXTRAS, bool(ConfDefaultFlag.DETECT_EXTRAS)
        )
        self._adv_storage_control = entry_options.get(
            ConfName.ADV_STORAGE_CONTROL, bool(ConfDefaultFlag.ADV_STORAGE_CONTROL)
        )
        self._adv_site_limit_control = entry_options.get(
            ConfName.ADV_SITE_LIMIT_CONTROL,
            bool(ConfDefaultFlag.ADV_SITE_LIMIT_CONTROL),
        )
        self._allow_battery_energy_reset = entry_options.get(
            ConfName.ALLOW_BATTERY_ENERGY_RESET,
            bool(ConfDefaultFlag.ALLOW_BATTERY_ENERGY_RESET),
        )
        self._request_timeout = entry_options.get(
            ConfName.REQUEST_TIMEOUT, ConfDefaultInt.REQUEST_TIMEOUT
        )
        self._sleep_after_write = entry_options.get(
            ConfName.SLEEP_AFTER_WRITE, ConfDefaultInt.SLEEP_AFTER_WRITE
        )
        self._battery_rating_adjust = entry_options.get(
            ConfName.BATTERY_RATING_ADJUST, ConfDefaultInt.BATTERY_RATING_ADJUST
        )
        self._battery_energy_reset_cycles = entry_options.get(
            ConfName.BATTERY_ENERGY_RESET_CYCLES,
            ConfDefaultInt.BATTERY_ENERGY_RESET_CYCLES,
        )
        self._close_after_polling = entry_options.get(
            ConfName.CLOSE_AFTER_POLLING, bool(ConfDefaultFlag.CLOSE_AFTER_POLLING)
        )

        self._id = entry_data[CONF_NAME].lower()
        self.inverters = []
        self.meters = []
        self.batteries = []
        self.der_batteries = []
        self.evses = []
        self.inverter_common = {}
        self.mmppt_common = {}
        self._write_settle_cycles: dict[int, int] = {}

        self._initalized = False
        self._coordinator_timeouts_count = 0
        self._coordinator_timeouts_limit = RetrySettings.CoordinatorTimeouts

        self.connection = connection

        _LOGGER.debug(
            "%s configuration: inverter_list=%s, detect_meters=%s, "
            "detect_batteries=%s, detect_extras=%s, adv_storage_control=%s, "
            "adv_site_limit_control=%s, allow_battery_energy_reset=%s, "
            "request_timeout=%s, sleep_after_write=%s, battery_rating_adjust=%s, "
            "close_after_polling=%s, ",
            DOMAIN,
            self._inverter_list,
            self._detect_meters,
            self._detect_batteries,
            self._detect_extras,
            self._adv_storage_control,
            self._adv_site_limit_control,
            self._allow_battery_energy_reset,
            self._request_timeout,
            self._sleep_after_write,
            self._battery_rating_adjust,
            self._close_after_polling,
        )

    async def _async_init_solaredge(self) -> None:  # noqa: C901
        """Detect devices and load initial modbus data from inverters."""

        if self.option_storage_control:
            _LOGGER.warning(
                "Power Control Options: Storage Control is enabled. "
                "Use at your own risk! "
                "Adjustable parameters in Modbus registers are intended for "
                "long-term storage. Periodic changes may damage the flash memory."
            )

        if self.option_site_limit_control:
            _LOGGER.warning(
                "Power Control Options: Site Limit Control is enabled. "
                "Use at your own risk! "
                "Adjustable parameters in Modbus registers are intended for "
                "long-term storage. Periodic changes may damage the flash memory."
            )

        for inverter_unit_id in self._inverter_list:
            try:
                _LOGGER.debug(
                    "Looking for inverter at %s ID %s", self.hub_host, inverter_unit_id
                )
                new_inverter = SolarEdgeInverter(inverter_unit_id, self)
                await new_inverter.init_device()
                self.inverters.append(new_inverter)

                ir.async_delete_issue(
                    self._hass,
                    DOMAIN,
                    self._setup_inverter_id_failed_issue(inverter_unit_id),
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ) as e:
                raise HubInitFailed(f"{e}") from e

            except DeviceInvalid as e:
                # Inverters are mandatory, but if the Device ID is invalid or not responding
                # skip it and warn the user instead of failing the entire hub setup
                _LOGGER.error(
                    "Inverter at %s ID %s: %s", self.hub_host, inverter_unit_id, e
                )
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    self._setup_inverter_id_failed_issue(inverter_unit_id),
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="setup_inverter_id_failed",
                    translation_placeholders={
                        "device_id": str(inverter_unit_id),
                        "host": self.hub_host,
                    },
                    data={"entry_id": self._entry_id},
                )
                continue

            except DeviceIsEVSE as e:
                _LOGGER.debug(
                    "Device model matches EVSE at %s ID %s: %s",
                    self.hub_host,
                    inverter_unit_id,
                    e,
                )
                new_evse = SolarEdgeEVSE(inverter_unit_id, self)
                await new_evse.init_device()
                self.evses.append(new_evse)

                try:
                    _LOGGER.debug(
                        "Scanning SunS models at %s ID %s",
                        self.hub_host,
                        inverter_unit_id,
                    )
                    new_evse.sunspec_models = await async_suns_scan_with_retry(
                        self.connection.for_unit(inverter_unit_id), 40000
                    )

                    for model in new_evse.sunspec_models.chain:
                        _LOGGER.debug(
                            "E%s: found SunS model %s (length %s)",
                            inverter_unit_id,
                            model.model_id,
                            model.length,
                        )

                except (ModbusError, SunSpecError) as e:
                    _LOGGER.debug(
                        "E%s: SunS model scan failed: %s", inverter_unit_id, e
                    )

                # Skip meter and battery detection if DeviceIsEVSE
                new_evse.evse_common.restrict_fields(["C_Version"])
                continue

            try:
                _LOGGER.debug(
                    "Scanning SunS models at %s ID %s", self.hub_host, inverter_unit_id
                )
                suns_models = await async_suns_scan_with_retry(
                    self.connection.for_unit(inverter_unit_id), 40000
                )
                new_inverter.sunspec_models = suns_models

                der_storage_models = suns_models.get(713, []) if suns_models else []

                for model in suns_models.chain:
                    _LOGGER.debug(
                        "I%s: found SunS model %s (length %s)",
                        inverter_unit_id,
                        model.model_id,
                        model.length,
                    )

            except (ModbusError, SunSpecError) as e:
                _LOGGER.debug("I%s: SunS model scan failed: %s", inverter_unit_id, e)
                der_storage_models = []

            if self._detect_meters:
                for meter_id in METER_REG_BASE:
                    try:
                        _LOGGER.debug(
                            "Looking for meter I%sM%s", inverter_unit_id, meter_id
                        )
                        new_meter = SolarEdgeMeter(inverter_unit_id, meter_id, self)
                        await new_meter.init_device()

                        for meter in self.meters:
                            # Allow duplicate serial number on meters PR#412
                            if new_meter.serial == meter.serial:
                                _LOGGER.warning(
                                    "Duplicate serial %s on I%sM%s",
                                    new_meter.serial,
                                    inverter_unit_id,
                                    meter_id,
                                )

                        new_meter.via_device = new_inverter.uid_base
                        self.meters.append(new_meter)
                        _LOGGER.debug("Found I%sM%s", inverter_unit_id, meter_id)

                    except (  # noqa: PERF203
                        ModbusConnectionError,
                        ModbusProtocolError,
                        ModbusTimeoutError,
                    ) as e:
                        raise HubInitFailed(f"{e}") from e

                    except DeviceInvalid as e:
                        _LOGGER.debug("I%sM%s: %s", inverter_unit_id, meter_id, e)

            if self._detect_batteries:
                # SolarEdge proprietary battery block for up to three batteries.
                for battery_id in BATTERY_REG_BASE:
                    try:
                        _LOGGER.debug(
                            "Looking for battery I%sB%s", inverter_unit_id, battery_id
                        )
                        new_battery = SolarEdgeBattery(
                            inverter_unit_id, battery_id, self
                        )
                        await new_battery.init_device()

                        for battery in self.batteries:
                            if new_battery.serial == battery.serial:
                                _LOGGER.warning(
                                    "Duplicate serial %s on I%sB%s",
                                    new_battery.serial,
                                    inverter_unit_id,
                                    battery_id,
                                )
                                raise DeviceInvalid(  # noqa: TRY301
                                    f"Duplicate B{battery_id} serial "
                                    f"{new_battery.serial}"
                                )

                        new_battery.via_device = new_inverter.uid_base
                        self.batteries.append(new_battery)
                        _LOGGER.debug("Found I%sB%s", inverter_unit_id, battery_id)

                    except (  # noqa: PERF203
                        ModbusConnectionError,
                        ModbusProtocolError,
                        ModbusTimeoutError,
                    ) as e:
                        raise HubInitFailed(f"{e}") from e

                    except DeviceInvalid as e:
                        _LOGGER.debug("I%sB%s: %s", inverter_unit_id, battery_id, e)

                # DER Storage Capacity (SunSpec model 713)
                for der_id, der_storage_model in enumerate(der_storage_models, 1):
                    try:
                        _LOGGER.debug(
                            "Looking for DER Storage Capacity I%sDERB%s",
                            inverter_unit_id,
                            der_id,
                        )
                        new_der_battery = SolarEdgeDERBattery(
                            inverter_unit_id, der_id, self, der_storage_model
                        )
                        await new_der_battery.init_device()

                        new_der_battery.via_device = new_inverter.uid_base
                        self.der_batteries.append(new_der_battery)
                        _LOGGER.debug(
                            "Found I%s DER Storage Capacity battery %s",
                            inverter_unit_id,
                            der_id,
                        )

                    except (  # noqa: PERF203
                        ModbusConnectionError,
                        ModbusProtocolError,
                        ModbusTimeoutError,
                    ) as e:
                        raise HubInitFailed(f"{e}") from e

                    except DeviceInvalid as e:
                        _LOGGER.debug("I%sDERB%s: %s", inverter_unit_id, der_id, e)

            new_inverter.inverter_common.restrict_fields(["C_Version"])

        if not self.inverters:
            # fail the hub setup if there are no inverters
            raise HubInitFailed(
                f"No usable inverters found at {self.hub_host} for configured "
                "Device ID(s). Check the repair issue(s) for details."
            )

        try:
            for inverter in self.inverters:
                await inverter.read_modbus_data()
            for meter in self.meters:
                await meter.read_modbus_data()
            for battery in self.batteries:
                await battery.read_modbus_data()
            for der_battery in self.der_batteries:
                await der_battery.read_modbus_data()
            for evse in self.evses:
                await evse.read_modbus_data()

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise HubInitFailed(f"Read error: {e}") from e

        except DeviceInvalid as e:
            raise HubInitFailed(f"Invalid device: {e}") from e

        except TimeoutError as e:
            raise HubInitFailed(f"Timeout error: {e}") from e

        self.initalized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        if not self.initalized:
            try:
                async with asyncio.timeout(self.coordinator_timeout):
                    await self._async_init_solaredge()

            except TimeoutError as err:
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    "check_configuration",
                    is_fixable=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="check_configuration",
                    data={"entry_id": self._entry_id},
                )
                raise HubInitFailed(
                    f"Coordinator setup timed out after {self.coordinator_timeout} seconds."
                ) from err

            ir.async_delete_issue(self._hass, DOMAIN, "check_configuration")

            return True

        try:
            async with asyncio.timeout(self.coordinator_timeout):
                for inverter in self.inverters:
                    await inverter.read_modbus_data()
                for meter in self.meters:
                    await meter.read_modbus_data()
                for battery in self.batteries:
                    await battery.read_modbus_data()
                for der_battery in self.der_batteries:
                    await der_battery.read_modbus_data()
                for evse in self.evses:
                    await evse.read_modbus_data()

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            await self.connection.disconnect()
            raise DataUpdateFailed(f"Update failed: {e}") from e

        except DeviceInvalid as e:
            await self.connection.disconnect()
            raise DataUpdateFailed(f"Invalid device: {e}") from e

        except TimeoutError as e:
            await self.connection.disconnect()

            self._coordinator_timeouts_count += 1

            _LOGGER.debug(
                "Coordinator timeout %s limit %s",
                self._coordinator_timeouts_count,
                self._coordinator_timeouts_limit,
            )

            if self._coordinator_timeouts_count >= self._coordinator_timeouts_limit:
                _LOGGER.warning(
                    "Coordinator has timed out %s times in a row.",
                    self._coordinator_timeouts_limit,
                )
                self._coordinator_timeouts_count = 0

            raise DataUpdateFailed(f"Timeout error: {e}") from e

        if self._coordinator_timeouts_count > 0:
            _LOGGER.debug(
                "Coordinator timeout count %s limit %s",
                self._coordinator_timeouts_count,
                self._coordinator_timeouts_limit,
            )
            self._coordinator_timeouts_count = 0

        if self.close_after_polling:
            await self.connection.disconnect()

        return True

    async def component_update(self, unit: int, component) -> None:
        """Update a SolarEdge modbus Component and track write settle cycles.

        Reads always happen inside the coordinator refresh loop.

        Future: if modbus-connection provides a way to get the unit id from the component,
        do that instead of passing the unit separately. We need it to track settle cycles.
        """

        await async_update_with_retry(component)

        cycles_remaining = self._write_settle_cycles.get(unit)
        if cycles_remaining is None:
            return

        if cycles_remaining <= 1:
            _LOGGER.debug("Clearing unit %s request spacing.", unit)
            self.connection.for_unit(unit).set_message_spacing(0)
            del self._write_settle_cycles[unit]
        else:
            _LOGGER.debug(
                "Unit %s has %s refreshes until clearing.", unit, cycles_remaining - 1
            )
            self._write_settle_cycles[unit] = cycles_remaining - 1

    async def component_write(self, unit: int, component, field: str, value) -> None:
        """Write a SolarEdge modbus Component and set optional spacing.

        Writes are outside the refresh loop. SolarEdge inverters may not respond
        (timeout) on errors instead of sending a modbus exception response.

        Future: if modbus-connection provides a way to get the unit id from the component,
        do that instead of passing the unit separately. We need it for sleep after write.
        """

        if self.sleep_after_write > 0:
            _LOGGER.debug(
                "Spacing requests to unit %s for %s seconds after write to field %s.",
                unit,
                self.sleep_after_write,
                field,
            )
            self.connection.for_unit(unit).set_message_spacing(self.sleep_after_write)
            self._write_settle_cycles[unit] = WRITE_SETTLE_CYCLES

        try:
            await async_write_with_retry(component, field, value)

        except IllegalFunctionError as e:
            _LOGGER.debug("Unit %s Write IllegalFunction: %s", unit, e)
            raise HomeAssistantError(
                f"Function not supported by device at ID {unit}."
            ) from e

        except IllegalDataAddressError as e:
            _LOGGER.debug("Unit %s Write IllegalAddress: %s", unit, e)
            raise HomeAssistantError(
                f"Address not supported at device at ID {unit}."
            ) from e

        except IllegalDataValueError as e:
            _LOGGER.debug("Unit %s Write IllegalValue: %s", unit, e)
            raise HomeAssistantError(f"Value invalid for device at ID {unit}.") from e

        except ModbusExceptionError as e:
            _LOGGER.debug("Unit %s Write rejected: %s", unit, e)
            raise HomeAssistantError(
                f"Write rejected by device at ID {unit}: {e}"
            ) from e

        except ModbusTimeoutError as e:
            _LOGGER.error("Write failed: No response from inverter ID %s.", unit)
            raise HomeAssistantError(f"No response from inverter ID {unit}.") from e

        except (ModbusConnectionError, ModbusProtocolError) as e:
            _LOGGER.error("Connection failed: %s", e)
            raise HomeAssistantError(f"Connection to inverter ID {unit} failed.") from e

        _LOGGER.debug("Finished with write %s.", field)

    def _setup_inverter_id_failed_issue(self, unit_id: int) -> str:
        return f"setup_inverter_id_failed_{self._entry_id}_{unit_id}"

    def _device_replaced_issue(self, unit_id: int) -> str:
        return f"device_replaced_{self._entry_id}_{unit_id}"

    def _check_inverter_replaced(self, inverter: SolarEdgeInverter) -> None:
        """Detect a different inverter now answering at this Modbus device ID.

        Compares against the device registry, keyed by a stable identifier
        independent of model/serial (see _device_anchor()), so a hardware
        swap at the same Modbus ID is detected even though uid_base -- and
        therefore every entity unique_id under it -- changed. Raises a
        fixable repair issue offering to migrate the old entities/history
        onto the replacement, or ignore it.
        """
        anchor = _device_anchor(self._entry_id, "inverter", inverter.inverter_unit_id)
        device_registry = dr.async_get(self._hass)
        existing = device_registry.async_get_device(identifiers={(DOMAIN, anchor)})

        if existing is None:
            # Never seen before at this Modbus ID -- nothing to compare against.
            return

        issue_id = self._device_replaced_issue(inverter.inverter_unit_id)

        if (
            existing.model == inverter.model
            and existing.serial_number == inverter.serial
        ):
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return

        old_uid_base = next(
            (
                identifier[1]
                for identifier in existing.identifiers
                if identifier[0] == DOMAIN and identifier[1] != anchor
            ),
            None,
        )
        if old_uid_base is None:
            # No prior uid_base recorded to compare/migrate from; treat as new.
            return

        _LOGGER.warning(
            "Inverter at %s ID %s appears to have been replaced: "
            "was %s (%s), now %s (%s).",
            self.hub_host,
            inverter.inverter_unit_id,
            existing.model,
            existing.serial_number,
            inverter.model,
            inverter.serial,
        )

        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="device_replaced",
            translation_placeholders={
                "device_id": str(inverter.inverter_unit_id),
                "host": self.hub_host,
                "old_model": existing.model or "unknown",
                "old_serial": existing.serial_number or "unknown",
                "new_model": inverter.model,
                "new_serial": inverter.serial,
            },
            data={
                "entry_id": self._entry_id,
                "device_id": inverter.inverter_unit_id,
                "old_uid_base": old_uid_base,
                "new_uid_base": inverter.uid_base,
                "old_model": existing.model or "unknown",
                "old_serial": existing.serial_number or "unknown",
                "new_model": inverter.model,
                "new_serial": inverter.serial,
            },
        )

    @property
    def initalized(self):
        """Return the initalized."""
        return self._initalized

    @initalized.setter
    def initalized(self, value: bool) -> None:
        if value is True:
            self._initalized = True
        else:
            self._initalized = False

    @property
    def name(self):
        """Return the name of this hub."""
        return self._name

    @property
    def hub_id(self) -> str:
        """Return the ID of this hub."""
        return self._id

    @property
    def hass(self) -> HomeAssistant:
        """Return the Home Assistant instance."""
        return self._hass

    @property
    def entry_id(self) -> str:
        """Return the config entry ID."""
        return self._entry_id

    @property
    def hub_host(self) -> str:
        """Return the modbus client host."""
        return self._host

    @property
    def hub_port(self) -> int:
        """Return the modbus client port."""
        return self._port

    @property
    def option_storage_control(self) -> bool:
        """Return the option storage control."""
        return self._adv_storage_control

    @property
    def option_site_limit_control(self) -> bool:
        """Return the option site limit control."""
        return self._adv_site_limit_control

    @property
    def option_detect_extras(self) -> bool:
        """Return the option detect extras."""
        return self._detect_extras

    @property
    def allow_battery_energy_reset(self) -> bool:
        """Return the allow battery energy reset."""
        return self._allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        """Return the battery rating adjust."""
        return (self._battery_rating_adjust + 100) / 100

    @property
    def battery_energy_reset_cycles(self) -> int:
        """Return the battery energy reset cycles."""
        return self._battery_energy_reset_cycles

    @property
    def close_after_polling(self) -> bool:
        """Return the close after polling."""
        return self._close_after_polling

    @property
    def number_of_meters(self) -> int:
        """Return the number of meters."""
        return len(self.meters)

    @property
    def number_of_batteries(self) -> int:
        """Return the number of batteries."""
        return len(self.batteries)

    @property
    def number_of_inverters(self) -> int:
        """Return the number of inverters."""
        return len(self._inverter_list)

    @property
    def request_timeout(self) -> int:
        """Return the request timeout."""
        return self._request_timeout

    @property
    def sleep_after_write(self) -> int:
        """Return the sleep after write."""
        return self._sleep_after_write

    @property
    def coordinator_timeout(self) -> int:
        """Return the coordinator timeout."""
        if not self.initalized:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Init * self.number_of_inverters
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 3  # max 3 per inverter
            this_timeout += (SolarEdgeTimeouts.Battery * 2) * 3  # max 3 per inverter
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters
            # SunS model-chain scan runs unconditionally, once per inverter at setup
            this_timeout += (
                SolarEdgeTimeouts.Read
                * RetrySettings.RequestRetries
                * self.number_of_inverters
            )

        else:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_meters
            this_timeout += SolarEdgeTimeouts.Battery * self.number_of_batteries
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters

        this_timeout = this_timeout / 1000

        # The per-step timeouts were based on the default request_timeout;
        # scale the coordinator timeout if the user changes the value
        this_timeout *= self.request_timeout / ConfDefaultInt.REQUEST_TIMEOUT

        # Add the sleep_after_write value to the coordinator timeout
        this_timeout += self.sleep_after_write * WRITE_SETTLE_CYCLES

        _LOGGER.debug("coordinator timeout is %s", this_timeout)
        return this_timeout


class SolarEdgeInverter:
    """Defines a SolarEdge inverter."""

    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        """Initialize the solar edge inverter."""
        self.inverter_unit_id = device_id
        self.hub = hub
        self.mmppt_units = []
        self.has_parent = False
        self.has_battery = None
        self.sunspec_models = None
        self.global_power_control = None
        self.advanced_power_control = None
        self.site_limit_control = None
        self.storage_control = None
        self._gpc_timeouts_count = 0
        self._apc_timeouts_count = 0
        self._use_status_vendor4 = False
        self._use_mmppt_units = False
        self.write_count = 0
        self.write_count_listeners = set()

        self.inverter_common = InverterCommon(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )
        self.inverter_data = InverterData(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )
        self.mmppt_common = MmpptCommon(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )
        self.mmppt_data = MmpptData(self.hub.connection.for_unit(self.inverter_unit_id))
        self.global_power_control_data = GlobalDynamicPowerControl(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )
        self.advanced_power_control_data = AdvancedPowerControl(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )
        self.site_limit_control_data = SiteLimitControl(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )
        self.storage_control_data = StorageControl(
            self.hub.connection.for_unit(self.inverter_unit_id)
        )

    def _feature_timeout_issue_id(self, feature: str) -> str:
        return f"detect_timeout_{feature}_{self.hub.entry_id}_{self.inverter_unit_id}"

    async def init_device(self) -> None:
        """Set up data about the device from modbus."""

        try:
            _LOGGER.debug(
                "Reading component InverterCommon(for_unit(%s))", self.inverter_unit_id
            )
            await self.hub.component_update(self.inverter_unit_id, self.inverter_common)

            _log_component_fields(f"I{self.inverter_unit_id}", self.inverter_common)

            self.hub.inverter_common[self.inverter_unit_id] = self.inverter_common

        except (ModbusConnectionError, ModbusProtocolError) as e:
            raise DeviceInvalid(
                f"Error reading inverter ID {self.inverter_unit_id} at InverterCommon: {e}"
            ) from e

        except ModbusTimeoutError as err:
            raise DeviceInvalid(
                f"No response from Device ID {self.inverter_unit_id}"
            ) from err

        except ModbusExceptionError as err:
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            ) from err

        if DETECT_EVSE_REGEX.match(self.inverter_common.C_Model):
            raise DeviceIsEVSE(f"Model {self.inverter_common.C_Model}")

        if (
            self.inverter_common.C_SunSpec_ID == SunSpecNotImpl.UINT32
            or self.inverter_common.C_SunSpec_DID == SunSpecNotImpl.UINT16
            or self.inverter_common.C_SunSpec_ID != 0x53756E53
            or self.inverter_common.C_SunSpec_DID != 0x0001
            or self.inverter_common.C_SunSpec_Length != 65
        ):
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            )

        self.manufacturer = self.inverter_common.C_Manufacturer
        self.model = self.inverter_common.C_Model
        self.option = self.inverter_common.C_Option
        self.serial = self.inverter_common.C_SerialNumber
        self.device_address = self.inverter_common.C_Device_address
        self.name = f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id}"
        self.uid_base = f"{self.model}_{self.serial}"

        self.hub._check_inverter_replaced(self)

        try:
            this_ver = _parse_se_version(self.inverter_common.C_Version)
            self._use_status_vendor4 = this_ver >= AwesomeVersion(
                STATUS_VENDOR4_VERSION,
                ensure_strategy=AwesomeVersionStrategy.SIMPLEVER,
            )
            self._use_mmppt_units = this_ver >= AwesomeVersion(
                MMPPT_UNITS_VERSION,
                ensure_strategy=AwesomeVersionStrategy.SIMPLEVER,
            )
        except (
            AwesomeVersionCompareException,
            AwesomeVersionStrategyException,
            ValueError,
        ) as e:
            _LOGGER.warning(
                "Could not parse inverter version %r: %s",
                self.inverter_common.C_Version,
                e,
            )
            self._use_status_vendor4 = False
            self._use_mmppt_units = False

        self.inverter_data.restrict_status_vendor4(self._use_status_vendor4)

        is_multi_mppt = False

        if self.use_mmppt_units:
            try:
                _LOGGER.debug(
                    "Reading component MmpptCommon(for_unit(%s))", self.inverter_unit_id
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.mmppt_common
                )

                _log_component_fields(
                    f"I{self.inverter_unit_id} MMPPT", self.mmppt_common
                )

                if (
                    SunSpecNotImpl.UINT16
                    in (self.mmppt_common.mmppt_DID, self.mmppt_common.mmppt_Units)
                    or self.mmppt_common.mmppt_DID != 160
                    or self.mmppt_common.mmppt_Units not in [2, 3]
                ):
                    _LOGGER.debug("I%s is NOT Multiple MPPT", self.inverter_unit_id)

                else:
                    _LOGGER.debug("I%s is Multiple MPPT", self.inverter_unit_id)
                    is_multi_mppt = True

            except ModbusConnectionError as e:
                raise ModbusConnectionError(
                    f"Connection error reading inverter ID {self.inverter_unit_id} at MmpptCommon: {e}"
                ) from e

            except ModbusProtocolError as e:
                raise ModbusProtocolError(
                    f"Protocol error reading inverter ID {self.inverter_unit_id} at MmpptCommon: {e}"
                ) from e

            except ModbusTimeoutError as e:
                raise ModbusTimeoutError(
                    f"Timeout error reading inverter ID {self.inverter_unit_id} at MmpptCommon: {e}"
                ) from e

            except ModbusExceptionError:
                _LOGGER.debug("I%s is NOT Multiple MPPT", self.inverter_unit_id)
        else:
            _LOGGER.debug(
                "I%s is NOT Multiple MPPT (firmware does not support MMPPT units)",
                self.inverter_unit_id,
            )

        self.hub.mmppt_common[self.inverter_unit_id] = (
            self.mmppt_common if is_multi_mppt else None
        )

        if is_multi_mppt:
            for unit_index in range(self.mmppt_common.mmppt_Units):
                self.mmppt_units.append(SolarEdgeMMPPTUnit(self, self.hub, unit_index))
                _LOGGER.debug("I%s MMPPT Unit %s", self.inverter_unit_id, unit_index)

    async def read_modbus_data(self) -> None:  # noqa: C901
        """Read and update dynamic modbus registers."""

        try:
            _LOGGER.debug(
                "Reading component InverterCommon(for_unit(%s))", self.inverter_unit_id
            )
            await self.hub.component_update(self.inverter_unit_id, self.inverter_common)

            _LOGGER.debug(
                "Reading component InverterData(for_unit(%s))", self.inverter_unit_id
            )
            await self.hub.component_update(self.inverter_unit_id, self.inverter_data)

            _log_component_fields(f"I{self.inverter_unit_id}", self.inverter_data)

            if (
                self.inverter_data.C_SunSpec_DID == SunSpecNotImpl.UINT16
                or self.inverter_data.C_SunSpec_DID not in [101, 102, 103]
                or self.inverter_data.C_SunSpec_Length != 50
            ):
                raise DeviceInvalid(f"Inverter {self.inverter_unit_id} not usable.")

        except ModbusConnectionError as e:
            raise ModbusConnectionError(
                f"Connection error reading inverter ID {self.inverter_unit_id} at InverterData: {e}"
            ) from e

        except ModbusProtocolError as e:
            raise ModbusProtocolError(
                f"Protocol error reading inverter ID {self.inverter_unit_id} at InverterData: {e}"
            ) from e

        except ModbusTimeoutError as e:
            raise ModbusTimeoutError(
                f"Timeout error reading inverter ID {self.inverter_unit_id} at InverterData: {e}"
            ) from e

        """ Multiple MPPT Extension """
        if (
            self.use_mmppt_units
            and self.hub.mmppt_common[self.inverter_unit_id] is not None
        ):
            try:
                _LOGGER.debug(
                    "Reading component MmpptData(for_unit(%s))", self.inverter_unit_id
                )
                await self.hub.component_update(self.inverter_unit_id, self.mmppt_data)

                _log_component_fields(f"I{self.inverter_unit_id}", self.mmppt_data)

                for unit_index, mmppt_unit_data in enumerate(self.mmppt_data.units):
                    _log_component_fields(
                        f"I{self.inverter_unit_id} MMPPT{unit_index}", mmppt_unit_data
                    )

            except ModbusConnectionError as e:
                raise ModbusConnectionError(
                    f"Connection error reading inverter ID {self.inverter_unit_id} at MmpptData: {e}"
                ) from e

            except ModbusProtocolError as e:
                raise ModbusProtocolError(
                    f"Protocol error reading inverter ID {self.inverter_unit_id} at MmpptData: {e}"
                ) from e

            except ModbusTimeoutError as e:
                raise ModbusTimeoutError(
                    f"Timeout error reading inverter ID {self.inverter_unit_id} at MmpptData: {e}"
                ) from e

        """ Global Dynamic Power Control and Status """
        if self.hub.option_detect_extras and self.global_power_control is not False:
            try:
                _LOGGER.debug(
                    "Reading component GlobalDynamicPowerControl(for_unit(%s))",
                    self.inverter_unit_id,
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.global_power_control_data
                )
                self.global_power_control = True
                self._gpc_timeouts_count = 0

                _log_component_fields(
                    f"I{self.inverter_unit_id}", self.global_power_control_data
                )

                ir.async_delete_issue(
                    self.hub.hass, DOMAIN, self._feature_timeout_issue_id("gpc")
                )

            except (IllegalDataAddressError, IllegalFunctionError):
                self.global_power_control = False
                self._gpc_timeouts_count = 0
                _LOGGER.debug(
                    "I%s: global power control NOT available", self.inverter_unit_id
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
                ModbusExceptionError,
            ):
                # Anything other than a definitive rejection above is treated
                self._gpc_timeouts_count += 1
                give_up = self._gpc_timeouts_count >= RetrySettings.FeatureProbeTimeouts

                if give_up:
                    self.global_power_control = False
                    self._gpc_timeouts_count = 0
                    ir.async_create_issue(
                        self.hub.hass,
                        DOMAIN,
                        self._feature_timeout_issue_id("gpc"),
                        is_fixable=True,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="detect_timeout_gpc",
                        translation_placeholders={
                            "device_id": str(self.inverter_unit_id),
                            "host": self.hub.hub_host,
                        },
                        data={
                            "entry_id": self.hub.entry_id,
                            "inverter_unit_id": self.inverter_unit_id,
                        },
                    )
                    _LOGGER.debug(
                        "I%s: The inverter did not respond while reading data for "
                        "Global Dynamic Power Controls. These entities will be "
                        "unavailable.",
                        self.inverter_unit_id,
                    )
                else:
                    _LOGGER.debug(
                        "I%s: global power control read failed (%s of %s times) before "
                        "disabling.",
                        self.inverter_unit_id,
                        self._gpc_timeouts_count,
                        RetrySettings.FeatureProbeTimeouts,
                    )

        """ Advanced Power Control: Power Control Block """
        if self.hub.option_detect_extras and self.advanced_power_control is not False:
            try:
                _LOGGER.debug(
                    "Reading component AdvancedPowerControl(for_unit(%s))",
                    self.inverter_unit_id,
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.advanced_power_control_data
                )
                self.advanced_power_control = True
                self._apc_timeouts_count = 0

                _log_component_fields(
                    f"I{self.inverter_unit_id}", self.advanced_power_control_data
                )

                ir.async_delete_issue(
                    self.hub.hass, DOMAIN, self._feature_timeout_issue_id("apc")
                )

            except (IllegalDataAddressError, IllegalFunctionError):
                self.advanced_power_control = False
                self._apc_timeouts_count = 0
                _LOGGER.debug(
                    "I%s: advanced power control NOT available", self.inverter_unit_id
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
                ModbusExceptionError,
            ):
                self._apc_timeouts_count += 1
                give_up = self._apc_timeouts_count >= RetrySettings.FeatureProbeTimeouts

                if give_up:
                    self.advanced_power_control = False
                    self._apc_timeouts_count = 0
                    ir.async_create_issue(
                        self.hub.hass,
                        DOMAIN,
                        self._feature_timeout_issue_id("apc"),
                        is_fixable=True,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="detect_timeout_apc",
                        translation_placeholders={
                            "device_id": str(self.inverter_unit_id),
                            "host": self.hub.hub_host,
                        },
                        data={
                            "entry_id": self.hub.entry_id,
                            "inverter_unit_id": self.inverter_unit_id,
                        },
                    )
                    _LOGGER.debug(
                        "I%s: The inverter did not respond while reading data for "
                        "Advanced Power Controls. These entities will be unavailable.",
                        self.inverter_unit_id,
                    )
                else:
                    _LOGGER.debug(
                        "I%s: advanced power control read failed (%s of %s times) "
                        "before disabling.",
                        self.inverter_unit_id,
                        self._apc_timeouts_count,
                        RetrySettings.FeatureProbeTimeouts,
                    )

        """ Power Control Options: Site Limit Control """
        if self.hub.option_site_limit_control and self.site_limit_control is not False:
            try:
                _LOGGER.debug(
                    "Reading component SiteLimitControl(for_unit(%s))",
                    self.inverter_unit_id,
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.site_limit_control_data
                )
                self.site_limit_control = True

                _log_component_fields(
                    f"I{self.inverter_unit_id}", self.site_limit_control_data
                )

            except ModbusExceptionError:
                # Before v4.0.0 we were reading Ext_Prod_Max in its own detection block.
                # revisit with own block or exclude Ext_Prod_Max and retry
                self.site_limit_control = False
                _LOGGER.debug(
                    "I%s: site limit control NOT available", self.inverter_unit_id
                )

            except ModbusConnectionError as e:
                raise ModbusConnectionError(
                    f"Connection error reading inverter ID {self.inverter_unit_id} "
                    f"at SiteLimitControl: {e}"
                ) from e

            except ModbusProtocolError as e:
                raise ModbusProtocolError(
                    f"Protocol error reading inverter ID {self.inverter_unit_id} "
                    f"at SiteLimitControl: {e}"
                ) from e

            except ModbusTimeoutError as e:
                raise ModbusTimeoutError(
                    f"Timeout error reading inverter ID {self.inverter_unit_id} "
                    f"at SiteLimitControl: {e}"
                ) from e

        """ Power Control Options: Storage Control """
        if self.hub.option_storage_control and self.storage_control is not False:
            if self.has_battery is None:
                self.has_battery = False
                for battery in self.hub.batteries:
                    if self.inverter_unit_id == battery.inverter_unit_id:
                        self.has_battery = True

            try:
                _LOGGER.debug(
                    "Reading component StorageControl(for_unit(%s))",
                    self.inverter_unit_id,
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.storage_control_data
                )
                self.storage_control = True

                _log_component_fields(
                    f"I{self.inverter_unit_id}", self.storage_control_data
                )

            except ModbusExceptionError:
                self.storage_control = False
                _LOGGER.debug(
                    "I%s: storage control NOT available", self.inverter_unit_id
                )

            except ModbusConnectionError as e:
                raise ModbusConnectionError(
                    f"Connection error reading inverter ID {self.inverter_unit_id} "
                    f"at StorageControl: {e}"
                ) from e

            except ModbusProtocolError as e:
                raise ModbusProtocolError(
                    f"Protocol error reading inverter ID {self.inverter_unit_id} "
                    f"at StorageControl: {e}"
                ) from e

            except ModbusTimeoutError as e:
                raise ModbusTimeoutError(
                    f"Timeout error reading inverter ID {self.inverter_unit_id} "
                    f"at StorageControl: {e}"
                ) from e

    async def write(
        self, component, field: str, value, count_write: bool = True
    ) -> None:
        """Write a Component field.

        count_write=False is for dynamic setpoints that don't count against
        flash wear the write count sensor is meant to track.
        """
        await self.hub.component_write(self.inverter_unit_id, component, field, value)

        if not count_write:
            return

        self.write_count += 1
        for listener in list(self.write_count_listeners):
            listener()

    @property
    def fw_version(self) -> str | None:
        """Return the fw version."""
        return getattr(self.inverter_common, "C_Version", None)

    @property
    def anchor(self) -> str:
        """Stable identifier for this Modbus device ID, independent of uid_base.

        See _device_anchor() and SolarEdgeModbusMultiHub._check_inverter_replaced().
        """
        return _device_anchor(self.hub._entry_id, "inverter", self.inverter_unit_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base), (DOMAIN, self.anchor)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial,
            sw_version=self.fw_version,
            hw_version=self.option,
        )

    @property
    def is_mmppt(self) -> bool:
        """Return True if mmppt."""
        return self.hub.mmppt_common[self.inverter_unit_id] is not None

    @property
    def use_status_vendor4(self) -> bool:
        """Return the use status vendor4."""
        return self._use_status_vendor4

    @property
    def use_mmppt_units(self) -> bool:
        """Return the use mmppt units."""
        return self._use_mmppt_units

    @property
    def has_storage_control(self) -> bool | None:
        """Return True if storage control."""
        return self.storage_control

    @property
    def has_global_power_control(self) -> bool | None:
        """Return True if global power control."""
        return self.global_power_control

    @property
    def has_advanced_power_control(self) -> bool | None:
        """Return True if advanced power control."""
        return self.advanced_power_control

    @property
    def has_site_limit_control(self) -> bool | None:
        """Return True if site limit control."""
        return self.site_limit_control


class SolarEdgeMMPPTUnit:
    """Defines a SolarEdge inverter MMPPT unit."""

    def __init__(
        self, inverter: SolarEdgeInverter, hub: SolarEdgeModbusMultiHub, unit: int
    ) -> None:
        """Initialize the solar edge mmppt unit."""
        self.inverter = inverter
        self.hub = hub
        self.unit = unit
        self.mmppt_key = f"mmppt_{self.unit}"

    @property
    def anchor(self) -> str:
        """Stable identifier for this MMPPT unit, independent of uid_base."""
        return _device_anchor(
            self.hub._entry_id,
            "inverter",
            self.inverter.inverter_unit_id,
            "mmppt",
            self.unit,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.inverter.uid_base, self.mmppt_key),
                (DOMAIN, self.anchor),
            },
            name=f"{self.inverter.name} MPPT{self.unit}",
            manufacturer=self.inverter.manufacturer,
            model=self.inverter.model,
            hw_version=f"ID {self.mmppt_id}",
            serial_number=f"{self.mmppt_idstr}",
            via_device=(DOMAIN, self.inverter.uid_base),
        )

    @property
    def mmppt_id(self) -> str:
        """Return the mmppt id."""
        return self.inverter.mmppt_data.units[self.unit].ID

    @property
    def mmppt_idstr(self) -> str:
        """Return the mmppt idstr."""
        return self.inverter.mmppt_data.units[self.unit].IDStr


class SolarEdgeMeter:
    """Defines a SolarEdge meter."""

    def __init__(
        self, device_id: int, meter_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
        """Initialize the solar edge meter."""
        self.inverter_unit_id = device_id
        self.hub = hub
        self.meter_id = meter_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self.mmppt_common = self.hub.mmppt_common[self.inverter_unit_id]
        self._via_device = None

        try:
            self.start_address = METER_REG_BASE[self.meter_id]
        except KeyError as err:
            raise DeviceInvalid(f"Invalid meter_id {self.meter_id}") from err

        if self.mmppt_common is not None:
            if self.mmppt_common.mmppt_Units == 2:
                self.start_address = self.start_address + 50
            elif self.mmppt_common.mmppt_Units == 3:
                self.start_address = self.start_address + 70
            else:
                raise DeviceInvalid(
                    f"Invalid mmppt_Units value {self.mmppt_common.mmppt_Units}"
                )

        self.base_offset = self.start_address - METER_REG_BASE[1]

        self.meter_info = MeterInfo(
            self.hub.connection.for_unit(self.inverter_unit_id),
            base_offset=self.base_offset,
        )
        self.meter_data = MeterData(
            self.hub.connection.for_unit(self.inverter_unit_id),
            base_offset=self.base_offset,
        )

    async def init_device(self) -> None:
        """Init device."""
        try:
            _LOGGER.debug(
                "Reading component MeterInfo(for_unit(%s),base_offset=%s)",
                self.inverter_unit_id,
                self.base_offset,
            )
            await self.hub.component_update(self.inverter_unit_id, self.meter_info)

            _log_component_fields(
                f"I{self.inverter_unit_id}M{self.meter_id}", self.meter_info
            )

            if (
                self.meter_info.C_SunSpec_DID == SunSpecNotImpl.UINT16
                or self.meter_info.C_SunSpec_DID != 0x0001
                or self.meter_info.C_SunSpec_Length != 65
            ):
                raise DeviceInvalid(
                    f"Meter I{self.inverter_unit_id}M{self.meter_id} ident incorrect or not installed."
                )

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                f"Error reading MeterInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset}): {e}"
            ) from e

        except ModbusExceptionError as err:
            raise DeviceInvalid(
                f"Meter I{self.inverter_unit_id}M{self.meter_id}: unsupported address"
            ) from err

        self.manufacturer = self.meter_info.C_Manufacturer
        self.model = self.meter_info.C_Model
        self.option = self.meter_info.C_Option
        self.fw_version = self.meter_info.C_Version
        self.serial = self.meter_info.C_SerialNumber
        self.device_address = self.meter_info.C_Device_address
        self.name = (
            f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id} M{self.meter_id}"
        )

        inverter_model = self.inverter_common.C_Model
        inerter_serial = self.inverter_common.C_SerialNumber
        self.uid_base = f"{inverter_model}_{inerter_serial}_M{self.meter_id}"

    async def read_modbus_data(self) -> None:
        """Read modbus data."""
        try:
            _LOGGER.debug(
                "Reading component MeterData(for_unit(%s),base_offset=%s)",
                self.inverter_unit_id,
                self.base_offset,
            )
            await self.hub.component_update(self.inverter_unit_id, self.meter_data)

        except ModbusConnectionError as e:
            raise ModbusConnectionError(
                f"Connection error reading inverter ID {self.inverter_unit_id} at MeterData: {e}"
            ) from e

        except ModbusProtocolError as e:
            raise ModbusProtocolError(
                f"Protocol error reading inverter ID {self.inverter_unit_id} at MeterData: {e}"
            ) from e

        except ModbusTimeoutError as e:
            raise ModbusTimeoutError(
                f"Timeout error reading inverter ID {self.inverter_unit_id} at MeterData: {e}"
            ) from e

        _log_component_fields(
            f"I{self.inverter_unit_id}M{self.meter_id}", self.meter_data
        )

        if (
            self.meter_data.C_SunSpec_DID == SunSpecNotImpl.UINT16
            or self.meter_data.C_SunSpec_DID not in [201, 202, 203, 204]
            or self.meter_data.C_SunSpec_Length != 105
        ):
            raise DeviceInvalid(
                f"Meter {self.meter_id} ident incorrect or not installed."
            )

    @property
    def anchor(self) -> str:
        """Stable identifier for this meter, independent of uid_base."""
        return _device_anchor(
            self.hub._entry_id,
            "inverter",
            self.inverter_unit_id,
            "meter",
            self.meter_id,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base), (DOMAIN, self.anchor)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial,
            sw_version=self.fw_version,
            hw_version=self.option,
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        """Return the via device."""
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)


class _DERStorageBatteryInfo:
    """Battery identity for a DER Storage Capacity (SunSpec model 713).

    Model 713 identity is the inverter manufacturer/model/serial. Used by SolarEdgeDERBattery.
    """

    def __init__(self, der: DERStorageCapacity, inverter_common, battery_id: int):
        self._der = der
        self.B_Manufacturer = inverter_common.C_Manufacturer
        self.B_Model = f"{inverter_common.C_Model}"
        self.B_Version = None
        self.B_Option = None
        self.B_SerialNumber = f"{inverter_common.C_SerialNumber}"
        self.B_Device_Address = inverter_common.C_Device_address

    @property
    def B_RatedEnergy(self):
        return self._der.WHRtg

    def __getattr__(self, name):
        return None


class _DERStorageBatteryData:
    """Adapt DER Storage Capacity (SunSpec model 713) to BatteryData.

    Provides the BatteryData attributes that sensor.py expects.

    Only SoC/SoH/energy/status are in model 713; every other BatteryData
    field (temps, voltage, current, power, event logs) will be None.
    Sta is not currently populated by SolarEdge devices, but is mapped so
    the status sensor is ready if that changes.
    """

    _MAPPED = {
        "B_SOE": "SoC",
        "B_SOH": "SoH",
        "B_Energy_Available": "WHAvail",
        "B_Energy_Max": "WHRtg",
        "B_Status": "Sta",
    }

    def __init__(self, der: DERStorageCapacity):
        self._der = der

    def __getattr__(self, name):
        mapped = self._MAPPED.get(name)
        return getattr(self._der, mapped) if mapped else None


class SolarEdgeBattery:
    """Defines a SolarEdge battery."""

    def __init__(
        self, device_id: int, battery_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
        """Initialize the solar edge battery."""
        self.inverter_unit_id = device_id
        self.hub = hub
        self.battery_id = battery_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self._via_device = None

        try:
            self.base_offset = BATTERY_REG_BASE[self.battery_id] - BATTERY_REG_BASE[1]
        except KeyError as err:
            raise DeviceInvalid(f"Invalid battery_id {self.battery_id}") from err

        self.battery_info = BatteryInfo(
            self.hub.connection.for_unit(self.inverter_unit_id),
            base_offset=self.base_offset,
        )
        self.battery_data = BatteryData(
            self.hub.connection.for_unit(self.inverter_unit_id),
            base_offset=self.base_offset,
        )

    async def init_device(self) -> None:
        """Init device."""
        try:
            _LOGGER.debug(
                "Reading component BatteryInfo(for_unit(%s),base_offset=%s)",
                self.inverter_unit_id,
                self.base_offset,
            )
            async with asyncio.timeout(self.hub.request_timeout):
                # only try battery once during init, otherwise this takes too long
                await self.hub.component_update(
                    self.inverter_unit_id, self.battery_info
                )

            _log_component_fields(
                f"I{self.inverter_unit_id}B{self.battery_id}", self.battery_info
            )

        except TimeoutError as err:
            raise DeviceInvalid(
                f"Timeout BatteryInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            ) from err

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                f"Error reading BatteryInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset}): {e}"
            ) from e

        except ModbusExceptionError as err:
            raise DeviceInvalid(
                f"Battery I{self.inverter_unit_id}B{self.battery_id}: unsupported address"
            ) from err

        if (
            float_to_hex(self.battery_info.B_RatedEnergy) == hex(SunSpecNotImpl.FLOAT32)
            or self.battery_info.B_RatedEnergy <= 0
        ):
            raise DeviceInvalid(f"Battery {self.battery_id} not usable (rating <=0)")

        self.manufacturer = self.battery_info.B_Manufacturer
        self.model = self.battery_info.B_Model
        self.option = ""
        self.fw_version = self.battery_info.B_Version
        self.serial = self.battery_info.B_SerialNumber
        self.device_address = self.battery_info.B_Device_Address
        self.name = (
            f"{self.hub.hub_id.capitalize()} "
            f"I{self.inverter_unit_id} B{self.battery_id}"
        )

        inverter_model = self.inverter_common.C_Model
        inerter_serial = self.inverter_common.C_SerialNumber
        self.uid_base = f"{inverter_model}_{inerter_serial}_B{self.battery_id}"

    async def read_modbus_data(self) -> None:
        """Read modbus data."""
        try:
            _LOGGER.debug(
                "Reading component BatteryData(for_unit(%s),base_offset=%s)",
                self.inverter_unit_id,
                self.base_offset,
            )
            await self.hub.component_update(self.inverter_unit_id, self.battery_data)

        except ModbusConnectionError as e:
            raise ModbusConnectionError(
                f"Connection error reading inverter ID {self.inverter_unit_id} at BatteryData: {e}"
            ) from e

        except ModbusProtocolError as e:
            raise ModbusProtocolError(
                f"Protocol error reading inverter ID {self.inverter_unit_id} at BatteryData: {e}"
            ) from e

        except ModbusTimeoutError as e:
            raise ModbusTimeoutError(
                f"Timeout error reading inverter ID {self.inverter_unit_id} at BatteryData: {e}"
            ) from e

        _log_component_fields(
            f"I{self.inverter_unit_id}B{self.battery_id}", self.battery_data
        )

    @property
    def anchor(self) -> str:
        """Stable identifier for this battery, independent of uid_base."""
        return _device_anchor(
            self.hub._entry_id,
            "inverter",
            self.inverter_unit_id,
            "battery",
            self.battery_id,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base), (DOMAIN, self.anchor)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial,
            sw_version=self.fw_version,
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        """Return the via device."""
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)

    @property
    def allow_battery_energy_reset(self) -> bool:
        """Return the allow battery energy reset."""
        return self.hub.allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        """Return the battery rating adjust."""
        return self.hub.battery_rating_adjust

    @property
    def battery_energy_reset_cycles(self) -> int:
        """Return the battery energy reset cycles."""
        return self.hub.battery_energy_reset_cycles


class SolarEdgeDERBattery:
    """SunSpec model 713 (DER Storage Capacity).

    Independent of SolarEdgeBattery (proprietary battery block, not a fallback).
    Both can be present on the same inverter at once. Any model-713 blocks the SunS scan
    finds each become one of these. Not documented by SolarEdge. Reported in
    https://github.com/WillCodeForCats/solaredge-modbus-multi/discussions/1055

    Exposes the same battery_info/battery_data attributes with _DERStorage* adapters.
    """

    def __init__(
        self,
        device_id: int,
        battery_id: int,
        hub: SolarEdgeModbusMultiHub,
        der_storage_model,
    ) -> None:
        """Initialize the solar edge der battery."""
        self.inverter_unit_id = device_id
        self.hub = hub
        self.battery_id = battery_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self._via_device = None

        self.der_storage_capacity_data = DERStorageCapacity(
            self.hub.connection.for_unit(self.inverter_unit_id), der_storage_model
        )

    async def init_device(self) -> None:
        """Init device."""
        try:
            _LOGGER.debug(
                "Reading component DERStorageCapacity(for_unit(%s))",
                self.inverter_unit_id,
            )
            await self.hub.component_update(
                self.inverter_unit_id, self.der_storage_capacity_data
            )

            _log_component_fields(
                f"I{self.inverter_unit_id}DERB{self.battery_id}",
                self.der_storage_capacity_data,
            )

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                "Error reading DERStorageCapacity"
                f"(for_unit({self.inverter_unit_id})): {e}"
            ) from e

        except ModbusExceptionError as err:
            raise DeviceInvalid(
                f"Battery I{self.inverter_unit_id}DERB{self.battery_id}: "
                "DER Storage Capacity unsupported address"
            ) from err

        except SunSpecError as e:
            raise DeviceInvalid(
                f"Battery I{self.inverter_unit_id}DERB{self.battery_id}: "
                f"DER Storage Capacity model shifted or invalid: {e}"
            ) from e

        # WHRtg does not appear to be supported, but if it was then we could check the
        # capacity and skip adding it on systems with no battery
        # if (
        #    self.der_storage_capacity_data.WHRtg is None
        #    or self.der_storage_capacity_data.WHRtg <= 0
        # ):
        #    raise DeviceInvalid(
        #        f"DER Storage Capacity battery {self.battery_id} not usable "
        #        "(rating <=0)"
        #    )

        self.battery_info = _DERStorageBatteryInfo(
            self.der_storage_capacity_data, self.inverter_common, self.battery_id
        )
        self.battery_data = _DERStorageBatteryData(self.der_storage_capacity_data)

        self.manufacturer = self.battery_info.B_Manufacturer
        self.model = self.battery_info.B_Model
        self.option = "SunSpec Model 713"
        self.fw_version = self.battery_info.B_Version
        self.serial = self.battery_info.B_SerialNumber
        self.device_address = self.battery_info.B_Device_Address
        self.name = (
            f"{self.hub.hub_id.capitalize()} "
            f"I{self.inverter_unit_id} DERB{self.battery_id}"
        )

        inverter_model = self.inverter_common.C_Model
        inerter_serial = self.inverter_common.C_SerialNumber
        self.uid_base = f"{inverter_model}_{inerter_serial}_DERB{self.battery_id}"

    async def read_modbus_data(self) -> None:
        """Refresh from DER Storage Capacity (SunSpec model 713).

        self.battery_data is a _DERStorageBatteryData adapter wrapping the
        same der_storage_capacity_data instance refreshed here, so it picks up
        the new values automatically -- no need to rebuild it every poll.
        """
        try:
            _LOGGER.debug(
                "Reading component DERStorageCapacity(for_unit(%s))",
                self.inverter_unit_id,
            )
            await self.hub.component_update(
                self.inverter_unit_id, self.der_storage_capacity_data
            )

        except ModbusConnectionError as e:
            raise ModbusConnectionError(
                "Connection error reading inverter ID "
                f"{self.inverter_unit_id} at DERStorageCapacity: {e}"
            ) from e

        except ModbusProtocolError as e:
            raise ModbusProtocolError(
                "Protocol error reading inverter ID "
                f"{self.inverter_unit_id} at DERStorageCapacity: {e}"
            ) from e

        except ModbusTimeoutError as e:
            raise ModbusTimeoutError(
                "Timeout error reading inverter ID "
                f"{self.inverter_unit_id} at DERStorageCapacity: {e}"
            ) from e

        except SunSpecError as e:
            raise ModbusProtocolError(
                "DER Storage Capacity model shifted or invalid reading "
                f"inverter ID {self.inverter_unit_id} at DERStorageCapacity: {e}"
            ) from e

        _log_component_fields(
            f"I{self.inverter_unit_id}DERB{self.battery_id}",
            self.der_storage_capacity_data,
        )

    @property
    def anchor(self) -> str:
        """Stable identifier for this DER battery, independent of uid_base."""
        return _device_anchor(
            self.hub._entry_id,
            "inverter",
            self.inverter_unit_id,
            "derbattery",
            self.battery_id,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base), (DOMAIN, self.anchor)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial,
            sw_version=self.fw_version,
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        """Return the via device."""
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)

    @property
    def allow_battery_energy_reset(self) -> bool:
        """Return the allow battery energy reset."""
        return self.hub.allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        """Return the battery rating adjust."""
        return self.hub.battery_rating_adjust

    @property
    def battery_energy_reset_cycles(self) -> int:
        """Return the battery energy reset cycles."""
        return self.hub.battery_energy_reset_cycles


class SolarEdgeEVSE:
    """Class that defines a SolarEdge EVSE."""

    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        """Initialize the solar edge evse."""
        self.evse_unit_id = device_id
        self.hub = hub
        self.has_parent = False
        self.sunspec_models = None

        self.evse_common = EvseCommon(self.hub.connection.for_unit(self.evse_unit_id))

    async def init_device(self) -> None:
        """Set up data about the device from modbus."""

        try:
            _LOGGER.debug(
                "Reading component EvseCommon(for_unit(%s))", self.evse_unit_id
            )
            await self.hub.component_update(self.evse_unit_id, self.evse_common)

            _log_component_fields(f"E{self.evse_unit_id}", self.evse_common)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                f"Error reading evse ID {self.evse_unit_id} at EvseCommon: {e}"
            ) from e

        except ModbusExceptionError as err:
            raise DeviceInvalid(f"ID {self.evse_unit_id} is not SunSpec.") from err

        if (
            self.evse_common.C_SunSpec_ID == SunSpecNotImpl.UINT32
            or self.evse_common.C_SunSpec_DID == SunSpecNotImpl.UINT16
            or self.evse_common.C_SunSpec_ID != 0x53756E53
            or self.evse_common.C_SunSpec_DID != 0x0001
            or self.evse_common.C_SunSpec_Length != 65
        ):
            raise DeviceInvalid(f"ID {self.evse_unit_id} is not SunSpec.")

        self.manufacturer = self.evse_common.C_Manufacturer
        self.model = self.evse_common.C_Model
        self.option = self.evse_common.C_Option
        self.serial = self.evse_common.C_SerialNumber
        self.device_address = self.evse_common.C_Device_address
        self.name = f"{self.hub.hub_id.capitalize()} E{self.evse_unit_id}"
        self.uid_base = f"{self.model}_{self.serial}"

    async def read_modbus_data(self) -> None:
        """Read and update dynamic modbus registers."""

        try:
            _LOGGER.debug(
                "Reading component EvseCommon(for_unit(%s))", self.evse_unit_id
            )
            await self.hub.component_update(self.evse_unit_id, self.evse_common)

            _log_component_fields(f"E{self.evse_unit_id}", self.evse_common)

        except ModbusExceptionError:
            _LOGGER.error("E%s: EVSE register(s) NOT available", self.evse_unit_id)

        except ModbusConnectionError as e:
            raise ModbusConnectionError(
                f"Connection error reading evse ID {self.evse_unit_id} at EvseCommon: {e}"
            ) from e

        except ModbusProtocolError as e:
            raise ModbusProtocolError(
                f"Protocol error reading evse ID {self.evse_unit_id} at EvseCommon: {e}"
            ) from e

        except ModbusTimeoutError as e:
            raise ModbusTimeoutError(
                f"Timeout error reading evse ID {self.evse_unit_id} at EvseCommon: {e}"
            ) from e

    @property
    def fw_version(self) -> str | None:
        """Return the fw version."""
        return getattr(self.evse_common, "C_Version", None)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial,
            sw_version=self.fw_version,
            hw_version=self.option,
        )
