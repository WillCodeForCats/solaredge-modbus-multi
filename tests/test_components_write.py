"""Component write tests."""

import pytest
from modbus_connection.mock import MockModbusUnit, WriteEvent

from custom_components.solaredge_modbus_multi.components import AdvancedPowerControl

# Add more later, this is just a starting point with a simple test.


@pytest.mark.parametrize(
    "field, address",
    [
        ("CommitPwrCtlSettings", 61696),
        ("RestorePwrCtlDefaults", 61697),
    ],
)
@pytest.mark.asyncio
async def test_advanced_power_control_buttons_write(
    mock_modbus_unit: MockModbusUnit, field: str, address: int
) -> None:
    events: list[WriteEvent] = []
    mock_modbus_unit.on_write(events.append)

    component = AdvancedPowerControl(mock_modbus_unit)
    await component.write(field, 1)

    assert len(events) == 1
    event = events[0]
    assert event.register_type == "holding"
    assert event.address == address
    assert event.values == [1]
