"""Tests for SolarEdgeModbusMultiHub.component_write()'s exception mapping."""

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from modbus_connection.exceptions import (
    IllegalDataAddressError,
    IllegalDataValueError,
    IllegalFunctionError,
    ModbusExceptionError,
)
from modbus_connection.mock import MockModbusConnection

from custom_components.solaredge_modbus_multi.components import (
    GlobalDynamicPowerControl,
)
from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.hub import SolarEdgeModbusMultiHub

ENTRY_DATA = {
    CONF_NAME: "SolarEdge",
    CONF_HOST: "127.0.0.1",
    CONF_PORT: 1502,
}
I_POWER_LIMIT_ADDRESS = 61441


def _make_hub(hass):
    hass.data[DOMAIN] = {"yaml": {}}
    connection = MockModbusConnection()
    hub = SolarEdgeModbusMultiHub(hass, "test_entry_id", ENTRY_DATA, {}, connection)
    return hub, connection


@pytest.mark.parametrize(
    "error, expected_message",
    [
        (IllegalFunctionError(), "Function not supported by device at ID 1."),
        (IllegalDataAddressError(), "Address not supported at device at ID 1."),
        (IllegalDataValueError(), "Value invalid for device at ID 1."),
    ],
)
async def test_component_write_maps_specific_typed_exception(
    hass, error, expected_message
):
    hub, connection = _make_hub(hass)
    connection.for_unit(1).fail_write(I_POWER_LIMIT_ADDRESS, error)
    component = GlobalDynamicPowerControl(connection.for_unit(1))

    with pytest.raises(HomeAssistantError) as exc_info:
        await hub.component_write(1, component, "I_Power_Limit", 50)

    assert str(exc_info.value) == expected_message


async def test_component_write_falls_back_to_generic_message_for_other_codes(hass):
    hub, connection = _make_hub(hass)
    connection.for_unit(1).fail_write(
        I_POWER_LIMIT_ADDRESS, ModbusExceptionError(4, "device failure")
    )
    component = GlobalDynamicPowerControl(connection.for_unit(1))

    with pytest.raises(HomeAssistantError) as exc_info:
        await hub.component_write(1, component, "I_Power_Limit", 50)

    assert str(exc_info.value) == "Write rejected by device at ID 1: device failure"
