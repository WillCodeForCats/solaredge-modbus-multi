"""Decode round-trip test for the AdvancedPowerControl fields sensor.py uses."""

import pytest
from modbus_connection.mock import MockModbusUnit

from custom_components.solaredge_modbus_multi.components import AdvancedPowerControl

# Add more later, this is just a starting point with a simple test.


@pytest.mark.asyncio
async def test_advanced_power_control_decode(mock_modbus_unit: MockModbusUnit) -> None:
    mock_modbus_unit.load_raw(
        {
            "holding": {
                # CommitPwrCtlSettings: Int16 (signed)
                61696: 0x0000,
                # RestorePwrCtlDefaults: Int16 (signed)
                61697: 0xFFFF,
            }
        }
    )

    component = AdvancedPowerControl(mock_modbus_unit)
    await component.async_update()

    assert component.CommitPwrCtlSettings == 0
    assert component.RestorePwrCtlDefaults == -1
