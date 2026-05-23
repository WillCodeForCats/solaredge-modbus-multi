"""Unit tests for helper functions in helpers.py."""

from __future__ import annotations

import struct
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.solaredge_modbus_multi.helpers import (
    check_device_id,
    device_list_from_string,
    float_to_hex,
    host_valid,
    int_list_to_string,
    update_accum,
)

# ---------------------------------------------------------------------------
# float_to_hex
# ---------------------------------------------------------------------------


class TestFloatToHex:
    def test_known_value(self):
        """Known IEEE 754 little-endian: 1.0 → 0x3f800000."""
        assert float_to_hex(1.0) == hex(struct.unpack("<I", struct.pack("<f", 1.0))[0])

    def test_zero(self):
        assert float_to_hex(0.0) == "0x0"

    def test_negative(self):
        result = float_to_hex(-1.0)
        assert result.startswith("0x")

    def test_not_implemented_marker(self):
        """SunSpec FLOAT32 not-implemented value 0x7FC00000."""
        ni = struct.unpack("<f", struct.pack("<I", 0x7FC00000))[0]
        assert float_to_hex(ni) == hex(0x7FC00000)

    def test_integer_input(self):
        """Accepts int as well as float."""
        assert float_to_hex(0) == "0x0"

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            float_to_hex("not a number")

    def test_invalid_type_none_raises(self):
        with pytest.raises(TypeError):
            float_to_hex(None)

    def test_struct_error_raises_value_error(self):
        with patch("struct.pack", side_effect=struct.error("mocked")):
            with pytest.raises(ValueError, match="Error converting"):
                float_to_hex(1.0)


# ---------------------------------------------------------------------------
# int_list_to_string
# ---------------------------------------------------------------------------


class TestIntListToString:
    def test_ascii_string(self):
        """Pack ASCII characters into 16-bit words and decode them."""
        # "AB" = 0x4142
        assert int_list_to_string([0x4142]) == "AB"

    def test_empty_list(self):
        assert int_list_to_string([]) == ""

    def test_null_padding_stripped(self):
        """Trailing null bytes from fixed-length SunSpec strings are removed."""
        # "A\x00" padded word
        result = int_list_to_string([0x4100])
        assert "\x00" not in result
        assert result == "A"

    def test_trailing_whitespace_stripped(self):
        # "A " — trailing space should be stripped by rstrip()
        result = int_list_to_string([0x4120])
        assert result == "A"

    def test_invalid_utf8_ignored(self):
        """Invalid UTF-8 sequences are silently dropped."""
        result = int_list_to_string([0xFFFF])
        assert isinstance(result, str)

    def test_multi_word(self):
        # "Hello" across multiple words: He=0x4865, ll=0x6C6C, o\x00=0x6F00
        result = int_list_to_string([0x4865, 0x6C6C, 0x6F00])
        assert result == "Hello"


# ---------------------------------------------------------------------------
# update_accum
# ---------------------------------------------------------------------------


class _Accum:
    """Minimal object with a .last attribute as update_accum expects."""

    def __init__(self, last=None):
        self.last = last


class TestUpdateAccum:
    def test_first_call_sets_last(self):
        acc = _Accum(last=None)
        result = update_accum(acc, 100)
        assert result == 100
        assert acc.last == 100

    def test_increasing_value(self):
        acc = _Accum(last=100)
        result = update_accum(acc, 200)
        assert result == 200
        assert acc.last == 200

    def test_equal_value_accepted(self):
        """Same value on consecutive polls is valid (not a decrease)."""
        acc = _Accum(last=100)
        result = update_accum(acc, 100)
        assert result == 100

    def test_decreasing_value_raises(self):
        acc = _Accum(last=200)
        with pytest.raises(ValueError, match="increasing"):
            update_accum(acc, 100)

    def test_zero_value_raises(self):
        acc = _Accum(last=None)
        with pytest.raises(ValueError):
            update_accum(acc, 0)

    def test_negative_value_raises(self):
        acc = _Accum(last=None)
        with pytest.raises(ValueError):
            update_accum(acc, -1)


# ---------------------------------------------------------------------------
# host_valid
# ---------------------------------------------------------------------------


class TestHostValid:
    def test_valid_ipv4(self):
        assert host_valid("192.168.1.1")

    def test_valid_ipv4_broadcast(self):
        assert host_valid("10.0.0.1")

    def test_valid_ipv6(self):
        assert host_valid("::1")

    def test_out_of_range_octets_accepted_as_hostname(self):
        # 999.x.x.x fails ipaddress but matches DOMAIN_REGEX as a dotted hostname
        assert host_valid("999.999.999.999")

    def test_leading_dash_rejected(self):
        assert not host_valid("-invalid.host")

    def test_valid_hostname(self):
        assert host_valid("inverter.local")

    def test_valid_hostname_subdomain(self):
        assert host_valid("my-inverter.home.lan")

    def test_invalid_hostname_spaces(self):
        assert not host_valid("not a host")

    def test_empty_string(self):
        assert not host_valid("")


# ---------------------------------------------------------------------------
# check_device_id
# ---------------------------------------------------------------------------


class TestCheckDeviceId:
    def test_valid_low_boundary(self):
        assert check_device_id("1") == 1

    def test_valid_high_boundary(self):
        assert check_device_id("247") == 247

    def test_valid_mid(self):
        assert check_device_id("10") == 10

    def test_accepts_int(self):
        assert check_device_id(5) == 5

    def test_zero_raises(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("0")

    def test_above_247_raises(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("248")

    def test_negative_raises(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("-1")

    def test_non_integer_string_raises(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("abc")

    def test_empty_string_raises(self):
        with pytest.raises(HomeAssistantError):
            check_device_id("")


# ---------------------------------------------------------------------------
# device_list_from_string
# ---------------------------------------------------------------------------


class TestDeviceListFromString:
    def test_single_id(self):
        assert device_list_from_string("1") == [1]

    def test_multiple_ids(self):
        assert device_list_from_string("1,3,5") == [1, 3, 5]

    def test_range(self):
        assert device_list_from_string("1-3") == [1, 2, 3]

    def test_mixed_range_and_single(self):
        assert device_list_from_string("1,3-5,7") == [1, 3, 4, 5, 7]

    def test_deduplication(self):
        assert device_list_from_string("1,1,2") == [1, 2]

    def test_sorted_output(self):
        assert device_list_from_string("5,1,3") == [1, 3, 5]

    def test_whitespace_around_ids(self):
        assert device_list_from_string(" 1 , 2 , 3 ") == [1, 2, 3]

    def test_invalid_range_multiple_dashes_raises(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("1-2-3")

    def test_range_end_less_than_start_raises(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("5-3")

    def test_out_of_bounds_id_raises(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("0")

    def test_out_of_bounds_high_raises(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("248")

    def test_empty_entry_raises(self):
        with pytest.raises(HomeAssistantError):
            device_list_from_string("1,,3")
