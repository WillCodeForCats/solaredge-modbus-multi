"""Tests for StorageChargeLimit/StorageDischargeLimit's battery flag check."""

from types import SimpleNamespace

import pytest

from custom_components.solaredge_modbus_multi.number import (
    StorageChargeLimit,
    StorageDischargeLimit,
)


def _make_platform(has_battery):
    return SimpleNamespace(has_battery=has_battery)


@pytest.mark.parametrize("entity_class", [StorageChargeLimit, StorageDischargeLimit])
def test_disabled_by_default_without_a_battery(entity_class):
    """Test disabled by default without a battery."""
    entity = entity_class(_make_platform(has_battery=False), None, None)
    assert entity.entity_registry_enabled_default is False


@pytest.mark.parametrize("entity_class", [StorageChargeLimit, StorageDischargeLimit])
def test_enabled_by_default_with_a_battery(entity_class):
    """Test enabled by default with a battery."""
    entity = entity_class(_make_platform(has_battery=True), None, None)
    assert entity.entity_registry_enabled_default is True


@pytest.mark.parametrize("entity_class", [StorageChargeLimit, StorageDischargeLimit])
def test_disabled_by_default_when_battery_not_yet_detected(entity_class):
    """Test disabled by default when battery not yet detected."""
    entity = entity_class(_make_platform(has_battery=None), None, None)
    assert entity.entity_registry_enabled_default is False
