"""SolarEdge components for modbus-connection device modelling."""

from __future__ import annotations

from typing import Any

from modbus_connection.model import (
    Component,
    float32,
    int32,
    integer,
    repeating_group,
    string,
    uint32,
    uint64,
)

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


class GlobalDynamicPowerControl(Component):
    """Global Dynamic Power Control and Status"""

    I_RRCR = integer(61440, signed=False)
    I_Power_Limit = integer(61441, signed=False, unit="%", writable=True)
    I_CosPhi = float32(61442, word_order="little", writable=True)


class AdvancedPowerControl(Component):
    """Advanced Power Control Power Control Block is read every polling cycle."""

    CommitPwrCtlSettings = integer(61696, signed=True, writable=True)
    RestorePwrCtlDefaults = integer(61697, signed=True, writable=True)
    PwrFrqDeratingConfig = int32(61698, word_order="little", writable=True)
    ReactivePwrConfig = int32(61700, word_order="little", writable=True)
    ReactPwrIterTime = uint32(61702, unit="ms", word_order="little", writable=True)
    ActivePwrGrad = int32(61704, word_order="little", writable=True)
    FixedCosPhiPhase = float32(61706, word_order="little", writable=True)
    FixedReactPwr = float32(61708, unit="VAR", word_order="little", writable=True)
    ReactCosPhiVsPX_0 = float32(61710, word_order="little", writable=True)
    ReactCosPhiVsPX_1 = float32(61712, word_order="little", writable=True)
    ReactCosPhiVsPX_2 = float32(61714, word_order="little", writable=True)
    ReactCosPhiVsPX_3 = float32(61716, word_order="little", writable=True)
    ReactCosPhiVsPX_4 = float32(61718, word_order="little", writable=True)
    ReactCosPhiVsPX_5 = float32(61720, word_order="little", writable=True)
    ReactCosPhiVsPY_0 = float32(61722, word_order="little", writable=True)
    ReactCosPhiVsPY_1 = float32(61724, word_order="little", writable=True)
    ReactCosPhiVsPY_2 = float32(61726, word_order="little", writable=True)
    ReactCosPhiVsPY_3 = float32(61728, word_order="little", writable=True)
    ReactCosPhiVsPY_4 = float32(61730, word_order="little", writable=True)
    ReactCosPhiVsPY_5 = float32(61732, word_order="little", writable=True)
    ReactQVsVgX_0 = float32(61734, unit="%", word_order="little", writable=True)
    ReactQVsVgX_1 = float32(61736, unit="%", word_order="little", writable=True)
    ReactQVsVgX_2 = float32(61738, unit="%", word_order="little", writable=True)
    ReactQVsVgX_3 = float32(61740, unit="%", word_order="little", writable=True)
    ReactQVsVgX_4 = float32(61742, unit="%", word_order="little", writable=True)
    ReactQVsVgX_5 = float32(61744, unit="%", word_order="little", writable=True)
    ReactQVsVgY_0 = float32(61746, unit="%", word_order="little", writable=True)
    ReactQVsVgY_1 = float32(61748, unit="%", word_order="little", writable=True)
    ReactQVsVgY_2 = float32(61750, unit="%", word_order="little", writable=True)
    ReactQVsVgY_3 = float32(61752, unit="%", word_order="little", writable=True)
    ReactQVsVgY_4 = float32(61754, unit="%", word_order="little", writable=True)
    ReactQVsVgY_5 = float32(61756, unit="%", word_order="little", writable=True)
    FRT_KFactor = float32(61758, word_order="little", writable=True)
    PowerReduce = float32(61760, word_order="little", writable=True)
    AdvPwrCtrlEn = int32(61762, word_order="little", writable=True)
    FrtEn = int32(61764, word_order="little", writable=True)
    MaxWakeupFreq = float32(61766, unit="Hz", word_order="little", writable=True)
    MinWakeupFreq = float32(61768, unit="Hz", word_order="little", writable=True)
    MaxWakeupVg = float32(61770, unit="V", word_order="little", writable=True)
    MinWakeupVg = float32(61772, unit="V", word_order="little", writable=True)
    Vnom = float32(61774, unit="V", word_order="little", writable=True)
    Inom = float32(61776, unit="A", word_order="little", writable=True)
    PwrVsFreqX_0 = float32(61778, unit="Hz", word_order="little", writable=True)
    PwrVsFreqX_1 = float32(61780, unit="Hz", word_order="little", writable=True)
    PwrVsFreqY_0 = float32(61782, word_order="little", writable=True)
    PwrVsFreqY_1 = float32(61784, word_order="little", writable=True)
    ResetFreq = float32(61786, unit="Hz", word_order="little", writable=True)
    MaxFreq = float32(61788, unit="Hz", word_order="little", writable=True)
    ReactQVsPX_0 = float32(61790, unit="%", word_order="little", writable=True)
    ReactQVsPX_1 = float32(61792, unit="%", word_order="little", writable=True)
    ReactQVsPX_2 = float32(61794, unit="%", word_order="little", writable=True)
    ReactQVsPX_3 = float32(61796, unit="%", word_order="little", writable=True)
    ReactQVsPX_4 = float32(61798, unit="%", word_order="little", writable=True)
    ReactQVsPX_5 = float32(61800, unit="%", word_order="little", writable=True)
    ReactQVsPY_0 = float32(61802, unit="%", word_order="little", writable=True)
    ReactQVsPY_1 = float32(61804, unit="%", word_order="little", writable=True)
    ReactQVsPY_2 = float32(61806, unit="%", word_order="little", writable=True)
    ReactQVsPY_3 = float32(61808, unit="%", word_order="little", writable=True)
    ReactQVsPY_4 = float32(61810, unit="%", word_order="little", writable=True)
    ReactQVsPY_5 = float32(61812, unit="%", word_order="little", writable=True)
    PwrFrqDeratingResetTime = uint32(
        61814, unit="ms", word_order="little", writable=True
    )
    PwrFrqDeratingGradTime = uint32(
        61816, unit="ms", word_order="little", writable=True
    )
    ReactCosPhiVsPVgLockInMax = float32(
        61818, unit="V", word_order="little", writable=True
    )
    ReactCosPhiVsPVgLockInMin = float32(
        61820, unit="V", word_order="little", writable=True
    )
    ReactCosPhiVsPVgLockOutMax = float32(
        61822, unit="V", word_order="little", writable=True
    )
    ReactCosPhiVsPVgLockOutMin = float32(
        61824, unit="V", word_order="little", writable=True
    )
    ReactQVsVgPLockInMax = float32(61826, unit="V", word_order="little", writable=True)
    ReactQVsVgPLockInMin = float32(61828, unit="V", word_order="little", writable=True)
    ReactQVsVgPLockOutMax = float32(61830, unit="V", word_order="little", writable=True)
    ReactQVsVgPLockOutMin = float32(61832, unit="V", word_order="little", writable=True)
    ReactQVsVgType = uint32(61834, word_order="little", writable=True)
    PwrSoftStartTime = uint32(61836, unit="ms", word_order="little", writable=True)
    MaxCurrent = float32(61838, unit="A", word_order="little", writable=True)
    PwrVsVgX_0 = float32(61840, unit="V", word_order="little", writable=True)
    PwrVsVgX_1 = float32(61842, unit="V", word_order="little", writable=True)
    PwrVsVgX_2 = float32(61844, unit="V", word_order="little", writable=True)
    PwrVsVgX_3 = float32(61846, unit="V", word_order="little", writable=True)
    PwrVsVgX_4 = float32(61848, unit="V", word_order="little", writable=True)
    PwrVsVgX_5 = float32(61850, unit="V", word_order="little", writable=True)
    PwrVsVgY_0 = float32(61852, word_order="little", writable=True)
    PwrVsVgY_1 = float32(61854, word_order="little", writable=True)
    PwrVsVgY_2 = float32(61856, word_order="little", writable=True)
    PwrVsVgY_3 = float32(61858, word_order="little", writable=True)
    PwrVsVgY_4 = float32(61860, word_order="little", writable=True)
    PwrVsVgY_5 = float32(61862, word_order="little", writable=True)
    DisconnectAtZeroPwrLim = float32(61864, word_order="little", writable=True)


