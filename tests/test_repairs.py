"""Tests for RetryFeatureDetectionRepairFlow in repairs.py."""

from types import SimpleNamespace

from homeassistant.data_entry_flow import FlowResultType

from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.repairs import (
    RetryFeatureDetectionRepairFlow,
)


def _make_flow(hass, entry_id, inverter, attr):
    hub = SimpleNamespace(inverters=[inverter])
    hass.data.setdefault(DOMAIN, {})[entry_id] = {"hub": hub}

    flow = RetryFeatureDetectionRepairFlow(entry_id, inverter.inverter_unit_id, attr)
    flow.hass = hass
    flow.handler = DOMAIN
    flow.issue_id = f"test_issue_{entry_id}"
    return flow


async def test_confirm_step_shows_form_first(hass):
    inverter = SimpleNamespace(inverter_unit_id=1, global_power_control=False)
    flow = _make_flow(hass, "test_entry", inverter, "global_power_control")

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert inverter.global_power_control is False


async def test_submitting_resets_the_flag_to_none(hass):
    inverter = SimpleNamespace(inverter_unit_id=1, global_power_control=False)
    flow = _make_flow(hass, "test_entry", inverter, "global_power_control")

    result = await flow.async_step_confirm(user_input={})

    assert inverter.global_power_control is None
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_resets_the_right_inverter_and_attribute(hass):
    inverter_1 = SimpleNamespace(inverter_unit_id=1, advanced_power_control=False)
    inverter_2 = SimpleNamespace(inverter_unit_id=2, advanced_power_control=False)
    hub = SimpleNamespace(inverters=[inverter_1, inverter_2])
    hass.data.setdefault(DOMAIN, {})["test_entry"] = {"hub": hub}

    flow = RetryFeatureDetectionRepairFlow("test_entry", 2, "advanced_power_control")
    flow.hass = hass

    await flow.async_step_confirm(user_input={})

    assert inverter_1.advanced_power_control is False
    assert inverter_2.advanced_power_control is None


async def test_unknown_inverter_unit_id_is_a_no_op(hass):
    inverter = SimpleNamespace(inverter_unit_id=1, global_power_control=False)
    flow = _make_flow(hass, "test_entry", inverter, "global_power_control")
    flow._inverter_unit_id = 99

    result = await flow.async_step_confirm(user_input={})

    assert inverter.global_power_control is False
    assert result["type"] == FlowResultType.CREATE_ENTRY
