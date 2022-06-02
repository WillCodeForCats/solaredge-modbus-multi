import logging
import threading

from typing import Any, Callable, Optional, Dict
from datetime import timedelta
from collections import OrderedDict

from pymodbus.client.sync import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.compat import iteritems

from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    SUNSPEC_NOT_IMPL_UINT16,
)

from .helpers import (
    parse_modbus_string
)

_LOGGER = logging.getLogger(__name__)

class SolarEdgeModbusMultiHub:
    """Thread safe wrapper class for pymodbus."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        host: str,
        port: int,
        scan_interval: int,
        number_of_inverters: bool = 1,
        start_device_id: int = 1,
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._name = name
        self.number_of_inverters = number_of_inverters
        self.start_device_id = start_device_id
        self._scan_interval = timedelta(seconds=scan_interval)
        self._polling_interval = None
        self._sensors = []
        self.data = {}

        self._client = ModbusTcpClient(host=self._host, port=self._port)
        
        self._id = name.lower()
        
        self.online = False
        
        self.inverters = []
        self.meters = []
        self.batteries = []

    async def async_init_solaredge(self) -> None:

        if not self.is_socket_open():        
            self.connect()

        for inverter_index in range(self.number_of_inverters):
            inverter_unit_id = inverter_index + self.start_device_id
            
            try:
                self.inverters.append(SolarEdgeInverter(inverter_unit_id, self))
            except Exception as e:
                _LOGGER.error(f"Inverter device ID {inverter_unit_id}: {e}")
                raise ConfigEntryNotReady(f"Inverter device ID {inverter_unit_id} not found.")
        
            try:
                self.meters.append(SolarEdgeMeter(inverter_unit_id, 1, self))
                _LOGGER.info(f"Found meter 1 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                self.meters.append(SolarEdgeMeter(inverter_unit_id, 2, self))
                _LOGGER.info(f"Found meter 2 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                self.meters.append(SolarEdgeMeter(inverter_unit_id, 3, self))
                _LOGGER.info(f"Found meter 3 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                self.batteries.append(SolarEdgeBattery(inverter_unit_id, 1, self))
                _LOGGER.info(f"Found battery 1 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                self.batteries.append(SolarEdgeBattery(inverter_unit_id, 2, self))
                _LOGGER.info(f"Found battery 2 on inverter ID {inverter_unit_id}")
            except:
                pass

        try:
            for inverter in self.inverters:
                inverter.read_modbus_data()
                await inverter.publish_updates()

            for meter in self.meters:
                meter.read_modbus_data()
                await meter.publish_updates()

        except:
            raise ConfigEntryNotReady(f"Devices not ready.")

        self.close()

        self._polling_interval = async_track_time_interval(
            self._hass, self.async_refresh_modbus_data, self._scan_interval
        )

        self.online = True

    async def async_refresh_modbus_data(self, _now: Optional[int] = None) -> None:

        if not self.is_socket_open():        
            self.connect()
        
        if not self.is_socket_open():
            self.online = False
            _LOGGER.error(f"Could not open Modbus/TCP connection to {self._host}")
        
        else:
            self.online = True
            try:
                for inverter in self.inverters:
                    inverter.read_modbus_data()
                    await inverter.publish_updates()
                
                for meter in self.meters:
                    meter.read_modbus_data()
                    await meter.publish_updates()
            
            except Exception as e:
                self.online = False
                _LOGGER.error(f"Failed to update devices: {e}")

        self.close()

    @property
    def name(self):
        """Return the name of this hub."""
        return self._name

    @property
    def hub_id(self) -> str:
        return self._id

    def close(self):
        """Disconnect client."""
        with self._lock:
            self._client.close()

    def connect(self):
        """Connect client."""
        with self._lock:
            self._client.connect()

    def is_socket_open(self):
        """Check client."""
        with self._lock:
            return self._client.is_socket_open()

    async def shutdown(self) -> None:
        self._polling_interval()
        self._polling_interval = None
        self.online = False        
        self.close()

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
        self._callbacks = set()
        
        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40000, count=4
        )
        if inverter_data.isError():
            _LOGGER.error(inverter_data)
            raise RuntimeError(inverter_data)
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )
        
        decoded_ident = OrderedDict([
            ('C_SunSpec_ID', decoder.decode_32bit_uint()),
            ('C_SunSpec_DID', decoder.decode_16bit_uint()),
            ('C_SunSpec_Length', decoder.decode_16bit_uint()),
        ])
        
        for name, value in iteritems(decoded_ident):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)
 
        if (
            decoded_ident['C_SunSpec_DID'] == SUNSPEC_NOT_IMPL_UINT16
            or decoded_ident['C_SunSpec_DID'] != 0x0001
            or decoded_ident['C_SunSpec_Length'] != 65
        ):
            raise RuntimeError("Inverter {self.inverter_unit_id} not usable.")
        
        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40004, count=65
        )
        if inverter_data.isError():
            _LOGGER.error(inverter_data)
            raise RuntimeError(inverter_data)
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )
        
        self.decoded_common = OrderedDict([
            ('C_Manufacturer', parse_modbus_string(decoder.decode_string(32))),
            ('C_Model', parse_modbus_string(decoder.decode_string(32))),
            ('C_Option', parse_modbus_string(decoder.decode_string(16))),
            ('C_Version', parse_modbus_string(decoder.decode_string(16))),
            ('C_SerialNumber', parse_modbus_string(decoder.decode_string(32))),
            ('C_Device_address', decoder.decode_16bit_uint()),
        ])
        
        for name, value in iteritems(self.decoded_common):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)
        
        self.manufacturer = self.decoded_common['C_Manufacturer']
        self.model = self.decoded_common['C_Model']
        self.option = self.decoded_common['C_Option']
        self.fw_version = self.decoded_common['C_Version']
        self.serial = self.decoded_common['C_SerialNumber']
        self.device_address = self.decoded_common['C_Device_address']
        self.name = f"{hub.hub_id.capitalize()} I{self.inverter_unit_id}"
        
        self._device_info = {
            "identifiers": {(DOMAIN, f"{self.model}_{self.serial}")},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when SolarEdgeInverter changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self) -> None:
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

    def read_modbus_data(self) -> None:
        
        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40069, count=2
        )
        if inverter_data.isError():
            _LOGGER.error(inverter_data)
            raise RuntimeError(inverter_data)
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )
        
        decoded_ident = OrderedDict([
            ('C_SunSpec_DID', decoder.decode_16bit_uint()),
            ('C_SunSpec_Length', decoder.decode_16bit_uint()),
        ])
        
        for name, value in iteritems(decoded_ident):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)
        
        if (
            decoded_ident['C_SunSpec_DID'] == SUNSPEC_NOT_IMPL_UINT16
            or decoded_ident['C_SunSpec_DID'] not in [101,102,103]
            or decoded_ident['C_SunSpec_Length'] != 50
        ):
            raise RuntimeError("Inverter {self.inverter_unit_id} not usable.")
        
        inverter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40071, count=38
        )
        if inverter_data.isError():
            _LOGGER.error(inverter_data)
            raise RuntimeError(inverter_data)
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )
        
        self.decoded_model = OrderedDict([
            ('C_SunSpec_DID',     decoded_ident['C_SunSpec_DID']),
            ('AC_Current',      decoder.decode_16bit_uint()),
            ('AC_Current_A',     decoder.decode_16bit_uint()),
            ('AC_Current_B',     decoder.decode_16bit_uint()),
            ('AC_Current_C',     decoder.decode_16bit_uint()),
            ('AC_Current_SF',   decoder.decode_16bit_int()),
            ('AC_Voltage_AB',    decoder.decode_16bit_uint()),
            ('AC_Voltage_BC',    decoder.decode_16bit_uint()),
            ('AC_Voltage_CA',    decoder.decode_16bit_uint()),
            ('AC_Voltage_AN',    decoder.decode_16bit_uint()),
            ('AC_Voltage_BN',    decoder.decode_16bit_uint()),
            ('AC_Voltage_CN',    decoder.decode_16bit_uint()),
            ('AC_Voltage_SF',   decoder.decode_16bit_int()),
            ('AC_Power',        decoder.decode_16bit_int()),
            ('AC_Power_SF',     decoder.decode_16bit_int()),
            ('AC_Frequency',    decoder.decode_16bit_uint()),
            ('AC_Frequency_SF', decoder.decode_16bit_int()),
            ('AC_VA',           decoder.decode_16bit_int()),
            ('AC_VA_SF',        decoder.decode_16bit_int()),
            ('AC_var',          decoder.decode_16bit_int()),
            ('AC_var_SF',       decoder.decode_16bit_int()),
            ('AC_PF',           decoder.decode_16bit_int()),
            ('AC_PF_SF',        decoder.decode_16bit_int()),
            ('AC_Energy_WH',    decoder.decode_32bit_uint()),
            ('AC_Energy_WH_SF', decoder.decode_16bit_uint()),
            ('I_DC_Current',      decoder.decode_16bit_uint()),
            ('I_DC_Current_SF',   decoder.decode_16bit_int()),
            ('I_DC_Voltage',      decoder.decode_16bit_uint()),
            ('I_DC_Voltage_SF',   decoder.decode_16bit_int()),
            ('I_DC_Power',        decoder.decode_16bit_int()),
            ('I_DC_Power_SF',     decoder.decode_16bit_int()),
            ('I_Temp_Cab',        decoder.decode_16bit_int()),
            ('I_Temp_Sink',       decoder.decode_16bit_int()),
            ('I_Temp_Trns',       decoder.decode_16bit_int()),
            ('I_Temp_Other',      decoder.decode_16bit_int()),
            ('I_Temp_SF',         decoder.decode_16bit_int()),
            ('I_Status',          decoder.decode_16bit_int()),
            ('I_Status_Vendor',   decoder.decode_16bit_int()),
        ])
        
        for name, value in iteritems(self.decoded_model):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)
 
    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info


class SolarEdgeMeter:
    def __init__(self, device_id: int, meter_id: int, hub: SolarEdgeModbusMultiHub) -> None:

        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = []
        self.decoded_model = []
        self._callbacks = set()
        self.start_address = None
      
        if meter_id == 1:
            self.start_address = 40000 + 121
        elif meter_id == 2:
            self.start_address = 40000 + 295
        elif meter_id == 3:
            self.start_address = 40000 + 469
        else:
            raise ValueError("Invalid meter_id")

        meter_info = hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address, count=2
        )
        if meter_info.isError():
            _LOGGER.debug(meter_info)
            raise RuntimeError(meter_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_info.registers, byteorder=Endian.Big
        )
        decoded_ident = OrderedDict([
            ('C_SunSpec_DID', decoder.decode_16bit_uint()),
            ('C_SunSpec_Length', decoder.decode_16bit_uint()),
        ])
        
        for name, value in iteritems(decoded_ident):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)

        if (
            decoded_ident['C_SunSpec_DID'] == SUNSPEC_NOT_IMPL_UINT16
            or decoded_ident['C_SunSpec_DID'] != 0x0001
            or decoded_ident['C_SunSpec_Length'] != 65
        ):
            raise RuntimeError("Meter {meter_id} not usable.")

        meter_info = hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address + 2, count=65
        )
        if meter_info.isError():
            _LOGGER.debug(meter_info)
            raise RuntimeError(meter_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_info.registers, byteorder=Endian.Big
        )
        self.decoded_common = OrderedDict([
            ('C_Manufacturer', parse_modbus_string(decoder.decode_string(32))),
            ('C_Model', parse_modbus_string(decoder.decode_string(32))),
            ('C_Option', parse_modbus_string(decoder.decode_string(16))),
            ('C_Version', parse_modbus_string(decoder.decode_string(16))),
            ('C_SerialNumber', parse_modbus_string(decoder.decode_string(32))),
            ('C_Device_address', decoder.decode_16bit_uint()),
        ])

        for name, value in iteritems(self.decoded_common):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)

        self.manufacturer = self.decoded_common['C_Manufacturer']
        self.model = self.decoded_common['C_Model']
        self.option = self.decoded_common['C_Option']
        self.fw_version = self.decoded_common['C_Version']
        self.serial = self.decoded_common['C_SerialNumber']
        self.device_address = self.decoded_common['C_Device_address']
        self.name = f"{hub.hub_id.capitalize()} M{self.inverter_unit_id}-{meter_id}"

        self._device_info = {
            "identifiers": {(DOMAIN, f"{self.model}_{self.serial}")},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when SolarEdgeMeter changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self) -> None:
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

    def read_modbus_data(self) -> None:
        
        meter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address + 67, count=2
        )
        if meter_data.isError():
            _LOGGER.error(f"Meter read error: {meter_data}")
            raise RuntimeError(f"Meter read error: {meter_data}")
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_data.registers, byteorder=Endian.Big
        )
        
        decoded_ident = OrderedDict([
            ('C_SunSpec_DID', decoder.decode_16bit_uint()),
            ('C_SunSpec_Length', decoder.decode_16bit_uint()),
        ])
        
        for name, value in iteritems(decoded_ident):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)
        
        if (
            decoded_ident['C_SunSpec_DID'] == SUNSPEC_NOT_IMPL_UINT16
            or decoded_ident['C_SunSpec_DID'] not in [201,202,203,204]
            or decoded_ident['C_SunSpec_Length'] != 105
        ):
            raise RuntimeError("Meter on inverter {self.inverter_unit_id} not usable.")

        meter_data = self.hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address + 69, count=105
        )
        if meter_data.isError():
            _LOGGER.error(f"Meter read error: {meter_data}")
            raise RuntimeError(f"Meter read error: {meter_data}")
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_data.registers, byteorder=Endian.Big
        )
        
        self.decoded_model = OrderedDict([
            ('C_SunSpec_DID',           decoded_ident['C_SunSpec_DID']),
            ('AC_Current',              decoder.decode_16bit_int()),
            ('AC_Current_A',            decoder.decode_16bit_int()),
            ('AC_Current_B',            decoder.decode_16bit_int()),
            ('AC_Current_C',            decoder.decode_16bit_int()),
            ('AC_Current_SF',           decoder.decode_16bit_int()),
            ('AC_Voltage_LN',           decoder.decode_16bit_int()),
            ('AC_Voltage_AN',           decoder.decode_16bit_int()),
            ('AC_Voltage_BN',           decoder.decode_16bit_int()),
            ('AC_Voltage_CN',           decoder.decode_16bit_int()),
            ('AC_Voltage_LL',           decoder.decode_16bit_int()),
            ('AC_Voltage_AB',           decoder.decode_16bit_int()),
            ('AC_Voltage_BC',           decoder.decode_16bit_int()),
            ('AC_Voltage_CA',           decoder.decode_16bit_int()),
            ('AC_Voltage_SF',           decoder.decode_16bit_int()),
            ('AC_Frequency',            decoder.decode_16bit_int()),
            ('AC_Frequency_SF',         decoder.decode_16bit_int()),
            ('AC_Power',                decoder.decode_16bit_int()),
            ('AC_Power_A',              decoder.decode_16bit_int()),
            ('AC_Power_B',              decoder.decode_16bit_int()),
            ('AC_Power_C',              decoder.decode_16bit_int()),
            ('AC_Power_SF',             decoder.decode_16bit_int()),
            ('AC_VA',                   decoder.decode_16bit_int()),
            ('AC_VA_A',                 decoder.decode_16bit_int()),
            ('AC_VA_B',                 decoder.decode_16bit_int()),
            ('AC_VA_C',                 decoder.decode_16bit_int()),
            ('AC_VA_SF',                decoder.decode_16bit_int()),
            ('AC_var',                  decoder.decode_16bit_int()),
            ('AC_var_A',                decoder.decode_16bit_int()),
            ('AC_var_B',                decoder.decode_16bit_int()),
            ('AC_var_C',                decoder.decode_16bit_int()),
            ('AC_var_SF',               decoder.decode_16bit_int()),
            ('AC_PF',                   decoder.decode_16bit_int()),
            ('AC_PF_A',                 decoder.decode_16bit_int()),
            ('AC_PF_B',                 decoder.decode_16bit_int()),
            ('AC_PF_C',                 decoder.decode_16bit_int()),
            ('AC_PF_SF',                decoder.decode_16bit_int()),
            ('AC_Energy_WH_Exported',   decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Exported_A', decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Exported_B', decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Exported_C', decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Imported',   decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Imported_A', decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Imported_B', decoder.decode_32bit_uint()),
            ('AC_Energy_WH_Imported_C', decoder.decode_32bit_uint()),
            ('AC_Energy_WH_SF',         decoder.decode_16bit_int()),
            ('M_VAh_Exported',          decoder.decode_32bit_uint()),
            ('M_VAh_Exported_A',        decoder.decode_32bit_uint()),
            ('M_VAh_Exported_B',        decoder.decode_32bit_uint()),
            ('M_VAh_Exported_C',        decoder.decode_32bit_uint()),
            ('M_VAh_Imported',          decoder.decode_32bit_uint()),
            ('M_VAh_Imported_A',        decoder.decode_32bit_uint()),
            ('M_VAh_Imported_B',        decoder.decode_32bit_uint()),
            ('M_VAh_Imported_C',        decoder.decode_32bit_uint()),
            ('M_VAh_SF',                decoder.decode_16bit_int()),
            ('M_varh_Import_Q1',      decoder.decode_32bit_uint()),
            ('M_varh_Import_Q1_A',    decoder.decode_32bit_uint()),
            ('M_varh_Import_Q1_B',    decoder.decode_32bit_uint()),
            ('M_varh_Import_Q1_C',    decoder.decode_32bit_uint()),
            ('M_varh_Import_Q2',      decoder.decode_32bit_uint()),
            ('M_varh_Import_Q2_A',    decoder.decode_32bit_uint()),
            ('M_varh_Import_Q2_B',    decoder.decode_32bit_uint()),
            ('M_varh_Import_Q2_C',    decoder.decode_32bit_uint()),
            ('M_varh_Export_Q3',      decoder.decode_32bit_uint()),
            ('M_varh_Export_Q3_A',    decoder.decode_32bit_uint()),
            ('M_varh_Export_Q3_B',    decoder.decode_32bit_uint()),
            ('M_varh_Export_Q3_C',    decoder.decode_32bit_uint()),
            ('M_varh_Export_Q4',      decoder.decode_32bit_uint()),
            ('M_varh_Export_Q4_A',    decoder.decode_32bit_uint()),
            ('M_varh_Export_Q4_B',    decoder.decode_32bit_uint()),
            ('M_varh_Export_Q4_C',  decoder.decode_32bit_uint()),
            ('M_varh_SF',               decoder.decode_16bit_int()),
            ('M_Events',                decoder.decode_32bit_uint()),
      ])
        
        for name, value in iteritems(self.decoded_model):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)
 
    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        


class SolarEdgeBattery:    
    def __init__(self, device_id: int, battery_id: int, hub: SolarEdgeModbusMultiHub) -> None:

        self.inverter_unit_id = device_id
        self.hub = hub
        self._callbacks = set()
        self.start_address = None
 
        if battery_id == 1:
            self.start_address = 57600
        elif battery_id == 2:
            self.start_address = 57856
        else:
            raise ValueError("Invalid battery_id")

        battery_info = hub.read_holding_registers(
            unit=self.inverter_unit_id, address=self.start_address, count=75
        )
        if battery_info.isError():
            _LOGGER.debug(battery_info)
            raise RuntimeError(battery_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            battery_info.registers, byteorder=Endian.Big
        )
        decoded_ident = OrderedDict([
            ('B_Manufacturer', parse_modbus_string(decoder.decode_string(32))),
            ('B_Model', parse_modbus_string(decoder.decode_string(32))),
            ('B_Version', parse_modbus_string(decoder.decode_string(32))),
            ('B_SerialNumber', parse_modbus_string(decoder.decode_string(32))),
            ('B_Device_address', decoder.decode_16bit_uint()),
            ('Reserved', decoder.decode_16bit_uint()),
            ('B_RatedEnergy', decoder.decode_32bit_float()),
            ('B_MaxChargePower', decoder.decode_32bit_float()),
            ('B_MaxDischargePower', decoder.decode_32bit_float()),
            ('B_MaxChargePeakPower', decoder.decode_32bit_float()),
            ('B_MaxDischargePeakPower', decoder.decode_32bit_float()),
        ])

        for name, value in iteritems(decoded_common):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)

        _LOGGER.warning("Battery registers are not officially supported by SolarEdge. Use at your own risk!")

        self.manufacturer = decoded_ident['B_Manufacturer']
        self.model = decoded_ident['B_Model']
        self.option = None
        self.fw_version = decoded_ident['B_Version']
        self.serial = decoded_ident['B_SerialNumber']
        self.device_address = decoded_ident['B_Device_address']
        self.name = f"{hub.hub_id.capitalize()} B{self.inverter_unit_id}-{battery_id}"

        self._device_info = {
            "identifiers": {(DOMAIN, f"{self.model}_{self.serial}")},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when SolarEdgeBattery changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self) -> None:
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        
