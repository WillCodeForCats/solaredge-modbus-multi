"""Tests for diagnostics._sunspec_scan()."""

from modbus_connection.model.sunspec import SunSpecModel, SunSpecModels

from custom_components.solaredge_modbus_multi.diagnostics import _sunspec_scan


class _FakeInverter:
    def __init__(self, sunspec_models):
        self.sunspec_models = sunspec_models


def test_sunspec_scan_none_when_scan_never_succeeded():
    inverter = _FakeInverter(None)

    assert _sunspec_scan(inverter) is None


def test_sunspec_scan_orders_by_address_not_insertion_order():
    models = SunSpecModels()
    models[713] = [SunSpecModel(model_id=713, address=40054, length=8)]
    models[103] = [SunSpecModel(model_id=103, address=40002, length=50)]
    inverter = _FakeInverter(models)

    result = _sunspec_scan(inverter)

    assert result == [
        {"model_id": 103, "address": 40002, "length": 50},
        {"model_id": 713, "address": 40054, "length": 8},
    ]


def test_sunspec_scan_includes_repeated_model_ids():
    models = SunSpecModels()
    models[203] = [
        SunSpecModel(model_id=203, address=40070, length=105),
        SunSpecModel(model_id=203, address=40177, length=105),
    ]
    inverter = _FakeInverter(models)

    result = _sunspec_scan(inverter)

    assert len(result) == 2
    assert result[0]["address"] == 40070
    assert result[1]["address"] == 40177
