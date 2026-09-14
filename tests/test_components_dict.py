"""Tests for component_to_dict()/component_field_names() in components.py."""

from modbus_connection.mock import MockModbusConnection

from custom_components.solaredge_modbus_multi.components import (
    BatteryInfo,
    GlobalDynamicPowerControl,
    component_field_names,
    component_to_dict,
)


def _unit():
    return MockModbusConnection().for_unit(1)


async def test_component_to_dict_plain_component_uses_declared_fields():
    mock_unit = _unit()
    mock_unit.load_raw({"holding": {61440: 3, 61441: 50}})
    component = GlobalDynamicPowerControl(mock_unit)
    await component.async_update()

    result = component_to_dict(component)

    assert result["I_RRCR"] == 3
    assert result["I_Power_Limit"] == 50
    assert "I_CosPhi" in result


def test_component_to_dict_after_restrict_fields_shows_none_not_missing():
    component = GlobalDynamicPowerControl(_unit())
    component.restrict_fields(["I_RRCR"])

    result = component_to_dict(component)

    assert result["I_RRCR"] is None
    assert result["I_Power_Limit"] is None


def test_component_field_names_battery_info_excludes_private_raw_fields():
    component = BatteryInfo(_unit())

    names = component_field_names(component)

    assert "B_Manufacturer" in names
    assert "B_Model" in names
    assert "B_SerialNumber" in names
    assert "_B_Manufacturer" not in names
    assert "_B_Model" not in names
    assert "_B_SerialNumber" not in names


def test_component_to_dict_battery_info_uses_cleaned_properties_not_raw_fields():
    component = BatteryInfo(_unit())
    component._values["_B_Manufacturer"] = "LG Chem\x00\x00SERIAL123"
    component._values["_B_Model"] = "RESU10H\x00\x00SERIAL123"
    component._values["_B_SerialNumber"] = "SERIAL123"

    result = component_to_dict(component)

    assert result["B_Manufacturer"] == "LG Chem"
    assert result["B_Model"] == "RESU10H"
    assert result["B_SerialNumber"] == "SERIAL123"
    assert "_B_Manufacturer" not in result
    assert "_B_Model" not in result
    assert "_B_SerialNumber" not in result
