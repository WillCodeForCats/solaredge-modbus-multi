"""Tests for diagnostics._inverter_model()."""

from modbus_connection.mock import MockModbusConnection

from custom_components.solaredge_modbus_multi.components import (
    AdvancedPowerControl,
    GlobalDynamicPowerControl,
    InverterData,
    MmpptData,
    SiteLimitControl,
)
from custom_components.solaredge_modbus_multi.diagnostics import _inverter_model


class _FakeInverter:
    def __init__(self, unit):
        self.inverter_data = InverterData(unit)
        self.mmppt_data = MmpptData(unit)
        self.global_power_control_data = GlobalDynamicPowerControl(unit)
        self.advanced_power_control_data = AdvancedPowerControl(unit)
        self.site_limit_control_data = SiteLimitControl(unit)


def test_inverter_model_merges_every_component():
    unit = MockModbusConnection().for_unit(1)
    inverter = _FakeInverter(unit)

    model = _inverter_model(inverter)

    assert "AC_Power" in model
    assert "I_Power_Limit" in model
    assert "CommitPwrCtlSettings" in model
    assert "E_Lim_Ctl_Mode" in model


def test_inverter_model_defaults_to_none_for_never_read_components():
    unit = MockModbusConnection().for_unit(1)
    inverter = _FakeInverter(unit)

    model = _inverter_model(inverter)

    assert model["AC_Power"] is None
    assert model["I_Power_Limit"] is None
    assert model["CommitPwrCtlSettings"] is None
    assert model["E_Lim_Ctl_Mode"] is None


async def test_inverter_model_reflects_a_successful_read():
    unit = MockModbusConnection().for_unit(1)
    unit.load_raw({"holding": {61441: 42}})
    inverter = _FakeInverter(unit)
    await inverter.global_power_control_data.async_update()

    model = _inverter_model(inverter)

    assert model["I_Power_Limit"] == 42
