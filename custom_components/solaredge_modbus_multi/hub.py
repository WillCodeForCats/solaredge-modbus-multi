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
    DEVICE_STATUS, VENDOR_STATUS,
    SUNSPEC_NOT_IMPL_INT16, SUNSPEC_NOT_IMPL_UINT16,
    SUNSPEC_NOT_IMPL_UINT32, SUNSPEC_NOT_ACCUM_ACC32,
    SUNSPEC_ACCUM_LIMIT
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
        self._client = ModbusTcpClient(host=host, port=port)
        self._lock = threading.Lock()
        self._name = name
        self.number_of_inverters = number_of_inverters
        self.start_device_id = start_device_id
        self._scan_interval = timedelta(seconds=scan_interval)
        self._unsub_interval_method = None
        self._sensors = []
        self.data = {}
        
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
            except:
                raise ConfigEntryNotReady(f"Inverter device ID {inverter_unit_id} not found.")
                _LOGGER.error(f"Inverter device ID {inverter_unit_id} not found.")
        
            try:
                _LOGGER.debug(f"Looking for meter 1 on inverter ID {inverter_unit_id}")
                self.meters.append(SolarEdgeMeter(inverter_unit_id, 1, self))
                _LOGGER.debug(f"Found meter 1 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                _LOGGER.debug(f"Looking for meter 2 on inverter ID {inverter_unit_id}")
                self.meters.append(SolarEdgeMeter(inverter_unit_id, 2, self))
                _LOGGER.debug(f"Found meter 2 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                _LOGGER.debug(f"Looking for meter 3 on inverter ID {inverter_unit_id}")
                self.meters.append(SolarEdgeMeter(inverter_unit_id, 3, self))
                _LOGGER.debug(f"Found meter 3 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                _LOGGER.debug(f"Looking for battery 1 on inverter ID {inverter_unit_id}")
                self.batteries.append(SolarEdgeBattery(inverter_unit_id, 1, self))
                _LOGGER.debug(f"Found battery 1 on inverter ID {inverter_unit_id}")
            except:
                pass

            try:
                _LOGGER.debug(f"Looking for battery 2 on inverter ID {inverter_unit_id}")
                self.batteries.append(SolarEdgeBattery(inverter_unit_id, 2, self))
                _LOGGER.debug(f"Found battery 2 on inverter ID {inverter_unit_id}")
            except:
                pass

        self.online = True
        self.close() # for dev only

    @callback
    def async_add_solaredge_sensor(self, update_callback):
        """Listen for data updates."""
        # This is the first sensor, set up interval.
        if not self._sensors:
            self._unsub_interval_method = async_track_time_interval(
                self._hass, self.async_refresh_modbus_data, self._scan_interval
            )

        self._sensors.append(update_callback)

    @callback
    def async_remove_solaredge_sensor(self, update_callback):
        """Remove data update."""
        self._sensors.remove(update_callback)
        
        if self.is_socket_open():
            self.close()

        if not self._sensors:
            """stop the interval timer upon removal of last sensor"""
            self._unsub_interval_method()
            self._unsub_interval_method = None

    async def async_refresh_modbus_data(self, _now: Optional[int] = None) -> None:
        """Time to update."""
        if not self._sensors:
            return

        self.connect()
        
        if not self.is_socket_open():
            _LOGGER.error("Could not open Modbus/TCP connection for %s", self._name)
        else:
            update_result = self.read_modbus_data()
            if update_result:
              for update_callback in self._sensors:
                    update_callback()
        
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
        
        inverter_data = hub.read_holding_registers(
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
       
        inverter_data = hub.read_holding_registers(
            unit=self.inverter_unit_id, address=40004, count=65
        )
        if inverter_data.isError():
            _LOGGER.error(inverter_data)
            raise RuntimeError(inverter_data)
        

        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )
   
        decoded_common = OrderedDict([
            ('C_Manufacturer', parse_modbus_string(decoder.decode_string(32))),
            ('C_Model', parse_modbus_string(decoder.decode_string(32))),
            ('C_Option', parse_modbus_string(decoder.decode_string(16))),
            ('C_Version', parse_modbus_string(decoder.decode_string(16))),
            ('C_SerialNumber', parse_modbus_string(decoder.decode_string(32))),
            ('C_Device_address', decoder.decode_16bit_uint()),
        ])
        
        for name, value in iteritems(decoded_common):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)

        self.manufacturer = decoded_common['C_Manufacturer']
        self.model = decoded_common['C_Model']
        self.option = decoded_common['C_Option']
        self.fw_version = decoded_common['C_Version']
        self.serial = decoded_common['C_SerialNumber']
        self.device_address = decoded_common['C_Device_address']
        self.name = f"{hub.hub_id.capitalize()} I{self.inverter_unit_id}"
        
        self._device_info = {
            "identifiers": {(DOMAIN, f"{self.model}_{self.serial}")},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

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
        
        if meter_id == 1:
            start_address = 40000 + 121
        elif meter_id == 2:
            start_address = 40000 + 295
        elif meter_id == 3:
            start_address = 40000 + 469
        else:
            raise ValueError("Invalid meter_id")

        meter_info = hub.read_holding_registers(
            unit=self.inverter_unit_id, address=start_address, count=2
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
            unit=self.inverter_unit_id, address=start_address + 2, count=65
        )
        if meter_info.isError():
            _LOGGER.debug(meter_info)
            raise RuntimeError(meter_info)

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_info.registers, byteorder=Endian.Big
        )
        decoded_common = OrderedDict([
            ('C_Manufacturer', parse_modbus_string(decoder.decode_string(32))),
            ('C_Model', parse_modbus_string(decoder.decode_string(32))),
            ('C_Option', parse_modbus_string(decoder.decode_string(16))),
            ('C_Version', parse_modbus_string(decoder.decode_string(16))),
            ('C_SerialNumber', parse_modbus_string(decoder.decode_string(32))),
            ('C_Device_address', decoder.decode_16bit_uint()),
        ])

        for name, value in iteritems(decoded_common):
            _LOGGER.debug("%s %s", name, hex(value) if isinstance(value, int) else value)

        self.manufacturer = decoded_common['C_Manufacturer']
        self.model = decoded_common['C_Model']
        self.option = decoded_common['C_Option']
        self.fw_version = decoded_common['C_Version']
        self.serial = decoded_common['C_SerialNumber']
        self.device_address = decoded_common['C_Device_address']
        self.name = f"{hub.hub_id.capitalize()} M{self.inverter_unit_id}-{meter_id}"

        self._device_info = {
            "identifiers": {(DOMAIN, f"{self.model}_{self.serial}")},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.fw_version,
            "hw_version": self.option,
        }

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
        
        if battery_id == 1:
            start_address = 57600
        elif battery_id == 2:
            start_address = 57856
        else:
            raise ValueError("Invalid battery_id")

        battery_info = hub.read_holding_registers(
            unit=self.inverter_unit_id, address=start_address, count=75
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

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        
