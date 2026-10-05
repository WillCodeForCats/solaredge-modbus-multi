"""SunSpec accumulators at the LIMIT32 sentinel are unavailable, then recover.

A uint32 can never exceed 0xFFFFFFFF, so the former `> LIMIT32` guard never
fired and the sentinel would have been scaled and published as a counter value.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.solaredge_modbus_multi.const import SunSpecAccum
from custom_components.solaredge_modbus_multi.sensor import (
    MeterVAhIE,
    MetervarhIE,
    SolarEdgeACEnergy,
)


def _platform(model: dict) -> MagicMock:
    platform = MagicMock()
    platform.uid_base = "se_dev_1"
    platform.online = True
    platform.decoded_model = model
    return platform


def test_inverter_ac_energy_sentinel_then_recovers(mock_config_entry, mock_coordinator):
    platform = _platform({"AC_Energy_WH": 123456, "AC_Energy_WH_SF": 0})
    sensor = SolarEdgeACEnergy(platform, mock_config_entry, mock_coordinator)

    assert sensor.available is True

    platform.decoded_model["AC_Energy_WH"] = SunSpecAccum.LIMIT32
    assert sensor.available is False

    platform.decoded_model["AC_Energy_WH"] = 123457
    assert sensor.available is True
    assert sensor._value == 123457


@pytest.mark.parametrize(
    ("sensor_class", "value_key", "sf_key"),
    [
        (MeterVAhIE, "M_VAh_Exported", "M_VAh_SF"),
        (MetervarhIE, "M_varh_Export_Q1", "M_varh_SF"),
    ],
)
def test_meter_accumulator_sentinel_then_recovers(
    sensor_class, value_key, sf_key, mock_config_entry, mock_coordinator
):
    phase = value_key.split("_", 2)[2]
    platform = _platform({value_key: 5000, sf_key: 0})
    sensor = sensor_class(platform, mock_config_entry, mock_coordinator, phase)

    assert sensor.native_value == 5000

    platform.decoded_model[value_key] = SunSpecAccum.LIMIT32
    assert sensor.native_value is None

    platform.decoded_model[value_key] = 5001
    assert sensor.native_value == 5001
