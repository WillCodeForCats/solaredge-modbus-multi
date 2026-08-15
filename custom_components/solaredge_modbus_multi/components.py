"""SolarEdge components for modbus-connection device modelling."""

from __future__ import annotations

from typing import Any

from modbus_connection.model import Component, float32, integer, string, uint32, uint64

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


class InverterData(Component):
    """Inverter data is read every polling cycle."""

    C_SunSpec_DID = integer(40069, signed=False)
    C_SunSpec_Length = integer(40070, signed=False)
    AC_Current = integer(40071, signed=False, unit="A")
    AC_Current_A = integer(40072, signed=False, unit="A")
    AC_Current_B = integer(40073, signed=False, unit="A")
    AC_Current_C = integer(40074, signed=False, unit="A")
    AC_Current_SF = integer(40075, signed=True)
    AC_Voltage_AB = integer(40076, signed=False, unit="V")
    AC_Voltage_BC = integer(40077, signed=False, unit="V")
    AC_Voltage_CA = integer(40078, signed=False, unit="V")
    AC_Voltage_AN = integer(40079, signed=False, unit="V")
    AC_Voltage_BN = integer(40080, signed=False, unit="V")
    AC_Voltage_CN = integer(40081, signed=False, unit="V")
    AC_Voltage_SF = integer(40082, signed=True)
    AC_Power = integer(40083, signed=True, unit="W")
    AC_Power_SF = integer(40084, signed=True)
    AC_Frequency = integer(40085, signed=False, unit="Hz")
    AC_Frequency_SF = integer(40086, signed=True)
    AC_VA = integer(40087, signed=True, unit="VA")
    AC_VA_SF = integer(40088, signed=True)
    AC_var = integer(40089, signed=True, unit="var")
    AC_var_SF = integer(40090, signed=True)
    AC_PF = integer(40091, signed=True, unit="%")
    AC_PF_SF = integer(40092, signed=True)
    AC_Energy_WH = uint32(40093, unit="Wh")
    AC_Energy_WH_SF = integer(40095, signed=False)
    I_DC_Current = integer(40096, signed=False, unit="A")
    I_DC_Current_SF = integer(40097, signed=True)
    I_DC_Voltage = integer(40098, signed=False, unit="V")
    I_DC_Voltage_SF = integer(40099, signed=True)
    I_DC_Power = integer(40100, signed=True, unit="W")
    I_DC_Power_SF = integer(40101, signed=True)
    I_Temp_Cab = integer(40102, signed=True, unit="C")  # unsupported on SolarEdge
    I_Temp_Sink = integer(40103, signed=True, unit="C")
    I_Temp_Trns = integer(40104, signed=True, unit="C")  # unsupported on SolarEdge
    I_Temp_Other = integer(40105, signed=True, unit="C")  # unsupported on SolarEdge
    I_Temp_SF = integer(40106, signed=True)
    I_Status = integer(40107, signed=False)
    I_Status_Vendor = integer(40108, signed=False)
    I_Grid_Status = integer(40113, signed=False)  # previously uint32 little endian
    I_Status_Vendor4 = uint32(40119)

    def restrict_status_vendor4(self, use_status_vendor4: bool) -> None:
        """Remove I_Status_Vendor4 on firmware that doesn't support it.

        modbus-connection only offers a keep-list with restrict_fields(), so
        excluding one means passing everything we still want back in.
        """
        if use_status_vendor4:
            return

        self.restrict_fields(
            [name for name in self.declared_fields if name != "I_Status_Vendor4"]
        )


class MmpptCommon(Component):
    """MMPPT common block is only read once at setup."""

    mmppt_DID = integer(40121, signed=False)
    mmppt_Length = integer(40122, signed=False)
    mmppt_Units = integer(40129, signed=False)


class MmpptUnit(Component):
    """MMPPT units are read every polling cycle."""

    mmppt_DCA_SF = integer(40123, signed=True)
    mmppt_DCV_SF = integer(40124, signed=True)
    mmppt_DCW_SF = integer(40125, signed=True)
    mmppt_DCWH_SF = integer(40126, signed=True)


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


class BatteryData(Component):
    """Battery data is read every polling cycle."""

    B_MaxChargePower = float32(57668, unit="W", word_order="little")
    B_MaxDischargePower = float32(57670, unit="W", word_order="little")
    B_MaxChargePeakPower = float32(57672, unit="W", word_order="little")
    B_MaxDischargePeakPower = float32(57674, unit="W", word_order="little")
    B_Temp_Average = float32(57708, word_order="little")
    B_Temp_Max = float32(57710, word_order="little")
    B_DC_Voltage = float32(57712, unit="V", word_order="little")
    B_DC_Current = float32(57714, unit="A", word_order="little")
    B_DC_Power = float32(57716, unit="W", word_order="little")
    B_Export_Energy_WH = uint64(57718, unit="Wh", word_order="little")
    B_Import_Energy_WH = uint64(57722, unit="Wh", word_order="little")
    B_Energy_Max = float32(57726, unit="Wh", word_order="little")
    B_Energy_Available = float32(57728, unit="Wh", word_order="little")
    B_SOH = float32(57730, word_order="little")
    B_SOE = float32(57732, word_order="little")
    B_Status = uint32(57734, word_order="little")
    B_Status_Vendor = uint32(57736, word_order="little")
    B_Event_Log1 = integer(57738, signed=False)
    B_Event_Log2 = integer(57739, signed=False)
    B_Event_Log3 = integer(57740, signed=False)
    B_Event_Log4 = integer(57741, signed=False)
    B_Event_Log5 = integer(57742, signed=False)
    B_Event_Log6 = integer(57743, signed=False)
    B_Event_Log7 = integer(57744, signed=False)
    B_Event_Log8 = integer(57745, signed=False)
    B_Event_Log_Vendor1 = integer(57746, signed=False)
    B_Event_Log_Vendor2 = integer(57747, signed=False)
    B_Event_Log_Vendor3 = integer(57748, signed=False)
    B_Event_Log_Vendor4 = integer(57749, signed=False)
    B_Event_Log_Vendor5 = integer(57750, signed=False)
    B_Event_Log_Vendor6 = integer(57751, signed=False)
    B_Event_Log_Vendor7 = integer(57752, signed=False)
    B_Event_Log_Vendor8 = integer(57753, signed=False)
