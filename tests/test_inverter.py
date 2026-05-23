"""Unit tests for SolarEdgeInverter and SolarEdgeMMPPTUnit."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.solaredge_modbus_multi.exceptions import (
    DeviceInvalid,
    ModbusIllegalAddress,
    ModbusIOError,
    ModbusReadError,
)
from custom_components.solaredge_modbus_multi.inverter import (
    SolarEdgeInverter,
    SolarEdgeMMPPTUnit,
)

from .fixtures import (
    INVERTER_COMMON_REGS,
    INVERTER_GRID_STATUS_REGS,
    INVERTER_MMPPT_2,
    INVERTER_MMPPT_3,
    INVERTER_MMPPT_3_DATA_REGS,
    INVERTER_MMPPT_DATA_REGS,
    INVERTER_MMPPT_NONE,
    INVERTER_MODEL_REGS,
    INVERTER_VERSION_REGS,
    MockHub,
    encode_string_be,
    make_inverter_model_regs,
    make_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hub_with(responses):
    hub = MockHub(responses=responses)
    return hub


def _inverter_with(responses):
    hub = _hub_with(responses)
    hub.inverter_common[1] = {}
    hub.mmppt_common[1] = None
    return SolarEdgeInverter(device_id=1, hub=hub)


# ---------------------------------------------------------------------------
# init_device — happy paths
# ---------------------------------------------------------------------------


class TestInverterInitDeviceHappyPath:
    async def test_no_mmppt_sets_common_fields(self):
        inv = _inverter_with([INVERTER_COMMON_REGS, INVERTER_MMPPT_NONE])
        await inv.init_device()

        assert inv.manufacturer == "SolarEdge"
        assert inv.model == "SE5000H"
        assert inv.serial == "SN123456"
        assert inv.option == "000TNS"
        assert inv.device_address == 1
        assert inv.name == "Solaredge I1"
        assert inv.uid_base == "SE5000H_SN123456"

    async def test_no_mmppt_decoded_mmppt_is_none(self):
        inv = _inverter_with([INVERTER_COMMON_REGS, INVERTER_MMPPT_NONE])
        await inv.init_device()
        assert inv.decoded_mmppt is None
        assert inv.is_mmppt is False
        assert inv.mmppt_units == []

    async def test_no_mmppt_hub_inverter_common_populated(self):
        hub = _hub_with([INVERTER_COMMON_REGS, INVERTER_MMPPT_NONE])
        hub.inverter_common[1] = {}
        hub.mmppt_common[1] = None
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        await inv.init_device()

        common = hub.inverter_common[1]
        assert common["C_SunSpec_ID"] == 0x53756E53
        assert common["C_SunSpec_DID"] == 1
        assert common["C_SunSpec_Length"] == 65

    async def test_with_mmppt_2_creates_units(self):
        responses = [INVERTER_COMMON_REGS, INVERTER_MMPPT_2]
        inv = _inverter_with(responses)
        await inv.init_device()

        assert inv.is_mmppt is True
        assert len(inv.mmppt_units) == 2
        assert inv.decoded_mmppt["mmppt_Units"] == 2

    async def test_use_status_vendor4_true_for_ge_3_20_0(self):
        """Version 3.20.0 should enable vendor4 status."""
        inv = _inverter_with([INVERTER_COMMON_REGS, INVERTER_MMPPT_NONE])
        await inv.init_device()
        assert inv.use_status_vendor4 is True

    async def test_use_status_vendor4_false_for_older(self):
        """Version below 3.20.0 should NOT enable vendor4 status."""
        old_ver_common = list(INVERTER_COMMON_REGS)
        # regs[44:52] is C_Version — replace with "3.19.0"
        old_ver_common[44:52] = encode_string_be("3.19.0", 8)
        inv = _inverter_with([old_ver_common, INVERTER_MMPPT_NONE])
        await inv.init_device()
        assert inv.use_status_vendor4 is False


# ---------------------------------------------------------------------------
# init_device — error / invalid-data paths
# ---------------------------------------------------------------------------


class TestInverterInitDeviceErrors:
    async def test_modbus_io_error_raises_device_invalid(self):
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIOError("timeout"))
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="No response"):
            await inv.init_device()

    async def test_illegal_address_raises_device_invalid(self):
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIllegalAddress("bad addr"))
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        with pytest.raises(DeviceInvalid, match="not a SunSpec inverter"):
            await inv.init_device()

    async def test_wrong_sunspec_id_raises_device_invalid(self):
        bad = list(INVERTER_COMMON_REGS)
        bad[0] = 0xDEAD  # corrupt C_SunSpec_ID hi word
        inv = _inverter_with([bad, INVERTER_MMPPT_NONE])
        with pytest.raises(DeviceInvalid):
            await inv.init_device()

    async def test_wrong_sunspec_did_raises_device_invalid(self):
        bad = list(INVERTER_COMMON_REGS)
        bad[2] = 0x0002  # C_SunSpec_DID != 1
        inv = _inverter_with([bad, INVERTER_MMPPT_NONE])
        with pytest.raises(DeviceInvalid):
            await inv.init_device()

    async def test_wrong_sunspec_length_raises_device_invalid(self):
        bad = list(INVERTER_COMMON_REGS)
        bad[3] = 99  # C_SunSpec_Length != 65
        inv = _inverter_with([bad, INVERTER_MMPPT_NONE])
        with pytest.raises(DeviceInvalid):
            await inv.init_device()

    async def test_mmppt_io_error_raises_modbus_read_error(self):
        """IO error on the MMPPT block (second read) raises ModbusReadError."""
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[make_response(INVERTER_COMMON_REGS), ModbusIOError("timeout")]
        )
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        with pytest.raises(ModbusReadError):
            await inv.init_device()

    async def test_mmppt_illegal_address_sets_none(self):
        """IllegalAddress on MMPPT block is treated as 'no MMPPT present'."""
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[make_response(INVERTER_COMMON_REGS), ModbusIllegalAddress("no mmppt")]
        )
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        await inv.init_device()
        assert inv.decoded_mmppt is None


# ---------------------------------------------------------------------------
# read_modbus_data — happy paths
# ---------------------------------------------------------------------------


class TestInverterReadModbusDataHappyPath:
    async def _init(self):
        hub = MockHub()
        # init_device calls
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_COMMON_REGS),
                make_response(INVERTER_MMPPT_NONE),
            ]
        )
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        await inv.init_device()
        # reset mock for read_modbus_data calls
        # Order: 40044 (version) → 40069 (model) → 40119 (vendor4, fw>=3.20) → 40113 (grid)
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),  # 40044
                make_response(INVERTER_MODEL_REGS),  # 40069
                make_response([0, 0]),  # 40119 I_Status_Vendor4 (use_status_vendor4=True)
                make_response(INVERTER_GRID_STATUS_REGS),  # 40113 (grid status)
            ]
        )
        return inv

    async def test_sets_decoded_model_did(self):
        inv = await self._init()
        await inv.read_modbus_data()
        assert inv.decoded_model["C_SunSpec_DID"] == 101

    async def test_sets_decoded_model_length(self):
        inv = await self._init()
        await inv.read_modbus_data()
        assert inv.decoded_model["C_SunSpec_Length"] == 50

    async def test_updates_c_version(self):
        inv = await self._init()
        await inv.read_modbus_data()
        assert inv.decoded_common["C_Version"] == "3.20.0"

    async def test_sets_grid_status(self):
        inv = await self._init()
        await inv.read_modbus_data()
        assert inv.decoded_model["I_Grid_Status"] == 1
        assert inv._grid_status is True

    async def test_sets_ac_energy_wh(self):
        inv = await self._init()
        await inv.read_modbus_data()
        assert inv.decoded_model["AC_Energy_WH"] == 0x000F4240  # 1 000 000

    async def test_read_with_mmppt_2_populates_units(self):
        """With MMPPT=2, read_modbus_data reads 40123 and stores unit data."""
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_COMMON_REGS),
                make_response(INVERTER_MMPPT_2),
            ]
        )
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        await inv.init_device()

        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),  # 40044
                make_response(INVERTER_MODEL_REGS),  # 40069
                make_response([0, 0]),  # 40119 vendor4 status
                make_response(INVERTER_MMPPT_DATA_REGS),  # 40123 (48 regs, 2 units)
                make_response(INVERTER_GRID_STATUS_REGS),  # 40113
            ]
        )
        await inv.read_modbus_data()
        assert "mmppt_0" in inv.decoded_model
        assert "mmppt_1" in inv.decoded_model


# ---------------------------------------------------------------------------
# read_modbus_data — validation failures
# ---------------------------------------------------------------------------


class TestInverterReadModbusDataErrors:
    async def _init_no_extras(self):
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_COMMON_REGS),
                make_response(INVERTER_MMPPT_NONE),
            ]
        )
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        await inv.init_device()
        return inv, hub

    async def test_bad_did_raises_device_invalid(self):
        inv, hub = await self._init_no_extras()
        bad_model = make_inverter_model_regs(did=999)
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(bad_model),
                # use_status_vendor4=True → 40119, but DeviceInvalid is raised before that
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        with pytest.raises(DeviceInvalid, match="not usable"):
            await inv.read_modbus_data()

    async def test_wrong_length_raises_device_invalid(self):
        inv, hub = await self._init_no_extras()
        bad_model = make_inverter_model_regs()
        bad_model[1] = 99  # C_SunSpec_Length != 50
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(bad_model),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        with pytest.raises(DeviceInvalid, match="not usable"):
            await inv.read_modbus_data()

    async def test_modbus_io_error_raises_modbus_read_error(self):
        inv, hub = await self._init_no_extras()
        hub.modbus_read_holding_registers = AsyncMock(side_effect=ModbusIOError("timeout"))
        with pytest.raises(ModbusReadError, match="No response"):
            await inv.read_modbus_data()

    async def test_grid_status_illegal_address_disables(self):
        """IllegalAddress on grid status read disables the feature (no exception)."""
        inv, hub = await self._init_no_extras()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),  # 40119 vendor4
                ModbusIllegalAddress("no grid status"),  # 40113
            ]
        )
        await inv.read_modbus_data()
        assert inv._grid_status is False


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestInverterProperties:
    def setup_method(self):
        self.hub = MockHub()
        self.inv = SolarEdgeInverter(device_id=1, hub=self.hub)

    def test_fw_version_absent(self):
        assert self.inv.fw_version is None

    def test_fw_version_present(self):
        self.inv.decoded_common["C_Version"] = "3.20.0"
        assert self.inv.fw_version == "3.20.0"

    def test_is_mmppt_false_when_none(self):
        self.inv.decoded_mmppt = None
        assert self.inv.is_mmppt is False

    def test_is_mmppt_true_when_set(self):
        self.inv.decoded_mmppt = {"mmppt_Units": 2}
        assert self.inv.is_mmppt is True

    def test_online_delegates_to_hub(self):
        self.hub.online = True
        assert self.inv.online is True
        self.hub.online = False
        assert self.inv.online is False

    def test_last_update_none_initially(self):
        assert self.inv.last_update is None

    def test_set_last_update(self):
        import datetime

        ts = datetime.datetime(2025, 1, 1, 12, 0, 0)
        self.inv.set_last_update(ts)
        assert self.inv.last_update == ts

    def test_device_info_requires_attributes(self):
        """device_info property returns a DeviceInfo object once attributes are set."""
        self.inv.manufacturer = "SolarEdge"
        self.inv.model = "SE5000H"
        self.inv.serial = "SN123456"
        self.inv.option = "000TNS"
        self.inv.name = "Solaredge I1"
        self.inv.uid_base = "SE5000H_SN123456"
        self.inv.decoded_common["C_Version"] = "3.20.0"
        info = self.inv.device_info
        assert info is not None


# ---------------------------------------------------------------------------
# SolarEdgeMMPPTUnit
# ---------------------------------------------------------------------------


class TestSolarEdgeMMPPTUnit:
    def setup_method(self):
        self.hub = MockHub()
        self.hub.online = True
        self.inv = SolarEdgeInverter(device_id=1, hub=self.hub)
        self.inv.decoded_mmppt = {"mmppt_Units": 2}
        self.inv.decoded_model = {
            "mmppt_0": {"ID": 1, "IDStr": "MPPT1"},
            "mmppt_1": {"ID": 2, "IDStr": "MPPT2"},
        }
        self.unit = SolarEdgeMMPPTUnit(self.inv, self.hub, unit=0)

    def test_online_true_when_both_online(self):
        self.hub.online = True
        assert self.unit.online is True

    def test_online_false_when_hub_offline(self):
        self.hub.online = False
        assert self.unit.online is False

    def test_mmppt_id(self):
        assert self.unit.mmppt_id == 1

    def test_mmppt_idstr(self):
        assert self.unit.mmppt_idstr == "MPPT1"


# ---------------------------------------------------------------------------
# Helpers shared by optional-path tests
# ---------------------------------------------------------------------------


async def _init_inverter_no_mmppt():
    """Return (inv, hub) after init_device with MMPPT_NONE and fw 3.20.0."""
    hub = MockHub()
    hub.modbus_read_holding_registers = AsyncMock(
        side_effect=[
            make_response(INVERTER_COMMON_REGS),
            make_response(INVERTER_MMPPT_NONE),
        ]
    )
    inv = SolarEdgeInverter(device_id=1, hub=hub)
    await inv.init_device()
    return inv, hub


def _base_reads():
    """Minimal responses for read_modbus_data (no options, fw=3.20, no MMPPT)."""
    return [
        make_response(INVERTER_VERSION_REGS),  # 40044
        make_response(INVERTER_MODEL_REGS),  # 40069
        make_response([0, 0]),  # 40119 vendor4 (use_status_vendor4)
        make_response(INVERTER_GRID_STATUS_REGS),  # 40113
    ]


# ---------------------------------------------------------------------------
# MMPPT=3 path
# ---------------------------------------------------------------------------


class TestInverterMmppt3:
    async def test_mmppt_3_reads_68_regs_and_populates_3_units(self):
        hub = MockHub()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_COMMON_REGS),
                make_response(INVERTER_MMPPT_3),
            ]
        )
        inv = SolarEdgeInverter(device_id=1, hub=hub)
        await inv.init_device()

        assert inv.decoded_mmppt["mmppt_Units"] == 3
        assert len(inv.mmppt_units) == 3

        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),  # vendor4
                make_response(INVERTER_MMPPT_3_DATA_REGS),  # 40123 rcount=68
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert "mmppt_0" in inv.decoded_model
        assert "mmppt_1" in inv.decoded_model
        assert "mmppt_2" in inv.decoded_model


# ---------------------------------------------------------------------------
# Grid status edge cases
# ---------------------------------------------------------------------------


class TestInverterGridStatusEdgeCases:
    async def test_grid_status_false_skips_read(self):
        """When _grid_status=False, no read at 40113 is issued."""
        inv, hub = await _init_inverter_no_mmppt()
        inv._grid_status = False
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                # no 40113 read — would StopAsyncIteration if attempted
            ]
        )
        await inv.read_modbus_data()
        assert "I_Grid_Status" not in inv.decoded_model

    async def test_grid_status_modbus_io_exception_does_not_raise(self):
        """pymodbus ModbusIOException on 40113 is swallowed, not re-raised."""
        from pymodbus.exceptions import ModbusIOException as PyModbusIOException

        inv, hub = await _init_inverter_no_mmppt()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                PyModbusIOException("io error"),  # 40113
            ]
        )
        await inv.read_modbus_data()  # must not raise
        assert "I_Grid_Status" not in inv.decoded_model


# ---------------------------------------------------------------------------
# Global Power Control (61440)
# ---------------------------------------------------------------------------


class TestInverterGlobalPowerControl:
    async def _init(self):
        inv, hub = await _init_inverter_no_mmppt()
        hub.option_detect_extras = True
        inv.advanced_power_control = False  # isolate — skip the APC block
        return inv, hub

    async def test_happy_path_sets_flag_and_fields(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response([0] * 4),  # 61440
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.global_power_control is True
        assert "I_RRCR" in inv.decoded_model
        assert "I_Power_Limit" in inv.decoded_model
        assert "I_CosPhi" in inv.decoded_model

    async def test_illegal_address_sets_false_and_no_exception(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                ModbusIllegalAddress("no GPC"),  # 61440
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.global_power_control is False

    async def test_modbus_io_error_raises_modbus_read_error(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                ModbusIOError("timeout"),  # 61440
            ]
        )
        with pytest.raises(ModbusReadError):
            await inv.read_modbus_data()

    async def test_timeout_creates_issue_and_does_not_raise(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                TimeoutError(),  # 61440 times out
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        with patch("custom_components.solaredge_modbus_multi.inverter.ir.async_create_issue") as mock_issue:
            await inv.read_modbus_data()
        mock_issue.assert_called_once()

    async def test_pymodbus_io_exception_creates_issue_and_does_not_raise(self):
        from pymodbus.exceptions import ModbusIOException as PyModbusIOException

        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                PyModbusIOException("io error"),  # 61440
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        with patch("custom_components.solaredge_modbus_multi.inverter.ir.async_create_issue") as mock_issue:
            await inv.read_modbus_data()
        mock_issue.assert_called_once()

    async def test_global_power_control_false_skips_read(self):
        """Second call with global_power_control=False issues no 61440 read."""
        inv, hub = await self._init()
        inv.global_power_control = False
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),  # directly to 40113
            ]
        )
        await inv.read_modbus_data()
        assert "I_RRCR" not in inv.decoded_model


# ---------------------------------------------------------------------------
# Advanced Power Control (61696 + 61782)
# ---------------------------------------------------------------------------


class TestInverterAdvancedPowerControl:
    async def _init(self):
        inv, hub = await _init_inverter_no_mmppt()
        hub.option_detect_extras = True
        inv.global_power_control = False  # isolate — skip the GPC block
        return inv, hub

    async def test_happy_path_sets_flag(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response([0] * 86),  # 61696
                make_response([0] * 84),  # 61782
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.advanced_power_control is True
        assert "AdvPwrCtrlEn" in inv.decoded_model
        assert "PwrVsFreqY_0" in inv.decoded_model

    async def test_illegal_address_on_first_block_sets_false(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                ModbusIllegalAddress("no APC"),  # 61696
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.advanced_power_control is False

    async def test_modbus_io_error_raises_modbus_read_error(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                ModbusIOError("timeout"),  # 61696
            ]
        )
        with pytest.raises(ModbusReadError):
            await inv.read_modbus_data()

    async def test_timeout_creates_issue_and_does_not_raise(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                TimeoutError(),  # 61696 times out
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        with patch("custom_components.solaredge_modbus_multi.inverter.ir.async_create_issue") as mock_issue:
            await inv.read_modbus_data()
        mock_issue.assert_called_once()

    async def test_advanced_power_control_false_skips_both_blocks(self):
        inv, hub = await self._init()
        inv.advanced_power_control = False
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert "AdvPwrCtrlEn" not in inv.decoded_model


# ---------------------------------------------------------------------------
# Site Limit Control (57344 + 57362)
# ---------------------------------------------------------------------------


class TestInverterSiteLimitControl:
    async def _init(self):
        inv, hub = await _init_inverter_no_mmppt()
        hub.option_site_limit_control = True
        return inv, hub

    async def test_happy_path_populates_fields(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response([0] * 4),  # 57344
                make_response([0] * 2),  # 57362
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.site_limit_control is True
        assert "E_Lim_Ctl_Mode" in inv.decoded_model
        assert "E_Site_Limit" in inv.decoded_model
        assert "Ext_Prod_Max" in inv.decoded_model

    async def test_illegal_address_on_57344_sets_false(self):
        # 57362 block is OUTSIDE the 57344 try/except, so it still runs even when 57344 fails
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                ModbusIllegalAddress("no site limit"),  # 57344
                make_response([0] * 2),  # 57362 still runs
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.site_limit_control is False

    async def test_illegal_address_on_57362_removes_ext_prod_max(self):
        """57362 returning IllegalAddress removes Ext_Prod_Max from the model."""
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response([0] * 4),  # 57344 ok
                ModbusIllegalAddress("no ext prod max"),  # 57362
                make_response(INVERTER_GRID_STATUS_REGS),
            ]
        )
        await inv.read_modbus_data()
        assert inv.site_limit_control is True
        assert "Ext_Prod_Max" not in inv.decoded_model

    async def test_io_error_on_57344_raises_modbus_read_error(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                ModbusIOError("timeout"),  # 57344
            ]
        )
        with pytest.raises(ModbusReadError):
            await inv.read_modbus_data()

    async def test_io_error_on_57362_raises_modbus_read_error(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response([0] * 4),  # 57344 ok
                ModbusIOError("timeout"),  # 57362
            ]
        )
        with pytest.raises(ModbusReadError):
            await inv.read_modbus_data()


# ---------------------------------------------------------------------------
# Storage Control (57348)
# ---------------------------------------------------------------------------


class TestInverterStorageControl:
    async def _init(self):
        inv, hub = await _init_inverter_no_mmppt()
        hub.option_storage_control = True
        return inv, hub

    async def test_happy_path_populates_decoded_storage_control(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
                make_response([0] * 14),  # 57348
            ]
        )
        await inv.read_modbus_data()
        assert isinstance(inv.decoded_storage_control, dict)
        assert "control_mode" in inv.decoded_storage_control
        assert "backup_reserve" in inv.decoded_storage_control
        assert "command_timeout" in inv.decoded_storage_control

    async def test_has_battery_true_when_battery_matches_inverter(self):
        inv, hub = await self._init()
        mock_battery = MockHub()  # used as a plain object here
        mock_battery.inverter_unit_id = 1
        hub.batteries = [mock_battery]
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
                make_response([0] * 14),
            ]
        )
        await inv.read_modbus_data()
        assert inv.has_battery is True

    async def test_has_battery_false_when_no_matching_battery(self):
        inv, hub = await self._init()
        mock_battery = MockHub()
        mock_battery.inverter_unit_id = 99  # different inverter
        hub.batteries = [mock_battery]
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
                make_response([0] * 14),
            ]
        )
        await inv.read_modbus_data()
        assert inv.has_battery is False

    async def test_illegal_address_sets_decoded_storage_control_false(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
                ModbusIllegalAddress("no storage"),  # 57348
            ]
        )
        await inv.read_modbus_data()
        assert inv.decoded_storage_control is False

    async def test_io_error_raises_modbus_read_error(self):
        inv, hub = await self._init()
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
                ModbusIOError("timeout"),  # 57348
            ]
        )
        with pytest.raises(ModbusReadError):
            await inv.read_modbus_data()

    async def test_decoded_storage_control_false_skips_read(self):
        """When decoded_storage_control=False, no 57348 read is issued."""
        inv, hub = await self._init()
        inv.decoded_storage_control = False
        hub.modbus_read_holding_registers = AsyncMock(
            side_effect=[
                make_response(INVERTER_VERSION_REGS),
                make_response(INVERTER_MODEL_REGS),
                make_response([0, 0]),
                make_response(INVERTER_GRID_STATUS_REGS),
                # no 57348 read
            ]
        )
        await inv.read_modbus_data()
        assert inv.decoded_storage_control is False
