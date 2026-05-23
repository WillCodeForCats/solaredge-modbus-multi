"""Unit tests for SolarEdgeBattery."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock

import pytest

from custom_components.solaredge_modbus_multi.battery import SolarEdgeBattery
from custom_components.solaredge_modbus_multi.const import BATTERY_REG_BASE, SunSpecNotImpl
from custom_components.solaredge_modbus_multi.exceptions import (
    DeviceInvalid,
    ModbusIllegalAddress,
    ModbusIOError,
    ModbusReadError,
)

from .fixtures import (
    BATTERY_COMMON_REGS,
    BATTERY_MODEL_REGS,
    MockHub,
    float32_le,
    make_battery_common_regs,
    make_battery_model_regs,
    make_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hub_for_battery(inverter_unit_id: int = 1) -> MockHub:
    hub = MockHub()
    hub.inverter_common[inverter_unit_id] = {
        "C_Model": "SE5000H",
        "C_SerialNumber": "SN123456",
    }
    return hub


def _not_impl_float32_le() -> list[int]:
    """Registers encoding SunSpec FLOAT32 not-implemented (0x7FC00000)."""
    b = struct.pack(">I", SunSpecNotImpl.FLOAT32)
    msw = (b[0] << 8) | b[1]
    lsw = (b[2] << 8) | b[3]
    return [lsw, msw]  # word_order='little'


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestBatteryInit:
    def test_invalid_battery_id_raises_device_invalid(self):
        hub = _hub_for_battery()
        with pytest.raises(DeviceInvalid, match="Invalid battery_id"):
            SolarEdgeBattery(device_id=1, battery_id=99, hub=hub)

    def test_valid_battery_id_sets_start_address(self):
        hub = _hub_for_battery()
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        assert b.start_address == BATTERY_REG_BASE[1]

    def test_battery_id_2_uses_different_address(self):
        hub = _hub_for_battery()
        b = SolarEdgeBattery(device_id=1, battery_id=2, hub=hub)
        assert b.start_address == BATTERY_REG_BASE[2]

    def test_has_parent_is_true(self):
        hub = _hub_for_battery()
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        assert b.has_parent is True


# ---------------------------------------------------------------------------
# init_device — happy path
# ---------------------------------------------------------------------------


class TestBatteryInitDeviceHappyPath:
    async def test_sets_common_fields(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(BATTERY_COMMON_REGS)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        await b.init_device()

        assert b.manufacturer == "LG Chem"
        assert b.model == "RESU10H"
        assert b.serial == "BAT001"
        assert b.device_address == 1

    async def test_name_and_uid_base(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(BATTERY_COMMON_REGS)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        await b.init_device()

        assert b.name == "Solaredge I1 B1"
        assert b.uid_base == "SE5000H_SN123456_B1"

    async def test_option_is_empty_string(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(BATTERY_COMMON_REGS)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        await b.init_device()
        assert b.option == ""

    async def test_ascii_ctrl_chars_removed(self):
        """Control characters in battery strings should be stripped."""
        regs = make_battery_common_regs()
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(regs)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        await b.init_device()
        assert "\x00" not in b.manufacturer
        assert "\x01" not in b.serial


# ---------------------------------------------------------------------------
# init_device — error / invalid-data paths
# ---------------------------------------------------------------------------


class TestBatteryInitDeviceErrors:
    async def test_rated_energy_zero_raises_device_invalid(self):
        regs = make_battery_common_regs()
        regs[66:68] = float32_le(0.0)  # B_RatedEnergy = 0 → invalid
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(regs)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="rating"):
            await b.init_device()

    async def test_rated_energy_negative_raises_device_invalid(self):
        regs = make_battery_common_regs()
        regs[66:68] = float32_le(-100.0)
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(regs)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="rating"):
            await b.init_device()

    async def test_rated_energy_not_impl_raises_device_invalid(self):
        regs = make_battery_common_regs()
        regs[66:68] = _not_impl_float32_le()  # SunSpec FLOAT32 not-implemented
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(regs)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        with pytest.raises(DeviceInvalid):
            await b.init_device()

    async def test_modbus_io_error_raises_device_invalid(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIOError("timeout"))
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="No response"):
            await b.init_device()

    async def test_illegal_address_raises_device_invalid(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIllegalAddress("bad addr"))
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="unsupported address"):
            await b.init_device()


# ---------------------------------------------------------------------------
# read_modbus_data — happy path
# ---------------------------------------------------------------------------


class TestBatteryReadModbusDataHappyPath:
    async def _init_battery(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(BATTERY_COMMON_REGS)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        await b.init_device()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(BATTERY_MODEL_REGS)])
        return b

    async def test_sets_max_charge_power(self):
        b = await self._init_battery()
        await b.read_modbus_data()
        assert abs(b.decoded_model["B_MaxChargePower"] - 5000.0) < 1.0

    async def test_sets_status(self):
        b = await self._init_battery()
        await b.read_modbus_data()
        assert b.decoded_model["B_Status"] == 3

    async def test_sets_temp_average(self):
        b = await self._init_battery()
        await b.read_modbus_data()
        assert abs(b.decoded_model["B_Temp_Average"] - 25.0) < 0.01

    async def test_sets_soe(self):
        b = await self._init_battery()
        await b.read_modbus_data()
        assert abs(b.decoded_model["B_SOE"] - 75.0) < 0.01

    async def test_event_log_fields_present(self):
        b = await self._init_battery()
        await b.read_modbus_data()
        assert "B_Event_Log1" in b.decoded_model
        assert "B_Event_Log_Vendor1" in b.decoded_model


# ---------------------------------------------------------------------------
# read_modbus_data — error paths
# ---------------------------------------------------------------------------


class TestBatteryReadModbusDataErrors:
    async def _init_battery(self):
        hub = _hub_for_battery()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(BATTERY_COMMON_REGS)])
        b = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
        await b.init_device()
        return b

    async def test_modbus_io_error_raises_modbus_read_error(self):
        b = await self._init_battery()
        b.hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIOError("timeout"))
        with pytest.raises(ModbusReadError, match="No response"):
            await b.read_modbus_data()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestBatteryProperties:
    def setup_method(self):
        self.hub = _hub_for_battery()
        self.hub.allow_battery_energy_reset = False
        self.hub.battery_rating_adjust = 1.0
        self.hub.battery_energy_reset_cycles = 0
        self.b = SolarEdgeBattery(device_id=1, battery_id=1, hub=self.hub)
        self.b.manufacturer = "LG Chem"
        self.b.model = "RESU10H"
        self.b.option = ""
        self.b.fw_version = "1.5.1"
        self.b.serial = "BAT001"
        self.b.device_address = 1
        self.b.name = "Solaredge I1 B1"
        self.b.uid_base = "SE5000H_SN123456_B1"

    def test_online_delegates_to_hub(self):
        self.hub.online = True
        assert self.b.online is True
        self.hub.online = False
        assert self.b.online is False

    def test_last_update_none_initially(self):
        assert self.b.last_update is None

    def test_set_last_update(self):
        import datetime

        ts = datetime.datetime(2025, 6, 1)
        self.b.set_last_update(ts)
        assert self.b.last_update == ts

    def test_via_device_setter(self):
        self.b.via_device = "SE5000H_SN123456"
        assert self.b.via_device == ("solaredge_modbus_multi", "SE5000H_SN123456")

    def test_allow_battery_energy_reset_delegates(self):
        self.hub.allow_battery_energy_reset = True
        assert self.b.allow_battery_energy_reset is True

    def test_battery_rating_adjust_delegates(self):
        self.hub.battery_rating_adjust = 1.05
        assert self.b.battery_rating_adjust == 1.05

    def test_battery_energy_reset_cycles_delegates(self):
        self.hub.battery_energy_reset_cycles = 10
        assert self.b.battery_energy_reset_cycles == 10

    def test_device_info(self):
        self.b.via_device = "SE5000H_SN123456"
        info = self.b.device_info
        assert info is not None
