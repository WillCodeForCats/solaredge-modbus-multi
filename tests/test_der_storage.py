"""Tests for DER Storage Capacity (SunSpec model 713) on the inverter device.

The DER storage has no device of its own: its sensors are on the inverter
device, enabled by default only for a non-zero first value, and the inverter
skips reading the block when none of them are enabled. Devices created by
earlier versions are removed on setup.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from modbus_connection.exceptions import ModbusExceptionError
from modbus_connection.mock import MockModbusConnection
from modbus_connection.model.sunspec import SunSpecModel
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi import (
    _async_migrate_legacy_der_entities,
    _async_remove_legacy_der_devices,
)
from custom_components.solaredge_modbus_multi.components import DERStorageCapacity
from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.hub import SolarEdgeInverter
from custom_components.solaredge_modbus_multi.sensor import (
    SolarEdgeDERStorageSOC,
    SolarEdgeDERStorageSOH,
    SolarEdgeDERStorageStatus,
)


def _platform(*ders):
    return SimpleNamespace(
        uid_base="inv", der_storage=list(ders), der_storage_listeners=set()
    )


def _der(soc=None, soh=None, sta=None):
    return SimpleNamespace(SoC=soc, SoH=soh, Sta=sta)


# --- default enabled state ---------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), (0, False), (0.0, False), (1, True), (55.5, True), (100, True)],
)
def test_soc_enabled_default_depends_on_first_value(value, expected):
    """Test soc enabled default depends on first value."""
    entity = SolarEdgeDERStorageSOC(_platform(_der(soc=value)), None, None, 1)
    assert entity.entity_registry_enabled_default is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), (0, False), (0.0, False), (1, True), (97.0, True)],
)
def test_soh_enabled_default_depends_on_first_value(value, expected):
    """Test soh enabled default depends on first value."""
    entity = SolarEdgeDERStorageSOH(_platform(_der(soh=value)), None, None, 1)
    assert entity.entity_registry_enabled_default is expected


def test_status_disabled_by_default():
    """Test status disabled by default."""
    entity = SolarEdgeDERStorageStatus(_platform(_der(sta=3)), None, None, 1)
    assert entity.entity_registry_enabled_default is False


def test_soc_not_implemented_value_disables_by_default():
    """Test soc not implemented value disables by default."""
    # SunSpecNotImpl.FLOAT32 is 0x7FC00000, a NaN
    entity = SolarEdgeDERStorageSOC(_platform(_der(soc=float("nan"))), None, None, 1)
    assert entity.entity_registry_enabled_default is False


# --- names and unique IDs ----------------------------------------------------


def test_single_block_name_and_unique_id():
    """Test single block name and unique id."""
    soc = SolarEdgeDERStorageSOC(_platform(_der()), None, None, 1)
    assert soc.name == "Storage State of Charge"
    assert soc.unique_id == "inv_storage_1_soc"


def test_soh_and_status_unique_ids():
    """Test soh and status unique ids."""
    platform = _platform(_der())
    soh = SolarEdgeDERStorageSOH(platform, None, None, 1)
    status = SolarEdgeDERStorageStatus(platform, None, None, 1)
    assert soh.unique_id == "inv_storage_1_soh"
    assert status.unique_id == "inv_storage_1_status"


def test_multiple_blocks_are_numbered_and_keep_unique_ids():
    """Test multiple blocks are numbered and keep unique ids."""
    platform = _platform(_der(), _der())
    second = SolarEdgeDERStorageSOC(platform, None, None, 2)
    assert second.name == "Storage 2 State of Charge"
    assert second.unique_id == "inv_storage_2_soc"


# --- listener registration ---------------------------------------------------


async def test_entity_registers_as_listener_only_while_added(hass):
    """Test entity registers as listener only while added."""
    platform = _platform(_der(soc=50))
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), config_entry=None, name="test"
    )
    entity = SolarEdgeDERStorageSOC(platform, None, coordinator, 1)
    entity.hass = hass
    entity.entity_id = "sensor.inv_battery_state_of_energy"

    await entity.async_added_to_hass()
    assert platform.der_storage_listeners == {entity}

    await entity.async_will_remove_from_hass()
    assert platform.der_storage_listeners == set()


# --- skipping the read -------------------------------------------------------


def _make_inverter(component_update):
    stub_hub = SimpleNamespace(
        connection=MockModbusConnection(), component_update=component_update
    )
    inverter = SolarEdgeInverter(1, stub_hub)
    unit = stub_hub.connection.for_unit(1)
    model = SunSpecModel(model_id=713, address=41438, length=7)
    inverter.der_storage = [DERStorageCapacity(unit, model)]
    return inverter


async def test_read_der_storage_skipped_without_listeners():
    """Test read der storage skipped without listeners."""
    component_update = AsyncMock()
    inverter = _make_inverter(component_update)

    await inverter.read_der_storage()

    component_update.assert_not_called()


async def test_read_der_storage_reads_with_a_listener():
    """Test read der storage reads with a listener."""
    component_update = AsyncMock()
    inverter = _make_inverter(component_update)
    inverter.der_storage_listeners.add(object())

    await inverter.read_der_storage()

    component_update.assert_awaited_once_with(1, inverter.der_storage[0])


async def test_init_der_storage_reads_without_listeners_and_skips_failures():
    """Test init der storage reads without listeners and skips failures."""
    component_update = AsyncMock(side_effect=[None, ModbusExceptionError(2, "bad")])
    stub_hub = SimpleNamespace(
        connection=MockModbusConnection(), component_update=component_update
    )
    inverter = SolarEdgeInverter(1, stub_hub)
    models = [
        SunSpecModel(model_id=713, address=41438, length=7),
        SunSpecModel(model_id=713, address=41500, length=7),
    ]

    await inverter.init_der_storage(models)

    assert component_update.await_count == 2
    assert len(inverter.der_storage) == 1


# --- legacy device cleanup ---------------------------------------------------


def _setup_registry(hass, legacy_identifier="inv_DERB1"):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    inverter_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "inv")}
    )
    legacy_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, legacy_identifier)}
    )
    # State of Charge was re-registered on the inverter device; the old
    # model sensor is still on the legacy device
    soc = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "inv_DERB1_battery_soe",
        config_entry=entry,
        device_id=inverter_device.id,
    )
    model_sensor = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "inv_DERB1_model",
        config_entry=entry,
        device_id=legacy_device.id,
    )
    return entry, device_registry, entity_registry, soc, model_sensor, legacy_device


async def test_legacy_der_device_and_its_entities_removed(hass):
    """Test legacy der device and its entities removed."""
    entry, device_registry, entity_registry, soc, model_sensor, legacy = (
        _setup_registry(hass)
    )
    hub = SimpleNamespace(inverters=[_platform(_der())])

    _async_remove_legacy_der_devices(hass, entry, hub)

    assert device_registry.async_get(legacy.id) is None
    assert entity_registry.async_get(model_sensor.entity_id) is None
    # the entity on the inverter device and the inverter device survive
    assert entity_registry.async_get(soc.entity_id) is not None
    assert device_registry.async_get_device(identifiers={(DOMAIN, "inv")})


async def test_legacy_device_kept_when_no_der_block_found(hass):
    """Test legacy device kept when no der block found."""
    entry, device_registry, entity_registry, _soc, model_sensor, legacy = (
        _setup_registry(hass)
    )
    hub = SimpleNamespace(inverters=[_platform()])

    _async_remove_legacy_der_devices(hass, entry, hub)

    assert device_registry.async_get(legacy.id) is not None
    assert entity_registry.async_get(model_sensor.entity_id) is not None


async def test_other_devices_not_removed(hass):
    """Test other devices not removed."""
    entry, device_registry, _, _, _, _ = _setup_registry(
        hass, legacy_identifier="inv_DERB2"
    )
    hub = SimpleNamespace(inverters=[_platform(_der())])

    _async_remove_legacy_der_devices(hass, entry, hub)

    # DERB2 is not one of the blocks found, so it is left alone
    assert device_registry.async_get_device(identifiers={(DOMAIN, "inv_DERB2")})
    assert device_registry.async_get_device(identifiers={(DOMAIN, "inv")})


async def test_legacy_der_soc_keeps_entity_id_and_unsupported_removed(hass):
    """Test legacy der soc keeps entity id and unsupported removed."""
    entry, _, entity_registry, soc, _model, legacy = _setup_registry(hass)
    unsupported = [
        entity_registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"inv_DERB1_{suffix}",
            config_entry=entry,
            device_id=legacy.id,
        )
        for suffix in ("battery_soh", "status")
    ]
    hub = SimpleNamespace(inverters=[_platform(_der())])

    _async_migrate_legacy_der_entities(hass, hub)

    assert entity_registry.async_get(soc.entity_id).unique_id == "inv_storage_1_soc"
    for entity in unsupported:
        assert entity_registry.async_get(entity.entity_id) is None


async def test_legacy_der_entity_not_migrated_when_new_one_exists(hass):
    """Test legacy der entity not migrated when new one exists."""
    entry, _, entity_registry, _soc, _model, legacy = _setup_registry(hass)
    old = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "inv_DERB1_battery_soe",
        config_entry=entry,
        device_id=legacy.id,
    )
    new = entity_registry.async_get_or_create(
        "sensor", DOMAIN, "inv_storage_1_soc", config_entry=entry
    )
    hub = SimpleNamespace(inverters=[_platform(_der())])

    _async_migrate_legacy_der_entities(hass, hub)

    assert entity_registry.async_get(old.entity_id).unique_id == "inv_DERB1_battery_soe"
    assert entity_registry.async_get(new.entity_id).unique_id == "inv_storage_1_soc"
