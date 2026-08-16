from __future__ import annotations

import asyncio
import importlib.metadata
import logging

from awesomeversion import AwesomeVersion
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

from .components import (
    AdvancedPowerControl,
    BatteryData,
    BatteryInfo,
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

    pass


class HubInitFailed(SolarEdgeException):
    """Raised when an error happens during init"""

    pass


class DeviceInitFailed(SolarEdgeException):
    """Raised when a device can't be initialized"""

    pass


class DeviceIsEVSE(SolarEdgeException):
    """Raised when an inverter device matches a EVSE model"""

    pass


class ModbusReadError(SolarEdgeException):
    """Raised when a modbus read fails (generic)"""

    pass


class ModbusIllegalFunction(SolarEdgeException):
    """Raised when a modbus address is invalid"""

    pass


class ModbusIllegalAddress(SolarEdgeException):
    """Raised when a modbus address is invalid"""

    pass


class ModbusIllegalValue(SolarEdgeException):
    """Raised when a modbus address is invalid"""

    pass


class ModbusIOError(SolarEdgeException):
    """Raised when a modbus IO error occurs"""

    pass


class ModbusWriteError(SolarEdgeException):
    """Raised when a modbus write fails (generic)"""

    pass


class DataUpdateFailed(SolarEdgeException):
    """Raised when an update cycle fails"""

    pass


class DeviceInvalid(SolarEdgeException):
    """Raised when a device is not usable or invalid"""

    pass


class ModbusReadResult:
    """Wraps a modbus-connection register list like pymodbus for compatibility."""

    __slots__ = ("registers",)

    def __init__(self, registers: list[int]) -> None:
        self.registers = registers


async def async_update_with_retry(component) -> None:
    """Call component.async_update(), retrying transient connection/timeout errors.

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
        self._modbus_timeouts_limit = self._yaml_config.get("retry", {}).get(
            "modbus_timeouts", RetrySettings.ModbusTimeouts
        )
        self._id = entry_data[CONF_NAME].lower()
        self.inverters = []
        self.meters = []
        self.batteries = []
        self.evses = []
        self.inverter_common = {}
        self.mmppt_common = {}
        self._write_settle_cycles: dict[int, int] = {}

        self._initalized = False
        self._modbus_timeouts_count = 0

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

            except (ModbusReadError, TimeoutError) as e:
                raise HubInitFailed(f"{e}")

            except DeviceInvalid as e:
                # Inverters are mandatory
                _LOGGER.error(f"Inverter at {self.hub_host} ID {inverter_unit_id}: {e}")
                raise HubInitFailed(f"{e}")

            except DeviceIsEVSE as e:
                _LOGGER.debug(
                    f"Device model matches EVSE at {self.hub_host} ID {inverter_unit_id}: {e}"
                )
                new_evse = SolarEdgeEVSE(inverter_unit_id, self)
                await new_evse.init_device()
                self.evses.append(new_evse)

                # Skip meter and battery detection if DeviceIsEVSE
                continue

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

                    except (ModbusReadError, TimeoutError) as e:
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}M{meter_id}: {e}")
                        pass

            if self._detect_batteries:
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

                    except (ModbusReadError, TimeoutError) as e:
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}B{battery_id}: {e}")
                        pass

        try:
            for inverter in self.inverters:
                await inverter.read_modbus_data()
            for meter in self.meters:
                await meter.read_modbus_data()
            for battery in self.batteries:
                await battery.read_modbus_data()
            for evse in self.evses:
                await evse.read_modbus_data()

        except (ModbusReadError, ModbusIllegalFunction, ModbusIllegalValue) as e:
            raise HubInitFailed(f"Read error: {e}")

        except DeviceInvalid as e:
            raise HubInitFailed(f"Invalid device: {e}")

        except ModbusIOError as e:
            raise HubInitFailed(f"Connection failed: {e}")

        except TimeoutError as e:
            raise HubInitFailed(f"Timeout error: {e}")

        self.initalized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        if not self.initalized:
            try:
                async with asyncio.timeout(self.coordinator_timeout):
                    await self._async_init_solaredge()

            except (ModbusIOError, TimeoutError) as e:
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    "check_configuration",
                    is_fixable=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="check_configuration",
                    data={"entry_id": self._entry_id},
                )
                raise HubInitFailed(f"Setup failed: {e}")

            ir.async_delete_issue(self._hass, DOMAIN, "check_configuration")

            await self.connection.disconnect()

            return True

        try:
            async with asyncio.timeout(self.coordinator_timeout):
                for inverter in self.inverters:
                    await inverter.read_modbus_data()
                for meter in self.meters:
                    await meter.read_modbus_data()
                for battery in self.batteries:
                    await battery.read_modbus_data()
                for evse in self.evses:
                    await evse.read_modbus_data()

        except (ModbusReadError, ModbusIllegalFunction, ModbusIllegalValue) as e:
            await self.connection.disconnect()
            raise DataUpdateFailed(f"Update failed: {e}")

        except DeviceInvalid as e:
            await self.connection.disconnect()
            raise DataUpdateFailed(f"Invalid device: {e}")

        except (ModbusIOError, ModbusConnectionError, ModbusProtocolError) as e:
            await self.connection.disconnect()
            raise DataUpdateFailed(f"Connection failed: {e}")

        except TimeoutError as e:
            await self.connection.disconnect()

            self._modbus_timeouts_count += 1

            _LOGGER.debug(
                f"Refresh timeout {self._modbus_timeouts_count} limit {self._modbus_timeouts_limit}"
            )

            if self._modbus_timeouts_count >= self._modbus_timeouts_limit:
                _LOGGER.warning(
                    f"Modbus connection has timed out "
                    f"{self._modbus_timeouts_limit} times in a row."
                )
                self._modbus_timeouts_count = 0

            raise DataUpdateFailed(f"Timeout error: {e}")

        if self._modbus_timeouts_count > 0:
            _LOGGER.debug(
                f"Modbus timeout count {self._modbus_timeouts_count} limit {self._modbus_timeouts_limit}"
            )
            self._modbus_timeouts_count = 0

        for unit, cycles_remaining in list(self._write_settle_cycles.items()):
            _LOGGER.debug(
                f"Request spaced unit {unit} has {cycles_remaining} until clearing."
            )
            if cycles_remaining <= 1:
                _LOGGER.debug(f"Clearing unit {unit} request spacing.")
                self.connection.for_unit(unit).set_message_spacing(0)
                del self._write_settle_cycles[unit]
            else:
                self._write_settle_cycles[unit] = cycles_remaining - 1

        await self.connection.disconnect()

        return True

    async def modbus_read_holding_registers(self, unit, address, rcount):
        """Read modbus registers from inverter."""

        _LOGGER.debug(
            f"unit={unit}: modbus_read_holding_registers "
            f"address={address} count={rcount}"
        )

        for attempt in range(1, RetrySettings.RequestRetries + 1):
            try:
                registers = await self.connection.for_unit(unit).read_holding_registers(
                    address, rcount
                )
                break

            except ModbusExceptionError as e:
                if e.exception_code == ModbusExceptions.IllegalAddress:
                    _LOGGER.debug(f"unit={unit} Read IllegalAddress: {e}")
                    raise ModbusIllegalAddress(e)

                if e.exception_code == ModbusExceptions.IllegalFunction:
                    _LOGGER.debug(f"unit={unit} Read IllegalFunction: {e}")
                    raise ModbusIllegalFunction(e)

                if e.exception_code == ModbusExceptions.IllegalValue:
                    _LOGGER.debug(f"unit={unit} Read IllegalValue: {e}")
                    raise ModbusIllegalValue(e)

                raise ModbusReadError(e)

            except ModbusTimeoutError:
                if attempt >= RetrySettings.RequestRetries:
                    raise

                _LOGGER.debug(
                    f"unit={unit}: read timeout, attempt {attempt} "
                    f"of {RetrySettings.RequestRetries}"
                )

            except (ModbusConnectionError, ModbusProtocolError) as e:
                if attempt >= RetrySettings.RequestRetries:
                    raise ModbusIOError(e)

                _LOGGER.debug(
                    f"unit={unit}: read error, attempt {attempt} "
                    f"of {RetrySettings.RequestRetries}: {e}"
                )

        _LOGGER.debug(
            f"unit={unit}: Registers received={len(registers)} "
            f"requested={rcount} address={address} "
            f"result={registers}"
        )

        if len(registers) != rcount:
            raise ModbusReadError(
                f"unit={unit}: Registers received != requested : "
                f"{len(registers)} != {rcount} at {address}"
            )

        return ModbusReadResult(registers)

    async def modbus_write_registers(self, unit: int, address: int, payload) -> None:
        """Write modbus registers to inverter."""

        for attempt in range(1, RetrySettings.RequestRetries + 1):
            try:
                await self.connection.for_unit(unit).write_registers(address, payload)
                break

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

                raise ModbusWriteError(e)

            except ModbusTimeoutError as e:
                if attempt >= RetrySettings.RequestRetries:
                    _LOGGER.error(f"Write failed: No response from inverter ID {unit}.")
                    raise HomeAssistantError(
                        f"No response from inverter ID {unit}."
                    ) from e

                _LOGGER.debug(
                    f"unit={unit}: write timeout, attempt {attempt} "
                    f"of {RetrySettings.RequestRetries}"
                )

            except (ModbusConnectionError, ModbusProtocolError) as e:
                if attempt >= RetrySettings.RequestRetries:
                    _LOGGER.error(f"Connection failed: {e}")
                    raise HomeAssistantError(
                        f"Connection to inverter ID {unit} failed."
                    )

                _LOGGER.debug(
                    f"unit={unit}: write error, attempt {attempt} "
                    f"of {RetrySettings.RequestRetries}: {e}"
                )

        if self.sleep_after_write > 0:
            _LOGGER.debug(
                f"Spacing requests to unit {unit} for {self.sleep_after_write} "
                f"seconds after write to address {address}."
            )
            self.connection.for_unit(unit).set_message_spacing(self.sleep_after_write)
            self._write_settle_cycles[unit] = WRITE_SETTLE_CYCLES

        _LOGGER.debug(f"Finished with write {address}.")

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
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 2  # max 2 per inverter
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters

        else:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_meters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_batteries
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
        self.decoded_storage_control = None
        self.has_parent = False
        self.has_battery = None
        self.global_power_control = None
        self.advanced_power_control = None
        self.site_limit_control = None
        self._use_status_vendor4 = False
        self._use_mmppt_units = False

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
            await async_update_with_retry(self.inverter_common)

            self.decoded_common = component_to_dict(self.inverter_common)

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value}"
                        f"{type(value)}"
                    ),
                )

            self.hub.inverter_common[self.inverter_unit_id] = self.decoded_common

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise DeviceInvalid(
                f"Error reading inverter ID {self.inverter_unit_id} at InverterCommon: {e}"
            )

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
            this_ver = AwesomeVersion(self.inverter_common.C_Version)
            self._use_status_vendor4 = this_ver >= AwesomeVersion(
                STATUS_VENDOR4_VERSION
            )
            self._use_mmppt_units = this_ver >= AwesomeVersion(MMPPT_UNITS_VERSION)
        except (AwesomeVersionCompareException, AwesomeVersionStrategyException) as e:
            _LOGGER.error(
                f"Error checking inverter version: {e}. Please report this issue."
            )

        self.inverter_common.restrict_fields(["C_Version"])
        self.inverter_data.restrict_status_vendor4(self._use_status_vendor4)

        is_multi_mppt = False

        if self.use_mmppt_units:
            try:
                _LOGGER.debug(
                    f"Reading component MmpptCommon(for_unit({self.inverter_unit_id}))"
                )
                await async_update_with_retry(self.mmppt_common)

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
                    self.decoded_mmppt = None

                else:
                    _LOGGER.debug(f"I{self.inverter_unit_id} is Multiple MPPT")
                    is_multi_mppt = True

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ) as e:
                raise ModbusReadError(
                    f"Error reading inverter ID {self.inverter_unit_id} at MmpptCommon: {e}"
                )

            except ModbusExceptionError:
                _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")
                self.decoded_mmppt = None
        else:
            _LOGGER.debug(
                f"I{self.inverter_unit_id} is NOT Multiple MPPT "
                "(firmware does not support MMPPT units)"
            )
            self.decoded_mmppt = None

        self.hub.mmppt_common[self.inverter_unit_id] = self.decoded_mmppt

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
            await async_update_with_retry(self.inverter_common)

            _LOGGER.debug(
                f"Reading component InverterData(for_unit({self.inverter_unit_id}))"
            )
            await async_update_with_retry(self.inverter_data)

            self.decoded_model = component_to_dict(self.inverter_data)

            if (
                self.inverter_data.C_SunSpec_DID == SunSpecNotImpl.UINT16
                or self.inverter_data.C_SunSpec_DID not in [101, 102, 103]
                or self.inverter_data.C_SunSpec_Length != 50
            ):
                raise DeviceInvalid(f"Inverter {self.inverter_unit_id} not usable.")

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise ModbusReadError(
                f"Error reading inverter ID {self.inverter_unit_id} at InverterData: {e}"
            )

        """ Multiple MPPT Extension """
        if self.use_mmppt_units and self.decoded_mmppt is not None:
            try:
                _LOGGER.debug(
                    f"Reading component MmpptData(for_unit({self.inverter_unit_id}))"
                )
                await async_update_with_retry(self.mmppt_data)

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

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ) as e:
                raise ModbusReadError(
                    f"Error reading inverter ID {self.inverter_unit_id} at MmpptData: {e}"
                )

        """ Global Dynamic Power Control and Status """
        if self.hub.option_detect_extras is True and (
            self.global_power_control is True or self.global_power_control is None
        ):
            try:
                _LOGGER.debug(
                    f"Reading component GlobalDynamicPowerControl(for_unit({self.inverter_unit_id}))"
                )
                await async_update_with_retry(self.global_power_control_data)

                self.decoded_model.update(
                    component_to_dict(self.global_power_control_data)
                )

                self.global_power_control = True

            except ModbusExceptionError:
                self.global_power_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: global power control NOT available"
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
                TimeoutError,
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
        if self.hub.option_detect_extras is True and (
            self.advanced_power_control is True or self.advanced_power_control is None
        ):
            try:
                _LOGGER.debug(
                    "Reading component "
                    f"AdvancedPowerControl(for_unit({self.inverter_unit_id}))"
                )
                await async_update_with_retry(self.advanced_power_control_data)

                self.decoded_model.update(
                    component_to_dict(self.advanced_power_control_data)
                )

                self.advanced_power_control = True

            except ModbusExceptionError:
                self.advanced_power_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: advanced power control NOT available"
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
                TimeoutError,
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
        if (
            self.hub.option_site_limit_control is True
            and self.site_limit_control is not False
        ):
            try:
                _LOGGER.debug(
                    "Reading component "
                    f"SiteLimitControl(for_unit({self.inverter_unit_id}))"
                )
                await async_update_with_retry(self.site_limit_control_data)

                self.decoded_model.update(
                    component_to_dict(self.site_limit_control_data)
                )

                self.site_limit_control = True

            except ModbusExceptionError:
                # Assumes Ext_Prod_Max fails together with the rest of this
                # block rather than independently; if a device turns out to
                # reject it alone, revisit with per-field handling.
                self.site_limit_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: site limit control NOT available"
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ) as e:
                raise ModbusReadError(
                    f"Error reading inverter ID {self.inverter_unit_id} "
                    f"at SiteLimitControl: {e}"
                )

        for name, value in iter(self.decoded_model.items()):
            if isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value
            _LOGGER.debug(
                f"I{self.inverter_unit_id}: {name} {display_value} {type(value)}"
            )

        """ Power Control Options: Storage Control """
        if (
            self.hub.option_storage_control is True
            and self.decoded_storage_control is not False
        ):
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
                await async_update_with_retry(self.storage_control_data)

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
                self.decoded_storage_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: storage control NOT available"
                )

            except (
                ModbusConnectionError,
                ModbusProtocolError,
                ModbusTimeoutError,
            ) as e:
                raise ModbusReadError(
                    f"Error reading inverter ID {self.inverter_unit_id} "
                    f"at StorageControl: {e}"
                )

    async def write_registers(self, address, payload) -> None:
        """Write inverter register."""
        await self.hub.modbus_write_registers(self.inverter_unit_id, address, payload)

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
        if self.decoded_mmppt is None:
            return False

        return True

    @property
    def use_status_vendor4(self) -> bool:
        return self._use_status_vendor4

    @property
    def use_mmppt_units(self) -> bool:
        return self._use_mmppt_units


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
        return self.inverter.decoded_model[self.mmppt_key]["ID"]

    @property
    def mmppt_idstr(self) -> str:
        return self.inverter.decoded_model[self.mmppt_key]["IDStr"]


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
            if self.mmppt_common["mmppt_Units"] == 2:
                self.start_address = self.start_address + 50
            elif self.mmppt_common["mmppt_Units"] == 3:
                self.start_address = self.start_address + 70
            else:
                raise DeviceInvalid(
                    f"Invalid mmppt_Units value {self.mmppt_common['mmppt_Units']}"
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
            await async_update_with_retry(self.meter_info)

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

        inverter_model = self.inverter_common["C_Model"]
        inerter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inerter_serial}_M{self.meter_id}"

    async def read_modbus_data(self) -> None:
        try:
            _LOGGER.debug(
                f"Reading component MeterData(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )
            await async_update_with_retry(self.meter_data)

            self.decoded_model = component_to_dict(self.meter_data)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise ModbusReadError(
                f"Error reading inverter ID {self.inverter_unit_id} at MeterData: {e}"
            )

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
            await async_update_with_retry(self.battery_info)

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

        inverter_model = self.inverter_common["C_Model"]
        inerter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inerter_serial}_B{self.battery_id}"

    async def read_modbus_data(self) -> None:
        try:
            _LOGGER.debug(
                f"Reading component BatteryData(for_unit({self.inverter_unit_id}),base_offset={self.base_offset})"
            )
            await async_update_with_retry(self.battery_data)

            self.decoded_model = component_to_dict(self.battery_data)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise ModbusReadError(
                f"Error reading inverter ID {self.inverter_unit_id} at BatteryData: {e}"
            )

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
            await async_update_with_retry(self.evse_common)

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

        self.evse_common.restrict_fields(["C_Version"])

    async def read_modbus_data(self) -> None:
        """Read and update dynamic modbus registers."""

        try:
            _LOGGER.debug(
                f"Reading component EvseCommon(for_unit({self.evse_unit_id}))"
            )
            await async_update_with_retry(self.evse_common)

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

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:
            raise ModbusReadError(
                f"Error reading evse ID {self.evse_unit_id} at EvseCommon: {e}"
            )

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
