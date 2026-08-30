"""Tests for SolarEdgeWriteCount in sensor.py.

Added in 1c201ff "Add sensor SolarEdgeWriteCount" to track modbus write commands
for flash-wear visibility (see discussion #727).

95b9d9e "Add a flag to not track a write" (Active Power Limit and CosPhi are
dynamic setpoints that aren't saved to inverter flash, so they shouldn't count
against the flash-wear counter).
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.solaredge_modbus_multi.hub import SolarEdgeInverter
from custom_components.solaredge_modbus_multi.sensor import SolarEdgeWriteCount


def _make_platform(write_count=0):
    return SimpleNamespace(
        uid_base="inverter_1",
        write_count=write_count,
        write_count_listeners=set(),
    )


def _make_inverter():
    stub_hub = SimpleNamespace(write_registers=AsyncMock())
    return SolarEdgeInverter(1, stub_hub)


def _make_entity(hass, platform):
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), config_entry=None, name="test"
    )
    entity = SolarEdgeWriteCount(platform, None, coordinator)
    entity.hass = hass
    entity.entity_id = "sensor.inverter_1_write_count"
    return entity


def test_unique_id():
    entity = SolarEdgeWriteCount(_make_platform(), None, None)
    assert entity.unique_id == "inverter_1_write_count"


def test_name():
    entity = SolarEdgeWriteCount(_make_platform(), None, None)
    assert entity.name == "Write Count"


def test_always_available():
    entity = SolarEdgeWriteCount(_make_platform(), None, None)
    assert entity.available is True


def test_native_value_reads_from_platform():
    entity = SolarEdgeWriteCount(_make_platform(write_count=7), None, None)
    assert entity.native_value == 7


def test_write_count_updated_writes_ha_state(monkeypatch):
    entity = SolarEdgeWriteCount(_make_platform(), None, None)
    calls = []
    monkeypatch.setattr(entity, "async_write_ha_state", lambda: calls.append(True))

    entity._write_count_updated()

    assert calls == [True]


async def test_restores_last_state_on_add(hass):
    platform = _make_platform(write_count=0)
    entity = _make_entity(hass, platform)
    mock_restore_cache(hass, [State(entity.entity_id, "42")])

    await entity.async_added_to_hass()

    assert platform.write_count == 42
    assert entity._write_count_updated in platform.write_count_listeners


@pytest.mark.parametrize("last_state", [STATE_UNAVAILABLE, STATE_UNKNOWN])
async def test_does_not_restore_unavailable_or_unknown(hass, last_state):
    platform = _make_platform(write_count=3)
    entity = _make_entity(hass, platform)
    mock_restore_cache(hass, [State(entity.entity_id, last_state)])

    await entity.async_added_to_hass()

    assert platform.write_count == 3


async def test_does_not_restore_non_numeric_state(hass):
    # Checks the `except ValueError: pass` condition
    platform = _make_platform(write_count=3)
    entity = _make_entity(hass, platform)
    mock_restore_cache(hass, [State(entity.entity_id, "not-a-number")])

    await entity.async_added_to_hass()

    assert platform.write_count == 3


async def test_removes_listener_on_remove(hass):
    platform = _make_platform()
    entity = _make_entity(hass, platform)
    mock_restore_cache(hass, [])
    await entity.async_added_to_hass()
    assert entity._write_count_updated in platform.write_count_listeners

    await entity.async_will_remove_from_hass()

    assert entity._write_count_updated not in platform.write_count_listeners


async def test_write_registers_counts_by_default():
    inverter = _make_inverter()
    calls = []
    inverter.write_count_listeners.add(lambda: calls.append(True))

    await inverter.write_registers(40001, [1])

    inverter.hub.write_registers.assert_awaited_once_with(1, 40001, [1])
    assert inverter.write_count == 1
    assert calls == [True]


async def test_write_registers_count_write_false_skips_counting():
    # 95b9d9e "Add a flag to not track a write" - the write itself must still
    # happen, only the counter/listener side is skipped.
    inverter = _make_inverter()
    calls = []
    inverter.write_count_listeners.add(lambda: calls.append(True))

    await inverter.write_registers(40001, [1], count_write=False)

    inverter.hub.write_registers.assert_awaited_once_with(1, 40001, [1])
    assert inverter.write_count == 0
    assert calls == []
