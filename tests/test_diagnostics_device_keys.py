"""Tests diagnostics keys for meters/batteries/der_batteries."""

from types import SimpleNamespace

from modbus_connection.mock import MockModbusConnection
from modbus_connection.model.sunspec import SunSpecModel, SunSpecModels
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.components import (
    BatteryData,
    BatteryInfo,
    DERStorageCapacity,
    EvseCommon,
    MeterData,
    MeterInfo,
)
from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _fake_meter(inverter_unit_id, meter_id):
    unit = MockModbusConnection().for_unit(inverter_unit_id)
    return SimpleNamespace(
        device_info={"identifiers": {(DOMAIN, f"meter_{inverter_unit_id}_{meter_id}")}},
        inverter_unit_id=inverter_unit_id,
        meter_id=meter_id,
        meter_info=MeterInfo(unit),
        meter_data=MeterData(unit),
    )


def _fake_battery(inverter_unit_id, battery_id):
    unit = MockModbusConnection().for_unit(inverter_unit_id)
    return SimpleNamespace(
        device_info={
            "identifiers": {(DOMAIN, f"battery_{inverter_unit_id}_{battery_id}")}
        },
        inverter_unit_id=inverter_unit_id,
        battery_id=battery_id,
        battery_info=BatteryInfo(unit),
        battery_data=BatteryData(unit),
    )


def _fake_der_battery(inverter_unit_id, battery_id):
    unit = MockModbusConnection().for_unit(inverter_unit_id)
    model = SunSpecModel(model_id=713, address=41438, length=7)
    return SimpleNamespace(
        device_info={
            "identifiers": {(DOMAIN, f"der_battery_{inverter_unit_id}_{battery_id}")}
        },
        inverter_unit_id=inverter_unit_id,
        battery_id=battery_id,
        der_storage_capacity_data=DERStorageCapacity(unit, model),
    )


def _fake_evse(inverter_unit_id, sunspec_models=None):
    unit = MockModbusConnection().for_unit(inverter_unit_id)
    return SimpleNamespace(
        device_info={"identifiers": {(DOMAIN, f"evse_{inverter_unit_id}")}},
        evse_unit_id=inverter_unit_id,
        evse_common=EvseCommon(unit),
        sunspec_models=sunspec_models,
    )


def _fake_hub(meters=(), batteries=(), der_batteries=(), evses=()):
    return SimpleNamespace(
        inverters=[],
        meters=list(meters),
        batteries=list(batteries),
        der_batteries=list(der_batteries),
        evses=list(evses),
    )


async def _get_diagnostics(hass, hub):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": hub,
        "dependency_versions": {"tmodbus": "0.6.2", "modbus-connection": "4.12.1"},
    }

    return await async_get_config_entry_diagnostics(hass, entry)


async def test_meters_on_different_inverters_get_distinct_keys(hass):
    hub = _fake_hub(meters=[_fake_meter(1, 1), _fake_meter(2, 1)])

    data = await _get_diagnostics(hass, hub)

    meter_keys = [k for k in data if k.startswith("meter_id_")]
    assert len(meter_keys) == 2
    assert "meter_id_I1_M1" in data
    assert "meter_id_I2_M1" in data


async def test_batteries_on_different_inverters_get_distinct_keys(hass):
    hub = _fake_hub(batteries=[_fake_battery(1, 1), _fake_battery(2, 1)])

    data = await _get_diagnostics(hass, hub)

    battery_keys = [k for k in data if k.startswith("battery_id_")]
    assert len(battery_keys) == 2
    assert "battery_id_I1_B1" in data
    assert "battery_id_I2_B1" in data


async def test_der_batteries_on_different_inverters_get_distinct_keys(hass):
    hub = _fake_hub(der_batteries=[_fake_der_battery(1, 1), _fake_der_battery(2, 1)])

    data = await _get_diagnostics(hass, hub)

    der_keys = [k for k in data if k.startswith("der_battery_id_")]
    assert len(der_keys) == 2
    assert "der_battery_id_I1_DERB1" in data
    assert "der_battery_id_I2_DERB1" in data


async def test_der_battery_and_regular_battery_keys_do_not_collide(hass):
    hub = _fake_hub(
        batteries=[_fake_battery(1, 1)],
        der_batteries=[_fake_der_battery(1, 1)],
    )

    data = await _get_diagnostics(hass, hub)

    assert "battery_id_I1_B1" in data
    assert "der_battery_id_I1_DERB1" in data


async def test_evse_includes_sunspec_scan_results(hass):
    models = SunSpecModels()
    models[1] = [SunSpecModel(model_id=1, address=40002, length=65)]
    hub = _fake_hub(evses=[_fake_evse(1, sunspec_models=models)])

    data = await _get_diagnostics(hass, hub)

    assert data["evse_unit_id_1"]["sunspec_models"] == [
        {"model_id": 1, "address": 40002, "length": 65}
    ]


async def test_evse_sunspec_scan_defaults_to_none(hass):
    hub = _fake_hub(evses=[_fake_evse(1)])

    data = await _get_diagnostics(hass, hub)

    assert data["evse_unit_id_1"]["sunspec_models"] is None
