from __future__ import annotations

import asyncio
import importlib.metadata
import logging

from awesomeversion import AwesomeVersion, AwesomeVersionStrategy
from awesomeversion.exceptions import (
    AwesomeVersionCompareException,
    AwesomeVersionStrategyException,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import DeviceInfo
from modbus_connection.exceptions import (
    ModbusConnectionError,
    ModbusExceptionError,
    ModbusProtocolError,
    ModbusTimeoutError,
)
from modbus_connection.model.sunspec import SunSpecError
from modbus_connection.model.sunspec import scan as suns_scan

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
    component_to_dict,
)
from .const import (
    BATTERY_REG_BASE,
    DETECT_EVSE_REGEX,
    DOMAIN,
    METER_REG_BASE,
    MMPPT_UNITS_VERSION,
    STATUS_VENDOR4_VERSION,
    TMODBUS_REQUIRED_VERSION,
    WRITE_SETTLE_CYCLES,
    ConfDefaultFlag,
    ConfDefaultInt,
    ConfDefaultStr,
    ConfName,
    ModbusExceptions,
    RetrySettings,
    SolarEdgeTimeouts,
    SunSpecNotImpl,
)
from .helpers import float_to_hex

_LOGGER = logging.getLogger(__name__)
tmodbus_version = importlib.metadata.version("tmodbus")


class SolarEdgeException(Exception):
    """Base class for other exceptions"""


class HubInitFailed(SolarEdgeException):
    """Raised when an error happens during init"""


class DeviceIsEVSE(SolarEdgeException):
    """Raised when an inverter device matches a EVSE model"""


class DataUpdateFailed(SolarEdgeException):
    """Raised when an update cycle fails"""


class DeviceInvalid(SolarEdgeException):
    """Raised when a device is not usable or invalid"""


async def async_update_with_retry(component) -> None:
    """Call component.async_update(), retrying connection/timeout errors.

    modbus-connection has no built-in per-request retry, unlike pymodbus's
    `retries` option, so this method mimics that behavior.
    """
    for attempt in range(1, RetrySettings.RequestRetries + 1):
        try:
            await component.async_update()
            return

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            _LOGGER.debug(
                f"{type(component).__name__}.async_update() attempt {attempt} "
                f"of {RetrySettings.RequestRetries} failed: {e}"
            )

            if attempt >= RetrySettings.RequestRetries:
                raise


async def async_write_with_retry(component, field: str, value) -> None:
    """Call component.write(field, value), retrying connection/timeout errors.

    Like async_update_with_retry() but for writes.
    """
    for attempt in range(1, RetrySettings.RequestRetries + 1):
        try:
            await component.write(field, value)
            return

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            _LOGGER.debug(
                f"{type(component).__name__}.write({field!r}) attempt {attempt} "
                f"of {RetrySettings.RequestRetries} failed: {e}"
            )

            if attempt >= RetrySettings.RequestRetries:
                raise


def _parse_se_version(version_str: str) -> AwesomeVersion:
    """Strip zero-padding from SolarEdge firmware version strings."""
    stripped = ".".join(str(int(p)) for p in version_str.split("."))
    return AwesomeVersion(stripped, ensure_strategy=AwesomeVersionStrategy.SIMPLEVER)


