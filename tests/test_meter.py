"""Unit tests for SolarEdgeMeter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.solaredge_modbus_multi.const import METER_REG_BASE
from custom_components.solaredge_modbus_multi.exceptions import (
    DeviceInvalid,
    ModbusIllegalAddress,
    ModbusIOError,
    ModbusReadError,
)
from custom_components.solaredge_modbus_multi.meter import SolarEdgeMeter

from .fixtures import (
    METER_COMMON_REGS,
    METER_MODEL_REGS,
    MockHub,
    make_meter_model_regs,
    make_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hub_for_meter(inverter_unit_id: int = 1) -> MockHub:
    hub = MockHub()
    hub.inverter_common[inverter_unit_id] = {
        "C_Model": "SE5000H",
        "C_SerialNumber": "SN123456",
    }
    hub.mmppt_common[inverter_unit_id] = None  # no MMPPT by default
    return hub


# ---------------------------------------------------------------------------
# __init__ — start_address calculation
# ---------------------------------------------------------------------------


class TestMeterInit:
    def test_invalid_meter_id_raises_device_invalid(self):
        hub = _hub_for_meter()
        with pytest.raises(DeviceInvalid, match="Invalid meter_id"):
            SolarEdgeMeter(device_id=1, meter_id=99, hub=hub)

    def test_no_mmppt_uses_base_address(self):
        hub = _hub_for_meter()
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        assert m.start_address == METER_REG_BASE[1]

    def test_mmppt_2_adds_50_offset(self):
        hub = _hub_for_meter()
        hub.mmppt_common[1] = {"mmppt_Units": 2}
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        assert m.start_address == METER_REG_BASE[1] + 50

    def test_mmppt_3_adds_70_offset(self):
        hub = _hub_for_meter()
        hub.mmppt_common[1] = {"mmppt_Units": 3}
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        assert m.start_address == METER_REG_BASE[1] + 70

    def test_invalid_mmppt_units_raises_device_invalid(self):
        hub = _hub_for_meter()
        hub.mmppt_common[1] = {"mmppt_Units": 5}
        with pytest.raises(DeviceInvalid, match="Invalid mmppt_Units"):
            SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)

    def test_meter_id_2_uses_different_base(self):
        hub = _hub_for_meter()
        m = SolarEdgeMeter(device_id=1, meter_id=2, hub=hub)
        assert m.start_address == METER_REG_BASE[2]

    def test_has_parent_is_true(self):
        hub = _hub_for_meter()
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        assert m.has_parent is True


# ---------------------------------------------------------------------------
# init_device — happy path
# ---------------------------------------------------------------------------


class TestMeterInitDeviceHappyPath:
    async def test_sets_common_fields(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(METER_COMMON_REGS)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        await m.init_device()

        assert m.manufacturer == "SolarEdge"
        assert m.model == "SE-MTR-3Y"
        assert m.option == "Export+Import"
        assert m.serial == "MTR789012"
        assert m.device_address == 1

    def _meter_name(self, m):
        return m.name

    async def test_name_and_uid_base(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(METER_COMMON_REGS)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        await m.init_device()

        assert m.name == "Solaredge I1 M1"
        assert m.uid_base == "SE5000H_SN123456_M1"

    async def test_hub_inverter_common_read(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(METER_COMMON_REGS)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        await m.init_device()
        # Should have stored inv model/serial in uid_base
        assert "SE5000H" in m.uid_base


# ---------------------------------------------------------------------------
# init_device — error / invalid-data paths
# ---------------------------------------------------------------------------


class TestMeterInitDeviceErrors:
    async def test_bad_did_raises_device_invalid(self):
        bad = list(METER_COMMON_REGS)
        bad[0] = 0x0002  # C_SunSpec_DID != 1
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(bad)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="ident incorrect"):
            await m.init_device()

    async def test_wrong_length_raises_device_invalid(self):
        bad = list(METER_COMMON_REGS)
        bad[1] = 99  # C_SunSpec_Length != 65
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(bad)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="ident incorrect"):
            await m.init_device()

    async def test_modbus_io_error_raises_device_invalid(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIOError("timeout"))
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="No response"):
            await m.init_device()

    async def test_illegal_address_raises_device_invalid(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIllegalAddress("bad addr"))
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="unsupported address"):
            await m.init_device()

    async def test_sunspec_not_impl_did_raises_device_invalid(self):
        bad = list(METER_COMMON_REGS)
        bad[0] = 0xFFFF  # UINT16 not-implemented
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(bad)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        with pytest.raises(DeviceInvalid):
            await m.init_device()

    async def test_response_is_error_raises_modbus_read_error(self):
        """If the response itself says isError(), raise ModbusReadError."""
        from unittest.mock import MagicMock

        error_resp = MagicMock()
        error_resp.registers = list(METER_COMMON_REGS)
        error_resp.isError.return_value = True  # unusual: error result, no exception raised

        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[error_resp])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        with pytest.raises(ModbusReadError):
            await m.init_device()


# ---------------------------------------------------------------------------
# read_modbus_data — happy path
# ---------------------------------------------------------------------------


class TestMeterReadModbusDataHappyPath:
    async def _init_meter(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(METER_COMMON_REGS)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        await m.init_device()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(METER_MODEL_REGS)])
        return m

    async def test_sets_did_and_length(self):
        m = await self._init_meter()
        await m.read_modbus_data()
        assert m.decoded_model["C_SunSpec_DID"] == 201
        assert m.decoded_model["C_SunSpec_Length"] == 105

    async def test_sets_ac_current(self):
        m = await self._init_meter()
        await m.read_modbus_data()
        assert m.decoded_model["AC_Current"] == 10


# ---------------------------------------------------------------------------
# read_modbus_data — validation failures
# ---------------------------------------------------------------------------


class TestMeterReadModbusDataErrors:
    async def _init_meter(self):
        hub = _hub_for_meter()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(METER_COMMON_REGS)])
        m = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
        await m.init_device()
        return m

    async def test_bad_did_raises_device_invalid(self):
        m = await self._init_meter()
        bad = make_meter_model_regs(did=999)
        m.hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(bad)])
        with pytest.raises(DeviceInvalid, match="ident incorrect"):
            await m.read_modbus_data()

    async def test_wrong_length_raises_device_invalid(self):
        m = await self._init_meter()
        bad = make_meter_model_regs(did=201)
        bad[1] = 99  # C_SunSpec_Length != 105
        m.hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(bad)])
        with pytest.raises(DeviceInvalid, match="ident incorrect"):
            await m.read_modbus_data()

    async def test_modbus_io_error_raises_modbus_read_error(self):
        m = await self._init_meter()
        m.hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIOError("timeout"))
        with pytest.raises(ModbusReadError, match="No response"):
            await m.read_modbus_data()

    async def test_sunspec_not_impl_did_raises_device_invalid(self):
        m = await self._init_meter()
        bad = make_meter_model_regs()
        bad[0] = 0xFFFF
        m.hub.modbus_read_holding_registers = AsyncMock(side_effect=[make_response(bad)])
        with pytest.raises(DeviceInvalid):
            await m.read_modbus_data()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestMeterProperties:
    def setup_method(self):
        self.hub = _hub_for_meter()
        self.m = SolarEdgeMeter(device_id=1, meter_id=1, hub=self.hub)
        self.m.manufacturer = "SolarEdge"
        self.m.model = "SE-MTR-3Y"
        self.m.option = "Export+Import"
        self.m.fw_version = "1.0.0"
        self.m.serial = "MTR789012"
        self.m.device_address = 1
        self.m.name = "Solaredge I1 M1"
        self.m.uid_base = "SE5000H_SN123456_M1"

    def test_online_delegates_to_hub(self):
        self.hub.online = True
        assert self.m.online is True
        self.hub.online = False
        assert self.m.online is False

    def test_last_update_none_initially(self):
        assert self.m.last_update is None

    def test_set_last_update(self):
        import datetime

        ts = datetime.datetime(2025, 1, 1)
        self.m.set_last_update(ts)
        assert self.m.last_update == ts

    def test_via_device_setter(self):
        self.m.via_device = "SE5000H_SN123456"
        assert self.m.via_device == ("solaredge_modbus_multi", "SE5000H_SN123456")

    def test_device_info(self):
        self.m.via_device = "SE5000H_SN123456"
        info = self.m.device_info
        assert info is not None
