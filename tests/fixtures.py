"""Shared test utilities — register-data factories and mock stubs."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock

from custom_components.solaredge_modbus_multi.const import DOMAIN

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def make_response(registers: list[int]) -> MagicMock:
    """Return a non-error modbus response with given registers."""
    resp = MagicMock()
    resp.registers = list(registers)
    resp.isError.return_value = False
    return resp


def encode_string_be(text: str, nwords: int) -> list[int]:
    """Encode ASCII text as big-endian UINT16 register words."""
    padded = (text.encode("ascii", errors="replace") + b"\x00" * (nwords * 2))[: nwords * 2]
    return [(padded[i * 2] << 8) | padded[i * 2 + 1] for i in range(nwords)]


def encode_string_le(text: str, nwords: int) -> list[int]:
    """Encode ASCII text as byte-swapped (little-endian) UINT16 register words."""
    padded = (text.encode("ascii", errors="replace") + b"\x00" * (nwords * 2))[: nwords * 2]
    return [(padded[i * 2 + 1] << 8) | padded[i * 2] for i in range(nwords)]


def float32_le(value: float) -> list[int]:
    """Encode a float32 as 2 registers with word_order='little' (LSW first)."""
    b = struct.pack(">f", value)
    msw = (b[0] << 8) | b[1]
    lsw = (b[2] << 8) | b[3]
    return [lsw, msw]


# ---------------------------------------------------------------------------
# Mock classes
# ---------------------------------------------------------------------------


class MockHass:
    """Minimal Home Assistant stub."""

    def __init__(self) -> None:
        self.data = {DOMAIN: {"yaml": {}}}


class MockHub:
    """Minimal hub stub for unit-testing device classes."""

    def __init__(self, responses: list[list[int]] | None = None) -> None:
        self.hub_id = "solaredge"
        self.online = True
        self.inverter_common: dict = {}
        self.mmppt_common: dict = {}
        self.batteries: list = []
        self.option_storage_control = False
        self.option_site_limit_control = False
        self.option_detect_extras = False
        self._hass = MockHass()
        self._entry_id = "test_entry"
        self.is_connected = True

        if responses is not None:
            self.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(r) for r in responses])
        else:
            self.modbus_read_holding_registers = AsyncMock(return_value=make_response([]))

    async def connect(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Inverter register data
# ---------------------------------------------------------------------------

SUNSPEC_ID_REGS = [0x5375, 0x6E53]  # 0x53756E53 = "SunS"

INVERTER_COMMON_REGS = (
    SUNSPEC_ID_REGS  # regs[0:2]  C_SunSpec_ID = 0x53756E53
    + [0x0001, 65]  # regs[2:4]  C_SunSpec_DID=1, C_SunSpec_Length=65
    + encode_string_be("SolarEdge", 16)  # regs[4:20]  C_Manufacturer (string32)
    + encode_string_be("SE5000H", 16)  # regs[20:36] C_Model (string32)
    + encode_string_be("000TNS", 8)  # regs[36:44] C_Option (string16)
    + encode_string_be("3.20.0", 8)  # regs[44:52] C_Version (string16)
    + encode_string_be("SN123456", 16)  # regs[52:68] C_SerialNumber (string32)
    + [1]  # regs[68]    C_Device_address
)
assert len(INVERTER_COMMON_REGS) == 69

# MMPPT block — no MMPPT (DID = UINT16 not-impl)
INVERTER_MMPPT_NONE = [0xFFFF] + [0] * 8
assert len(INVERTER_MMPPT_NONE) == 9

# MMPPT block — 2 units (DID=160, Units=2)
INVERTER_MMPPT_2 = [160, 10, 0, 0, 0, 0, 0, 0, 2]
assert len(INVERTER_MMPPT_2) == 9

# MMPPT block — 3 units (DID=160, Units=3)
INVERTER_MMPPT_3 = [160, 14, 0, 0, 0, 0, 0, 0, 3]
assert len(INVERTER_MMPPT_3) == 9

# 68 registers for address 40123 (MMPPT data, 3 units)
INVERTER_MMPPT_3_DATA_REGS = [0] * 68

# version string read at 40044
INVERTER_VERSION_REGS = encode_string_be("3.20.0", 8)
assert len(INVERTER_VERSION_REGS) == 8


def make_inverter_model_regs(did: int = 101) -> list[int]:
    """40 registers for address 40069 (inverter model block)."""
    regs = [0] * 40
    regs[0] = did  # C_SunSpec_DID — must be 101/102/103
    regs[1] = 50  # C_SunSpec_Length — must be 50
    regs[2] = 100  # AC_Current (uint16)
    regs[6] = 0xFFFF  # AC_Current_SF = -1 (int16 two's complement)
    regs[16] = 5000  # AC_Frequency (uint16)
    regs[24] = 0x000F  # AC_Energy_WH hi word  → 0x000F4240 = 1 000 000 Wh
    regs[25] = 0x4240  # AC_Energy_WH lo word
    regs[27] = 50  # I_DC_Current (uint16)
    regs[29] = 3500  # I_DC_Voltage (uint16)
    return regs


INVERTER_MODEL_REGS = make_inverter_model_regs()

# 2 registers for address 40113 (grid on/off status)
INVERTER_GRID_STATUS_REGS = [1, 0]  # UINT32 little-endian = 1 (connected)

# 48 registers for address 40123 (MMPPT data, 2 units)
INVERTER_MMPPT_DATA_REGS = [0] * 48

# ---------------------------------------------------------------------------
# Meter register data
# ---------------------------------------------------------------------------

METER_COMMON_REGS = (
    [0x0001, 65]  # regs[0:2]  C_SunSpec_DID=1, C_SunSpec_Length=65
    + encode_string_be("SolarEdge", 16)  # regs[2:18]  C_Manufacturer
    + encode_string_be("SE-MTR-3Y", 16)  # regs[18:34] C_Model
    + encode_string_be("Export+Import", 8)  # regs[34:42] C_Option
    + encode_string_be("1.0.0", 8)  # regs[42:50] C_Version
    + encode_string_be("MTR789012", 16)  # regs[50:66] C_SerialNumber
    + [1]  # regs[66]    C_Device_address
)
assert len(METER_COMMON_REGS) == 67


def make_meter_model_regs(did: int = 201) -> list[int]:
    """107 registers for meter model block (address start_addr + 67)."""
    regs = [0] * 107
    regs[0] = did  # C_SunSpec_DID — must be 201-204
    regs[1] = 105  # C_SunSpec_Length — must be 105
    regs[2] = 10  # AC_Current (int16)
    return regs


METER_MODEL_REGS = make_meter_model_regs()

# ---------------------------------------------------------------------------
# Battery register data
# ---------------------------------------------------------------------------


def make_battery_common_regs() -> list[int]:
    """68 registers for battery common block (address start_address).

    Battery strings are stored as standard big-endian UINT16 registers on the
    wire (word_order='little' in pymodbus only affects multi-register types
    like FLOAT32/UINT32, not single UINT16 words).
    """
    regs = (
        encode_string_be("LG Chem", 16)  # regs[0:16]  B_Manufacturer
        + encode_string_be("RESU10H", 16)  # regs[16:32] B_Model
        + encode_string_be("1.5.1", 16)  # regs[32:48] B_Version
        + encode_string_be("BAT001", 16)  # regs[48:64] B_SerialNumber
        + [1]  # regs[64]    B_Device_Address (uint16)
        + [0]  # regs[65]    reserved
        + float32_le(9600.0)  # regs[66:68] B_RatedEnergy (FLOAT32 little)
    )
    assert len(regs) == 68
    return regs


BATTERY_COMMON_REGS = make_battery_common_regs()


def make_battery_model_regs() -> list[int]:
    """86 registers for battery model block (address start_address + 68)."""
    regs = [0] * 86
    regs[0:2] = float32_le(5000.0)  # B_MaxChargePower
    regs[2:4] = float32_le(5000.0)  # B_MaxDischargePower
    regs[4:6] = float32_le(6000.0)  # B_MaxChargePeakPower
    regs[6:8] = float32_le(6000.0)  # B_MaxDischargePeakPower
    regs[40:42] = float32_le(25.0)  # B_Temp_Average
    regs[42:44] = float32_le(30.0)  # B_Temp_Max
    regs[44:46] = float32_le(48.0)  # B_DC_Voltage
    regs[46:48] = float32_le(5.0)  # B_DC_Current
    regs[48:50] = float32_le(240.0)  # B_DC_Power
    regs[50:54] = [0, 1000, 0, 0]  # B_Export_Energy_WH (uint64 little)
    regs[54:58] = [0, 500, 0, 0]  # B_Import_Energy_WH (uint64 little)
    regs[58:60] = float32_le(9600.0)  # B_Energy_Max
    regs[60:62] = float32_le(7200.0)  # B_Energy_Available
    regs[62:64] = float32_le(100.0)  # B_SOH
    regs[64:66] = float32_le(75.0)  # B_SOE
    regs[66] = 3  # B_Status lo word (uint32 little) = 3
    regs[67] = 0  # B_Status hi word
    regs[68] = 0  # B_Status_Vendor lo word
    regs[69] = 0  # B_Status_Vendor hi word
    return regs


BATTERY_MODEL_REGS = make_battery_model_regs()
