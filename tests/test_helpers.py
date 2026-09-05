"""Tests for custom_components/solaredge_modbus_multi/helpers.py."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.solaredge_modbus_multi.helpers import (
    check_device_id,
    device_list_from_string,
    float_to_hex,
    host_valid,
)


class TestFloatToHex:
    # f08890d "Raise TypeError from struct.error in helper" (PR #468) - struct.error from bad input
    # b0897d8 "Improvements in float_to_hex" (PR #752) - added the isinstance check

    @pytest.mark.parametrize(
        "value",
        [1.0, -1.0, 0, 0.0, 3.14159],
    )
    def test_returns_hex_string(self, value):
        result = float_to_hex(value)
        assert isinstance(result, str)
        assert result.startswith("0x")
        # A 32-bit float is 4 bytes -> 8 hex digits
        int(result, 16)

    def test_non_numeric_raises_type_error(self):
        with pytest.raises(TypeError):
            float_to_hex("not a number")

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            float_to_hex(None)


class TestHostValid:
    @pytest.mark.parametrize("host", ["192.168.1.100", "10.0.0.1"])
    def test_valid_ipv4(self, host):
        assert host_valid(host)

    @pytest.mark.parametrize("host", ["::1", "2001:db8::1"])
    def test_valid_ipv6(self, host):
        assert host_valid(host)

    def test_valid_hostname(self):
        assert host_valid("inverter.local")

    @pytest.mark.parametrize("host", ["not a hostname!", "-bad-.-domain-"])
    def test_invalid_host(self, host):
        assert not host_valid(host)


class TestDeviceListFromString:
    # 3adb066 "Add new helpers for non sequential IDs"
    # 9b47f83 "Raise translation keys for device list errors" (PR #636)
    # PR #615, issue #460, and PR #636
    # Added device_list_from_string/check_device_id to replace sequential inverters.

    def test_docstring_example(self):
        assert device_list_from_string("1,3-5,7") == [1, 3, 4, 5, 7]

    @pytest.mark.parametrize("value", ["1", "247"])
    def test_boundary_ids_are_valid(self, value):
        assert device_list_from_string(value) == [int(value)]

    @pytest.mark.parametrize("value", ["0", "248"])
    def test_out_of_range_ids(self, value):
        with pytest.raises(HomeAssistantError):
            device_list_from_string(value)

    def test_overlapping_entries(self):
        assert device_list_from_string("5,1-3,2") == [1, 2, 3, 5]

    def test_reversed_range(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("5-3")

    def test_multi_dash_range(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("1-2-3")

    def test_non_numeric_id(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("abc")

    def test_empty_component(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("")

    def test_whitespace_is_tolerated(self):
        assert device_list_from_string(" 1 , 2 ") == [1, 2]


class TestCheckDeviceId:
    def test_valid_id_returns_int(self):
        assert check_device_id("42") == 42

    def test_empty_string(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("")

    def test_non_numeric(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("abc")
