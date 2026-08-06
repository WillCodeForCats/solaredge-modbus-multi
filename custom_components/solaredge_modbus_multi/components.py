"""SolarEdge components for modbus-connection device modelling."""

from __future__ import annotations

from modbus_connection.model import Component, integer, string, uint32


class InverterCommon(Component):
    """Inverter common block is only read once at setup."""

    C_SunSpec_ID = uint32(40000)
    C_SunSpec_DID = integer(40002, signed=False)
    C_SunSpec_Length = integer(40003, signed=False)
    C_Manufacturer = string(40004, 16)
    C_Model = string(40020, 16)
    C_Option = string(40036, 8)
    C_Version = string(40044, 8)
    C_SerialNumber = string(40052, 16)
    C_Device_address = integer(40068, signed=False)


class MmpptCommon(Component):
    """MMPPT common block is only read once at setup."""

    mmppt_DID = integer(40121, signed=False)
    mmppt_Length = integer(40122, signed=False)
    mmppt_Units = integer(40129, signed=False)