class SiteLimitControl(Component):
    """Power Control Options: Site Limit Control, read every polling cycle."""

    register_ranges = ((57344, 57347), (57362, 57363))

    E_Lim_Ctl_Mode = integer(57344, signed=False, writable=True)
    E_Lim_Ctl = integer(57345, signed=False, writable=True)
    E_Site_Limit = float32(57346, unit="W", word_order="little", writable=True)
    Ext_Prod_Max = float32(57362, unit="W", word_order="little", writable=True)


class MmpptCommon(Component):
    """MMPPT common block is only read once at setup."""

    mmppt_DID = integer(40121, signed=False)
    mmppt_Length = integer(40122, signed=False)
    mmppt_Units = integer(40129, signed=False)


class MmpptUnit(Component):
    """Sub-component of MmpptData.units; modbus-connection builds
    one instance per unit (2 or 3, per mmppt_Units) itself, each shifted by
    stride * unit_index
    """

    ID = integer(40131, signed=False)
    IDStr = string(40132, 16)
    DCA = integer(40140, signed=False, unit="A")
    DCV = integer(40141, signed=False, unit="V")
    DCW = integer(40142, signed=False, unit="W")
    DCWH = uint32(40143, unit="Wh")
    Tms = uint32(40145)
    Tmp = integer(40147, signed=True, unit="C")
    DCSt = integer(40148, signed=False)
    DCEvt = uint32(40149)


class MmpptData(Component):
    """MMPPT scale factors, events, and every unit; read every polling cycle."""

    mmppt_DCA_SF = integer(40123, signed=True)
    mmppt_DCV_SF = integer(40124, signed=True)
    mmppt_DCW_SF = integer(40125, signed=True)
    mmppt_DCWH_SF = integer(40126, signed=True)
    mmppt_Events = uint32(40127)
    units = repeating_group(integer(40129, signed=False), MmpptUnit, stride=20)


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


