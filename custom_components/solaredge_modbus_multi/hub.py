import logging
import threading

from typing import Optional
from datetime import timedelta

from pymodbus.client.sync import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

from homeassistant.core import callback
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
        hass,
        name,
        host,
        port,
        scan_interval,
        number_of_inverters=1,
        device_id=1,
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._client = ModbusTcpClient(host=host, port=port)
        self._lock = threading.Lock()
        self._name = name
        self.read_meter1 = False
        self.read_meter2 = False
        self.read_meter3 = False
        self.number_of_inverters = number_of_inverters
        self.device_id = device_id
        self._scan_interval = timedelta(seconds=scan_interval)
        self._unsub_interval_method = None
        self._sensors = []
        self.data = {}
        
        self.se_inverters = []
        self.se_meters = []

    async def async_init_solaredge(self) -> None:
        
        for inverter_index in range(self.number_of_inverters):
            inverter_unit_id = inverter_index + self.device_id
            self.se_inverters.append(SolarEdgeInverter(inverter_unit_id, self))
        
        if self.read_meter1 == True:
            self.se_meters.append(SolarEdgeMeter(self.device_id, 1, self))

        if self.read_meter2 == True:
            self.se_meters.append(SolarEdgeMeter(self.device_id, 2, self))

        if self.read_meter3 == True:
            self.se_meters.append(SolarEdgeMeter(self.device_id, 3, self))

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

    def read_holding_registers(self, unit, address, count):
        """Read holding registers."""
        with self._lock:
            kwargs = {"unit": unit} if unit else {}
            return self._client.read_holding_registers(address, count, **kwargs)

    def read_modbus_data(self):
        return (
            self.read_modbus_data_inverters()
            and self.read_modbus_data_meter1()
            and self.read_modbus_data_meter2()
            and self.read_modbus_data_meter3()
        )

    def read_modbus_data_inverters(self):
        """start reading inverter data"""
        for inverter_index in range(self.number_of_inverters):
            try:
                raise NotImplementedError
                            
            except Exception as error:
                _LOGGER.error("Error reading inverter at id %s: %s", inverter_unit_id, error)
                return False

        return True

    def read_modbus_data_meter1(self):
        if not self.read_meter1:
            return True
        else:
            return self.read_modbus_data_meter("m1_", 40000 + 121)

    def read_modbus_data_meter2(self):
        if not self.read_meter2:
            return True
        else:
            return self.read_modbus_data_meter("m2_", 40000 + 295)

    def read_modbus_data_meter3(self):
        if not self.read_meter3:
            return True
        else:
            return self.read_modbus_data_meter("m3_", 40000 + 469)

    def read_modbus_data_meter(self, meter_prefix, start_address):
        """start reading meter data"""
        try:
            raise NotImplementedError
            
        except Exception as error:
            _LOGGER.error("Error reading meter on inverter %s: %s", self.device_id, error)
            return False

        return True


class SolarEdgeInverter:
    def __init__(self, device_id: int, hub: SolarEdgeModbusHub) -> None:

        inverter_prefix = "i" + str(inverter_index + 1) + "_"
        inverter_unit_id = inverter_index + self.device_id
        
        inverter_data = hub.read_holding_registers(
            unit=inverter_unit_id, address=40000, count=4
        )
        assert(not inverter_data.isError())
        
        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.Big
        )

        decoded_ident = OrderedDict([
            ('C_SunSpec_ID', decoder.decode_32bit_uint()),
            ('C_SunSpec_DID', decoder.decode_16bit_uint()),
            ('C_SunSpec_Length', decoder.decode_16bit_uint()),
        ])
        
        inverter_data = hub.read_holding_registers(
            unit=inverter_unit_id, address=40004, count=decoded_ident['C_SunSpec_Length']
        )
        assert(not inverter_data.isError())
   
        decoded_common = OrderedDict([
            ('C_Manufacturer', parse_modbus_string(decoder.decode_string(32))),
            ('C_Model', parse_modbus_string(decoder.decode_string(32))),
            ('C_Option', parse_modbus_string(decoder.decode_string(16))),
            ('C_Version', parse_modbus_string(decoder.decode_string(16))),
            ('C_SerialNumber', parse_modbus_string(decoder.decode_string(32))),
            ('C_Device_address', decoder.decode_16bit_uint()),
        ])
        
        self.model = decoded_common['C_Model']
        self.option = decoded_common['C_Opt']
        self.serial = decoded_common['C_SerialNumber']
        self.firmware_version = decoded_common['C_Version']
        
        self._device_info = {
            "identifiers": {(DOMAIN, self.hub.name)},
            "name": f"{hub.name.capitalize()} Inverter {device_id}",
            "manufacturer": decoded_common['C_Manufacturer'],
            "model": self.model,
            "sw_version": self.firmware_version,
        }


    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        


class SolarEdgeMeter:
    def __init__(self, device_id: int, meter_id: int, hub: SolarEdgeModbusHub) -> None:
        
        if meter_id == 1:
            start_address = 40000 + 121
        elif meter_id == 2:
            start_address = 40000 + 295
        elif meter_id == 2:
            start_address = 40000 + 469
        else:
            raise ValueError("Invalid meter_id")

        meter_info = self.read_holding_registers(
            unit=self.device_id, address=start_address, count=2
        )
        assert(not meter_info.isError())

        decoder = BinaryPayloadDecoder.fromRegisters(
            meter_info.registers, byteorder=Endian.Big
        )
        decoded_ident = OrderedDict([
            ('C_SunSpec_DID', decoder.decode_16bit_uint()),
            ('C_SunSpec_Length', decoder.decode_16bit_uint()),
        ])
        
        meter_info = self.read_holding_registers(
            unit=self.device_id, address=start_address + 2, count=decoded_ident['C_SunSpec_Length']
        )
        assert(not meter_info.isError())

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

        self.model = decoded_common['C_Model']
        self.option = decoded_common['C_Opt']
        self.serial = decoded_common['C_SerialNumber']
        self.firmware_version = decoded_common['C_Version']

        self._device_info = {
            "identifiers": {(DOMAIN, self.hub.name)},
            "name": f"{hub.name.capitalize()} Meter {meter_id}",
            "manufacturer": decoded_common['C_Manufacturer'],
            "model": self.model,
            "sw_version": self.firmware_version,
        }

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info


class SolarEdgeBattery:
    def __init__(self, device_id: int, battery_id: int, hub: SolarEdgeModbusHub) -> None:

        self._device_info = {
            "identifiers": {(DOMAIN, self.hub.name)},
            "name": f"{hub.name.capitalize()} Battery {battery_id}",
            "manufacturer": ATTR_MANUFACTURER,
            "model": self.model,
            "sw_version": self.firmware_version,
        }

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        