class SolarEdgeModbusMultiHub:
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

        self._tmodbus_version = tmodbus_version

        _LOGGER.debug(
            (
                f"{DOMAIN} configuration: "
                f"inverter_list={self._inverter_list}, "
                f"detect_meters={self._detect_meters}, "
                f"detect_batteries={self._detect_batteries}, "
                f"detect_extras={self._detect_extras}, "
                f"adv_storage_control={self._adv_storage_control}, "
                f"adv_site_limit_control={self._adv_site_limit_control}, "
                f"allow_battery_energy_reset={self._allow_battery_energy_reset}, "
                f"sleep_after_write={self._sleep_after_write}, "
                f"battery_rating_adjust={self._battery_rating_adjust}, "
            ),
        )

        _LOGGER.debug(f"tmodbus version {self.tmodbus_version}")

    async def _async_init_solaredge(self) -> None:
        """Detect devices and load initial modbus data from inverters."""

        tmodbus_version_tuple = self._safe_version_tuple(self.tmodbus_version)
        required_version_tuple = self._safe_version_tuple(self.tmodbus_required_version)

        if tmodbus_version_tuple < required_version_tuple:
            raise HubInitFailed(
                f"tmodbus version must be at least {self.tmodbus_required_version}, "
                f"but {self.tmodbus_version} is installed. Please remove or upgrade other custom "
                "integrations that depend on an older version of tmodbus and restart."
            )

        if self.option_storage_control:
            _LOGGER.warning(
                (
                    "Power Control Options: Storage Control is enabled. "
                    "Use at your own risk! "
                    "Adjustable parameters in Modbus registers are intended for "
                    "long-term storage. Periodic changes may damage the flash memory."
                ),
            )

        if self.option_site_limit_control:
            _LOGGER.warning(
                (
                    "Power Control Options: Site Limit Control is enabled. "
                    "Use at your own risk! "
                    "Adjustable parameters in Modbus registers are intended for "
                    "long-term storage. Periodic changes may damage the flash memory."
                ),
            )

        for inverter_unit_id in self._inverter_list:
            try:
                _LOGGER.debug(
                    f"Looking for inverter at {self.hub_host} ID {inverter_unit_id}"
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
                raise HubInitFailed(f"{e}")

            except DeviceInvalid as e:
                # Inverters are mandatory, but if the Device ID is invalid or not responding
                # skip it and warn the user instead of failing the entire hub setup
                _LOGGER.error(f"Inverter at {self.hub_host} ID {inverter_unit_id}: {e}")
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
                    f"Device model matches EVSE at {self.hub_host} ID {inverter_unit_id}: {e}"
                )
                new_evse = SolarEdgeEVSE(inverter_unit_id, self)
                await new_evse.init_device()
                self.evses.append(new_evse)

                # Skip meter and battery detection if DeviceIsEVSE
                new_evse.evse_common.restrict_fields(["C_Version"])
                continue

            try:
                _LOGGER.debug(
                    f"Scanning SunS models at {self.hub_host} ID {inverter_unit_id}"
                )
                suns_models = await suns_scan(
                    self.connection.for_unit(inverter_unit_id), 40000
                )

                der_storage_models = suns_models.get(713, []) if suns_models else []

                for model in suns_models.chain:
                    _LOGGER.debug(
                        f"I{inverter_unit_id}: found SunS model {model.model_id} "
                        f"(length {model.length})"
                    )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
                ModbusExceptionError,
                SunSpecError,
            ) as e:
                _LOGGER.debug(f"I{inverter_unit_id}: SunS model scan failed: {e}")
                der_storage_models = []

            if self._detect_meters:
                for meter_id in METER_REG_BASE:
                    try:
                        _LOGGER.debug(
                            f"Looking for meter I{inverter_unit_id}M{meter_id}"
                        )
                        new_meter = SolarEdgeMeter(inverter_unit_id, meter_id, self)
                        await new_meter.init_device()

                        for meter in self.meters:
                            # Allow duplicate serial number on meters PR#412
                            if new_meter.serial == meter.serial:
                                _LOGGER.warning(
                                    (
                                        f"Duplicate serial {new_meter.serial} "
                                        f"on I{inverter_unit_id}M{meter_id}"
                                    ),
                                )

                        new_meter.via_device = new_inverter.uid_base
                        self.meters.append(new_meter)
                        _LOGGER.debug(f"Found I{inverter_unit_id}M{meter_id}")

                    except (
                        ModbusConnectionError,
                        ModbusProtocolError,
                        ModbusTimeoutError,
                    ) as e:
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}M{meter_id}: {e}")
                        pass

            if self._detect_batteries:
                # SolarEdge proprietary battery block for up to three batteries.
                for battery_id in BATTERY_REG_BASE:
                    try:
                        _LOGGER.debug(
                            f"Looking for battery I{inverter_unit_id}B{battery_id}"
                        )
                        new_battery = SolarEdgeBattery(
                            inverter_unit_id, battery_id, self
                        )
                        await new_battery.init_device()

                        for battery in self.batteries:
                            if new_battery.serial == battery.serial:
                                _LOGGER.warning(
                                    (
                                        f"Duplicate serial {new_battery.serial} "
                                        f"on I{inverter_unit_id}B{battery_id}"
                                    ),
                                )
                                raise DeviceInvalid(
                                    f"Duplicate B{battery_id} serial "
                                    f"{new_battery.serial}"
                                )

                        new_battery.via_device = new_inverter.uid_base
                        self.batteries.append(new_battery)
                        _LOGGER.debug(f"Found I{inverter_unit_id}B{battery_id}")

                    except (
                        ModbusConnectionError,
                        ModbusProtocolError,
                        ModbusTimeoutError,
                    ) as e:
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}B{battery_id}: {e}")
                        pass

                # DER Storage Capacity (SunSpec model 713)
                for der_id, der_storage_model in enumerate(der_storage_models, 1):
                    try:
                        _LOGGER.debug(
                            "Looking for DER Storage Capacity "
                            f"I{inverter_unit_id}DERB{der_id}"
                        )
                        new_der_battery = SolarEdgeDERBattery(
                            inverter_unit_id, der_id, self, der_storage_model
                        )
                        await new_der_battery.init_device()

                        new_der_battery.via_device = new_inverter.uid_base
                        self.der_batteries.append(new_der_battery)
                        _LOGGER.debug(
                            f"Found I{inverter_unit_id} DER Storage Capacity "
                            f"battery {der_id}"
                        )

                    except (
                        ModbusConnectionError,
                        ModbusProtocolError,
                        ModbusTimeoutError,
                    ) as e:
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}DERB{der_id}: {e}")
                        pass

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
            raise HubInitFailed(f"Read error: {e}")

        except DeviceInvalid as e:
            raise HubInitFailed(f"Invalid device: {e}")

        except TimeoutError as e:
            raise HubInitFailed(f"Timeout error: {e}")

        self.initalized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        if not self.initalized:
            try:
                async with asyncio.timeout(self.coordinator_timeout):
                    await self._async_init_solaredge()

            except TimeoutError:
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
                )

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
            raise DataUpdateFailed(f"Update failed: {e}")

        except DeviceInvalid as e:
            await self.connection.disconnect()
            raise DataUpdateFailed(f"Invalid device: {e}")

        except TimeoutError as e:
            await self.connection.disconnect()

            self._coordinator_timeouts_count += 1

            _LOGGER.debug(
                f"Coordinator timeout {self._coordinator_timeouts_count} limit {self._coordinator_timeouts_limit}"
            )

            if self._coordinator_timeouts_count >= self._coordinator_timeouts_limit:
                _LOGGER.warning(
                    f"Coordinator has timed out "
                    f"{self._coordinator_timeouts_limit} times in a row."
                )
                self._coordinator_timeouts_count = 0

            raise DataUpdateFailed(f"Timeout error: {e}")

        if self._coordinator_timeouts_count > 0:
            _LOGGER.debug(
                f"Coordinator timeout count {self._coordinator_timeouts_count} limit {self._coordinator_timeouts_limit}"
            )
            self._coordinator_timeouts_count = 0

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
            _LOGGER.debug(f"Clearing unit {unit} request spacing.")
            self.connection.for_unit(unit).set_message_spacing(0)
            del self._write_settle_cycles[unit]
        else:
            _LOGGER.debug(
                f"Unit {unit} has {cycles_remaining - 1} refreshes until clearing."
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
                f"Spacing requests to unit {unit} for {self.sleep_after_write} "
                f"seconds after write to field {field}."
            )
            self.connection.for_unit(unit).set_message_spacing(self.sleep_after_write)
            self._write_settle_cycles[unit] = WRITE_SETTLE_CYCLES

        try:
            await async_write_with_retry(component, field, value)

        except ModbusExceptionError as e:
            if e.exception_code == ModbusExceptions.IllegalAddress:
                _LOGGER.debug(f"Unit {unit} Write IllegalAddress: {e}")
                raise HomeAssistantError(
                    f"Address not supported at device at ID {unit}."
                )

            if e.exception_code == ModbusExceptions.IllegalFunction:
                _LOGGER.debug(f"Unit {unit} Write IllegalFunction: {e}")
                raise HomeAssistantError(
                    f"Function not supported by device at ID {unit}."
                )

            if e.exception_code == ModbusExceptions.IllegalValue:
                _LOGGER.debug(f"Unit {unit} Write IllegalValue: {e}")
                raise HomeAssistantError(f"Value invalid for device at ID {unit}.")

            _LOGGER.debug(f"Unit {unit} Write rejected: {e}")
            raise HomeAssistantError(
                f"Write rejected by device at ID {unit}: {e}"
            ) from e

        except ModbusTimeoutError as e:
            _LOGGER.error(f"Write failed: No response from inverter ID {unit}.")
            raise HomeAssistantError(f"No response from inverter ID {unit}.") from e

        except (ModbusConnectionError, ModbusProtocolError) as e:
            _LOGGER.error(f"Connection failed: {e}")
            raise HomeAssistantError(f"Connection to inverter ID {unit} failed.")

        _LOGGER.debug(f"Finished with write {field}.")

    def _setup_inverter_id_failed_issue(self, unit_id: int) -> str:
        return f"setup_inverter_id_failed_{self._entry_id}_{unit_id}"

    @staticmethod
    def _safe_version_tuple(version_str: str) -> tuple[int, ...]:
        try:
            version_parts = version_str.split(".")
            version_tuple = tuple(int(part) for part in version_parts)
            return version_tuple
        except ValueError:
            raise ValueError(f"Invalid version string: {version_str}")

    @property
    def initalized(self):
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
    def hub_host(self) -> str:
        """Return the modbus client host."""
        return self._host

    @property
    def hub_port(self) -> int:
        """Return the modbus client port."""
        return self._port

    @property
    def option_storage_control(self) -> bool:
        return self._adv_storage_control

    @property
    def option_site_limit_control(self) -> bool:
        return self._adv_site_limit_control

    @property
    def option_detect_extras(self) -> bool:
        return self._detect_extras

    @property
    def allow_battery_energy_reset(self) -> bool:
        return self._allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        return (self._battery_rating_adjust + 100) / 100

    @property
    def battery_energy_reset_cycles(self) -> int:
        return self._battery_energy_reset_cycles

    @property
    def number_of_meters(self) -> int:
        return len(self.meters)

    @property
    def number_of_batteries(self) -> int:
        return len(self.batteries)

    @property
    def number_of_inverters(self) -> int:
        return len(self._inverter_list)

    @property
    def sleep_after_write(self) -> int:
        return self._sleep_after_write

    @property
    def tmodbus_required_version(self) -> str:
        return TMODBUS_REQUIRED_VERSION

    @property
    def tmodbus_version(self) -> str:
        return self._tmodbus_version

    @property
    def coordinator_timeout(self) -> int:
        if not self.initalized:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Init * self.number_of_inverters
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 3  # max 3 per inverter
            this_timeout += (SolarEdgeTimeouts.Battery * 2) * 3  # max 3 per inverter
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters
            # SunS model-chain scan runs unconditionally, once per inverter at setup
            this_timeout += SolarEdgeTimeouts.Read * self.number_of_inverters

        else:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_meters
            this_timeout += SolarEdgeTimeouts.Battery * self.number_of_batteries
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters

        this_timeout = this_timeout / 1000

        _LOGGER.debug(f"coordinator timeout is {this_timeout}")
        return this_timeout


