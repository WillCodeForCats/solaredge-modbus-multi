"""Tests diagnostics keys for meters/batteries/DER storage."""

from types import SimpleNamespace

from modbus_connection.mock import MockModbusConnection
from modbus_connection.model.sunspec import SunSpecModel, SunSpecModels
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.components import (
    AdvancedPowerControl,
    BatteryData,
    BatteryInfo,
    DERStorageCapacity,
    EvseCommon,
    GlobalDynamicPowerControl,
    InverterCommon,
    InverterData,
    MeterData,
    MeterInfo,
    MmpptCommon,
    MmpptData,
    SiteLimitControl,
    StorageControl,
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


def _fake_inverter(inverter_unit_id, der_count=0):
    unit = MockModbusConnection().for_unit(inverter_unit_id)
    model = SunSpecModel(model_id=713, address=41438, length=7)
    return SimpleNamespace(
        inverter_unit_id=inverter_unit_id,
        device_info={"identifiers": {(DOMAIN, f"inverter_{inverter_unit_id}")}},
        global_power_control=None,
        advanced_power_control=None,
        site_limit_control=None,
        inverter_common=InverterCommon(unit),
        inverter_data=InverterData(unit),
        mmppt_common=MmpptCommon(unit),
        mmppt_data=MmpptData(unit),
        global_power_control_data=GlobalDynamicPowerControl(unit),
        advanced_power_control_data=AdvancedPowerControl(unit),
        site_limit_control_data=SiteLimitControl(unit),
        storage_control_data=StorageControl(unit),
        sunspec_models=None,
        use_status_vendor4=False,
        use_mmppt_units=False,
        has_battery=None,
        has_storage_control=False,
        has_global_power_control=False,
        has_advanced_power_control=False,
        has_site_limit_control=False,
        der_storage=[DERStorageCapacity(unit, model) for _ in range(der_count)],
    )


def _fake_evse(inverter_unit_id, sunspec_models=None):
    unit = MockModbusConnection().for_unit(inverter_unit_id)
    return SimpleNamespace(
        device_info={"identifiers": {(DOMAIN, f"evse_{inverter_unit_id}")}},
        evse_unit_id=inverter_unit_id,
        evse_common=EvseCommon(unit),
        sunspec_models=sunspec_models,
    )


def _fake_hub(meters=(), batteries=(), inverters=(), evses=()):
    return SimpleNamespace(
        inverters=list(inverters),
        meters=list(meters),
        batteries=list(batteries),
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
    """Test meters on different inverters get distinct keys."""
    hub = _fake_hub(meters=[_fake_meter(1, 1), _fake_meter(2, 1)])

    data = await _get_diagnostics(hass, hub)

    meter_keys = [k for k in data if k.startswith("meter_id_")]
    assert len(meter_keys) == 2
    assert "meter_id_I1_M1" in data
    assert "meter_id_I2_M1" in data


async def test_batteries_on_different_inverters_get_distinct_keys(hass):
    """Test batteries on different inverters get distinct keys."""
    hub = _fake_hub(batteries=[_fake_battery(1, 1), _fake_battery(2, 1)])

    data = await _get_diagnostics(hass, hub)

    battery_keys = [k for k in data if k.startswith("battery_id_")]
    assert len(battery_keys) == 2
    assert "battery_id_I1_B1" in data
    assert "battery_id_I2_B1" in data


async def test_der_storage_on_different_inverters_get_distinct_keys(hass):
    """Test der batteries on different inverters get distinct keys."""
    hub = _fake_hub(inverters=[_fake_inverter(1, 1), _fake_inverter(2, 1)])

    data = await _get_diagnostics(hass, hub)

    der_keys = [k for k in data if k.startswith("der_storage_id_")]
    assert len(der_keys) == 2
    assert "der_storage_id_I1_storage_1" in data
    assert "der_storage_id_I2_storage_1" in data


async def test_der_storage_and_regular_battery_keys_do_not_collide(hass):
    """Test der storage and regular battery keys do not collide."""
    hub = _fake_hub(
        batteries=[_fake_battery(1, 1)],
        inverters=[_fake_inverter(1, 1)],
    )

    data = await _get_diagnostics(hass, hub)

    assert "battery_id_I1_B1" in data
    assert "der_storage_id_I1_storage_1" in data


async def test_evse_includes_sunspec_scan_results(hass):
    """Test evse includes sunspec scan results."""
    models = SunSpecModels()
    models[1] = [SunSpecModel(model_id=1, address=40002, length=65)]
    hub = _fake_hub(evses=[_fake_evse(1, sunspec_models=models)])

    data = await _get_diagnostics(hass, hub)

    assert data["evse_unit_id_1"]["sunspec_models"] == [
        {"model_id": 1, "address": 40002, "length": 65}
    ]


async def test_evse_sunspec_scan_defaults_to_none(hass):
    """Test evse sunspec scan defaults to none."""
    hub = _fake_hub(evses=[_fake_evse(1)])

    data = await _get_diagnostics(hass, hub)

    assert data["evse_unit_id_1"]["sunspec_models"] is None
