from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import DeviceInfo

try:
    from pymodbus.client import AsyncModbusTcpClient
    from pymodbus.constants import Endian
    from pymodbus.exceptions import ConnectionException, ModbusIOException
    from pymodbus.payload import BinaryPayloadDecoder
    from pymodbus.pdu import ExceptionResponse, ModbusExceptions
except ImportError:
    raise ImportError("pymodbus is not installed, or pymodbus version is not supported")

from .const import DOMAIN, ModbusDefaults, SolarEdgeTimeouts, SunSpecNotImpl
from .helpers import float_to_hex, parse_modbus_string

_LOGGER = logging.getLogger(__name__)


class SolarEdgeException(Exception):
    """Base class for other exceptions"""

    pass


class HubInitFailed(SolarEdgeException):
    """Raised when an error happens during init"""

    pass


class DeviceInitFailed(SolarEdgeException):
    """Raised when a device can't be initialized"""

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


class SolarEdgeModbusMultiHub:
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        name: str,
        host: str,
        port: int,
        number_of_inverters: int = 1,
        start_device_id: int = 1,
        detect_meters: bool = True,
        detect_batteries: bool = False,
        detect_extras: bool = True,
        keep_modbus_open: bool = False,
        adv_storage_control: bool = False,
        adv_site_limit_control: bool = False,
        allow_battery_energy_reset: bool = False,
        sleep_after_write: int = 3,
        battery_rating_adjust: int = 0,
        battery_energy_reset_cycles: int = 0,
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._name = name
        self._host = host
        self._port = port
        self._entry_id = entry_id
        self._number_of_inverters = number_of_inverters
        self._start_device_id = start_device_id
        self._detect_meters = detect_meters
        self._detect_batteries = detect_batteries
        self._detect_extras = detect_extras
        self._keep_modbus_open = keep_modbus_open
        self._adv_storage_control = adv_storage_control
        self._adv_site_limit_control = adv_site_limit_control
        self._allow_battery_energy_reset = allow_battery_energy_reset
        self._sleep_after_write = sleep_after_write
        self._battery_rating_adjust = battery_rating_adjust
        self._battery_energy_reset_cycles = battery_energy_reset_cycles

        self._id = name.lower()
        self._lock = asyncio.Lock()
        self.inverters = []
        self.meters = []
        self.batteries = []
        self.inverter_common = {}
        self.mmppt_common = {}
        self.has_write = None

        self._initalized = False
        self._online = True

        self._client = None

        _LOGGER.debug(
            (
                f"{DOMAIN} configuration: "
                f"number_of_inverters={self._number_of_inverters}, "
                f"start_device_id={self._start_device_id}, "
                f"detect_meters={self._detect_meters}, "
                f"detect_batteries={self._detect_batteries}, "
                f"detect_extras={self._detect_extras}, "
                f"keep_modbus_open={self._keep_modbus_open}, "
                f"adv_storage_control={self._adv_storage_control}, "
                f"adv_site_limit_control={self._adv_site_limit_control}, "
                f"allow_battery_energy_reset={self._allow_battery_energy_reset}, "
                f"sleep_after_write={self._sleep_after_write}, "
                f"battery_rating_adjust={self._battery_rating_adjust}, "
            ),
        )

    async def _async_init_solaredge(self) -> None:
        """Detect devices and load initial modbus data from inverters."""

        if not self.is_connected:
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
                f"Modbus/TCP connect to {self.hub_host}:{self.hub_port} failed."
            )

        if self.option_storage_control:
            _LOGGER.warning(
                (
                    "Power Control Options: Storage Control is enabled. "
                    "Use at your own risk!"
                ),
            )

        if self.option_site_limit_control:
            _LOGGER.warning(
                (
                    "Power Control Options: Site Limit Control is enabled. "
                    "Use at your own risk!"
                ),
            )

        for inverter_index in range(self._number_of_inverters):
            inverter_unit_id = inverter_index + self._start_device_id

            try:
                new_inverter = SolarEdgeInverter(inverter_unit_id, self)
                await new_inverter.init_device()
                self.inverters.append(new_inverter)

            except ModbusReadError as e:
                self.disconnect()
                raise HubInitFailed(f"{e}")

            except DeviceInvalid as e:
                # Inverters are mandatory
                _LOGGER.error(f"Inverter at {self.hub_host} ID {inverter_unit_id}: {e}")
                raise HubInitFailed(f"{e}")

            if self._detect_meters:
                try:
                    new_meter_1 = SolarEdgeMeter(inverter_unit_id, 1, self)
                    await new_meter_1.init_device()

                    for meter in self.meters:
                        if new_meter_1.serial == meter.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_meter_1.serial} "
                                    f"on meter 1 inverter {inverter_unit_id}"
                                ),
                            )

                    new_meter_1.via_device = new_inverter.uid_base
                    self.meters.append(new_meter_1)
                    _LOGGER.debug(f"Found meter 1 on inverter ID {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid as e:
                    _LOGGER.debug(f"I{inverter_unit_id}M1: {e}")
                    pass

                try:
                    new_meter_2 = SolarEdgeMeter(inverter_unit_id, 2, self)
                    await new_meter_2.init_device()

                    for meter in self.meters:
                        if new_meter_2.serial == meter.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_meter_2.serial} "
                                    f"on meter 2 inverter {inverter_unit_id}"
                                ),
                            )

                    new_meter_2.via_device = new_inverter.uid_base
                    self.meters.append(new_meter_2)
                    _LOGGER.debug(f"Found meter 2 on inverter ID {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid as e:
                    _LOGGER.debug(f"I{inverter_unit_id}M2: {e}")
                    pass

                try:
                    new_meter_3 = SolarEdgeMeter(inverter_unit_id, 3, self)
                    await new_meter_3.init_device()

                    for meter in self.meters:
                        if new_meter_3.serial == meter.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_meter_3.serial} "
                                    f"on meter 3 inverter {inverter_unit_id}"
                                ),
                            )

                    new_meter_3.via_device = new_inverter.uid_base
                    self.meters.append(new_meter_3)
                    _LOGGER.debug(f"Found meter 3 on inverter ID {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid as e:
                    _LOGGER.debug(f"I{inverter_unit_id}M3: {e}")
                    pass

            if self._detect_batteries:
                try:
                    new_battery_1 = SolarEdgeBattery(inverter_unit_id, 1, self)
                    await new_battery_1.init_device()

                    for battery in self.batteries:
                        if new_battery_1.serial == battery.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_battery_1.serial} "
                                    f"on battery 1 inverter {inverter_unit_id}"
                                ),
                            )
                            raise DeviceInvalid(
                                f"Duplicate b1 serial {new_battery_1.serial}"
                            )

                    new_battery_1.via_device = new_inverter.uid_base
                    self.batteries.append(new_battery_1)
                    _LOGGER.debug(f"Found battery 1 inverter {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid as e:
                    _LOGGER.debug(f"I{inverter_unit_id}B1: {e}")
                    pass

                try:
                    new_battery_2 = SolarEdgeBattery(inverter_unit_id, 2, self)
                    await new_battery_2.init_device()

                    for battery in self.batteries:
                        if new_battery_2.serial == battery.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_battery_2.serial} "
                                    f"on battery 2 inverter {inverter_unit_id}"
                                ),
                            )
                            raise DeviceInvalid(
                                f"Duplicate b2 serial {new_battery_2.serial}"
                            )

                    new_battery_2.via_device = new_inverter.uid_base
                    self.batteries.append(new_battery_2)
                    _LOGGER.debug(f"Found battery 2 inverter {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid as e:
                    _LOGGER.debug(f"I{inverter_unit_id}B2: {e}")
                    pass

        try:
            for inverter in self.inverters:
                await inverter.read_modbus_data()

            for meter in self.meters:
                await meter.read_modbus_data()

            for battery in self.batteries:
                await battery.read_modbus_data()

        except ModbusReadError as e:
            self.disconnect()
            raise HubInitFailed(f"Read error: {e}")

        except DeviceInvalid as e:
            self.disconnect()
            raise HubInitFailed(f"Invalid device: {e}")

        except ConnectionException as e:
            self.disconnect()
            raise HubInitFailed(f"Connection failed: {e}")

        except ModbusIOException as e:
            self.disconnect()
            raise HubInitFailed(f"Modbus error: {e}")

        self.initalized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        if not self.is_connected:
            await self.connect()

        if not self.initalized:
            try:
                async with self._lock:
                    await self._async_init_solaredge()

            except ConnectionException as e:
                self.disconnect()
                raise HubInitFailed(f"Setup failed: {e}")

            return True

        if not self.is_connected:
            self.online = False
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                "check_configuration",
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="check_configuration",
                data={"entry_id": self._entry_id},
            )
            raise DataUpdateFailed(
                f"Modbus/TCP connect to {self.hub_host}:{self.hub_port} failed."
            )

        else:
            if not self.online:
                ir.async_delete_issue(self._hass, DOMAIN, "check_configuration")
            self.online = True

            try:
                async with self._lock:
                    for inverter in self.inverters:
                        await inverter.read_modbus_data()
                    for meter in self.meters:
                        await meter.read_modbus_data()
                    for battery in self.batteries:
                        await battery.read_modbus_data()

            except ModbusReadError as e:
                self.disconnect()
                raise DataUpdateFailed(f"Update failed: {e}")

            except DeviceInvalid as e:
                if not self._keep_modbus_open:
                    self.disconnect()
                raise DataUpdateFailed(f"Invalid device: {e}")

            except ConnectionException as e:
                self.disconnect()
                raise DataUpdateFailed(f"Connection failed: {e}")

            except ModbusIOException as e:
                self.disconnect()
                raise DataUpdateFailed(f"Modbus error: {e}")

        if not self._keep_modbus_open:
            self.disconnect()

        return True

    async def connect(self) -> None:
        """Connect to inverter."""

        if self._client is None:
            self._client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                reconnect_delay=ModbusDefaults.ReconnectDelay,
                reconnect_delay_max=ModbusDefaults.ReconnectDelayMax,
                timeout=ModbusDefaults.Timeout,
            )

        await self._client.connect()

    def disconnect(self) -> None:
        """Disconnect from inverter."""

        if self._client is not None:
            self._client.close()

    async def shutdown(self) -> None:
        """Shut down the hub and disconnect."""
        async with self._lock:
            self.online = False
            self.disconnect()
            self._client = None

    async def modbus_read_holding_registers(self, unit, address, rcount):
        """Read modbus registers from inverter."""

        self._rr_unit = unit
        self._rr_address = address
        self._rr_count = rcount

        kwargs = {"slave": self._rr_unit} if self._rr_unit else {}

        result = await self._client.read_holding_registers(
            self._rr_address, self._rr_count, **kwargs
        )

        if result.isError():
            _LOGGER.debug(f"Unit {unit}: {result}")

            if type(result) is ModbusIOException:
                raise ModbusIOError(result)

            if type(result) is ExceptionResponse:
                if result.exception_code == ModbusExceptions.IllegalAddress:
                    raise ModbusIllegalAddress(result)

                if result.exception_code == ModbusExceptions.IllegalFunction:
                    raise ModbusIllegalFunction(result)

                if result.exception_code == ModbusExceptions.IllegalValue:
                    raise ModbusIllegalValue(result)

            raise ModbusReadError(result)

        _LOGGER.debug(
            f"Registers received requested : {len(result.registers)} {self._rr_count}"
        )

        if len(result.registers) != rcount:
            _LOGGER.error(
                "Registers received != requested : "
                f"{len(result.registers)} != {self._rr_count}"
            )
            raise ModbusReadError(
                f"Registers received != requested on inverter ID {self._rr_count}"
            )

        return result

    async def write_registers(self, unit: int, address: int, payload) -> None:
        """Write modbus registers to inverter."""

        self._wr_unit = unit
        self._wr_address = address
        self._wr_payload = payload

        try:
            async with self._lock:
                if not self.is_connected:
                    await self.connect()

                kwargs = {"slave": self._wr_unit} if self._wr_unit else {}
                result = await self._client.write_registers(
                    self._wr_address, self._wr_payload, **kwargs
                )

                self.has_write = address

                if self.sleep_after_write > 0:
                    _LOGGER.debug(
                        f"Sleep {self.sleep_after_write} seconds after write {address}."
                    )
                    await asyncio.sleep(self.sleep_after_write)

                self.has_write = None
                _LOGGER.debug(f"Finished with write {address}.")

        except ModbusIOException as e:
            self.disconnect()

            raise HomeAssistantError(
                f"Error sending command to inverter ID {self._wr_unit}: {e}."
            )

        except ConnectionException as e:
            self.disconnect()

            _LOGGER.error(f"Connection failed: {e}")
            raise HomeAssistantError(
                f"Connection to inverter ID {self._wr_unit} failed."
            )

        if result.isError():
            if type(result) is ModbusIOException:
                self.disconnect()
                _LOGGER.error(
                    f"Write failed: No response from inverter ID {self._wr_unit}."
                )
                raise HomeAssistantError(
                    "No response from inverter ID {self._wr_unit}."
                )

            if type(result) is ExceptionResponse:
                if result.exception_code == ModbusExceptions.IllegalAddress:
                    _LOGGER.debug(f"Write IllegalAddress: {result}")
                    raise HomeAssistantError(
                        "Address not supported at device at ID {self._wr_unit}."
                    )

                if result.exception_code == ModbusExceptions.IllegalFunction:
                    _LOGGER.debug(f"Write IllegalFunction: {result}")
                    raise HomeAssistantError(
                        "Function not supported by device at ID {self._wr_unit}."
                    )

                if result.exception_code == ModbusExceptions.IllegalValue:
                    _LOGGER.debug(f"Write IllegalValue: {result}")
                    raise HomeAssistantError(
                        "Value invalid for device at ID {self._wr_unit}."
                    )

            self.disconnect()
            raise ModbusWriteError(result)

    @property
    def online(self):
        return self._online

    @online.setter
    def online(self, value: bool) -> None:
        if value is True:
            self._online = True
        else:
            self._online = False

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
    def keep_modbus_open(self) -> bool:
        return self._keep_modbus_open

    @keep_modbus_open.setter
    def keep_modbus_open(self, value: bool) -> None:
        if value is True:
            self._keep_modbus_open = True
        else:
            self._keep_modbus_open = False

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
        return self._number_of_inverters

    @keep_modbus_open.setter
    def keep_modbus_open(self, value: bool) -> None:
        if value is True:
            self._keep_modbus_open = True
        else:
            self._keep_modbus_open = False

        _LOGGER.debug(f"keep_modbus_open={self._keep_modbus_open}")

    @property
    def sleep_after_write(self) -> int:
        return self._sleep_after_write

    @property
    def coordinator_timeout(self) -> int:
        if not self.initalized:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Init * self.number_of_inverters
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 3  # max 3 per inverter
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 2  # max 2 per inverter

        else:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_meters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_batteries

        this_timeout = this_timeout / 1000

        _LOGGER.debug(f"coordinator timeout is {this_timeout}")
        return this_timeout

    @property
    def is_connected(self) -> bool:
        """Check modbus client connection status."""
        if self._client is None:
            return False

        return self._client.connected


