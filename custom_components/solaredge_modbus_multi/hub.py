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
    DEVICE_STATUS, VENDOR_STATUS,
    SUNSPEC_NOT_IMPL_INT16, SUNSPEC_NOT_IMPL_UINT16,
    SUNSPEC_NOT_IMPL_UINT32, SUNSPEC_NOT_ACCUM_ACC32,
    SUNSPEC_ACCUM_LIMIT
)

_LOGGER = logging.getLogger(__name__)

class SolarEdgeModbusHub:
    """Thread safe wrapper class for pymodbus."""

    def __init__(
        self,
        hass,
        name,
        host,
        port,
        scan_interval,
        read_meter1=False,
        read_meter2=False,
        read_meter3=False,
        number_of_inverters=1,
        device_id=1,
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._client = ModbusTcpClient(host=host, port=port)
        self._lock = threading.Lock()
        self._name = name
        self.read_meter1 = read_meter1
        self.read_meter2 = read_meter2
        self.read_meter3 = read_meter3
        self.number_of_inverters = number_of_inverters
        self.device_id = device_id
        self._scan_interval = timedelta(seconds=scan_interval)
        self._unsub_interval_method = None
        self._sensors = []
        self.data = {}
        
        self.se_inverters = []
        self.se_meters = []

    async def _async_init_solaredge(self) -> None:
        
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

    def scale_factor(self, value: int, sf: int):
        try:
            return value * (10 ** sf)
        except ZeroDivisionError:
            return 0
        
    def watts_to_kilowatts(self, value):
        return round(value * 0.001, 3)

    def parse_modbus_string(self, s: str) -> str:
        return s.decode(encoding="utf-8", errors="ignore").replace("\x00", "").rstrip()

    def update_accum(self, key: str, raw: int, current: int) -> None:
        try:
            last = self.data[key]
        except KeyError:
            last = 0
            
        if last is None:
            last = 0

        if not raw > 0:
            raise ValueError(f"update_accum {key} must be non-zero value.")
                
        if current >= last:
            # doesn't account for accumulator rollover, but it would probably take
            # several decades to roll over to 0 so we'll worry about it later
            self.data[key] = current    
        else:
            raise ValueError(f"update_accum {key} must be an increasing value.")

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
                inverter_prefix = "i" + str(inverter_index + 1) + "_"
                inverter_unit_id = inverter_index + self.device_id
                
                inverter_data = self.read_holding_registers(
                    unit=inverter_unit_id, address=40004, count=108
                )
                assert(not inverter_data.isError())
                
                decoder = BinaryPayloadDecoder.fromRegisters(
                    inverter_data.registers, byteorder=Endian.Big
                )
            
                cmanufacturer = decoder.decode_string(32)
                self.data[inverter_prefix + "manufacturer"] = self.parse_modbus_string(cmanufacturer)
            
                cmodel = decoder.decode_string(32)
                self.data[inverter_prefix + "model"] = self.parse_modbus_string(cmodel)

                decoder.skip_bytes(16)
            
                cversion = decoder.decode_string(16)
                self.data[inverter_prefix + "version"] = self.parse_modbus_string(cversion)

                cserialnumber = decoder.decode_string(32)
                self.data[inverter_prefix + "serialnumber"] = self.parse_modbus_string(cserialnumber)

                cdeviceaddress = decoder.decode_16bit_uint()
                self.data[inverter_prefix + "deviceaddress"] = cdeviceaddress

                sunspecdid = decoder.decode_16bit_uint()
                self.data[inverter_prefix + "sunspecdid"] = sunspecdid
            
                # skip register
                decoder.skip_bytes(2)
            
                accurrent = decoder.decode_16bit_uint()
                accurrenta = decoder.decode_16bit_uint()
                accurrentb = decoder.decode_16bit_uint()
                accurrentc = decoder.decode_16bit_uint()
                accurrentsf = decoder.decode_16bit_int()

                if (accurrent == SUNSPEC_NOT_IMPL_UINT16 or accurrentsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "accurrent"] = None
                else:
                    accurrent = self.scale_factor(accurrent, accurrentsf)
                    self.data[inverter_prefix + "accurrent"] = round(accurrent, abs(accurrentsf))

                if (accurrenta == SUNSPEC_NOT_IMPL_UINT16 or accurrentsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "accurrenta"] = None
                else:
                    accurrenta = self.scale_factor(accurrenta, accurrentsf)
                    self.data[inverter_prefix + "accurrenta"] = round(accurrenta, abs(accurrentsf))
                    
                if (accurrentb == SUNSPEC_NOT_IMPL_UINT16 or accurrentsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "accurrentb"] = None
                else:
                    accurrentb = self.scale_factor(accurrentb, accurrentsf)
                    self.data[inverter_prefix + "accurrentb"] = round(accurrentb, abs(accurrentsf))
                   
                if  (accurrentc == SUNSPEC_NOT_IMPL_UINT16 or accurrentsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "accurrentc"] = None
                else:
                    accurrentc = self.scale_factor(accurrentc, accurrentsf)
                    self.data[inverter_prefix + "accurrentc"] = round(accurrentc, abs(accurrentsf))

                acvoltageab = decoder.decode_16bit_uint()
                acvoltagebc = decoder.decode_16bit_uint()
                acvoltageca = decoder.decode_16bit_uint()
                acvoltagean = decoder.decode_16bit_uint()
                acvoltagebn = decoder.decode_16bit_uint()
                acvoltagecn = decoder.decode_16bit_uint()
                acvoltagesf = decoder.decode_16bit_int()

                if (acvoltageab == SUNSPEC_NOT_IMPL_UINT16 or acvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvoltageab"] = None
                else:
                    acvoltageab = self.scale_factor(acvoltageab, acvoltagesf)
                    self.data[inverter_prefix + "acvoltageab"] = round(acvoltageab, abs(acvoltagesf))

                if (acvoltagebc == SUNSPEC_NOT_IMPL_UINT16 or acvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvoltagebc"] = None
                else:                
                    acvoltagebc = self.scale_factor(acvoltagebc, acvoltagesf)
                    self.data[inverter_prefix + "acvoltagebc"] = round(acvoltagebc, abs(acvoltagesf))

                if (acvoltageca == SUNSPEC_NOT_IMPL_UINT16 or acvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvoltageca"] = None
                else:
                    acvoltageca = self.scale_factor(acvoltageca, acvoltagesf)
                    self.data[inverter_prefix + "acvoltageca"] = round(acvoltageca, abs(acvoltagesf))

                if (acvoltagean == SUNSPEC_NOT_IMPL_UINT16 or acvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvoltagean"] = None
                else:
                    acvoltagean = self.scale_factor(acvoltagean, acvoltagesf)
                    self.data[inverter_prefix + "acvoltagean"] = round(acvoltagean, abs(acvoltagesf))

                if (acvoltagebn == SUNSPEC_NOT_IMPL_UINT16 or acvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvoltagebn"] = None
                else:
                    acvoltagebn = self.scale_factor(acvoltagebn, acvoltagesf)
                    self.data[inverter_prefix + "acvoltagebn"] = round(acvoltagebn, abs(acvoltagesf))

                if (acvoltagecn == SUNSPEC_NOT_IMPL_UINT16 or acvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvoltagecn"] = None
                else:
                    acvoltagecn = self.scale_factor(acvoltagecn, acvoltagesf)
                    self.data[inverter_prefix + "acvoltagecn"] = round(acvoltagecn, abs(acvoltagesf))
                
                acpower = decoder.decode_16bit_int()
                acpowersf = decoder.decode_16bit_int()

                if (acpower == SUNSPEC_NOT_IMPL_INT16 or acpowersf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acpower"] = None
                else:
                    acpower = self.scale_factor(acpower, acpowersf)
                    self.data[inverter_prefix + "acpower"] = round(acpower, abs(acpowersf))

                acfreq = decoder.decode_16bit_uint()
                acfreqsf = decoder.decode_16bit_int()
                
                if (acfreq == SUNSPEC_NOT_IMPL_UINT16 or acfreqsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acfreq"] = None
                else:
                    acfreq = self.scale_factor(acfreq, acfreqsf)
                    self.data[inverter_prefix + "acfreq"] = round(acfreq, abs(acfreqsf))

                acva = decoder.decode_16bit_int()
                acvasf = decoder.decode_16bit_int()
                
                if (acva == SUNSPEC_NOT_IMPL_INT16 or acvasf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acva"] = None
                else:                
                    acva = self.scale_factor(acva, acvasf)
                    self.data[inverter_prefix + "acva"] = round(acva, abs(acvasf))

                acvar = decoder.decode_16bit_int()
                acvarsf = decoder.decode_16bit_int()
                
                if (acvar == SUNSPEC_NOT_IMPL_INT16 or acvarsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acvar"] = None
                else:
                    acvar = self.scale_factor(acvar, acvarsf)
                    self.data[inverter_prefix + "acvar"] = round(acvar, abs(acvarsf))

                acpf = decoder.decode_16bit_int()
                acpfsf = decoder.decode_16bit_int()
                
                if (acpf == SUNSPEC_NOT_IMPL_INT16 or acpfsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "acpf"] = None
                else:
                    acpf = self.scale_factor(acpf, acpfsf)
                    self.data[inverter_prefix + "acpf"] = round(acpf, abs(acpfsf))

                acenergy = decoder.decode_32bit_uint()
                acenergysf = decoder.decode_16bit_uint()

                if (
                    acenergy == SUNSPEC_NOT_ACCUM_ACC32 or
                    acenergy > SUNSPEC_ACCUM_LIMIT or
                    acenergysf == SUNSPEC_NOT_IMPL_UINT16
                ):
                    self.data[inverter_prefix + "acenergy"] = None
                else:
                    acenergy = self.scale_factor(acenergy, acenergysf)
                    acenergy_kw = self.watts_to_kilowatts(acenergy)
                    self.update_accum(f"{inverter_prefix}acenergy", acenergy, acenergy_kw)

                dccurrent = decoder.decode_16bit_uint()
                dccurrentsf = decoder.decode_16bit_int()

                if (dccurrent == SUNSPEC_NOT_IMPL_UINT16 or dccurrentsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "dccurrent"] = None
                else:
                    dccurrent = self.scale_factor(dccurrent, dccurrentsf)
                    self.data[inverter_prefix + "dccurrent"] = round(dccurrent, abs(dccurrentsf))

                dcvoltage = decoder.decode_16bit_uint()
                dcvoltagesf = decoder.decode_16bit_int()
                
                if (dcvoltage == SUNSPEC_NOT_IMPL_UINT16 or dcvoltagesf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "dcvoltage"] = None
                else:                    
                    dcvoltage = self.scale_factor(dcvoltage, dcvoltagesf)
                    self.data[inverter_prefix + "dcvoltage"] = round(dcvoltage, abs(dcvoltagesf))

                dcpower = decoder.decode_16bit_int()
                dcpowersf = decoder.decode_16bit_int()
                
                if (dcpower == SUNSPEC_NOT_IMPL_INT16 or dcpowersf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "dcpower"] = None
                else:
                    dcpower = self.scale_factor(dcpower, dcpowersf)
                    self.data[inverter_prefix + "dcpower"] = round(dcpower, abs(dcpowersf))

                # skip register
                decoder.skip_bytes(2)

                tempsink = decoder.decode_16bit_int()

                # skip 2 registers
                decoder.skip_bytes(4)

                tempsf = decoder.decode_16bit_int()
                
                if (tempsink == SUNSPEC_NOT_IMPL_INT16 or tempsf == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "tempsink"] = None
                else:
                    tempsink = self.scale_factor(tempsink, tempsf)
                    self.data[inverter_prefix + "tempsink"] = round(tempsink, abs(tempsf))

                status = decoder.decode_16bit_int()
                
                if (status == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "status"] = None
                else:
                    self.data[inverter_prefix + "status"] = status
            
                if status in DEVICE_STATUS:
                    self.data[inverter_prefix + "status_text"] = DEVICE_STATUS[status]
                else:
                    self.data[inverter_prefix + "status_text"] = "Unknown"
            
                statusvendor = decoder.decode_16bit_int()
                
                if (statusvendor == SUNSPEC_NOT_IMPL_INT16):
                    self.data[inverter_prefix + "statusvendor"] = None
                else:
                    self.data[inverter_prefix + "statusvendor"] = statusvendor
            
                if statusvendor in VENDOR_STATUS:
                    self.data[inverter_prefix + "statusvendor_text"] = VENDOR_STATUS[statusvendor]
                else:
                    self.data[inverter_prefix + "statusvendor_text"] = "Unknown"
            
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
            meter_info = self.read_holding_registers(
                unit=self.device_id, address=start_address, count=68
            )
            assert(not meter_info.isError())

            decoder = BinaryPayloadDecoder.fromRegisters(
                meter_info.registers, byteorder=Endian.Big
            )

            decoder.skip_bytes(4)

            cmanufacturer = decoder.decode_string(32)
            self.data[meter_prefix + "manufacturer"] = self.parse_modbus_string(cmanufacturer)
        
            cmodel = decoder.decode_string(32)
            self.data[meter_prefix + "model"] = self.parse_modbus_string(cmodel)

            copt = decoder.decode_string(16)
            self.data[meter_prefix + "option"] = self.parse_modbus_string(copt)

            cversion = decoder.decode_string(16)
            self.data[meter_prefix + "version"] = self.parse_modbus_string(cversion)

            cserialnumber = decoder.decode_string(32)
            self.data[meter_prefix + "serialnumber"] = self.parse_modbus_string(cserialnumber)

            cdeviceaddress = decoder.decode_16bit_uint()
            self.data[meter_prefix + "deviceaddress"] = cdeviceaddress

            sunspecdid = decoder.decode_16bit_uint()
            self.data[meter_prefix + "sunspecdid"] = sunspecdid

        except Exception as error:
            _LOGGER.error("Error reading meter info on inverter %s: %s", self.device_id, error)
            return False

        try:
            meter_data = self.read_holding_registers(
                unit=self.device_id, address=start_address + 69, count=105
            )
            assert(not meter_data.isError())

            decoder = BinaryPayloadDecoder.fromRegisters(
                meter_data.registers, byteorder=Endian.Big
            )

            accurrent = decoder.decode_16bit_int()
            accurrenta = decoder.decode_16bit_int()
            accurrentb = decoder.decode_16bit_int()
            accurrentc = decoder.decode_16bit_int()
            accurrentsf = decoder.decode_16bit_int()

            accurrent = self.scale_factor(accurrent, accurrentsf)
            accurrenta = self.scale_factor(accurrenta, accurrentsf)
            accurrentb = self.scale_factor(accurrentb, accurrentsf)
            accurrentc = self.scale_factor(accurrentc, accurrentsf)

            self.data[meter_prefix + "accurrent"] = round(accurrent, abs(accurrentsf))
            self.data[meter_prefix + "accurrenta"] = round(accurrenta, abs(accurrentsf))
            self.data[meter_prefix + "accurrentb"] = round(accurrentb, abs(accurrentsf))
            self.data[meter_prefix + "accurrentc"] = round(accurrentc, abs(accurrentsf))

            acvoltageln = decoder.decode_16bit_int()
            acvoltagean = decoder.decode_16bit_int()
            acvoltagebn = decoder.decode_16bit_int()
            acvoltagecn = decoder.decode_16bit_int()
            acvoltagell = decoder.decode_16bit_int()
            acvoltageab = decoder.decode_16bit_int()
            acvoltagebc = decoder.decode_16bit_int()
            acvoltageca = decoder.decode_16bit_int()
            acvoltagesf = decoder.decode_16bit_int()

            acvoltageln = self.scale_factor(acvoltageln, acvoltagesf)
            acvoltagean = self.scale_factor(acvoltagean, acvoltagesf)
            acvoltagebn = self.scale_factor(acvoltagebn, acvoltagesf)
            acvoltagecn = self.scale_factor(acvoltagecn, acvoltagesf)
            acvoltagell = self.scale_factor(acvoltagell, acvoltagesf)
            acvoltageab = self.scale_factor(acvoltageab, acvoltagesf)
            acvoltagebc = self.scale_factor(acvoltagebc, acvoltagesf)
            acvoltageca = self.scale_factor(acvoltageca, acvoltagesf)

            self.data[meter_prefix + "acvoltageln"] = round(
                acvoltageln, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltagean"] = round(
                acvoltagean, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltagebn"] = round(
                acvoltagebn, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltagecn"] = round(
                acvoltagecn, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltagell"] = round(
                acvoltagell, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltageab"] = round(
                acvoltageab, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltagebc"] = round(
                acvoltagebc, abs(acvoltagesf)
            )
            self.data[meter_prefix + "acvoltageca"] = round(
                acvoltageca, abs(acvoltagesf)
            )

            acfreq = decoder.decode_16bit_int()
            acfreqsf = decoder.decode_16bit_int()

            acfreq = self.scale_factor(acfreq, acfreqsf)

            self.data[meter_prefix + "acfreq"] = round(acfreq, abs(acfreqsf))

            acpower = decoder.decode_16bit_int()
            acpowera = decoder.decode_16bit_int()
            acpowerb = decoder.decode_16bit_int()
            acpowerc = decoder.decode_16bit_int()
            acpowersf = decoder.decode_16bit_int()

            acpower = self.scale_factor(acpower, acpowersf)
            acpowera = self.scale_factor(acpowera, acpowersf)
            acpowerb = self.scale_factor(acpowerb, acpowersf)
            acpowerc = self.scale_factor(acpowerc, acpowersf)

            self.data[meter_prefix + "acpower"] = round(acpower, abs(acpowersf))
            self.data[meter_prefix + "acpowera"] = round(acpowera, abs(acpowersf))
            self.data[meter_prefix + "acpowerb"] = round(acpowerb, abs(acpowersf))
            self.data[meter_prefix + "acpowerc"] = round(acpowerc, abs(acpowersf))

            acva = decoder.decode_16bit_int()
            acvaa = decoder.decode_16bit_int()
            acvab = decoder.decode_16bit_int()
            acvac = decoder.decode_16bit_int()
            acvasf = decoder.decode_16bit_int()

            acva = self.scale_factor(acva, acvasf)
            acvaa = self.scale_factor(acvaa, acvasf)
            acvab = self.scale_factor(acvab, acvasf)
            acvac = self.scale_factor(acvac, acvasf)

            self.data[meter_prefix + "acva"] = round(acva, abs(acvasf))
            self.data[meter_prefix + "acvaa"] = round(acvaa, abs(acvasf))
            self.data[meter_prefix + "acvab"] = round(acvab, abs(acvasf))
            self.data[meter_prefix + "acvac"] = round(acvac, abs(acvasf))

            acvar = decoder.decode_16bit_int()
            acvara = decoder.decode_16bit_int()
            acvarb = decoder.decode_16bit_int()
            acvarc = decoder.decode_16bit_int()
            acvarsf = decoder.decode_16bit_int()

            acvar = self.scale_factor(acvar, acvarsf)
            acvara = self.scale_factor(acvara, acvarsf)
            acvarb = self.scale_factor(acvarb, acvarsf)
            acvarc = self.scale_factor(acvarc, acvarsf)

            self.data[meter_prefix + "acvar"] = round(acvar, abs(acvarsf))
            self.data[meter_prefix + "acvara"] = round(acvara, abs(acvarsf))
            self.data[meter_prefix + "acvarb"] = round(acvarb, abs(acvarsf))
            self.data[meter_prefix + "acvarc"] = round(acvarc, abs(acvarsf))

            acpf = decoder.decode_16bit_int()
            acpfa = decoder.decode_16bit_int()
            acpfb = decoder.decode_16bit_int()
            acpfc = decoder.decode_16bit_int()
            acpfsf = decoder.decode_16bit_int()

            acpf = self.scale_factor(acpf, acpfsf)
            acpfa = self.scale_factor(acpfa, acpfsf)
            acpfb = self.scale_factor(acpfb, acpfsf)
            acpfc = self.scale_factor(acpfc, acpfsf)

            self.data[meter_prefix + "acpf"] = round(acpf, abs(acpfsf))
            self.data[meter_prefix + "acpfa"] = round(acpfa, abs(acpfsf))
            self.data[meter_prefix + "acpfb"] = round(acpfb, abs(acpfsf))
            self.data[meter_prefix + "acpfc"] = round(acpfc, abs(acpfsf))

            exported = decoder.decode_32bit_uint()
            exporteda = decoder.decode_32bit_uint()
            exportedb = decoder.decode_32bit_uint()
            exportedc = decoder.decode_32bit_uint()
            imported = decoder.decode_32bit_uint()
            importeda = decoder.decode_32bit_uint()
            importedb = decoder.decode_32bit_uint()
            importedc = decoder.decode_32bit_uint()
            energywsf = decoder.decode_16bit_int()

            if (
                exported == SUNSPEC_NOT_ACCUM_ACC32 or 
                exported > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exported"] = None
            else:                
                exported = self.scale_factor(exported, energywsf)
                exported_kw = self.watts_to_kilowatts(exported)
                self.update_accum(f"{meter_prefix}exported", exported, exported_kw)
            
            if (
                exporteda == SUNSPEC_NOT_ACCUM_ACC32 or
                exporteda > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exporteda"] = None
            else:           
                exporteda = self.scale_factor(exporteda, energywsf)
                exporteda_kw = self.watts_to_kilowatts(exporteda)
                self.update_accum(f"{meter_prefix}exporteda", exporteda, exporteda_kw)
    
            if (
                exportedb == SUNSPEC_NOT_ACCUM_ACC32 or
                exportedb > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exportedb"] = None
            else:                   
                exportedb = self.scale_factor(exportedb, energywsf)
                exportedb_kw = self.watts_to_kilowatts(exportedb)
                self.update_accum(f"{meter_prefix}exportedb", exportedb, exportedb_kw)

            if (
                exportedc == SUNSPEC_NOT_ACCUM_ACC32 or
                exportedc > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exportedc"] = None
            else:                   
                exportedc = self.scale_factor(exportedc, energywsf)
                exportedc_kw = self.watts_to_kilowatts(exportedc)
                self.update_accum(f"{meter_prefix}exportedc", exportedc, exportedc_kw)

            if (
                imported == SUNSPEC_NOT_ACCUM_ACC32 or
                imported > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "imported"] = None
            else:                            
                imported = self.scale_factor(imported, energywsf)
                imported_kw = self.watts_to_kilowatts(imported)
                self.update_accum(f"{meter_prefix}imported", imported, imported_kw)

            if (
                importeda == SUNSPEC_NOT_ACCUM_ACC32 or
                importeda > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importeda"] = None
            else:                            
                importeda = self.scale_factor(importeda, energywsf)
                importeda_kw = self.watts_to_kilowatts(importeda)
                self.update_accum(f"{meter_prefix}importeda", importeda, importeda_kw)

            if (
                importedb == SUNSPEC_NOT_ACCUM_ACC32 or
                importedb > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importedb"] = None
            else:                            
                importedb = self.scale_factor(importedb, energywsf)
                importedb_kw = self.watts_to_kilowatts(importedb)
                self.update_accum(f"{meter_prefix}importedb", importedb, importedb_kw)

            if (
                importedc == SUNSPEC_NOT_ACCUM_ACC32 or
                importedc > SUNSPEC_ACCUM_LIMIT or
                energywsf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importedc"] = None
            else:                            
                importedc = self.scale_factor(importedc, energywsf)
                importedc_kw = self.watts_to_kilowatts(importedc)
                self.update_accum(f"{meter_prefix}importedc", importedc, importedc_kw)
                        
            exportedva = decoder.decode_32bit_uint()
            exportedvaa = decoder.decode_32bit_uint()
            exportedvab = decoder.decode_32bit_uint()
            exportedvac = decoder.decode_32bit_uint()
            importedva = decoder.decode_32bit_uint()
            importedvaa = decoder.decode_32bit_uint()
            importedvab = decoder.decode_32bit_uint()
            importedvac = decoder.decode_32bit_uint()
            energyvasf = decoder.decode_16bit_int()

            if (
                exportedva == SUNSPEC_NOT_ACCUM_ACC32 or 
                exportedva > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exportedva"] = None
            else:
                exportedva = self.scale_factor(exportedva, energyvasf)
                self.data[meter_prefix + "exportedva"] = round(
                    exportedva, abs(energyvasf)
                    )

            if (
                exportedvaa == SUNSPEC_NOT_ACCUM_ACC32 or 
                exportedvaa > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exportedvaa"] = None
            else:
                exportedvaa = self.scale_factor(exportedvaa, energyvasf)
                self.data[meter_prefix + "exportedvaa"] = round(
                    exportedvaa, abs(energyvasf)
                    )

            if (
                exportedvab == SUNSPEC_NOT_ACCUM_ACC32 or 
                exportedvab > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exportedvab"] = None
            else:
                exportedvab = self.scale_factor(exportedvab, energyvasf)
                self.data[meter_prefix + "exportedvab"] = round(
                    exportedvab, abs(energyvasf)
                    )  

            if (
                exportedvac == SUNSPEC_NOT_ACCUM_ACC32 or 
                exportedvac > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "exportedvac"] = None
            else:
                exportedvac = self.scale_factor(exportedvac, energyvasf)
                self.data[meter_prefix + "exportedvac"] = round(
                    exportedvac, abs(energyvasf)
                    )

            if (
                importedva == SUNSPEC_NOT_ACCUM_ACC32 or 
                importedva > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importedva"] = None
            else:
                importedva = self.scale_factor(importedva, energyvasf)
                self.data[meter_prefix + "importedva"] = round(
                    importedva, abs(energyvasf)
                    )

            if (
                importedvaa == SUNSPEC_NOT_ACCUM_ACC32 or 
                importedvaa > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importedvaa"] = None
            else:
                importedvaa = self.scale_factor(importedvaa, energyvasf)
                self.data[meter_prefix + "importedvaa"] = round(
                    importedvaa, abs(energyvasf)
                    )

            if (
                importedvab == SUNSPEC_NOT_ACCUM_ACC32 or 
                importedvab > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importedvab"] = None
            else:
                importedvab = self.scale_factor(importedvab, energyvasf)
                self.data[meter_prefix + "importedvab"] = round(
                    importedvab, abs(energyvasf)
                    )

            if (
                importedvac == SUNSPEC_NOT_ACCUM_ACC32 or 
                importedvac > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importedvac"] = None
            else:
                importedvac = self.scale_factor(importedvac, energyvasf)
                self.data[meter_prefix + "importedvac"] = round(
                    importedvac, abs(energyvasf)
                    )

            importvarhq1 = decoder.decode_32bit_uint()
            importvarhq1a = decoder.decode_32bit_uint()
            importvarhq1b = decoder.decode_32bit_uint()
            importvarhq1c = decoder.decode_32bit_uint()
            importvarhq2 = decoder.decode_32bit_uint()
            importvarhq2a = decoder.decode_32bit_uint()
            importvarhq2b = decoder.decode_32bit_uint()
            importvarhq2c = decoder.decode_32bit_uint()
            importvarhq3 = decoder.decode_32bit_uint()
            importvarhq3a = decoder.decode_32bit_uint()
            importvarhq3b = decoder.decode_32bit_uint()
            importvarhq3c = decoder.decode_32bit_uint()
            importvarhq4 = decoder.decode_32bit_uint()
            importvarhq4a = decoder.decode_32bit_uint()
            importvarhq4b = decoder.decode_32bit_uint()
            importvarhq4c = decoder.decode_32bit_uint()
            energyvarsf = decoder.decode_16bit_int()

            if (
                importvarhq1 == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq1 > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq1"] = None
            else:
                importvarhq1 = self.scale_factor(importvarhq1, energyvarsf)
                self.data[meter_prefix + "importvarhq1"] = round(
                    importvarhq1, abs(energyvarsf)
                )

            if (
                importvarhq1a == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq1a > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq1a"] = None
            else:
                importvarhq1a = self.scale_factor(importvarhq1a, energyvarsf)
                self.data[meter_prefix + "importvarhq1a"] = round(
                    importvarhq1a, abs(energyvarsf)
                )

            if (
                importvarhq1b == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq1b > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq1b"] = None
            else:
                importvarhq1b = self.scale_factor(importvarhq1b, energyvarsf)
                self.data[meter_prefix + "importvarhq1b"] = round(
                    importvarhq1b, abs(energyvarsf)
                )

            if (
                importvarhq1c == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq1c > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq1c"] = None
            else:
                importvarhq1c = self.scale_factor(importvarhq1c, energyvarsf)
                self.data[meter_prefix + "importvarhq1c"] = round(
                    importvarhq1c, abs(energyvarsf)
                )

            if (
                importvarhq2 == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq2 > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq2"] = None
            else:
                importvarhq2 = self.scale_factor(importvarhq2, energyvarsf)
                self.data[meter_prefix + "importvarhq2"] = round(
                    importvarhq2, abs(energyvarsf)
                )

            if (
                importvarhq2a == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq2a > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq2a"] = None
            else:
                importvarhq2a = self.scale_factor(importvarhq2a, energyvarsf)
                self.data[meter_prefix + "importvarhq2a"] = round(
                    importvarhq2a, abs(energyvarsf)
                )

            if (
                importvarhq2b == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq2b > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq2b"] = None
            else:
                importvarhq2b = self.scale_factor(importvarhq2b, energyvarsf)
                self.data[meter_prefix + "importvarhq2b"] = round(
                    importvarhq2b, abs(energyvarsf)
                )

            if (
                importvarhq2c == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq2c > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq2c"] = None
            else:
                importvarhq2c = self.scale_factor(importvarhq2c, energyvarsf)
                self.data[meter_prefix + "importvarhq2c"] = round(
                    importvarhq2c, abs(energyvarsf)
                )

            if (
                importvarhq3 == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq3 > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq3"] = None
            else:
                importvarhq3 = self.scale_factor(importvarhq3, energyvarsf)
                self.data[meter_prefix + "importvarhq3"] = round(
                    importvarhq3, abs(energyvarsf)
                )

            if (
                importvarhq3a == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq3a > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq3a"] = None
            else:
                importvarhq3a = self.scale_factor(importvarhq3a, energyvarsf)
                self.data[meter_prefix + "importvarhq3a"] = round(
                    importvarhq3a, abs(energyvarsf)
                )

            if (
                importvarhq3b == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq3b > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq3b"] = None
            else:
                importvarhq3b = self.scale_factor(importvarhq3b, energyvarsf)
                self.data[meter_prefix + "importvarhq3b"] = round(
                    importvarhq3b, abs(energyvarsf)
                )

            if (
                importvarhq3c == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq3c > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq3c"] = None
            else:
                importvarhq3c = self.scale_factor(importvarhq3c, energyvarsf)
                self.data[meter_prefix + "importvarhq3c"] = round(
                    importvarhq3c, abs(energyvarsf)
                )

            if (
                importvarhq4 == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq4 > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq4"] = None
            else:
                importvarhq4 = self.scale_factor(importvarhq4, energyvarsf)
                self.data[meter_prefix + "importvarhq4"] = round(
                    importvarhq4, abs(energyvarsf)
                )

            if (
                importvarhq4a == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq4a > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq4a"] = None
            else:
                importvarhq4a = self.scale_factor(importvarhq4a, energyvarsf)
                self.data[meter_prefix + "importvarhq4a"] = round(
                    importvarhq4a, abs(energyvarsf)
                )

            if (
                importvarhq4b == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq4b > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq4b"] = None
            else:
                importvarhq4b = self.scale_factor(importvarhq4b, energyvarsf)
                self.data[meter_prefix + "importvarhq4b"] = round(
                    importvarhq4b, abs(energyvarsf)
                )

            if (
                importvarhq4c == SUNSPEC_NOT_ACCUM_ACC32 or 
                importvarhq4c > SUNSPEC_ACCUM_LIMIT or
                energyvasf == SUNSPEC_NOT_IMPL_INT16
            ):
                self.data[meter_prefix + "importvarhq4c"] = None
            else:
                importvarhq4c = self.scale_factor(importvarhq4c, energyvarsf)
                self.data[meter_prefix + "importvarhq4c"] = round(
                    importvarhq4c, abs(energyvarsf)
                )
        
            meterevents = decoder.decode_32bit_uint()
            self.data[meter_prefix + "meterevents"] = hex(meterevents)

        except Exception as error:
            _LOGGER.error("Error reading meter on inverter %s: %s", self.device_id, error)
            return False

        return True

class SolarEdgeInverter:
    def __init__(self, device_id: int, hub: SolarEdgeModbusHub) -> None:

        self._device_info = {
            "identifiers": {(DOMAIN, self.hub.name)},
            "name": f"{hub.name.capitalize()} Inverter {device_id}",
            "manufacturer": ATTR_MANUFACTURER,
            #"model": self.model,
            #"sw_version": self.firmware_version,
        }

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        

class SolarEdgeMeter:
    def __init__(self, device_id: int, meter_id: int, hub: SolarEdgeModbusHub) -> None:

        self._device_info = {
            "identifiers": {(DOMAIN, self.hub.name)},
            "name": f"{hub.name.capitalize()} Meter {meter_id}",
            "manufacturer": ATTR_MANUFACTURER,
            #"model": self.model,
            #"sw_version": self.firmware_version,
        }

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info        
