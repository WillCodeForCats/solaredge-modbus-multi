"""Tests for the button platform.

Covers async_setup_entry's entity selection, the shared base class properties,
and each button's identity, availability, and press behavior.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.solaredge_modbus_multi.button import (
    SolarEdgeCommitControlSettings,
    SolarEdgeDefaultControlSettings,
    SolarEdgeRefreshButton,
    async_setup_entry,
)
from custom_components.solaredge_modbus_multi.const import DOMAIN


def _coordinator(last_update_success=True):
    """Build a fake coordinator with a mocked refresh request."""
    return SimpleNamespace(
        last_update_success=last_update_success,
        async_request_refresh=AsyncMock(),
    )


def _setup_hass(inverters, detect_extras):
    """Build a fake hass and config entry around a hub with the given inverters."""
    hub = SimpleNamespace(inverters=inverters, option_detect_extras=detect_extras)
    entry = SimpleNamespace(entry_id="entry1")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry1": {"hub": hub, "coordinator": _coordinator()}}}
    )
    return hass, entry


@pytest.mark.parametrize(
    ("detect_extras", "expected"),
    [
        (False, [SolarEdgeRefreshButton]),
        (
            True,
            [
                SolarEdgeRefreshButton,
                SolarEdgeCommitControlSettings,
                SolarEdgeDefaultControlSettings,
            ],
        ),
    ],
)
async def test_setup_entry_entities_per_inverter(detect_extras, expected):
    """Each inverter gets a refresh button, plus the control buttons with extras."""
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
    entity = SolarEdgeRefreshButton(platform, entry, _coordinator())

    assert entity.device_info == {"id": "dev"}
    assert entity.config_entry_id == "entry1"
    assert entity.config_entry_name == "Site"
    assert entity.should_poll is False


def test_coordinator_update_writes_state():
    """A coordinator update writes the entity state."""
    platform = SimpleNamespace(uid_base="inverter_1")
    entity = SolarEdgeRefreshButton(platform, None, _coordinator())

    with patch.object(entity, "async_write_ha_state") as write_state:
        entity._handle_coordinator_update()

    write_state.assert_called_once_with()


async def test_refresh_button():
    """Refresh is always available and requests a coordinator refresh."""
    platform = SimpleNamespace(uid_base="inverter_1")
    coordinator = _coordinator(last_update_success=False)
    entity = SolarEdgeRefreshButton(platform, None, coordinator)

    assert entity.unique_id == "inverter_1_refresh"
    assert entity.name == "Refresh"
    assert entity.available is True

    await entity.async_press()

    coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("cls", "suffix", "name", "register", "enabled_default"),
    [
        (
            SolarEdgeCommitControlSettings,
            "bt_commit_pwr_settings",
            "Commit Power Settings",
            "CommitPwrCtlSettings",
            True,
        ),
        (
            SolarEdgeDefaultControlSettings,
            "bt_default_pwr_settings",
            "Default Power Settings",
            "RestorePwrCtlDefaults",
            False,
        ),
    ],
)
class TestControlButtons:
    """Behavior shared by the commit and default power control buttons."""

    @staticmethod
    def _platform(supported=True):
        """Build a fake inverter platform for the control buttons."""
        return SimpleNamespace(
            uid_base="inverter_1",
            has_advanced_power_control=supported,
            advanced_power_control_data="apc_data",
            write=AsyncMock(),
        )

    def test_identity(self, cls, suffix, name, register, enabled_default):
        """Unique id, name, and default enablement."""
        entity = cls(self._platform(), None, _coordinator())

        assert entity.unique_id == f"inverter_1{suffix}"
        assert entity.name == name
        assert entity.entity_registry_enabled_default is enabled_default

    @pytest.mark.parametrize(
        ("supported", "update_ok", "available"),
        [
            (True, True, True),
            (False, True, False),
            (True, False, False),
        ],
    )
    def test_available(
        self,
        cls,
        suffix,
        name,
        register,
        enabled_default,
        supported,
        update_ok,
        available,
    ):
        """Available only when the update succeeded and power control is supported."""
        entity = cls(self._platform(supported), None, _coordinator(update_ok))
        assert entity.available is available

    async def test_press_writes_register(
        self, cls, suffix, name, register, enabled_default
    ):
        """Pressing writes 1 to the register, then requests a refresh."""
        platform = self._platform()
        coordinator = _coordinator()
        entity = cls(platform, None, coordinator)

        await entity.async_press()

        platform.write.assert_awaited_once_with("apc_data", register, 1)
        coordinator.async_request_refresh.assert_awaited_once_with()
