"""Tests for the binary sensor platform.

Covers async_setup_entry's entity selection, the shared base class properties,
and each binary sensor's availability, state, and attributes.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.solaredge_modbus_multi.binary_sensor import (
    AdvPowerControlEnabled,
    GridStatusOnOff,
    InverterProblem,
    async_setup_entry,
)
from custom_components.solaredge_modbus_multi.const import (
    DOMAIN,
    VENDOR4_STATUS,
    VENDOR_STATUS,
    SunSpecNotImpl,
)

COORDINATOR = SimpleNamespace(last_update_success=True)
FAILED_COORDINATOR = SimpleNamespace(last_update_success=False)


def _setup_hass(inverters, detect_extras):
    hub = SimpleNamespace(inverters=inverters, option_detect_extras=detect_extras)
    entry = SimpleNamespace(entry_id="entry1")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry1": {"hub": hub, "coordinator": COORDINATOR}}}
    )
    return hass, entry


@pytest.mark.parametrize(
    ("detect_extras", "expected"),
    [
        (False, [InverterProblem, GridStatusOnOff]),
        (True, [InverterProblem, GridStatusOnOff, AdvPowerControlEnabled]),
    ],
)
async def test_setup_entry_entities_per_inverter(detect_extras, expected):
    """Each inverter gets problem and grid status, plus adv power control with extras."""
    hass, entry = _setup_hass([SimpleNamespace(), SimpleNamespace()], detect_extras)
    add = MagicMock()

    await async_setup_entry(hass, entry, add)

    entities = add.call_args.args[0]
    assert [type(e) for e in entities] == expected * 2


async def test_setup_entry_no_inverters_adds_nothing():
    """Nothing is added when the hub has no inverters."""
    hass, entry = _setup_hass([], True)
    add = MagicMock()

    await async_setup_entry(hass, entry, add)

    add.assert_not_called()


def test_base_class_properties():
    """Device info and config entry values come from the platform and entry."""
    platform = SimpleNamespace(uid_base="inverter_1", device_info={"id": "dev"})
    entry = SimpleNamespace(entry_id="entry1", data={"name": "Site"})
    entity = InverterProblem(platform, entry, COORDINATOR)

    assert entity.device_info == {"id": "dev"}
    assert entity.config_entry_id == "entry1"
    assert entity.config_entry_name == "Site"
    assert entity.should_poll is False


def test_coordinator_update_writes_state():
    """A coordinator update writes the entity state."""
    platform = SimpleNamespace(uid_base="inverter_1")
    entity = InverterProblem(platform, None, COORDINATOR)

    with patch.object(entity, "async_write_ha_state") as write_state:
        entity._handle_coordinator_update()

    write_state.assert_called_once_with()


@pytest.mark.parametrize(
    ("status", "available", "is_on"),
    [
        (7, True, True),
        (4, True, False),
        (1, True, False),
        (None, False, None),
        (SunSpecNotImpl.UINT16, False, None),
        (99, False, None),
    ],
)
def test_inverter_problem(status, available, is_on):
    """Problem is on only for the fault status, and unavailable for bad status."""
    platform = SimpleNamespace(
        uid_base="inverter_1",
        inverter_data=SimpleNamespace(I_Status=status),
    )
    entity = InverterProblem(platform, None, COORDINATOR)

    assert entity.unique_id == "inverter_1_problem"
    assert entity.name == "Problem"
    assert entity.available is available
    if available:
        assert entity.is_on is is_on


def test_inverter_problem_unavailable_when_update_failed():
    """Problem is unavailable when the coordinator update failed."""
    platform = SimpleNamespace(
        uid_base="inverter_1", inverter_data=SimpleNamespace(I_Status=4)
    )
    entity = InverterProblem(platform, None, FAILED_COORDINATOR)
    assert entity.available is False


@pytest.mark.parametrize(
    ("use_v4", "vendor", "vendor4", "expected"),
    [
        (False, 17, None, {"status_value": 17, "status_text": VENDOR_STATUS[17]}),
        (False, 12345, None, {"status_value": 12345}),
        (False, SunSpecNotImpl.UINT16, None, {}),
        (False, None, None, {}),
        (True, 0, SunSpecNotImpl.UINT32, {}),
        (True, 0, None, {}),
        (
            True,
            0,
            0x03000002,
            {"status_value": "3x2", "status_text": VENDOR4_STATUS[3][2]},
        ),
        (True, 0, 0x01000001, {"status_value": "1x1"}),
    ],
)
def test_inverter_problem_vendor_attributes(use_v4, vendor, vendor4, expected):
    """Attributes come from vendor4 when in use, otherwise from vendor status."""
    platform = SimpleNamespace(
        uid_base="inverter_1",
        use_status_vendor4=use_v4,
        inverter_data=SimpleNamespace(
            I_Status=7, I_Status_Vendor=vendor, I_Status_Vendor4=vendor4
        ),
    )
    entity = InverterProblem(platform, None, COORDINATOR)
    assert entity.extra_state_attributes == expected


@pytest.mark.parametrize(
    ("grid_status", "available", "is_on"),
    [
        (0, True, True),
        (1, True, False),
        (0x00010000, True, False),
        (None, False, None),
    ],
)
def test_grid_status_on_off(grid_status, available, is_on):
    """Grid is on only when the status is zero, and unavailable when unread."""
    platform = SimpleNamespace(
        uid_base="inverter_1",
        inverter_data=SimpleNamespace(I_Grid_Status=grid_status),
    )
    entity = GridStatusOnOff(platform, None, COORDINATOR)

    assert entity.unique_id == "inverter_1_grid_status_on_off"
    assert entity.name == "Grid Status"
    assert entity.available is available
    assert entity.entity_registry_enabled_default is available
    if available:
        assert entity.is_on is is_on


def test_grid_status_unavailable_when_update_failed():
    """Grid status is unavailable when the coordinator update failed."""
    platform = SimpleNamespace(
        uid_base="inverter_1", inverter_data=SimpleNamespace(I_Grid_Status=0)
    )
    entity = GridStatusOnOff(platform, None, FAILED_COORDINATOR)
    assert entity.available is False


@pytest.mark.parametrize(
    ("supported", "enabled", "available", "is_on"),
    [
        (True, 1, True, True),
        (True, 0, True, False),
        (True, None, False, None),
        (False, 1, False, None),
    ],
)
def test_adv_power_control_enabled(supported, enabled, available, is_on):
    """On only when enabled, unavailable when unsupported or unread."""
    platform = SimpleNamespace(
        uid_base="inverter_1",
        has_advanced_power_control=supported,
        advanced_power_control_data=SimpleNamespace(AdvPwrCtrlEn=enabled),
    )
    entity = AdvPowerControlEnabled(platform, None, COORDINATOR)

    assert entity.unique_id == "inverter_1_adv_pwr_ctrl_en"
    assert entity.name == "Advanced Power Control"
    assert entity.entity_category == "diagnostic"
    assert entity.available is available
    if available:
        assert entity.is_on is is_on
