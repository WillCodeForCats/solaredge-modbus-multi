"""SolarEdge components for modbus-connection device modelling."""

from __future__ import annotations

from typing import Any

from modbus_connection.model import Component, float32, integer, string, uint32

_ASCII_CTRL_CHARS = dict.fromkeys(range(32))


def component_to_dict(component: Component) -> dict[str, Any]:
    """Build a dict of field name to decoded value from a Component's declared fields."""
    return {name: getattr(component, name) for name in component.declared_fields}


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


class EvseCommon(InverterCommon):
    """
    EVSE common block is only read once at setup.
    SolarEdge EVSE devices present as an inverter, reuse InverterCommon.
    """


class MeterInfo(Component):
    """Meter info block is only read once at setup."""

    C_SunSpec_DID = integer(40121, signed=False)
    C_SunSpec_Length = integer(40122, signed=False)
    C_Manufacturer = string(40123, 16)
    C_Model = string(40139, 16)
    C_Option = string(40155, 8)
    C_Version = string(40163, 8)
    C_SerialNumber = string(40171, 16)
    C_Device_address = integer(40187, signed=False)


class BatteryInfo(Component):
    """Battery info block is only read once at setup."""

    _B_Manufacturer = string(57600, 16)
    _B_Model = string(57616, 16)
    B_Version = string(57632, 16)
    _B_SerialNumber = string(57648, 16)
    B_Device_Address = integer(57664, signed=False)
    B_RatedEnergy = float32(57666, unit="Wh", word_order="little")

    @property
    def B_Manufacturer(self) -> str | None:
        manufacturer = self._B_Manufacturer
        if manufacturer is None:
            return None
        serial = self._B_SerialNumber
        if serial is not None:
            manufacturer = manufacturer.removesuffix(serial)
        return manufacturer.translate(_ASCII_CTRL_CHARS)

    @property
    def B_Model(self) -> str | None:
        model = self._B_Model
        if model is None:
            return None
        serial = self._B_SerialNumber
        if serial is not None:
            model = model.removesuffix(serial)
        return model.translate(_ASCII_CTRL_CHARS)

    @property
    def B_SerialNumber(self) -> str | None:
        serial = self._B_SerialNumber
        if serial is None:
            return None
        return serial.translate(_ASCII_CTRL_CHARS)