class SolarEdgeInverter:
    """Defines a SolarEdge inverter."""

    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.mmppt_units = []
        self.decoded_common = {}
        self.decoded_model = {}
        self.decoded_mmppt = {}
        self.decoded_storage_control = {}
        self.has_parent = False
        self.has_battery = None
        self.global_power_control = None
        self.advanced_power_control = None
        self.site_limit_control = None
        self.storage_control = None
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

    async def init_device(self) -> None:
        """Set up data about the device from modbus."""

        try:
            _LOGGER.debug(
                f"Reading component InverterCommon(for_unit({self.inverter_unit_id}))"
            )
            await self.hub.component_update(self.inverter_unit_id, self.inverter_common)

            self.decoded_common = component_to_dict(self.inverter_common)

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value} "
                        f"{type(value)}"
                    ),
                )

            self.hub.inverter_common[self.inverter_unit_id] = self.inverter_common

        except (ModbusConnectionError, ModbusProtocolError) as e:
            raise DeviceInvalid(
                f"Error reading inverter ID {self.inverter_unit_id} at InverterCommon: {e}"
            )

        except ModbusTimeoutError:
            raise DeviceInvalid(f"No response from Device ID {self.inverter_unit_id}")

        except ModbusExceptionError:
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            )

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
                f"Could not parse inverter version "
                f"{self.inverter_common.C_Version!r}: {e}"
            )
            self._use_status_vendor4 = False
            self._use_mmppt_units = False

        self.inverter_data.restrict_status_vendor4(self._use_status_vendor4)

        is_multi_mppt = False

        if self.use_mmppt_units:
            try:
                _LOGGER.debug(
                    f"Reading component MmpptCommon(for_unit({self.inverter_unit_id}))"
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.mmppt_common
                )

                self.decoded_mmppt = component_to_dict(self.mmppt_common)

                for name, value in iter(self.decoded_mmppt.items()):
                    _LOGGER.debug(
                        (
                            f"I{self.inverter_unit_id} MMPPT: "
                            f"{name} {hex(value) if isinstance(value, int) else value} "
                            f"{type(value)}"
                        ),
                    )

                if (
                    self.mmppt_common.mmppt_DID == SunSpecNotImpl.UINT16
                    or self.mmppt_common.mmppt_Units == SunSpecNotImpl.UINT16
                    or self.mmppt_common.mmppt_DID not in [160]
                    or self.mmppt_common.mmppt_Units not in [2, 3]
                ):
                    _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")

                else:
                    _LOGGER.debug(f"I{self.inverter_unit_id} is Multiple MPPT")
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
                _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")
        else:
            _LOGGER.debug(
                f"I{self.inverter_unit_id} is NOT Multiple MPPT "
                "(firmware does not support MMPPT units)"
            )

        self.hub.mmppt_common[self.inverter_unit_id] = (
            self.mmppt_common if is_multi_mppt else None
        )

        if is_multi_mppt:
            for unit_index in range(self.mmppt_common.mmppt_Units):
                self.mmppt_units.append(SolarEdgeMMPPTUnit(self, self.hub, unit_index))
                _LOGGER.debug(f"I{self.inverter_unit_id} MMPPT Unit {unit_index}")

    async def read_modbus_data(self) -> None:
        """Read and update dynamic modbus registers."""

        try:
            _LOGGER.debug(
                f"Reading component InverterCommon(for_unit({self.inverter_unit_id}))"
            )
            await self.hub.component_update(self.inverter_unit_id, self.inverter_common)

            _LOGGER.debug(
                f"Reading component InverterData(for_unit({self.inverter_unit_id}))"
            )
            await self.hub.component_update(self.inverter_unit_id, self.inverter_data)

            self.decoded_model = component_to_dict(self.inverter_data)

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
                    f"Reading component MmpptData(for_unit({self.inverter_unit_id}))"
                )
                await self.hub.component_update(self.inverter_unit_id, self.mmppt_data)

                self.decoded_model.update(component_to_dict(self.mmppt_data))

                for unit_index, mmppt_unit_data in enumerate(self.mmppt_data.units):
                    self.decoded_model.update(
                        dict(
                            [
                                (
                                    f"mmppt_{unit_index}",
                                    component_to_dict(mmppt_unit_data),
                                )
                            ]
                        )
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
                    f"Reading component GlobalDynamicPowerControl(for_unit({self.inverter_unit_id}))"
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.global_power_control_data
                )
                self.global_power_control = True

                self.decoded_model.update(
                    component_to_dict(self.global_power_control_data)
                )

            except ModbusExceptionError:
                self.global_power_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: global power control NOT available"
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ):
                self.global_power_control = False
                ir.async_create_issue(
                    self.hub._hass,
                    DOMAIN,
                    "detect_timeout_gpc",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_gpc",
                    data={"entry_id": self.hub._entry_id},
                )
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: The inverter did not respond while "
                    "reading data for Global Dynamic Power Controls. These entities "
                    "will be unavailable."
                )

        """ Advanced Power Control: Power Control Block """
        if self.hub.option_detect_extras and self.advanced_power_control is not False:
            try:
                _LOGGER.debug(
                    "Reading component "
                    f"AdvancedPowerControl(for_unit({self.inverter_unit_id}))"
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.advanced_power_control_data
                )
                self.advanced_power_control = True

                self.decoded_model.update(
                    component_to_dict(self.advanced_power_control_data)
                )

            except ModbusExceptionError:
                self.advanced_power_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: advanced power control NOT available"
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ):
                self.advanced_power_control = False
                ir.async_create_issue(
                    self.hub._hass,
                    DOMAIN,
                    "detect_timeout_apc",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_apc",
                    data={"entry_id": self.hub._entry_id},
                )
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: The inverter did not respond while "
                    "reading data for Advanced Power Controls. These entities "
                    "will be unavailable."
                )

        """ Power Control Options: Site Limit Control """
        if self.hub.option_site_limit_control and self.site_limit_control is not False:
            try:
                _LOGGER.debug(
                    "Reading component "
                    f"SiteLimitControl(for_unit({self.inverter_unit_id}))"
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.site_limit_control_data
                )
                self.site_limit_control = True

                self.decoded_model.update(
                    component_to_dict(self.site_limit_control_data)
                )

            except ModbusExceptionError:
                # Before v4.0.0 we were reading Ext_Prod_Max in its own detection block.
                # revisit with own block or exclude Ext_Prod_Max and retry
                self.site_limit_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: site limit control NOT available"
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

        for name, value in iter(self.decoded_model.items()):
            if isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value
            _LOGGER.debug(
                f"I{self.inverter_unit_id}: {name} {display_value} {type(value)}"
            )

        """ Power Control Options: Storage Control """
        if self.hub.option_storage_control and self.storage_control is not False:
            if self.has_battery is None:
                self.has_battery = False
                for battery in self.hub.batteries:
                    if self.inverter_unit_id == battery.inverter_unit_id:
                        self.has_battery = True

            try:
                _LOGGER.debug(
                    "Reading component "
                    f"StorageControl(for_unit({self.inverter_unit_id}))"
                )
                await self.hub.component_update(
                    self.inverter_unit_id, self.storage_control_data
                )
                self.storage_control = True

                self.decoded_storage_control = component_to_dict(
                    self.storage_control_data
                )

                for name, value in iter(self.decoded_storage_control.items()):
                    if isinstance(value, float):
                        display_value = float_to_hex(value)
                    else:
                        display_value = hex(value) if isinstance(value, int) else value
                    _LOGGER.debug(
                        f"I{self.inverter_unit_id}: "
                        f"{name} {display_value} {type(value)}"
                    )

            except ModbusExceptionError:
                self.storage_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: storage control NOT available"
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
        return getattr(self.inverter_common, "C_Version", None)

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

    @property
    def is_mmppt(self) -> bool:
        return self.hub.mmppt_common[self.inverter_unit_id] is not None

    @property
    def use_status_vendor4(self) -> bool:
        return self._use_status_vendor4

    @property
    def use_mmppt_units(self) -> bool:
        return self._use_mmppt_units

    @property
    def has_storage_control(self) -> bool | None:
        return self.storage_control

    @property
    def has_global_power_control(self) -> bool | None:
        return self.global_power_control

    @property
    def has_advanced_power_control(self) -> bool | None:
        return self.advanced_power_control

    @property
    def has_site_limit_control(self) -> bool | None:
        return self.site_limit_control


