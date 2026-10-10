"""Tests for the switch platform.

Covers async_setup_entry's entity selection, the shared base class properties,
and each switch's availability, state, and write behavior.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.solaredge_modbus_multi.const import DOMAIN, SunSpecNotImpl
from custom_components.solaredge_modbus_multi.switch import (
    SolarEdgeExternalProduction,
    SolarEdgeGridControl,
    SolarEdgeNegativeSiteLimit,
    async_setup_entry,
)


def _coordinator(last_update_success=True):
    return SimpleNamespace(
        last_update_success=last_update_success,
        async_request_refresh=AsyncMock(),
    )


def _setup_hass(inverters, site_limit, detect_extras):
    hub = SimpleNamespace(
        inverters=inverters,
        option_site_limit_control=site_limit,
        option_detect_extras=detect_extras,
    )
    entry = SimpleNamespace(entry_id="entry1")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry1": {"hub": hub, "coordinator": _coordinator()}}}
    )
    return hass, entry


@pytest.mark.parametrize(
    ("site_limit", "detect_extras", "expected"),
    [
        (False, False, []),
        (True, False, [SolarEdgeExternalProduction, SolarEdgeNegativeSiteLimit]),
        (False, True, [SolarEdgeGridControl]),
        (
            True,
            True,
            [
                SolarEdgeExternalProduction,
                SolarEdgeNegativeSiteLimit,
                SolarEdgeGridControl,
            ],
        ),
    ],
)
async def test_setup_entry_entities_per_inverter(site_limit, detect_extras, expected):
    """Entities per inverter follow the site limit and extras options."""
    hass, entry = _setup_hass(
        [SimpleNamespace(), SimpleNamespace()], site_limit, detect_extras
    )
    add = MagicMock()

    await async_setup_entry(hass, entry, add)

    if expected:
        entities = add.call_args.args[0]
        assert [type(e) for e in entities] == expected * 2
    else:
        add.assert_not_called()


def test_base_class_properties():
    """Device info and config entry values come from the platform and entry."""
    platform = SimpleNamespace(uid_base="inverter_1", device_info={"id": "dev"})
    entry = SimpleNamespace(entry_id="entry1", data={"name": "Site"})
    entity = SolarEdgeGridControl(platform, entry, _coordinator())

    assert entity.device_info == {"id": "dev"}
    assert entity.config_entry_id == "entry1"
    assert entity.config_entry_name == "Site"
    assert entity.should_poll is False


def test_coordinator_update_writes_state():
    """A coordinator update writes the entity state."""
    platform = SimpleNamespace(uid_base="inverter_1")
    entity = SolarEdgeGridControl(platform, None, _coordinator())

    with patch.object(entity, "async_write_ha_state") as write_state:
        entity._handle_coordinator_update()

    write_state.assert_called_once_with()


def _site_limit_platform(mode=0, supported=True):
    return SimpleNamespace(
        uid_base="inverter_1",
        has_site_limit_control=supported,
        site_limit_control_data=SimpleNamespace(E_Lim_Ctl_Mode=mode),
        write=AsyncMock(),
    )


@pytest.mark.parametrize(
    ("cls", "suffix", "name", "bit", "enabled_default"),
    [
        (
            SolarEdgeExternalProduction,
            "_external_production",
            "External Production",
            10,
            False,
        ),
        (
            SolarEdgeNegativeSiteLimit,
            "_negative_site_limit",
            "Negative Site Limit",
            11,
            True,
        ),
    ],
)
class TestSiteLimitSwitches:
    """Behavior shared by the switches that toggle bits of E_Lim_Ctl_Mode."""

    def test_identity(self, cls, suffix, name, bit, enabled_default):
        """Unique id, name, and default enablement."""
        entity = cls(_site_limit_platform(), None, _coordinator())

        assert entity.unique_id == f"inverter_1{suffix}"
        assert entity.name == name
        assert entity.entity_registry_enabled_default is enabled_default

    @pytest.mark.parametrize(
        ("mode", "supported", "update_ok", "available"),
        [
            (0, True, True, True),
            (0, False, True, False),
            (0, True, False, False),
            (None, True, True, False),
            (SunSpecNotImpl.UINT16, True, True, False),
        ],
    )
    def test_available(
        self,
        cls,
        suffix,
        name,
        bit,
        enabled_default,
        mode,
        supported,
        update_ok,
        available,
    ):
        """Available only when supported, updated, and the mode was read."""
        entity = cls(
            _site_limit_platform(mode, supported), None, _coordinator(update_ok)
        )
        assert entity.available is available

    def test_is_on(self, cls, suffix, name, bit, enabled_default):
        """On reflects only this switch's bit."""
        on = cls(_site_limit_platform(1 << bit), None, _coordinator())
        off = cls(_site_limit_platform(0xFFFF & ~(1 << bit)), None, _coordinator())

        assert on.is_on
        assert not off.is_on

    async def test_turn_on(self, cls, suffix, name, bit, enabled_default):
        """Turning on sets the bit and keeps the others."""
        platform = _site_limit_platform(0b1)
        coordinator = _coordinator()
        entity = cls(platform, None, coordinator)

        await entity.async_turn_on()

        platform.write.assert_awaited_once_with(
            platform.site_limit_control_data, "E_Lim_Ctl_Mode", 0b1 | (1 << bit)
        )
        coordinator.async_request_refresh.assert_awaited_once_with()

    async def test_turn_off(self, cls, suffix, name, bit, enabled_default):
        """Turning off clears the bit and keeps the others."""
        platform = _site_limit_platform(0b1 | (1 << bit))
        coordinator = _coordinator()
        entity = cls(platform, None, coordinator)

        await entity.async_turn_off()

        platform.write.assert_awaited_once_with(
            platform.site_limit_control_data, "E_Lim_Ctl_Mode", 0b1
        )
        coordinator.async_request_refresh.assert_awaited_once_with()


