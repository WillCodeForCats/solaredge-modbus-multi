"""Tests for SolarEdgeSensorBase.scale_factor in sensor.py."""

import pytest

from custom_components.solaredge_modbus_multi.sensor import SolarEdgeSensorBase

# 4b7a8e6 "Remove scale_factor helper function" and revert d0b0e77 (both
# PR #503, code-quality) - scale_factor moved from a standalone
# function to a method on the base class.
#
# 72948a1 "Validate sunspec scale factor range" (PR #43) - added the
# SUNSPEC_SF_RANGE check for scale_factor. In order to test this we'd
# need to modify scale_factor to raise an exception if sf not in SUNSPEC_SF_RANGE.


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