class SolarEdgeInverter:
    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = []
        self.decoded_model = []
        self.decoded_mmppt = []
        self.decoded_storage_control = None
        self.has_parent = False
        self.has_battery = None
        self.global_power_control = None
        self.advanced_power_control = None
        self.site_limit_control = None

    async def init_device(self) -> None:
        try:
            inverter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40000, rcount=69
            )

            decoder = BinaryPayloadDecoder.fromRegisters(
                inverter_data.registers, byteorder=Endian.BIG
            )

            self.decoded_common = OrderedDict(
                [
                    ("C_SunSpec_ID", decoder.decode_32bit_uint()),
                    ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                    ("C_SunSpec_Length", decoder.decode_16bit_uint()),
                    (
                        "C_Manufacturer",
                        parse_modbus_string(decoder.decode_string(32)),
                    ),
                    ("C_Model", parse_modbus_string(decoder.decode_string(32))),
                    ("C_Option", parse_modbus_string(decoder.decode_string(16))),
                    ("C_Version", parse_modbus_string(decoder.decode_string(16))),
                    (
                        "C_SerialNumber",
                        parse_modbus_string(decoder.decode_string(32)),
                    ),
                    ("C_Device_address", decoder.decode_16bit_uint()),
                ]
            )

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value}"
                        f"{type(value)}"
                    ),
                )

            self.hub.inverter_common[self.inverter_unit_id] = self.decoded_common

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            )

        if (
            self.decoded_common["C_SunSpec_ID"] == SunSpecNotImpl.UINT32
            or self.decoded_common["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_common["C_SunSpec_ID"] != 0x53756E53
            or self.decoded_common["C_SunSpec_DID"] != 0x0001
            or self.decoded_common["C_SunSpec_Length"] != 65
        ):
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            )

        try:
            mmppt_common = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40121, rcount=9
            )

            decoder = BinaryPayloadDecoder.fromRegisters(
                mmppt_common.registers, byteorder=Endian.BIG
            )

            self.decoded_mmppt = OrderedDict(
                [
                    ("mmppt_DID", decoder.decode_16bit_uint()),
                    ("mmppt_Length", decoder.decode_16bit_uint()),
                    ("ignore", decoder.skip_bytes(12)),
                    ("mmppt_Units", decoder.decode_16bit_uint()),
                ]
            )

            try:
                del self.decoded_mmppt["ignore"]
            except KeyError:
                pass

            for name, value in iter(self.decoded_mmppt.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id} MMPPT: "
                        f"{name} {hex(value) if isinstance(value, int) else value} "
                        f"{type(value)}"
                    ),
                )

            if (
                self.decoded_mmppt["mmppt_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_mmppt["mmppt_Units"] == SunSpecNotImpl.UINT16
                or self.decoded_mmppt["mmppt_DID"] not in [160]
                or self.decoded_mmppt["mmppt_Units"] not in [2, 3]
            ):
                _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")
                self.decoded_mmppt = None

            else:
                _LOGGER.debug(f"I{self.inverter_unit_id} is Multiple MPPT")

        except ModbusIOError:
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
            )

        except ModbusIllegalAddress:
            _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")
            self.decoded_mmppt = None

        self.hub.mmppt_common[self.inverter_unit_id] = self.decoded_mmppt

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.fw_version = self.decoded_common["C_Version"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id}"
        self.uid_base = f"{self.model}_{self.serial}"

    async def read_modbus_data(self) -> None:
        try:
            inverter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40069, rcount=40
            )

            decoder = BinaryPayloadDecoder.fromRegisters(
                inverter_data.registers, byteorder=Endian.BIG
            )

            self.decoded_model = OrderedDict(
                [
                    ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                    ("C_SunSpec_Length", decoder.decode_16bit_uint()),
                    ("AC_Current", decoder.decode_16bit_uint()),
                    ("AC_Current_A", decoder.decode_16bit_uint()),
                    ("AC_Current_B", decoder.decode_16bit_uint()),
                    ("AC_Current_C", decoder.decode_16bit_uint()),
                    ("AC_Current_SF", decoder.decode_16bit_int()),
                    ("AC_Voltage_AB", decoder.decode_16bit_uint()),
                    ("AC_Voltage_BC", decoder.decode_16bit_uint()),
                    ("AC_Voltage_CA", decoder.decode_16bit_uint()),
                    ("AC_Voltage_AN", decoder.decode_16bit_uint()),
                    ("AC_Voltage_BN", decoder.decode_16bit_uint()),
                    ("AC_Voltage_CN", decoder.decode_16bit_uint()),
                    ("AC_Voltage_SF", decoder.decode_16bit_int()),
                    ("AC_Power", decoder.decode_16bit_int()),
                    ("AC_Power_SF", decoder.decode_16bit_int()),
                    ("AC_Frequency", decoder.decode_16bit_uint()),
                    ("AC_Frequency_SF", decoder.decode_16bit_int()),
                    ("AC_VA", decoder.decode_16bit_int()),
                    ("AC_VA_SF", decoder.decode_16bit_int()),
                    ("AC_var", decoder.decode_16bit_int()),
                    ("AC_var_SF", decoder.decode_16bit_int()),
                    ("AC_PF", decoder.decode_16bit_int()),
                    ("AC_PF_SF", decoder.decode_16bit_int()),
                    ("AC_Energy_WH", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_SF", decoder.decode_16bit_uint()),
                    ("I_DC_Current", decoder.decode_16bit_uint()),
                    ("I_DC_Current_SF", decoder.decode_16bit_int()),
                    ("I_DC_Voltage", decoder.decode_16bit_uint()),
                    ("I_DC_Voltage_SF", decoder.decode_16bit_int()),
                    ("I_DC_Power", decoder.decode_16bit_int()),
                    ("I_DC_Power_SF", decoder.decode_16bit_int()),
                    ("I_Temp_Cab", decoder.decode_16bit_int()),
                    ("I_Temp_Sink", decoder.decode_16bit_int()),
                    ("I_Temp_Trns", decoder.decode_16bit_int()),
                    ("I_Temp_Other", decoder.decode_16bit_int()),
                    ("I_Temp_SF", decoder.decode_16bit_int()),
                    ("I_Status", decoder.decode_16bit_int()),
                    ("I_Status_Vendor", decoder.decode_16bit_int()),
                ]
            )

            if (
                self.decoded_model["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_model["C_SunSpec_DID"] not in [101, 102, 103]
                or self.decoded_model["C_SunSpec_Length"] != 50
            ):
                raise DeviceInvalid(f"Inverter {self.inverter_unit_id} not usable.")

        except ModbusIOError:
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
            )

        """ Multiple MPPT Extension """
        if self.decoded_mmppt is not None:
            if self.decoded_mmppt["mmppt_Units"] == 2:
                mmppt_registers = 48

            elif self.decoded_mmppt["mmppt_Units"] == 3:
                mmppt_registers = 68

            else:
                self.decoded_mmppt = None
                raise DeviceInvalid(
                    f"Inverter {self.inverter_unit_id} MMPPT must be 2 or 3 units"
                )

            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=40123, rcount=mmppt_registers
                )

                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers, byteorder=Endian.BIG
                )

                if self.decoded_mmppt["mmppt_Units"] in [2, 3]:
                    self.decoded_model.update(
                        OrderedDict(
                            [
                                ("mmppt_DCA_SF", decoder.decode_16bit_int()),
                                ("mmppt_DCV_SF", decoder.decode_16bit_int()),
                                ("mmppt_DCW_SF", decoder.decode_16bit_int()),
                                ("mmppt_DCWH_SF", decoder.decode_16bit_int()),
                                ("mmppt_Events", decoder.decode_32bit_uint()),
                                ("ignore", decoder.skip_bytes(2)),
                                ("mmppt_TmsPer", decoder.decode_16bit_uint()),
                                ("mmppt_0_ID", decoder.decode_16bit_uint()),
                                (
                                    "mmppt_0_IDStr",
                                    parse_modbus_string(decoder.decode_string(16)),
                                ),
                                ("mmppt_0_DCA", decoder.decode_16bit_uint()),
                                ("mmppt_0_DCV", decoder.decode_16bit_uint()),
                                ("mmppt_0_DCW", decoder.decode_16bit_uint()),
                                ("mmppt_0_DCWH", decoder.decode_32bit_uint()),
                                ("mmppt_0_Tms", decoder.decode_32bit_uint()),
                                ("mmppt_0_Tmp", decoder.decode_16bit_int()),
                                ("mmppt_0_DCSt", decoder.decode_16bit_uint()),
                                ("mmppt_0_DCEvt", decoder.decode_32bit_uint()),
                                ("mmppt_1_ID", decoder.decode_16bit_uint()),
                                (
                                    "mmppt_1_IDStr",
                                    parse_modbus_string(decoder.decode_string(16)),
                                ),
                                ("mmppt_1_DCA", decoder.decode_16bit_uint()),
                                ("mmppt_1_DCV", decoder.decode_16bit_uint()),
                                ("mmppt_1_DCW", decoder.decode_16bit_uint()),
                                ("mmppt_1_DCWH", decoder.decode_32bit_uint()),
                                ("mmppt_1_Tms", decoder.decode_32bit_uint()),
                                ("mmppt_1_Tmp", decoder.decode_16bit_int()),
                                ("mmppt_1_DCSt", decoder.decode_16bit_uint()),
                                ("mmppt_1_DCEvt", decoder.decode_32bit_uint()),
                            ]
                        )
                    )

                if self.decoded_mmppt["mmppt_Units"] in [3]:
                    self.decoded_model.update(
                        OrderedDict(
                            [
                                ("mmppt_2_ID", decoder.decode_16bit_uint()),
                                (
                                    "mmppt_2_IDStr",
                                    parse_modbus_string(decoder.decode_string(16)),
                                ),
                                ("mmppt_2_DCA", decoder.decode_16bit_uint()),
                                ("mmppt_2_DCV", decoder.decode_16bit_uint()),
                                ("mmppt_2_DCW", decoder.decode_16bit_uint()),
                                ("mmppt_2_DCWH", decoder.decode_32bit_uint()),
                                ("mmppt_2_Tms", decoder.decode_32bit_uint()),
                                ("mmppt_2_Tmp", decoder.decode_16bit_int()),
                                ("mmppt_2_DCSt", decoder.decode_16bit_uint()),
                                ("mmppt_2_DCEvt", decoder.decode_32bit_uint()),
                            ]
                        )
                    )

                try:
                    del self.decoded_model["ignore"]
                except KeyError:
                    pass

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

        """ Global Dynamic Power Control and Status """
        if self.hub.option_detect_extras is True and (
            self.global_power_control is True or self.global_power_control is None
        ):
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=61440, rcount=4
                )

                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE,
                )

                self.decoded_model.update(
                    OrderedDict(
                        [
                            ("I_RRCR", decoder.decode_16bit_uint()),
                            ("I_Power_Limit", decoder.decode_16bit_uint()),
                            ("I_CosPhi", decoder.decode_32bit_float()),
                        ]
                    )
                )
                self.global_power_control = True

            except ModbusIllegalAddress:
                self.global_power_control = False
                _LOGGER.debug(
                    (f"I{self.inverter_unit_id}: " "global power control NOT available")
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

        """ Advanced Power Control """
        if self.hub.option_detect_extras is True and (
            self.advanced_power_control is True or self.advanced_power_control is None
        ):
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=61762, rcount=2
                )

                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE,
                )

                self.decoded_model.update(
                    OrderedDict(
                        [
                            ("I_AdvPwrCtrlEn", decoder.decode_32bit_int()),
                        ]
                    )
                )
                self.advanced_power_control = True

            except ModbusIllegalAddress:
                self.advanced_power_control = False
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}: "
                        "advanced power control NOT available"
                    )
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

        """ Power Control Options: Site Limit Control """
        if (
            self.hub.option_site_limit_control is True
            and self.site_limit_control is not False
        ):
            """Site Limit and Mode"""
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57344, rcount=4
                )

                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE,
                )

                self.decoded_model.update(
                    OrderedDict(
                        [
                            ("E_Lim_Ctl_Mode", decoder.decode_16bit_uint()),
                            ("E_Lim_Ctl", decoder.decode_16bit_uint()),
                            ("E_Site_Limit", decoder.decode_32bit_float()),
                        ]
                    )
                )

                self.site_limit_control = True

            except ModbusIllegalAddress:
                self.site_limit_control = False
                _LOGGER.debug(
                    (f"I{self.inverter_unit_id}: " "site limit control NOT available")
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

            """ External Production Max Power """
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57362, rcount=2
                )

                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE,
                )

                self.decoded_model.update(
                    OrderedDict(
                        [
                            ("Ext_Prod_Max", decoder.decode_32bit_float()),
                        ]
                    )
                )

            except ModbusIllegalAddress:
                try:
                    del self.decoded_model["Ext_Prod_Max"]
                except KeyError:
                    pass

                _LOGGER.debug((f"I{self.inverter_unit_id}: Ext_Prod_Max NOT available"))

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

        for name, value in iter(self.decoded_model.items()):
            if isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value
            _LOGGER.debug(
                f"I{self.inverter_unit_id}: " f"{name} {display_value} {type(value)}"
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
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57348, rcount=14
                )

                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE,
                )

                self.decoded_storage_control = OrderedDict(
                    [
                        ("control_mode", decoder.decode_16bit_uint()),
                        ("ac_charge_policy", decoder.decode_16bit_uint()),
                        ("ac_charge_limit", decoder.decode_32bit_float()),
                        ("backup_reserve", decoder.decode_32bit_float()),
                        ("default_mode", decoder.decode_16bit_uint()),
                        ("command_timeout", decoder.decode_32bit_uint()),
                        ("command_mode", decoder.decode_16bit_uint()),
                        ("charge_limit", decoder.decode_32bit_float()),
                        ("discharge_limit", decoder.decode_32bit_float()),
                    ]
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

            except ModbusIllegalAddress:
                self.decoded_storage_control = False
                _LOGGER.debug(
                    (f"I{self.inverter_unit_id}: " "storage control NOT available")
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

    async def write_registers(self, address, payload) -> None:
        """Write inverter register."""
        await self.hub.write_registers(self.inverter_unit_id, address, payload)

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            sw_version=self.fw_version,
            hw_version=self.option,
        )

    @property
    def is_mmppt(self) -> bool:
        if self.decoded_mmppt is None:
            return False

        return True


class SolarEdgeMeter:
    def __init__(
        self, device_id: int, meter_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = []
        self.decoded_model = []
        self.start_address = 40000
        self.meter_id = meter_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self.mmppt_common = self.hub.mmppt_common[self.inverter_unit_id]
        self._via_device = None

        if self.meter_id == 1:
            self.start_address = self.start_address + 121
        elif self.meter_id == 2:
            self.start_address = self.start_address + 295
        elif self.meter_id == 3:
            self.start_address = self.start_address + 469
        else:
            raise ValueError(f"Invalid meter_id {self.meter_id}")

        if self.mmppt_common is not None:
            if self.mmppt_common["mmppt_Units"] == 2:
                self.start_address = self.start_address + 50

            elif self.mmppt_common["mmppt_Units"] == 3:
                self.start_address = self.start_address + 70

            else:
                raise ValueError(
                    f"Invalid mmppt_Units value {self.mmppt_common['mmppt_Units']}"
                )

    async def init_device(self) -> None:
        try:
            meter_info = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id,
                address=self.start_address,
                rcount=67,
            )
            if meter_info.isError():
                _LOGGER.debug(meter_info)
                raise ModbusReadError(meter_info)

            decoder = BinaryPayloadDecoder.fromRegisters(
                meter_info.registers, byteorder=Endian.BIG
            )
            self.decoded_common = OrderedDict(
                [
                    ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                    ("C_SunSpec_Length", decoder.decode_16bit_uint()),
                    (
                        "C_Manufacturer",
                        parse_modbus_string(decoder.decode_string(32)),
                    ),
                    ("C_Model", parse_modbus_string(decoder.decode_string(32))),
                    ("C_Option", parse_modbus_string(decoder.decode_string(16))),
                    ("C_Version", parse_modbus_string(decoder.decode_string(16))),
                    (
                        "C_SerialNumber",
                        parse_modbus_string(decoder.decode_string(32)),
                    ),
                    ("C_Device_address", decoder.decode_16bit_uint()),
                ]
            )

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}M{self.meter_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value} "
                        f"{type(value)}"
                    ),
                )

            if (
                self.decoded_common["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_common["C_SunSpec_DID"] != 0x0001
                or self.decoded_common["C_SunSpec_Length"] != 65
            ):
                raise DeviceInvalid(
                    f"Meter {self.meter_id} ident incorrect or not installed."
                )

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            raise DeviceInvalid(f"Meter {self.meter_id}: unsupported address")

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.fw_version = self.decoded_common["C_Version"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = f"{self.hub.hub_id.capitalize()} M{self.meter_id}"

        inverter_model = self.inverter_common["C_Model"]
        inerter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inerter_serial}_M{self.meter_id}"

    async def read_modbus_data(self) -> None:
        try:
            meter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id,
                address=self.start_address + 67,
                rcount=107,
            )

            decoder = BinaryPayloadDecoder.fromRegisters(
                meter_data.registers, byteorder=Endian.BIG
            )

            self.decoded_model = OrderedDict(
                [
                    ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                    ("C_SunSpec_Length", decoder.decode_16bit_uint()),
                    ("AC_Current", decoder.decode_16bit_int()),
                    ("AC_Current_A", decoder.decode_16bit_int()),
                    ("AC_Current_B", decoder.decode_16bit_int()),
                    ("AC_Current_C", decoder.decode_16bit_int()),
                    ("AC_Current_SF", decoder.decode_16bit_int()),
                    ("AC_Voltage_LN", decoder.decode_16bit_int()),
                    ("AC_Voltage_AN", decoder.decode_16bit_int()),
                    ("AC_Voltage_BN", decoder.decode_16bit_int()),
                    ("AC_Voltage_CN", decoder.decode_16bit_int()),
                    ("AC_Voltage_LL", decoder.decode_16bit_int()),
                    ("AC_Voltage_AB", decoder.decode_16bit_int()),
                    ("AC_Voltage_BC", decoder.decode_16bit_int()),
                    ("AC_Voltage_CA", decoder.decode_16bit_int()),
                    ("AC_Voltage_SF", decoder.decode_16bit_int()),
                    ("AC_Frequency", decoder.decode_16bit_int()),
                    ("AC_Frequency_SF", decoder.decode_16bit_int()),
                    ("AC_Power", decoder.decode_16bit_int()),
                    ("AC_Power_A", decoder.decode_16bit_int()),
                    ("AC_Power_B", decoder.decode_16bit_int()),
                    ("AC_Power_C", decoder.decode_16bit_int()),
                    ("AC_Power_SF", decoder.decode_16bit_int()),
                    ("AC_VA", decoder.decode_16bit_int()),
                    ("AC_VA_A", decoder.decode_16bit_int()),
                    ("AC_VA_B", decoder.decode_16bit_int()),
                    ("AC_VA_C", decoder.decode_16bit_int()),
                    ("AC_VA_SF", decoder.decode_16bit_int()),
                    ("AC_var", decoder.decode_16bit_int()),
                    ("AC_var_A", decoder.decode_16bit_int()),
                    ("AC_var_B", decoder.decode_16bit_int()),
                    ("AC_var_C", decoder.decode_16bit_int()),
                    ("AC_var_SF", decoder.decode_16bit_int()),
                    ("AC_PF", decoder.decode_16bit_int()),
                    ("AC_PF_A", decoder.decode_16bit_int()),
                    ("AC_PF_B", decoder.decode_16bit_int()),
                    ("AC_PF_C", decoder.decode_16bit_int()),
                    ("AC_PF_SF", decoder.decode_16bit_int()),
                    ("AC_Energy_WH_Exported", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Exported_A", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Exported_B", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Exported_C", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Imported", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Imported_A", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Imported_B", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_Imported_C", decoder.decode_32bit_uint()),
                    ("AC_Energy_WH_SF", decoder.decode_16bit_int()),
                    ("M_VAh_Exported", decoder.decode_32bit_uint()),
                    ("M_VAh_Exported_A", decoder.decode_32bit_uint()),
                    ("M_VAh_Exported_B", decoder.decode_32bit_uint()),
                    ("M_VAh_Exported_C", decoder.decode_32bit_uint()),
                    ("M_VAh_Imported", decoder.decode_32bit_uint()),
                    ("M_VAh_Imported_A", decoder.decode_32bit_uint()),
                    ("M_VAh_Imported_B", decoder.decode_32bit_uint()),
                    ("M_VAh_Imported_C", decoder.decode_32bit_uint()),
                    ("M_VAh_SF", decoder.decode_16bit_int()),
                    ("M_varh_Import_Q1", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q1_A", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q1_B", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q1_C", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q2", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q2_A", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q2_B", decoder.decode_32bit_uint()),
                    ("M_varh_Import_Q2_C", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q3", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q3_A", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q3_B", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q3_C", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q4", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q4_A", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q4_B", decoder.decode_32bit_uint()),
                    ("M_varh_Export_Q4_C", decoder.decode_32bit_uint()),
                    ("M_varh_SF", decoder.decode_16bit_int()),
                    ("M_Events", decoder.decode_32bit_uint()),
                ]
            )

        except ModbusIOError:
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
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
            self.decoded_model["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_model["C_SunSpec_DID"] not in [201, 202, 203, 204]
            or self.decoded_model["C_SunSpec_Length"] != 105
        ):
            raise DeviceInvalid(
                f"Meter {self.meter_id} ident incorrect or not installed."
            )

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
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
    def __init__(
        self, device_id: int, battery_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = []
        self.decoded_model = []
        self.start_address = None
        self.battery_id = battery_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self._via_device = None

        if self.battery_id == 1:
            self.start_address = 57600
        elif self.battery_id == 2:
            self.start_address = 57856
        else:
            raise ValueError("Invalid battery_id {self.battery_id}")

    async def init_device(self) -> None:
        try:
            battery_info = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=self.start_address, rcount=76
            )

            decoder = BinaryPayloadDecoder.fromRegisters(
                battery_info.registers,
                byteorder=Endian.BIG,
                wordorder=Endian.LITTLE,
            )
            self.decoded_common = OrderedDict(
                [
                    (
                        "B_Manufacturer",
                        parse_modbus_string(decoder.decode_string(32)),
                    ),
                    ("B_Model", parse_modbus_string(decoder.decode_string(32))),
                    ("B_Version", parse_modbus_string(decoder.decode_string(32))),
                    (
                        "B_SerialNumber",
                        parse_modbus_string(decoder.decode_string(32)),
                    ),
                    ("B_Device_Address", decoder.decode_16bit_uint()),
                    ("ignore", decoder.skip_bytes(2)),
                    ("B_RatedEnergy", decoder.decode_32bit_float()),
                    ("B_MaxChargePower", decoder.decode_32bit_float()),
                    ("B_MaxDischargePower", decoder.decode_32bit_float()),
                    ("B_MaxChargePeakPower", decoder.decode_32bit_float()),
                    ("B_MaxDischargePeakPower", decoder.decode_32bit_float()),
                ]
            )

            try:
                del self.decoded_common["ignore"]
            except KeyError:
                pass

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

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            raise DeviceInvalid(f"Battery {self.battery_id} unsupported address")

        self.decoded_common["B_Manufacturer"] = self.decoded_common[
            "B_Manufacturer"
        ].removesuffix(self.decoded_common["B_SerialNumber"])
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].removesuffix(
            self.decoded_common["B_SerialNumber"]
        )

        # Remove ASCII control characters from descriptive strings
        ascii_ctrl_chars = dict.fromkeys(range(32))
        self.decoded_common["B_Manufacturer"] = self.decoded_common[
            "B_Manufacturer"
        ].translate(ascii_ctrl_chars)
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].translate(
            ascii_ctrl_chars
        )
        self.decoded_common["B_SerialNumber"] = self.decoded_common[
            "B_SerialNumber"
        ].translate(ascii_ctrl_chars)

        if (
            float_to_hex(self.decoded_common["B_RatedEnergy"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self.decoded_common["B_RatedEnergy"] <= 0
        ):
            raise DeviceInvalid(f"Battery {self.battery_id} not usable (rating <=0)")

        self.manufacturer = self.decoded_common["B_Manufacturer"]
        self.model = self.decoded_common["B_Model"]
        self.option = ""
        self.fw_version = self.decoded_common["B_Version"]
        self.serial = self.decoded_common["B_SerialNumber"]
        self.device_address = self.decoded_common["B_Device_Address"]
        self.name = f"{self.hub.hub_id.capitalize()} B{self.battery_id}"

        inverter_model = self.inverter_common["C_Model"]
        inerter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inerter_serial}_B{self.battery_id}"

    async def read_modbus_data(self) -> None:
        try:
            battery_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id,
                address=self.start_address + 108,
                rcount=46,
            )

            decoder = BinaryPayloadDecoder.fromRegisters(
                battery_data.registers,
                byteorder=Endian.BIG,
                wordorder=Endian.LITTLE,
            )

            self.decoded_model = OrderedDict(
                [
                    ("B_Temp_Average", decoder.decode_32bit_float()),
                    ("B_Temp_Max", decoder.decode_32bit_float()),
                    ("B_DC_Voltage", decoder.decode_32bit_float()),
                    ("B_DC_Current", decoder.decode_32bit_float()),
                    ("B_DC_Power", decoder.decode_32bit_float()),
                    ("B_Export_Energy_WH", decoder.decode_64bit_uint()),
                    ("B_Import_Energy_WH", decoder.decode_64bit_uint()),
                    ("B_Energy_Max", decoder.decode_32bit_float()),
                    ("B_Energy_Available", decoder.decode_32bit_float()),
                    ("B_SOH", decoder.decode_32bit_float()),
                    ("B_SOE", decoder.decode_32bit_float()),
                    ("B_Status", decoder.decode_32bit_uint()),
                    ("B_Status_Vendor", decoder.decode_32bit_uint()),
                    ("B_Event_Log1", decoder.decode_16bit_uint()),
                    ("B_Event_Log2", decoder.decode_16bit_uint()),
                    ("B_Event_Log3", decoder.decode_16bit_uint()),
                    ("B_Event_Log4", decoder.decode_16bit_uint()),
                    ("B_Event_Log5", decoder.decode_16bit_uint()),
                    ("B_Event_Log6", decoder.decode_16bit_uint()),
                    ("B_Event_Log7", decoder.decode_16bit_uint()),
                    ("B_Event_Log8", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor1", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor2", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor3", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor4", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor5", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor6", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor7", decoder.decode_16bit_uint()),
                    ("B_Event_Log_Vendor8", decoder.decode_16bit_uint()),
                ]
            )

        except ModbusIOError:
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
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
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
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