def _adv_platform(enabled=0, supported=True):
    return SimpleNamespace(
        uid_base="inverter_1",
        has_advanced_power_control=supported,
        advanced_power_control_data=SimpleNamespace(AdvPwrCtrlEn=enabled),
        write=AsyncMock(),
    )


def test_grid_control_identity():
    """Unique id and name."""
    entity = SolarEdgeGridControl(_adv_platform(), None, _coordinator())

    assert entity.unique_id == "inverter_1_adv_pwr_ctrl"
    assert entity.name == "Advanced Power Control"


@pytest.mark.parametrize(
    ("enabled", "supported", "update_ok", "available"),
    [
        (0, True, True, True),
        (0, False, True, False),
        (0, True, False, False),
        (None, True, True, False),
    ],
)
def test_grid_control_available(enabled, supported, update_ok, available):
    """Available only when supported, updated, and the value was read."""
    entity = SolarEdgeGridControl(
        _adv_platform(enabled, supported), None, _coordinator(update_ok)
    )
    assert entity.available is available


@pytest.mark.parametrize(("enabled", "is_on"), [(1, True), (0, False)])
def test_grid_control_is_on(enabled, is_on):
    """On only when the enable register is 1."""
    entity = SolarEdgeGridControl(_adv_platform(enabled), None, _coordinator())
    assert entity.is_on is is_on


@pytest.mark.parametrize(
    ("method", "value"), [("async_turn_on", 1), ("async_turn_off", 0)]
)
async def test_grid_control_writes(method, value):
    """Turning on or off writes the enable register and refreshes."""
    platform = _adv_platform()
    coordinator = _coordinator()
    entity = SolarEdgeGridControl(platform, None, coordinator)

    await getattr(entity, method)()

    platform.write.assert_awaited_once_with(
        platform.advanced_power_control_data, "AdvPwrCtrlEn", value
    )
    coordinator.async_request_refresh.assert_awaited_once_with()
