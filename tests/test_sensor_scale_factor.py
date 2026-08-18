"""Tests for SolarEdgeSensorBase.scale_factor in sensor.py."""

import pytest

from custom_components.solaredge_modbus_multi.sensor import SolarEdgeSensorBase


@pytest.mark.parametrize(
    "value, sf, expected",
    [
        (100, -2, 1.0),
        (500, 1, 5000),
        (0, -3, 0.0),
        (-250, -1, -25.0),
        (1, 0, 1),
    ],
)
def test_scale_factor(value, sf, expected):
    assert SolarEdgeSensorBase.scale_factor(None, value, sf) == expected
