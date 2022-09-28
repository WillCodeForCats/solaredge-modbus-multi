import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.compat import iteritems
from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.pdu import ModbusExceptions

from .const import DOMAIN, SunSpecNotImpl
from .helpers import parse_modbus_string

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
    """Raised when a modbus read fails"""

    pass


class ModbusWriteError(SolarEdgeException):
    """Raised when a modbus write fails"""

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
        name: str,
        host: str,
        port: int,
        number_of_inverters: int = 1,
        start_device_id: int = 1,
        detect_meters: bool = True,
        detect_batteries: bool = False,
        single_device_entity: bool = True,
        keep_modbus_open: bool = False,
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._name = name
        self._host = host
        self._port = port
        self._number_of_inverters = number_of_inverters
        self._start_device_id = start_device_id
        self._detect_meters = detect_meters
        self._detect_batteries = detect_batteries
        self._single_device_entity = single_device_entity
        self.keep_modbus_open = keep_modbus_open
        self._lock = threading.Lock()
        self._id = name.lower()
        self._client = None
        self.inverters = []
        self.meters = []
        self.batteries = []
        self.inverter_common = {}
        self.mmppt_common = {}

        self.initalized = False
        self.online = False

        _LOGGER.debug(
            (
                f"{DOMAIN} configuration: "
                f"number_of_inverters={self._number_of_inverters}, "
                f"start_device_id={self._start_device_id}, "
                f"detect_meters={self._detect_meters}, "
                f"detect_batteries={self._detect_batteries}, "
                f"single_device_entity={self._single_device_entity}, "
                f"keep_modbus_open={self.keep_modbus_open}, "
            ),
        )

    async def _async_init_solaredge(self) -> None:
        if not self.is_socket_open():
            raise HubInitFailed(f"Could not open Modbus/TCP connection to {self._host}")

        if self._detect_batteries:
            _LOGGER.warning(
                (
                    "Battery registers not officially supported by SolarEdge. "
                    "Use at your own risk!"
                ),
            )

        for inverter_index in range(self._number_of_inverters):
            inverter_unit_id = inverter_index + self._start_device_id

            try:
                new_inverter = SolarEdgeInverter(inverter_unit_id, self)
                await self._hass.async_add_executor_job(new_inverter.init_device)
                self.inverters.append(new_inverter)

            except ModbusReadError as e:
                self.disconnect()
                raise HubInitFailed(f"{e}")

            except DeviceInvalid as e:
                """Inverters are required"""
                _LOGGER.error(f"Inverter device ID {inverter_unit_id}: {e}")
                raise HubInitFailed(f"Inverter device ID {inverter_unit_id} not found.")

            if self._detect_meters:
                try:
                    new_meter_1 = SolarEdgeMeter(inverter_unit_id, 1, self)
                    await self._hass.async_add_executor_job(new_meter_1.init_device)

                    for meter in self.meters:
                        if new_meter_1.serial == meter.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_meter_1.serial} "
                                    f"on meter 1 inverter {inverter_unit_id}"
                                ),
                            )
                            raise DeviceInvalid(
                                f"Duplicate m1 serial {new_meter_1.serial}"
                            )

                    self.meters.append(new_meter_1)
                    _LOGGER.debug(f"Found meter 1 on inverter ID {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid:
                    pass

                try:
                    new_meter_2 = SolarEdgeMeter(inverter_unit_id, 2, self)
                    await self._hass.async_add_executor_job(new_meter_2.init_device)

                    for meter in self.meters:
                        if new_meter_2.serial == meter.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_meter_2.serial} "
                                    f"on meter 2 inverter {inverter_unit_id}"
                                ),
                            )
                            raise DeviceInvalid(
                                f"Duplicate m2 serial {new_meter_2.serial}"
                            )

                    self.meters.append(new_meter_2)
                    _LOGGER.debug(f"Found meter 2 on inverter ID {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid:
                    pass

                try:
                    new_meter_3 = SolarEdgeMeter(inverter_unit_id, 3, self)
                    await self._hass.async_add_executor_job(new_meter_3.init_device)

                    for meter in self.meters:
                        if new_meter_3.serial == meter.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_meter_3.serial} "
                                    f"on meter 3 inverter {inverter_unit_id}"
                                ),
                            )
                            raise DeviceInvalid(
                                f"Duplicate m3 serial {new_meter_3.serial}"
                            )

                    self.meters.append(new_meter_3)
                    _LOGGER.debug(f"Found meter 3 on inverter ID {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid:
                    pass

            if self._detect_batteries:
                try:
                    new_battery_1 = SolarEdgeBattery(inverter_unit_id, 1, self)
                    await self._hass.async_add_executor_job(new_battery_1.init_device)

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

                    self.batteries.append(new_battery_1)
                    _LOGGER.debug(f"Found battery 1 inverter {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid:
                    pass

                try:
                    new_battery_2 = SolarEdgeBattery(inverter_unit_id, 2, self)
                    await self._hass.async_add_executor_job(new_battery_2.init_device)

                    for battery in self.batteries:
                        if new_battery_2.serial == battery.serial:
                            _LOGGER.warning(
                                (
                                    f"Duplicate serial {new_battery_2.serial} "
                                    f"on battery 2 inverter {inverter_unit_id}"
                                ),
                            )
                            raise DeviceInvalid(
                                f"Duplicate b2 serial {new_battery_1.serial}"
                            )

                    self.batteries.append(new_battery_2)
                    _LOGGER.debug(f"Found battery 2 inverter {inverter_unit_id}")

                except ModbusReadError as e:
                    self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid:
                    pass

        try:
            for inverter in self.inverters:
                await self._hass.async_add_executor_job(inverter.read_modbus_data)

            for meter in self.meters:
                await self._hass.async_add_executor_job(meter.read_modbus_data)

            for battery in self.batteries:
                await self._hass.async_add_executor_job(battery.read_modbus_data)

        except Exception:
            raise HubInitFailed("Devices not ready.")

        self.initalized = True

    async def async_refresh_modbus_data(self, _now: Optional[int] = None) -> bool:
        if not self.is_socket_open():
            await self.connect()

        if not self.initalized:
            try:
                await self._async_init_solaredge()

            except ConnectionException as e:
                self.disconnect()
                raise HubInitFailed(f"Setup failed: {e}")

        if not self.is_socket_open():
            self.online = False
            raise DataUpdateFailed(
                f"Could not open Modbus/TCP connection to {self._host}"
            )

        else:
            self.online = True
            try:
                for inverter in self.inverters:
                    await self._hass.async_add_executor_job(inverter.read_modbus_data)
                for meter in self.meters:
                    await self._hass.async_add_executor_job(meter.read_modbus_data)
                for battery in self.batteries:
                    await self._hass.async_add_executor_job(battery.read_modbus_data)

            except ModbusReadError as e:
                self.online = False
                self.disconnect()
                raise DataUpdateFailed(f"Update failed: {e}")

            except DeviceInvalid as e:
                self.online = False
                if not self.keep_modbus_open:
                    self.disconnect()
                raise DataUpdateFailed(f"Invalid device: {e}")

            except ConnectionException as e:
                self.online = False
                self.disconnect()
                raise DataUpdateFailed(f"Connection failed: {e}")

        if not self.keep_modbus_open:
            self.disconnect()

        return True

    @property
    def name(self):
        """Return the name of this hub."""
        return self._name

    @property
    def hub_id(self) -> str:
        return self._id

    def disconnect(self) -> None:
        """Disconnect modbus client."""
        with self._lock:
            self._client.close()

    async def connect(self) -> None:
        """Connect modbus client."""
        with self._lock:
            if self._client is None:
                self._client = ModbusTcpClient(host=self._host, port=self._port)

            await self._hass.async_add_executor_job(self._client.connect)

    def is_socket_open(self) -> bool:
        """Check modbus client connection status."""
        with self._lock:
            if self._client is None:
                return False

            return self._client.is_socket_open()

    async def shutdown(self) -> None:
        """Shut down the hub."""
        self.online = False
        self.disconnect()
        self._client = None

    def read_holding_registers(self, unit, address, count):
        """Read holding registers."""
        with self._lock:
            kwargs = {"unit": unit} if unit else {}
            return self._client.read_holding_registers(address, count, **kwargs)


class SolarEdgeInverter:
    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = []
        self.decoded_model = []
        self.decoded_mmppt = []
        self.has_parent = False
        self.global_power_control_block = None

    def init_device(self) -> None:
        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40000, count=4
        )
        if inverter_data.isError():
            _LOGGER.debug(f"Inverter {self.inverter_unit_id}: {inverter_data}")
            raise ModbusReadError(inverter_data)

        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )

        decoded_ident = OrderedDict(
            [
                ("C_SunSpec_ID", decoder.decode_32bit_uint()),
                ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                ("C_SunSpec_Length", decoder.decode_16bit_uint()),
            ]
        )

        for name, value in iteritems(decoded_ident):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

        if (
            decoded_ident["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or decoded_ident["C_SunSpec_DID"] != 0x0001
            or decoded_ident["C_SunSpec_Length"] != 65
        ):
            raise DeviceInvalid("Inverter {self.inverter_unit_id} not usable.")

        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40004, count=65
        )
        if inverter_data.isError():
            _LOGGER.debug(f"Inverter {self.inverter_unit_id}: {inverter_data}")
            raise ModbusReadError(inverter_data)

        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )

        self.decoded_common = OrderedDict(
            [
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

        for name, value in iteritems(self.decoded_common):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

        self.hub.inverter_common[self.inverter_unit_id] = self.decoded_common

        mmppt_common = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40121, count=10
        )
        if mmppt_common.isError():
            _LOGGER.debug(f"Inverter {self.inverter_unit_id} MMPPT: {inverter_data}")

            if mmppt_common.exception_code == ModbusExceptions.IllegalAddress:
                _LOGGER.debug(f"Inverter {self.inverter_unit_id} is NOT Multiple MPPT")
                self.decoded_mmppt = None

            else:
                raise ModbusReadError(mmppt_common)

        else:
            decoder = BinaryPayloadDecoder.fromRegisters(
                mmppt_common.registers, byteorder=Endian.Big
            )

            self.decoded_mmppt = OrderedDict(
                [
                    ("mmppt_DID", decoder.decode_16bit_uint()),
                    ("mmppt_Length", decoder.decode_16bit_uint()),
                    ("mmppt_DCA_SF", decoder.decode_16bit_int()),
                    ("mmppt_DCV_SF", decoder.decode_16bit_int()),
                    ("mmppt_DCW_SF", decoder.decode_16bit_int()),
                    ("mmppt_DCWH_SF", decoder.decode_16bit_int()),
                    ("mmppt_Events", decoder.decode_32bit_uint()),
                    ("mmppt_Units", decoder.decode_16bit_uint()),
                    ("mmppt_TmsPer", decoder.decode_16bit_uint()),
                ]
            )

            for name, value in iteritems(self.decoded_mmppt):
                _LOGGER.debug(
                    (
                        f"Inverter {self.inverter_unit_id} MMPPT: "
                        f"{name} {hex(value) if isinstance(value, int) else value}"
                    ),
                )

            if (
                self.decoded_mmppt["mmppt_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_mmppt["mmppt_Units"] == SunSpecNotImpl.UINT16
                or self.decoded_mmppt["mmppt_DID"] not in [160]
                or self.decoded_mmppt["mmppt_Units"] not in [2, 3]
            ):
                _LOGGER.debug(f"Inverter {self.inverter_unit_id} is NOT Multiple MPPT")
                self.decoded_mmppt = None
            else:
                _LOGGER.debug(f"Inverter {self.inverter_unit_id} is Multiple MPPT")

        self.hub.mmppt_common[self.inverter_unit_id] = self.decoded_mmppt

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.fw_version = self.decoded_common["C_Version"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id}"
        self.uid_base = f"{self.model}_{self.serial}"

        self._device_info = {
            "identifiers": {(DOMAIN, f"{self.model}_{self.serial}")},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

    def read_modbus_data(self) -> None:
        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40069, count=2
        )
        if inverter_data.isError():
            _LOGGER.debug(f"Inverter {self.inverter_unit_id}: {inverter_data}")
            raise ModbusReadError(inverter_data)

        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )

        decoded_ident = OrderedDict(
            [
                ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                ("C_SunSpec_Length", decoder.decode_16bit_uint()),
            ]
        )

        for name, value in iteritems(decoded_ident):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

        if (
            decoded_ident["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or decoded_ident["C_SunSpec_DID"] not in [101, 102, 103]
            or decoded_ident["C_SunSpec_Length"] != 50
        ):
            raise DeviceInvalid(f"Inverter {self.inverter_unit_id} not usable.")

        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40071, count=38
        )
        if inverter_data.isError():
            _LOGGER.debug(f"Inverter {self.inverter_unit_id}: {inverter_data}")
            raise ModbusReadError(inverter_data)

        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )

        self.decoded_model = OrderedDict(
            [
                ("C_SunSpec_DID", decoded_ident["C_SunSpec_DID"]),
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
            self.global_power_control_block is True
            or self.global_power_control_block is None
        ):
            inverter_data = self.hub.read_holding_registers(
                unit=self.inverter_unit_id, address=61440, count=4
            )
            if inverter_data.isError():
                if inverter_data.exception_code == 0x02:
                    self.global_power_control_block = False
                    _LOGGER.debug(
                        (
                            f"Inverter {self.inverter_unit_id}: "
                            "global power control block unavailable"
                        )
                    )
                else:
                    _LOGGER.debug(f"Inverter {self.inverter_unit_id}: {inverter_data}")
                    raise ModbusReadError(inverter_data)

            else:
                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers,
                    byteorder=Endian.Big,
                    wordorder=Endian.Little,
                )

                self.decoded_model.append(
                    OrderedDict(
                        [
                            ("I_RRCR", decoder.decode_16bit_uint()),
                            ("I_Power_Limit", decoder.decode_16bit_uint()),
                            ("I_CosPhi", decoder.decode_32bit_float()),
                        ]
                    )
                )
                self.power_status_available = True

        for name, value in iteritems(self.decoded_model):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info

    @property
    def single_device_entity(self) -> bool:
        return self.hub._single_device_entity


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

    def init_device(self) -> None:
        meter_info = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address, count=2
        )
        if meter_info.isError():
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} "
                    f"meter {self.meter_id}: {meter_info}"
                ),
            )

            if meter_info.exception_code == ModbusExceptions.IllegalAddress:
                raise DeviceInvalid(meter_info)

            else:
                raise ModbusReadError(meter_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_info.registers, byteorder=Endian.Big
        )
        decoded_ident = OrderedDict(
            [
                ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                ("C_SunSpec_Length", decoder.decode_16bit_uint()),
            ]
        )

        for name, value in iteritems(decoded_ident):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} meter {self.meter_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

        if (
            decoded_ident["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or decoded_ident["C_SunSpec_DID"] != 0x0001
            or decoded_ident["C_SunSpec_Length"] != 65
        ):
            raise DeviceInvalid("Meter {self.meter_id} not usable.")

        meter_info = self.hub.read_holding_registers(
            unit=self.inverter_unit_id,
            address=self.start_address + 2,
            count=65,
        )
        if meter_info.isError():
            _LOGGER.debug(meter_info)
            raise ModbusReadError(meter_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_info.registers, byteorder=Endian.Big
        )
        self.decoded_common = OrderedDict(
            [
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

        for name, value in iteritems(self.decoded_common):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} meter {self.meter_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

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

        self._device_info = {
            "identifiers": {(DOMAIN, self.uid_base)},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

    def read_modbus_data(self) -> None:
        meter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id,
            address=self.start_address + 67,
            count=2,
        )
        if meter_data.isError():
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} "
                    f"meter {self.meter_id}: {meter_data}"
                ),
            )
            raise ModbusReadError(f"Meter read error: {meter_data}")

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_data.registers, byteorder=Endian.Big
        )

        decoded_ident = OrderedDict(
            [
                ("C_SunSpec_DID", decoder.decode_16bit_uint()),
                ("C_SunSpec_Length", decoder.decode_16bit_uint()),
            ]
        )

        for name, value in iteritems(decoded_ident):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} meter {self.meter_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

        if (
            decoded_ident["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or decoded_ident["C_SunSpec_DID"] not in [201, 202, 203, 204]
            or decoded_ident["C_SunSpec_Length"] != 105
        ):
            raise DeviceInvalid(
                f"Meter on inverter {self.inverter_unit_id} not usable."
            )

        meter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id,
            address=self.start_address + 69,
            count=105,
        )
        if meter_data.isError():
            _LOGGER.error(f"Meter read error: {meter_data}")
            raise ModbusReadError(f"Meter read error: {meter_data}")

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_data.registers, byteorder=Endian.Big
        )

        self.decoded_model = OrderedDict(
            [
                ("C_SunSpec_DID", decoded_ident["C_SunSpec_DID"]),
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

        for name, value in iteritems(self.decoded_model):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} meter {self.meter_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info

    @property
    def single_device_entity(self) -> bool:
        return self.hub._single_device_entity


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

        if self.battery_id == 1:
            self.start_address = 57600
        elif self.battery_id == 2:
            self.start_address = 57856
        else:
            raise ValueError("Invalid battery_id {self.battery_id}")

    def init_device(self) -> None:
        battery_info = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address, count=76
        )
        if battery_info.isError():
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} "
                    f"battery {self.battery_id}: {battery_info}"
                ),
            )

            if battery_info.exception_code == ModbusExceptions.IllegalAddress:
                raise DeviceInvalid(battery_info)

            else:
                raise ModbusReadError(battery_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            battery_info.registers,
            byteorder=Endian.Big,
            wordorder=Endian.Little,
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
                ("Reserved", decoder.decode_16bit_uint()),
                ("B_RatedEnergy", decoder.decode_32bit_float()),
                ("B_MaxChargePower", decoder.decode_32bit_float()),
                ("B_MaxDischargePower", decoder.decode_32bit_float()),
                ("B_MaxChargePeakPower", decoder.decode_32bit_float()),
                ("B_MaxDischargePeakPower", decoder.decode_32bit_float()),
            ]
        )

        for name, value in iteritems(self.decoded_common):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} batt {self.battery_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

        self.decoded_common["B_Manufacturer"] = self.decoded_common[
            "B_Manufacturer"
        ].removesuffix(self.decoded_common["B_SerialNumber"])
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].removesuffix(
            self.decoded_common["B_SerialNumber"]
        )

        ascii_ctrl_chars = dict.fromkeys(range(32))
        self.decoded_common["B_Manufacturer"] = self.decoded_common[
            "B_Manufacturer"
        ].translate(ascii_ctrl_chars)

        if (
            len(self.decoded_common["B_Manufacturer"]) == 0
            or len(self.decoded_common["B_Model"]) == 0
            or len(self.decoded_common["B_SerialNumber"]) == 0
        ):
            raise DeviceInvalid("Battery {self.battery_id} not usable.")

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

        self._device_info = {
            "identifiers": {(DOMAIN, self.uid_base)},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
        }

    def read_modbus_data(self) -> None:
        battery_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id,
            address=self.start_address + 108,
            count=46,
        )
        if battery_data.isError():
            _LOGGER.error(f"Battery read error: {battery_data}")
            raise ModbusReadError(f"Battery read error: {battery_data}")

        decoder = BinaryPayloadDecoder.fromRegisters(
            battery_data.registers,
            byteorder=Endian.Big,
            wordorder=Endian.Little,
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

        for name, value in iteritems(self.decoded_model):
            _LOGGER.debug(
                (
                    f"Inverter {self.inverter_unit_id} batt {self.battery_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value}"
                ),
            )

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info

    @property
    def single_device_entity(self) -> bool:
        return self.hub._single_device_entity