class MeterData(Component):
    """Meter data is read every polling cycle."""

    C_SunSpec_DID = integer(40188, signed=False)
    C_SunSpec_Length = integer(40189, signed=False)
    AC_Current = integer(40190, signed=True, unit="A")
    AC_Current_A = integer(40191, signed=True, unit="A")
    AC_Current_B = integer(40192, signed=True, unit="A")
    AC_Current_C = integer(40193, signed=True, unit="A")
    AC_Current_SF = integer(40194, signed=True)
    AC_Voltage_LN = integer(40195, signed=True, unit="V")
    AC_Voltage_AN = integer(40196, signed=True, unit="V")
    AC_Voltage_BN = integer(40197, signed=True, unit="V")
    AC_Voltage_CN = integer(40198, signed=True, unit="V")
    AC_Voltage_LL = integer(40199, signed=True, unit="V")
    AC_Voltage_AB = integer(40200, signed=True, unit="V")
    AC_Voltage_BC = integer(40201, signed=True, unit="V")
    AC_Voltage_CA = integer(40202, signed=True, unit="V")
    AC_Voltage_SF = integer(40203, signed=True)
    AC_Frequency = integer(40204, signed=True, unit="Hz")
    AC_Frequency_SF = integer(40205, signed=True)
    AC_Power = integer(40206, signed=True, unit="W")
    AC_Power_A = integer(40207, signed=True, unit="W")
    AC_Power_B = integer(40208, signed=True, unit="W")
    AC_Power_C = integer(40209, signed=True, unit="W")
    AC_Power_SF = integer(40210, signed=True)
    AC_VA = integer(40211, signed=True, unit="VA")
    AC_VA_A = integer(40212, signed=True, unit="VA")
    AC_VA_B = integer(40213, signed=True, unit="VA")
    AC_VA_C = integer(40214, signed=True, unit="VA")
    AC_VA_SF = integer(40215, signed=True)
    AC_var = integer(40216, signed=True, unit="var")
    AC_var_A = integer(40217, signed=True, unit="var")
    AC_var_B = integer(40218, signed=True, unit="var")
    AC_var_C = integer(40219, signed=True, unit="var")
    AC_var_SF = integer(40220, signed=True)
    AC_PF = integer(40221, signed=True, unit="%")
    AC_PF_A = integer(40222, signed=True, unit="%")
    AC_PF_B = integer(40223, signed=True, unit="%")
    AC_PF_C = integer(40224, signed=True, unit="%")
    AC_PF_SF = integer(40225, signed=True)
    AC_Energy_WH_Exported = uint32(40226, unit="Wh")
    AC_Energy_WH_Exported_A = uint32(40228, unit="Wh")
    AC_Energy_WH_Exported_B = uint32(40230, unit="Wh")
    AC_Energy_WH_Exported_C = uint32(40232, unit="Wh")
    AC_Energy_WH_Imported = uint32(40234, unit="Wh")
    AC_Energy_WH_Imported_A = uint32(40236, unit="Wh")
    AC_Energy_WH_Imported_B = uint32(40238, unit="Wh")
    AC_Energy_WH_Imported_C = uint32(40240, unit="Wh")
    AC_Energy_WH_SF = integer(40242, signed=True)
    M_VAh_Exported = uint32(40243, unit="VAh")
    M_VAh_Exported_A = uint32(40245, unit="VAh")
    M_VAh_Exported_B = uint32(40247, unit="VAh")
    M_VAh_Exported_C = uint32(40249, unit="VAh")
    M_VAh_Imported = uint32(40251, unit="VAh")
    M_VAh_Imported_A = uint32(40253, unit="VAh")
    M_VAh_Imported_B = uint32(40255, unit="VAh")
    M_VAh_Imported_C = uint32(40257, unit="VAh")
    M_VAh_SF = integer(40259, signed=True)
    M_varh_Import_Q1 = uint32(40260, unit="varh")
    M_varh_Import_Q1_A = uint32(40262, unit="varh")
    M_varh_Import_Q1_B = uint32(40264, unit="varh")
    M_varh_Import_Q1_C = uint32(40266, unit="varh")
    M_varh_Import_Q2 = uint32(40268, unit="varh")
    M_varh_Import_Q2_A = uint32(40270, unit="varh")
    M_varh_Import_Q2_B = uint32(40272, unit="varh")
    M_varh_Import_Q2_C = uint32(40274, unit="varh")
    M_varh_Export_Q3 = uint32(40276, unit="varh")
    M_varh_Export_Q3_A = uint32(40278, unit="varh")
    M_varh_Export_Q3_B = uint32(40280, unit="varh")
    M_varh_Export_Q3_C = uint32(40282, unit="varh")
    M_varh_Export_Q4 = uint32(40284, unit="varh")
    M_varh_Export_Q4_A = uint32(40286, unit="varh")
    M_varh_Export_Q4_B = uint32(40288, unit="varh")
    M_varh_Export_Q4_C = uint32(40290, unit="varh")
    M_varh_SF = integer(40292, signed=True)
    M_Events = uint32(40293)


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