class SolarEdgeMMPPTUnit:
    """Defines a SolarEdge inverter MMPPT unit."""

    def __init__(
        self, inverter: SolarEdgeInverter, hub: SolarEdgeModbusMultiHub, unit: int
    ) -> None:
        self.inverter = inverter
        self.hub = hub
        self.unit = unit
        self.mmppt_key = f"mmppt_{self.unit}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.inverter.uid_base, self.mmppt_key)},
            name=f"{self.inverter.name} MPPT{self.unit}",
            manufacturer=self.inverter.manufacturer,
            model=self.inverter.model,
            hw_version=f"ID {self.mmppt_id}",
            serial_number=f"{self.mmppt_idstr}",
            via_device=(DOMAIN, self.inverter.uid_base),
        )

    @property
    def mmppt_id(self) -> str:
        return self.inverter.mmppt_data.units[self.unit].ID

    @property
    def mmppt_idstr(self) -> str:
        return self.inverter.mmppt_data.units[self.unit].IDStr


class SolarEdgeMeter:
    """Defines a SolarEdge meter."""

    def __init__(
        self, device_id: int, meter_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.meter_id = meter_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self.mmppt_common = self.hub.mmppt_common[self.inverter_unit_id]
        self._via_device = None

        try:
            self.start_address = METER_REG_BASE[self.meter_id]
        except KeyError:
            raise DeviceInvalid(f"Invalid meter_id {self.meter_id}")

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
        try:
            _LOGGER.debug(
                f"Reading component MeterInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )
            await self.hub.component_update(self.inverter_unit_id, self.meter_info)

            self.decoded_common = component_to_dict(self.meter_info)

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}M{self.meter_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value} "
                        f"{type(value)}"
                    ),
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
            )

        except ModbusExceptionError:
            raise DeviceInvalid(
                f"Meter I{self.inverter_unit_id}M{self.meter_id}: unsupported address"
            )

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
        try:
            _LOGGER.debug(
                f"Reading component MeterData(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )
            await self.hub.component_update(self.inverter_unit_id, self.meter_data)

            self.decoded_model = component_to_dict(self.meter_data)

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

        for name, value in iter(self.decoded_model.items()):
            _LOGGER.debug(
                (
                    f"I{self.inverter_unit_id}M{self.meter_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value} "
                    f"{type(value)}"
                ),
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
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
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
    """Adapts DER Storage Capacity (SunSpec model 713) component to the
    BatteryData attributes that sensor.py expects.

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
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.battery_id = battery_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self._via_device = None

        try:
            self.base_offset = BATTERY_REG_BASE[self.battery_id] - BATTERY_REG_BASE[1]
        except KeyError:
            raise DeviceInvalid(f"Invalid battery_id {self.battery_id}")

        self.battery_info = BatteryInfo(
            self.hub.connection.for_unit(self.inverter_unit_id),
            base_offset=self.base_offset,
        )
        self.battery_data = BatteryData(
            self.hub.connection.for_unit(self.inverter_unit_id),
            base_offset=self.base_offset,
        )

    async def init_device(self) -> None:
        try:
            _LOGGER.debug(
                f"Reading component BatteryInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )
            async with asyncio.timeout(RetrySettings.RequestTimeout):
                # only try once during init, otherwise this takes too long
                await self.hub.component_update(
                    self.inverter_unit_id, self.battery_info
                )

            self.decoded_common = component_to_dict(self.battery_info)

            for name, value in iter(self.decoded_common.items()):
                if isinstance(value, float):
                    display_value = float_to_hex(value)
                else:
                    display_value = hex(value) if isinstance(value, int) else value
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}B{self.battery_id}: "
                        f"{name} {display_value} {type(value)}"
                    ),
                )

        except TimeoutError:
            raise DeviceInvalid(
                f"Timeout BatteryInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                f"Error reading BatteryInfo(for_unit({self.inverter_unit_id}),base_offset={self.base_offset}): {e}"
            )

        except ModbusExceptionError:
            raise DeviceInvalid(
                f"Battery I{self.inverter_unit_id}B{self.battery_id}: unsupported address"
            )

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
        try:
            _LOGGER.debug(
                f"Reading component BatteryData(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )
            await self.hub.component_update(self.inverter_unit_id, self.battery_data)

            self.decoded_model = component_to_dict(self.battery_data)

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

        for name, value in iter(self.decoded_model.items()):
            if isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value

            _LOGGER.debug(
                f"I{self.inverter_unit_id}B{self.battery_id}: "
                f"{name} {display_value} {type(value)}"
            )

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
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)

    @property
    def allow_battery_energy_reset(self) -> bool:
        return self.hub.allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        return self.hub.battery_rating_adjust

    @property
    def battery_energy_reset_cycles(self) -> int:
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
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.battery_id = battery_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self._via_device = None

        self.der_storage_capacity_data = DERStorageCapacity(
            self.hub.connection.for_unit(self.inverter_unit_id), der_storage_model
        )

    async def init_device(self) -> None:
        try:
            _LOGGER.debug(
                "Reading component "
                f"DERStorageCapacity(for_unit({self.inverter_unit_id}))"
            )
            await self.hub.component_update(
                self.inverter_unit_id, self.der_storage_capacity_data
            )

            self.decoded_common = component_to_dict(self.der_storage_capacity_data)

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}DERB{self.battery_id}: "
                    f"{name} {value} {type(value)}"
                )

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                "Error reading DERStorageCapacity"
                f"(for_unit({self.inverter_unit_id})): {e}"
            )

        except ModbusExceptionError:
            raise DeviceInvalid(
                f"Battery I{self.inverter_unit_id}DERB{self.battery_id}: "
                "DER Storage Capacity unsupported address"
            )

        except SunSpecError as e:
            raise DeviceInvalid(
                f"Battery I{self.inverter_unit_id}DERB{self.battery_id}: "
                f"DER Storage Capacity model shifted or invalid: {e}"
            )

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
                "Reading component "
                f"DERStorageCapacity(for_unit({self.inverter_unit_id}))"
            )
            await self.hub.component_update(
                self.inverter_unit_id, self.der_storage_capacity_data
            )

            self.decoded_model = component_to_dict(self.der_storage_capacity_data)

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

        for name, value in iter(self.decoded_model.items()):
            _LOGGER.debug(
                f"I{self.inverter_unit_id}DERB{self.battery_id}: "
                f"{name} {value} {type(value)}"
            )

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
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)

    @property
    def allow_battery_energy_reset(self) -> bool:
        return self.hub.allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        return self.hub.battery_rating_adjust

    @property
    def battery_energy_reset_cycles(self) -> int:
        return self.hub.battery_energy_reset_cycles


class SolarEdgeEVSE:
    """Class that defines a SolarEdge EVSE."""

    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.evse_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.has_parent = False

        self.evse_common = EvseCommon(self.hub.connection.for_unit(self.evse_unit_id))

    async def init_device(self) -> None:
        """Set up data about the device from modbus."""

        try:
            _LOGGER.debug(
                f"Reading component EvseCommon(for_unit({self.evse_unit_id}))"
            )
            await self.hub.component_update(self.evse_unit_id, self.evse_common)

            self.decoded_common = component_to_dict(self.evse_common)

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"E{self.evse_unit_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value}"
                        f"{type(value)}"
                    ),
                )

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                f"Error reading evse ID {self.evse_unit_id} at EvseCommon: {e}"
            )

        except ModbusExceptionError:
            raise DeviceInvalid(f"ID {self.evse_unit_id} is not SunSpec.")

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
                f"Reading component EvseCommon(for_unit({self.evse_unit_id}))"
            )
            await self.hub.component_update(self.evse_unit_id, self.evse_common)

            for name, value in iter(self.decoded_model.items()):
                if isinstance(value, float):
                    display_value = float_to_hex(value)
                else:
                    display_value = hex(value) if isinstance(value, int) else value
                _LOGGER.debug(
                    f"E{self.evse_unit_id}: {name} {display_value} {type(value)}"
                )

        except ModbusExceptionError:
            _LOGGER.error(f"E{self.evse_unit_id}: EVSE register(s) NOT available")

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
